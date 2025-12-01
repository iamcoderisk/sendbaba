"""
SendBaba Forms Controller
Handles form builder, submissions, and embed code generation
"""
from flask import Blueprint, render_template, request, jsonify, session, current_app, make_response
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
import json
import uuid
import secrets

form_bp = Blueprint('forms', __name__, url_prefix='/dashboard/forms')


def get_organization_id():
    if current_user.is_authenticated:
        return getattr(current_user, 'organization_id', session.get('organization_id'))
    return session.get('organization_id')


# ==================== PAGE ROUTES ====================

@form_bp.route('/')
@login_required
def index():
    """Forms list page"""
    return render_template('dashboard/forms/index.html')


@form_bp.route('/create')
@login_required
def create():
    """Create new form page"""
    form_type = request.args.get('type', 'inline')
    return render_template('dashboard/forms/builder.html', form_type=form_type, form=None)


@form_bp.route('/<form_id>/edit')
@login_required
def edit(form_id):
    """Edit form page"""
    from app.models.forms import Form
    from app import db
    
    form = Form.query.filter_by(id=form_id, organization_id=get_organization_id()).first()
    if not form:
        return render_template('errors/404.html'), 404
    
    return render_template('dashboard/forms/builder.html', form=form)


@form_bp.route('/<form_id>/submissions')
@login_required
def submissions(form_id):
    """View form submissions"""
    return render_template('dashboard/forms/submissions.html', form_id=form_id)


# ==================== API ROUTES ====================

@form_bp.route('/api/list')
@login_required
def api_list():
    """Get all forms for organization"""
    from app.models.forms import Form
    from app import db
    
    org_id = get_organization_id()
    
    # Filter params
    form_type = request.args.get('type')
    status = request.args.get('status')
    search = request.args.get('search')
    
    query = Form.query.filter_by(organization_id=org_id)
    
    if form_type:
        query = query.filter_by(form_type=form_type)
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(Form.name.ilike(f'%{search}%'))
    
    forms = query.order_by(Form.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'forms': [f.to_dict() for f in forms]
    })


@form_bp.route('/api/create', methods=['POST'])
@login_required
def api_create():
    """Create new form"""
    from app.models.forms import Form
    from app import db
    
    data = request.get_json()
    
    form = Form(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        name=data.get('name', 'Untitled Form'),
        description=data.get('description'),
        form_type=data.get('form_type', 'inline'),
        fields=json.dumps(data.get('fields', [
            {'id': 'email', 'type': 'email', 'label': 'Email', 'required': True, 'placeholder': 'Enter your email'}
        ])),
        design_settings=json.dumps(data.get('design', {
            'primary_color': '#8B5CF6',
            'background_color': '#FFFFFF',
            'text_color': '#1F2937',
            'button_text': 'Subscribe',
            'font_family': 'Inter'
        })),
        trigger_type=data.get('trigger_type', 'immediate'),
        trigger_value=data.get('trigger_value'),
        success_action=data.get('success_action', 'message'),
        success_message=data.get('success_message', 'Thanks for subscribing!'),
        double_optin=data.get('double_optin', False),
        add_to_list_id=data.get('add_to_list_id'),
        add_tags=data.get('add_tags'),
        status='draft'
    )
    
    db.session.add(form)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'form': form.to_dict(),
        'message': 'Form created successfully'
    })


@form_bp.route('/api/<form_id>', methods=['GET'])
@login_required
def api_get(form_id):
    """Get form details"""
    from app.models.forms import Form
    
    form = Form.query.filter_by(id=form_id, organization_id=get_organization_id()).first()
    if not form:
        return jsonify({'error': 'Form not found'}), 404
    
    return jsonify({
        'success': True,
        'form': form.to_dict()
    })


@form_bp.route('/api/<form_id>', methods=['PUT'])
@login_required
def api_update(form_id):
    """Update form"""
    from app.models.forms import Form
    from app import db
    
    form = Form.query.filter_by(id=form_id, organization_id=get_organization_id()).first()
    if not form:
        return jsonify({'error': 'Form not found'}), 404
    
    data = request.get_json()
    
    # Update fields
    if 'name' in data:
        form.name = data['name']
    if 'description' in data:
        form.description = data['description']
    if 'fields' in data:
        form.fields = json.dumps(data['fields'])
    if 'design' in data:
        form.design_settings = json.dumps(data['design'])
    if 'trigger_type' in data:
        form.trigger_type = data['trigger_type']
    if 'trigger_value' in data:
        form.trigger_value = data['trigger_value']
    if 'success_action' in data:
        form.success_action = data['success_action']
    if 'success_message' in data:
        form.success_message = data['success_message']
    if 'success_redirect_url' in data:
        form.success_redirect_url = data['success_redirect_url']
    if 'double_optin' in data:
        form.double_optin = data['double_optin']
    if 'add_to_list_id' in data:
        form.add_to_list_id = data['add_to_list_id']
    if 'add_tags' in data:
        form.add_tags = data['add_tags']
    if 'status' in data:
        form.status = data['status']
    
    form.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'form': form.to_dict(),
        'message': 'Form updated successfully'
    })


