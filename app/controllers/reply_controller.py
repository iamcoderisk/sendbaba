"""
SendBaba Replies Controller
Handles email reply tracking and AI analysis
"""
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
import json
import uuid
import re

reply_bp = Blueprint('replies', __name__, url_prefix='/dashboard/replies')


def get_organization_id():
    if current_user.is_authenticated:
        return getattr(current_user, 'organization_id', session.get('organization_id'))
    return session.get('organization_id')


# ==================== PAGE ROUTES ====================

@reply_bp.route('/')
@login_required
def index():
    """Replies inbox page"""
    return render_template('dashboard/replies/index.html')


@reply_bp.route('/<reply_id>')
@login_required
def view(reply_id):
    """View single reply"""
    from app.models.replies import EmailReply
    
    reply = EmailReply.query.filter_by(id=reply_id, organization_id=get_organization_id()).first()
    if not reply:
        return render_template('errors/404.html'), 404
    
    return render_template('dashboard/replies/view.html', reply=reply)


@reply_bp.route('/insights')
@login_required
def insights():
    """Reply insights/analytics page"""
    return render_template('dashboard/replies/insights.html')


@reply_bp.route('/templates')
@login_required
def templates():
    """Reply templates page"""
    return render_template('dashboard/replies/templates.html')


# ==================== API ROUTES ====================

@reply_bp.route('/api/list')
@login_required
def api_list():
    """Get replies list"""
    from app.models.replies import EmailReply
    
    org_id = get_organization_id()
    
    # Filters
    status = request.args.get('status')
    sentiment = request.args.get('sentiment')
    intent = request.args.get('intent')
    category = request.args.get('category')
    starred = request.args.get('starred')
    search = request.args.get('search')
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    query = EmailReply.query.filter_by(organization_id=org_id)
    
    if status:
        query = query.filter_by(status=status)
    if sentiment:
        query = query.filter_by(sentiment=sentiment)
    if intent:
        query = query.filter_by(intent=intent)
    if category:
        query = query.filter_by(category=category)
    if starred == 'true':
        query = query.filter_by(starred=True)
    if search:
        query = query.filter(
            (EmailReply.from_email.ilike(f'%{search}%')) |
            (EmailReply.subject.ilike(f'%{search}%')) |
            (EmailReply.body_text.ilike(f'%{search}%'))
        )
    
    replies = query.order_by(EmailReply.received_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'success': True,
        'replies': [r.to_dict() for r in replies.items],
        'total': replies.total,
        'pages': replies.pages,
        'current_page': page,
        'unread_count': EmailReply.query.filter_by(organization_id=org_id, status='unread').count()
    })


@reply_bp.route('/api/<reply_id>', methods=['GET'])
@login_required
def api_get(reply_id):
    """Get reply details"""
    from app.models.replies import EmailReply
    
    reply = EmailReply.query.filter_by(id=reply_id, organization_id=get_organization_id()).first()
    if not reply:
        return jsonify({'error': 'Reply not found'}), 404
    
    # Mark as read
    if reply.status == 'unread':
        reply.status = 'read'
        from app import db
        db.session.commit()
    
    return jsonify({
        'success': True,
        'reply': reply.to_dict()
    })


@reply_bp.route('/api/<reply_id>', methods=['PUT'])
@login_required
def api_update(reply_id):
    """Update reply"""
    from app.models.replies import EmailReply
    from app import db
    
    reply = EmailReply.query.filter_by(id=reply_id, organization_id=get_organization_id()).first()
    if not reply:
        return jsonify({'error': 'Reply not found'}), 404
    
    data = request.get_json()
    
    if 'status' in data:
        reply.status = data['status']
    if 'starred' in data:
        reply.starred = data['starred']
    if 'category' in data:
        reply.category = data['category']
    if 'assigned_to' in data:
        reply.assigned_to = data['assigned_to']
        reply.assigned_at = datetime.utcnow()
    
    reply.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'reply': reply.to_dict()
    })


