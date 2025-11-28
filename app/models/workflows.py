"""
Workflow Models for SendBaba
"""
from datetime import datetime
import json
import uuid

class Workflow:
    """Workflow model - uses raw SQL"""
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', str(uuid.uuid4()))
        self.organization_id = kwargs.get('organization_id')
        self.name = kwargs.get('name', 'Untitled Workflow')
        self.description = kwargs.get('description')
        self.trigger_type = kwargs.get('trigger_type', 'contact_added')
        self.trigger_config = kwargs.get('trigger_config', '{}')
        self.steps = kwargs.get('steps', '[]')
        self.status = kwargs.get('status', 'draft')
        self.allow_reentry = kwargs.get('allow_reentry', False)
        self.goal_type = kwargs.get('goal_type')
        self.goal_config = kwargs.get('goal_config')
        self.total_enrolled = kwargs.get('total_enrolled', 0)
        self.active_contacts = kwargs.get('active_contacts', 0)
        self.completed = kwargs.get('completed', 0)
        self.goal_reached = kwargs.get('goal_reached', 0)
        self.created_at = kwargs.get('created_at', datetime.utcnow())
        self.updated_at = kwargs.get('updated_at', datetime.utcnow())
        self.activated_at = kwargs.get('activated_at')
    
    @property
    def steps_list(self):
        if isinstance(self.steps, str):
            try:
                return json.loads(self.steps)
            except:
                return []
        return self.steps or []
    
    @property
    def trigger_configuration(self):
        if isinstance(self.trigger_config, str):
            try:
                return json.loads(self.trigger_config)
            except:
                return {}
        return self.trigger_config or {}
    
    @property
    def conversion_rate(self):
        if self.total_enrolled > 0:
            return round((self.goal_reached / self.total_enrolled) * 100, 1)
        return 0
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'trigger_type': self.trigger_type,
            'trigger_config': self.trigger_configuration,
            'steps': self.steps_list,
            'status': self.status,
            'allow_reentry': self.allow_reentry,
            'total_enrolled': self.total_enrolled,
            'active_contacts': self.active_contacts,
            'completed': self.completed,
            'goal_reached': self.goal_reached,
            'conversion_rate': self.conversion_rate,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class WorkflowEnrollment:
    """Tracks contacts enrolled in workflows"""
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', str(uuid.uuid4()))
        self.workflow_id = kwargs.get('workflow_id')
        self.contact_id = kwargs.get('contact_id')
        self.current_step = kwargs.get('current_step', 0)
        self.status = kwargs.get('status', 'active')
        self.entry_count = kwargs.get('entry_count', 1)
        self.enrolled_at = kwargs.get('enrolled_at', datetime.utcnow())
        self.completed_at = kwargs.get('completed_at')
        self.next_action_at = kwargs.get('next_action_at')
    
    def to_dict(self):
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'contact_id': self.contact_id,
            'current_step': self.current_step,
            'status': self.status,
            'entry_count': self.entry_count,
            'enrolled_at': self.enrolled_at.isoformat() if self.enrolled_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class WorkflowLog:
    """Logs workflow execution events"""
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', str(uuid.uuid4()))
        self.workflow_id = kwargs.get('workflow_id')
        self.enrollment_id = kwargs.get('enrollment_id')
        self.contact_id = kwargs.get('contact_id')
        self.action_type = kwargs.get('action_type')
        self.step_index = kwargs.get('step_index')
        self.success = kwargs.get('success', True)
        self.message = kwargs.get('message')
        self.created_at = kwargs.get('created_at', datetime.utcnow())
    
    def to_dict(self):
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'enrollment_id': self.enrollment_id,
            'contact_id': self.contact_id,
            'action_type': self.action_type,
            'step_index': self.step_index,
            'success': self.success,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
