"""
SendBaba Staging App - with Context Processor for Features
"""
from flask import Flask, redirect, session, render_template_string, g
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
    login_manager.login_view = 'login'
    
    with app.app_context():
        # Register blueprints
        blueprints = [
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
            text("SELECT id, email, organization_id FROM users WHERE id = :id"),
            {"id": user_id}
        ).fetchone()
        if result:
            class User:
                is_authenticated = True
                is_active = True
                is_anonymous = False
                def __init__(self, id, email, organization_id):
                    self.id = id
                    self.email = email
                    self.organization_id = organization_id
                def get_id(self):
                    return str(self.id)
            return User(result[0], result[1], result[2])
        return None
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        from flask import request
        from werkzeug.security import check_password_hash
        from sqlalchemy import text
        
        if current_user.is_authenticated:
            return redirect('/dashboard')
        
        error = None
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')
            
            result = db.session.execute(
                text("SELECT id, email, password_hash, organization_id FROM users WHERE email = :email"),
                {"email": email}
            ).fetchone()
            
            if result and check_password_hash(result[2], password):
                class User:
                    is_authenticated = True
                    is_active = True
                    is_anonymous = False
                    def __init__(self, id, email, organization_id):
                        self.id = id
                        self.email = email
                        self.organization_id = organization_id
                    def get_id(self):
                        return str(self.id)
                
                user = User(result[0], result[1], result[3])
                login_user(user)
                session['user_id'] = result[0]
                session['organization_id'] = result[3]
                next_page = request.args.get('next', '/dashboard')
                return redirect(next_page)
            else:
                error = "Invalid email or password"
        
        return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Login - SendBaba</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center">
    <div class="bg-white p-8 rounded-2xl shadow-lg w-full max-w-md">
        <div class="text-center mb-8">
            <div class="w-16 h-16 bg-gradient-to-br from-orange-500 to-orange-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <i class="fas fa-paper-plane text-white text-2xl"></i>
            </div>
            <h1 class="text-2xl font-bold text-gray-900">Welcome Back</h1>
            <p class="text-gray-500">Sign in to your SendBaba account</p>
        </div>
        {% if error %}
        <div class="mb-4 p-4 bg-red-50 text-red-700 rounded-xl text-sm">
            <i class="fas fa-exclamation-circle mr-2"></i>{{ error }}
        </div>
        {% endif %}
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Email</label>
                <input type="email" name="email" required class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-orange-500 focus:border-orange-500">
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Password</label>
                <input type="password" name="password" required class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-orange-500 focus:border-orange-500">
            </div>
            <button type="submit" class="w-full py-3 bg-gradient-to-r from-orange-500 to-orange-600 text-white rounded-xl font-semibold hover:shadow-lg transition">
                Sign In
            </button>
        </form>
    </div>
</body>
</html>
        ''', error=error)
    
    @app.route('/logout')
    @app.route('/auth/logout')
    def logout():
        from flask_login import logout_user
        logout_user()
        session.clear()
        return redirect('/login')
    
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect('/dashboard')
        return redirect('/login')
    
    return app
