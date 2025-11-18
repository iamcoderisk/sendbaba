#!/usr/bin/env python3
"""Generate DKIM keys for a domain"""
import sys
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

def generate_dkim_keys(domain):
    print(f"🔐 Generating DKIM keys for {domain}...")
    
    os.makedirs('/opt/sendbaba-staging/data/dkim', exist_ok=True)
    
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Save private key
    private_path = f'/opt/sendbaba-staging/data/dkim/{domain}_private.key'
    with open(private_path, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Get public key for DNS
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    key_content = public_pem.decode('utf-8')
    key_content = key_content.replace('-----BEGIN PUBLIC KEY-----', '')
    key_content = key_content.replace('-----END PUBLIC KEY-----', '')
    key_content = ''.join(key_content.split())
    
    dns_record = f'v=DKIM1; k=rsa; p={key_content}'
    
    # Save DNS record
    with open(f'/opt/sendbaba-staging/data/dkim/{domain}_public.txt', 'w') as f:
        f.write(f"Add this DNS TXT record:\n\n")
        f.write(f"Name: mail._domainkey.{domain}\n")
        f.write(f"Type: TXT\n")
        f.write(f"Value: {dns_record}\n")
    
    print(f"\n✅ Keys generated!")
    print(f"📁 Private key: {private_path}")
    print(f"📁 DNS record: /opt/sendbaba-staging/data/dkim/{domain}_public.txt")
    print(f"\n🌐 Add this DNS TXT record to enable DKIM:")
    print(f"   Name: mail._domainkey.{domain}")
    print(f"   Value: {dns_record[:70]}...")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 generate_dkim.py <domain>")
        print("Example: python3 generate_dkim.py sendbaba.com")
        sys.exit(1)
    
    generate_dkim_keys(sys.argv[1])
