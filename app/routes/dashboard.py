"""Dashboard routes and views"""
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.services.dashboard import DashboardService
from app.config.config_manager import ConfigManager
from app.models.user import User, UserPreferences, NotificationSettings, UserNotification
from app.models.arbitrage import ArbitrageOpportunity
from app.utils.coingecko import get_supported_exchanges, get_supported_assets
from app.services.notification_service import NotificationManager
from app.database import db

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')
config_manager = ConfigManager()
dashboard_service = DashboardService(config_manager)

@bp.route('/')
@login_required
def index():
    """Render the main dashboard page"""
    return render_template('dashboard/index.html')

@bp.route('/configure')
@login_required
def configure():
    """Settings configuration view"""
    # Get or create user preferences
    user_preferences = UserPreferences.query.filter_by(user_id=current_user.id).first()
    if not user_preferences:
        user_preferences = UserPreferences(user_id=current_user.id)
        db.session.add(user_preferences)
        db.session.commit()
    
    # Get exchange and asset data
    exchanges = get_supported_exchanges()
    assets = get_supported_assets()
    
    return render_template('dashboard/configure.html',
                         user_preferences=user_preferences,
                         exchanges=exchanges,
                         assets=assets)

@bp.route('/save-settings', methods=['POST'])
@login_required
def save_settings():
    """Save user preferences"""
    try:
        # Get or create user preferences
        preferences = UserPreferences.query.filter_by(user_id=current_user.id).first()
        if not preferences:
            preferences = UserPreferences(user_id=current_user.id)
            db.session.add(preferences)
        
        # Update preferences
        preferences.preferred_exchanges = request.form.getlist('exchanges')
        preferences.preferred_assets = request.form.getlist('assets')
        preferences.min_profit_percent = float(request.form.get('min_profit_percent', 0.5))
        preferences.include_slippage = 'include_slippage' in request.form
        preferences.include_fees = 'include_fees' in request.form
        
        # Update configuration status
        if preferences.has_valid_configuration():
            preferences.is_configuration_active = True
            preferences.configuration_started_at = datetime.utcnow()
        
        db.session.commit()
        flash('Settings saved successfully! Your arbitrage scanner is now active.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving settings: {str(e)}', 'error')
    
    return redirect(url_for('dashboard.configure'))

@bp.route('/data')
@login_required
def get_dashboard_data():
    """Get all dashboard data for the current user"""
    try:
        user = User.query.get(current_user.id)  # Get actual User instance
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        data = dashboard_service.get_user_dashboard_data(user)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/notification')
@login_required
def notification():
    """Render the notification settings page"""
    return render_template('dashboard/notification.html')

