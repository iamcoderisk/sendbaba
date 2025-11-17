import psycopg2

try:
    # Connect to the STAGING database
    conn = psycopg2.connect(
        host="localhost",
        database="emailer_staging",
        user="emailer_staging",
        password="StagingSecurePass456"
    )
    
    cur = conn.cursor()
    
    print("Creating departments table in emailer_staging...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id SERIAL PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        color VARCHAR(7) DEFAULT '#6366F1',
        email_quota INTEGER DEFAULT 1000,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """)
    print("✅ departments table created")
    
    print("Creating team_members table in emailer_staging...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS team_members (
        id SERIAL PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        department_id INTEGER,
        user_id VARCHAR(36),
        email VARCHAR(120) UNIQUE NOT NULL,
        first_name VARCHAR(50),
        last_name VARCHAR(50),
        password_hash VARCHAR(255),
        role VARCHAR(20) DEFAULT 'member',
        can_send_email BOOLEAN DEFAULT TRUE,
        can_manage_contacts BOOLEAN DEFAULT TRUE,
        can_manage_campaigns BOOLEAN DEFAULT TRUE,
        can_view_analytics BOOLEAN DEFAULT TRUE,
        can_manage_team BOOLEAN DEFAULT FALSE,
        can_manage_billing BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT TRUE,
        invitation_token VARCHAR(100),
        invitation_accepted BOOLEAN DEFAULT FALSE,
        emails_sent INTEGER DEFAULT 0,
        last_login TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """)
    print("✅ team_members table created")
    
    print("Creating audit_logs table in emailer_staging...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        user_id INTEGER,
        action VARCHAR(100) NOT NULL,
        resource_type VARCHAR(50),
        resource_id INTEGER,
        details JSON,
        ip_address VARCHAR(45),
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)
    print("✅ audit_logs table created")
    
    print("Creating indexes in emailer_staging...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_departments_org ON departments(organization_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_team_members_org ON team_members(organization_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_team_members_dept ON team_members(department_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_org ON audit_logs(organization_id);")
    print("✅ indexes created")
    
    conn.commit()
    print("\n🎉 All team tables created successfully in emailer_staging!")
    
    # Verify
    cur.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('departments', 'team_members', 'audit_logs')
        ORDER BY table_name;
    """)
    
    tables = cur.fetchall()
    print(f"✅ Verified tables: {[t[0] for t in tables]}")
    
    cur.close()
    conn.close()
    
except psycopg2.OperationalError as e:
    print(f"❌ Database connection error: {e}")
    print("\nTrying to create the database first...")
    
    # Try to create the database if it doesn't exist
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="postgres",
            user="postgres",
            password=""
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute("CREATE DATABASE emailer_staging;")
        cur.execute("CREATE USER emailer_staging WITH PASSWORD 'StagingSecurePass456';")
        cur.execute("GRANT ALL PRIVILEGES ON DATABASE emailer_staging TO emailer_staging;")
        
        print("✅ Database created! Run this script again.")
        
        cur.close()
        conn.close()
    except Exception as e2:
        print(f"❌ Could not create database: {e2}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
