"""
SendBaba Segments Controller
Handles contact segmentation with query builder
"""
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
import json
import uuid

segment_bp = Blueprint('segments', __name__, url_prefix='/dashboard/segments')


def get_organization_id():
    if current_user.is_authenticated:
        return getattr(current_user, 'organization_id', session.get('organization_id'))
    return session.get('organization_id')


# ==================== PAGE ROUTES ====================

@segment_bp.route('/')
@login_required
def index():
    """Segments list page"""
    return render_template('dashboard/segments/index.html')


@segment_bp.route('/create')
@login_required
def create():
    """Create new segment page"""
    return render_template('dashboard/segments/builder.html', segment=None)


@segment_bp.route('/<segment_id>/edit')
@login_required
def edit(segment_id):
    """Edit segment page"""
    from app.models.segments import Segment
    
    segment = Segment.query.filter_by(id=segment_id, organization_id=get_organization_id()).first()
    if not segment:
        return render_template('errors/404.html'), 404
    
    return render_template('dashboard/segments/builder.html', segment=segment)


@segment_bp.route('/<segment_id>/contacts')
@login_required
def view_contacts(segment_id):
    """View contacts in segment"""
    return render_template('dashboard/segments/contacts.html', segment_id=segment_id)


# ==================== API ROUTES ====================

@segment_bp.route('/api/list')
@login_required
def api_list():
    """Get all segments"""
    from app.models.segments import Segment
    
    org_id = get_organization_id()
    segments = Segment.query.filter_by(organization_id=org_id, is_active=True)\
        .order_by(Segment.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'segments': [s.to_dict() for s in segments]
    })


@segment_bp.route('/api/create', methods=['POST'])
@login_required
def api_create():
    """Create new segment"""
    from app.models.segments import Segment
    from app import db
    
    data = request.get_json()
    
    segment = Segment(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        name=data.get('name', 'Untitled Segment'),
        description=data.get('description'),
        segment_type=data.get('segment_type', 'dynamic'),
        rules=json.dumps(data.get('rules', {'conditions': []})),
        rules_match=data.get('rules_match', 'all'),
        color=data.get('color', 'purple'),
        icon=data.get('icon', 'fa-users'),
        created_by=session.get('user_id')
    )
    
    db.session.add(segment)
    db.session.commit()
    
    # Calculate initial count
    count = calculate_segment_count(segment)
    segment.cached_count = count
    segment.last_calculated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'segment': segment.to_dict(),
        'message': 'Segment created successfully'
    })


@segment_bp.route('/api/<segment_id>', methods=['GET'])
@login_required
def api_get(segment_id):
    """Get segment details"""
    from app.models.segments import Segment
    
    segment = Segment.query.filter_by(id=segment_id, organization_id=get_organization_id()).first()
    if not segment:
        return jsonify({'error': 'Segment not found'}), 404
    
    return jsonify({
        'success': True,
        'segment': segment.to_dict()
    })


@segment_bp.route('/api/<segment_id>', methods=['PUT'])
@login_required
def api_update(segment_id):
    """Update segment"""
    from app.models.segments import Segment
    from app import db
    
    segment = Segment.query.filter_by(id=segment_id, organization_id=get_organization_id()).first()
    if not segment:
        return jsonify({'error': 'Segment not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        segment.name = data['name']
    if 'description' in data:
        segment.description = data['description']
    if 'rules' in data:
        segment.rules = json.dumps(data['rules'])
    if 'rules_match' in data:
        segment.rules_match = data['rules_match']
    if 'color' in data:
        segment.color = data['color']
    if 'icon' in data:
        segment.icon = data['icon']
    
    segment.updated_at = datetime.utcnow()
    
    # Recalculate count
    count = calculate_segment_count(segment)
    segment.cached_count = count
    segment.last_calculated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'segment': segment.to_dict(),
        'message': 'Segment updated successfully'
    })


@segment_bp.route('/api/<segment_id>', methods=['DELETE'])
@login_required
def api_delete(segment_id):
    """Delete segment"""
    from app.models.segments import Segment
    from app import db
    
    segment = Segment.query.filter_by(id=segment_id, organization_id=get_organization_id()).first()
    if not segment:
        return jsonify({'error': 'Segment not found'}), 404
    
    db.session.delete(segment)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Segment deleted successfully'
    })


@segment_bp.route('/api/<segment_id>/duplicate', methods=['POST'])
@login_required
def api_duplicate(segment_id):
    """Duplicate segment"""
    from app.models.segments import Segment
    from app import db
    
    segment = Segment.query.filter_by(id=segment_id, organization_id=get_organization_id()).first()
    if not segment:
        return jsonify({'error': 'Segment not found'}), 404
    
    new_segment = Segment(
        id=str(uuid.uuid4()),
        organization_id=segment.organization_id,
        name=f"{segment.name} (Copy)",
        description=segment.description,
        segment_type=segment.segment_type,
        rules=segment.rules,
        rules_match=segment.rules_match,
        color=segment.color,
        icon=segment.icon,
        created_by=session.get('user_id')
    )
    
    db.session.add(new_segment)
    db.session.commit()
    
    # Calculate count
    count = calculate_segment_count(new_segment)
    new_segment.cached_count = count
    new_segment.last_calculated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'segment': new_segment.to_dict(),
        'message': 'Segment duplicated successfully'
    })


