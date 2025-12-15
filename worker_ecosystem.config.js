module.exports = {
  apps: [{
    name: 'sendbaba-worker',
    script: '/opt/sendbaba/worker_start.sh',
    interpreter: '/bin/bash',
    cwd: '/opt/sendbaba',
    autorestart: true,
    max_memory_restart: '3G',
    error_file: '/opt/sendbaba/logs/error.log',
    out_file: '/opt/sendbaba/logs/out.log',
    env: {
      NODE_ENV: 'production'
    }
  }]
};
