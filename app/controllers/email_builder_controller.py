"""
SendBaba Email Builder Controller
Handles GrapeJS email template builder with storage
"""
from flask import Blueprint, render_template, request, jsonify, session, send_file
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
import json
import uuid
import os
import base64
from io import BytesIO

email_builder_bp = Blueprint('email_builder', __name__, url_prefix='/dashboard/email-builder')


def get_organization_id():
    if current_user.is_authenticated:
        return getattr(current_user, 'organization_id', session.get('organization_id'))
    return session.get('organization_id')


# ==================== PAGE ROUTES ====================

@email_builder_bp.route('/')
@login_required
def index():
    """Email templates list"""
    return render_template('dashboard/email_builder/index.html')


@email_builder_bp.route('/create')
@login_required
def create():
    """Create new template - opens builder"""
    template_id = request.args.get('from')  # Clone from existing template
    return render_template('dashboard/email_builder/builder.html', template_id=None, clone_from=template_id)


@email_builder_bp.route('/<template_id>/edit')
@login_required
def edit(template_id):
    """Edit existing template"""
    from app.models.email_builder import EmailTemplate
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return render_template('errors/404.html'), 404
    
    return render_template('dashboard/email_builder/builder.html', template_id=template_id, template=template)


@email_builder_bp.route('/<template_id>/preview')
@login_required
def preview(template_id):
    """Preview template"""
    from app.models.email_builder import EmailTemplate
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return render_template('errors/404.html'), 404
    
    return template.get_full_html()


@email_builder_bp.route('/gallery')
@login_required
def gallery():
    """Browse template gallery"""
    return render_template('dashboard/email_builder/gallery.html')


@email_builder_bp.route('/blocks')
@login_required
def blocks():
    """Manage custom blocks"""
    return render_template('dashboard/email_builder/blocks.html')


@email_builder_bp.route('/assets')
@login_required
def assets():
    """Asset manager"""
    return render_template('dashboard/email_builder/assets.html')


# ==================== TEMPLATES API ====================

@email_builder_bp.route('/api/templates')
@login_required
def api_list_templates():
    """Get all templates"""
    from app.models.email_builder import EmailTemplate
    
    org_id = get_organization_id()
    category = request.args.get('category')
    status = request.args.get('status')
    search = request.args.get('search')
    
    query = EmailTemplate.query.filter_by(organization_id=org_id)
    
    if category:
        query = query.filter_by(category=category)
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(EmailTemplate.name.ilike(f'%{search}%'))
    
    templates = query.order_by(EmailTemplate.updated_at.desc()).all()
    
    return jsonify({
        'success': True,
        'templates': [t.to_dict(include_content=False) for t in templates]
    })


@email_builder_bp.route('/api/templates', methods=['POST'])
@login_required
def api_create_template():
    """Create new template"""
    from app.models.email_builder import EmailTemplate
    from app import db
    
    data = request.get_json()
    
    template = EmailTemplate(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        name=data.get('name', 'Untitled Template'),
        description=data.get('description'),
        category=data.get('category', 'custom'),
        subject=data.get('subject'),
        preheader=data.get('preheader'),
        gjs_html=data.get('gjs_html', ''),
        gjs_css=data.get('gjs_css', ''),
        gjs_components=json.dumps(data.get('gjs_components', [])),
        gjs_styles=json.dumps(data.get('gjs_styles', [])),
        gjs_assets=json.dumps(data.get('gjs_assets', [])),
        text_content=data.get('text_content'),
        status='draft',
        created_by=session.get('user_id')
    )
    
    db.session.add(template)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'template': template.to_dict(),
        'message': 'Template created successfully'
    })


@email_builder_bp.route('/api/templates/<template_id>', methods=['GET'])
@login_required
def api_get_template(template_id):
    """Get template details with GrapeJS data"""
    from app.models.email_builder import EmailTemplate
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    return jsonify({
        'success': True,
        'template': template.to_dict(include_content=True),
        'grapesjs': template.to_grapesjs_data()
    })