@form_bp.route('/api/<form_id>', methods=['DELETE'])
@login_required
def api_delete(form_id):
    """Delete form"""
    from app.models.forms import Form
    from app import db
    
    form = Form.query.filter_by(id=form_id, organization_id=get_organization_id()).first()
    if not form:
        return jsonify({'error': 'Form not found'}), 404
    
    db.session.delete(form)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Form deleted successfully'
    })


@form_bp.route('/api/<form_id>/duplicate', methods=['POST'])
@login_required
def api_duplicate(form_id):
    """Duplicate a form"""
    from app.models.forms import Form
    from app import db
    
    form = Form.query.filter_by(id=form_id, organization_id=get_organization_id()).first()
    if not form:
        return jsonify({'error': 'Form not found'}), 404
    
    new_form = Form(
        id=str(uuid.uuid4()),
        organization_id=form.organization_id,
        name=f"{form.name} (Copy)",
        description=form.description,
        form_type=form.form_type,
        fields=form.fields,
        design_settings=form.design_settings,
        trigger_type=form.trigger_type,
        trigger_value=form.trigger_value,
        success_action=form.success_action,
        success_message=form.success_message,
        success_redirect_url=form.success_redirect_url,
        double_optin=form.double_optin,
        add_to_list_id=form.add_to_list_id,
        add_tags=form.add_tags,
        status='draft'
    )
    
    db.session.add(new_form)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'form': new_form.to_dict(),
        'message': 'Form duplicated successfully'
    })


@form_bp.route('/api/<form_id>/submissions')
@login_required
def api_submissions(form_id):
    """Get form submissions"""
    from app.models.forms import Form, FormSubmission
    
    form = Form.query.filter_by(id=form_id, organization_id=get_organization_id()).first()
    if not form:
        return jsonify({'error': 'Form not found'}), 404
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    submissions = FormSubmission.query.filter_by(form_id=form_id)\
        .order_by(FormSubmission.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'submissions': [s.to_dict() for s in submissions.items],
        'total': submissions.total,
        'pages': submissions.pages,
        'current_page': page
    })


@form_bp.route('/api/<form_id>/embed-code')
@login_required
def api_embed_code(form_id):
    """Get embed code for form"""
    from app.models.forms import Form
    
    form = Form.query.filter_by(id=form_id, organization_id=get_organization_id()).first()
    if not form:
        return jsonify({'error': 'Form not found'}), 404
    
    base_url = request.host_url.rstrip('/')
    embed_code = form.get_embed_code(base_url)
    
    return jsonify({
        'success': True,
        'embed_code': embed_code,
        'form_url': f"{base_url}/forms/{form_id}"
    })


@form_bp.route('/api/<form_id>/stats')
@login_required
def api_stats(form_id):
    """Get form statistics"""
    from app.models.forms import Form, FormSubmission
    from app import db
    from sqlalchemy import func
    from datetime import timedelta
    
    form = Form.query.filter_by(id=form_id, organization_id=get_organization_id()).first()
    if not form:
        return jsonify({'error': 'Form not found'}), 404
    
    # Get daily submissions for last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_stats = db.session.query(
        func.date(FormSubmission.created_at).label('date'),
        func.count(FormSubmission.id).label('count')
    ).filter(
        FormSubmission.form_id == form_id,
        FormSubmission.created_at >= thirty_days_ago
    ).group_by(func.date(FormSubmission.created_at)).all()
    
    return jsonify({
        'success': True,
        'stats': {
            'views': form.views,
            'submissions': form.submissions,
            'conversion_rate': form.conversion_rate,
            'daily_submissions': [{'date': str(d.date), 'count': d.count} for d in daily_stats]
        }
    })


# ==================== PUBLIC ROUTES (No auth required) ====================

