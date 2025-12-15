#!/bin/bash
# ==============================================
# SENDBABA CLUSTER MASTER SETUP SCRIPT
# Run on: Main Server (156.67.29.186)
# ==============================================

set -e

# Configuration
MAIN_SERVER="156.67.29.186"
REDIS_IP="194.163.128.208"
DB_PASSWORD="SecurePassword123"
REDIS_PASSWORD="SendBabaRedis2024!"
SERVER_PASSWORD="B@ttl3k0d3@Se"

# All worker servers
WORKERS=(
    "161.97.170.33"
    "75.119.151.72"
    "75.119.153.106"
    "173.212.214.23"
    "173.212.213.239"
    "173.212.213.184"
    "185.215.180.157"
    "185.215.164.39"
    "176.126.87.21"
    "185.215.167.20"
    "185.208.206.35"
)

echo "=========================================="
echo "SENDBABA CLUSTER SETUP"
echo "=========================================="
echo "Main Server: $MAIN_SERVER"
echo "Redis IP: $REDIS_IP"
echo "Workers: ${#WORKERS[@]}"
echo "=========================================="

# Install sshpass for password-based SSH
if ! command -v sshpass &> /dev/null; then
    echo "[1/7] Installing sshpass..."
    apt update && apt install -y sshpass
fi

# Function to run command on remote server
run_remote() {
    local server=$1
    local cmd=$2
    sshpass -p "$SERVER_PASSWORD" ssh -o StrictHostKeyChecking=no root@$server "$cmd"
}

# Function to copy file to remote server
copy_to_remote() {
    local server=$1
    local src=$2
    local dst=$3
    sshpass -p "$SERVER_PASSWORD" scp -o StrictHostKeyChecking=no "$src" root@$server:"$dst"
}

# ==============================================
# STEP 1: Setup SSH Keys (optional but recommended)
# ==============================================
setup_ssh_keys() {
    echo "[1/7] Setting up SSH keys..."
    
    # Generate SSH key if not exists
    if [ ! -f ~/.ssh/id_rsa ]; then
        ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
    fi
    
    # Copy key to all workers
    for worker in "${WORKERS[@]}"; do
        echo "  Copying SSH key to $worker..."
        sshpass -p "$SERVER_PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no root@$worker 2>/dev/null || true
    done
    
    echo "✅ SSH keys configured"
}

# ==============================================
# STEP 2: Configure Main Server
# ==============================================
configure_main_server() {
    echo "[2/7] Configuring Main Server..."
    
    # Update .env file
    cat > /opt/sendbaba-staging/.env << ENVFILE
# Database (local)
DATABASE_URL=postgresql://emailer:${DB_PASSWORD}@localhost:5432/emailer

# Redis (on main server, accessible via extra IP)
REDIS_URL=redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0

# Flask
FLASK_ENV=production
SECRET_KEY=$(openssl rand -hex 32)
ENVFILE
    
    # Update PostgreSQL to allow all workers
    PG_HBA=$(find /etc/postgresql -name pg_hba.conf | head -1)
    
    for worker in "${WORKERS[@]}"; do
        if ! grep -q "$worker" "$PG_HBA"; then
            echo "host    emailer    emailer    $worker/32    md5" >> "$PG_HBA"
            echo "  Added $worker to PostgreSQL"
        fi
    done
    
    # Ensure PostgreSQL listens externally
    PG_CONF=$(find /etc/postgresql -name postgresql.conf | head -1)
    sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"
    sed -i "s/listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"
    
    systemctl restart postgresql
    
    # Ensure Redis is configured
    if [ -f /etc/redis/redis.conf ]; then
        sed -i 's/^bind 127.0.0.1.*/bind 0.0.0.0/' /etc/redis/redis.conf
        if ! grep -q "^requirepass" /etc/redis/redis.conf; then
            echo "requirepass ${REDIS_PASSWORD}" >> /etc/redis/redis.conf
        fi
        systemctl restart redis-server
    fi
    
    echo "✅ Main server configured"
}

