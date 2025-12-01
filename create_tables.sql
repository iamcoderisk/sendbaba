-- Suppression list table
CREATE TABLE IF NOT EXISTS suppression_list (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL,
    email VARCHAR(255) NOT NULL,
    reason VARCHAR(50) DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, email)
);

CREATE INDEX IF NOT EXISTS idx_suppression_org_email ON suppression_list(organization_id, email);

-- Email tracking table
CREATE TABLE IF NOT EXISTS email_tracking (
    id VARCHAR(36) PRIMARY KEY,
    email_id VARCHAR(36),
    organization_id VARCHAR(36),
    tracking_id VARCHAR(64) UNIQUE,
    recipient VARCHAR(255),
    opened_at TIMESTAMP,
    clicked_at TIMESTAMP,
    open_count INTEGER DEFAULT 0,
    click_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tracking_id ON email_tracking(tracking_id);
CREATE INDEX IF NOT EXISTS idx_tracking_email ON email_tracking(email_id);

-- Add tracking columns to emails table if not exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'emails' AND column_name = 'opened_at') THEN
        ALTER TABLE emails ADD COLUMN opened_at TIMESTAMP;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'emails' AND column_name = 'clicked_at') THEN
        ALTER TABLE emails ADD COLUMN clicked_at TIMESTAMP;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'emails' AND column_name = 'open_count') THEN
        ALTER TABLE emails ADD COLUMN open_count INTEGER DEFAULT 0;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'emails' AND column_name = 'click_count') THEN
        ALTER TABLE emails ADD COLUMN click_count INTEGER DEFAULT 0;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'emails' AND column_name = 'tracking_id') THEN
        ALTER TABLE emails ADD COLUMN tracking_id VARCHAR(64);
    END IF;
END $$;

-- Webhook events log
CREATE TABLE IF NOT EXISTS webhook_events (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36),
    event_type VARCHAR(50),
    payload JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_org ON webhook_events(organization_id);
CREATE INDEX IF NOT EXISTS idx_webhook_status ON webhook_events(status);

-- IP warmup tracking
CREATE TABLE IF NOT EXISTS ip_warmup (
    id VARCHAR(36) PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    current_day INTEGER DEFAULT 1,
    daily_limit INTEGER DEFAULT 50,
    total_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

ANALYZE emails;
ANALYZE contacts;
ANALYZE campaigns;
