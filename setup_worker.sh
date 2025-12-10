#!/bin/bash
# Run this on each worker server to set it up as an email relay

WORKER_IP=$1
HOSTNAME=$2

if [ -z "$WORKER_IP" ] || [ -z "$HOSTNAME" ]; then
    echo "Usage: ./setup_worker.sh <worker_ip> <hostname>"
    exit 1
fi

echo "Setting up worker $HOSTNAME ($WORKER_IP)..."

# Install required packages
apt-get update
apt-get install -y postfix opendkim opendkim-tools

# Configure Postfix
cat > /etc/postfix/main.cf << EOF
smtpd_banner = \$myhostname ESMTP
biff = no
append_dot_mydomain = no
readme_directory = no
compatibility_level = 2

# TLS parameters
smtpd_tls_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem
smtpd_tls_key_file=/etc/ssl/private/ssl-cert-snakeoil.key
smtpd_use_tls=yes
smtpd_tls_session_cache_database = btree:\${data_directory}/smtpd_scache
smtp_tls_session_cache_database = btree:\${data_directory}/smtp_scache

# Network
myhostname = $HOSTNAME
mydomain = sendbaba.com
myorigin = \$mydomain
inet_interfaces = all
inet_protocols = ipv4
mydestination = localhost
relayhost = 
mynetworks = 127.0.0.0/8 156.67.29.186/32

# Limits
smtpd_recipient_limit = 1000
default_process_limit = 100
smtp_destination_concurrency_limit = 20
smtp_destination_rate_delay = 1s

# DKIM
milter_protocol = 2
milter_default_action = accept
smtpd_milters = inet:localhost:8891
non_smtpd_milters = inet:localhost:8891
EOF

# Restart Postfix
systemctl restart postfix
systemctl enable postfix

echo "✅ Worker $HOSTNAME configured"
