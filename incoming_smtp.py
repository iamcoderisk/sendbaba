#!/usr/bin/env python3
"""
SendBaba Incoming SMTP Server - Multi-Tenant
Receives emails for multiple domains and stores them in the database
"""

import asyncio
import email
import logging
import os
import sys
import uuid
import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Envelope
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('incoming_smtp')

# Database connection
DATABASE_URL = "postgresql://emailer:SecurePassword123@localhost/emailer"

def get_db():
    """Get database connection"""
    return psycopg2.connect(DATABASE_URL)

def get_accepted_domains():
    """Get list of domains we accept mail for (from database)"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        domains = []
        
        # Get from mailbox_domains (legacy)
        try:
            cur.execute("""
                SELECT domain FROM mailbox_domains 
                WHERE is_active = true AND mx_verified = true
            """)
            domains += [r['domain'].lower() for r in cur.fetchall()]
        except:
            pass
        
        # Get from webmail_domains (custom domains)
        try:
            cur.execute("""
                SELECT domain_name FROM webmail_domains 
                WHERE is_active = true AND dns_verified = true
            """)
            domains += [r['domain_name'].lower() for r in cur.fetchall()]
        except:
            pass
        
        conn.close()
        
        # Always include these
        default_domains = ['sendbaba.com', 'mail.sendbaba.com', 'inbox.sendbaba.com']
        all_domains = list(set(domains + default_domains))
        
        logger.info(f"Accepting mail for domains: {all_domains}")
        return all_domains
    except Exception as e:
        logger.error(f"Failed to get domains: {e}")
        return ['sendbaba.com', 'mail.sendbaba.com', 'inbox.sendbaba.com']

# Global domain list (refreshed periodically)
ACCEPTED_DOMAINS = get_accepted_domains()

def refresh_domains():
    """Refresh the list of accepted domains"""
    global ACCEPTED_DOMAINS
    ACCEPTED_DOMAINS = get_accepted_domains()

def extract_email_address(header_value):
    """Extract email address from header like 'Name <email@domain.com>'"""
    if not header_value:
        return None
    match = re.search(r'<([^>]+)>', header_value)
    if match:
        return match.group(1).lower()
    if '@' in header_value:
        return header_value.strip().lower()
    return None

def extract_name(header_value):
    """Extract name from header like 'Name <email@domain.com>'"""
    if not header_value:
        return None
    match = re.search(r'^([^<]+)<', header_value)
    if match:
        return match.group(1).strip().strip('"')
    return None

def get_mailbox_for_email(email_address):
    """Get or create mailbox for an email address"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        email_lower = email_address.lower()
        domain = email_lower.split('@')[-1] if '@' in email_lower else ''
        
        # Check if mailbox exists
        cur.execute("SELECT id, organization_id FROM mailboxes WHERE email = %s", (email_lower,))
        mailbox = cur.fetchone()
        
        if mailbox:
            conn.close()
            return mailbox['id']
        
        # Get organization for this domain (check both tables)
        org_id = None
        
        # Check mailbox_domains first
        cur.execute("""
            SELECT o.id as org_id FROM mailbox_organizations o
            JOIN mailbox_domains d ON d.organization_id = o.id
            WHERE d.domain = %s AND d.is_active = true
        """, (domain,))
        org = cur.fetchone()
        if org:
            org_id = org['org_id']
        
        # Check webmail_domains if not found
        if not org_id:
            try:
                cur.execute("""
                    SELECT organization_id as org_id FROM webmail_domains
                    WHERE domain_name = %s AND is_active = true AND dns_verified = true
                """, (domain,))
                org = cur.fetchone()
                if org:
                    org_id = org['org_id']
            except:
                pass
        
        # If no org found, try to get sendbaba default
        if not org_id:
            cur.execute("SELECT id FROM mailbox_organizations WHERE slug = 'sendbaba'")
            default_org = cur.fetchone()
            org_id = default_org['id'] if default_org else None
        
        # Auto-create mailbox (catch-all behavior)
        cur.execute("""
            INSERT INTO mailboxes (organization_id, email, name, is_active)
            VALUES (%s, %s, %s, true)
            RETURNING id
        """, (org_id, email_lower, email_lower.split('@')[0]))
        
        mailbox_id = cur.fetchone()['id']
        conn.commit()
        conn.close()
        
        logger.info(f"Auto-created mailbox: {email_lower}")
        return mailbox_id
        
    except Exception as e:
        logger.error(f"Error getting mailbox: {e}")
        return None


