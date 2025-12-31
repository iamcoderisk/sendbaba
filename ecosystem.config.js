module.exports = {
  apps: [
    {
      name: 'celery-worker',
      cwd: '/opt/sendbaba-staging',
      script: '/opt/sendbaba-staging/venv/bin/celery',
      args: '-A celery_app worker --loglevel=INFO --concurrency=50 -n worker@staging',
      interpreter: 'none',
      env: {
        PYTHONPATH: '/opt/sendbaba-staging'
      },
      max_restarts: 10,
      restart_delay: 5000
    },
    {
      name: 'celery-beat',
      cwd: '/opt/sendbaba-staging',
      script: '/opt/sendbaba-staging/venv/bin/celery',
      args: '-A celery_app beat --loglevel=INFO',
      interpreter: 'none',
      env: {
        PYTHONPATH: '/opt/sendbaba-staging'
      },
      max_restarts: 10,
      restart_delay: 5000
    },
    {
      name: 'incoming-smtp',
      cwd: '/opt/sendbaba-staging',
      script: 'incoming_smtp.py',
      interpreter: '/opt/sendbaba-staging/venv/bin/python',
      max_restarts: 10,
      restart_delay: 5000
    },
    {
      name: 'sendbaba-web',
      cwd: '/opt/sendbaba-staging',
      script: '/opt/sendbaba-staging/venv/bin/gunicorn',
      args: '-w 4 -b 0.0.0.0:8000 --timeout 120 wsgi:app',
      interpreter: 'none',
      max_restarts: 10,
      restart_delay: 5000
    }
  ]
};