@form_bp.route('/embed/<form_id>.js')
def embed_script(form_id):
    """Generate JavaScript embed for form"""
    from app.models.forms import Form
    
    form = Form.query.filter_by(id=form_id, status='active').first()
    if not form:
        return 'console.error("SendBaba: Form not found");', 404, {'Content-Type': 'application/javascript'}
    
    # Track view
    form.views += 1
    from app import db
    db.session.commit()
    
    base_url = request.host_url.rstrip('/')
    design = form.design
    fields = form.fields_list
    
    # Generate the embed JavaScript
    js_code = f'''
(function() {{
    var formId = "{form.id}";
    var formType = "{form.form_type}";
    var config = {{
        primaryColor: "{design.get('primary_color', '#8B5CF6')}",
        backgroundColor: "{design.get('background_color', '#FFFFFF')}",
        textColor: "{design.get('text_color', '#1F2937')}",
        buttonText: "{design.get('button_text', 'Subscribe')}",
        successMessage: "{form.success_message}",
        successAction: "{form.success_action}",
        redirectUrl: "{form.success_redirect_url or ''}",
        triggerType: "{form.trigger_type}",
        triggerValue: "{form.trigger_value or ''}"
    }};
    var fields = {json.dumps(fields)};
    
    function createForm() {{
        var container = document.getElementById("sb-form-" + formId);
        if (!container && formType === "inline") {{
            console.error("SendBaba: Container not found");
            return;
        }}
        
        var form = document.createElement("form");
        form.className = "sb-form";
        form.id = "sb-form-inner-" + formId;
        form.style.cssText = "background:" + config.backgroundColor + ";padding:24px;border-radius:8px;max-width:400px;font-family:system-ui,-apple-system,sans-serif;";
        
        fields.forEach(function(field) {{
            var wrapper = document.createElement("div");
            wrapper.style.marginBottom = "16px";
            
            if (field.label) {{
                var label = document.createElement("label");
                label.textContent = field.label + (field.required ? " *" : "");
                label.style.cssText = "display:block;margin-bottom:4px;font-size:14px;color:" + config.textColor + ";";
                wrapper.appendChild(label);
            }}
            
            var input = document.createElement("input");
            input.type = field.type || "text";
            input.name = field.id;
            input.placeholder = field.placeholder || "";
            input.required = field.required || false;
            input.style.cssText = "width:100%;padding:10px 12px;border:1px solid #D1D5DB;border-radius:6px;font-size:14px;box-sizing:border-box;";
            wrapper.appendChild(input);
            
            form.appendChild(wrapper);
        }});
        
        var button = document.createElement("button");
        button.type = "submit";
        button.textContent = config.buttonText;
        button.style.cssText = "width:100%;padding:12px;background:" + config.primaryColor + ";color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;";
        form.appendChild(button);
        
        form.onsubmit = function(e) {{
            e.preventDefault();
            submitForm(form);
        }};
        
        if (formType === "inline") {{
            container.appendChild(form);
        }} else if (formType === "popup") {{
            showPopup(form);
        }} else if (formType === "slide_in") {{
            showSlideIn(form);
        }} else if (formType === "sticky_bar") {{
            showStickyBar(form);
        }}
    }}
    
    function showPopup(form) {{
        var overlay = document.createElement("div");
        overlay.id = "sb-popup-overlay-" + formId;
        overlay.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:99999;";
        
        var modal = document.createElement("div");
        modal.style.cssText = "background:#fff;border-radius:12px;padding:8px;position:relative;max-width:90%;";
        
        var close = document.createElement("button");
        close.innerHTML = "&times;";
        close.style.cssText = "position:absolute;top:8px;right:12px;background:none;border:none;font-size:24px;cursor:pointer;color:#666;";
        close.onclick = function() {{ overlay.remove(); }};
        
        modal.appendChild(close);
        modal.appendChild(form);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
    }}
    
    function showSlideIn(form) {{
        var container = document.createElement("div");
        container.id = "sb-slidein-" + formId;
        container.style.cssText = "position:fixed;bottom:20px;right:20px;z-index:99999;box-shadow:0 4px 20px rgba(0,0,0,0.15);border-radius:12px;";
        
        var close = document.createElement("button");
        close.innerHTML = "&times;";
        close.style.cssText = "position:absolute;top:8px;right:12px;background:none;border:none;font-size:20px;cursor:pointer;color:#666;z-index:1;";
        close.onclick = function() {{ container.remove(); }};
        
        container.appendChild(close);
        container.appendChild(form);
        document.body.appendChild(container);
    }}
    
    function showStickyBar(form) {{
        form.style.cssText = "display:flex;align-items:center;gap:12px;padding:12px 24px;max-width:none;border-radius:0;";
        form.querySelector("div").style.marginBottom = "0";
        form.querySelector("button").style.width = "auto";
        
        var bar = document.createElement("div");
        bar.id = "sb-stickybar-" + formId;
        bar.style.cssText = "position:fixed;bottom:0;left:0;right:0;background:" + config.backgroundColor + ";box-shadow:0 -2px 10px rgba(0,0,0,0.1);z-index:99999;";
        
        var close = document.createElement("button");
        close.innerHTML = "&times;";
        close.style.cssText = "position:absolute;top:50%;right:16px;transform:translateY(-50%);background:none;border:none;font-size:20px;cursor:pointer;color:#666;";
        close.onclick = function() {{ bar.remove(); }};
        
        bar.appendChild(form);
        bar.appendChild(close);
        document.body.appendChild(bar);
    }}
    
    function submitForm(form) {{
        var data = {{}};
        var inputs = form.querySelectorAll("input");
        inputs.forEach(function(input) {{
            data[input.name] = input.value;
        }});
        
        var button = form.querySelector("button");
        button.disabled = true;
        button.textContent = "Submitting...";
        
        fetch("{base_url}/forms/submit/" + formId, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify(data)
        }})
        .then(function(r) {{ return r.json(); }})
        .then(function(result) {{
            if (result.success) {{
                if (config.successAction === "redirect" && config.redirectUrl) {{
                    window.location.href = config.redirectUrl;
                }} else {{
                    form.innerHTML = "<p style='text-align:center;color:" + config.textColor + ";padding:20px;'>" + config.successMessage + "</p>";
                }}
            }} else {{
                alert(result.error || "Submission failed");
                button.disabled = false;
                button.textContent = config.buttonText;
            }}
        }})
        .catch(function() {{
            alert("Network error. Please try again.");
            button.disabled = false;
            button.textContent = config.buttonText;
        }});
    }}
    
    function init() {{
        if (config.triggerType === "immediate") {{
            createForm();
        }} else if (config.triggerType === "time_delay") {{
            setTimeout(createForm, parseInt(config.triggerValue) * 1000);
        }} else if (config.triggerType === "scroll") {{
            var triggered = false;
            window.addEventListener("scroll", function() {{
                if (triggered) return;
                var scrollPercent = (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100;
                if (scrollPercent >= parseInt(config.triggerValue)) {{
                    triggered = true;
                    createForm();
                }}
            }});
        }} else if (config.triggerType === "exit_intent") {{
            document.addEventListener("mouseout", function(e) {{
                if (e.clientY < 10) createForm();
            }}, {{ once: true }});
        }} else {{
            createForm();
        }}
    }}
    
    if (document.readyState === "loading") {{
        document.addEventListener("DOMContentLoaded", init);
    }} else {{
        init();
    }}
}})();
'''
    
    response = make_response(js_code)
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response


