import sys
sys.path.insert(0, '/opt/sendbaba-staging')

# Check if auth controller exists and fix registration
import os

auth_path = '/opt/sendbaba-staging/app/controllers/auth_controller.py'

if os.path.exists(auth_path):
    with open(auth_path, 'r') as f:
        content = f.read()
    
    # Check if registration is working
    if 'def register' in content:
        print("✅ Auth controller has register function")
    else:
        print("❌ Auth controller missing register function")
else:
    print("❌ Auth controller not found")

# Check database for users table
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    conn = psycopg2.connect("postgresql://emailer:SecurePassword123@localhost/emailer")
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check users table
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
    columns = [r['column_name'] for r in cur.fetchall()]
    print(f"✅ Users table columns: {columns}")
    
    # Check if registration_type exists
    if 'registration_type' not in columns:
        print("Adding registration_type column...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_type VARCHAR(50) DEFAULT 'campaign'")
        conn.commit()
        print("✅ Added registration_type column")
    
    # Check if is_verified exists
    if 'is_verified' not in columns:
        print("Adding is_verified column...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT true")
        conn.commit()
        print("✅ Added is_verified column")
    
    # Check if verification_token exists
    if 'verification_token' not in columns:
        print("Adding verification_token column...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token VARCHAR(255)")
        conn.commit()
        print("✅ Added verification_token column")
    
    # Check mailbox tables
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'mailbox%'")
    tables = [r['table_name'] for r in cur.fetchall()]
    print(f"✅ Mailbox tables: {tables}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Database error: {e}")
