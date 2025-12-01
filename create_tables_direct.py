import psycopg2

try:
    # Database connection
    conn = psycopg2.connect(
        host="localhost",
        database="emailer",
        user="emailer",
        password="SecurePassword123"
    )
    
    cur = conn.cursor()
    
    print("Creating departments table...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id SERIAL PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id),
        name VARCHAR(100) NOT NULL,
        description TEXT,
        color VARCHAR(7) DEFAULT '#6366F1',
        email_quota INTEGER DEFAULT 1000,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """)
    print("✅ departments table created")
    
    print("Creating team_members table...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS team_members (
        id SERIAL PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id),
        department_id INTEGER REFERENCES departments(id),
        user_id VARCHAR(36) REFERENCES users(id),
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
    
    print("Creating audit_logs table...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id),
        user_id INTEGER REFERENCES team_members(id),
        action VARCHAR(100) NOT NULL,
        resource_type VARCHAR(50),
        resource_id INTEGER,
        details JSON,
        ip_address VARCHAR(45),
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)
    print("✅ audit_logs table created")
    
    print("Creating indexes...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_departments_org ON departments(organization_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_team_members_org ON team_members(organization_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_team_members_dept ON team_members(department_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_org ON audit_logs(organization_id);")
    print("✅ indexes created")
    
    conn.commit()
    print("\n🎉 All team tables created successfully!")
    
    # Verify tables exist
    cur.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('departments', 'team_members', 'audit_logs')
        ORDER BY table_name;
    """)
    
    tables = cur.fetchall()
    print(f"\n✅ Verified tables exist: {[t[0] for t in tables]}")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
