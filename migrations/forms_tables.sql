-- Forms tables
CREATE TABLE IF NOT EXISTS forms (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL DEFAULT 'Untitled Form',
    description TEXT,
    form_type VARCHAR(50) DEFAULT 'inline',
    status VARCHAR(20) DEFAULT 'draft',
    fields TEXT DEFAULT '[]',
    design_settings TEXT DEFAULT '{}',
    trigger_type VARCHAR(50) DEFAULT 'immediate',
    trigger_value VARCHAR(50),
    success_action VARCHAR(50) DEFAULT 'message',
    success_message TEXT DEFAULT 'Thanks for subscribing!',
    success_redirect_url VARCHAR(500),
    double_optin BOOLEAN DEFAULT FALSE,
    add_to_list_id VARCHAR(36),
    add_tags VARCHAR(500),
    views INTEGER DEFAULT 0,
    submissions INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS form_submissions (
    id VARCHAR(36) PRIMARY KEY,
    form_id VARCHAR(36) NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    contact_id VARCHAR(36),
    data TEXT,
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    referrer VARCHAR(500),
    page_url VARCHAR(500),
    confirmation_token VARCHAR(100),
    confirmed BOOLEAN DEFAULT TRUE,
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_forms_org ON forms(organization_id);
CREATE INDEX IF NOT EXISTS idx_forms_status ON forms(status);
CREATE INDEX IF NOT EXISTS idx_form_submissions_form ON form_submissions(form_id);
CREATE INDEX IF NOT EXISTS idx_form_submissions_created ON form_submissions(created_at);
