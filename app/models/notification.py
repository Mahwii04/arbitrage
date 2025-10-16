"""Models for notification system"""
from datetime import datetime
from app.database import db
from enum import Enum

class NotificationType(Enum):
    """Types of notifications"""
    ARBITRAGE_OPPORTUNITY = 'arbitrage_opportunity'
    PRICE_ALERT = 'price_alert'
    SYSTEM_UPDATE = 'system_update'
    SCANNER_STATUS = 'scanner_status'

class NotificationChannel(Enum):
    """Notification delivery channels"""
    IN_APP = 'in_app'
    EMAIL = 'email'
    TELEGRAM = 'telegram'
    WHATSAPP = 'whatsapp'

class NotificationStatus(Enum):
    """Notification status"""
    PENDING = 'pending'
    SENT = 'sent'
    FAILED = 'failed'
    READ = 'read'

class Notification(db.Model):
    """Model for storing notifications"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.Enum(NotificationType), nullable=False)
    channel = db.Column(db.Enum(NotificationChannel), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    data = db.Column(db.JSON)  # Additional data (e.g., opportunity details)
    status = db.Column(db.Enum(NotificationStatus), default=NotificationStatus.PENDING)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('notifications', lazy=True))
    
    def mark_as_sent(self):
        """Mark notification as sent"""
        self.status = NotificationStatus.SENT
        self.sent_at = datetime.utcnow()
        db.session.commit()
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.status = NotificationStatus.READ
        self.read_at = datetime.utcnow()
        db.session.commit()
    
    def mark_as_failed(self):
        """Mark notification as failed"""
        self.status = NotificationStatus.FAILED
        db.session.commit()
    
    def to_dict(self):
        """Convert notification to dictionary"""
        return {
            'id': self.id,
            'type': self.type.value,
            'channel': self.channel.value,
            'title': self.title,
            'message': self.message,
            'data': self.data,
            'status': self.status.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None
        }

class NotificationPreference(db.Model):
    """Model for user notification preferences"""
    __tablename__ = 'notification_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Channel preferences
    in_app_enabled = db.Column(db.Boolean, default=True)
    email_enabled = db.Column(db.Boolean, default=False)
    telegram_enabled = db.Column(db.Boolean, default=False)
    whatsapp_enabled = db.Column(db.Boolean, default=False)
    
    # Telegram settings
    telegram_chat_id = db.Column(db.String(100))
    telegram_username = db.Column(db.String(100))
    
    # WhatsApp settings
    whatsapp_number = db.Column(db.String(20))
    whatsapp_username = db.Column(db.String(100))
    
    # Notification type preferences
    arbitrage_notifications = db.Column(db.Boolean, default=True)
    price_alert_notifications = db.Column(db.Boolean, default=True)
    system_notifications = db.Column(db.Boolean, default=True)
    scanner_status_notifications = db.Column(db.Boolean, default=True)
    
    # Frequency settings
    min_profit_threshold = db.Column(db.Float, default=0.5)  # Minimum profit % to notify
    max_notifications_per_hour = db.Column(db.Integer, default=10)
    quiet_hours_start = db.Column(db.Time)  # Start of quiet hours (no notifications)
    quiet_hours_end = db.Column(db.Time)    # End of quiet hours
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('notification_preferences', uselist=False))
    
    def get_enabled_channels(self):
        """Get list of enabled notification channels"""
        channels = []
        if self.in_app_enabled:
            channels.append(NotificationChannel.IN_APP)
        if self.email_enabled:
            channels.append(NotificationChannel.EMAIL)
        if self.telegram_enabled and self.telegram_chat_id:
            channels.append(NotificationChannel.TELEGRAM)
        if self.whatsapp_enabled and self.whatsapp_number:
            channels.append(NotificationChannel.WHATSAPP)
        return channels
    
    def is_notification_type_enabled(self, notification_type):
        """Check if a specific notification type is enabled"""
        type_mapping = {
            NotificationType.ARBITRAGE_OPPORTUNITY: self.arbitrage_notifications,
            NotificationType.PRICE_ALERT: self.price_alert_notifications,
            NotificationType.SYSTEM_UPDATE: self.system_notifications,
            NotificationType.SCANNER_STATUS: self.scanner_status_notifications
        }
        return type_mapping.get(notification_type, False)
    
    def should_send_notification(self, notification_type, profit_percent=None):
        """Check if notification should be sent based on preferences"""
        # Check if notification type is enabled
        if not self.is_notification_type_enabled(notification_type):
            return False
        
        # Check profit threshold for arbitrage opportunities
        if (notification_type == NotificationType.ARBITRAGE_OPPORTUNITY and 
            profit_percent is not None and 
            profit_percent < self.min_profit_threshold):
            return False
        
        # TODO: Add quiet hours check
        # TODO: Add rate limiting check
        
        return True
    
    def to_dict(self):
        """Convert preferences to dictionary"""
        return {
            'id': self.id,
            'in_app_enabled': self.in_app_enabled,
            'email_enabled': self.email_enabled,
            'telegram_enabled': self.telegram_enabled,
            'telegram_chat_id': self.telegram_chat_id,
            'telegram_username': self.telegram_username,
            'whatsapp_enabled': self.whatsapp_enabled,
            'whatsapp_number': self.whatsapp_number,
            'whatsapp_username': self.whatsapp_username,
            'arbitrage_notifications': self.arbitrage_notifications,
            'price_alert_notifications': self.price_alert_notifications,
            'system_notifications': self.system_notifications,
            'scanner_status_notifications': self.scanner_status_notifications,
            'min_profit_threshold': self.min_profit_threshold,
            'max_notifications_per_hour': self.max_notifications_per_hour,
            'quiet_hours_start': self.quiet_hours_start.strftime('%H:%M') if self.quiet_hours_start else None,
            'quiet_hours_end': self.quiet_hours_end.strftime('%H:%M') if self.quiet_hours_end else None
        }