"""
SendBaba Workflows Controller
Handles email automation workflows
"""
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
import json
import uuid

workflow_bp = Blueprint('workflows', __name__, url_prefix='/dashboard/workflows')


def get_organization_id():
    if current_user.is_authenticated:
        return getattr(current_user, 'organization_id', session.get('organization_id'))
    return session.get('organization_id')


# ==================== PAGE ROUTES ====================

@workflow_bp.route('/')
@login_required
def index():
    """Workflows list page"""
    return render_template('dashboard/workflows/index.html')


@workflow_bp.route('/create')
@login_required
def create():
    """Create new workflow page"""
    template_id = request.args.get('template')
    return render_template('dashboard/workflows/builder.html', workflow=None, template_id=template_id)


@workflow_bp.route('/<workflow_id>/edit')
@login_required
def edit(workflow_id):
    """Edit workflow page"""
    from app.models.workflows import Workflow
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return render_template('errors/404.html'), 404
    
    return render_template('dashboard/workflows/builder.html', workflow=workflow)


@workflow_bp.route('/<workflow_id>/analytics')
@login_required
def analytics(workflow_id):
    """Workflow analytics page"""
    return render_template('dashboard/workflows/analytics.html', workflow_id=workflow_id)


@workflow_bp.route('/templates')
@login_required
def templates():
    """Browse workflow templates"""
    return render_template('dashboard/workflows/templates.html')


# ==================== API ROUTES ====================

@workflow_bp.route('/api/list')
@login_required
def api_list():
    """Get all workflows"""
    from app.models.workflows import Workflow
    
    org_id = get_organization_id()
    status = request.args.get('status')
    
    query = Workflow.query.filter_by(organization_id=org_id)
    
    if status:
        query = query.filter_by(status=status)
    
    workflows = query.order_by(Workflow.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'workflows': [w.to_dict() for w in workflows]
    })


@workflow_bp.route('/api/create', methods=['POST'])
@login_required
def api_create():
    """Create new workflow"""
    from app.models.workflows import Workflow
    from app import db
    
    data = request.get_json()
    
    # Default steps structure
    default_steps = [
        {
            'id': str(uuid.uuid4()),
            'type': 'trigger',
            'name': 'Trigger',
            'config': {}
        }
    ]
    
    workflow = Workflow(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        name=data.get('name', 'Untitled Workflow'),
        description=data.get('description'),
        trigger_type=data.get('trigger_type', 'contact_added'),
        trigger_config=json.dumps(data.get('trigger_config', {})),
        steps=json.dumps(data.get('steps', default_steps)),
        allow_reentry=data.get('allow_reentry', False),
        status='draft'
    )
    
    db.session.add(workflow)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'workflow': workflow.to_dict(),
        'message': 'Workflow created successfully'
    })


@workflow_bp.route('/api/<workflow_id>', methods=['GET'])
@login_required
def api_get(workflow_id):
    """Get workflow details"""
    from app.models.workflows import Workflow
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    return jsonify({
        'success': True,
        'workflow': workflow.to_dict()
    })


@workflow_bp.route('/api/<workflow_id>', methods=['PUT'])
@login_required
def api_update(workflow_id):
    """Update workflow"""
    from app.models.workflows import Workflow
    from app import db
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        workflow.name = data['name']
    if 'description' in data:
        workflow.description = data['description']
    if 'trigger_type' in data:
        workflow.trigger_type = data['trigger_type']
    if 'trigger_config' in data:
        workflow.trigger_config = json.dumps(data['trigger_config'])
    if 'steps' in data:
        workflow.steps = json.dumps(data['steps'])
    if 'allow_reentry' in data:
        workflow.allow_reentry = data['allow_reentry']
    if 'goal_type' in data:
        workflow.goal_type = data['goal_type']
    if 'goal_config' in data:
        workflow.goal_config = json.dumps(data['goal_config'])
    
    workflow.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'workflow': workflow.to_dict(),
        'message': 'Workflow updated successfully'
    })


@workflow_bp.route('/api/<workflow_id>', methods=['DELETE'])
@login_required
def api_delete(workflow_id):
    """Delete workflow"""
    from app.models.workflows import Workflow
    from app import db
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    db.session.delete(workflow)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Workflow deleted successfully'
    })