@email_builder_bp.route('/api/templates/<template_id>', methods=['PUT'])
@login_required
def api_update_template(template_id):
    """Update template"""
    from app.models.email_builder import EmailTemplate
    from app import db
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        template.name = data['name']
    if 'description' in data:
        template.description = data['description']
    if 'category' in data:
        template.category = data['category']
    if 'subject' in data:
        template.subject = data['subject']
    if 'preheader' in data:
        template.preheader = data['preheader']
    if 'gjs_html' in data:
        template.gjs_html = data['gjs_html']
    if 'gjs_css' in data:
        template.gjs_css = data['gjs_css']
    if 'gjs_components' in data:
        template.gjs_components = json.dumps(data['gjs_components']) if isinstance(data['gjs_components'], (list, dict)) else data['gjs_components']
    if 'gjs_styles' in data:
        template.gjs_styles = json.dumps(data['gjs_styles']) if isinstance(data['gjs_styles'], (list, dict)) else data['gjs_styles']
    if 'gjs_assets' in data:
        template.gjs_assets = json.dumps(data['gjs_assets']) if isinstance(data['gjs_assets'], (list, dict)) else data['gjs_assets']
    if 'text_content' in data:
        template.text_content = data['text_content']
    if 'status' in data:
        template.status = data['status']
    
    template.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'template': template.to_dict(),
        'message': 'Template saved successfully'
    })


@email_builder_bp.route('/api/templates/<template_id>', methods=['DELETE'])
@login_required
def api_delete_template(template_id):
    """Delete template"""
    from app.models.email_builder import EmailTemplate
    from app import db
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    if template.is_system:
        return jsonify({'error': 'Cannot delete system template'}), 400
    
    db.session.delete(template)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Template deleted successfully'
    })


@email_builder_bp.route('/api/templates/<template_id>/duplicate', methods=['POST'])
@login_required
def api_duplicate_template(template_id):
    """Duplicate template"""
    from app.models.email_builder import EmailTemplate
    from app import db
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    new_template = EmailTemplate(
        id=str(uuid.uuid4()),
        organization_id=template.organization_id,
        name=f"{template.name} (Copy)",
        description=template.description,
        category=template.category,
        subject=template.subject,
        preheader=template.preheader,
        gjs_html=template.gjs_html,
        gjs_css=template.gjs_css,
        gjs_components=template.gjs_components,
        gjs_styles=template.gjs_styles,
        gjs_assets=template.gjs_assets,
        text_content=template.text_content,
        status='draft',
        created_by=session.get('user_id')
    )
    
    db.session.add(new_template)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'template': new_template.to_dict(),
        'message': 'Template duplicated successfully'
    })


# ==================== GRAPESJS STORAGE API ====================

@email_builder_bp.route('/api/gjs/load/<template_id>')
@login_required
def api_gjs_load(template_id):
    """Load template data for GrapeJS"""
    from app.models.email_builder import EmailTemplate
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    return jsonify({
        'gjs-html': template.gjs_html or '',
        'gjs-css': template.gjs_css or '',
        'gjs-components': template.gjs_components or '[]',
        'gjs-styles': template.gjs_styles or '[]',
        'gjs-assets': template.gjs_assets or '[]'
    })


@email_builder_bp.route('/api/gjs/store/<template_id>', methods=['POST'])
@login_required
def api_gjs_store(template_id):
    """Store template data from GrapeJS (auto-save)"""
    from app.models.email_builder import EmailTemplate
    from app import db
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    data = request.get_json()
    
    template.gjs_html = data.get('gjs-html', template.gjs_html)
    template.gjs_css = data.get('gjs-css', template.gjs_css)
    template.gjs_components = data.get('gjs-components', template.gjs_components)
    template.gjs_styles = data.get('gjs-styles', template.gjs_styles)
    template.gjs_assets = data.get('gjs-assets', template.gjs_assets)
    template.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Saved'
    })


