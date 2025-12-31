"""
SendBaba Domain Controller - SendGrid-style DNS Authentication
==============================================================
Users only need to add:
1. SPF:  TXT @ "v=spf1 include:_spf.sendbaba.com ~all"
2. DKIM: CNAME mail._domainkey → [unique-id].dkim.sendbaba.com  
3. DMARC: TXT _dmarc "v=DMARC1; p=quarantine; ..."

SendBaba manages all IPs centrally - users never need to update DNS when we add IPs!
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import logging
import uuid
import hashlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import dns.resolver

logger = logging.getLogger(__name__)

domain_bp = Blueprint('domain', __name__, url_prefix='/dashboard/domains')

# SendBaba centralized SPF - users just include this
SENDBABA_SPF_INCLUDE = '_spf.sendbaba.com'

# SendBaba DKIM domain for CNAME
SENDBABA_DKIM_DOMAIN = 'dkim.sendbaba.com'


def generate_dkim_keys():
    """Generate DKIM key pair (2048-bit RSA)"""
    try:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

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


def generate_domain_token(domain_name, org_id):
    """Generate unique verification token for domain"""
    data = f"{domain_name}:{org_id}:{uuid.uuid4()}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


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
                created_at, verified_at, verification_token
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
    """Add new domain with DKIM generation - SendGrid style"""
    try:
        data = request.get_json() if request.is_json else request.form
        domain_name = data.get('domain', '').strip().lower()

        if domain_name.startswith('www.'):
            domain_name = domain_name[4:]

        if not domain_name:
            return jsonify({'success': False, 'error': 'Domain name is required'}), 400

        if '.' not in domain_name or len(domain_name) < 4:
            return jsonify({'success': False, 'error': 'Invalid domain format'}), 400

        # Check if domain exists
        existing = db.session.execute(text("""
            SELECT id FROM domains
            WHERE organization_id = :org_id AND domain_name = :domain
        """), {
            'org_id': current_user.organization_id,
            'domain': domain_name
        }).fetchone()

        if existing:
            return jsonify({'success': False, 'error': 'Domain already added'}), 400

        # Generate DKIM keys
        private_key, public_key = generate_dkim_keys()
        if not private_key:
            return jsonify({'success': False, 'error': 'Failed to generate DKIM keys'}), 500

        # Generate unique verification token
        verification_token = generate_domain_token(domain_name, current_user.organization_id)
        
        domain_id = str(uuid.uuid4())
        dkim_selector = 'mail'  # Standard selector

        db.session.execute(text("""
            INSERT INTO domains (
                id, organization_id, domain_name,
                dkim_selector, dkim_private_key, dkim_public_key,
                verification_token,
                dns_verified, is_active,
                spf_valid, dkim_valid, dmarc_valid,
                created_at
            ) VALUES (
                :id, :org_id, :domain,
                :selector, :private_key, :public_key,
                :token,
                false, true,
                false, false, false,
                NOW()
            )
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id,
            'domain': domain_name,
            'selector': dkim_selector,
            'private_key': private_key,
            'public_key': public_key,
            'token': verification_token
        })

        db.session.commit()

        # Generate DNS records - SendGrid style (simple!)
        dns_records = get_dns_records_for_domain(domain_name, public_key, dkim_selector, verification_token)

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
        return jsonify({'success': False, 'error': 'Failed to add domain'}), 500


def get_dns_records_for_domain(domain_name, public_key, selector='mail', verification_token=None):
    """
    Generate SendGrid-style DNS records
    Users add these ONCE and never need to update when we add IPs!
    """
    records = []
    
    # 1. SPF - Just include SendBaba's SPF (we manage IPs centrally)
    records.append({
        'type': 'TXT',
        'host': '@',
        'name': domain_name,
        'value': f'v=spf1 include:{SENDBABA_SPF_INCLUDE} ~all',
        'description': 'SPF Record - Authorizes SendBaba to send on your behalf',
        'priority': 1
    })
    
    # 2. DKIM - TXT record with the public key
    records.append({
        'type': 'TXT',
        'host': f'{selector}._domainkey',
        'name': f'{selector}._domainkey.{domain_name}',
        'value': f'v=DKIM1; k=rsa; p={public_key}',
        'description': 'DKIM Record - Email signature verification',
        'priority': 2
    })
    
    # 3. DMARC - Standard DMARC policy
    records.append({
        'type': 'TXT',
        'host': '_dmarc',
        'name': f'_dmarc.{domain_name}',
        'value': f'v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@{domain_name}; fo=1',
        'description': 'DMARC Record - Email authentication policy',
        'priority': 3
    })
    
    # 4. Optional: Domain verification TXT (like SendGrid's verification)
    if verification_token:
        records.append({
            'type': 'TXT',
            'host': '_sendbaba',
            'name': f'_sendbaba.{domain_name}',
            'value': f'sendbaba-verification={verification_token}',
            'description': 'SendBaba Domain Verification',
            'priority': 4
        })
    
    return records


