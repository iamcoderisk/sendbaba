
@analytics_bp.route('/worker-capacity', methods=['GET'])
def get_worker_capacity():
    """Get real-time worker capacity"""
    from app.tasks.distributed_sender import get_capacity_report
    report = get_capacity_report()
    return jsonify(report)

@analytics_bp.route('/update-warmup/<ip>', methods=['POST'])
def update_warmup_limit(ip):
    """Update daily limit for a warming IP"""
    from app.tasks.distributed_sender import WORKER_IPS
    data = request.get_json()
    new_limit = data.get('daily_limit')
    
    if ip in WORKER_IPS and new_limit:
        WORKER_IPS[ip]['daily_limit'] = int(new_limit)
        return jsonify({'success': True, 'ip': ip, 'new_limit': new_limit})
    return jsonify({'success': False, 'error': 'Invalid IP or limit'}), 400