@reply_bp.route('/api/<reply_id>/star', methods=['POST'])
@login_required
def api_star(reply_id):
    """Toggle star on reply"""
    from app.models.replies import EmailReply
    from app import db
    
    reply = EmailReply.query.filter_by(id=reply_id, organization_id=get_organization_id()).first()
    if not reply:
        return jsonify({'error': 'Reply not found'}), 404
    
    reply.starred = not reply.starred
    db.session.commit()
    
    return jsonify({
        'success': True,
        'starred': reply.starred
    })


@reply_bp.route('/api/<reply_id>/archive', methods=['POST'])
@login_required
def api_archive(reply_id):
    """Archive reply"""
    from app.models.replies import EmailReply
    from app import db
    
    reply = EmailReply.query.filter_by(id=reply_id, organization_id=get_organization_id()).first()
    if not reply:
        return jsonify({'error': 'Reply not found'}), 404
    
    reply.status = 'archived'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Reply archived'
    })


@reply_bp.route('/api/<reply_id>/spam', methods=['POST'])
@login_required
def api_spam(reply_id):
    """Mark as spam"""
    from app.models.replies import EmailReply
    from app import db
    
    reply = EmailReply.query.filter_by(id=reply_id, organization_id=get_organization_id()).first()
    if not reply:
        return jsonify({'error': 'Reply not found'}), 404
    
    reply.status = 'spam'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Marked as spam'
    })


@reply_bp.route('/api/<reply_id>/analyze', methods=['POST'])
@login_required
def api_analyze(reply_id):
    """Re-analyze reply with AI"""
    from app.models.replies import EmailReply
    from app import db
    
    reply = EmailReply.query.filter_by(id=reply_id, organization_id=get_organization_id()).first()
    if not reply:
        return jsonify({'error': 'Reply not found'}), 404
    
    # Run AI analysis
    analysis = analyze_email_content(reply.body_text or reply.body_html, reply.subject)
    
    # Update reply with analysis
    reply.sentiment = analysis['sentiment']
    reply.sentiment_score = analysis['sentiment_score']
    reply.intent = analysis['intent']
    reply.urgency = analysis['urgency']
    reply.topics = json.dumps(analysis['topics'])
    reply.key_phrases = json.dumps(analysis['key_phrases'])
    reply.suggested_response = analysis['suggested_response']
    reply.ai_summary = analysis['summary']
    reply.is_auto_reply = analysis['is_auto_reply']
    reply.is_out_of_office = analysis['is_out_of_office']
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'analysis': analysis,
        'reply': reply.to_dict()
    })


@reply_bp.route('/api/<reply_id>/send-response', methods=['POST'])
@login_required
def api_send_response(reply_id):
    """Send response to reply"""
    from app.models.replies import EmailReply
    from app import db
    
    reply = EmailReply.query.filter_by(id=reply_id, organization_id=get_organization_id()).first()
    if not reply:
        return jsonify({'error': 'Reply not found'}), 404
    
    data = request.get_json()
    response_body = data.get('body')
    response_subject = data.get('subject', f"Re: {reply.subject}")
    template_id = data.get('template_id')
    
    if not response_body:
        return jsonify({'error': 'Response body required'}), 400
    
    # Send email via SMTP
    success = send_reply_email(reply, response_subject, response_body)
    
    if success:
        reply.status = 'replied'
        reply.replied_at = datetime.utcnow()
        
        # Calculate response time
        if reply.received_at:
            reply.reply_time_seconds = int((datetime.utcnow() - reply.received_at).total_seconds())
        
        # Track template usage
        if template_id:
            track_template_usage(template_id)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Response sent successfully'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Failed to send response'
        }), 500


@reply_bp.route('/api/bulk-action', methods=['POST'])
@login_required
def api_bulk_action():
    """Perform bulk action on replies"""
    from app.models.replies import EmailReply
    from app import db
    
    data = request.get_json()
    reply_ids = data.get('reply_ids', [])
    action = data.get('action')
    
    if not reply_ids or not action:
        return jsonify({'error': 'Reply IDs and action required'}), 400
    
    org_id = get_organization_id()
    
    replies = EmailReply.query.filter(
        EmailReply.id.in_(reply_ids),
        EmailReply.organization_id == org_id
    ).all()
    
    for reply in replies:
        if action == 'archive':
            reply.status = 'archived'
        elif action == 'spam':
            reply.status = 'spam'
        elif action == 'read':
            reply.status = 'read'
        elif action == 'unread':
            reply.status = 'unread'
        elif action == 'star':
            reply.starred = True
        elif action == 'unstar':
            reply.starred = False
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'{len(replies)} replies updated'
    })


