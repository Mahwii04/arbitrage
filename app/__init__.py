from flask import Flask
from flask_login import LoginManager
from flask_mail import Mail
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from app.database import db, init_db
import os

# Load environment variables
load_dotenv()

# Initialize Flask extensions
login_manager = LoginManager()
mail = Mail()
scheduler = BackgroundScheduler()

def create_app(config_name=None):
    app = Flask(__name__)
    
    # Determine configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    # Load configuration
    if config_name == 'production':
        from config.production import ProductionConfig
        app.config.from_object(ProductionConfig)
    elif config_name == 'testing':
        from config.base import TestingConfig
        app.config.from_object(TestingConfig)
    else:
        from config.base import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)
    
    # Apply mail configuration based on provider
    mail_config = app.config.get_mail_config() if hasattr(app.config, 'get_mail_config') else {}
    app.config.update(mail_config)
    
    # Set default sender
    app.config['MAIL_DEFAULT_SENDER'] = app.config.get('MAIL_USERNAME')
    
    # Legacy email configuration for backward compatibility
    mail_provider = os.getenv('MAIL_PROVIDER', 'quantumautomata').lower()
    
    # Load configuration based on selected provider
    if mail_provider == 'quantumautomata':
        app.config['MAIL_SERVER'] = os.getenv('QUANTUM_MAIL_SERVER')
        app.config['MAIL_PORT'] = int(os.getenv('QUANTUM_MAIL_PORT', 465))
        app.config['MAIL_USE_TLS'] = os.getenv('QUANTUM_MAIL_USE_TLS', 'False') == 'True'
        app.config['MAIL_USE_SSL'] = os.getenv('QUANTUM_MAIL_USE_SSL', 'True') == 'True'
        app.config['MAIL_USERNAME'] = os.getenv('QUANTUM_MAIL_USERNAME')
        app.config['MAIL_PASSWORD'] = os.getenv('QUANTUM_MAIL_PASSWORD')
    elif mail_provider == 'gmail':
        app.config['MAIL_SERVER'] = os.getenv('GMAIL_MAIL_SERVER')
        app.config['MAIL_PORT'] = int(os.getenv('GMAIL_MAIL_PORT', 587))
        app.config['MAIL_USE_TLS'] = os.getenv('GMAIL_MAIL_USE_TLS', 'True') == 'True'
        app.config['MAIL_USE_SSL'] = os.getenv('GMAIL_MAIL_USE_SSL', 'False') == 'True'
        app.config['MAIL_USERNAME'] = os.getenv('GMAIL_MAIL_USERNAME')
        app.config['MAIL_PASSWORD'] = os.getenv('GMAIL_MAIL_PASSWORD')
    elif mail_provider == 'outlook':
        app.config['MAIL_SERVER'] = os.getenv('OUTLOOK_MAIL_SERVER')
        app.config['MAIL_PORT'] = int(os.getenv('OUTLOOK_MAIL_PORT', 587))
        app.config['MAIL_USE_TLS'] = os.getenv('OUTLOOK_MAIL_USE_TLS', 'True') == 'True'
        app.config['MAIL_USE_SSL'] = os.getenv('OUTLOOK_MAIL_USE_SSL', 'False') == 'True'
        app.config['MAIL_USERNAME'] = os.getenv('OUTLOOK_MAIL_USERNAME')
        app.config['MAIL_PASSWORD'] = os.getenv('OUTLOOK_MAIL_PASSWORD')
    elif mail_provider == 'custom':
        app.config['MAIL_SERVER'] = os.getenv('CUSTOM_MAIL_SERVER')
        app.config['MAIL_PORT'] = int(os.getenv('CUSTOM_MAIL_PORT', 587))
        app.config['MAIL_USE_TLS'] = os.getenv('CUSTOM_MAIL_USE_TLS', 'True') == 'True'
        app.config['MAIL_USE_SSL'] = os.getenv('CUSTOM_MAIL_USE_SSL', 'False') == 'True'
        app.config['MAIL_USERNAME'] = os.getenv('CUSTOM_MAIL_USERNAME')
        app.config['MAIL_PASSWORD'] = os.getenv('CUSTOM_MAIL_PASSWORD')
    else:
        # Fallback to quantumautomata if invalid provider
        app.config['MAIL_SERVER'] = os.getenv('QUANTUM_MAIL_SERVER')
        app.config['MAIL_PORT'] = int(os.getenv('QUANTUM_MAIL_PORT', 465))
        app.config['MAIL_USE_TLS'] = os.getenv('QUANTUM_MAIL_USE_TLS', 'False') == 'True'
        app.config['MAIL_USE_SSL'] = os.getenv('QUANTUM_MAIL_USE_SSL', 'True') == 'True'
        app.config['MAIL_USERNAME'] = os.getenv('QUANTUM_MAIL_USERNAME')
        app.config['MAIL_PASSWORD'] = os.getenv('QUANTUM_MAIL_PASSWORD')
    
    app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']
    app.config['MAIL_PROVIDER'] = mail_provider
    
    # Telegram Bot Configuration
    app.config['TELEGRAM_BOT_TOKEN'] = os.getenv('TELEGRAM_BOT_TOKEN')
    
    # Meta WhatsApp Business API Configuration
    app.config['META_WHATSAPP_ACCESS_TOKEN'] = os.getenv('META_WHATSAPP_ACCESS_TOKEN')
    app.config['META_WHATSAPP_PHONE_NUMBER_ID'] = os.getenv('META_WHATSAPP_PHONE_NUMBER_ID')
    app.config['META_WHATSAPP_BUSINESS_ACCOUNT_ID'] = os.getenv('META_WHATSAPP_BUSINESS_ACCOUNT_ID')
    app.config['META_WHATSAPP_WEBHOOK_VERIFY_TOKEN'] = os.getenv('META_WHATSAPP_WEBHOOK_VERIFY_TOKEN')
    
    # Initialize extensions with app
    init_db(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'  # type: ignore
    mail.init_app(app)
    
    with app.app_context():
        # Import parts of our application
        from app.models.user import User
        from app.routes import auth, main, settings, dashboard
        
        # Register blueprints
        app.register_blueprint(auth.bp)
        app.register_blueprint(main.bp)
        app.register_blueprint(settings.bp)
        app.register_blueprint(dashboard.bp)
        
        # Start the background scheduler
        if not scheduler.running:
            scheduler.start()
        
        # Initialize and start background arbitrage scanner
        from app.services.background_scanner import background_scanner
        background_scanner.init_app(app)
        
        # Start background scanner in production or when explicitly enabled
        if not app.config.get('TESTING', False):
            background_scanner.start()
            app.logger.info("Background arbitrage scanner started")
        
        # Register CLI commands
        from app.cli import init_app as init_cli
        init_cli(app)
        
        return app