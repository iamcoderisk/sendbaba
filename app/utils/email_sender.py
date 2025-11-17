"""
Email sending utility for SendBaba
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, url_for
import logging

logger = logging.getLogger(__name__)

def send_team_invitation_email(member_email, invitation_token, inviter_name, org_name):
    """
    Send team invitation email
    """
    try:
        # Create invitation URL
        invitation_url = f"https://playmaster.sendbaba.com/team/accept-invite/{invitation_token}"
        
        # Email content
        subject = f"You've been invited to join {org_name} on SendBaba"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 You're Invited!</h1>
                </div>
                <div class="content">
                    <p>Hi there,</p>
                    <p><strong>{inviter_name}</strong> has invited you to join <strong>{org_name}</strong> on SendBaba.</p>
                    <p>SendBaba is a powerful email marketing platform that helps teams send, track, and manage email campaigns.</p>
                    
                    <center>
                        <a href="{invitation_url}" class="button">Accept Invitation & Set Password</a>
                    </center>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="background: #eee; padding: 10px; word-break: break-all; font-size: 12px;">{invitation_url}</p>
                    
                    <p>This invitation will expire in 7 days.</p>
                    
                    <p>If you didn't expect this invitation, you can safely ignore this email.</p>
                </div>
                <div class="footer">
                    <p>© 2024 SendBaba. All rights reserved.</p>
                    <p>This is an automated email, please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        You've been invited to join {org_name} on SendBaba
        
        {inviter_name} has invited you to join their team on SendBaba.
        
        Accept your invitation and set your password here:
        {invitation_url}
        
        This invitation will expire in 7 days.
        
        If you didn't expect this invitation, you can safely ignore this email.
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = 'SendBaba <noreply@sendbaba.com>'
        msg['To'] = member_email
        
        # Attach both text and HTML versions
        part1 = MIMEText(text_body, 'plain')
        part2 = MIMEText(html_body, 'html')
        msg.attach(part1)
        msg.attach(part2)
        
        # Send via SMTP (using local server or external SMTP)
        try:
            # Try local SMTP first
            with smtplib.SMTP('localhost', 25) as server:
                server.send_message(msg)
                logger.info(f"✅ Invitation email sent to {member_email}")
                return True
        except Exception as local_error:
            logger.warning(f"Local SMTP failed: {local_error}, trying external...")
            
            # Fallback to external SMTP if available
            try:
                smtp_host = current_app.config.get('MAIL_SERVER', 'smtp.gmail.com')
                smtp_port = current_app.config.get('MAIL_PORT', 587)
                smtp_user = current_app.config.get('MAIL_USERNAME')
                smtp_pass = current_app.config.get('MAIL_PASSWORD')
                
                if smtp_user and smtp_pass:
                    with smtplib.SMTP(smtp_host, smtp_port) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                        logger.info(f"✅ Invitation email sent to {member_email} via external SMTP")
                        return True
                else:
                    logger.error("No external SMTP configured")
                    return False
            except Exception as ext_error:
                logger.error(f"External SMTP failed: {ext_error}")
                return False
                
    except Exception as e:
        logger.error(f"Failed to send invitation email: {e}")
        return False