@segment_bp.route('/api/<segment_id>/contacts')
@login_required
def api_contacts(segment_id):
    """Get contacts in segment"""
    from app.models.segments import Segment
    
    segment = Segment.query.filter_by(id=segment_id, organization_id=get_organization_id()).first()
    if not segment:
        return jsonify({'error': 'Segment not found'}), 404
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    contacts, total = get_segment_contacts(segment, page, per_page)
    
    return jsonify({
        'success': True,
        'contacts': contacts,
        'total': total,
        'pages': (total + per_page - 1) // per_page,
        'current_page': page
    })


@segment_bp.route('/api/<segment_id>/refresh', methods=['POST'])
@login_required
def api_refresh(segment_id):
    """Refresh segment count"""
    from app.models.segments import Segment
    from app import db
    
    segment = Segment.query.filter_by(id=segment_id, organization_id=get_organization_id()).first()
    if not segment:
        return jsonify({'error': 'Segment not found'}), 404
    
    count = calculate_segment_count(segment)
    segment.cached_count = count
    segment.last_calculated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'count': count,
        'message': 'Segment refreshed'
    })


@segment_bp.route('/api/preview', methods=['POST'])
@login_required
def api_preview():
    """Preview segment results without saving"""
    data = request.get_json()
    rules = data.get('rules', {'conditions': []})
    rules_match = data.get('rules_match', 'all')
    
    # Create temporary segment object
    from app.models.segments import Segment
    temp_segment = Segment(
        organization_id=get_organization_id(),
        rules=json.dumps(rules),
        rules_match=rules_match
    )
    
    count = calculate_segment_count(temp_segment)
    contacts, _ = get_segment_contacts(temp_segment, 1, 10)
    
    return jsonify({
        'success': True,
        'count': count,
        'preview_contacts': contacts
    })


@segment_bp.route('/api/fields')
@login_required
def api_fields():
    """Get available fields for segment builder"""
    from app.models.segments import SEGMENT_FIELDS, SEGMENT_OPERATORS
    
    return jsonify({
        'success': True,
        'fields': SEGMENT_FIELDS,
        'operators': SEGMENT_OPERATORS
    })


@segment_bp.route('/api/<segment_id>/export', methods=['POST'])
@login_required
def api_export(segment_id):
    """Export segment contacts"""
    from app.models.segments import Segment
    
    segment = Segment.query.filter_by(id=segment_id, organization_id=get_organization_id()).first()
    if not segment:
        return jsonify({'error': 'Segment not found'}), 404
    
    # Get all contacts
    contacts, total = get_segment_contacts(segment, 1, 100000)
    
    # Generate CSV
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['Email', 'First Name', 'Last Name', 'Phone', 'Status', 'Created'])
    
    # Data
    for contact in contacts:
        writer.writerow([
            contact.get('email', ''),
            contact.get('first_name', ''),
            contact.get('last_name', ''),
            contact.get('phone', ''),
            contact.get('status', ''),
            contact.get('created_at', '')
        ])
    
    csv_data = output.getvalue()
    
    return jsonify({
        'success': True,
        'csv': csv_data,
        'filename': f'segment_{segment.name}_{datetime.utcnow().strftime("%Y%m%d")}.csv'
    })


# ==================== QUERY BUILDER ENGINE ====================

def calculate_segment_count(segment):
    """Calculate the number of contacts matching segment rules"""
    query = build_segment_query(segment)
    if query is None:
        return 0
    return query.count()


def get_segment_contacts(segment, page=1, per_page=50):
    """Get paginated contacts matching segment rules"""
    query = build_segment_query(segment)
    if query is None:
        return [], 0
    
    total = query.count()
    contacts = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return [contact_to_dict(c) for c in contacts], total


def build_segment_query(segment):
    """Build SQLAlchemy query from segment rules"""
    try:
        from app.models import Contact
        from app import db
        from sqlalchemy import and_, or_, func
        
        org_id = segment.organization_id
        rules = segment.rules_list
        rules_match = segment.rules_match
        
        conditions = rules.get('conditions', [])
        
        if not conditions:
            # No conditions = all contacts
            return Contact.query.filter_by(organization_id=org_id, status='active')
        
        query_conditions = []
        
        for condition in conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            
            if not field or not operator:
                continue
            
            sql_condition = build_condition(Contact, field, operator, value)
            if sql_condition is not None:
                query_conditions.append(sql_condition)
        
        if not query_conditions:
            return Contact.query.filter_by(organization_id=org_id, status='active')
        
        base_query = Contact.query.filter_by(organization_id=org_id)
        
        if rules_match == 'all':
            return base_query.filter(and_(*query_conditions))
        else:
            return base_query.filter(or_(*query_conditions))
    
    except Exception as e:
        print(f"Error building segment query: {e}")
        return None