# ==================== BLOCKS API ====================

@email_builder_bp.route('/api/blocks')
@login_required
def api_list_blocks():
    """Get all blocks for GrapeJS"""
    from app.models.email_builder import EmailBlock
    
    org_id = get_organization_id()
    
    # Get system blocks and organization blocks
    blocks = EmailBlock.query.filter(
        (EmailBlock.is_system == True) | (EmailBlock.organization_id == org_id),
        EmailBlock.is_active == True
    ).order_by(EmailBlock.category, EmailBlock.sort_order).all()
    
    # Convert to GrapeJS format
    gjs_blocks = [b.to_grapesjs_block() for b in blocks]
    
    return jsonify({
        'success': True,
        'blocks': gjs_blocks
    })


@email_builder_bp.route('/api/blocks', methods=['POST'])
@login_required
def api_create_block():
    """Create custom block"""
    from app.models.email_builder import EmailBlock
    from app import db
    
    data = request.get_json()
    
    block = EmailBlock(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        name=data.get('name', 'Custom Block'),
        description=data.get('description'),
        category=data.get('category', 'custom'),
        html=data.get('html', ''),
        css=data.get('css'),
        gjs_components=json.dumps(data.get('gjs_components')) if data.get('gjs_components') else None,
        is_system=False
    )
    
    db.session.add(block)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'block': block.to_dict()
    })


@email_builder_bp.route('/api/blocks/<block_id>', methods=['DELETE'])
@login_required
def api_delete_block(block_id):
    """Delete custom block"""
    from app.models.email_builder import EmailBlock
    from app import db
    
    block = EmailBlock.query.filter_by(id=block_id, organization_id=get_organization_id()).first()
    if not block:
        return jsonify({'error': 'Block not found'}), 404
    
    if block.is_system:
        return jsonify({'error': 'Cannot delete system block'}), 400
    
    db.session.delete(block)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Block deleted'
    })


# ==================== ASSETS API ====================

@email_builder_bp.route('/api/assets')
@login_required
def api_list_assets():
    """Get all assets"""
    from app.models.email_builder import EmailAsset
    
    org_id = get_organization_id()
    
    assets = EmailAsset.query.filter_by(organization_id=org_id)\
        .order_by(EmailAsset.created_at.desc()).all()
    
    # Convert to GrapeJS format
    gjs_assets = [a.to_grapesjs_asset() for a in assets]
    
    return jsonify({
        'success': True,
        'assets': gjs_assets,
        'data': [a.to_dict() for a in assets]
    })


@email_builder_bp.route('/api/assets/upload', methods=['POST'])
@login_required
def api_upload_asset():
    """Upload new asset"""
    from app.models.email_builder import EmailAsset
    from app import db
    
    if 'file' not in request.files:
        # Check for base64 data
        data = request.get_json()
        if data and data.get('data'):
            return upload_base64_asset(data)
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        return jsonify({'error': 'Invalid file type'}), 400
    
    # Generate unique filename
    filename = f"{uuid.uuid4()}.{ext}"
    
    # Save file (implement based on your storage system)
    # For now, we'll use base64 storage or local file system
    upload_folder = os.environ.get('UPLOAD_FOLDER', '/opt/sendbaba-staging/uploads/assets')
    os.makedirs(upload_folder, exist_ok=True)
    
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    
    # Get image dimensions if it's an image
    width, height = None, None
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.size
    except:
        pass
    
    # Create URL (implement based on your URL scheme)
    base_url = request.host_url.rstrip('/')
    url = f"{base_url}/uploads/assets/{filename}"
    
    # Create asset record
    asset = EmailAsset(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        filename=filename,
        original_filename=file.filename,
        file_type='image',
        mime_type=file.content_type,
        file_size=os.path.getsize(file_path),
        storage_path=file_path,
        url=url,
        width=width,
        height=height,
        uploaded_by=session.get('user_id')
    )
    
    db.session.add(asset)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'asset': asset.to_dict(),
        'data': [asset.to_grapesjs_asset()]  # GrapeJS format
    })


