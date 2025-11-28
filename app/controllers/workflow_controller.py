"""
SendBaba Workflows Controller
Handles email automation workflows
"""
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
from datetime import datetime, timedelta
import json
import uuid
import logging

logger = logging.getLogger(__name__)

workflow_bp = Blueprint('workflow', __name__, url_prefix='/dashboard/workflows')


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
    template_type = request.args.get('template')
    return render_template('dashboard/workflows/builder.html', workflow=None, template_type=template_type)


@workflow_bp.route('/<workflow_id>/edit')
@login_required
def edit(workflow_id):
    """Edit workflow page"""
    org_id = get_organization_id()
    
    result = db.session.execute(text("""
        SELECT id, name, description, trigger_type, trigger_config, steps, status, 
               allow_reentry, total_enrolled, active_contacts, completed, goal_reached
        FROM workflows 
        WHERE id = :id AND organization_id = :org_id
    """), {'id': workflow_id, 'org_id': org_id})
    
    row = result.fetchone()
    if not row:
        return render_template('errors/404.html'), 404
    
    workflow = {
        'id': row[0],
        'name': row[1],
        'description': row[2],
        'trigger_type': row[3],
        'trigger_config': json.loads(row[4]) if row[4] else {},
        'steps': json.loads(row[5]) if row[5] else [],
        'status': row[6],
        'allow_reentry': row[7],
        'total_enrolled': row[8],
        'active_contacts': row[9],
        'completed': row[10],
        'goal_reached': row[11]
    }
    
    return render_template('dashboard/workflows/builder.html', workflow=workflow)


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
    org_id = get_organization_id()
    status = request.args.get('status')
    
    query = """
        SELECT id, name, description, trigger_type, status, 
               total_enrolled, active_contacts, completed, goal_reached, created_at
        FROM workflows 
        WHERE organization_id = :org_id
    """
    params = {'org_id': org_id}
    
    if status:
        query += " AND status = :status"
        params['status'] = status
    
    query += " ORDER BY created_at DESC"
    
    result = db.session.execute(text(query), params)
    
    workflows = []
    for row in result:
        total = row[5] or 0
        goal = row[8] or 0
        conversion = round((goal / total * 100), 1) if total > 0 else 0
        
        workflows.append({
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'trigger_type': row[3],
            'status': row[4],
            'total_enrolled': total,
            'active_contacts': row[6] or 0,
            'completed': row[7] or 0,
            'goal_reached': goal,
            'conversion_rate': conversion,
            'created_at': row[9].isoformat() if row[9] else None
        })
    
    return jsonify({'success': True, 'workflows': workflows})


@workflow_bp.route('/api/create', methods=['POST'])
@login_required
def api_create():
    """Create new workflow"""
    data = request.get_json()
    org_id = get_organization_id()
    workflow_id = str(uuid.uuid4())
    
    steps = data.get('steps', [])
    if isinstance(steps, list):
        steps = json.dumps(steps)
    
    trigger_config = data.get('trigger_config', {})
    if isinstance(trigger_config, dict):
        trigger_config = json.dumps(trigger_config)
    
    db.session.execute(text("""
        INSERT INTO workflows (id, organization_id, name, description, trigger_type, trigger_config, steps, status)
        VALUES (:id, :org_id, :name, :description, :trigger_type, :trigger_config, :steps, :status)
    """), {
        'id': workflow_id,
        'org_id': org_id,
        'name': data.get('name', 'Untitled Workflow'),
        'description': data.get('description'),
        'trigger_type': data.get('trigger_type', 'contact_added'),
        'trigger_config': trigger_config,
        'steps': steps,
        'status': data.get('status', 'draft')
    })
    db.session.commit()
    
    return jsonify({
        'success': True,
        'workflow': {'id': workflow_id, 'name': data.get('name')},
        'message': 'Workflow created successfully'
    })


@workflow_bp.route('/api/<workflow_id>', methods=['PUT'])
@login_required
def api_update(workflow_id):
    """Update workflow"""
    org_id = get_organization_id()
    data = request.get_json()
    
    # Check exists
    result = db.session.execute(text(
        "SELECT id FROM workflows WHERE id = :id AND organization_id = :org_id"
    ), {'id': workflow_id, 'org_id': org_id})
    
    if not result.fetchone():
        return jsonify({'error': 'Workflow not found'}), 404
    
    steps = data.get('steps', [])
    if isinstance(steps, list):
        steps = json.dumps(steps)
    
    trigger_config = data.get('trigger_config', {})
    if isinstance(trigger_config, dict):
        trigger_config = json.dumps(trigger_config)
    
    db.session.execute(text("""
        UPDATE workflows SET
            name = :name,
            description = :description,
            trigger_type = :trigger_type,
            trigger_config = :trigger_config,
            steps = :steps,
            status = :status,
            updated_at = :updated_at
        WHERE id = :id AND organization_id = :org_id
    """), {
        'id': workflow_id,
        'org_id': org_id,
        'name': data.get('name', 'Untitled Workflow'),
        'description': data.get('description'),
        'trigger_type': data.get('trigger_type', 'contact_added'),
        'trigger_config': trigger_config,
        'steps': steps,
        'status': data.get('status', 'draft'),
        'updated_at': datetime.utcnow()
    })
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Workflow updated'})


