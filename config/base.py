"""Base configuration for the arbitrage bot"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration class"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    
    # Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    
    # Email configuration - Dynamic provider selection
    MAIL_PROVIDER = os.environ.get('MAIL_PROVIDER', 'quantumautomata').lower()
    
    # QuantumAutomata email settings
    QUANTUM_MAIL_SERVER = os.environ.get('QUANTUM_MAIL_SERVER')
    QUANTUM_MAIL_PORT = int(os.environ.get('QUANTUM_MAIL_PORT', 465))
    QUANTUM_MAIL_USE_TLS = os.environ.get('QUANTUM_MAIL_USE_TLS', 'False') == 'True'
    QUANTUM_MAIL_USE_SSL = os.environ.get('QUANTUM_MAIL_USE_SSL', 'True') == 'True'
    QUANTUM_MAIL_USERNAME = os.environ.get('QUANTUM_MAIL_USERNAME')
    QUANTUM_MAIL_PASSWORD = os.environ.get('QUANTUM_MAIL_PASSWORD')
    
    # Gmail settings
    GMAIL_MAIL_SERVER = os.environ.get('GMAIL_MAIL_SERVER')
    GMAIL_MAIL_PORT = int(os.environ.get('GMAIL_MAIL_PORT', 587))
    GMAIL_MAIL_USE_TLS = os.environ.get('GMAIL_MAIL_USE_TLS', 'True') == 'True'
    GMAIL_MAIL_USE_SSL = os.environ.get('GMAIL_MAIL_USE_SSL', 'False') == 'True'
    GMAIL_MAIL_USERNAME = os.environ.get('GMAIL_MAIL_USERNAME')
    GMAIL_MAIL_PASSWORD = os.environ.get('GMAIL_MAIL_PASSWORD')
    
    # Outlook settings
    OUTLOOK_MAIL_SERVER = os.environ.get('OUTLOOK_MAIL_SERVER')
    OUTLOOK_MAIL_PORT = int(os.environ.get('OUTLOOK_MAIL_PORT', 587))
    OUTLOOK_MAIL_USE_TLS = os.environ.get('OUTLOOK_MAIL_USE_TLS', 'True') == 'True'
    OUTLOOK_MAIL_USE_SSL = os.environ.get('OUTLOOK_MAIL_USE_SSL', 'False') == 'True'
    OUTLOOK_MAIL_USERNAME = os.environ.get('OUTLOOK_MAIL_USERNAME')
    OUTLOOK_MAIL_PASSWORD = os.environ.get('OUTLOOK_MAIL_PASSWORD')
    
    # Custom email settings
    CUSTOM_MAIL_SERVER = os.environ.get('CUSTOM_MAIL_SERVER')
    CUSTOM_MAIL_PORT = int(os.environ.get('CUSTOM_MAIL_PORT', 587))
    CUSTOM_MAIL_USE_TLS = os.environ.get('CUSTOM_MAIL_USE_TLS', 'True') == 'True'
    CUSTOM_MAIL_USE_SSL = os.environ.get('CUSTOM_MAIL_USE_SSL', 'False') == 'True'
    CUSTOM_MAIL_USERNAME = os.environ.get('CUSTOM_MAIL_USERNAME')
    CUSTOM_MAIL_PASSWORD = os.environ.get('CUSTOM_MAIL_PASSWORD')
    
    # WhatsApp settings
    WHATSAPP_ENABLED = os.environ.get('WHATSAPP_ENABLED', 'False') == 'True'
    WHATSAPP_PHONE_NUMBER = os.environ.get('WHATSAPP_PHONE_NUMBER')
    WHATSAPP_API_KEY = os.environ.get('WHATSAPP_API_KEY')
    
    # Background scanner settings
    SCANNER_INTERVAL = int(os.environ.get('SCANNER_INTERVAL', 300))  # 5 minutes default
    SCANNER_ENABLED = os.environ.get('SCANNER_ENABLED', 'true').lower() == 'true'
    
    # API Keys
    COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')
    
    @classmethod
    def get_mail_config(cls):
        """Get mail configuration based on selected provider"""
        provider = cls.MAIL_PROVIDER
        
        if provider == 'quantumautomata':
            return {
                'MAIL_SERVER': cls.QUANTUM_MAIL_SERVER,
                'MAIL_PORT': cls.QUANTUM_MAIL_PORT,
                'MAIL_USE_TLS': cls.QUANTUM_MAIL_USE_TLS,
                'MAIL_USE_SSL': cls.QUANTUM_MAIL_USE_SSL,
                'MAIL_USERNAME': cls.QUANTUM_MAIL_USERNAME,
                'MAIL_PASSWORD': cls.QUANTUM_MAIL_PASSWORD
            }
        elif provider == 'gmail':
            return {
                'MAIL_SERVER': cls.GMAIL_MAIL_SERVER,
                'MAIL_PORT': cls.GMAIL_MAIL_PORT,
                'MAIL_USE_TLS': cls.GMAIL_MAIL_USE_TLS,
                'MAIL_USE_SSL': cls.GMAIL_MAIL_USE_SSL,
                'MAIL_USERNAME': cls.GMAIL_MAIL_USERNAME,
                'MAIL_PASSWORD': cls.GMAIL_MAIL_PASSWORD
            }
        elif provider == 'outlook':
            return {
                'MAIL_SERVER': cls.OUTLOOK_MAIL_SERVER,
                'MAIL_PORT': cls.OUTLOOK_MAIL_PORT,
                'MAIL_USE_TLS': cls.OUTLOOK_MAIL_USE_TLS,
                'MAIL_USE_SSL': cls.OUTLOOK_MAIL_USE_SSL,
                'MAIL_USERNAME': cls.OUTLOOK_MAIL_USERNAME,
                'MAIL_PASSWORD': cls.OUTLOOK_MAIL_PASSWORD
            }
        elif provider == 'custom':
            return {
                'MAIL_SERVER': cls.CUSTOM_MAIL_SERVER,
                'MAIL_PORT': cls.CUSTOM_MAIL_PORT,
                'MAIL_USE_TLS': cls.CUSTOM_MAIL_USE_TLS,
                'MAIL_USE_SSL': cls.CUSTOM_MAIL_USE_SSL,
                'MAIL_USERNAME': cls.CUSTOM_MAIL_USERNAME,
                'MAIL_PASSWORD': cls.CUSTOM_MAIL_PASSWORD
            }
        else:
            return {}

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///arbitrage.db'

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': 'config.production.ProductionConfig',
    'default': DevelopmentConfig
}