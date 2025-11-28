import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='emailer',
    user='emailer',
    password='SecurePassword123'
)
cur = conn.cursor()

# Create email_replies table
email_replies_sql = """
CREATE TABLE IF NOT EXISTS email_replies (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL,
    original_email_id VARCHAR(36),
    campaign_id VARCHAR(36),
    contact_id VARCHAR(36),
    from_email VARCHAR(255) NOT NULL,
    from_name VARCHAR(255),
    subject VARCHAR(500),
    body_text TEXT,
    body_html TEXT,
    message_id VARCHAR(500),
    in_reply_to VARCHAR(500),
    references_header TEXT,
    has_attachments BOOLEAN DEFAULT FALSE,
    attachment_count INTEGER DEFAULT 0,
    attachments JSON,
    sentiment VARCHAR(50),
    sentiment_score FLOAT,
    intent VARCHAR(50),
    urgency VARCHAR(50) DEFAULT 'low',
    topics JSON,
    key_phrases JSON,
    suggested_response TEXT,
    ai_summary TEXT,
    category VARCHAR(50),
    is_auto_reply BOOLEAN DEFAULT FALSE,
    is_out_of_office BOOLEAN DEFAULT FALSE,
    is_bounce BOOLEAN DEFAULT FALSE,
    status VARCHAR(50) DEFAULT 'unread',
    starred BOOLEAN DEFAULT FALSE,
    assigned_to VARCHAR(36),
    assigned_at TIMESTAMP,
    replied_at TIMESTAMP,
    reply_time_seconds INTEGER,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

# Create email_templates table  
email_templates_sql = """
CREATE TABLE IF NOT EXISTS email_templates (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100) DEFAULT 'custom',
    subject VARCHAR(500),
    preheader VARCHAR(500),
    gjs_html TEXT,
    gjs_css TEXT,
    gjs_components TEXT,
    gjs_styles TEXT,
    gjs_assets TEXT,
    text_content TEXT,
    thumbnail_url VARCHAR(500),
    is_system BOOLEAN DEFAULT FALSE,
    is_shared BOOLEAN DEFAULT FALSE,
    is_locked BOOLEAN DEFAULT FALSE,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    version INTEGER DEFAULT 1,
    parent_template_id VARCHAR(36),
    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(36)
)
"""

try:
    cur.execute(email_replies_sql)
    conn.commit()
    print("✅ email_replies table created")
except Exception as e:
    print(f"❌ email_replies: {e}")
    conn.rollback()

try:
    cur.execute(email_templates_sql)
    conn.commit()
    print("✅ email_templates table created")
except Exception as e:
    print(f"❌ email_templates: {e}")
    conn.rollback()

# Create indexes
try:
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_replies_org ON email_replies(organization_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_replies_status ON email_replies(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_replies_sentiment ON email_replies(sentiment)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_templates_org ON email_templates(organization_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_templates_category ON email_templates(category)")
    conn.commit()
    print("✅ Indexes created")
except Exception as e:
    print(f"❌ Indexes: {e}")
    conn.rollback()

cur.close()
conn.close()
print("\n✅ All missing tables fixed!")