@workflow_bp.route('/api/<workflow_id>/activate', methods=['POST'])
@login_required
def api_activate(workflow_id):
    """Activate workflow"""
    from app.models.workflows import Workflow
    from app import db
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    # Validate workflow has required steps
    steps = workflow.steps_list
    if len(steps) < 2:
        return jsonify({'error': 'Workflow must have at least one action step'}), 400
    
    workflow.status = 'active'
    workflow.activated_at = datetime.utcnow()
    db.session.commit()
    
    # Start workflow engine for this workflow
    start_workflow_engine(workflow)
    
    return jsonify({
        'success': True,
        'message': 'Workflow activated successfully'
    })


@workflow_bp.route('/api/<workflow_id>/pause', methods=['POST'])
@login_required
def api_pause(workflow_id):
    """Pause workflow"""
    from app.models.workflows import Workflow
    from app import db
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    workflow.status = 'paused'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Workflow paused successfully'
    })


@workflow_bp.route('/api/<workflow_id>/duplicate', methods=['POST'])
@login_required
def api_duplicate(workflow_id):
    """Duplicate workflow"""
    from app.models.workflows import Workflow
    from app import db
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    new_workflow = Workflow(
        id=str(uuid.uuid4()),
        organization_id=workflow.organization_id,
        name=f"{workflow.name} (Copy)",
        description=workflow.description,
        trigger_type=workflow.trigger_type,
        trigger_config=workflow.trigger_config,
        steps=workflow.steps,
        allow_reentry=workflow.allow_reentry,
        goal_type=workflow.goal_type,
        goal_config=workflow.goal_config,
        status='draft'
    )
    
    db.session.add(new_workflow)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'workflow': new_workflow.to_dict(),
        'message': 'Workflow duplicated successfully'
    })


@workflow_bp.route('/api/<workflow_id>/enrollments')
@login_required
def api_enrollments(workflow_id):
    """Get workflow enrollments"""
    from app.models.workflows import Workflow, WorkflowEnrollment
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    query = WorkflowEnrollment.query.filter_by(workflow_id=workflow_id)
    if status:
        query = query.filter_by(status=status)
    
    enrollments = query.order_by(WorkflowEnrollment.enrolled_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'enrollments': [e.to_dict() for e in enrollments.items],
        'total': enrollments.total,
        'pages': enrollments.pages
    })


@workflow_bp.route('/api/<workflow_id>/enroll', methods=['POST'])
@login_required
def api_enroll_contact(workflow_id):
    """Manually enroll contact in workflow"""
    from app.models.workflows import Workflow, WorkflowEnrollment
    from app import db
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    if workflow.status != 'active':
        return jsonify({'error': 'Workflow is not active'}), 400
    
    data = request.get_json()
    contact_id = data.get('contact_id')
    
    if not contact_id:
        return jsonify({'error': 'Contact ID required'}), 400
    
    # Check if already enrolled
    existing = WorkflowEnrollment.query.filter_by(
        workflow_id=workflow_id,
        contact_id=contact_id,
        status='active'
    ).first()
    
    if existing and not workflow.allow_reentry:
        return jsonify({'error': 'Contact already enrolled'}), 400
    
    enrollment = WorkflowEnrollment(
        id=str(uuid.uuid4()),
        workflow_id=workflow_id,
        contact_id=contact_id,
        current_step=0,
        status='active',
        entry_count=1 if not existing else existing.entry_count + 1
    )
    
    workflow.total_enrolled += 1
    workflow.active_contacts += 1
    
    db.session.add(enrollment)
    db.session.commit()
    
    # Process first step
    process_enrollment_step(enrollment)
    
    return jsonify({
        'success': True,
        'enrollment': enrollment.to_dict(),
        'message': 'Contact enrolled successfully'
    })


@workflow_bp.route('/api/<workflow_id>/stats')
@login_required
def api_stats(workflow_id):
    """Get workflow statistics"""
    from app.models.workflows import Workflow, WorkflowEnrollment, WorkflowLog
    from app import db
    from sqlalchemy import func
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    # Get step completion stats
    steps = workflow.steps_list
    step_stats = []
    
    for i, step in enumerate(steps):
        completed = WorkflowLog.query.filter_by(
            workflow_id=workflow_id,
            step_index=i,
            success=True
        ).count()
        step_stats.append({
            'step_index': i,
            'step_name': step.get('name', f'Step {i+1}'),
            'completed': completed
        })
    
    # Daily enrollments last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_enrollments = db.session.query(
        func.date(WorkflowEnrollment.enrolled_at).label('date'),
        func.count(WorkflowEnrollment.id).label('count')
    ).filter(
        WorkflowEnrollment.workflow_id == workflow_id,
        WorkflowEnrollment.enrolled_at >= thirty_days_ago
    ).group_by(func.date(WorkflowEnrollment.enrolled_at)).all()
    
    return jsonify({
        'success': True,
        'stats': {
            'total_enrolled': workflow.total_enrolled,
            'active_contacts': workflow.active_contacts,
            'completed': workflow.completed,
            'goal_reached': workflow.goal_reached,
            'conversion_rate': workflow.conversion_rate,
            'step_stats': step_stats,
            'daily_enrollments': [{'date': str(d.date), 'count': d.count} for d in daily_enrollments]
        }
    })


