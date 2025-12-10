from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import logging
import uuid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import dns.resolver

logger = logging.getLogger(__name__)

domain_bp = Blueprint('domain', __name__, url_prefix='/dashboard/domains')

# SendBaba Email Infrastructure IPs
SENDING_IPS = [
    '156.67.29.186',   # mail1.sendbaba.com
    '161.97.162.82',   # mail2.sendbaba.com
    '207.244.232.12',  # mail3.sendbaba.com
    '31.220.109.225',  # mail4.sendbaba.com
]


def generate_dkim_keys():
    """Generate DKIM key pair (2048-bit RSA)"""
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
        
        # Format for DNS (remove headers and newlines)
        public_key_dns = public_pem.replace('-----BEGIN PUBLIC KEY-----', '')
        public_key_dns = public_key_dns.replace('-----END PUBLIC KEY-----', '')
        public_key_dns = public_key_dns.replace('\n', '').strip()
        
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
                dkim_selector, dkim_public_key, 
                spf_valid, dkim_valid, dmarc_valid,
                created_at, verified_at
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
        
        # Remove www if present
        if domain_name.startswith('www.'):
            domain_name = domain_name[4:]
        
        if not domain_name:
            return jsonify({
                'success': False,
                'error': 'Domain name is required'
            }), 400
        
        # Validate domain format
        if '.' not in domain_name or len(domain_name) < 4:
            return jsonify({
                'success': False,
                'error': 'Invalid domain format'
            }), 400
        
        # Check if domain exists for this org
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
                'error': 'This domain is already added to your account'
            }), 400
        
        # Generate DKIM keys
        private_key, public_key = generate_dkim_keys()
        
        if not private_key:
            return jsonify({
                'success': False,
                'error': 'Failed to generate DKIM keys. Please try again.'
            }), 500
        
        # Create domain
        domain_id = str(uuid.uuid4())
        
        db.session.execute(text("""
            INSERT INTO domains (
                id, organization_id, domain_name,
                dkim_selector, dkim_private_key, dkim_public_key,
                dns_verified, is_active, 
                spf_valid, dkim_valid, dmarc_valid,
                created_at
            ) VALUES (
                :id, :org_id, :domain,
                'mail', :private_key, :public_key,
                false, true,
                false, false, false,
                NOW()
            )
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id,
            'domain': domain_name,
            'private_key': private_key,
            'public_key': public_key
        })
        
        db.session.commit()
        
        # Generate DNS records for response
        spf_value = 'v=spf1 ' + ' '.join([f'ip4:{ip}' for ip in SENDING_IPS]) + ' ~all'
        
        dns_records = {
            'spf': {
                'type': 'TXT',
                'host': '@',
                'value': spf_value,
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
                'value': f'v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain_name}; fo=1',
                'ttl': 3600
            }
        }
        
        logger.info(f"Domain {domain_name} added by user {current_user.id}")
        
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
    """Verify domain DNS records (SPF, DKIM, DMARC)"""
    try:
        # Get domain
        result = db.session.execute(text("""
            SELECT domain_name, dkim_public_key FROM domains 
            WHERE id = :id AND organization_id = :org_id
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id
        })
        
        row = result.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Domain not found'}), 404
        
        domain_name = row[0]
        dkim_public_key = row[1]
        
        verification_results = {
            'spf': {'valid': False, 'message': ''},
            'dkim': {'valid': False, 'message': ''},
            'dmarc': {'valid': False, 'message': ''}
        }
        
        # Check SPF
        try:
            answers = dns.resolver.resolve(domain_name, 'TXT', lifetime=10)
            for rdata in answers:
                txt_value = str(rdata).strip('"')
                if 'v=spf1' in txt_value:
                    # Check if any of our IPs are included
                    has_our_ip = any(ip in txt_value for ip in SENDING_IPS)
                    if has_our_ip:
                        verification_results['spf'] = {'valid': True, 'message': 'SPF record found with SendBaba IPs'}
                    else:
                        verification_results['spf'] = {'valid': False, 'message': 'SPF record found but missing SendBaba IPs'}
                    break
            if not verification_results['spf']['message']:
                verification_results['spf'] = {'valid': False, 'message': 'No SPF record found'}
        except dns.resolver.NXDOMAIN:
            verification_results['spf'] = {'valid': False, 'message': 'Domain not found'}
        except dns.resolver.NoAnswer:
            verification_results['spf'] = {'valid': False, 'message': 'No SPF record found'}
        except Exception as e:
            verification_results['spf'] = {'valid': False, 'message': f'Error checking SPF: {str(e)}'}
        
        # Check DKIM
        try:
            dkim_domain = f'mail._domainkey.{domain_name}'
            answers = dns.resolver.resolve(dkim_domain, 'TXT', lifetime=10)
            for rdata in answers:
                txt_value = str(rdata).strip('"').replace(' ', '')
                if 'v=DKIM1' in txt_value or 'k=rsa' in txt_value:
                    # Check if the public key matches
                    if dkim_public_key and dkim_public_key[:50] in txt_value:
                        verification_results['dkim'] = {'valid': True, 'message': 'DKIM record verified'}
                    else:
                        verification_results['dkim'] = {'valid': True, 'message': 'DKIM record found'}
                    break
        except dns.resolver.NXDOMAIN:
            verification_results['dkim'] = {'valid': False, 'message': 'DKIM record not found'}
        except dns.resolver.NoAnswer:
            verification_results['dkim'] = {'valid': False, 'message': 'DKIM record not found'}
        except Exception as e:
            verification_results['dkim'] = {'valid': False, 'message': f'Error checking DKIM: {str(e)}'}
        
        # Check DMARC
        try:
            dmarc_domain = f'_dmarc.{domain_name}'
            answers = dns.resolver.resolve(dmarc_domain, 'TXT', lifetime=10)
            for rdata in answers:
                txt_value = str(rdata).strip('"')
                if 'v=DMARC1' in txt_value:
                    verification_results['dmarc'] = {'valid': True, 'message': 'DMARC record found'}
                    break
        except dns.resolver.NXDOMAIN:
            verification_results['dmarc'] = {'valid': False, 'message': 'DMARC record not found'}
        except dns.resolver.NoAnswer:
            verification_results['dmarc'] = {'valid': False, 'message': 'DMARC record not found'}
        except Exception as e:
            verification_results['dmarc'] = {'valid': False, 'message': f'Error checking DMARC: {str(e)}'}
        
        # Determine overall verification status
        # At minimum, require SPF to be valid
        spf_valid = verification_results['spf']['valid']
        dkim_valid = verification_results['dkim']['valid']
        dmarc_valid = verification_results['dmarc']['valid']
        
        # Consider verified if SPF is valid (DKIM and DMARC are recommended but not required)
        overall_verified = spf_valid
        
        # Update domain status
        db.session.execute(text("""
            UPDATE domains 
            SET dns_verified = :verified,
                spf_valid = :spf_valid,
                dkim_valid = :dkim_valid,
                dmarc_valid = :dmarc_valid,
                verified_at = CASE WHEN :verified THEN NOW() ELSE verified_at END,
                updated_at = NOW()
            WHERE id = :id
        """), {
            'id': domain_id,
            'verified': overall_verified,
            'spf_valid': spf_valid,
            'dkim_valid': dkim_valid,
            'dmarc_valid': dmarc_valid
        })
        db.session.commit()
        
        if overall_verified:
            logger.info(f"Domain {domain_name} verified successfully")
            return jsonify({
                'success': True,
                'message': 'Domain verified successfully!',
                'results': verification_results
            })
        else:
            # Build error message
            errors = []
            if not spf_valid:
                errors.append(f"SPF: {verification_results['spf']['message']}")
            if not dkim_valid:
                errors.append(f"DKIM: {verification_results['dkim']['message']}")
            if not dmarc_valid:
                errors.append(f"DMARC: {verification_results['dmarc']['message']}")
            
            return jsonify({
                'success': False,
                'error': '; '.join(errors),
                'results': verification_results
            })
    
    except Exception as e:
        logger.error(f"Verify domain error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Verification failed. Please try again.'
        }), 500


