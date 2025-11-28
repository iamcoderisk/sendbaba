import os
import re

controllers = [
    '/opt/sendbaba-staging/app/controllers/form_controller.py',
    '/opt/sendbaba-staging/app/controllers/workflow_controller.py',
    '/opt/sendbaba-staging/app/controllers/segment_controller.py',
    '/opt/sendbaba-staging/app/controllers/integration_controller.py',
    '/opt/sendbaba-staging/app/controllers/reply_controller.py',
    '/opt/sendbaba-staging/app/controllers/email_builder_controller.py',
]

for filepath in controllers:
    if not os.path.exists(filepath):
        print(f"❌ Not found: {filepath}")
        continue
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    
    # Add flask_login import if not present
    if 'from flask_login import' not in content:
        # Find the flask import line and add flask_login after it
        content = content.replace(
            'from flask import Blueprint',
            'from flask import Blueprint\nfrom flask_login import login_required, current_user'
        )
    
    # Remove the custom login_required decorator definition
    # Match the pattern: def login_required(f): ... return decorated_function
    pattern = r"# Helper decorator for login required\ndef login_required\(f\):.*?return decorated_function\n"
    content = re.sub(pattern, '', content, flags=re.DOTALL)
    
    # Also try another pattern variant
    pattern2 = r"def login_required\(f\):\s+@wraps\(f\).*?return decorated_function\n"
    content = re.sub(pattern2, '', content, flags=re.DOTALL)
    
    # Update get_organization_id to use current_user
    old_get_org = '''def get_organization_id():
    return session.get('organization_id')'''
    new_get_org = '''def get_organization_id():
    if current_user.is_authenticated:
        return getattr(current_user, 'organization_id', session.get('organization_id'))
    return session.get('organization_id')'''
    content = content.replace(old_get_org, new_get_org)
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✅ Fixed: {os.path.basename(filepath)}")
    else:
        print(f"⚠️  No changes: {os.path.basename(filepath)}")

print("\n✅ Auth fix complete!")
