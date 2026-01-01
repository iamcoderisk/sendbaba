"""
Worker Management API for Admin Hub
"""
from flask import Blueprint, request, jsonify
from app.tasks.worker_manager import (
    get_all_workers,
    get_worker_by_ip,
    get_total_capacity,
    update_worker_limit,
    update_worker_status,
    advance_warmup_stage,
    get_warmup_schedule,
    update_warmup_schedule,
    get_daily_report,
    register_worker
)

workers_bp = Blueprint('workers', __name__, url_prefix='/api/workers')

@workers_bp.route('/', methods=['GET'])
def list_workers():
    """List all workers with current status"""
    workers = get_all_workers()
    capacity = get_total_capacity()
    return jsonify({
        'success': True,
        'workers': workers,
        'capacity': capacity
    })

@workers_bp.route('/capacity', methods=['GET'])
def get_capacity():
    """Get total system capacity"""
    capacity = get_total_capacity()
    return jsonify({
        'success': True,
        **capacity
    })

@workers_bp.route('/<ip>', methods=['GET'])
def get_worker(ip):
    """Get single worker details"""
    worker = get_worker_by_ip(ip)
    if not worker:
        return jsonify({'success': False, 'error': 'Worker not found'}), 404
    return jsonify({'success': True, 'worker': worker})

@workers_bp.route('/<ip>/limit', methods=['PUT'])
def set_worker_limit(ip):
    """Update worker daily limit"""
    data = request.get_json()
    new_limit = data.get('daily_limit')
    if not new_limit:
        return jsonify({'success': False, 'error': 'daily_limit required'}), 400
    update_worker_limit(ip, int(new_limit))
    return jsonify({'success': True, 'ip': ip, 'daily_limit': new_limit})

@workers_bp.route('/<ip>/status', methods=['PUT'])
def set_worker_status(ip):
    """Update worker status"""
    data = request.get_json()
    status = data.get('status')
    if status not in ['active', 'warming', 'paused', 'disabled']:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400
    update_worker_status(ip, status)
    return jsonify({'success': True, 'ip': ip, 'status': status})

@workers_bp.route('/<ip>/advance', methods=['POST'])
def advance_worker(ip):
    """Manually advance warmup stage"""
    result = advance_warmup_stage(ip)
    if result:
        return jsonify({
            'success': True, 
            'ip': ip, 
            'new_stage': result[0],
            'new_limit': result[1],
            'status': result[2]
        })
    return jsonify({'success': False, 'error': 'Failed to advance'}), 400

@workers_bp.route('/schedule', methods=['GET'])
def get_schedule():
    """Get warmup schedule"""
    schedule = get_warmup_schedule()
    return jsonify({'success': True, 'schedule': schedule})

@workers_bp.route('/schedule/<int:stage>', methods=['PUT'])
def update_schedule(stage):
    """Update warmup schedule stage"""
    data = request.get_json()
    update_warmup_schedule(
        stage,
        daily_limit=data.get('daily_limit'),
        min_success_rate=data.get('min_success_rate'),
        min_days=data.get('min_days_at_stage')
    )
    return jsonify({'success': True, 'stage': stage})

@workers_bp.route('/report/daily', methods=['GET'])
def daily_report():
    """Get daily sending report"""
    report = get_daily_report()
    return jsonify({'success': True, 'report': report})

@workers_bp.route('/register', methods=['POST'])
def register_new_worker():
    """Register a new worker IP"""
    data = request.get_json()
    ip = data.get('ip_address')
    hostname = data.get('hostname')
    if not ip:
        return jsonify({'success': False, 'error': 'ip_address required'}), 400
    register_worker(ip, hostname)
    return jsonify({'success': True, 'ip': ip})
