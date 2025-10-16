"""Email service for sending emails"""
from threading import Thread
from flask import current_app, render_template
from flask_mail import Message
from app import mail

def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        mail.send(msg)

def send_email(subject, sender, recipients, text_body, html_body=None):
    """Send email with optional HTML body"""
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    if html_body:
        msg.html = html_body
    
    # Get the current application context
    app = current_app if current_app else None
    if app:
        # Send email asynchronously only if we have an app context
        Thread(target=send_async_email, args=(app, msg)).start()
    else:
        # Fallback to synchronous send if no app context
        mail.send(msg)

def send_password_reset_email(user, token):
    """Send password reset email to user"""
    send_email('Reset Your Password',
               sender=current_app.config['MAIL_USERNAME'],
               recipients=[user.email],
               text_body=render_template('email/reset_password.txt',
                                       user=user, token=token))