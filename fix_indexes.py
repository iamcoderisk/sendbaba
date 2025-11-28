import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='emailer',
    user='emailer',
    password='SecurePassword123'
)
cur = conn.cursor()

print("Checking tables...")

# Check email_replies columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'email_replies'
    ORDER BY ordinal_position
""")
replies_cols = [c[0] for c in cur.fetchall()]
print(f"email_replies columns: {len(replies_cols)} columns")

# Check email_templates columns  
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'email_templates'
    ORDER BY ordinal_position
""")
templates_cols = [c[0] for c in cur.fetchall()]
print(f"email_templates columns: {len(templates_cols)} columns")

# Create indexes only if column exists
if 'organization_id' in replies_cols:
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_email_replies_org ON email_replies(organization_id)")
        conn.commit()
        print("✅ idx_email_replies_org created")
    except Exception as e:
        print(f"❌ {e}")
        conn.rollback()

if 'status' in replies_cols:
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_email_replies_status ON email_replies(status)")
        conn.commit()
        print("✅ idx_email_replies_status created")
    except Exception as e:
        print(f"❌ {e}")
        conn.rollback()

if 'sentiment' in replies_cols:
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_email_replies_sentiment ON email_replies(sentiment)")
        conn.commit()
        print("✅ idx_email_replies_sentiment created")
    except Exception as e:
        print(f"❌ {e}")
        conn.rollback()

if 'organization_id' in templates_cols:
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_email_templates_org ON email_templates(organization_id)")
        conn.commit()
        print("✅ idx_email_templates_org created")
    except Exception as e:
        print(f"❌ {e}")
        conn.rollback()

if 'category' in templates_cols:
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_email_templates_category ON email_templates(category)")
        conn.commit()
        print("✅ idx_email_templates_category created")
    except Exception as e:
        print(f"❌ {e}")
        conn.rollback()

cur.close()
conn.close()
print("\n✅ Done!")
