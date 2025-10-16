"""Notification service classes for different channels"""
import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template_string
from app.database import db
from app.models.user import UserNotification, NotificationSettings
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class BaseNotificationService:
    """Base class for notification services"""
    
    def __init__(self):
        self.channel = None
    
    def send_notification(self, user_id: int, notification_type: str, title: str, 
                         message: str, data: Dict = None) -> bool:
        """Send notification - to be implemented by subclasses"""
        raise NotImplementedError
    
    def create_notification_record(self, user_id: int, notification_type: str, 
                                 title: str, message: str, data: Dict = None) -> UserNotification:
        """Create notification record in database"""
        notification = UserNotification(
            user_id=user_id,
            notification_type=notification_type,
            channel=self.channel,
            title=title,
            message=message,
            data=data or {}
        )
        db.session.add(notification)
        db.session.commit()
        return notification

class InAppNotificationService(BaseNotificationService):
    """Service for in-app notifications"""
    
    def __init__(self):
        super().__init__()
        self.channel = 'in_app'
    
    def send_notification(self, user_id: int, notification_type: str, title: str, 
                         message: str, data: Dict = None) -> bool:
        """Send in-app notification (store in database)"""
        try:
            notification = self.create_notification_record(
                user_id, notification_type, title, message, data
            )
            notification.mark_as_sent()
            db.session.commit()
            logger.info(f"In-app notification sent to user {user_id}: {title}")
            return True
        except Exception as e:
            logger.error(f"Failed to send in-app notification to user {user_id}: {str(e)}")
            return False
    
    def get_unread_notifications(self, user_id: int, limit: int = 50) -> List[UserNotification]:
        """Get unread notifications for user"""
        return UserNotification.query.filter_by(
            user_id=user_id,
            channel='in_app',
            status='sent'
        ).order_by(UserNotification.created_at.desc()).limit(limit).all()
    
    def mark_notification_as_read(self, notification_id: int, user_id: int) -> bool:
        """Mark notification as read"""
        try:
            notification = UserNotification.query.filter_by(
                id=notification_id,
                user_id=user_id,
                channel='in_app'
            ).first()
            
            if notification:
                notification.mark_as_read()
                db.session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to mark notification {notification_id} as read: {str(e)}")
            return False
    
    def mark_all_as_read(self, user_id: int) -> bool:
        """Mark all notifications as read for user"""
        try:
            notifications = UserNotification.query.filter_by(
                user_id=user_id,
                channel='in_app',
                status='sent'
            ).all()
            
            for notification in notifications:
                notification.mark_as_read()
            
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark all notifications as read for user {user_id}: {str(e)}")
            return False