@domain_bp.route('/<domain_id>/delete', methods=['POST'])
@login_required
def delete_domain(domain_id):
    """Delete domain"""
    try:
        # Get domain name for logging
        result = db.session.execute(text("""
            SELECT domain_name FROM domains 
            WHERE id = :id AND organization_id = :org_id
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id
        }).fetchone()
        
        if not result:
            return jsonify({'success': False, 'error': 'Domain not found'}), 404
        
        domain_name = result[0]
        
        db.session.execute(text("""
            DELETE FROM domains 
            WHERE id = :id AND organization_id = :org_id
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id
        })
        
        db.session.commit()
        
        logger.info(f"Domain {domain_name} deleted by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Domain deleted successfully'
        })
    
    except Exception as e:
        logger.error(f"Delete domain error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to delete domain'
        }), 500


@domain_bp.route('/<domain_id>/dns-records', methods=['GET'])
@login_required
def get_dns_records(domain_id):
    """Get DNS records for a domain"""
    try:
        result = db.session.execute(text("""
            SELECT domain_name, dkim_public_key FROM domains 
            WHERE id = :id AND organization_id = :org_id
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id
        }).fetchone()
        
        if not result:
            return jsonify({'success': False, 'error': 'Domain not found'}), 404
        
        domain_name, dkim_public_key = result
        
        # Generate SPF with all IPs
        spf_value = 'v=spf1 ' + ' '.join([f'ip4:{ip}' for ip in SENDING_IPS]) + ' ~all'
        
        return jsonify({
            'success': True,
            'domain': domain_name,
            'records': {
                'spf': {
                    'type': 'TXT',
                    'host': '@',
                    'value': spf_value,
                    'ttl': 3600
                },
                'dkim': {
                    'type': 'TXT',
                    'host': 'mail._domainkey',
                    'value': f'v=DKIM1; k=rsa; p={dkim_public_key}',
                    'ttl': 3600
                },
                'dmarc': {
                    'type': 'TXT',
                    'host': '_dmarc',
                    'value': f'v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain_name}; fo=1',
                    'ttl': 3600
                }
            },
            'sending_ips': SENDING_IPS
        })
    
    except Exception as e:
        logger.error(f"Get DNS records error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to get DNS records'}), 500
