"""
SendBaba Database Migration
Creates tables for all 6 features: Forms, Workflows, Segments, Integrations, Replies, Email Builder
Run with: python migrations/create_feature_tables.py
"""

import psycopg2
import os

# Database connection
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'emailer')
DB_USER = os.environ.get('DB_USER', 'emailer')
DB_PASS = os.environ.get('DB_PASS', 'SecurePassword123')

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

MIGRATIONS = [
    # ==================== FORMS ====================
    """
    CREATE TABLE IF NOT EXISTS forms (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        form_type VARCHAR(50) DEFAULT 'inline',
        fields JSON,
        design_settings JSON,
        trigger_type VARCHAR(50) DEFAULT 'immediate',
        trigger_value INTEGER,
        success_action VARCHAR(50) DEFAULT 'message',
        success_message TEXT,
        success_redirect_url VARCHAR(500),
        double_optin BOOLEAN DEFAULT FALSE,
        double_optin_email_id VARCHAR(36),
        contact_list_id VARCHAR(36),
        tags VARCHAR(500),
        status VARCHAR(50) DEFAULT 'draft',
        views INTEGER DEFAULT 0,
        submissions INTEGER DEFAULT 0,
        conversion_rate FLOAT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_forms_org ON forms(organization_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS form_submissions (
        id VARCHAR(36) PRIMARY KEY,
        form_id VARCHAR(36) NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
        organization_id VARCHAR(36) NOT NULL,
        data JSON,
        email VARCHAR(255),
        ip_address VARCHAR(50),
        user_agent TEXT,
        referrer TEXT,
        confirmation_token VARCHAR(100),
        confirmed BOOLEAN DEFAULT FALSE,
        confirmed_at TIMESTAMP,
        contact_id VARCHAR(36),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_form_submissions_form ON form_submissions(form_id);
    """,
    
    # ==================== WORKFLOWS ====================
    """
    CREATE TABLE IF NOT EXISTS workflows (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        trigger_type VARCHAR(50) NOT NULL,
        trigger_config JSON,
        steps JSON,
        status VARCHAR(50) DEFAULT 'draft',
        entry_limit INTEGER,
        allow_reentry BOOLEAN DEFAULT FALSE,
        goal_type VARCHAR(50),
        goal_config JSON,
        total_enrolled INTEGER DEFAULT 0,
        active_contacts INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        goal_reached INTEGER DEFAULT 0,
        conversion_rate FLOAT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(36)
    );
    CREATE INDEX IF NOT EXISTS idx_workflows_org ON workflows(organization_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS workflow_enrollments (
        id VARCHAR(36) PRIMARY KEY,
        workflow_id VARCHAR(36) NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
        contact_id VARCHAR(36) NOT NULL,
        organization_id VARCHAR(36) NOT NULL,
        current_step INTEGER DEFAULT 0,
        status VARCHAR(50) DEFAULT 'active',
        enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        exited_at TIMESTAMP,
        exit_reason VARCHAR(255),
        next_action_at TIMESTAMP,
        metadata JSON
    );
    CREATE INDEX IF NOT EXISTS idx_workflow_enrollments_workflow ON workflow_enrollments(workflow_id);
    CREATE INDEX IF NOT EXISTS idx_workflow_enrollments_contact ON workflow_enrollments(contact_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS workflow_logs (
        id VARCHAR(36) PRIMARY KEY,
        workflow_id VARCHAR(36) NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
        enrollment_id VARCHAR(36),
        contact_id VARCHAR(36),
        action_type VARCHAR(50),
        step_index INTEGER,
        step_type VARCHAR(50),
        success BOOLEAN DEFAULT TRUE,
        message TEXT,
        metadata JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_workflow_logs_workflow ON workflow_logs(workflow_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS workflow_templates (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        category VARCHAR(100),
        trigger_type VARCHAR(50),
        steps JSON,
        is_active BOOLEAN DEFAULT TRUE,
        usage_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    
    # ==================== SEGMENTS ====================
    """
    CREATE TABLE IF NOT EXISTS segments (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        segment_type VARCHAR(50) DEFAULT 'dynamic',
        rules JSON,
        rules_match VARCHAR(20) DEFAULT 'all',
        static_members JSON,
        cached_count INTEGER DEFAULT 0,
        last_calculated_at TIMESTAMP,
        color VARCHAR(50) DEFAULT 'purple',
        icon VARCHAR(50) DEFAULT 'fa-users',
        status VARCHAR(50) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(36)
    );
    CREATE INDEX IF NOT EXISTS idx_segments_org ON segments(organization_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS segment_conditions (
        id VARCHAR(36) PRIMARY KEY,
        segment_id VARCHAR(36) NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
        field VARCHAR(100) NOT NULL,
        operator VARCHAR(50) NOT NULL,
        value TEXT,
        value_type VARCHAR(50) DEFAULT 'string',
        condition_group INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_segment_conditions_segment ON segment_conditions(segment_id);
    """,
    
    # ==================== INTEGRATIONS ====================
    """
    CREATE TABLE IF NOT EXISTS integrations (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        integration_type VARCHAR(50) NOT NULL,
        name VARCHAR(255),
        api_key TEXT,
        api_secret TEXT,
        access_token TEXT,
        refresh_token TEXT,
        token_expires_at TIMESTAMP,
        store_url VARCHAR(500),
        webhook_secret VARCHAR(255),
        config JSON,
        sync_contacts BOOLEAN DEFAULT TRUE,
        sync_orders BOOLEAN DEFAULT FALSE,
        sync_products BOOLEAN DEFAULT FALSE,
        auto_tag_customers BOOLEAN DEFAULT TRUE,
        field_mapping JSON,
        status VARCHAR(50) DEFAULT 'pending',
        last_sync_at TIMESTAMP,
        contacts_synced INTEGER DEFAULT 0,
        orders_synced INTEGER DEFAULT 0,
        last_error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(36)
    );
    CREATE INDEX IF NOT EXISTS idx_integrations_org ON integrations(organization_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS integration_sync_logs (
        id VARCHAR(36) PRIMARY KEY,
        integration_id VARCHAR(36) NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
        organization_id VARCHAR(36) NOT NULL,
        sync_type VARCHAR(50),
        entity_type VARCHAR(50),
        status VARCHAR(50) DEFAULT 'running',
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        records_processed INTEGER DEFAULT 0,
        records_created INTEGER DEFAULT 0,
        records_updated INTEGER DEFAULT 0,
        records_failed INTEGER DEFAULT 0,
        errors JSON,
        metadata JSON
    );
    CREATE INDEX IF NOT EXISTS idx_integration_sync_logs_integration ON integration_sync_logs(integration_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS integration_webhooks (
        id VARCHAR(36) PRIMARY KEY,
        integration_id VARCHAR(36) NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
        organization_id VARCHAR(36) NOT NULL,
        event_type VARCHAR(100),
        payload JSON,
        headers JSON,
        processed BOOLEAN DEFAULT FALSE,
        processed_at TIMESTAMP,
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_integration_webhooks_integration ON integration_webhooks(integration_id);
    """,
    
    # ==================== REPLIES ====================
    """
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
    );
    CREATE INDEX IF NOT EXISTS idx_email_replies_org ON email_replies(organization_id);
    CREATE INDEX IF NOT EXISTS idx_email_replies_status ON email_replies(status);
    CREATE INDEX IF NOT EXISTS idx_email_replies_sentiment ON email_replies(sentiment);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS reply_templates (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        name VARCHAR(255) NOT NULL,
        subject VARCHAR(500),
        body TEXT NOT NULL,
        category VARCHAR(100),
        tags VARCHAR(500),
        auto_suggest BOOLEAN DEFAULT FALSE,
        trigger_keywords JSON,
        trigger_intents JSON,
        usage_count INTEGER DEFAULT 0,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(36)
    );
    CREATE INDEX IF NOT EXISTS idx_reply_templates_org ON reply_templates(organization_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS reply_analytics (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        date DATE NOT NULL,
        total_replies INTEGER DEFAULT 0,
        positive_count INTEGER DEFAULT 0,
        negative_count INTEGER DEFAULT 0,
        neutral_count INTEGER DEFAULT 0,
        inquiry_count INTEGER DEFAULT 0,
        complaint_count INTEGER DEFAULT 0,
        feedback_count INTEGER DEFAULT 0,
        avg_response_time INTEGER,
        replied_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(organization_id, date)
    );
    """,
    
    # ==================== EMAIL BUILDER ====================
    """
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
    );
    CREATE INDEX IF NOT EXISTS idx_email_templates_org ON email_templates(organization_id);
    CREATE INDEX IF NOT EXISTS idx_email_templates_category ON email_templates(category);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS email_blocks (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36),
        name VARCHAR(255) NOT NULL,
        description TEXT,
        category VARCHAR(100) DEFAULT 'custom',
        html TEXT NOT NULL,
        css TEXT,
        gjs_components TEXT,
        thumbnail_url VARCHAR(500),
        is_system BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT TRUE,
        sort_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_email_blocks_org ON email_blocks(organization_id);
    """,
    
    """
    CREATE TABLE IF NOT EXISTS email_assets (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        filename VARCHAR(255) NOT NULL,
        original_filename VARCHAR(255),
        file_type VARCHAR(50) DEFAULT 'image',
        mime_type VARCHAR(100),
        file_size INTEGER,
        storage_path TEXT,
        url TEXT NOT NULL,
        thumbnail_url TEXT,
        width INTEGER,
        height INTEGER,
        alt_text VARCHAR(500),
        tags VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        uploaded_by VARCHAR(36)
    );
    CREATE INDEX IF NOT EXISTS idx_email_assets_org ON email_assets(organization_id);
    """
]


def run_migrations():
    conn = get_connection()
    cur = conn.cursor()
    
    print("🚀 Running SendBaba Feature Migrations...")
    print("=" * 50)
    
    for i, migration in enumerate(MIGRATIONS, 1):
        try:
            cur.execute(migration)
            conn.commit()
            # Extract table name from migration
            lines = migration.strip().split('\n')
            for line in lines:
                if 'CREATE TABLE' in line:
                    table_name = line.split('EXISTS')[1].split('(')[0].strip() if 'EXISTS' in line else 'unknown'
                    print(f"  ✅ [{i}/{len(MIGRATIONS)}] {table_name}")
                    break
        except Exception as e:
            conn.rollback()
            print(f"  ❌ Migration {i} failed: {str(e)[:50]}")
    
    cur.close()
    conn.close()
    
    print("=" * 50)
    print("✅ All migrations completed!")


if __name__ == '__main__':
    run_migrations()
