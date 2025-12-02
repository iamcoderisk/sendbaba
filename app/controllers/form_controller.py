"""SendBaba Forms Controller"""
from flask import Blueprint, render_template, request, jsonify, make_response
from flask_login import login_required, current_user
from datetime import datetime
import json, uuid, secrets, logging

logger = logging.getLogger(__name__)
form_bp = Blueprint('forms', __name__, url_prefix='/dashboard/forms')


def get_db():
    from app import db
    return db


def get_models():
    from app.models.forms import Form, FormSubmission
    return Form, FormSubmission


@form_bp.route('/')
@login_required
def index():
    return render_template('dashboard/forms/index.html')


@form_bp.route('/create')
@login_required
def create():
    return render_template('dashboard/forms/builder.html', form=None, form_type=request.args.get('type', 'inline'))


@form_bp.route('/<form_id>/edit')
@login_required
def edit(form_id):
    Form, _ = get_models()
    form = Form.query.filter_by(id=form_id).first()
    return render_template('dashboard/forms/builder.html', form=form, form_type=form.form_type if form else 'inline')


@form_bp.route('/<form_id>/submissions')
@login_required
def submissions_page(form_id):
    Form, _ = get_models()
    form = Form.query.filter_by(id=form_id).first()
    if not form:
        form = type('obj', (object,), {'id': form_id, 'name': 'Form', 'views': 0, 'submissions': 0, 'conversion_rate': 0, 'status': 'unknown'})()
    return render_template('dashboard/forms/submissions.html', form=form)


@form_bp.route('/api/list')
@login_required
def api_list():
    try:
        Form, _ = get_models()
        org_id = str(current_user.organization_id)
        forms = Form.query.filter_by(organization_id=org_id).order_by(Form.created_at.desc()).all()
        return jsonify({'success': True, 'forms': [f.to_dict() for f in forms]})
    except Exception as e:
        logger.error(f"List error: {e}")
        return jsonify({'success': True, 'forms': []})


@form_bp.route('/api/create', methods=['POST'])
@login_required
def api_create():
    try:
        Form, _ = get_models()
        db = get_db()
        data = request.get_json() or {}
        
        form = Form(
            id=str(uuid.uuid4()),
            organization_id=str(current_user.organization_id),
            name=data.get('name') or 'Untitled Form',
            form_type=data.get('form_type') or 'inline',
            fields=json.dumps(data.get('fields') or [{'id': 'email_1', 'type': 'email', 'label': 'Email', 'required': True}]),
            design_settings=json.dumps(data.get('design') or {}),
            trigger_type=data.get('trigger_type') or 'immediate',
            trigger_value=data.get('trigger_value') or None,
            success_action=data.get('success_action') or 'message',
            success_message=data.get('success_message') or 'Thanks!',
            success_redirect_url=data.get('success_redirect_url') or None,
            double_optin=bool(data.get('double_optin')),
            status=data.get('status') or 'draft'
        )
        db.session.add(form)
        db.session.commit()
        return jsonify({'success': True, 'form': form.to_dict()})
    except Exception as e:
        logger.error(f"Create error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@form_bp.route('/api/<form_id>', methods=['GET'])
@login_required
def api_get(form_id):
    Form, _ = get_models()
    form = Form.query.filter_by(id=form_id).first()
    if not form:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'form': form.to_dict()})


