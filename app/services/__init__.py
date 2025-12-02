"""SendBaba Services"""
# Import what exists
try:
    from .email_service import EmailService, email_service
except ImportError:
    EmailService = None
    email_service = None

try:
    from .email_service import on_user_register, on_user_login
except ImportError:
    on_user_register = None
    on_user_login = None
