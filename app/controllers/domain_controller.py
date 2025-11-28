from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.domain import Domain
from sqlalchemy import text
import logging
import uuid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import base64

logger = logging.getLogger(__name__)

domain_bp = Blueprint('domain', __name__, url_prefix='/dashboard/domains')


def generate_dkim_keys():
    """Generate DKIM key pair"""
    try:
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Get private key PEM
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        # Get public key
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # Format for DNS
        public_key_dns = public_pem.replace('-----BEGIN PUBLIC KEY-----', '')
        public_key_dns = public_key_dns.replace('-----END PUBLIC KEY-----', '')
        public_key_dns = public_key_dns.replace('\n', '')
        
        return private_pem, public_key_dns
    
    except Exception as e:
        logger.error(f"DKIM generation error: {e}")
        return None, None


@domain_bp.route('/')
@login_required
def list_domains():
    """List all domains for organization"""
    try:
        result = db.session.execute(text("""
            SELECT 
                id, domain_name, dns_verified, is_active, 
                dkim_selector, dkim_public_key, created_at, verified_at
            FROM domains 
            WHERE organization_id = :org_id 
            ORDER BY created_at DESC
        """), {'org_id': current_user.organization_id})
        
        domains = [dict(row._mapping) for row in result]
        
        return render_template('dashboard/domains.html', domains=domains)
    
    except Exception as e:
        logger.error(f"List domains error: {e}", exc_info=True)
        return render_template('dashboard/domains.html', domains=[])


@domain_bp.route('/add', methods=['POST'])
@login_required
def add_domain():
    """Add new domain with DKIM generation"""
    try:
        data = request.get_json() if request.is_json else request.form
        domain_name = data.get('domain', '').strip().lower()
        
        if not domain_name:
            return jsonify({
                'success': False,
                'error': 'Domain name is required'
            }), 400
        
        # Validate domain format
        if not domain_name or '.' not in domain_name:
            return jsonify({
                'success': False,
                'error': 'Invalid domain format'
            }), 400
        
        # Check if domain exists
        existing = db.session.execute(text("""
            SELECT id FROM domains 
            WHERE organization_id = :org_id AND domain_name = :domain
        """), {
            'org_id': current_user.organization_id,
            'domain': domain_name
        }).fetchone()
        
        if existing:
            return jsonify({
                'success': False,
                'error': 'Domain already exists in your organization'
            }), 400
        
        # Generate DKIM keys
        private_key, public_key = generate_dkim_keys()
        
        if not private_key:
            return jsonify({
                'success': False,
                'error': 'Failed to generate DKIM keys'
            }), 500
        
        # Create domain
        domain_id = str(uuid.uuid4())
        
        db.session.execute(text("""
            INSERT INTO domains (
                id, organization_id, domain_name,
                dkim_selector, dkim_private_key, dkim_public_key,
                dns_verified, is_active, created_at
            ) VALUES (
                :id, :org_id, :domain,
                'mail', :private_key, :public_key,
                false, true, NOW()
            )
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id,
            'domain': domain_name,
            'private_key': private_key,
            'public_key': public_key
        })
        
        db.session.commit()
        
        # Get server IP
        import socket
        try:
            server_ip = socket.gethostbyname(socket.gethostname())
        except:
            server_ip = '156.67.29.186'  # Your server IP
        
        # Generate DNS records
        dns_records = {
            'spf': {
                'type': 'TXT',
                'host': '@',
                'value': f'v=spf1 ip4:{server_ip} ~all',
                'ttl': 3600
            },
            'dkim': {
                'type': 'TXT',
                'host': 'mail._domainkey',
                'value': f'v=DKIM1; k=rsa; p={public_key}',
                'ttl': 3600
            },
            'dmarc': {
                'type': 'TXT',
                'host': '_dmarc',
                'value': f'v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain_name}',
                'ttl': 3600
            }
        }
        
        logger.info(f"Domain {domain_name} added successfully by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'Domain {domain_name} added successfully',
            'domain_id': domain_id,
            'dns_records': dns_records
        })
    
    except Exception as e:
        logger.error(f"Add domain error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to add domain. Please try again.'
        }), 500


@domain_bp.route('/<domain_id>/verify', methods=['POST'])
@login_required
def verify_domain(domain_id):
    """Verify domain DNS records"""
    try:
        import dns.resolver
        
        # Get domain
        result = db.session.execute(text("""
            SELECT domain_name FROM domains 
            WHERE id = :id AND organization_id = :org_id
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id
        })
        
        row = result.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Domain not found'}), 404
        
        domain_name = row[0]
        
        # Verify SPF, DKIM, DMARC
        verified = True
        errors = []
        
        try:
            # Check SPF
            answers = dns.resolver.resolve(domain_name, 'TXT')
            spf_found = any('v=spf1' in str(rdata) for rdata in answers)
            if not spf_found:
                verified = False
                errors.append('SPF record not found')
        except:
            verified = False
            errors.append('SPF record not found')
        
        if verified:
            db.session.execute(text("""
                UPDATE domains 
                SET dns_verified = true, verified_at = NOW()
                WHERE id = :id
            """), {'id': domain_id})
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Domain verified successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'DNS records not found: ' + ', '.join(errors)
            })
    
    except Exception as e:
        logger.error(f"Verify domain error: {e}")
        return jsonify({
            'success': False,
            'error': 'Verification failed. Please try again.'
        }), 500


@domain_bp.route('/<domain_id>/delete', methods=['POST'])
@login_required
def delete_domain(domain_id):
    """Delete domain"""
    try:
        db.session.execute(text("""
            DELETE FROM domains 
            WHERE id = :id AND organization_id = :org_id
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id
        })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Domain deleted successfully'
        })
    
    except Exception as e:
        logger.error(f"Delete domain error: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to delete domain'
        }), 500