@form_bp.route('/api/<form_id>', methods=['PUT'])
@login_required
def api_update(form_id):
    try:
        Form, _ = get_models()
        db = get_db()
        form = Form.query.filter_by(id=form_id).first()
        if not form:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        
        data = request.get_json() or {}
        if 'name' in data: form.name = data['name']
        if 'fields' in data: form.fields = json.dumps(data['fields'])
        if 'design' in data: form.design_settings = json.dumps(data['design'])
        if 'form_type' in data: form.form_type = data['form_type']
        if 'trigger_type' in data: form.trigger_type = data['trigger_type']
        if 'trigger_value' in data: form.trigger_value = data['trigger_value'] or None
        if 'success_action' in data: form.success_action = data['success_action']
        if 'success_message' in data: form.success_message = data['success_message']
        if 'success_redirect_url' in data: form.success_redirect_url = data['success_redirect_url'] or None
        if 'double_optin' in data: form.double_optin = bool(data['double_optin'])
        if 'status' in data: form.status = data['status']
        form.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'form': form.to_dict()})
    except Exception as e:
        logger.error(f"Update error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@form_bp.route('/api/<form_id>', methods=['DELETE'])
@login_required
def api_delete(form_id):
    try:
        Form, _ = get_models()
        db = get_db()
        form = Form.query.filter_by(id=form_id).first()
        if form:
            db.session.delete(form)
            db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@form_bp.route('/api/<form_id>/duplicate', methods=['POST'])
@login_required
def api_duplicate(form_id):
    try:
        Form, _ = get_models()
        db = get_db()
        form = Form.query.filter_by(id=form_id).first()
        if not form:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        
        new = Form(id=str(uuid.uuid4()), organization_id=form.organization_id, name=f"{form.name} (Copy)",
                   form_type=form.form_type, fields=form.fields, design_settings=form.design_settings,
                   trigger_type=form.trigger_type, success_action=form.success_action, success_message=form.success_message, status='draft')
        db.session.add(new)
        db.session.commit()
        return jsonify({'success': True, 'form': new.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@form_bp.route('/api/<form_id>/submissions')
@login_required
def api_submissions(form_id):
    try:
        _, FormSubmission = get_models()
        subs = FormSubmission.query.filter_by(form_id=form_id).order_by(FormSubmission.created_at.desc()).limit(100).all()
        return jsonify({'success': True, 'submissions': [s.to_dict() for s in subs], 'total': len(subs), 'pages': 1, 'current_page': 1})
    except:
        return jsonify({'success': True, 'submissions': [], 'total': 0, 'pages': 1, 'current_page': 1})


@form_bp.route('/api/<form_id>/embed-code')
@login_required
def api_embed_code(form_id):
    Form, _ = get_models()
    form = Form.query.filter_by(id=form_id).first()
    if not form:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'embed_code': form.get_embed_code(request.host_url.rstrip('/'))})


@form_bp.route('/api/<form_id>/toggle-status', methods=['POST'])
@login_required
def api_toggle(form_id):
    try:
        Form, _ = get_models()
        db = get_db()
        form = Form.query.filter_by(id=form_id).first()
        if form:
            form.status = 'paused' if form.status == 'active' else 'active'
            db.session.commit()
            return jsonify({'success': True, 'status': form.status})
        return jsonify({'success': False}), 404
    except:
        return jsonify({'success': False}), 500


@form_bp.route('/embed/<form_id>.js')
def embed_script(form_id):
    try:
        Form, _ = get_models()
        db = get_db()
        form = Form.query.filter_by(id=form_id).first()
        if not form or form.status != 'active':
            return 'console.error("Form not active");', 404, {'Content-Type': 'application/javascript'}
        form.views = (form.views or 0) + 1
        db.session.commit()
        d = form.design
        js = f'''(function(){{var f=document.createElement("form");f.innerHTML='<input type="email" name="email" placeholder="Email" required style="width:100%;padding:12px;border:1px solid #ddd;border-radius:8px;margin-bottom:12px;"><button type="submit" style="width:100%;padding:12px;background:{d.get("primary_color","#F97316")};color:#fff;border:none;border-radius:8px;cursor:pointer;">{d.get("button_text","Subscribe")}</button>';f.style.cssText="max-width:400px;padding:20px;background:#fff;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.1);font-family:system-ui;";f.onsubmit=function(e){{e.preventDefault();var d={{}};f.querySelectorAll("input").forEach(function(i){{d[i.name]=i.value;}});fetch("{request.host_url.rstrip('/')}/forms/submit/{form.id}",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(d)}}).then(function(){{f.innerHTML="<p style='text-align:center;padding:20px;'>{form.success_message or 'Thanks!'}</p>";}});}};var c=document.getElementById("sb-form-{form.id}");if(c)c.appendChild(f);else document.body.appendChild(f);}})();'''
        return js, 200, {'Content-Type': 'application/javascript'}
    except Exception as e:
        return f'console.error("{e}");', 500, {'Content-Type': 'application/javascript'}


@form_bp.route('/submit/<form_id>', methods=['POST'])
def submit_form(form_id):
    try:
        Form, FormSubmission = get_models()
        db = get_db()
        form = Form.query.filter_by(id=form_id, status='active').first()
        if not form:
            return jsonify({'success': False, 'error': 'Form not found'}), 404
        data = request.get_json() or {}
        sub = FormSubmission(id=str(uuid.uuid4()), form_id=form_id, data=json.dumps(data), ip_address=request.remote_addr)
        form.submissions = (form.submissions or 0) + 1
        db.session.add(sub)
        db.session.commit()
        return jsonify({'success': True, 'message': form.success_message or 'Thanks!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