class IncomingMailHandler:
    """Handle incoming emails - Multi-Tenant"""
    
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        """Check if we accept mail for this address"""
        # Refresh domains periodically
        if hasattr(self, '_last_refresh'):
            if (datetime.now() - self._last_refresh).seconds > 60:
                refresh_domains()
                self._last_refresh = datetime.now()
        else:
            self._last_refresh = datetime.now()
        
        domain = address.split('@')[-1].lower() if '@' in address else ''
        
        if domain not in ACCEPTED_DOMAINS:
            logger.warning(f"Rejected recipient: {address} (domain {domain} not accepted)")
            return '550 User not found'
        
        envelope.rcpt_tos.append(address)
        logger.info(f"Accepted recipient: {address}")
        return '250 OK'
    
    async def handle_DATA(self, server, session, envelope):
        """Process incoming email"""
        try:
            # Parse the email
            parser = BytesParser(policy=policy.default)
            msg = parser.parsebytes(envelope.content)
            
            # Extract headers
            from_email = extract_email_address(msg.get('From', ''))
            from_name = extract_name(msg.get('From', ''))
            to_email = extract_email_address(msg.get('To', ''))
            cc = msg.get('Cc', '')
            subject = msg.get('Subject', '(no subject)')
            message_id = msg.get('Message-ID', f'<{uuid.uuid4()}@sendbaba.com>')
            in_reply_to = msg.get('In-Reply-To', '')
            
            # Extract body
            body_text = ''
            body_html = ''
            has_attachments = False
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get('Content-Disposition', ''))
                    
                    if 'attachment' in content_disposition:
                        has_attachments = True
                        continue
                    
                    if content_type == 'text/plain':
                        try:
                            body_text = part.get_content()
                        except:
                            body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    elif content_type == 'text/html':
                        try:
                            body_html = part.get_content()
                        except:
                            body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            else:
                content_type = msg.get_content_type()
                try:
                    content = msg.get_content()
                except:
                    content = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                
                if content_type == 'text/html':
                    body_html = content
                else:
                    body_text = content
            
            # Determine folder (basic spam detection)
            folder = 'inbox'
            spam_score = 0
            
            spam_keywords = ['viagra', 'lottery', 'winner', 'nigerian prince', 'bitcoin investment', 'free money']
            subject_lower = (subject or '').lower()
            body_lower = (body_text or '').lower()
            
            for keyword in spam_keywords:
                if keyword in subject_lower or keyword in body_lower:
                    spam_score += 0.3
            
            if spam_score > 0.5:
                folder = 'spam'
            
            # Store in database
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            for rcpt in envelope.rcpt_tos:
                rcpt_lower = rcpt.lower()
                
                # Get or create mailbox
                mailbox_id = get_mailbox_for_email(rcpt_lower)
                
                if not mailbox_id:
                    logger.error(f"Could not get mailbox for: {rcpt_lower}")
                    continue
                
                # Generate thread_id
                thread_id = in_reply_to if in_reply_to else message_id
                
                # Insert email
                cur.execute("""
                    INSERT INTO mailbox_emails 
                    (mailbox_id, message_id, in_reply_to, thread_id, from_email, from_name, 
                     to_email, cc, subject, body_text, body_html, folder, is_spam, spam_score,
                     has_attachments, received_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id
                """, (
                    mailbox_id, message_id, in_reply_to, thread_id, from_email, from_name,
                    rcpt_lower, cc, subject, body_text, body_html, folder, folder == 'spam',
                    spam_score, has_attachments
                ))
                
                email_id = cur.fetchone()['id']
                logger.info(f"Stored email {email_id}: {from_email} -> {rcpt_lower}: {subject}")
                
                # Handle attachments
                if has_attachments and msg.is_multipart():
                    attachment_dir = f'/opt/sendbaba-staging/attachments/{email_id}'
                    os.makedirs(attachment_dir, exist_ok=True)
                    
                    for part in msg.walk():
                        content_disposition = str(part.get('Content-Disposition', ''))
                        if 'attachment' in content_disposition:
                            filename = part.get_filename() or f'attachment_{uuid.uuid4()}'
                            filepath = os.path.join(attachment_dir, filename)
                            
                            with open(filepath, 'wb') as f:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    f.write(payload)
                            
                            cur.execute("""
                                INSERT INTO mailbox_attachments (email_id, filename, content_type, size, path)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (
                                email_id, filename, part.get_content_type(),
                                os.path.getsize(filepath) if os.path.exists(filepath) else 0, filepath
                            ))
                            logger.info(f"Saved attachment: {filename}")
            
            conn.commit()
            conn.close()
            
            logger.info(f"Email processed successfully: {from_email} -> {envelope.rcpt_tos}")
            return '250 Message accepted for delivery'
            
        except Exception as e:
            logger.error(f"Error processing email: {e}", exc_info=True)
            return '451 Temporary failure, please try again later'


async def main():
    """Start the SMTP server"""
    handler = IncomingMailHandler()
    
    controller = Controller(
        handler,
        hostname='0.0.0.0',
        port=25,
        ready_timeout=10
    )
    
    logger.info("Starting SendBaba Multi-Tenant Incoming SMTP Server on port 25...")
    logger.info(f"Accepting mail for domains: {', '.join(ACCEPTED_DOMAINS)}")
    
    controller.start()
    logger.info("SMTP Server started successfully!")
    
    # Periodically refresh domains
    try:
        while True:
            await asyncio.sleep(60)
            refresh_domains()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        controller.stop()


if __name__ == '__main__':
    asyncio.run(main())
