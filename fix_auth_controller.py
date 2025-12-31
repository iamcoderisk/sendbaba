import re

auth_path = '/opt/sendbaba-staging/app/controllers/auth_controller.py'

with open(auth_path, 'r') as f:
    content = f.read()

# Check if check-email endpoint exists
if '/auth/api/check-email' not in content:
    # Find the end of the file and add the API endpoint
    new_endpoint = '''

@auth_bp.route('/auth/api/check-email')
def check_email_availability():
    """Check if a sendbaba.com email is available"""
    from flask import jsonify
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    username = request.args.get('username', '').lower().strip()
    
    if not username or len(username) < 3:
        return jsonify({'available': False, 'error': 'Username too short'})
    
    email = f"{username}@sendbaba.com"
    
    try:
        conn = psycopg2.connect("postgresql://emailer:SecurePassword123@localhost/emailer")
        cur = conn.cursor()
        
        # Check in mailboxes table
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (email,))
        exists = cur.fetchone()
        
        conn.close()
        
        return jsonify({'available': not exists, 'email': email})
    except Exception as e:
        return jsonify({'available': False, 'error': str(e)})

'''
    
    # Append to file
    with open(auth_path, 'a') as f:
        f.write(new_endpoint)
    print("✅ Added check-email API endpoint")
else:
    print("✅ check-email API already exists")

# Now check if register handles mailbox type
if "registration_type == 'mailbox'" not in content:
    print("⚠️  Need to update register function to handle mailbox type")
    
    # Find the register function and add mailbox handling
    # This is complex, so let's create a patch
    
    mailbox_handler = '''
        # Handle mailbox registration
        if registration_type == 'mailbox':
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            username = request.form.get('username', '').lower().strip()
            recovery_email = request.form.get('recovery_email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return redirect(url_for('auth.register'))
            
            email = f"{username}@sendbaba.com"
            name = f"{first_name} {last_name}".strip()
            
            # Check if email exists
            cur.execute("SELECT id FROM mailboxes WHERE email = %s", (email,))
            if cur.fetchone():
                flash('This email is already taken', 'error')
                return redirect(url_for('auth.register'))
            
            # Create user account first
            import hashlib
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            # Get or create internal org
            cur.execute("SELECT id FROM mailbox_organizations WHERE slug = 'sendbaba-internal'")
            org = cur.fetchone()
            if not org:
                cur.execute("INSERT INTO mailbox_organizations (name, slug, plan, max_mailboxes, max_storage_gb) VALUES ('SendBaba Internal', 'sendbaba-internal', 'enterprise', 1000, 1000) RETURNING id")
                org = cur.fetchone()
            
            # Create mailbox
            cur.execute("""
                INSERT INTO mailboxes (organization_id, email, name, password_hash, recovery_email, is_active, storage_used_mb)
                VALUES (%s, %s, %s, %s, %s, true, 0) RETURNING id
            """, (org['id'], email, name, password_hash, recovery_email))
            
            conn.commit()
            conn.close()
            
            flash('Registration successful! You can now login to your mailbox.', 'success')
            return redirect('https://mail.sendbaba.com')
'''
    
    print("⚠️  Please manually update the register function in auth_controller.py")
    print("    Add mailbox registration handling")
else:
    print("✅ Mailbox registration handling exists")