# ==============================================
# STEP 3: Create Worker Setup Script
# ==============================================
create_worker_script() {
    echo "[3/7] Creating worker setup script..."
    
    cat > /tmp/worker_setup.sh << 'WORKERSCRIPT'
#!/bin/bash
# Worker Setup Script - Run on each worker server

MAIN_SERVER="156.67.29.186"
REDIS_IP="194.163.128.208"
DB_PASSWORD="SecurePassword123"
REDIS_PASSWORD="SendBabaRedis2024!"
WORKER_IP=$(hostname -I | awk '{print $1}')

echo "=========================================="
echo "Setting up Worker: $WORKER_IP"
echo "=========================================="

# Update system
apt update

# Install dependencies
apt install -y python3 python3-pip python3-venv python3-dev \
    redis-tools postgresql-client build-essential libpq-dev curl git

# Create directories
mkdir -p /opt/sendbaba/logs
cd /opt/sendbaba

# Create virtual environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# Install Python packages
pip install --upgrade pip
pip install celery[redis] redis psycopg2-binary dnspython aiosmtplib \
    flask requests python-dotenv sqlalchemy gunicorn

# Create environment file
cat > /opt/sendbaba/.env << EOF
MAIN_SERVER=${MAIN_SERVER}
REDIS_IP=${REDIS_IP}
DATABASE_URL=postgresql://emailer:${DB_PASSWORD}@${MAIN_SERVER}:5432/emailer
REDIS_URL=redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@${REDIS_IP}:6379/0
CELERY_CONCURRENCY=25
EOF

# Create worker start script
cat > /opt/sendbaba/start_worker.sh << 'STARTSCRIPT'
#!/bin/bash
cd /opt/sendbaba
source venv/bin/activate
source .env
WORKER_IP=$(hostname -I | awk '{print $1}')
exec celery -A app.celery_app worker \
    --loglevel=info \
    --concurrency=${CELERY_CONCURRENCY:-25} \
    --hostname=worker@${WORKER_IP} \
    -Q email_queue,celery,default \
    --max-tasks-per-child=1000 \
    --prefetch-multiplier=4
STARTSCRIPT
chmod +x /opt/sendbaba/start_worker.sh

# Install PM2
if ! command -v pm2 &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt install -y nodejs
    npm install -g pm2
fi

# Create PM2 config
cat > /opt/sendbaba/ecosystem.config.js << 'PM2CONFIG'
module.exports = {
  apps: [{
    name: 'sendbaba-worker',
    script: '/opt/sendbaba/start_worker.sh',
    interpreter: '/bin/bash',
    cwd: '/opt/sendbaba',
    autorestart: true,
    max_memory_restart: '3G',
    error_file: '/opt/sendbaba/logs/error.log',
    out_file: '/opt/sendbaba/logs/out.log'
  }]
};
PM2CONFIG

# System optimization
cat > /etc/sysctl.d/99-sendbaba.conf << 'SYSCTL'
net.core.somaxconn = 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
net.ipv4.ip_local_port_range = 1024 65535
vm.swappiness = 10
SYSCTL
sysctl -p /etc/sysctl.d/99-sendbaba.conf 2>/dev/null || true

echo "✅ Worker base setup complete: $WORKER_IP"
WORKERSCRIPT

    chmod +x /tmp/worker_setup.sh
    echo "✅ Worker script created"
}

# ==============================================
# STEP 4: Setup All Workers
# ==============================================
setup_workers() {
    echo "[4/7] Setting up all workers..."
    
    for worker in "${WORKERS[@]}"; do
        echo ""
        echo ">>> Setting up $worker..."
        
        # Copy and run setup script
        copy_to_remote $worker /tmp/worker_setup.sh /tmp/worker_setup.sh
        run_remote $worker "chmod +x /tmp/worker_setup.sh && /tmp/worker_setup.sh"
        
        echo "✅ $worker base setup done"
    done
}

# ==============================================
# STEP 5: Copy App Files to Workers
# ==============================================
copy_app_files() {
    echo "[5/7] Copying app files to all workers..."
    
    for worker in "${WORKERS[@]}"; do
        echo "  Copying to $worker..."
        
        sshpass -p "$SERVER_PASSWORD" rsync -avz --progress \
            --exclude 'venv' \
            --exclude '__pycache__' \
            --exclude '*.pyc' \
            --exclude '*.log' \
            --exclude 'logs/' \
            --exclude '.git' \
            --exclude 'node_modules' \
            -e "ssh -o StrictHostKeyChecking=no" \
            /opt/sendbaba-staging/ root@$worker:/opt/sendbaba/
    done
    
    echo "✅ App files copied to all workers"
}

# ==============================================
# STEP 6: Start All Workers
# ==============================================
start_workers() {
    echo "[6/7] Starting all workers..."
    
    for worker in "${WORKERS[@]}"; do
        echo "  Starting worker on $worker..."
        run_remote $worker "cd /opt/sendbaba && source venv/bin/activate && pm2 delete all 2>/dev/null; pm2 start ecosystem.config.js && pm2 save && pm2 startup | tail -1 | bash"
    done
    
    echo "✅ All workers started"
}

# ==============================================
# STEP 7: Restart Main Server Services
# ==============================================
restart_main_services() {
    echo "[7/7] Restarting main server services..."
    
    cd /opt/sendbaba-staging
    source venv/bin/activate
    
    pm2 restart all
    
    echo "✅ Main server services restarted"
}

# ==============================================
# STEP 8: Verify Cluster
# ==============================================
verify_cluster() {
    echo ""
    echo "=========================================="
    echo "VERIFYING CLUSTER STATUS"
    echo "=========================================="
    
    cd /opt/sendbaba-staging
    source venv/bin/activate
    
    echo ""
    echo "Celery Workers:"
    celery -A app.celery_app inspect ping 2>/dev/null | grep -E "worker@|pong" || echo "Checking..."
    
    echo ""
    echo "PM2 Status (Main Server):"
    pm2 list
    
    echo ""
    echo "Checking each worker:"
    for worker in "${WORKERS[@]}"; do
        status=$(run_remote $worker "pm2 list 2>/dev/null | grep sendbaba" 2>/dev/null)
        if [[ $status == *"online"* ]]; then
            echo "  ✅ $worker - ONLINE"
        else
            echo "  ❌ $worker - OFFLINE or not ready"
        fi
    done
}

# ==============================================
# MAIN EXECUTION
# ==============================================

case "${1:-all}" in
    ssh)
        setup_ssh_keys
        ;;
    main)
        configure_main_server
        ;;
    workers)
        create_worker_script
        setup_workers
        ;;
    copy)
        copy_app_files
        ;;
    start)
        start_workers
        ;;
    restart)
        restart_main_services
        ;;
    verify)
        verify_cluster
        ;;
    all)
        setup_ssh_keys
        configure_main_server
        create_worker_script
        setup_workers
        copy_app_files
        start_workers
        restart_main_services
        sleep 10
        verify_cluster
        ;;
    *)
        echo "Usage: $0 {ssh|main|workers|copy|start|restart|verify|all}"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "SETUP COMPLETE!"
echo "=========================================="