@workflow_bp.route('/api/<workflow_id>/logs')
@login_required
def api_logs(workflow_id):
    """Get workflow execution logs"""
    from app.models.workflows import Workflow, WorkflowLog
    
    workflow = Workflow.query.filter_by(id=workflow_id, organization_id=get_organization_id()).first()
    if not workflow:
        return jsonify({'error': 'Workflow not found'}), 404
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    logs = WorkflowLog.query.filter_by(workflow_id=workflow_id)\
        .order_by(WorkflowLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'logs': [l.to_dict() for l in logs.items],
        'total': logs.total,
        'pages': logs.pages
    })


# ==================== TEMPLATES API ====================

@workflow_bp.route('/api/templates')
@login_required
def api_templates():
    """Get workflow templates"""
    from app.models.workflows import WorkflowTemplate
    
    category = request.args.get('category')
    
    query = WorkflowTemplate.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    
    templates = query.order_by(WorkflowTemplate.sort_order).all()
    
    return jsonify({
        'success': True,
        'templates': [t.to_dict() for t in templates]
    })


@workflow_bp.route('/api/templates/<template_id>/use', methods=['POST'])
@login_required
def api_use_template(template_id):
    """Create workflow from template"""
    from app.models.workflows import WorkflowTemplate, Workflow
    from app import db
    
    template = WorkflowTemplate.query.get(template_id)
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    data = request.get_json()
    
    workflow = Workflow(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        name=data.get('name', template.name),
        description=template.description,
        trigger_type=template.trigger_type,
        trigger_config=template.trigger_config,
        steps=template.steps,
        status='draft'
    )
    
    db.session.add(workflow)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'workflow': workflow.to_dict(),
        'message': 'Workflow created from template'
    })


# ==================== WORKFLOW ENGINE ====================

def start_workflow_engine(workflow):
    """Start processing for a workflow"""
    # This would typically start a background task/worker
    # For now, we'll just log the activation
    from app.models.workflows import WorkflowLog
    from app import db
    
    log = WorkflowLog(
        id=str(uuid.uuid4()),
        workflow_id=workflow.id,
        action_type='workflow_activated',
        success=True,
        message=f'Workflow "{workflow.name}" activated'
    )
    db.session.add(log)
    db.session.commit()