# ==================== INSIGHTS API ====================

@reply_bp.route('/api/insights')
@login_required
def api_insights():
    """Get reply insights/analytics"""
    from app.models.replies import EmailReply, ReplyAnalytics
    from app import db
    from sqlalchemy import func
    
    org_id = get_organization_id()
    days = request.args.get('days', 30, type=int)
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total counts
    total_replies = EmailReply.query.filter(
        EmailReply.organization_id == org_id,
        EmailReply.received_at >= start_date
    ).count()
    
    # Sentiment breakdown
    sentiment_counts = db.session.query(
        EmailReply.sentiment,
        func.count(EmailReply.id)
    ).filter(
        EmailReply.organization_id == org_id,
        EmailReply.received_at >= start_date,
        EmailReply.sentiment.isnot(None)
    ).group_by(EmailReply.sentiment).all()
    
    # Intent breakdown
    intent_counts = db.session.query(
        EmailReply.intent,
        func.count(EmailReply.id)
    ).filter(
        EmailReply.organization_id == org_id,
        EmailReply.received_at >= start_date,
        EmailReply.intent.isnot(None)
    ).group_by(EmailReply.intent).all()
    
    # Daily reply trend
    daily_trend = db.session.query(
        func.date(EmailReply.received_at).label('date'),
        func.count(EmailReply.id).label('count')
    ).filter(
        EmailReply.organization_id == org_id,
        EmailReply.received_at >= start_date
    ).group_by(func.date(EmailReply.received_at)).all()
    
    # Average response time
    avg_response = db.session.query(
        func.avg(EmailReply.reply_time_seconds)
    ).filter(
        EmailReply.organization_id == org_id,
        EmailReply.replied_at.isnot(None),
        EmailReply.received_at >= start_date
    ).scalar() or 0
    
    # Response rate
    replied_count = EmailReply.query.filter(
        EmailReply.organization_id == org_id,
        EmailReply.status == 'replied',
        EmailReply.received_at >= start_date
    ).count()
    
    response_rate = (replied_count / total_replies * 100) if total_replies > 0 else 0
    
    # Top topics
    all_topics = []
    replies_with_topics = EmailReply.query.filter(
        EmailReply.organization_id == org_id,
        EmailReply.topics.isnot(None),
        EmailReply.received_at >= start_date
    ).all()
    
    for reply in replies_with_topics:
        all_topics.extend(reply.topics_list)
    
    topic_counts = {}
    for topic in all_topics:
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    
    top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return jsonify({
        'success': True,
        'insights': {
            'total_replies': total_replies,
            'sentiment_breakdown': {s: c for s, c in sentiment_counts},
            'intent_breakdown': {i: c for i, c in intent_counts},
            'daily_trend': [{'date': str(d.date), 'count': d.count} for d in daily_trend],
            'avg_response_time_seconds': avg_response,
            'avg_response_time_formatted': format_duration(avg_response),
            'response_rate': round(response_rate, 1),
            'replied_count': replied_count,
            'top_topics': [{'topic': t, 'count': c} for t, c in top_topics]
        }
    })


# ==================== TEMPLATES API ====================

@reply_bp.route('/api/templates/list')
@login_required
def api_templates_list():
    """Get reply templates"""
    from app.models.replies import ReplyTemplate
    
    org_id = get_organization_id()
    category = request.args.get('category')
    
    query = ReplyTemplate.query.filter_by(organization_id=org_id, is_active=True)
    if category:
        query = query.filter_by(category=category)
    
    templates = query.order_by(ReplyTemplate.usage_count.desc()).all()
    
    return jsonify({
        'success': True,
        'templates': [t.to_dict() for t in templates]
    })


