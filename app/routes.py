
# ============ TRASH MANAGEMENT ROUTES ============

@app.route('/api/email/<int:id>/restore', methods=['POST'])
@login_required
def restore_email(id):
    """Restore email from trash to inbox"""
    try:
        email = Email.query.filter_by(id=id, user_id=current_user.id).first()
        if not email:
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        
        email.folder = 'inbox'
        email.is_deleted = False
        db.session.commit()
        return jsonify({'success': True, 'message': 'Email restored to inbox'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email/<int:id>/permanent-delete', methods=['POST'])
@login_required
def permanent_delete_email(id):
    """Permanently delete email from database"""
    try:
        email = Email.query.filter_by(id=id, user_id=current_user.id).first()
        if not email:
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        
        # Delete attachments first
        if hasattr(email, 'attachments'):
            for att in email.attachments:
                # Delete file from disk if exists
                if att.file_path and os.path.exists(att.file_path):
                    try:
                        os.remove(att.file_path)
                    except:
                        pass
                db.session.delete(att)
        
        db.session.delete(email)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Email permanently deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/emails/empty-trash', methods=['POST'])
@login_required
def empty_trash():
    """Permanently delete all emails in trash"""
    try:
        emails = Email.query.filter_by(user_id=current_user.id, folder='trash').all()
        count = len(emails)
        
        for email in emails:
            # Delete attachments first
            if hasattr(email, 'attachments'):
                for att in email.attachments:
                    if att.file_path and os.path.exists(att.file_path):
                        try:
                            os.remove(att.file_path)
                        except:
                            pass
                    db.session.delete(att)
            db.session.delete(email)
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{count} emails permanently deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ ATTACHMENT ROUTES ============

@app.route('/api/attachment/<int:id>')
@login_required
def get_attachment(id):
    """Serve attachment file for viewing/download"""
    try:
        att = Attachment.query.filter_by(id=id).first()
        if not att:
            return jsonify({'success': False, 'error': 'Attachment not found'}), 404
        
        # Verify user owns this email
        email = Email.query.filter_by(id=att.email_id, user_id=current_user.id).first()
        if not email:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Check if download requested
        download = request.args.get('download', '0') == '1'
        
        # If file stored on disk
        if att.file_path and os.path.exists(att.file_path):
            if download:
                return send_file(att.file_path, as_attachment=True, download_name=att.filename)
            else:
                return send_file(att.file_path, mimetype=att.content_type or 'application/octet-stream')
        
        # If file stored as binary in database
        if att.data:
            from io import BytesIO
            file_data = BytesIO(att.data)
            
            if download:
                return send_file(file_data, as_attachment=True, download_name=att.filename, mimetype=att.content_type or 'application/octet-stream')
            else:
                return send_file(file_data, mimetype=att.content_type or 'application/octet-stream')
        
        return jsonify({'success': False, 'error': 'Attachment data not found'}), 404
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Make sure to import these at top of file:
# import os
# from flask import send_file


# ============ TRASH MANAGEMENT ROUTES ============

@app.route('/api/email/<int:id>/restore', methods=['POST'])
@login_required
def restore_email(id):
    """Restore email from trash to inbox"""
    try:
        email = Email.query.filter_by(id=id, user_id=current_user.id).first()
        if not email:
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        
        email.folder = 'inbox'
        email.is_deleted = False
        db.session.commit()
        return jsonify({'success': True, 'message': 'Email restored to inbox'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email/<int:id>/permanent-delete', methods=['POST'])
@login_required
def permanent_delete_email(id):
    """Permanently delete email from database"""
    try:
        email = Email.query.filter_by(id=id, user_id=current_user.id).first()
        if not email:
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        
        # Delete attachments first
        if hasattr(email, 'attachments'):
            for att in email.attachments:
                # Delete file from disk if exists
                if att.file_path and os.path.exists(att.file_path):
                    try:
                        os.remove(att.file_path)
                    except:
                        pass
                db.session.delete(att)
        
        db.session.delete(email)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Email permanently deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/emails/empty-trash', methods=['POST'])
@login_required
def empty_trash():
    """Permanently delete all emails in trash"""
    try:
        emails = Email.query.filter_by(user_id=current_user.id, folder='trash').all()
        count = len(emails)
        
        for email in emails:
            # Delete attachments first
            if hasattr(email, 'attachments'):
                for att in email.attachments:
                    if att.file_path and os.path.exists(att.file_path):
                        try:
                            os.remove(att.file_path)
                        except:
                            pass
                    db.session.delete(att)
            db.session.delete(email)
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{count} emails permanently deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ ATTACHMENT ROUTES ============

@app.route('/api/attachment/<int:id>')
@login_required
def get_attachment(id):
    """Serve attachment file for viewing/download"""
    try:
        att = Attachment.query.filter_by(id=id).first()
        if not att:
            return jsonify({'success': False, 'error': 'Attachment not found'}), 404
        
        # Verify user owns this email
        email = Email.query.filter_by(id=att.email_id, user_id=current_user.id).first()
        if not email:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Check if download requested
        download = request.args.get('download', '0') == '1'
        
        # If file stored on disk
        if att.file_path and os.path.exists(att.file_path):
            if download:
                return send_file(att.file_path, as_attachment=True, download_name=att.filename)
            else:
                return send_file(att.file_path, mimetype=att.content_type or 'application/octet-stream')
        
        # If file stored as binary in database
        if att.data:
            from io import BytesIO
            file_data = BytesIO(att.data)
            
            if download:
                return send_file(file_data, as_attachment=True, download_name=att.filename, mimetype=att.content_type or 'application/octet-stream')
            else:
                return send_file(file_data, mimetype=att.content_type or 'application/octet-stream')
        
        return jsonify({'success': False, 'error': 'Attachment data not found'}), 404
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Make sure to import these at top of file:
# import os
# from flask import send_file