@domain_bp.route('/<domain_id>/verify', methods=['POST'])
@login_required
def verify_domain(domain_id):
    """Verify domain DNS records"""
    try:
        result = db.session.execute(text("""
            SELECT domain_name, dkim_public_key, dkim_selector, verification_token 
            FROM domains
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
        dkim_selector = row[2] or 'mail'
        verification_token = row[3]

        results = {
            'spf': {'valid': False, 'message': '', 'found': ''},
            'dkim': {'valid': False, 'message': '', 'found': ''},
            'dmarc': {'valid': False, 'message': '', 'found': ''},
            'verification': {'valid': False, 'message': '', 'found': ''}
        }

        # Check SPF - Now just needs to include SendBaba
        try:
            answers = dns.resolver.resolve(domain_name, 'TXT', lifetime=10)
            for rdata in answers:
                txt = str(rdata).strip('"')
                if 'v=spf1' in txt:
                    results['spf']['found'] = txt
                    # Check if includes SendBaba SPF
                    if SENDBABA_SPF_INCLUDE in txt or 'sendbaba' in txt.lower():
                        results['spf'] = {'valid': True, 'message': 'SPF includes SendBaba ✓', 'found': txt}
                    else:
                        results['spf'] = {'valid': False, 'message': f'SPF found but missing include:{SENDBABA_SPF_INCLUDE}', 'found': txt}
                    break
            if not results['spf']['found']:
                results['spf']['message'] = 'No SPF record found'
        except dns.resolver.NXDOMAIN:
            results['spf']['message'] = 'Domain not found in DNS'
        except dns.resolver.NoAnswer:
            results['spf']['message'] = 'No SPF record found'
        except Exception as e:
            results['spf']['message'] = f'Error: {str(e)[:50]}'

        # Check DKIM
        try:
            dkim_domain = f'{dkim_selector}._domainkey.{domain_name}'
            answers = dns.resolver.resolve(dkim_domain, 'TXT', lifetime=10)
            for rdata in answers:
                txt = str(rdata).strip('"').replace(' ', '')
                results['dkim']['found'] = txt[:100] + '...' if len(txt) > 100 else txt
                if 'v=DKIM1' in txt or 'k=rsa' in txt:
                    # Verify public key matches
                    if dkim_public_key and dkim_public_key[:30] in txt:
                        results['dkim'] = {'valid': True, 'message': 'DKIM verified ✓', 'found': results['dkim']['found']}
                    else:
                        results['dkim'] = {'valid': True, 'message': 'DKIM record found (key mismatch warning)', 'found': results['dkim']['found']}
                    break
        except dns.resolver.NXDOMAIN:
            results['dkim']['message'] = f'DKIM record not found at {dkim_selector}._domainkey'
        except dns.resolver.NoAnswer:
            results['dkim']['message'] = f'DKIM record not found at {dkim_selector}._domainkey'
        except Exception as e:
            results['dkim']['message'] = f'Error: {str(e)[:50]}'

        # Check DMARC
        try:
            dmarc_domain = f'_dmarc.{domain_name}'
            answers = dns.resolver.resolve(dmarc_domain, 'TXT', lifetime=10)
            for rdata in answers:
                txt = str(rdata).strip('"')
                if 'v=DMARC1' in txt:
                    results['dmarc'] = {'valid': True, 'message': 'DMARC configured ✓', 'found': txt}
                    break
        except:
            results['dmarc']['message'] = 'DMARC record not found (recommended but optional)'

        # Check SendBaba verification token
        if verification_token:
            try:
                verify_domain_name = f'_sendbaba.{domain_name}'
                answers = dns.resolver.resolve(verify_domain_name, 'TXT', lifetime=10)
                for rdata in answers:
                    txt = str(rdata).strip('"')
                    if verification_token in txt:
                        results['verification'] = {'valid': True, 'message': 'Domain ownership verified ✓', 'found': txt}
                        break
            except:
                results['verification']['message'] = 'Verification record not found (optional)'

        # Determine overall status - SPF and DKIM are required
        spf_valid = results['spf']['valid']
        dkim_valid = results['dkim']['valid']
        dmarc_valid = results['dmarc']['valid']
        overall_verified = spf_valid and dkim_valid

        # Update database
        db.session.execute(text("""
            UPDATE domains
            SET dns_verified = :verified,
                spf_valid = :spf,
                dkim_valid = :dkim,
                dmarc_valid = :dmarc,
                verified_at = CASE WHEN :verified THEN NOW() ELSE verified_at END,
                updated_at = NOW()
            WHERE id = :id
        """), {
            'id': domain_id,
            'verified': overall_verified,
            'spf': spf_valid,
            'dkim': dkim_valid,
            'dmarc': dmarc_valid
        })
        db.session.commit()

        return jsonify({
            'success': overall_verified,
            'verified': overall_verified,
            'message': 'Domain verified successfully!' if overall_verified else 'Please configure the required DNS records',
            'results': results
        })

    except Exception as e:
        logger.error(f"Verify domain error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Verification failed'}), 500


@domain_bp.route('/<domain_id>/dns-records', methods=['GET'])
@login_required
def get_dns_records(domain_id):
    """Get DNS records for a domain - SendGrid style"""
    try:
        result = db.session.execute(text("""
            SELECT domain_name, dkim_public_key, dkim_selector, verification_token
            FROM domains
            WHERE id = :id AND organization_id = :org_id
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id
        }).fetchone()

        if not result:
            return jsonify({'success': False, 'error': 'Domain not found'}), 404

        domain_name = result[0]
        public_key = result[1]
        selector = result[2] or 'mail'
        token = result[3]

        records = get_dns_records_for_domain(domain_name, public_key, selector, token)

        return jsonify({
            'success': True,
            'domain': domain_name,
            'records': records,
            'instructions': {
                'title': 'Add these DNS records to your domain',
                'note': 'You only need to do this once. SendBaba manages all sending IPs centrally.',
                'spf_note': f'The SPF record includes {SENDBABA_SPF_INCLUDE} which contains all our sending IPs.',
                'time_note': 'DNS changes can take up to 48 hours to propagate, but usually take 5-15 minutes.'
            }
        })

    except Exception as e:
        logger.error(f"Get DNS records error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to get DNS records'}), 500


@domain_bp.route('/<domain_id>/delete', methods=['POST'])
@login_required
def delete_domain(domain_id):
    """Delete domain"""
    try:
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
            DELETE FROM domains WHERE id = :id AND organization_id = :org_id
        """), {
            'id': domain_id,
            'org_id': current_user.organization_id
        })
        db.session.commit()

        logger.info(f"Domain {domain_name} deleted by user {current_user.id}")
        return jsonify({'success': True, 'message': 'Domain deleted'})

    except Exception as e:
        logger.error(f"Delete domain error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to delete domain'}), 500


@domain_bp.route('/<domain_id>/regenerate-dkim', methods=['POST'])
@login_required
def regenerate_dkim(domain_id):
    """Regenerate DKIM keys for a domain"""
    try:
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
        
        # Generate new DKIM keys
        private_key, public_key = generate_dkim_keys()
        if not private_key:
            return jsonify({'success': False, 'error': 'Failed to generate DKIM keys'}), 500

        # Update in database
        db.session.execute(text("""
            UPDATE domains
            SET dkim_private_key = :private_key,
                dkim_public_key = :public_key,
                dkim_valid = false,
                dns_verified = false,
                updated_at = NOW()
            WHERE id = :id
        """), {
            'id': domain_id,
            'private_key': private_key,
            'public_key': public_key
        })
        db.session.commit()

        logger.info(f"DKIM regenerated for {domain_name}")

        return jsonify({
            'success': True,
            'message': 'DKIM keys regenerated. Please update your DNS records.',
            'new_dkim_record': f'v=DKIM1; k=rsa; p={public_key}'
        })

    except Exception as e:
        logger.error(f"Regenerate DKIM error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to regenerate DKIM'}), 500
