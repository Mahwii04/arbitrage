"""Database initialization and first user creation script"""
import click
from flask.cli import with_appcontext
from app import create_app, db
from app.models.user import (
    User, UserPreferences, NotificationSettings, UserNotification,
    ScanHistory
)
from app.models.arbitrage import ArbitrageOpportunity
from app.models.admin import AdminRole

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
        db.session.flush()
        
        # Create default preferences
        preferences = UserPreferences(
            user_id=user.id,
            min_profit_percent=0.5
        )
        db.session.add(preferences)
        
        # Create default notification settings
        notification_settings = NotificationSettings(
            user_id=user.id
        )
        notification_settings.email_enabled = True
        notification_settings.in_app_enabled = True
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
    app.cli.add_command(make_admin_command)
    app.cli.add_command(list_users_command)
    
@click.command('make-admin')
@click.option('--email', prompt=True, help='Email of user to grant admin')
@with_appcontext
def make_admin_command(email):
    """Grant admin role to a user by email."""
    user = User.query.filter_by(email=email).first()
    if not user:
        click.echo('User not found', err=True)
        return
    if AdminRole.query.filter_by(user_id=user.id).first():
        click.echo('User is already an admin')
        return
    role = AdminRole(user_id=user.id)
    from app import db as _db
    _db.session.add(role)
    _db.session.commit()
    click.echo(f'Granted admin to {email}')

@click.command('list-users')
@with_appcontext
def list_users_command():
    """List all users."""
    users = User.query.all()
    if not users:
        click.echo('No users found.')
        return
    
    click.echo(f'Found {len(users)} users:')
    for user in users:
        admin_role = AdminRole.query.filter_by(user_id=user.id).first()
        role = "Admin" if admin_role else "User"
        click.echo(f'- {user.username} ({user.email}) [{role}]')
