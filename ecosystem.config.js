module.exports = {
  apps: [
    {
      name: 'sendbaba-web',
      script: '/opt/sendbaba-staging/start_gunicorn.sh',
      interpreter: '/bin/bash',
      cwd: '/opt/sendbaba-staging'
    },
    {
      name: 'celery-worker',
      script: '/opt/sendbaba-staging/start_celery_worker.sh',
      interpreter: '/bin/bash',
      cwd: '/opt/sendbaba-staging'
    },
    {
      name: 'celery-beat',
      script: '/opt/sendbaba-staging/start_celery_beat.sh',
      interpreter: '/bin/bash',
      cwd: '/opt/sendbaba-staging'
    }
  ]
};
