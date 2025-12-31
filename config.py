"""
SendBaba Production Configuration
"""
import os

class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY', '60b55ca25a3391f98774c37d68c65b88')
    DEBUG = False
    TESTING = False
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://emailer:SecurePassword123@localhost:5432/emailer')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 20,
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "max_overflow": 40
    }
    
    # Redis
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://:SendBabaRedis2024!@localhost:6379/0')
    
    # Celery
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    
    # Email Settings
    SMTP_POOL_SIZE = 10
    SMTP_TIMEOUT = 30
    
    # Rate Limiting (per domain per minute)
    RATE_LIMITS = {
        'gmail.com': 20,
        'yahoo.com': 15,
        'hotmail.com': 15,
        'outlook.com': 15,
        'aol.com': 10,
        'default': 30
    }
    
    # IP Warmup
    IP_WARMUP_ENABLED = True
    
    # Tracking
    TRACKING_DOMAIN = os.environ.get('TRACKING_DOMAIN', 'track.sendbaba.com')

class ProductionConfig(Config):
    DEBUG = False

class DevelopmentConfig(Config):
    DEBUG = True

config = ProductionConfig()
