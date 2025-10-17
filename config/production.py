"""Production configuration for the arbitrage bot"""
import os
from .base import Config

class ProductionConfig(Config):
    """Production configuration class"""
    
    # Flask settings
    DEBUG = False
    TESTING = False
    
    # Database - Use SQLite for now, can be changed to PostgreSQL later
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///arbitrage.db'
    
    # Redis for caching and session storage
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable must be set in production")
    
    # Session configuration
    SESSION_TYPE = 'redis'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = 'arbitrage:'
    
    # API Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/1'
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = '/app/logs/arbitrage.log'
    
    # Background scanner settings
    SCANNER_INTERVAL = int(os.environ.get('SCANNER_INTERVAL', 300))  # 5 minutes
    SCANNER_ENABLED = os.environ.get('SCANNER_ENABLED', 'true').lower() == 'true'
    
    # Exchange API settings
    BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY')
    BINANCE_SECRET_KEY = os.environ.get('BINANCE_SECRET_KEY')
    COINBASE_API_KEY = os.environ.get('COINBASE_API_KEY')
    COINBASE_SECRET_KEY = os.environ.get('COINBASE_SECRET_KEY')
    KRAKEN_API_KEY = os.environ.get('KRAKEN_API_KEY')
    KRAKEN_SECRET_KEY = os.environ.get('KRAKEN_SECRET_KEY')
    
    # Notification settings
    NOTIFICATION_ENABLED = os.environ.get('NOTIFICATION_ENABLED', 'true').lower() == 'true'
    EMAIL_NOTIFICATIONS = os.environ.get('EMAIL_NOTIFICATIONS', 'false').lower() == 'true'
    
    # SMTP settings for email notifications
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # Performance settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'max_overflow': 20
    }
    
    # Security headers
    SECURITY_HEADERS = {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block'
    }