@reply_bp.route('/api/templates', methods=['POST'])
@login_required
def api_templates_create():
    """Create reply template"""
    from app.models.replies import ReplyTemplate
    from app import db
    
    data = request.get_json()
    
    template = ReplyTemplate(
        id=str(uuid.uuid4()),
        organization_id=get_organization_id(),
        name=data.get('name', 'Untitled Template'),
        subject=data.get('subject'),
        body=data.get('body', ''),
        category=data.get('category'),
        tags=data.get('tags'),
        auto_suggest=data.get('auto_suggest', False),
        trigger_keywords=json.dumps(data.get('trigger_keywords', [])),
        trigger_intents=json.dumps(data.get('trigger_intents', [])),
        created_by=session.get('user_id')
    )
    
    db.session.add(template)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'template': template.to_dict()
    })


@reply_bp.route('/api/templates/<template_id>', methods=['PUT'])
@login_required
def api_templates_update(template_id):
    """Update reply template"""
    from app.models.replies import ReplyTemplate
    from app import db
    
    template = ReplyTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        template.name = data['name']
    if 'subject' in data:
        template.subject = data['subject']
    if 'body' in data:
        template.body = data['body']
    if 'category' in data:
        template.category = data['category']
    if 'tags' in data:
        template.tags = data['tags']
    if 'auto_suggest' in data:
        template.auto_suggest = data['auto_suggest']
    if 'trigger_keywords' in data:
        template.trigger_keywords = json.dumps(data['trigger_keywords'])
    if 'trigger_intents' in data:
        template.trigger_intents = json.dumps(data['trigger_intents'])
    
    template.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'template': template.to_dict()
    })


@reply_bp.route('/api/templates/<template_id>', methods=['DELETE'])
@login_required
def api_templates_delete(template_id):
    """Delete reply template"""
    from app.models.replies import ReplyTemplate
    from app import db
    
    template = ReplyTemplate.query.filter_by(id=template_id, organization_id=get_organization_id()).first()
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    db.session.delete(template)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Template deleted'
    })


@reply_bp.route('/api/suggest-templates', methods=['POST'])
@login_required
def api_suggest_templates():
    """Get suggested templates for a reply"""
    from app.models.replies import ReplyTemplate
    
    data = request.get_json()
    intent = data.get('intent')
    keywords = data.get('keywords', [])
    
    org_id = get_organization_id()
    
    # Find templates that match intent or keywords
    templates = ReplyTemplate.query.filter_by(
        organization_id=org_id,
        is_active=True,
        auto_suggest=True
    ).all()
    
    suggestions = []
    for template in templates:
        score = 0
        
        # Check intent match
        trigger_intents = json.loads(template.trigger_intents) if template.trigger_intents else []
        if intent and intent in trigger_intents:
            score += 10
        
        # Check keyword matches
        trigger_keywords = json.loads(template.trigger_keywords) if template.trigger_keywords else []
        for keyword in keywords:
            if keyword.lower() in [k.lower() for k in trigger_keywords]:
                score += 5
        
        if score > 0:
            suggestions.append({
                'template': template.to_dict(),
                'score': score
            })
    
    # Sort by score
    suggestions.sort(key=lambda x: x['score'], reverse=True)
    
    return jsonify({
        'success': True,
        'suggestions': suggestions[:5]
    })


# ==================== AI ANALYSIS ENGINE ====================

