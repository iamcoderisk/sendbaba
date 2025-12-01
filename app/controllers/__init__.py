"""
SendBaba Controllers Package
Register all blueprints
"""

from .form_controller import form_bp
from .workflow_controller import workflow_bp
from .segment_controller import segment_bp
from .integration_controller import integration_bp
from .reply_controller import reply_bp
from .email_builder_controller import email_builder_bp
from .campaign_controller import campaign_bp
from .auth_controller import auth_bp

__all__ = [
    'form_bp',
    'workflow_bp', 
    'segment_bp',
    'integration_bp',
    'reply_bp',
    'email_builder_bp',
    'campaign_bp',
    'auth_bp'
]

def register_blueprints(app):
    """Register all blueprints with the Flask app"""
    app.register_blueprint(auth_bp)  # Auth first for login/register routes
    app.register_blueprint(form_bp)
    app.register_blueprint(workflow_bp)
    app.register_blueprint(segment_bp)
    app.register_blueprint(integration_bp)
    app.register_blueprint(reply_bp)
    app.register_blueprint(email_builder_bp)
    app.register_blueprint(campaign_bp)
