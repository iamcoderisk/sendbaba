"""
Permission Helper Utilities
Centralized permission checking for role-based access control
"""
from flask_login import current_user
from functools import wraps
from flask import abort

def can_see_all_org_data():
    """Check if current user can see all organization data"""
    return hasattr(current_user, 'role') and current_user.role in ['admin', 'owner']


def get_user_filter_query(model, query=None):
    """
    Apply user-based filtering to a query based on role
    
    Args:
        model: SQLAlchemy model class
        query: Existing query (optional)
    
    Returns:
        Filtered query based on user role
    """
    from flask_login import current_user
    
    if query is None:
        query = model.query
    
    # Filter by organization
    query = query.filter_by(organization_id=current_user.organization_id)
    
    # If not admin/owner, filter to only user's own data
    if not can_see_all_org_data():
        if hasattr(model, 'created_by_user_id'):
            query = query.filter_by(created_by_user_id=current_user.id)
    
    return query


def require_admin(f):
    """Decorator to require admin/owner role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not can_see_all_org_data():
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function


def require_owner(f):
    """Decorator to require owner role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(current_user, 'role') or current_user.role != 'owner':
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function


def can_edit_resource(resource):
    """
    Check if current user can edit a resource
    
    Args:
        resource: Object with created_by_user_id attribute
    
    Returns:
        Boolean indicating edit permission
    """
    # Admins/owners can edit anything in their org
    if can_see_all_org_data():
        return resource.organization_id == current_user.organization_id
    
    # Regular users can only edit their own resources
    return (resource.organization_id == current_user.organization_id and 
            hasattr(resource, 'created_by_user_id') and
            resource.created_by_user_id == current_user.id)


def can_delete_resource(resource):
    """
    Check if current user can delete a resource
    Same logic as edit for now
    """
    return can_edit_resource(resource)