class EmailNotificationService(BaseNotificationService):
    """Service for email notifications"""
    
    def __init__(self):
        super().__init__()
        self.channel = 'email'
    
    def send_notification(self, user_id: int, notification_type: str, title: str, 
                         message: str, data: Dict = None) -> bool:
        """Send email notification"""
        try:
            # Get user's notification settings
            settings = NotificationSettings.query.filter_by(user_id=user_id).first()
            if not settings or not settings.email_enabled or not settings.email_address:
                logger.warning(f"Email notifications not enabled for user {user_id}")
                return False
            
            # Create notification record
            notification = self.create_notification_record(
                user_id, notification_type, title, message, data
            )
            
            # Send email
            success = self._send_email(
                to_email=settings.email_address,
                subject=title,
                body=message,
                data=data
            )
            
            if success:
                notification.mark_as_sent()
            else:
                notification.mark_as_failed("Failed to send email")
            
            db.session.commit()
            return success
            
        except Exception as e:
            logger.error(f"Failed to send email notification to user {user_id}: {str(e)}")
            return False
    
    def _send_email(self, to_email: str, subject: str, body: str, data: Dict = None) -> bool:
        """Send email using SMTP"""
        try:
            # Get email configuration from app config
            smtp_server = current_app.config.get('MAIL_SERVER', 'localhost')
            smtp_port = current_app.config.get('MAIL_PORT', 587)
            smtp_username = current_app.config.get('MAIL_USERNAME')
            smtp_password = current_app.config.get('MAIL_PASSWORD')
            use_tls = current_app.config.get('MAIL_USE_TLS', True)
            use_ssl = current_app.config.get('MAIL_USE_SSL', False)
            from_email = current_app.config.get('MAIL_DEFAULT_SENDER', smtp_username)
            
            if not smtp_username or not smtp_password:
                logger.error("Email credentials not configured")
                return False
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_email
            msg['To'] = to_email
            
            # Create HTML and text versions
            html_body = self._create_html_email(subject, body, data)
            text_body = body
            
            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email using appropriate connection type
            if use_ssl:
                # Use SSL connection (typically port 465)
                with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                    server.login(smtp_username, smtp_password)
                    server.send_message(msg)
            else:
                # Use regular SMTP with optional STARTTLS (typically port 587)
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    if use_tls:
                        server.starttls()
                    server.login(smtp_username, smtp_password)
                    server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    def _create_html_email(self, subject: str, body: str, data: Dict = None) -> str:
        """Create HTML email template"""
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{{ subject }}</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: #007bff; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background: #f8f9fa; }
                .footer { padding: 10px; text-align: center; font-size: 12px; color: #666; }
                .opportunity { background: white; padding: 15px; margin: 10px 0; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Arbitrage Alert</h1>
                </div>
                <div class="content">
                    <h2>{{ subject }}</h2>
                    <p>{{ body }}</p>
                    {% if data and data.opportunity %}
                    <div class="opportunity">
                        <h3>Opportunity Details:</h3>
                        <p><strong>Asset:</strong> {{ data.opportunity.token_symbol }}</p>
                        <p><strong>Buy Exchange:</strong> {{ data.opportunity.buy_exchange }}</p>
                        <p><strong>Sell Exchange:</strong> {{ data.opportunity.sell_exchange }}</p>
                        <p><strong>Profit:</strong> {{ data.opportunity.net_profit_percent }}%</p>
                    </div>
                    {% endif %}
                </div>
                <div class="footer">
                    <p>This is an automated message from your Arbitrage Scanner.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(html_template, subject=subject, body=body, data=data)

class TelegramNotificationService(BaseNotificationService):
    """Service for Telegram notifications"""
    
    def __init__(self):
        super().__init__()
        self.channel = 'telegram'
        self.bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN')
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def send_notification(self, user_id: int, notification_type: str, title: str, 
                         message: str, data: Dict = None) -> bool:
        """Send Telegram notification"""
        try:
            # Get user's notification settings
            settings = NotificationSettings.query.filter_by(user_id=user_id).first()
            if not settings or not settings.telegram_enabled or not settings.telegram_chat_id:
                logger.warning(f"Telegram notifications not enabled for user {user_id}")
                return False
            
            if not self.bot_token:
                logger.error("Telegram bot token not configured")
                return False
            
            # Create notification record
            notification = self.create_notification_record(
                user_id, notification_type, title, message, data
            )
            
            # Format message for Telegram
            telegram_message = self._format_telegram_message(title, message, data)
            
            # Send message
            success = self._send_telegram_message(
                chat_id=settings.telegram_chat_id,
                message=telegram_message
            )
            
            if success:
                notification.mark_as_sent()
            else:
                notification.mark_as_failed("Failed to send Telegram message")
            
            db.session.commit()
            return success
            
        except Exception as e:
            logger.error(f"Failed to send Telegram notification to user {user_id}: {str(e)}")
            return False
    
    def _send_telegram_message(self, chat_id: str, message: str) -> bool:
        """Send message via Telegram Bot API"""
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Telegram message sent successfully to chat {chat_id}")
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message to chat {chat_id}: {str(e)}")
            return False
    
    def _format_telegram_message(self, title: str, message: str, data: Dict = None) -> str:
        """Format message for Telegram with Markdown"""
        formatted_message = f"*{title}*\n\n{message}"
        
        if data and data.get('opportunity'):
            opp = data['opportunity']
            formatted_message += f"\n\n📊 *Opportunity Details:*\n"
            formatted_message += f"🪙 Asset: `{opp.get('token_symbol', 'N/A')}`\n"
            formatted_message += f"📈 Buy: `{opp.get('buy_exchange', 'N/A')}`\n"
            formatted_message += f"📉 Sell: `{opp.get('sell_exchange', 'N/A')}`\n"
            formatted_message += f"💰 Profit: `{opp.get('net_profit_percent', 0):.2f}%`\n"
            formatted_message += f"⏰ Time: `{datetime.now().strftime('%H:%M:%S')}`"
        
        return formatted_message
    
    def verify_chat_id(self, chat_id: str) -> bool:
        """Verify if chat ID is valid by sending a test message"""
        try:
            test_message = "✅ Telegram notifications are now enabled for your Arbitrage Scanner!"
            return self._send_telegram_message(chat_id, test_message)
        except Exception as e:
            logger.error(f"Failed to verify Telegram chat ID {chat_id}: {str(e)}")
            return False

class WhatsAppNotificationService(BaseNotificationService):
    """Service for WhatsApp notifications using Meta Business API"""
    
    def __init__(self):
        super().__init__()
        self.channel = 'whatsapp'
        self.access_token = current_app.config.get('META_WHATSAPP_ACCESS_TOKEN')
        self.phone_number_id = current_app.config.get('META_WHATSAPP_PHONE_NUMBER_ID')
        self.business_account_id = current_app.config.get('META_WHATSAPP_BUSINESS_ACCOUNT_ID')
        self.api_url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"
    
    def send_notification(self, user_id: int, notification_type: str, title: str, 
                         message: str, data: Dict = None) -> bool:
        """Send WhatsApp notification"""
        try:
            # Get user's notification settings
            settings = NotificationSettings.query.filter_by(user_id=user_id).first()
            if not settings or not settings.whatsapp_enabled or not settings.whatsapp_number:
                logger.warning(f"WhatsApp notifications not enabled for user {user_id}")
                return False
            
            if not self.access_token or not self.phone_number_id:
                logger.error("Meta WhatsApp Business API credentials not configured")
                return False
            
            # Create notification record
            notification = self.create_notification_record(
                user_id, notification_type, title, message, data
            )
            
            # Send message using template system
            success = self._send_whatsapp_message(
                to_number=settings.whatsapp_number,
                message=message,
                notification_type=notification_type,
                title=title,
                data=data
            )
            
            if success:
                notification.mark_as_sent()
            else:
                notification.mark_as_failed("Failed to send WhatsApp message")
            
            db.session.commit()
            return success
            
        except Exception as e:
            logger.error(f"Failed to send WhatsApp notification to user {user_id}: {str(e)}")
            return False
    
    def _send_whatsapp_message(self, to_number: str, message: str, notification_type: str = None, title: str = None, data: Dict = None) -> bool:
        """Send message via Meta WhatsApp Business API using custom templates"""
        try:
            import requests
            import re
            
            # Validate and format phone number
            original_number = to_number
            if to_number.startswith('+'):
                to_number = to_number[1:]
            
            # Basic phone number validation (should be digits only after removing +)
            if not re.match(r'^\d{10,15}$', to_number):
                logger.error(f"Invalid phone number format: {original_number} -> {to_number}. Must be 10-15 digits.")
                return False
            
            logger.info(f"Formatted phone number: {original_number} -> {to_number}")
            
            # Prepare headers
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            logger.info(f"Using API URL: {self.api_url}")
            logger.info(f"Using Phone Number ID: {self.phone_number_id}")
            
            # Use custom template based on notification type
            if notification_type:
                template_name, parameters = self._get_template_for_notification(notification_type, title, message, data)
            else:
                # Fallback for direct calls without notification type
                template_name, parameters = 'hello_world', []
            
            payload = {
                'messaging_product': 'whatsapp',
                'to': to_number,
                'type': 'template',
                'template': {
                    'name': template_name,
                    'language': {
                        'code': 'en_US'
                    }
                }
            }
            
            # Add parameters if template requires them
            if parameters:
                payload['template']['components'] = [{
                    'type': 'body',
                    'parameters': [{'type': 'text', 'text': str(param)} for param in parameters]
                }]
            
            logger.info(f"Using custom template '{template_name}' for {notification_type}")
            logger.info(f"Template parameters: {parameters}")
            
            # Send request to Meta API
            logger.info(f"Sending WhatsApp message to {to_number} via Meta API: {self.api_url}")
            logger.info(f"Payload: {payload}")
            
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            logger.info(f"Meta API Response Status: {response.status_code}")
            logger.info(f"Meta API Response Headers: {dict(response.headers)}")
            logger.info(f"Meta API Response: {response.text}")
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    logger.info(f"Parsed response data: {response_data}")
                    
                    # Check if messages array exists and has content
                    messages = response_data.get('messages', [])
                    if messages and len(messages) > 0:
                        message_id = messages[0].get('id')
                        if message_id:
                            logger.info(f"WhatsApp message sent successfully to {to_number}, Message ID: {message_id}")
                            return True
                        else:
                            logger.error(f"No message ID in response for {to_number}: {response_data}")
                            return False
                    else:
                        logger.error(f"No messages array in response for {to_number}: {response_data}")
                        return False
                        
                except ValueError as e:
                    logger.error(f"Failed to parse JSON response for {to_number}: {e}, Raw response: {response.text}")
                    return False
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get('error', {}).get('message', 'Unknown error')
                    error_code = error_data.get('error', {}).get('code', 'Unknown code')
                    logger.error(f"WhatsApp message failed to send to {to_number}. Status: {response.status_code}, Error Code: {error_code}, Error: {error_message}")
                except:
                    logger.error(f"WhatsApp message failed to send to {to_number}. Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message to {to_number}: {str(e)}")
            return False
    
    def _get_template_for_notification(self, notification_type: str, title: str, message: str, data: Dict = None) -> tuple:
        """Determine which template to use and extract parameters"""
        
        if notification_type == 'arbitrage_opportunity' and data and data.get('opportunity'):
            # Use arbitrage alert template
            opp = data['opportunity']
            
            # Check if this is a high-profit opportunity (>5%)
            profit_percent = data.get('profit_percent', 0)
            if profit_percent > 5.0:
                template_name = 'high_profit_alert'
                parameters = [
                    opp.get('token_symbol', 'N/A'),
                    f"{profit_percent:.2f}",
                    opp.get('buy_exchange', 'N/A'),
                    opp.get('sell_exchange', 'N/A'),
                    f"{data.get('profit_on_10000', 0):.2f}"
                ]
            else:
                template_name = 'arbitrage_alert'
                parameters = [
                    opp.get('token_symbol', 'N/A'),
                    opp.get('buy_exchange', 'N/A'),
                    opp.get('sell_exchange', 'N/A'),
                    f"{profit_percent:.2f}",
                    f"${data.get('raw_price_difference', 0):.2f}",
                    f"{data.get('profit_on_500', 0):.2f}",
                    f"{data.get('profit_on_1000', 0):.2f}",
                    f"{data.get('profit_on_5000', 0):.2f}",
                    f"{data.get('profit_on_10000', 0):.2f}",
                    f"{data.get('min_investment_required', 0):.2f}",
                    datetime.now().strftime('%H:%M:%S')
                ]
            
            return template_name, parameters
            
        elif notification_type in ['account_update', 'settings_change', 'system_notification']:
            # Use account notification template
            template_name = 'account_notification'
            parameters = [title, message]
            return template_name, parameters
            
        elif notification_type == 'welcome' and data and data.get('user_name'):
            # Use welcome template
            template_name = 'welcome_user'
            parameters = [data['user_name']]
            return template_name, parameters
            
        else:
            # Fallback to hello_world template for unknown types
            logger.warning(f"Unknown notification type '{notification_type}', using fallback template")
            return 'hello_world', []
    
    def _format_whatsapp_message(self, title: str, message: str, data: Dict = None) -> str:
        """Format message for WhatsApp (legacy method, kept for compatibility)"""
        formatted_message = f"*{title}*\n\n{message}"
        
        if data and data.get('opportunity'):
            opp = data['opportunity']
            formatted_message += f"\n\n📊 *Opportunity Details:*\n"
            formatted_message += f"🪙 Asset: {opp.get('token_symbol', 'N/A')}\n"
            formatted_message += f"📈 Buy: {opp.get('buy_exchange', 'N/A')}\n"
            formatted_message += f"📉 Sell: {opp.get('sell_exchange', 'N/A')}\n"
            formatted_message += f"💰 Profit: {opp.get('net_profit_percent', 0):.2f}%\n"
            formatted_message += f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}"
        
        return formatted_message
    
    def verify_whatsapp_number(self, phone_number: str, user_name: str = "User") -> bool:
        """Verify if WhatsApp number is valid by sending a welcome message"""
        try:
            # Use welcome template for verification
            return self._send_whatsapp_message(
                to_number=phone_number,
                message="Welcome message",
                notification_type="welcome",
                title="Welcome to Arbitrage Scanner",
                data={'user_name': user_name}
            )
        except Exception as e:
            logger.error(f"Failed to verify WhatsApp number {phone_number}: {str(e)}")
            return False
    
    def check_message_status(self, message_id: str) -> dict:
        """Check the delivery status of a sent message"""
        try:
            import requests
            
            # Meta API endpoint for message status
            status_url = f"https://graph.facebook.com/v18.0/{message_id}"
            
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            response = requests.get(status_url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get message status for {message_id}: {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Error checking message status for {message_id}: {str(e)}")
            return {}
    
    def send_template_message(self, to_number: str, template_name: str, language_code: str = "en_US", parameters: list = None) -> bool:
        """Send a WhatsApp template message (for first contact or outside 24h window)"""
        try:
            import requests
            
            # Format phone number
            if to_number.startswith('+'):
                to_number = to_number[1:]
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Prepare template payload
            payload = {
                'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': to_number,
                'type': 'template',
                'template': {
                    'name': template_name,
                    'language': {
                        'code': language_code
                    }
                }
            }
            
            # Add parameters if provided
            if parameters:
                payload['template']['components'] = [{
                    'type': 'body',
                    'parameters': [{'type': 'text', 'text': param} for param in parameters]
                }]
            
            logger.info(f"Sending WhatsApp template '{template_name}' to {to_number}")
            logger.info(f"Template payload: {payload}")
            
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            logger.info(f"Template API Response Status: {response.status_code}")
            logger.info(f"Template API Response: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                messages = response_data.get('messages', [])
                if messages and len(messages) > 0:
                    message_id = messages[0].get('id')
                    if message_id:
                        logger.info(f"WhatsApp template sent successfully to {to_number}, Message ID: {message_id}")
                        return True
            
            logger.error(f"Failed to send WhatsApp template to {to_number}: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp template to {to_number}: {str(e)}")
            return False

class NotificationManager:
    """Main notification manager that coordinates all services"""
    
    def __init__(self):
        self.in_app_service = InAppNotificationService()
        self.email_service = EmailNotificationService()
        self.telegram_service = TelegramNotificationService()
        self.whatsapp_service = WhatsAppNotificationService()
    
    def send_notification(self, user_id: int, notification_type: str, title: str, 
                         message: str, data: Dict = None) -> Dict[str, bool]:
        """Send notification through all enabled channels for user"""
        results = {}
        
        try:
            # Get user's notification settings
            settings = NotificationSettings.query.filter_by(user_id=user_id).first()
            if not settings:
                logger.warning(f"No notification settings found for user {user_id}")
                return results
            
            # Check if this notification type should be sent
            if not settings.should_send_notification(notification_type, 
                                                    data.get('profit_percent') if data else None):
                logger.info(f"Notification {notification_type} filtered out for user {user_id}")
                return results
            
            # Send through enabled channels
            enabled_channels = settings.get_enabled_channels()
            
            if 'in_app' in enabled_channels:
                results['in_app'] = self.in_app_service.send_notification(
                    user_id, notification_type, title, message, data
                )
            
            if 'email' in enabled_channels:
                results['email'] = self.email_service.send_notification(
                    user_id, notification_type, title, message, data
                )
            
            if 'telegram' in enabled_channels:
                results['telegram'] = self.telegram_service.send_notification(
                    user_id, notification_type, title, message, data
                )
            
            if 'whatsapp' in enabled_channels:
                results['whatsapp'] = self.whatsapp_service.send_notification(
                    user_id, notification_type, title, message, data
                )
            
            logger.info(f"Notification sent to user {user_id} via channels: {list(results.keys())}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to send notification to user {user_id}: {str(e)}")
            return results
    
    def send_arbitrage_opportunity_notification(self, user_id: int, opportunity) -> Dict[str, bool]:
        """Send notification for new arbitrage opportunity with profit calculator"""
        title = f"🚀 New Arbitrage Opportunity: {opportunity.token_symbol}"
        
        # Create profit calculator section with exact format requested
        profit_calculator = (
            f"Profit Calculator:\n"
            f"$500 will make ${opportunity.profit_on_500:.2f}\n"
            f"$1,000 will make ${opportunity.profit_on_1000:.2f}\n"
            f"$5,000 will make ${opportunity.profit_on_5000:.2f}\n"
            f"$10,000 will make ${opportunity.profit_on_10000:.2f}"
        )
        
        message = (
            f"💰 Profit opportunity detected!\n\n"
            f"Asset: {opportunity.token_symbol}\n"
            f"Buy on {opportunity.buy_exchange} → Sell on {opportunity.sell_exchange}\n"
            f"Price Difference: ${opportunity.raw_price_difference:.4f}\n"
            f"Net Profit: {opportunity.net_profit_percent:.2f}%\n\n"
            f"{profit_calculator}\n\n"
            f"⚠️ Minimum Investment: ${opportunity.min_investment_required:.2f}"
        )
        
        data = {
            'opportunity': opportunity.to_dict(),
            'profit_percent': opportunity.net_profit_percent,
            'profit_on_500': opportunity.profit_on_500,
            'profit_on_1000': opportunity.profit_on_1000,
            'profit_on_5000': opportunity.profit_on_5000,
            'profit_on_10000': opportunity.profit_on_10000,
            'raw_price_difference': opportunity.raw_price_difference,
            'min_investment_required': opportunity.min_investment_required
        }
        
        return self.send_notification(
            user_id, 'arbitrage_opportunity', title, message, data
        )
    
    def send_arbitrage_notification(self, user, opportunity):
        """Send arbitrage notification to a user (used by background scanner)"""
        return self.send_arbitrage_opportunity_notification(user.id, opportunity)