@form_bp.route('/submit/<form_id>', methods=['POST'])
def submit_form(form_id):
    """Handle form submission (public endpoint)"""
    from app.models.forms import Form, FormSubmission
    from app import db
    
    form = Form.query.filter_by(id=form_id, status='active').first()
    if not form:
        return jsonify({'success': False, 'error': 'Form not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    # Create submission
    submission = FormSubmission(
        id=str(uuid.uuid4()),
        form_id=form_id,
        data=json.dumps(data),
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500],
        referrer=request.headers.get('Referer', '')[:500],
        page_url=request.headers.get('Origin', '')
    )
    
    # Handle double opt-in
    if form.double_optin:
        submission.confirmation_token = secrets.token_urlsafe(32)
        submission.confirmed = False
        # TODO: Send confirmation email
    else:
        submission.confirmed = True
        # Create contact if email provided
        email = data.get('email')
        if email:
            contact_id = create_contact_from_submission(form, data)
            submission.contact_id = contact_id
    
    # Update form stats
    form.submissions += 1
    
    db.session.add(submission)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': form.success_message,
        'requires_confirmation': form.double_optin
    })


@form_bp.route('/confirm/<token>')
def confirm_submission(token):
    """Confirm double opt-in submission"""
    from app.models.forms import FormSubmission, Form
    from app import db
    
    submission = FormSubmission.query.filter_by(confirmation_token=token, confirmed=False).first()
    if not submission:
        return render_template('forms/confirmation_error.html'), 404
    
    submission.confirmed = True
    submission.confirmed_at = datetime.utcnow()
    
    # Create contact
    form = Form.query.get(submission.form_id)
    if form:
        contact_id = create_contact_from_submission(form, submission.submission_data)
        submission.contact_id = contact_id
    
    db.session.commit()
    
    return render_template('forms/confirmation_success.html', form=form)


def create_contact_from_submission(form, data):
    """Helper to create contact from form submission"""
    # This would integrate with your existing Contact model
    # For now, return None - implement based on your Contact model
    try:
        from app.models import Contact
        from app import db
        
        email = data.get('email')
        if not email:
            return None
        
        # Check if contact exists
        contact = Contact.query.filter_by(
            email=email,
            organization_id=form.organization_id
        ).first()
        
        if not contact:
            contact = Contact(
                id=str(uuid.uuid4()),
                organization_id=form.organization_id,
                email=email,
                first_name=data.get('first_name', data.get('name', '')),
                last_name=data.get('last_name', ''),
                phone=data.get('phone'),
                source=f'form:{form.id}',
                status='active'
            )
            db.session.add(contact)
        
        # Add tags if configured
        if form.add_tags:
            tags = form.add_tags.split(',')
            # Implement tag adding based on your tag system
        
        db.session.commit()
        return contact.id
    except:
        return None