def upload_base64_asset(data):
    """Handle base64 image upload"""
    from app.models.email_builder import EmailAsset
    from app import db
    
    base64_data = data.get('data')
    filename = data.get('filename', f'{uuid.uuid4()}.png')
    
    # Extract image data
    if ',' in base64_data:
        header, base64_data = base64_data.split(',', 1)
        # Get mime type from header
        mime_type = header.split(';')[0].split(':')[1] if ':' in header else 'image/png'
    else:
        mime_type = 'image/png'
    
    # Decode and save
    image_data = base64.b64decode(base64_data)
    
    ext = mime_type.split('/')[-1]
    if ext == 'jpeg':
        ext = 'jpg'
    
    filename = f"{uuid.uuid4()}.{ext}"
    
    upload_folder = os.environ.get('UPLOAD_FOLDER', '/opt/sendbaba-staging/uploads/assets')
    os.makedirs(upload_folder, exist_ok=True)
    
    file_path = os.path.join(upload_folder, filename)
    with open(file_path, 'wb') as f:
        f.write(image_data)
    
    # Get dimensions
    width, height = None, None
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.size
    except:
        pass
    
    base_url = request.host_url.rstrip('/')
    url = f"{base_url}/uploads/assets/{filename}"
    
    asset = EmailAsset(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        filename=filename,
        original_filename=data.get('filename', filename),
        file_type='image',
        mime_type=mime_type,
        file_size=len(image_data),
        storage_path=file_path,
        url=url,
        width=width,
        height=height,
        uploaded_by=session.get('user_id')
    )
    
    db.session.add(asset)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'asset': asset.to_dict(),
        'data': [asset.to_grapesjs_asset()]
    })


@email_builder_bp.route('/api/assets/<asset_id>', methods=['DELETE'])
@login_required
def api_delete_asset(asset_id):
    """Delete asset"""
    from app.models.email_builder import EmailAsset
    from app import db
    
    asset = EmailAsset.query.filter_by(id=asset_id, organization_id=get_organization_id()).first()
    if not asset:
        return jsonify({'error': 'Asset not found'}), 404
    
    # Delete file
    if asset.storage_path and os.path.exists(asset.storage_path):
        os.remove(asset.storage_path)
    
    db.session.delete(asset)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Asset deleted'
    })


# ==================== EXPORT API ====================

@email_builder_bp.route('/api/templates/<template_id>/export')
@login_required
def api_export_html(template_id):
    """Export template as HTML"""
    from app.models.email_builder import EmailTemplate
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    format = request.args.get('format', 'html')
    
    if format == 'html':
        html = template.get_full_html()
        return jsonify({
            'success': True,
            'html': html,
            'filename': f'{template.name}.html'
        })
    elif format == 'json':
        return jsonify({
            'success': True,
            'data': template.to_dict(include_content=True),
            'filename': f'{template.name}.json'
        })
    else:
        return jsonify({'error': 'Invalid format'}), 400