@bp.route('/notification-settings', methods=['GET'])
@login_required
def get_notification_settings():
    """Get user notification settings"""
    try:
        # Get or create notification settings
        settings = NotificationSettings.query.filter_by(user_id=current_user.id).first()
        if not settings:
            settings = NotificationSettings(user_id=current_user.id)
            db.session.add(settings)
            db.session.commit()
        
        return jsonify({
            'success': True,
            'settings': {
                'in_app_enabled': settings.in_app_enabled,
                'email_enabled': settings.email_enabled,
                'telegram_enabled': settings.telegram_enabled,
                'email_address': current_user.email,
                'telegram_username': settings.telegram_username,
                'telegram_chat_id': settings.telegram_chat_id,
                'arbitrage_notifications': settings.arbitrage_notifications,
                'price_alert_notifications': settings.price_alert_notifications,
                'system_notifications': settings.system_notifications,
                'scanner_status_notifications': settings.scanner_status_notifications,
                'min_profit_threshold': float(settings.min_profit_threshold),
                'max_notifications_per_hour': settings.max_notifications_per_hour,
                'notification_frequency': 'immediate',  # Default value
                'quiet_hours_start': settings.quiet_hours_start.strftime('%H:%M') if settings.quiet_hours_start else None,
                'quiet_hours_end': settings.quiet_hours_end.strftime('%H:%M') if settings.quiet_hours_end else None
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error loading notification settings: {str(e)}'
        }), 500

@bp.route('/notification-settings', methods=['POST'])
@login_required
def save_notification_settings():
    """Save user notification settings"""
    try:
        data = request.get_json()
        
        # Get or create notification settings
        settings = NotificationSettings.query.filter_by(user_id=current_user.id).first()
        if not settings:
            settings = NotificationSettings(user_id=current_user.id)
            db.session.add(settings)
        
        # Update settings
        settings.in_app_enabled = data.get('in_app_enabled', False)
        settings.email_enabled = data.get('email_enabled', False)
        settings.telegram_enabled = data.get('telegram_enabled', False)
        settings.whatsapp_enabled = data.get('whatsapp_enabled', False)
        settings.telegram_username = data.get('telegram_username', '')
        settings.telegram_chat_id = data.get('telegram_chat_id', '')
        settings.whatsapp_username = data.get('whatsapp_username', '')
        settings.whatsapp_number = data.get('whatsapp_number', '')
        settings.arbitrage_notifications = data.get('arbitrage_notifications', True)
        settings.price_alert_notifications = data.get('price_alert_notifications', True)
        settings.system_notifications = data.get('system_notifications', True)
        settings.scanner_status_notifications = data.get('scanner_status_notifications', True)
        settings.min_profit_threshold = data.get('min_profit_threshold', 0.5)
        settings.max_notifications_per_hour = data.get('max_notifications_per_hour', 10)
        
        # Handle quiet hours
        if data.get('quiet_hours_enabled') and data.get('quiet_hours_start') and data.get('quiet_hours_end'):
            from datetime import time
            start_time = datetime.strptime(data['quiet_hours_start'], '%H:%M').time()
            end_time = datetime.strptime(data['quiet_hours_end'], '%H:%M').time()
            settings.quiet_hours_start = start_time
            settings.quiet_hours_end = end_time
        else:
            settings.quiet_hours_start = None
            settings.quiet_hours_end = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification settings saved successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error saving notification settings: {str(e)}'
        }), 500

@bp.route('/test-notifications', methods=['POST'])
@login_required
def test_notifications():
    """Send test notifications to all enabled channels"""
    try:
        # Get or create notification settings for user
        settings = NotificationSettings.query.filter_by(user_id=current_user.id).first()
        if not settings:
            settings = NotificationSettings(user_id=current_user.id)
            db.session.add(settings)
            db.session.commit()
        
        notification_manager = NotificationManager()
        
        # Create test notification data with high profit to bypass threshold
        test_data = {
            'asset': 'BTC',
            'buy_exchange': 'Binance',
            'sell_exchange': 'Coinbase',
            'profit_percentage': 5.0,  # High profit to ensure it passes threshold
            'profit_percent': 5.0,     # Alternative key name
            'profit_amount': 250.00
        }
        
        results = notification_manager.send_notification(
            user_id=current_user.id,
            notification_type='arbitrage_opportunity',
            title='🧪 Test Notification',
            message='This is a test notification to verify your settings are working correctly. If you received this, your notification system is functioning properly!',
            data=test_data
        )
        
        # Check if any notifications were sent
        if results and any(results.values()):
            sent_channels = [channel for channel, success in results.items() if success]
            return jsonify({
                'success': True,
                'message': f'Test notifications sent successfully via: {", ".join(sent_channels)}'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No notifications were sent. Please check your notification settings and ensure at least one channel is enabled.'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error sending test notifications: {str(e)}'
        }), 500

