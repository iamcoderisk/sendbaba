"""
SendBaba Staging App - with Context Processor for Features
"""
from flask import Flask, redirect, session, render_template, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_user
import os
import logging

db = SQLAlchemy()
login_manager = LoginManager()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '60b55ca25a3391f98774c37d68c65b88')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://emailer:SecurePassword123@localhost:5432/emailer')
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"options": "-c search_path=public"}}
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    with app.app_context():
        # Register blueprints
        blueprints = [
            ('auth_controller', 'auth_bp', 'Auth'),
            ('billing_controller', 'billing_bp', 'Billing'),
            ('pricing_controller', 'pricing_bp', 'Pricing'),
            ('dashboard_controller', 'dashboard_bp', 'Dashboard'),
            ('campaign_controller', 'campaign_bp', 'Campaigns'),
            ('contact_controller', 'contact_bp', 'Contacts'),
            ('analytics_controller', 'analytics_bp', 'Analytics'),
            ('form_controller', 'form_bp', 'Forms'),
            ('workflow_controller', 'workflow_bp', 'Workflows'),
            ('segment_controller', 'segment_bp', 'Segments'),
            ('integration_controller', 'integration_bp', 'Integrations'),
            ('reply_controller', 'reply_bp', 'Reply AI'),
            ('email_builder_controller', 'email_builder_bp', 'Email Builder'),
            ('domain_controller', 'domain_bp', 'Domains'),
            ('team_controller', 'team_bp', 'Team'),
            ('settings_controller', 'settings_bp', 'Settings'),
        ]
        
        for module, bp_name, label in blueprints:
            try:
                mod = __import__(f'app.controllers.{module}', fromlist=[bp_name])
                bp = getattr(mod, bp_name)
                app.register_blueprint(bp)
                logger.info(f"✅ {label}")
            except Exception as e:
                logger.error(f"❌ {label}: {e}")
    
    # Context processor to inject features and subscription into all templates
    @app.context_processor
    def inject_features():
        """Inject features and subscription into all templates"""
        from sqlalchemy import text
        
        # Default features
        features = {
            'workflows': True,
            'segments': True,
            'team': True,
            'ai_reply': True
        }
        subscription = None
        
        try:
            if current_user.is_authenticated:
                org_id = getattr(current_user, 'organization_id', None)
                if org_id:
                    # Get features from organization
                    result = db.session.execute(text("""
                        SELECT feature_workflows, feature_segments, feature_team, feature_ai_reply
                        FROM organizations WHERE id = :org_id
                    """), {'org_id': org_id})
                    row = result.fetchone()
                    
                    if row:
                        features = {
                            'workflows': row[0] if row[0] is not None else True,
                            'segments': row[1] if row[1] is not None else True,
                            'team': row[2] if row[2] is not None else True,
                            'ai_reply': row[3] if row[3] is not None else True
                        }
                    
                    # Get subscription info
                    sub_result = db.session.execute(text("""
                        SELECT plan_name, status FROM subscriptions 
                        WHERE organization_id = :org_id ORDER BY created_at DESC LIMIT 1
                    """), {'org_id': org_id})
                    sub_row = sub_result.fetchone()
                    
                    if sub_row:
                        subscription = {
                            'plan_name': sub_row[0] or 'Free Plan',
                            'status': sub_row[1] or 'trial'
                        }
        except Exception as e:
            logger.error(f"Context processor error: {e}")
        
        return dict(features=features, subscription=subscription)
    
    @login_manager.user_loader
    def load_user(user_id):
        from sqlalchemy import text
        result = db.session.execute(
            text("SELECT id, email, organization_id, first_name FROM users WHERE id = :id"),
            {"id": user_id}
        ).fetchone()
        if result:
            class User:
                is_authenticated = True
                is_active = True
                is_anonymous = False
                def __init__(self, id, email, organization_id, first_name=None):
                    self.id = id
                    self.email = email
                    self.organization_id = organization_id
                    self.first_name = first_name
                def get_id(self):
                    return str(self.id)
            return User(result[0], result[1], result[2], result[3] if len(result) > 3 else None)
        return None
    
    @app.route('/')
    def index():
        """Home page - show landing for guests, redirect to dashboard for authenticated users"""
        if current_user.is_authenticated:
            return redirect('/dashboard/')
        return render_template('index.html')
    
    return app

# Register additional blueprints for enterprise features
try:
    from app.controllers.tracking_controller import tracking_bp
    from app.controllers.suppression_controller import suppression_bp
    from app.controllers.warmup_controller import warmup_bp
    from app.controllers.webhook_controller import webhook_bp
    from app.controllers.metrics_controller import metrics_bp
    
    # These will be registered in create_app
except ImportError as e:
    pass
