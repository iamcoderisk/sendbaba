import os

class StagingConfig:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'staging-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = 'postgresql://emailer_staging:StagingSecurePass456@localhost:5432/emailer_staging'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    ENVIRONMENT = 'STAGING'
    DEBUG = True
