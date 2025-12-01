-- Optimize emails table for high volume
CREATE INDEX IF NOT EXISTS idx_emails_campaign_status ON emails(campaign_id, status);
CREATE INDEX IF NOT EXISTS idx_emails_status_created ON emails(status, created_at);
CREATE INDEX IF NOT EXISTS idx_emails_org_status ON emails(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_contacts_org_active ON contacts(organization_id, status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_campaigns_org_status ON campaigns(organization_id, status);

-- Analyze tables
ANALYZE emails;
ANALYZE contacts;
ANALYZE campaigns;
