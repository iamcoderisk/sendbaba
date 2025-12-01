#!/usr/bin/env python3
"""Fix corrupted imports in all 6 controllers"""
import os
import re

controllers = [
    "app/controllers/form_controller.py",
    "app/controllers/workflow_controller.py", 
    "app/controllers/segment_controller.py",
    "app/controllers/integration_controller.py",
    "app/controllers/reply_controller.py",
    "app/controllers/email_builder_controller.py"
]

for filepath in controllers:
    print(f"Fixing: {filepath}")
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Find and fix corrupted flask_login import
    pattern = r'from flask_login import login_required, current_user(?:,\s*[a-z_]+)+'
    match = re.search(pattern, content)
    
    if match:
        corrupted = match.group(0)
        # Get flask items that were wrongly in flask_login
        parts = corrupted.split('current_user,')
        flask_items = parts[1].strip() if len(parts) > 1 else ''
        
        # Build correct imports
        if flask_items:
            flask_import = f"from flask import Blueprint, {flask_items}"
        else:
            flask_import = "from flask import Blueprint"
        flask_login_import = "from flask_login import login_required, current_user"
        
        # Replace corrupted line with correct flask_login import
        content = content.replace(corrupted, flask_login_import)
        
        # Fix the Blueprint import line
        if "from flask import Blueprint\n" in content:
            content = content.replace("from flask import Blueprint\n", f"{flask_import}\n")
        
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  ✅ Fixed")
    else:
        print(f"  ⏭️ Already correct or different pattern")

print("\n✅ All controllers processed!")
