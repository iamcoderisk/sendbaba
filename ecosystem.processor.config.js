module.exports = {
  apps: [{
    name: 'sendbaba-processor',
    script: '/opt/sendbaba-staging/campaign_processor.py',
    interpreter: '/opt/sendbaba-staging/venv/bin/python3',
    cwd: '/opt/sendbaba-staging',
    autorestart: true,
    watch: false,
    max_memory_restart: '1G'
  }]
};