def process_enrollment_step(enrollment):
    """Process the current step for an enrollment"""
    from app.models.workflows import Workflow, WorkflowLog
    from app import db
    
    workflow = Workflow.query.get(enrollment.workflow_id)
    if not workflow:
        return
    
    steps = workflow.steps_list
    if enrollment.current_step >= len(steps):
        # Workflow complete
        enrollment.status = 'completed'
        enrollment.completed_at = datetime.utcnow()
        workflow.active_contacts -= 1
        workflow.completed += 1
        db.session.commit()
        return
    
    step = steps[enrollment.current_step]
    step_type = step.get('type')
    step_config = step.get('config', {})
    
    success = True
    message = ''
    
    if step_type == 'trigger':
        # Trigger step - just move to next
        message = 'Trigger processed'
        
    elif step_type == 'send_email':
        # Send email action
        template_id = step_config.get('template_id')
        subject = step_config.get('subject')
        success = send_workflow_email(enrollment.contact_id, template_id, subject)
        message = 'Email sent' if success else 'Email send failed'
        
    elif step_type == 'wait':
        # Wait action - schedule next step
        wait_type = step_config.get('wait_type', 'delay')
        if wait_type == 'delay':
            delay_value = int(step_config.get('delay_value', 1))
            delay_unit = step_config.get('delay_unit', 'days')
            
            if delay_unit == 'minutes':
                delta = timedelta(minutes=delay_value)
            elif delay_unit == 'hours':
                delta = timedelta(hours=delay_value)
            else:
                delta = timedelta(days=delay_value)
            
            enrollment.next_action_at = datetime.utcnow() + delta
            message = f'Waiting {delay_value} {delay_unit}'
            db.session.commit()
            return  # Don't advance step yet
        
    elif step_type == 'condition':
        # Condition check
        condition_type = step_config.get('condition_type')
        # Implement condition logic
        message = 'Condition evaluated'
        
    elif step_type == 'add_tag':
        # Add tag to contact
        tag = step_config.get('tag')
        success = add_tag_to_contact(enrollment.contact_id, tag)
        message = f'Tag "{tag}" added' if success else 'Failed to add tag'
        
    elif step_type == 'remove_tag':
        # Remove tag from contact
        tag = step_config.get('tag')
        success = remove_tag_from_contact(enrollment.contact_id, tag)
        message = f'Tag "{tag}" removed' if success else 'Failed to remove tag'
        
    elif step_type == 'webhook':
        # Send webhook
        url = step_config.get('url')
        success = send_workflow_webhook(enrollment, url)
        message = 'Webhook sent' if success else 'Webhook failed'
    
    # Log the action
    log = WorkflowLog(
        id=str(uuid.uuid4()),
        workflow_id=workflow.id,
        enrollment_id=enrollment.id,
        contact_id=enrollment.contact_id,
        action_type=step_type,
        step_index=enrollment.current_step,
        success=success,
        message=message
    )
    db.session.add(log)
    
    # Move to next step
    enrollment.current_step += 1
    db.session.commit()
    
    # Process next step if immediate
    next_step_index = enrollment.current_step
    if next_step_index < len(steps):
        next_step = steps[next_step_index]
        if next_step.get('type') != 'wait':
            process_enrollment_step(enrollment)


def send_workflow_email(contact_id, template_id, subject):
    """Send email to contact"""
    # Implement email sending logic
    # This would integrate with your SMTP server
    return True


def add_tag_to_contact(contact_id, tag):
    """Add tag to contact"""
    # Implement based on your contact model
    return True


def remove_tag_from_contact(contact_id, tag):
    """Remove tag from contact"""
    # Implement based on your contact model
    return True


def send_workflow_webhook(enrollment, url):
    """Send webhook for workflow event"""
    import requests
    try:
        requests.post(url, json={
            'event': 'workflow_step',
            'enrollment_id': enrollment.id,
            'contact_id': enrollment.contact_id,
            'workflow_id': enrollment.workflow_id,
            'step': enrollment.current_step
        }, timeout=10)
        return True
    except:
        return False


# ==================== TRIGGER HANDLERS ====================

def trigger_contact_added(contact_id, organization_id):
    """Handle contact added trigger"""
    from app.models.workflows import Workflow, WorkflowEnrollment
    from app import db
    
    workflows = Workflow.query.filter_by(
        organization_id=organization_id,
        trigger_type='contact_added',
        status='active'
    ).all()
    
    for workflow in workflows:
        # Check trigger conditions
        config = workflow.trigger_configuration
        
        # Enroll contact
        enrollment = WorkflowEnrollment(
            id=str(uuid.uuid4()),
            workflow_id=workflow.id,
            contact_id=contact_id,
            status='active'
        )
        
        workflow.total_enrolled += 1
        workflow.active_contacts += 1
        
        db.session.add(enrollment)
        db.session.commit()
        
        # Process first step
        process_enrollment_step(enrollment)


def trigger_tag_added(contact_id, tag, organization_id):
    """Handle tag added trigger"""
    from app.models.workflows import Workflow, WorkflowEnrollment
    from app import db
    
    workflows = Workflow.query.filter_by(
        organization_id=organization_id,
        trigger_type='tag_added',
        status='active'
    ).all()
    
    for workflow in workflows:
        config = workflow.trigger_configuration
        trigger_tag = config.get('tag')
        
        if trigger_tag and trigger_tag != tag:
            continue
        
        # Enroll contact
        enrollment = WorkflowEnrollment(
            id=str(uuid.uuid4()),
            workflow_id=workflow.id,
            contact_id=contact_id,
            status='active'
        )
        
        workflow.total_enrolled += 1
        workflow.active_contacts += 1
        
        db.session.add(enrollment)
        db.session.commit()
        
        process_enrollment_step(enrollment)
