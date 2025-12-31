"""
SendBaba Redis Configuration
============================
Central Redis configuration for all services.
"""
import os

REDIS_PASSWORD = "SendBabaRedis2024!"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# For Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
