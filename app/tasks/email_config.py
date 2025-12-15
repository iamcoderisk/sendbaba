"""
SendBaba High-Performance Email Configuration
=============================================
Optimized for maximum throughput with 10 IPs.

THEORETICAL MAXIMUM:
- 10 IPs × 50 emails/sec = 500 emails/sec
- 500 × 60 = 30,000 emails/minute
- BUT: Gmail/Yahoo throttle per IP, so realistic is 200-500/min

REALISTIC TARGETS:
- Conservative: 200 emails/min (safe for all providers)
- Moderate: 500 emails/min (good reputation IPs)
- Aggressive: 1000 emails/min (warmed IPs, good domains)
"""

# Performance profiles
PROFILES = {
    'safe': {
        'BATCH_SIZE': 50,
        'CONCURRENT_BATCHES': 5,
        'DELAY_BETWEEN_EMAILS_MS': 100,  # 10/sec per worker
        'DELAY_BETWEEN_BATCHES_MS': 1000,
        'MAX_WORKERS': 10,
        'TARGET_PER_MINUTE': 200,
    },
    'moderate': {
        'BATCH_SIZE': 100,
        'CONCURRENT_BATCHES': 10,
        'DELAY_BETWEEN_EMAILS_MS': 50,  # 20/sec per worker
        'DELAY_BETWEEN_BATCHES_MS': 500,
        'MAX_WORKERS': 20,
        'TARGET_PER_MINUTE': 500,
    },
    'aggressive': {
        'BATCH_SIZE': 200,
        'CONCURRENT_BATCHES': 20,
        'DELAY_BETWEEN_EMAILS_MS': 20,  # 50/sec per worker
        'DELAY_BETWEEN_BATCHES_MS': 200,
        'MAX_WORKERS': 20,
        'TARGET_PER_MINUTE': 1000,
    },
    'maximum': {
        'BATCH_SIZE': 500,
        'CONCURRENT_BATCHES': 40,
        'DELAY_BETWEEN_EMAILS_MS': 10,  # 100/sec per worker
        'DELAY_BETWEEN_BATCHES_MS': 100,
        'MAX_WORKERS': 20,
        'TARGET_PER_MINUTE': 2000,
    }
}

# Active profile - change this to switch modes
ACTIVE_PROFILE = 'aggressive'

# Get current config
CONFIG = PROFILES[ACTIVE_PROFILE]

# Provider-specific delays (to avoid throttling)
PROVIDER_DELAYS = {
    'gmail.com': 100,      # Gmail is strict
    'googlemail.com': 100,
    'yahoo.com': 80,
    'hotmail.com': 50,
    'outlook.com': 50,
    'aol.com': 50,
    'default': 20,         # Others are more lenient
}

def get_provider_delay(email: str) -> int:
    """Get delay in ms for specific provider"""
    domain = email.split('@')[-1].lower() if '@' in email else 'default'
    return PROVIDER_DELAYS.get(domain, PROVIDER_DELAYS['default'])