@bp.route('/verify-telegram', methods=['POST'])
@login_required
def verify_telegram():
    """Verify Telegram connection"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        
        if not chat_id:
            return jsonify({
                'success': False,
                'message': 'Chat ID is required'
            }), 400
        
        notification_manager = NotificationManager()
        telegram_service = notification_manager.telegram_service
        
        # Send verification message
        success = telegram_service.send_message(
            chat_id=chat_id,
            message='🎉 Telegram connection verified successfully! You will now receive arbitrage alerts here.'
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Telegram connection verified successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to verify Telegram connection. Please check your Chat ID.'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error verifying Telegram: {str(e)}'
        }), 500

@bp.route('/verify-whatsapp', methods=['POST'])
@login_required
def verify_whatsapp():
    """Verify WhatsApp connection"""
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({
                'success': False,
                'message': 'Phone number is required'
            }), 400
        
        notification_manager = NotificationManager()
        whatsapp_service = notification_manager.whatsapp_service
        
        # Send verification message
        success = whatsapp_service.verify_whatsapp_number(phone_number)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'WhatsApp connection verified successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to verify WhatsApp connection. Please check your phone number and ensure WhatsApp is active.'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error verifying WhatsApp: {str(e)}'
        }), 500

@bp.route('/notification-history', methods=['GET', 'POST'])
@login_required
def get_notification_history():
    """Get user notification history or mark notifications as read"""
    try:
        if request.method == 'GET':
            limit = request.args.get('limit', 50, type=int)
            notifications = UserNotification.query.filter_by(
                user_id=current_user.id
            ).order_by(UserNotification.created_at.desc()).limit(limit).all()
            
            notification_list = [{
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'channel': notification.channel,
                'status': notification.status,
                'created_at': notification.created_at.isoformat(),
                'read_at': notification.read_at.isoformat() if notification.read_at else None
            } for notification in notifications]
            
            return jsonify({
                'success': True,
                'notifications': notification_list
            })
        
        elif request.method == 'POST':
            data = request.get_json()
            action = data.get('action')
            
            if action == 'mark_read':
                notification_id = data.get('notification_id')
                notification = UserNotification.query.filter_by(
                    id=notification_id,
                    user_id=current_user.id
                ).first()
                
                if notification:
                    notification.read_at = datetime.utcnow()
                    db.session.commit()
                    return jsonify({'success': True})
                else:
                    return jsonify({'success': False, 'message': 'Notification not found'}), 404
            
            elif action == 'mark_all_read':
                UserNotification.query.filter_by(
                    user_id=current_user.id,
                    read_at=None
                ).update({'read_at': datetime.utcnow()})
                db.session.commit()
                return jsonify({'success': True})
            
            else:
                return jsonify({'success': False, 'message': 'Invalid action'}), 400
                
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error loading notification history: {str(e)}'
        }), 500

@bp.route('/clear-notification-history', methods=['POST'])
@login_required
def clear_notification_history():
    """Clear user notification history"""
    try:
        UserNotification.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification history cleared successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error clearing notification history: {str(e)}'
        }), 500

@bp.route('/opportunities')
@login_required
def opportunities():
    """Display arbitrage opportunities for the current user"""
    try:
        # Get user preferences to filter opportunities
        user_preferences = UserPreferences.query.filter_by(user_id=current_user.id).first()
        
        # Query opportunities - filter by user's preferred assets if configured
        query = ArbitrageOpportunity.query.filter_by(is_active=True)
        
        if user_preferences and user_preferences.preferred_assets:
            query = query.filter(ArbitrageOpportunity.token_symbol.in_(user_preferences.preferred_assets))
        
        if user_preferences and user_preferences.preferred_exchanges:
            query = query.filter(
                db.or_(
                    ArbitrageOpportunity.buy_exchange.in_(user_preferences.preferred_exchanges),
                    ArbitrageOpportunity.sell_exchange.in_(user_preferences.preferred_exchanges)
                )
            )
        
        # Order by net profit percent descending and limit to recent opportunities
        opportunities = query.order_by(ArbitrageOpportunity.net_profit_percent.desc(), 
                                     ArbitrageOpportunity.timestamp.desc()).limit(100).all()
        
        return render_template('dashboard/opportunities.html', 
                             opportunities=opportunities,
                             user_preferences=user_preferences)
    
    except Exception as e:
        flash(f'Error loading opportunities: {str(e)}', 'error')
        return render_template('dashboard/opportunities.html', 
                             opportunities=[],
                             user_preferences=None)

@bp.route('/refresh')
@login_required
def refresh_dashboard():
    """Force refresh the dashboard data"""
    try:
        # Force a new scan if needed
        # scanner_service.scan_now()  # TODO: Implement this
        
        user = User.query.get(current_user.id)  # Get actual User instance
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        data = dashboard_service.get_user_dashboard_data(user)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500