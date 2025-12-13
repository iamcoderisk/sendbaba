module.exports = {
  apps: [
    {
      name: 'sendbaba-web',
      cwd: '/opt/sendbaba-staging',
      script: 'venv/bin/gunicorn',
      args: '-w 4 -b 0.0.0.0:5000 run:app',
      interpreter: 'none',
      env: {
        FLASK_ENV: 'production'
      }
    },
    {
      name: 'celery-worker',
      cwd: '/opt/sendbaba-staging',
      script: './start_celery_worker.sh',
      interpreter: 'bash',
      autorestart: true,
      max_restarts: 10
    },
    {
      name: 'celery-beat',
      cwd: '/opt/sendbaba-staging',
      script: './start_celery_beat.sh',
      interpreter: 'bash',
      autorestart: true,
      max_restarts: 10
    },
    {
      name: 'sendbaba-smtp',
      cwd: '/opt/sendbaba-staging',
      script: 'venv/bin/python',
      args: '-m app.smtp.relay_server',
      interpreter: 'none'
    }
  ]
};
