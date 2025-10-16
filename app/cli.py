"""Database initialization and first user creation script"""
import click
from flask.cli import with_appcontext
from app import create_app, db
from app.models.user import (
    User, UserPreferences, NotificationSettings, UserNotification,
    ScanHistory
)
from app.models.arbitrage import ArbitrageOpportunity

@click.command('init-db')
@with_appcontext
def init_db_command():
    """Initialize the database."""
    click.echo('Creating database tables...')
    db.create_all()
    click.echo('Database tables created successfully!')

@click.command('create-user')
@click.option('--username', prompt=True, help='Username for the new user')
@click.option('--email', prompt=True, help='Email address for the new user')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Password for the new user')
@with_appcontext
def create_user_command(username, email, password):
    """Create a new user."""
    try:
        # Create user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        
        # Create default preferences
        preferences = UserPreferences(
            user=user,
            min_profit_percent=0.5,
            preferred_exchanges=[],
            preferred_assets=[]
        )
        db.session.add(preferences)
        
        # Create default notification settings
        notification_settings = NotificationSettings(
            user=user,
            email_enabled=True,
            webapp_enabled=True
        )
        db.session.add(notification_settings)
        
        db.session.commit()
        click.echo(f'User {username} created successfully!')
        
    except Exception as e:
        db.session.rollback()
        click.echo(f'Error creating user: {str(e)}', err=True)

def init_app(app):
    """Register database commands"""
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_user_command)