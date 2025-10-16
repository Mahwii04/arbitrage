"""Main routes for the application"""
from flask import Blueprint, redirect, url_for, jsonify
from flask_login import current_user
from app import db

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """Redirect to login if not authenticated, otherwise to dashboard"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))

@bp.route('/health')
def health_check():
    """Health check endpoint for Docker monitoring"""
    try:
        # Check database connection
        db.session.execute('SELECT 1')
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'service': 'arbitrage-bot'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'service': 'arbitrage-bot'
        }), 503