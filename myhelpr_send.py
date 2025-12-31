#!/usr/bin/env python3
"""
Bridge script for MyHelpr to use SendBaba relay
"""
import sys
import json

sys.path.insert(0, '/opt/sendbaba-staging')

from app.smtp.relay_server import send_email_sync

def send_email(to_email, from_email, from_name, subject, html_body, reply_to=None):
    email_data = {
        'from': from_email,
        'from_name': from_name,
        'to': to_email,
        'subject': subject,
        'html_body': html_body,
    }
    if reply_to:
        email_data['reply_to'] = reply_to
    
    result = send_email_sync(email_data)
    return result

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print(json.dumps({'success': False, 'error': 'Missing args'}))
        sys.exit(1)
    
    to_email = sys.argv[1]
    from_email = sys.argv[2]
    from_name = sys.argv[3]
    subject = sys.argv[4]
    html_body = sys.argv[5] if len(sys.argv) > 5 else '<p>Test</p>'
    
    result = send_email(to_email, from_email, from_name, subject, html_body)
    print(json.dumps(result))