@workflow_bp.route('/api/<workflow_id>', methods=['DELETE'])
@login_required
def api_delete(workflow_id):
    """Delete workflow"""
    org_id = get_organization_id()
    
    db.session.execute(text(
        "DELETE FROM workflows WHERE id = :id AND organization_id = :org_id"
    ), {'id': workflow_id, 'org_id': org_id})
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Workflow deleted'})


@workflow_bp.route('/api/<workflow_id>/activate', methods=['POST'])
@login_required
def api_activate(workflow_id):
    """Activate workflow"""
    org_id = get_organization_id()
    
    db.session.execute(text("""
        UPDATE workflows SET status = 'active', activated_at = :now, updated_at = :now
        WHERE id = :id AND organization_id = :org_id
    """), {'id': workflow_id, 'org_id': org_id, 'now': datetime.utcnow()})
    db.session.commit()
    
    # Log activation
    db.session.execute(text("""
        INSERT INTO workflow_logs (id, workflow_id, action_type, success, message, created_at)
        VALUES (:id, :workflow_id, 'activated', true, 'Workflow activated', :now)
    """), {'id': str(uuid.uuid4()), 'workflow_id': workflow_id, 'now': datetime.utcnow()})
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Workflow activated'})


@workflow_bp.route('/api/<workflow_id>/pause', methods=['POST'])
@login_required
def api_pause(workflow_id):
    """Pause workflow"""
    org_id = get_organization_id()
    
    db.session.execute(text("""
        UPDATE workflows SET status = 'paused', updated_at = :now
        WHERE id = :id AND organization_id = :org_id
    """), {'id': workflow_id, 'org_id': org_id, 'now': datetime.utcnow()})
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Workflow paused'})


@workflow_bp.route('/api/<workflow_id>/duplicate', methods=['POST'])
@login_required
def api_duplicate(workflow_id):
    """Duplicate workflow"""
    org_id = get_organization_id()
    
    result = db.session.execute(text("""
        SELECT name, description, trigger_type, trigger_config, steps, allow_reentry
        FROM workflows WHERE id = :id AND organization_id = :org_id
    """), {'id': workflow_id, 'org_id': org_id})
    
    row = result.fetchone()
    if not row:
        return jsonify({'error': 'Workflow not found'}), 404
    
    new_id = str(uuid.uuid4())
    db.session.execute(text("""
        INSERT INTO workflows (id, organization_id, name, description, trigger_type, trigger_config, steps, status, allow_reentry)
        VALUES (:id, :org_id, :name, :description, :trigger_type, :trigger_config, :steps, 'draft', :allow_reentry)
    """), {
        'id': new_id,
        'org_id': org_id,
        'name': f"{row[0]} (Copy)",
        'description': row[1],
        'trigger_type': row[2],
        'trigger_config': row[3],
        'steps': row[4],
        'allow_reentry': row[5]
    })
    db.session.commit()
    
    return jsonify({'success': True, 'workflow': {'id': new_id}, 'message': 'Workflow duplicated'})


@workflow_bp.route('/api/<workflow_id>/stats')
@login_required
def api_stats(workflow_id):
    """Get workflow statistics"""
    org_id = get_organization_id()
    
    result = db.session.execute(text("""
        SELECT total_enrolled, active_contacts, completed, goal_reached, steps
        FROM workflows WHERE id = :id AND organization_id = :org_id
    """), {'id': workflow_id, 'org_id': org_id})
    
    row = result.fetchone()
    if not row:
        return jsonify({'error': 'Workflow not found'}), 404
    
    steps = json.loads(row[4]) if row[4] else []
    
    # Get step completion stats
    step_stats = []
    for i, step in enumerate(steps):
        count_result = db.session.execute(text("""
            SELECT COUNT(*) FROM workflow_logs 
            WHERE workflow_id = :wf_id AND step_index = :step AND success = true
        """), {'wf_id': workflow_id, 'step': i})
        count = count_result.scalar() or 0
        step_stats.append({
            'step_index': i,
            'step_name': step.get('name', f'Step {i+1}'),
            'completed': count
        })
    
    total = row[0] or 0
    goal = row[3] or 0
    
    return jsonify({
        'success': True,
        'stats': {
            'total_enrolled': total,
            'active_contacts': row[1] or 0,
            'completed': row[2] or 0,
            'goal_reached': goal,
            'conversion_rate': round((goal / total * 100), 1) if total > 0 else 0,
            'step_stats': step_stats
        }
    })
