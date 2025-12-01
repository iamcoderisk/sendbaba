module.exports = {
  apps: [
    // Main Flask App (Production with Gunicorn)
    {
      name: 'sendbaba-web',
      script: 'gunicorn',
      args: '-c gunicorn_config.py run:app',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      env: {
        FLASK_ENV: 'production',
        REDIS_URL: 'redis://localhost:6379/0'
      },
      instances: 1,
      autorestart: true,
      max_restarts: 10,
      watch: false
    },
    
    // Celery Worker - High Priority
    {
      name: 'celery-high',
      script: 'celery',
      args: '-A celery_app worker --loglevel=info --queues=high --concurrency=4 --hostname=high@%h',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10
    },
    
    // Celery Worker - Default
    {
      name: 'celery-default',
      script: 'celery',
      args: '-A celery_app worker --loglevel=info --queues=default --concurrency=8 --hostname=default@%h',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10
    },
    
    // Celery Worker - Bulk
    {
      name: 'celery-bulk',
      script: 'celery',
      args: '-A celery_app worker --loglevel=info --queues=bulk --concurrency=4 --hostname=bulk@%h',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10
    },
    
    // Celery Beat - Scheduler
    {
      name: 'celery-beat',
      script: 'celery',
      args: '-A celery_app beat --loglevel=info',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10
    },
    
    // Celery Flower - Monitoring
    {
      name: 'celery-flower',
      script: 'celery',
      args: '-A celery_app flower --port=5555',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true
    }
  ]
};
