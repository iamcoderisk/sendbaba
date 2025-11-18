import os
from pathlib import Path

class Config:
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database
    DATABASE_URL = os.getenv(
        'DATABASE_URL',
        'postgresql://emailer:SecurePassword123@localhost:5432/emailer'
    )
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # Redis
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    
    # SMTP Configuration
    SMTP_HOST = os.getenv('SMTP_HOST', 'localhost')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_TIMEOUT = 30
    SMTP_MAX_RETRIES = 3
    
    # DKIM
    DKIM_SELECTOR = os.getenv('DKIM_SELECTOR', 'mail')
    DKIM_PRIVATE_KEY_PATH = os.getenv('DKIM_PRIVATE_KEY_PATH', '/opt/sendbaba-staging/keys/dkim_private.pem')
    DKIM_PUBLIC_KEY_PATH = os.getenv('DKIM_PUBLIC_KEY_PATH', '/opt/sendbaba-staging/keys/dkim_public.pem')
    DKIM_KEY_SIZE = 2048
    
    # Email sending
    DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@sendbaba.com')
    DEFAULT_FROM_NAME = os.getenv('DEFAULT_FROM_NAME', 'SendBaba')
    
    # Rate limiting
    MAX_EMAILS_PER_SECOND = int(os.getenv('MAX_EMAILS_PER_SECOND', 100))
    MAX_EMAILS_PER_HOUR = int(os.getenv('MAX_EMAILS_PER_HOUR', 100000))
    
    # Monitoring
    ENABLE_METRICS = os.getenv('ENABLE_METRICS', 'true').lower() == 'true'

settings = Config()
