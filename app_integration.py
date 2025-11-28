"""
SendBaba App Integration
Add this to your main app.py to register all feature blueprints
"""

# Add these imports at the top of your app.py
from app.controllers import (
    form_bp,
    workflow_bp,
    segment_bp,
    integration_bp,
    reply_bp,
    email_builder_bp
)

# Add this function to register all blueprints
def register_feature_blueprints(app):
    """Register all SendBaba feature blueprints"""
    
    # Forms - Signup form builder
    app.register_blueprint(form_bp)
    
    # Workflows - Email automation
    app.register_blueprint(workflow_bp)
    
    # Segments - Contact query builder
    app.register_blueprint(segment_bp)
    
    # Integrations - Third-party connectors
    app.register_blueprint(integration_bp)
    
    # Replies - AI email analysis
    app.register_blueprint(reply_bp)
    
    # Email Builder - GrapeJS template builder
    app.register_blueprint(email_builder_bp)
    
    print("✅ All SendBaba feature blueprints registered")


# OR use the simpler method:
# from app.controllers import register_blueprints
# register_blueprints(app)