def analyze_email_content(body, subject=''):
    """Analyze email content using AI/NLP"""
    # This is a rule-based implementation
    # For production, integrate with OpenAI, Claude, or other AI services
    
    text = f"{subject} {body}".lower()
    
    # Sentiment analysis (simple rule-based)
    positive_words = ['thank', 'thanks', 'great', 'excellent', 'amazing', 'love', 'appreciate', 'wonderful', 'happy', 'pleased']
    negative_words = ['problem', 'issue', 'frustrated', 'disappointed', 'angry', 'terrible', 'worst', 'hate', 'upset', 'complaint']
    
    positive_count = sum(1 for word in positive_words if word in text)
    negative_count = sum(1 for word in negative_words if word in text)
    
    if positive_count > negative_count:
        sentiment = 'positive'
        sentiment_score = min(positive_count / 5, 1.0)
    elif negative_count > positive_count:
        sentiment = 'negative'
        sentiment_score = max(-negative_count / 5, -1.0)
    else:
        sentiment = 'neutral'
        sentiment_score = 0.0
    
    # Intent detection
    intent = 'other'
    if any(word in text for word in ['question', 'how', 'what', 'when', 'where', 'why', 'can you', 'could you', '?']):
        intent = 'inquiry'
    elif any(word in text for word in ['problem', 'issue', 'not working', 'broken', 'bug', 'error']):
        intent = 'complaint'
    elif any(word in text for word in ['feedback', 'suggestion', 'idea', 'recommend']):
        intent = 'feedback'
    elif any(word in text for word in ['buy', 'purchase', 'price', 'cost', 'interested in buying', 'want to order']):
        intent = 'purchase_intent'
    elif any(word in text for word in ['unsubscribe', 'remove me', 'stop sending', 'opt out']):
        intent = 'unsubscribe'
    elif any(word in text for word in ['thank you', 'thanks', 'appreciate']):
        intent = 'thank_you'
    elif any(word in text for word in ['help', 'support', 'assist', 'need help']):
        intent = 'support'
    
    # Urgency detection
    urgency = 'low'
    if any(word in text for word in ['urgent', 'asap', 'immediately', 'emergency', 'critical']):
        urgency = 'critical'
    elif any(word in text for word in ['soon', 'quickly', 'fast', 'priority']):
        urgency = 'high'
    elif any(word in text for word in ['when you can', 'at your convenience']):
        urgency = 'medium'
    
    # Topic extraction (simple keyword extraction)
    topics = []
    topic_patterns = [
        ('billing', ['invoice', 'payment', 'charge', 'refund', 'subscription', 'billing']),
        ('shipping', ['shipping', 'delivery', 'tracking', 'package', 'order']),
        ('technical', ['error', 'bug', 'not working', 'crash', 'technical']),
        ('account', ['account', 'login', 'password', 'profile', 'settings']),
        ('product', ['product', 'feature', 'functionality', 'service']),
        ('pricing', ['price', 'cost', 'discount', 'promotion', 'deal'])
    ]
    
    for topic, keywords in topic_patterns:
        if any(keyword in text for keyword in keywords):
            topics.append(topic)
    
    # Key phrase extraction (simple)
    key_phrases = []
    sentences = re.split(r'[.!?]', body)
    for sentence in sentences[:3]:
        sentence = sentence.strip()
        if len(sentence) > 20 and len(sentence) < 100:
            key_phrases.append(sentence)
    
    # Auto-reply detection
    is_auto_reply = any(phrase in text for phrase in [
        'auto-reply', 'automatic reply', 'out of office', 'do not reply',
        'this is an automated', 'auto response', 'automated message'
    ])
    
    is_out_of_office = any(phrase in text for phrase in [
        'out of office', 'on vacation', 'away from', 'limited access',
        'return on', 'back in the office'
    ])
    
    # Generate suggested response
    suggested_response = generate_suggested_response(intent, sentiment, topics)
    
    # Generate summary
    summary = f"{'Positive' if sentiment == 'positive' else 'Negative' if sentiment == 'negative' else 'Neutral'} {intent.replace('_', ' ')} "
    if topics:
        summary += f"about {', '.join(topics[:2])}"
    if urgency in ['high', 'critical']:
        summary += f" (Urgency: {urgency})"
    
    return {
        'sentiment': sentiment,
        'sentiment_score': sentiment_score,
        'intent': intent,
        'urgency': urgency,
        'topics': topics,
        'key_phrases': key_phrases[:5],
        'suggested_response': suggested_response,
        'summary': summary.strip(),
        'is_auto_reply': is_auto_reply,
        'is_out_of_office': is_out_of_office
    }


def generate_suggested_response(intent, sentiment, topics):
    """Generate a suggested response based on analysis"""
    responses = {
        'inquiry': "Thank you for reaching out! I'd be happy to help answer your question. ",
        'complaint': "I'm sorry to hear about this issue. Let me look into this for you right away. ",
        'feedback': "Thank you for your valuable feedback! We really appreciate you taking the time to share your thoughts. ",
        'purchase_intent': "Thank you for your interest! I'd be happy to help you with your purchase. ",
        'support': "Thank you for contacting support. I'm here to help resolve this for you. ",
        'thank_you': "You're very welcome! We're always happy to help. ",
        'unsubscribe': "I've processed your unsubscribe request. You will no longer receive emails from us. ",
        'other': "Thank you for your email. "
    }
    
    return responses.get(intent, responses['other'])


