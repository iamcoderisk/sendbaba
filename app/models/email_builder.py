"""
SendBaba Email Builder Module - Database Models
Handles email template storage for GrapeJS editor
"""
from datetime import datetime
import uuid
import json

try:
    from app import db
except ImportError:
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()


class EmailTemplate(db.Model):
    """Email template for drag-drop builder"""
    __tablename__ = 'email_templates'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False)
    
    # Template info
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default='custom')  # welcome, newsletter, promotional, transactional, custom
    
    # Template content
    subject = db.Column(db.String(500))
    preheader = db.Column(db.String(500))
    
    # GrapeJS data
    gjs_html = db.Column(db.Text)  # Final HTML output
    gjs_css = db.Column(db.Text)  # CSS styles
    gjs_components = db.Column(db.Text)  # JSON - GrapeJS component structure
    gjs_styles = db.Column(db.Text)  # JSON - GrapeJS style data
    gjs_assets = db.Column(db.Text)  # JSON - Assets used in template
    
    # Plain text version
    text_content = db.Column(db.Text)
    
    # Thumbnail
    thumbnail_url = db.Column(db.String(500))
    
    # Template settings
    is_system = db.Column(db.Boolean, default=False)  # System-provided templates
    is_shared = db.Column(db.Boolean, default=False)  # Shared with team
    is_locked = db.Column(db.Boolean, default=False)  # Prevent editing
    
    # Usage tracking
    usage_count = db.Column(db.Integer, default=0)
    last_used_at = db.Column(db.DateTime)
    
    # Status
    status = db.Column(db.String(20), default='draft')  # draft, active, archived
    
    # Version control
    version = db.Column(db.Integer, default=1)
    parent_template_id = db.Column(db.String(36))  # For versioning
    
    created_by = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def components(self):
        try:
            return json.loads(self.gjs_components) if self.gjs_components else []
        except:
            return []
    
    @property
    def styles(self):
        try:
            return json.loads(self.gjs_styles) if self.gjs_styles else []
        except:
            return []
    
    @property
    def assets(self):
        try:
            return json.loads(self.gjs_assets) if self.gjs_assets else []
        except:
            return []
    
    def get_full_html(self):
        """Generate full HTML email with styles"""
        if not self.gjs_html:
            return ''
        
        css = self.gjs_css or ''
        html = self.gjs_html or ''
        
        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    {css}
    </style>
</head>
<body>
    {html}
</body>
</html>'''
    
    def to_dict(self, include_content=True):
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'subject': self.subject,
            'preheader': self.preheader,
            'thumbnail_url': self.thumbnail_url,
            'is_system': self.is_system,
            'is_shared': self.is_shared,
            'status': self.status,
            'usage_count': self.usage_count,
            'version': self.version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_content:
            data['gjs_html'] = self.gjs_html
            data['gjs_css'] = self.gjs_css
            data['gjs_components'] = self.components
            data['gjs_styles'] = self.styles
            data['gjs_assets'] = self.assets
            data['text_content'] = self.text_content
        
        return data
    
    def to_grapesjs_data(self):
        """Return data in GrapeJS format"""
        return {
            'gjs-html': self.gjs_html or '',
            'gjs-css': self.gjs_css or '',
            'gjs-components': self.gjs_components or '[]',
            'gjs-styles': self.gjs_styles or '[]',
            'gjs-assets': self.gjs_assets or '[]'
        }


class EmailBlock(db.Model):
    """Reusable email content blocks"""
    __tablename__ = 'email_blocks'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36))
    
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default='custom')  # header, footer, content, button, image, social, divider, custom
    
    # Block content
    html = db.Column(db.Text, nullable=False)
    css = db.Column(db.Text)
    gjs_components = db.Column(db.Text)  # GrapeJS format
    
    # Thumbnail preview
    thumbnail_url = db.Column(db.String(500))
    
    # Settings
    is_system = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'html': self.html,
            'css': self.css,
            'thumbnail_url': self.thumbnail_url,
            'is_system': self.is_system,
            'is_active': self.is_active
        }
    
    def to_grapesjs_block(self):
        """Return as GrapeJS block definition"""
        return {
            'id': self.id,
            'label': self.name,
            'category': self.category.title(),
            'content': self.html,
            'attributes': {'class': f'sb-block-{self.category}'}
        }


class EmailAsset(db.Model):
    """Uploaded assets for email builder"""
    __tablename__ = 'email_assets'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False)
    
    # File info
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    file_type = db.Column(db.String(50))  # image, document
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.Integer)  # bytes
    
    # Storage
    storage_path = db.Column(db.String(500))
    url = db.Column(db.String(500), nullable=False)
    thumbnail_url = db.Column(db.String(500))
    
    # Image dimensions
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    
    # Metadata
    alt_text = db.Column(db.String(255))
    tags = db.Column(db.String(500))  # Comma-separated
    
    # Settings
    is_public = db.Column(db.Boolean, default=True)
    
    uploaded_by = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_type': self.file_type,
            'mime_type': self.mime_type,
            'file_size': self.file_size,
            'url': self.url,
            'thumbnail_url': self.thumbnail_url,
            'width': self.width,
            'height': self.height,
            'alt_text': self.alt_text,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def to_grapesjs_asset(self):
        """Return as GrapeJS asset"""
        return {
            'src': self.url,
            'type': 'image' if self.file_type == 'image' else 'other',
            'name': self.filename,
            'width': self.width,
            'height': self.height
        }


# Template categories
TEMPLATE_CATEGORIES = [
    {'value': 'welcome', 'label': 'Welcome', 'icon': 'fa-hand-wave'},
    {'value': 'newsletter', 'label': 'Newsletter', 'icon': 'fa-newspaper'},
    {'value': 'promotional', 'label': 'Promotional', 'icon': 'fa-tags'},
    {'value': 'transactional', 'label': 'Transactional', 'icon': 'fa-receipt'},
    {'value': 'announcement', 'label': 'Announcement', 'icon': 'fa-bullhorn'},
    {'value': 'event', 'label': 'Event', 'icon': 'fa-calendar'},
    {'value': 'custom', 'label': 'Custom', 'icon': 'fa-paint-brush'}
]

# Block categories
BLOCK_CATEGORIES = [
    {'value': 'header', 'label': 'Headers'},
    {'value': 'content', 'label': 'Content'},
    {'value': 'image', 'label': 'Images'},
    {'value': 'button', 'label': 'Buttons'},
    {'value': 'social', 'label': 'Social'},
    {'value': 'footer', 'label': 'Footers'},
    {'value': 'divider', 'label': 'Dividers'},
    {'value': 'custom', 'label': 'Custom'}
]