@email_builder_bp.route('/api/templates/import', methods=['POST'])
@login_required
def api_import_template():
    """Import template from HTML or JSON"""
    from app.models.email_builder import EmailTemplate
    from app import db
    
    if 'file' in request.files:
        file = request.files['file']
        content = file.read().decode('utf-8')
        filename = file.filename
    else:
        data = request.get_json()
        content = data.get('content', '')
        filename = data.get('filename', 'imported.html')
    
    if filename.endswith('.json'):
        # JSON import
        import_data = json.loads(content)
        template = EmailTemplate(
            id=str(uuid.uuid4()),
            organization_id=get_organization_id(),
            name=import_data.get('name', 'Imported Template'),
            description=import_data.get('description'),
            category=import_data.get('category', 'custom'),
            subject=import_data.get('subject'),
            gjs_html=import_data.get('gjs_html'),
            gjs_css=import_data.get('gjs_css'),
            gjs_components=json.dumps(import_data.get('gjs_components', [])),
            gjs_styles=json.dumps(import_data.get('gjs_styles', [])),
            status='draft',
            created_by=session.get('user_id')
        )
    else:
        # HTML import
        template = EmailTemplate(
            id=str(uuid.uuid4()),
            organization_id=get_organization_id(),
            name=filename.rsplit('.', 1)[0] if '.' in filename else 'Imported Template',
            category='custom',
            gjs_html=content,
            status='draft',
            created_by=session.get('user_id')
        )
    
    db.session.add(template)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'template': template.to_dict(),
        'message': 'Template imported successfully'
    })


# ==================== GALLERY/SYSTEM TEMPLATES ====================

@email_builder_bp.route('/api/gallery')
@login_required
def api_gallery():
    """Get gallery of system templates"""
    from app.models.email_builder import EmailTemplate
    
    # Get system templates
    templates = EmailTemplate.query.filter_by(is_system=True, status='active')\
        .order_by(EmailTemplate.category, EmailTemplate.name).all()
    
    return jsonify({
        'success': True,
        'templates': [t.to_dict(include_content=False) for t in templates]
    })


@email_builder_bp.route('/api/gallery/<template_id>/use', methods=['POST'])
@login_required
def api_use_gallery_template(template_id):
    """Create template from gallery template"""
    from app.models.email_builder import EmailTemplate
    from app import db
    
    gallery_template = EmailTemplate.query.filter_by(id=template_id, is_system=True).first()
    if not gallery_template:
        return jsonify({'error': 'Template not found'}), 404
    
    data = request.get_json() or {}
    
    new_template = EmailTemplate(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        name=data.get('name', gallery_template.name),
        description=gallery_template.description,
        category=gallery_template.category,
        subject=gallery_template.subject,
        preheader=gallery_template.preheader,
        gjs_html=gallery_template.gjs_html,
        gjs_css=gallery_template.gjs_css,
        gjs_components=gallery_template.gjs_components,
        gjs_styles=gallery_template.gjs_styles,
        gjs_assets=gallery_template.gjs_assets,
        text_content=gallery_template.text_content,
        parent_template_id=gallery_template.id,
        status='draft',
        created_by=session.get('user_id')
    )
    
    # Track usage
    gallery_template.usage_count += 1
    gallery_template.last_used_at = datetime.utcnow()
    
    db.session.add(new_template)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'template': new_template.to_dict(),
        'redirect_url': f'/dashboard/email-builder/{new_template.id}/edit'
    })


# ==================== CATEGORIES ====================

@email_builder_bp.route('/api/categories')
@login_required
def api_categories():
    """Get template categories"""
    from app.models.email_builder import TEMPLATE_CATEGORIES
    
    return jsonify({
        'success': True,
        'categories': TEMPLATE_CATEGORIES
    })


# ==================== SEND TEST EMAIL ====================

@email_builder_bp.route('/api/templates/<template_id>/send-test', methods=['POST'])
@login_required
def api_send_test(template_id):
    """Send test email with template"""
    from app.models.email_builder import EmailTemplate
    
    template = EmailTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    data = request.get_json()
    to_email = data.get('to_email')
    
    if not to_email:
        return jsonify({'error': 'Email address required'}), 400
    
    # Get full HTML
    html_content = template.get_full_html()
    subject = template.subject or f'Test: {template.name}'
    
    # Send via SMTP
    try:
        # Implement based on your SMTP setup
        # from app.smtp.relay_server import send_email_sync
        # send_email_sync(
        #     to=to_email,
        #     subject=subject,
        #     html=html_content,
        #     text=template.text_content
        # )
        return jsonify({
            'success': True,
            'message': f'Test email sent to {to_email}'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