def send_reply_email(reply, subject, body):
    """Send reply email via SMTP"""
    # Implement using your SMTP server
    # This would integrate with your existing email sending infrastructure
    try:
        # Example implementation:
        # from app.smtp.relay_server import send_email_sync
        # send_email_sync(to=reply.from_email, subject=subject, body=body)
        return True
    except:
        return False


def track_template_usage(template_id):
    """Track template usage"""
    from app.models.replies import ReplyTemplate
    from app import db
    
    template = ReplyTemplate.query.get(template_id)
    if template:
        template.usage_count += 1
        db.session.commit()


def format_duration(seconds):
    """Format duration in seconds to human readable"""
    if not seconds:
        return 'N/A'
    
    if seconds < 60:
        return f'{int(seconds)}s'
    elif seconds < 3600:
        return f'{int(seconds / 60)}m'
    elif seconds < 86400:
        return f'{int(seconds / 3600)}h {int((seconds % 3600) / 60)}m'
    else:
        return f'{int(seconds / 86400)}d {int((seconds % 86400) / 3600)}h'


# ==================== INCOMING EMAIL HANDLER ====================

def process_incoming_email(raw_email, organization_id):
    """Process incoming email and store as reply"""
    from app.models.replies import EmailReply
    from app import db
    import email
    from email import policy
    
    # Parse email
    msg = email.message_from_bytes(raw_email, policy=policy.default)
    
    # Extract fields
    from_email = msg.get('From', '')
    from_name = ''
    if '<' in from_email:
        from_name = from_email.split('<')[0].strip().strip('"')
        from_email = from_email.split('<')[1].rstrip('>')
    
    subject = msg.get('Subject', '')
    message_id = msg.get('Message-ID', '')
    in_reply_to = msg.get('In-Reply-To', '')
    references = msg.get('References', '')
    
    # Get body
    body_text = ''
    body_html = ''
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            elif content_type == 'text/html':
                body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        if content_type == 'text/html':
            body_html = payload
        else:
            body_text = payload
    
    # Check for attachments
    attachments = []
    has_attachments = False
    
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == 'attachment':
                has_attachments = True
                attachments.append({
                    'filename': part.get_filename(),
                    'content_type': part.get_content_type(),
                    'size': len(part.get_payload(decode=True) or b'')
                })
    
    # Create reply record
    reply = EmailReply(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        from_email=from_email,
        from_name=from_name,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=references,
        has_attachments=has_attachments,
        attachment_count=len(attachments),
        attachments=json.dumps(attachments) if attachments else None,
        status='unread'
    )
    
    # Try to link to original email/campaign
    if in_reply_to:
        # Find original email by message ID
        # reply.original_email_id = ...
        pass
    
    # Try to link to contact
    # contact = Contact.query.filter_by(email=from_email, organization_id=organization_id).first()
    # if contact:
    #     reply.contact_id = contact.id
    
    db.session.add(reply)
    db.session.commit()
    
    # Run AI analysis
    analysis = analyze_email_content(body_text or body_html, subject)
    
    reply.sentiment = analysis['sentiment']
    reply.sentiment_score = analysis['sentiment_score']
    reply.intent = analysis['intent']
    reply.urgency = analysis['urgency']
    reply.topics = json.dumps(analysis['topics'])
    reply.key_phrases = json.dumps(analysis['key_phrases'])
    reply.suggested_response = analysis['suggested_response']
    reply.ai_summary = analysis['summary']
    reply.is_auto_reply = analysis['is_auto_reply']
    reply.is_out_of_office = analysis['is_out_of_office']
    
    # Auto-categorize
    if analysis['is_auto_reply'] or analysis['is_out_of_office']:
        reply.category = 'other'
    elif analysis['intent'] == 'support':
        reply.category = 'support'
    elif analysis['intent'] == 'purchase_intent':
        reply.category = 'sales'
    elif 'billing' in analysis['topics']:
        reply.category = 'billing'
    elif analysis['intent'] == 'feedback':
        reply.category = 'feedback'
    
    db.session.commit()
    
    return reply
