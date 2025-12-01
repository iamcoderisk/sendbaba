"""
SendBaba Integrations Controller
Handles third-party integrations (Shopify, WooCommerce, Stripe, etc.)
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
import json
import uuid
import hmac
import hashlib
import secrets

integration_bp = Blueprint('integrations', __name__, url_prefix='/dashboard/integrations')


def get_organization_id():
    if current_user.is_authenticated:
        return getattr(current_user, 'organization_id', session.get('organization_id'))
    return session.get('organization_id')


# ==================== PAGE ROUTES ====================

@integration_bp.route('/')
@login_required
def index():
    """Integrations list page"""
    return render_template('dashboard/integrations/index.html')


@integration_bp.route('/connect/<integration_type>')
@login_required
def connect(integration_type):
    """Connect integration page"""
    from app.models.integrations import INTEGRATION_TYPES
    
    if integration_type not in INTEGRATION_TYPES:
        return render_template('errors/404.html'), 404
    
    integration_info = INTEGRATION_TYPES[integration_type]
    return render_template('dashboard/integrations/connect.html', 
                         integration_type=integration_type,
                         integration_info=integration_info)


@integration_bp.route('/<integration_id>/settings')
@login_required
def settings(integration_id):
    """Integration settings page"""
    from app.models.integrations import Integration
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return render_template('errors/404.html'), 404
    
    return render_template('dashboard/integrations/settings.html', integration=integration)


@integration_bp.route('/<integration_id>/logs')
@login_required
def logs(integration_id):
    """Integration sync logs page"""
    return render_template('dashboard/integrations/logs.html', integration_id=integration_id)


# ==================== API ROUTES ====================

@integration_bp.route('/api/available')
@login_required
def api_available():
    """Get available integration types"""
    from app.models.integrations import INTEGRATION_TYPES
    
    return jsonify({
        'success': True,
        'integrations': INTEGRATION_TYPES
    })


@integration_bp.route('/api/list')
@login_required
def api_list():
    """Get connected integrations"""
    from app.models.integrations import Integration
    
    integrations = Integration.query.filter_by(organization_id=get_organization_id()).all()
    
    return jsonify({
        'success': True,
        'integrations': [i.to_dict() for i in integrations]
    })


@integration_bp.route('/api/connect', methods=['POST'])
@login_required
def api_connect():
    """Connect new integration"""
    from app.models.integrations import Integration, INTEGRATION_TYPES
    from app import db
    
    data = request.get_json()
    integration_type = data.get('integration_type')
    
    if integration_type not in INTEGRATION_TYPES:
        return jsonify({'error': 'Invalid integration type'}), 400
    
    type_info = INTEGRATION_TYPES[integration_type]
    
    # Validate required fields
    for field in type_info.get('required_fields', []):
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # Generate webhook secret
    webhook_secret = secrets.token_urlsafe(32)
    
    integration = Integration(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        integration_type=integration_type,
        name=data.get('name', type_info['name']),
        api_key=data.get('api_key'),
        api_secret=data.get('api_secret'),
        store_url=data.get('store_url'),
        webhook_secret=webhook_secret,
        config=json.dumps(data.get('config', {})),
        sync_contacts=data.get('sync_contacts', True),
        sync_orders=data.get('sync_orders', True),
        auto_tag_customers=data.get('auto_tag_customers', True),
        default_tags=data.get('default_tags', ''),
        status='pending'
    )
    
    db.session.add(integration)
    db.session.commit()
    
    # Test connection
    success, message = test_integration_connection(integration)
    
    if success:
        integration.status = 'active'
        db.session.commit()
        
        # Setup webhooks if supported
        setup_integration_webhooks(integration)
    else:
        integration.status = 'error'
        integration.last_error = message
        db.session.commit()
    
    return jsonify({
        'success': success,
        'integration': integration.to_dict(),
        'message': message if not success else 'Integration connected successfully'
    })


@integration_bp.route('/api/<integration_id>', methods=['GET'])
@login_required
def api_get(integration_id):
    """Get integration details"""
    from app.models.integrations import Integration
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return jsonify({'error': 'Integration not found'}), 404
    
    return jsonify({
        'success': True,
        'integration': integration.to_dict(include_secrets=False)
    })


@integration_bp.route('/api/<integration_id>', methods=['PUT'])
@login_required
def api_update(integration_id):
    """Update integration settings"""
    from app.models.integrations import Integration
    from app import db
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return jsonify({'error': 'Integration not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        integration.name = data['name']
    if 'api_key' in data and data['api_key']:
        integration.api_key = data['api_key']
    if 'api_secret' in data and data['api_secret']:
        integration.api_secret = data['api_secret']
    if 'store_url' in data:
        integration.store_url = data['store_url']
    if 'sync_contacts' in data:
        integration.sync_contacts = data['sync_contacts']
    if 'sync_orders' in data:
        integration.sync_orders = data['sync_orders']
    if 'auto_tag_customers' in data:
        integration.auto_tag_customers = data['auto_tag_customers']
    if 'default_tags' in data:
        integration.default_tags = data['default_tags']
    if 'field_mapping' in data:
        integration.field_mapping = json.dumps(data['field_mapping'])
    if 'config' in data:
        integration.config = json.dumps(data['config'])
    
    integration.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'integration': integration.to_dict(),
        'message': 'Integration updated successfully'
    })


@integration_bp.route('/api/<integration_id>', methods=['DELETE'])
@login_required
def api_delete(integration_id):
    """Delete integration"""
    from app.models.integrations import Integration
    from app import db
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return jsonify({'error': 'Integration not found'}), 404
    
    # Remove webhooks
    remove_integration_webhooks(integration)
    
    db.session.delete(integration)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Integration disconnected successfully'
    })


@integration_bp.route('/api/<integration_id>/test', methods=['POST'])
@login_required
def api_test(integration_id):
    """Test integration connection"""
    from app.models.integrations import Integration
    from app import db
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return jsonify({'error': 'Integration not found'}), 404
    
    success, message = test_integration_connection(integration)
    
    if success:
        integration.status = 'active'
        integration.last_error = None
    else:
        integration.status = 'error'
        integration.last_error = message
    
    db.session.commit()
    
    return jsonify({
        'success': success,
        'message': message
    })


@integration_bp.route('/api/<integration_id>/sync', methods=['POST'])
@login_required
def api_sync(integration_id):
    """Trigger manual sync"""
    from app.models.integrations import Integration, IntegrationSyncLog
    from app import db
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return jsonify({'error': 'Integration not found'}), 404
    
    if integration.status != 'active':
        return jsonify({'error': 'Integration is not active'}), 400
    
    data = request.get_json() or {}
    sync_type = data.get('sync_type', 'full')  # full or incremental
    entity_type = data.get('entity_type', 'all')  # contacts, orders, or all
    
    # Create sync log
    sync_log = IntegrationSyncLog(
        id=str(uuid.uuid4()),
        integration_id=integration_id,
        sync_type=sync_type,
        entity_type=entity_type,
        status='running'
    )
    db.session.add(sync_log)
    db.session.commit()
    
    # Start sync process
    try:
        result = perform_sync(integration, sync_type, entity_type)
        
        sync_log.status = 'completed'
        sync_log.records_processed = result.get('processed', 0)
        sync_log.records_created = result.get('created', 0)
        sync_log.records_updated = result.get('updated', 0)
        sync_log.records_failed = result.get('failed', 0)
        sync_log.completed_at = datetime.utcnow()
        
        integration.last_sync_at = datetime.utcnow()
        integration.contacts_synced += result.get('created', 0)
        integration.orders_synced += result.get('orders_created', 0) if entity_type in ['orders', 'all'] else 0
        
    except Exception as e:
        sync_log.status = 'failed'
        sync_log.error_message = str(e)
        sync_log.completed_at = datetime.utcnow()
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'sync_log': sync_log.to_dict(),
        'message': f'Sync completed: {sync_log.records_created} created, {sync_log.records_updated} updated'
    })


@integration_bp.route('/api/<integration_id>/logs')
@login_required
def api_logs(integration_id):
    """Get sync logs"""
    from app.models.integrations import Integration, IntegrationSyncLog
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return jsonify({'error': 'Integration not found'}), 404
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    logs = IntegrationSyncLog.query.filter_by(integration_id=integration_id)\
        .order_by(IntegrationSyncLog.started_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'logs': [l.to_dict() for l in logs.items],
        'total': logs.total,
        'pages': logs.pages
    })


@integration_bp.route('/api/<integration_id>/pause', methods=['POST'])
@login_required
def api_pause(integration_id):
    """Pause integration"""
    from app.models.integrations import Integration
    from app import db
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return jsonify({'error': 'Integration not found'}), 404
    
    integration.status = 'disabled'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Integration paused'
    })


@integration_bp.route('/api/<integration_id>/resume', methods=['POST'])
@login_required
def api_resume(integration_id):
    """Resume integration"""
    from app.models.integrations import Integration
    from app import db
    
    integration = Integration.query.filter_by(id=integration_id, organization_id=get_organization_id()).first()
    if not integration:
        return jsonify({'error': 'Integration not found'}), 404
    
    # Test connection first
    success, message = test_integration_connection(integration)
    
    if success:
        integration.status = 'active'
        integration.last_error = None
    else:
        return jsonify({'success': False, 'error': message}), 400
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Integration resumed'
    })


# ==================== WEBHOOK ENDPOINTS ====================

@integration_bp.route('/webhook/<integration_id>', methods=['POST'])
def webhook_handler(integration_id):
    """Handle incoming webhooks from integrations"""
    from app.models.integrations import Integration, IntegrationWebhook
    from app import db
    
    integration = Integration.query.get(integration_id)
    if not integration or integration.status != 'active':
        return jsonify({'error': 'Integration not found'}), 404
    
    # Verify webhook signature
    signature = request.headers.get('X-Webhook-Signature') or \
                request.headers.get('X-Shopify-Hmac-Sha256') or \
                request.headers.get('X-WC-Webhook-Signature')
    
    if integration.webhook_secret and signature:
        if not verify_webhook_signature(request.data, integration.webhook_secret, signature):
            return jsonify({'error': 'Invalid signature'}), 401
    
    # Get event type
    event_type = request.headers.get('X-Shopify-Topic') or \
                 request.headers.get('X-WC-Webhook-Topic') or \
                 request.json.get('event_type', 'unknown')
    
    # Store webhook
    webhook = IntegrationWebhook(
        id=str(uuid.uuid4()),
        integration_id=integration_id,
        event_type=event_type,
        payload=json.dumps(request.json),
        headers=json.dumps(dict(request.headers)),
        status='pending'
    )
    db.session.add(webhook)
    db.session.commit()
    
    # Process webhook asynchronously
    process_webhook(webhook)
    
    return jsonify({'success': True})


# ==================== OAUTH ENDPOINTS ====================

@integration_bp.route('/oauth/shopify/callback')
def shopify_oauth_callback():
    """Handle Shopify OAuth callback"""
    from app.models.integrations import Integration
    from app import db
    
    code = request.args.get('code')
    shop = request.args.get('shop')
    state = request.args.get('state')  # integration_id
    
    if not code or not shop or not state:
        return redirect(url_for('integrations.index', error='oauth_failed'))
    
    integration = Integration.query.get(state)
    if not integration:
        return redirect(url_for('integrations.index', error='integration_not_found'))
    
    # Exchange code for access token
    access_token = exchange_shopify_token(shop, code, integration.api_key, integration.api_secret)
    
    if access_token:
        integration.access_token = access_token
        integration.store_url = f"https://{shop}"
        integration.status = 'active'
        
        # Setup webhooks
        setup_shopify_webhooks(integration)
    else:
        integration.status = 'error'
        integration.last_error = 'Failed to get access token'
    
    db.session.commit()
    
    return redirect(url_for('integrations.settings', integration_id=integration.id))


# ==================== INTEGRATION HELPERS ====================

def test_integration_connection(integration):
    """Test connection to integration"""
    integration_type = integration.integration_type
    
    try:
        if integration_type == 'shopify':
            return test_shopify_connection(integration)
        elif integration_type == 'woocommerce':
            return test_woocommerce_connection(integration)
        elif integration_type == 'stripe':
            return test_stripe_connection(integration)
        elif integration_type == 'zapier':
            return True, 'Zapier webhook ready'
        elif integration_type == 'custom_webhook':
            return True, 'Custom webhook ready'
        else:
            return False, 'Unknown integration type'
    except Exception as e:
        return False, str(e)


def test_shopify_connection(integration):
    """Test Shopify API connection"""
    import requests
    
    store_url = integration.store_url.rstrip('/')
    
    if integration.access_token:
        # OAuth connection
        headers = {
            'X-Shopify-Access-Token': integration.access_token,
            'Content-Type': 'application/json'
        }
    else:
        # API key connection
        headers = {
            'Content-Type': 'application/json'
        }
        store_url = store_url.replace('https://', f'https://{integration.api_key}:{integration.api_secret}@')
    
    try:
        response = requests.get(f'{store_url}/admin/api/2024-01/shop.json', headers=headers, timeout=10)
        if response.status_code == 200:
            return True, 'Connected to Shopify successfully'
        else:
            return False, f'Shopify API error: {response.status_code}'
    except requests.RequestException as e:
        return False, f'Connection failed: {str(e)}'


def test_woocommerce_connection(integration):
    """Test WooCommerce API connection"""
    import requests
    from requests.auth import HTTPBasicAuth
    
    store_url = integration.store_url.rstrip('/')
    
    try:
        response = requests.get(
            f'{store_url}/wp-json/wc/v3/system_status',
            auth=HTTPBasicAuth(integration.api_key, integration.api_secret),
            timeout=10
        )
        if response.status_code == 200:
            return True, 'Connected to WooCommerce successfully'
        else:
            return False, f'WooCommerce API error: {response.status_code}'
    except requests.RequestException as e:
        return False, f'Connection failed: {str(e)}'


def test_stripe_connection(integration):
    """Test Stripe API connection"""
    import requests
    
    try:
        response = requests.get(
            'https://api.stripe.com/v1/balance',
            auth=(integration.api_key, ''),
            timeout=10
        )
        if response.status_code == 200:
            return True, 'Connected to Stripe successfully'
        else:
            return False, f'Stripe API error: {response.status_code}'
    except requests.RequestException as e:
        return False, f'Connection failed: {str(e)}'


def setup_integration_webhooks(integration):
    """Setup webhooks for integration"""
    if integration.integration_type == 'shopify':
        setup_shopify_webhooks(integration)
    elif integration.integration_type == 'woocommerce':
        setup_woocommerce_webhooks(integration)


def remove_integration_webhooks(integration):
    """Remove webhooks when disconnecting"""
    # Implementation depends on integration type
    pass


def setup_shopify_webhooks(integration):
    """Setup Shopify webhooks"""
    import requests
    
    webhook_url = url_for('integrations.webhook_handler', integration_id=integration.id, _external=True)
    
    topics = ['customers/create', 'customers/update', 'orders/create', 'orders/paid']
    
    headers = {
        'X-Shopify-Access-Token': integration.access_token,
        'Content-Type': 'application/json'
    }
    
    for topic in topics:
        data = {
            'webhook': {
                'topic': topic,
                'address': webhook_url,
                'format': 'json'
            }
        }
        requests.post(
            f"{integration.store_url}/admin/api/2024-01/webhooks.json",
            headers=headers,
            json=data
        )


def setup_woocommerce_webhooks(integration):
    """Setup WooCommerce webhooks"""
    import requests
    from requests.auth import HTTPBasicAuth
    
    webhook_url = url_for('integrations.webhook_handler', integration_id=integration.id, _external=True)
    
    topics = [
        ('customer.created', 'Customer Created'),
        ('customer.updated', 'Customer Updated'),
        ('order.created', 'Order Created')
    ]
    
    for topic, name in topics:
        data = {
            'name': name,
            'topic': topic,
            'delivery_url': webhook_url,
            'secret': integration.webhook_secret
        }
        requests.post(
            f"{integration.store_url}/wp-json/wc/v3/webhooks",
            auth=HTTPBasicAuth(integration.api_key, integration.api_secret),
            json=data
        )


def verify_webhook_signature(payload, secret, signature):
    """Verify webhook signature"""
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).digest()
    
    import base64
    expected_b64 = base64.b64encode(expected).decode()
    
    return hmac.compare_digest(expected_b64, signature)


def exchange_shopify_token(shop, code, api_key, api_secret):
    """Exchange OAuth code for Shopify access token"""
    import requests
    
    try:
        response = requests.post(
            f'https://{shop}/admin/oauth/access_token',
            json={
                'client_id': api_key,
                'client_secret': api_secret,
                'code': code
            }
        )
        if response.status_code == 200:
            return response.json().get('access_token')
    except:
        pass
    return None


def perform_sync(integration, sync_type, entity_type):
    """Perform sync for integration"""
    result = {
        'processed': 0,
        'created': 0,
        'updated': 0,
        'failed': 0,
        'orders_created': 0
    }
    
    if integration.integration_type == 'shopify':
        result = sync_shopify(integration, sync_type, entity_type)
    elif integration.integration_type == 'woocommerce':
        result = sync_woocommerce(integration, sync_type, entity_type)
    elif integration.integration_type == 'stripe':
        result = sync_stripe(integration, sync_type, entity_type)
    
    return result


def sync_shopify(integration, sync_type, entity_type):
    """Sync data from Shopify"""
    import requests
    
    result = {'processed': 0, 'created': 0, 'updated': 0, 'failed': 0}
    
    headers = {
        'X-Shopify-Access-Token': integration.access_token,
        'Content-Type': 'application/json'
    }
    
    if entity_type in ['contacts', 'all']:
        # Fetch customers
        response = requests.get(
            f"{integration.store_url}/admin/api/2024-01/customers.json?limit=250",
            headers=headers
        )
        
        if response.status_code == 200:
            customers = response.json().get('customers', [])
            for customer in customers:
                result['processed'] += 1
                if create_or_update_contact_from_shopify(integration, customer):
                    result['created'] += 1
                else:
                    result['updated'] += 1
    
    return result


def sync_woocommerce(integration, sync_type, entity_type):
    """Sync data from WooCommerce"""
    import requests
    from requests.auth import HTTPBasicAuth
    
    result = {'processed': 0, 'created': 0, 'updated': 0, 'failed': 0}
    
    if entity_type in ['contacts', 'all']:
        response = requests.get(
            f"{integration.store_url}/wp-json/wc/v3/customers",
            auth=HTTPBasicAuth(integration.api_key, integration.api_secret),
            params={'per_page': 100}
        )
        
        if response.status_code == 200:
            customers = response.json()
            for customer in customers:
                result['processed'] += 1
                if create_or_update_contact_from_woocommerce(integration, customer):
                    result['created'] += 1
                else:
                    result['updated'] += 1
    
    return result


def sync_stripe(integration, sync_type, entity_type):
    """Sync data from Stripe"""
    import requests
    
    result = {'processed': 0, 'created': 0, 'updated': 0, 'failed': 0}
    
    if entity_type in ['contacts', 'all']:
        response = requests.get(
            'https://api.stripe.com/v1/customers',
            auth=(integration.api_key, ''),
            params={'limit': 100}
        )
        
        if response.status_code == 200:
            customers = response.json().get('data', [])
            for customer in customers:
                result['processed'] += 1
                if create_or_update_contact_from_stripe(integration, customer):
                    result['created'] += 1
                else:
                    result['updated'] += 1
    
    return result


def create_or_update_contact_from_shopify(integration, customer):
    """Create or update contact from Shopify customer"""
    # Implement based on your Contact model
    return True


def create_or_update_contact_from_woocommerce(integration, customer):
    """Create or update contact from WooCommerce customer"""
    # Implement based on your Contact model
    return True


def create_or_update_contact_from_stripe(integration, customer):
    """Create or update contact from Stripe customer"""
    # Implement based on your Contact model
    return True


def process_webhook(webhook):
    """Process incoming webhook"""
    from app.models.integrations import Integration
    from app import db
    
    integration = Integration.query.get(webhook.integration_id)
    if not integration:
        webhook.status = 'failed'
        webhook.error_message = 'Integration not found'
        db.session.commit()
        return
    
    try:
        payload = json.loads(webhook.payload)
        event_type = webhook.event_type
        
        if integration.integration_type == 'shopify':
            process_shopify_webhook(integration, event_type, payload)
        elif integration.integration_type == 'woocommerce':
            process_woocommerce_webhook(integration, event_type, payload)
        
        webhook.status = 'processed'
        webhook.processed_at = datetime.utcnow()
    except Exception as e:
        webhook.status = 'failed'
        webhook.error_message = str(e)
    
    db.session.commit()


def process_shopify_webhook(integration, event_type, payload):
    """Process Shopify webhook event"""
    if event_type == 'customers/create':
        create_or_update_contact_from_shopify(integration, payload)
    elif event_type == 'customers/update':
        create_or_update_contact_from_shopify(integration, payload)
    elif event_type == 'orders/create':
        # Handle order created
        pass


def process_woocommerce_webhook(integration, event_type, payload):
    """Process WooCommerce webhook event"""
    if event_type == 'customer.created':
        create_or_update_contact_from_woocommerce(integration, payload)
    elif event_type == 'customer.updated':
        create_or_update_contact_from_woocommerce(integration, payload)
