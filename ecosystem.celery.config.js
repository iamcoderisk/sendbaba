module.exports = {
  apps: [
    {
      name: 'celery-worker-1',
      script: '/opt/sendbaba-staging/venv/bin/celery',
      args: '-A app.celery_config worker --loglevel=info --concurrency=4 --queues=high,default --hostname=worker1@%h',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10
    },
    {
      name: 'celery-worker-2',
      script: '/opt/sendbaba-staging/venv/bin/celery',
      args: '-A app.celery_config worker --loglevel=info --concurrency=4 --queues=bulk,retry --hostname=worker2@%h',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10
    },
    {
      name: 'celery-beat',
      script: '/opt/sendbaba-staging/venv/bin/celery',
      args: '-A app.celery_config beat --loglevel=info',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10
    },
    {
      name: 'celery-flower',
      script: '/opt/sendbaba-staging/venv/bin/celery',
      args: '-A app.celery_config flower --port=5555',
      cwd: '/opt/sendbaba-staging',
      interpreter: 'none',
      autorestart: true
    }
  ]
};
