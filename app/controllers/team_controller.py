"""
Team Management Controller - Simplified & Fixed
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import secrets
import logging

logger = logging.getLogger(__name__)
team_bp = Blueprint('team', __name__, url_prefix='/dashboard/team')


def get_org_id():
    """Get organization ID safely"""
    try:
        if current_user and current_user.is_authenticated:
            return str(current_user.organization_id)
    except Exception as e:
        logger.error(f"get_org_id error: {e}")
    return None


@team_bp.route('/')
@login_required
def index():
    """Main team page"""
    org_id = get_org_id()
    departments = []
    members = []
    stats = {'total_departments': 0, 'total_members': 0, 'active_members': 0, 'pending_invitations': 0}
    
    if not org_id:
        logger.error("No org_id found")
        return render_template('dashboard/team/index.html', departments=[], members=[], stats=stats)
    
    try:
        # Simple department query
        try:
            dept_rows = db.session.execute(text("""
                SELECT id, name, description, color, 
                       COALESCE(email_quota, 1000) as email_quota,
                       COALESCE(emails_sent_this_month, 0) as emails_sent
                FROM departments 
                WHERE organization_id = :org_id 
                ORDER BY name
            """), {'org_id': org_id}).fetchall()
        except Exception as e:
            logger.error(f"Dept query v1 failed: {e}")
            # Even simpler fallback
            dept_rows = db.session.execute(text("""
                SELECT id, name, description, color, 1000 as email_quota, 0 as emails_sent
                FROM departments WHERE organization_id = :org_id ORDER BY name
            """), {'org_id': org_id}).fetchall()
        
        for d in dept_rows:
            # Count members for this department
            try:
                mc = db.session.execute(text("SELECT COUNT(*) FROM team_members WHERE department_id = :did"), 
                                       {'did': d[0]}).scalar() or 0
            except:
                mc = 0
            
            # Count contacts for this department
            try:
                cc = db.session.execute(text("SELECT COUNT(*) FROM contacts WHERE department_id = :did"), 
                                       {'did': d[0]}).scalar() or 0
            except:
                cc = 0
            
            departments.append({
                'id': d[0],
                'name': d[1] or 'Unnamed',
                'description': d[2] or '',
                'color': d[3] or '#F97316',
                'email_quota': d[4] or 1000,
                'emails_sent_this_month': d[5] or 0,
                'member_count': mc,
                'contact_count': cc,
                'total_emails': 0
            })
        
        # Simple member query
        try:
            member_rows = db.session.execute(text("""
                SELECT tm.id, tm.email, tm.first_name, tm.last_name, tm.role,
                       tm.department_id, d.name as dname, d.color as dcolor,
                       COALESCE(tm.invitation_accepted, false),
                       COALESCE(tm.is_active, true)
                FROM team_members tm
                LEFT JOIN departments d ON d.id = tm.department_id
                WHERE tm.organization_id = :org_id
                ORDER BY tm.email
            """), {'org_id': org_id}).fetchall()
        except Exception as e:
            logger.error(f"Member query v1 failed: {e}")
            # Simpler fallback
            member_rows = db.session.execute(text("""
                SELECT id, email, first_name, last_name, role, department_id, 
                       NULL as dname, NULL as dcolor, false, true
                FROM team_members WHERE organization_id = :org_id ORDER BY email
            """), {'org_id': org_id}).fetchall()
        
        for m in member_rows:
            email = m[1] or 'unknown@email.com'
            fname = m[2] or ''
            lname = m[3] or ''
            full = f"{fname} {lname}".strip()
            if not full:
                full = email.split('@')[0]
            
            members.append({
                'id': m[0],
                'email': email,
                'first_name': fname,
                'last_name': lname,
                'full_name': full,
                'role': m[4] or 'member',
                'department_id': m[5],
                'department_name': m[6] or 'Unassigned',
                'department_color': m[7] or '#F97316',
                'invitation_accepted': bool(m[8]),
                'is_active': bool(m[9]),
                'emails_sent_this_month': 0
            })
        
        stats = {
            'total_departments': len(departments),
            'total_members': len(members),
            'active_members': sum(1 for m in members if m['is_active']),
            'pending_invitations': sum(1 for m in members if not m['invitation_accepted'])
        }
        
        logger.info(f"Team page loaded: {len(departments)} depts, {len(members)} members")
        
    except Exception as e:
        logger.error(f"Team index error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        db.session.rollback()
    
    return render_template('dashboard/team/index.html', 
                         departments=departments, members=members, stats=stats)


@team_bp.route('/departments/create', methods=['GET', 'POST'])
@login_required
def create_department():
    """Create department"""
    if request.method == 'POST':
        org_id = get_org_id()
        try:
            name = request.form.get('name', '').strip()
            if not name:
                flash('Department name is required', 'error')
                return render_template('dashboard/team/create_department.html')
            
            db.session.execute(text("""
                INSERT INTO departments (organization_id, name, description, color, email_quota, created_at, updated_at)
                VALUES (:oid, :name, :desc, :color, :quota, NOW(), NOW())
            """), {
                'oid': org_id,
                'name': name,
                'desc': request.form.get('description', ''),
                'color': request.form.get('color', '#F97316'),
                'quota': int(request.form.get('email_quota', 1000))
            })
            db.session.commit()
            flash('Department created!', 'success')
            return redirect(url_for('team.index'))
        except Exception as e:
            logger.error(f"Create dept error: {e}")
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('dashboard/team/create_department.html')


@team_bp.route('/departments/<int:dept_id>')
@login_required
def view_department(dept_id):
    """View department"""
    org_id = get_org_id()
    try:
        d = db.session.execute(text("""
            SELECT id, name, description, color, COALESCE(email_quota, 1000)
            FROM departments WHERE id = :id AND organization_id = :oid
        """), {'id': dept_id, 'oid': org_id}).fetchone()
        
        if not d:
            flash('Department not found', 'error')
            return redirect(url_for('team.index'))
        
        department = {
            'id': d[0], 'name': d[1], 'description': d[2] or '',
            'color': d[3] or '#F97316', 'email_quota': d[4],
            'emails_sent_this_month': 0
        }
        
        # Members
        mrows = db.session.execute(text("""
            SELECT id, email, first_name, last_name, role, 
                   COALESCE(invitation_accepted, false), COALESCE(is_active, true)
            FROM team_members WHERE department_id = :did AND organization_id = :oid
        """), {'did': dept_id, 'oid': org_id}).fetchall()
        
        members = []
        for m in mrows:
            fname = m[2] or ''
            lname = m[3] or ''
            full = f"{fname} {lname}".strip() or m[1].split('@')[0]
            members.append({
                'id': m[0], 'email': m[1], 'first_name': fname, 'last_name': lname,
                'full_name': full, 'role': m[4] or 'member',
                'invitation_accepted': bool(m[5]), 'is_active': bool(m[6]),
                'emails_sent_this_month': 0, 'contact_count': 0
            })
        
        # Contacts
        crows = db.session.execute(text("""
            SELECT id, email, first_name, last_name, status, created_at
            FROM contacts WHERE department_id = :did AND organization_id = :oid LIMIT 100
        """), {'did': dept_id, 'oid': org_id}).fetchall()
        
        contacts = []
        for c in crows:
            fname = c[2] or ''
            lname = c[3] or ''
            name = f"{fname} {lname}".strip() or c[1].split('@')[0]
            contacts.append({
                'id': c[0], 'email': c[1], 'name': name,
                'status': c[4] or 'active', 'created_at': c[5], 'owner': ''
            })
        
        return render_template('dashboard/team/view_department.html',
            department=department, members=members, contacts=contacts, campaigns=[],
            email_stats={'sent':0,'delivered':0,'opened':0,'clicked':0,'bounced':0}, is_owner=True)
    
    except Exception as e:
        logger.error(f"View dept error: {e}")
        db.session.rollback()
        flash('Error loading department', 'error')
        return redirect(url_for('team.index'))


@team_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_department(dept_id):
    """Edit department"""
    org_id = get_org_id()
    try:
        d = db.session.execute(text("""
            SELECT id, name, description, color, COALESCE(email_quota, 1000)
            FROM departments WHERE id = :id AND organization_id = :oid
        """), {'id': dept_id, 'oid': org_id}).fetchone()
        
        if not d:
            flash('Not found', 'error')
            return redirect(url_for('team.index'))
        
        department = {'id': d[0], 'name': d[1], 'description': d[2] or '',
                     'color': d[3] or '#F97316', 'email_quota': d[4]}
        
        if request.method == 'POST':
            db.session.execute(text("""
                UPDATE departments SET name=:n, description=:d, color=:c, email_quota=:q, updated_at=NOW()
                WHERE id=:id AND organization_id=:oid
            """), {
                'id': dept_id, 'oid': org_id,
                'n': request.form.get('name', '').strip(),
                'd': request.form.get('description', ''),
                'c': request.form.get('color', '#F97316'),
                'q': int(request.form.get('email_quota', 1000))
            })
            db.session.commit()
            flash('Updated!', 'success')
            return redirect(url_for('team.index'))
        
        return render_template('dashboard/team/edit_department.html', department=department)
    except Exception as e:
        logger.error(f"Edit dept error: {e}")
        db.session.rollback()
        flash('Error', 'error')
        return redirect(url_for('team.index'))


@team_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
def delete_department(dept_id):
    """Delete department"""
    org_id = get_org_id()
    try:
        db.session.execute(text("UPDATE team_members SET department_id=NULL WHERE department_id=:id"), {'id': dept_id})
        db.session.execute(text("UPDATE contacts SET department_id=NULL WHERE department_id=:id"), {'id': dept_id})
        db.session.execute(text("DELETE FROM departments WHERE id=:id AND organization_id=:oid"), {'id': dept_id, 'oid': org_id})
        db.session.commit()
        flash('Deleted!', 'success')
    except Exception as e:
        logger.error(f"Delete dept error: {e}")
        db.session.rollback()
        flash('Error', 'error')
    return redirect(url_for('team.index'))


@team_bp.route('/members/invite', methods=['GET', 'POST'])
@login_required
def invite_member():
    """Invite member"""
    org_id = get_org_id()
    departments = []
    
    try:
        rows = db.session.execute(text(
            "SELECT id, name, color FROM departments WHERE organization_id=:oid ORDER BY name"
        ), {'oid': org_id}).fetchall()
        departments = [{'id': r[0], 'name': r[1], 'color': r[2]} for r in rows]
        
        if request.method == 'POST':
            email = request.form.get('email', '').lower().strip()
            if not email:
                flash('Email required', 'error')
                return render_template('dashboard/team/invite_member.html', departments=departments)
            
            # Check exists
            exists = db.session.execute(text(
                "SELECT id FROM team_members WHERE email=:e AND organization_id=:oid"
            ), {'e': email, 'oid': org_id}).fetchone()
            
            if exists:
                flash('Member already exists', 'error')
                return render_template('dashboard/team/invite_member.html', departments=departments)
            
            token = secrets.token_urlsafe(32)
            dept_id = request.form.get('department_id')
            if dept_id:
                dept_id = int(dept_id)
            else:
                dept_id = None
            
            db.session.execute(text("""
                INSERT INTO team_members 
                (organization_id, department_id, email, first_name, last_name, role,
                 invitation_token, invitation_accepted, is_active, invited_at,
                 can_send_email, can_manage_contacts, can_manage_campaigns, 
                 can_view_analytics, can_manage_team, can_manage_billing,
                 created_at, updated_at)
                VALUES (:oid, :did, :email, :fn, :ln, :role, :token, false, true, NOW(),
                        true, true, true, true, false, false, NOW(), NOW())
            """), {
                'oid': org_id, 'did': dept_id, 'email': email,
                'fn': request.form.get('first_name', '').strip(),
                'ln': request.form.get('last_name', '').strip(),
                'role': request.form.get('role', 'member'),
                'token': token
            })
            db.session.commit()
            
            link = f"https://playmaster.sendbaba.com/team/accept-invite/{token}"
            flash('Member invited!', 'success')
            return render_template('dashboard/team/invite_member.html', 
                                 departments=departments, invitation_link=link, invited_email=email)
    
    except Exception as e:
        logger.error(f"Invite error: {e}")
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return render_template('dashboard/team/invite_member.html', departments=departments)


@team_bp.route('/members/<int:mid>/change-department', methods=['POST'])
@login_required
def change_department(mid):
    """Change member department"""
    org_id = get_org_id()
    try:
        did = request.form.get('department_id')
        if did:
            did = int(did)
        else:
            did = None
        
        db.session.execute(text(
            "UPDATE team_members SET department_id=:did, updated_at=NOW() WHERE id=:id AND organization_id=:oid"
        ), {'id': mid, 'oid': org_id, 'did': did})
        db.session.commit()
        flash('Updated!', 'success')
    except Exception as e:
        logger.error(f"Change dept error: {e}")
        db.session.rollback()
    return redirect(url_for('team.index'))


@team_bp.route('/members/<int:mid>/edit', methods=['GET', 'POST'])
@login_required
def edit_member(mid):
    """Edit member"""
    org_id = get_org_id()
    try:
        m = db.session.execute(text("""
            SELECT id, email, first_name, last_name, role, department_id,
                   COALESCE(is_active, true),
                   COALESCE(can_send_email, true), COALESCE(can_manage_contacts, true),
                   COALESCE(can_manage_campaigns, true), COALESCE(can_view_analytics, true),
                   COALESCE(can_manage_team, false), COALESCE(can_manage_billing, false)
            FROM team_members WHERE id=:id AND organization_id=:oid
        """), {'id': mid, 'oid': org_id}).fetchone()
        
        if not m:
            flash('Not found', 'error')
            return redirect(url_for('team.index'))
        
        depts = db.session.execute(text(
            "SELECT id, name FROM departments WHERE organization_id=:oid ORDER BY name"
        ), {'oid': org_id}).fetchall()
        
        member = {
            'id': m[0], 'email': m[1], 'first_name': m[2] or '', 'last_name': m[3] or '',
            'role': m[4] or 'member', 'department_id': m[5], 'is_active': bool(m[6]),
            'can_send_email': bool(m[7]), 'can_manage_contacts': bool(m[8]),
            'can_manage_campaigns': bool(m[9]), 'can_view_analytics': bool(m[10]),
            'can_manage_team': bool(m[11]), 'can_manage_billing': bool(m[12])
        }
        departments = [{'id': d[0], 'name': d[1]} for d in depts]
        
        if request.method == 'POST':
            did = request.form.get('department_id')
            if did:
                did = int(did)
            else:
                did = None
            
            db.session.execute(text("""
                UPDATE team_members SET 
                    first_name=:fn, last_name=:ln, role=:role, department_id=:did,
                    is_active=:active, can_send_email=:ce, can_manage_contacts=:cc,
                    can_manage_campaigns=:cca, can_view_analytics=:cv,
                    can_manage_team=:ct, can_manage_billing=:cb, updated_at=NOW()
                WHERE id=:id AND organization_id=:oid
            """), {
                'id': mid, 'oid': org_id,
                'fn': request.form.get('first_name', '').strip(),
                'ln': request.form.get('last_name', '').strip(),
                'role': request.form.get('role', 'member'),
                'did': did,
                'active': request.form.get('is_active') == 'on',
                'ce': request.form.get('can_send_email') == 'on',
                'cc': request.form.get('can_manage_contacts') == 'on',
                'cca': request.form.get('can_manage_campaigns') == 'on',
                'cv': request.form.get('can_view_analytics') == 'on',
                'ct': request.form.get('can_manage_team') == 'on',
                'cb': request.form.get('can_manage_billing') == 'on'
            })
            db.session.commit()
            flash('Updated!', 'success')
            return redirect(url_for('team.index'))
        
        return render_template('dashboard/team/edit_member.html', member=member, departments=departments)
    
    except Exception as e:
        logger.error(f"Edit member error: {e}")
        db.session.rollback()
        flash('Error', 'error')
        return redirect(url_for('team.index'))


@team_bp.route('/members/<int:mid>/delete', methods=['POST'])
@login_required
def delete_member(mid):
    """Delete member"""
    org_id = get_org_id()
    try:
        db.session.execute(text(
            "DELETE FROM team_members WHERE id=:id AND organization_id=:oid"
        ), {'id': mid, 'oid': org_id})
        db.session.commit()
        flash('Removed!', 'success')
    except Exception as e:
        logger.error(f"Delete member error: {e}")
        db.session.rollback()
    return redirect(url_for('team.index'))


@team_bp.route('/send-email')
@login_required
def send_single_email():
    """Send email page"""
    org_id = get_org_id()
    templates = []
    domains = []
    contacts = []
    
    try:
        # Templates
        trows = db.session.execute(text("""
            SELECT id, name, subject, html_content, category 
            FROM email_templates WHERE organization_id IN ('system', :oid)
        """), {'oid': org_id}).fetchall()
        templates = [{'id': t[0], 'name': t[1], 'subject': t[2] or '', 
                     'html_content': t[3] or '', 'category': t[4] or ''} for t in trows]
        
        # Domains
        drows = db.session.execute(text("""
            SELECT id, domain_name FROM domains 
            WHERE organization_id=:oid AND dns_verified=true
        """), {'oid': org_id}).fetchall()
        domains = [{'id': str(d[0]), 'domain': d[1]} for d in drows if d[1]]
        
        # Contacts
        crows = db.session.execute(text("""
            SELECT email, first_name, last_name FROM contacts 
            WHERE organization_id=:oid LIMIT 100
        """), {'oid': org_id}).fetchall()
        contacts = [{'email': c[0], 'name': f"{c[1] or ''} {c[2] or ''}".strip() or c[0].split('@')[0]} 
                   for c in crows]
    except Exception as e:
        logger.error(f"Send email page error: {e}")
    
    uname = ''
    try:
        uname = getattr(current_user, 'name', '') or current_user.email.split('@')[0]
    except:
        pass
    
    return render_template('dashboard/team/send_email.html',
        templates=templates, domains=domains, recent_emails=[],
        contacts=contacts, user_name=uname, user_email=getattr(current_user, 'email', ''))


@team_bp.route('/send-email/send', methods=['POST'])
@login_required
def send_email_action():
    """Send email"""
    org_id = get_org_id()
    try:
        data = request.get_json() if request.is_json else request.form
        to_email = data.get('recipient_email', '').strip()
        subject = data.get('subject', '').strip()
        
        if not to_email or not subject:
            err = 'Recipient and subject required'
            if request.is_json:
                return jsonify({'success': False, 'error': err})
            flash(err, 'error')
            return redirect(url_for('team.send_single_email'))
        
        result = db.session.execute(text("""
            INSERT INTO single_emails 
            (organization_id, sender_user_id, from_name, from_email, reply_to,
             recipient_email, recipient_name, subject, html_body, status, created_at, updated_at)
            VALUES (:oid, :uid, :fn, :fe, :rt, :te, :tn, :subj, :body, 'queued', NOW(), NOW())
            RETURNING id
        """), {
            'oid': org_id, 'uid': str(current_user.id),
            'fn': data.get('from_name', '') or 'SendBaba',
            'fe': data.get('from_email', '') or 'noreply@sendbaba.com',
            'rt': data.get('reply_to', '') or data.get('from_email', ''),
            'te': to_email, 'tn': data.get('recipient_name', ''),
            'subj': subject, 'body': data.get('html_body', '')
        })
        eid = result.fetchone()[0]
        db.session.commit()
        
        try:
            from app.tasks.email_tasks import send_single_email_task
            send_single_email_task.delay(eid)
        except:
            pass
        
        if request.is_json:
            return jsonify({'success': True, 'id': eid})
        flash(f'Email queued!', 'success')
        return redirect(url_for('team.send_single_email'))
    
    except Exception as e:
        logger.error(f"Send email error: {e}")
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'error': str(e)})
        flash('Error', 'error')
        return redirect(url_for('team.send_single_email'))


@team_bp.route('/billing')
@login_required
def billing():
    """Billing page"""
    org_id = get_org_id()
    org_info = {'name': '', 'plan': 'free', 'monthly_email_limit': 10000, 
                'emails_used_this_month': 0, 'price_per_email': 0.001}
    
    try:
        o = db.session.execute(text(
            "SELECT name, plan, email_limit FROM organizations WHERE id=:oid"
        ), {'oid': org_id}).fetchone()
        
        if o:
            org_info = {
                'name': o[0] or '', 'plan': o[1] or 'free',
                'monthly_email_limit': o[2] or 10000,
                'emails_used_this_month': 0, 'price_per_email': 0.001
            }
    except Exception as e:
        logger.error(f"Billing error: {e}")
    
    return render_template('dashboard/team/billing.html',
        org_info=org_info, dept_usage=[], member_usage=[], daily_chart=[], billing_history=[])


@team_bp.route('/api/template/<int:tid>')
@login_required
def api_get_template(tid):
    """Get template"""
    try:
        r = db.session.execute(text(
            "SELECT id, name, subject, html_content FROM email_templates WHERE id=:id"
        ), {'id': tid}).fetchone()
        if r:
            return jsonify({'success': True, 'template': {
                'id': r[0], 'name': r[1], 'subject': r[2] or '', 'html_content': r[3] or ''
            }})
        return jsonify({'success': False, 'error': 'Not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
