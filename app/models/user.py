"""User and subscription related models"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from time import time
import jwt
from flask import current_app
from app import db, login_manager
from .base import TimestampMixin, JsonMixin

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin, TimestampMixin, JsonMixin):
    """User model for authentication and profile information"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    _is_active = db.Column('is_active', db.Boolean, default=True)
    subscription_tier = db.Column(db.String(20), nullable=False, default='free')
    
    @property
    def is_active(self):
        """Return whether the user is active"""
        return self._is_active
    
    @is_active.setter
    def is_active(self, value):
        """Set whether the user is active"""
        self._is_active = value
    
    # User preferences
    preferences = db.relationship('UserPreferences', backref='user', uselist=False, cascade='all, delete-orphan')
    # Notification settings
    notification_settings = db.relationship('NotificationSettings', backref='user', uselist=False, cascade='all, delete-orphan')
    # Scan history
    scan_history = db.relationship('ScanHistory', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        """Set hashed password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert user to dictionary, excluding sensitive data"""
        data = super().to_dict()
        data.pop('password_hash', None)
        return data
        
    def get_reset_password_token(self, expires_in=600):
        """Generate password reset token valid for 10 minutes"""
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'],
            algorithm='HS256'
        )
    
    @staticmethod
    def verify_reset_password_token(token):
        """Verify password reset token"""
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'],
                          algorithms=['HS256'])['reset_password']
        except:
            return None
        return User.query.get(id)

class UserPreferences(db.Model, TimestampMixin, JsonMixin):
    """User preferences for arbitrage notifications"""
    __tablename__ = 'user_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Minimum profit percentage to trigger notification
    min_profit_percent = db.Column(db.Float, nullable=False, default=0.5)
    
    # Preferred exchanges and assets (stored as JSON)
    preferred_exchanges = db.Column(db.JSON, nullable=False, default=lambda: [])
    preferred_assets = db.Column(db.JSON, nullable=False, default=lambda: [])
    
    # Additional preferences
    include_slippage = db.Column(db.Boolean, default=True)
    include_fees = db.Column(db.Boolean, default=True)
    
    # Configuration status tracking
    is_configuration_active = db.Column(db.Boolean, default=False)
    configuration_started_at = db.Column(db.DateTime)
    
    def __init__(self, user_id=None, min_profit_percent=0.5):
        self.user_id = user_id
        self.min_profit_percent = min_profit_percent
        self.preferred_exchanges = []
        self.preferred_assets = []
        self.is_configuration_active = False
    
    def has_valid_configuration(self):
        """Check if user has a valid configuration setup"""
        return (len(self.preferred_exchanges) >= 2 and 
                len(self.preferred_assets) >= 1 and 
                self.min_profit_percent >= 0.5)

class NotificationSettings(db.Model, TimestampMixin, JsonMixin):
    """User notification settings"""
    __tablename__ = 'notification_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Channel preferences
    in_app_enabled = db.Column(db.Boolean, default=True)
    email_enabled = db.Column(db.Boolean, default=False)
    telegram_enabled = db.Column(db.Boolean, default=False)
    whatsapp_enabled = db.Column(db.Boolean, default=False)
    
    # Contact information
    email_address = db.Column(db.String(120))
    telegram_chat_id = db.Column(db.String(100))
    telegram_username = db.Column(db.String(100))
    whatsapp_number = db.Column(db.String(20))
    whatsapp_username = db.Column(db.String(100))
    
    # Notification type preferences
    arbitrage_notifications = db.Column(db.Boolean, default=True)
    price_alert_notifications = db.Column(db.Boolean, default=True)
    system_notifications = db.Column(db.Boolean, default=True)
    scanner_status_notifications = db.Column(db.Boolean, default=True)
    
    # Frequency and threshold settings
    min_profit_threshold = db.Column(db.Float, default=0.5)  # Minimum profit % to notify
    max_notifications_per_hour = db.Column(db.Integer, default=10)
    notification_frequency = db.Column(db.String(20), default='immediate')  # immediate, hourly, daily
    quiet_hours_start = db.Column(db.Time)
    quiet_hours_end = db.Column(db.Time)
    
    def __init__(self, user_id=None):
        if user_id:
            self.user_id = user_id
    
    def get_enabled_channels(self):
        """Get list of enabled notification channels"""
        channels = []
        if self.in_app_enabled:
            channels.append('in_app')
        if self.email_enabled and self.email_address:
            channels.append('email')
        if self.telegram_enabled and self.telegram_chat_id:
            channels.append('telegram')
        if self.whatsapp_enabled and self.whatsapp_number:
            channels.append('whatsapp')
        return channels
    
    def should_send_notification(self, notification_type, profit_percent=None):
        """Check if notification should be sent based on preferences"""
        # Check if notification type is enabled
        type_mapping = {
            'arbitrage': self.arbitrage_notifications,
            'arbitrage_opportunity': self.arbitrage_notifications,
            'price_alert': self.price_alert_notifications,
            'system_update': self.system_notifications,
            'scanner_status': self.scanner_status_notifications
        }
        
        if not type_mapping.get(notification_type, False):
            return False
        
        # Check profit threshold for arbitrage opportunities
        if (notification_type in ['arbitrage_opportunity', 'arbitrage'] and 
            profit_percent is not None and 
            profit_percent < self.min_profit_threshold):
            return False
        
        return True

class ScanHistory(db.Model, TimestampMixin):
    """Track user's arbitrage scan history"""
    __tablename__ = 'scan_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scan_type = db.Column(db.String(20), nullable=False)  # manual, scheduled
    tokens_scanned = db.Column(db.Integer, nullable=False)
    exchanges_scanned = db.Column(db.Integer, nullable=False)
    opportunities_found = db.Column(db.Integer, nullable=False)
    scan_duration = db.Column(db.Float, nullable=False)  # in seconds

class UserNotification(db.Model, TimestampMixin):
    """User notification history"""
    __tablename__ = 'user_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    opportunity_id = db.Column(db.Integer, db.ForeignKey('arbitrage_opportunities.id'), nullable=True)
    
    notification_type = db.Column(db.String(50), nullable=False)  # arbitrage_opportunity, price_alert, etc.
    channel = db.Column(db.String(20), nullable=False)  # in_app, email, telegram
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    data = db.Column(db.JSON)  # Additional data
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, sent, failed, read
    sent_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    
    # Relationships
    user = db.relationship('User', backref='user_notifications')
    opportunity = db.relationship('ArbitrageOpportunity', backref='notifications')
    
    def mark_as_sent(self):
        """Mark notification as sent"""
        self.status = 'sent'
        self.sent_at = datetime.utcnow()
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.status = 'read'
        self.read_at = datetime.utcnow()
    
    def mark_as_failed(self, error_msg=None):
        """Mark notification as failed"""
        self.status = 'failed'
        if error_msg:
            self.error_message = error_msg
    
    def to_dict(self):
        """Convert notification to dictionary"""
        return {
            'id': self.id,
            'notification_type': self.notification_type,
            'channel': self.channel,
            'title': self.title,
            'message': self.message,
            'data': self.data,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None
        }