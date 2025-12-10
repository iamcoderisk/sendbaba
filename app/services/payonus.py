"""
Payonus Payment Service Provider Integration
"""
import requests
import logging
import os
import hashlib
import hmac

logger = logging.getLogger(__name__)

class PayonusService:
    def __init__(self):
        self.base_url = os.environ.get('PAYONUS_BASE_URL', 'https://api.payonus.com/v1')
        self.client_id = os.environ.get('PAYONUS_CLIENT_ID', 'sk_live_prin56l8CT3QnF0l5Uv6s6NJ')
        self.client_secret = os.environ.get('PAYONUS_CLIENT_SECRET', 'GgqWiKbYlPQv8PVbLYYpIxoZMiQvE3vHFdn87QVXO7M3HILyXmcgEc3lzJ6V4ox9')
    
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.client_secret}',
            'X-Client-ID': self.client_id,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def initialize_payment(self, amount, currency, email, name, reference, redirect_url, webhook_url, metadata=None):
        try:
            payload = {
                'amount': amount, 'currency': currency,
                'customer': {'email': email, 'name': name},
                'reference': reference, 'redirect_url': redirect_url,
                'callback_url': webhook_url, 'metadata': metadata or {}
            }
            response = requests.post(f'{self.base_url}/payments/initialize', json=payload, headers=self._get_headers(), timeout=30)
            result = response.json()
            if response.status_code == 200 and result.get('status') in ['success', True, 'true']:
                return {
                    'success': True,
                    'checkout_url': result.get('data', {}).get('checkout_url') or result.get('data', {}).get('authorization_url'),
                    'reference': result.get('data', {}).get('reference', reference)
                }
            return {'success': False, 'error': result.get('message', 'Payment initialization failed')}
        except Exception as e:
            logger.error(f"Payonus initialize error: {e}")
            return {'success': False, 'error': str(e)}
    
    def verify_payment(self, reference):
        try:
            response = requests.get(f'{self.base_url}/payments/verify/{reference}', headers=self._get_headers(), timeout=30)
            result = response.json()
            if response.status_code == 200:
                data = result.get('data', {})
                return {
                    'success': True, 'status': data.get('status', '').lower(),
                    'amount': data.get('amount'), 'reference': data.get('reference'),
                    'transaction_id': data.get('id') or data.get('transaction_id'),
                    'metadata': data.get('metadata', {})
                }
            return {'success': False, 'error': result.get('message', 'Verification failed')}
        except Exception as e:
            logger.error(f"Payonus verify error: {e}")
            return {'success': False, 'error': str(e)}

payonus = PayonusService()