def build_condition(model, field, operator, value):
    """Build individual SQL condition"""
    from sqlalchemy import func
    
    # Get the column
    if not hasattr(model, field):
        return None
    
    column = getattr(model, field)
    
    # String operators
    if operator == 'equals':
        return column == value
    elif operator == 'not_equals':
        return column != value
    elif operator == 'contains':
        return column.ilike(f'%{value}%')
    elif operator == 'not_contains':
        return ~column.ilike(f'%{value}%')
    elif operator == 'starts_with':
        return column.ilike(f'{value}%')
    elif operator == 'ends_with':
        return column.ilike(f'%{value}')
    elif operator == 'is_empty':
        return (column == None) | (column == '')
    elif operator == 'is_not_empty':
        return (column != None) & (column != '')
    
    # Number operators
    elif operator == 'greater_than':
        return column > float(value)
    elif operator == 'less_than':
        return column < float(value)
    elif operator == 'greater_or_equal':
        return column >= float(value)
    elif operator == 'less_or_equal':
        return column <= float(value)
    elif operator == 'between':
        if isinstance(value, list) and len(value) == 2:
            return column.between(float(value[0]), float(value[1]))
    
    # Date operators
    elif operator == 'on':
        return func.date(column) == value
    elif operator == 'before':
        return column < datetime.fromisoformat(value)
    elif operator == 'after':
        return column > datetime.fromisoformat(value)
    elif operator == 'in_last':
        # value should be like "7 days" or "30 days"
        parts = value.split()
        if len(parts) == 2:
            num = int(parts[0])
            unit = parts[1].lower()
            if unit.startswith('day'):
                delta = timedelta(days=num)
            elif unit.startswith('week'):
                delta = timedelta(weeks=num)
            elif unit.startswith('month'):
                delta = timedelta(days=num * 30)
            else:
                delta = timedelta(days=num)
            return column >= datetime.utcnow() - delta
    elif operator == 'not_in_last':
        parts = value.split()
        if len(parts) == 2:
            num = int(parts[0])
            unit = parts[1].lower()
            if unit.startswith('day'):
                delta = timedelta(days=num)
            elif unit.startswith('week'):
                delta = timedelta(weeks=num)
            elif unit.startswith('month'):
                delta = timedelta(days=num * 30)
            else:
                delta = timedelta(days=num)
            return column < datetime.utcnow() - delta
    
    # Tag operators (assuming tags is a comma-separated string)
    elif operator == 'has_tag':
        return column.ilike(f'%{value}%')
    elif operator == 'not_has_tag':
        return ~column.ilike(f'%{value}%')
    
    # Select operators
    elif operator == 'in':
        if isinstance(value, list):
            return column.in_(value)
    elif operator == 'not_in':
        if isinstance(value, list):
            return ~column.in_(value)
    
    return None


def contact_to_dict(contact):
    """Convert contact model to dictionary"""
    return {
        'id': contact.id,
        'email': contact.email,
        'first_name': contact.first_name,
        'last_name': contact.last_name,
        'phone': getattr(contact, 'phone', None),
        'status': contact.status,
        'tags': getattr(contact, 'tags', ''),
        'created_at': contact.created_at.isoformat() if contact.created_at else None
    }


# ==================== PRESET SEGMENTS ====================

def create_preset_segments(organization_id):
    """Create preset segments for new organization"""
    from app.models.segments import Segment
    from app import db
    
    presets = [
        {
            'name': 'Engaged Subscribers',
            'description': 'Contacts who opened or clicked in the last 30 days',
            'rules': {
                'conditions': [
                    {'field': 'last_opened_at', 'operator': 'in_last', 'value': '30 days'}
                ]
            },
            'color': 'green',
            'icon': 'fa-star'
        },
        {
            'name': 'Inactive Subscribers',
            'description': 'Contacts who haven\'t opened in 90 days',
            'rules': {
                'conditions': [
                    {'field': 'last_opened_at', 'operator': 'not_in_last', 'value': '90 days'}
                ]
            },
            'color': 'yellow',
            'icon': 'fa-moon'
        },
        {
            'name': 'New Subscribers',
            'description': 'Contacts added in the last 7 days',
            'rules': {
                'conditions': [
                    {'field': 'created_at', 'operator': 'in_last', 'value': '7 days'}
                ]
            },
            'color': 'blue',
            'icon': 'fa-user-plus'
        },
        {
            'name': 'VIP Customers',
            'description': 'High engagement contacts',
            'rules': {
                'conditions': [
                    {'field': 'open_rate', 'operator': 'greater_than', 'value': '50'}
                ]
            },
            'color': 'purple',
            'icon': 'fa-crown'
        }
    ]
    
    for preset in presets:
        segment = Segment(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            name=preset['name'],
            description=preset['description'],
            rules=json.dumps(preset['rules']),
            rules_match='all',
            color=preset['color'],
            icon=preset['icon']
        )
        db.session.add(segment)
    
    db.session.commit()
