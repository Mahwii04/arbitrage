import logging
import time
from threading import Thread, Event
from typing import Optional
from datetime import datetime, timedelta

from app.models.arbitrage import ArbitrageOpportunity
from app.models.user import User
from app.services.arbitrage_scanner import ArbitrageScanner
from app.services.notification_service import NotificationManager
from app.services.user_arbitrage_manager import UserArbitrageManager
from app.config.config_manager import ConfigManager
from app import db


class BackgroundArbitrageScanner:
    """
    Background service that continuously scans for arbitrage opportunities
    and sends notifications to users based on their preferences
    """
    
    def __init__(self, app=None):
        self.app = app
        self.logger = logging.getLogger(__name__)
        self.scanner = None
        self.notification_manager = None
        self.user_manager = None
        self.scan_thread = None
        self.stop_event = Event()
        self.scan_interval = 300  # 5 minutes default
        self.min_dollar_profit = 10.0  # Minimum $10 profit for $1000 investment
        self.is_running = False
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the background scanner with Flask app context"""
        self.app = app
        
        # Initialize services within app context
        with app.app_context():
            config_manager = ConfigManager()
            self.scanner = ArbitrageScanner(config_manager)
            self.notification_manager = NotificationManager()
            self.user_manager = UserArbitrageManager(config_manager)
            
            # Get configuration from app config
            self.scan_interval = app.config.get('ARBITRAGE_SCAN_INTERVAL', 300)
            self.min_dollar_profit = app.config.get('MIN_DOLLAR_PROFIT', 10.0)
            
        self.logger.info(f"Background arbitrage scanner initialized with {self.scan_interval}s interval")
    
    def start(self):
        """Start the background scanning service"""
        if self.is_running:
            self.logger.warning("Background scanner is already running")
            return
            
        if not self.app:
            self.logger.error("Flask app not initialized")
            return
            
        self.logger.info("Starting background arbitrage scanner...")
        self.stop_event.clear()
        self.is_running = True
        
        # Start scanning in a separate thread
        self.scan_thread = Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()
        
        self.logger.info("Background arbitrage scanner started successfully")
    
    def stop(self):
        """Stop the background scanning service"""
        if not self.is_running:
            self.logger.warning("Background scanner is not running")
            return
            
        self.logger.info("Stopping background arbitrage scanner...")
        self.stop_event.set()
        self.is_running = False
        
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=10)
            
        self.logger.info("Background arbitrage scanner stopped")
    
    def _scan_loop(self):
        """Main scanning loop that runs in background thread"""
        self.logger.info("Background scanning loop started")
        
        while not self.stop_event.is_set():
            try:
                with self.app.app_context():
                    self._perform_scan()
                    
            except Exception as e:
                self.logger.error(f"Error during background scan: {str(e)}", exc_info=True)
            
            # Wait for next scan or stop signal
            if self.stop_event.wait(timeout=self.scan_interval):
                break
                
        self.logger.info("Background scanning loop ended")
    
    def _perform_scan(self):
        """Perform a single arbitrage scan and process results"""
        scan_start = time.time()
        self.logger.info("Starting arbitrage scan...")
        
        try:
            # Check if scanner is properly initialized
            if not self.scanner:
                self.logger.error("Scanner not initialized, skipping scan")
                return
                
            # Check API health before scanning
            if not self.scanner.price_fetcher.health_check():
                self.logger.warning("Price fetcher health check failed, skipping scan")
                return
            
            # Perform all database operations within app context
            with self.app.app_context():
                # Get active users with notification preferences
                users = User.query.filter(User._is_active == True).all()
                if not users:
                    self.logger.info("No active users found for scanning")
                    return
                
                # Fetch current prices
                assets = self.scanner.config_manager.get_enabled_assets()
                exchange_configs = self.scanner.config_manager.get_enabled_exchanges()
                
                # Extract IDs for the price fetcher
                tokens = [asset['id'] for asset in assets]
                exchanges = [ex['id'] for ex in exchange_configs]
                
                self.logger.info(f"Fetching prices for {len(tokens)} tokens from {len(exchanges)} exchanges")
                price_data = self.scanner.price_fetcher.fetch_prices(tokens, exchanges)
                
                if not price_data:
                    self.logger.warning("No price data received, skipping scan")
                    return
                
                self.logger.info(f"Received {len(price_data)} price data points")
                
                # Find arbitrage opportunities
                opportunities = self.scanner.find_arbitrage_opportunities(
                    min_dollar_profit=10.0  # Minimum $10 profit for notifications
                )
                
                if opportunities:
                    self.logger.info(f"Found {len(opportunities)} arbitrage opportunities")
                    
                    # Send notifications to users
                    notification_count = 0
                    for opportunity in opportunities:
                        for user in users:
                            # Check if user has notification settings and should receive notifications
                            if (user.notification_settings and 
                                user.notification_settings.should_send_notification('arbitrage')):
                                try:
                                    success = self.notification_manager.send_arbitrage_notification(
                                        user.id, opportunity
                                    )
                                    if success:
                                        notification_count += 1
                                except Exception as e:
                                    self.logger.error(f"Failed to send notification to user {user.id}: {str(e)}")
                    
                    self.logger.info(f"Sent {notification_count} notifications for {len(opportunities)} opportunities")
                    
                    # Save opportunities to database
                    new_opportunities = []
                    for opportunity in opportunities:
                        try:
                            # Check if this opportunity already exists (avoid duplicates)
                            existing = self._find_existing_opportunity(opportunity)
                            
                            if not existing:
                                # Save new opportunity to database
                                db.session.add(opportunity)
                                new_opportunities.append(opportunity)
                                self.logger.debug(f"New opportunity: {opportunity.token_symbol} "
                                                f"{opportunity.buy_exchange} -> {opportunity.sell_exchange} "
                                            f"${opportunity.profit_on_1000:.2f} profit on $1000")
                        
                        except Exception as e:
                            self.logger.error(f"Error processing opportunity: {str(e)}")
                            continue
                    
                    # Commit new opportunities to database
                    if new_opportunities:
                        db.session.commit()
                        self.logger.info(f"Saved {len(new_opportunities)} new opportunities to database")
                    else:
                        self.logger.info("No new opportunities to save")
                else:
                    self.logger.info("No arbitrage opportunities found")
                    
        except Exception as e:
            self.logger.error(f"Error during arbitrage scan: {str(e)}", exc_info=True)
            with self.app.app_context():
                db.session.rollback()
        
        scan_duration = time.time() - scan_start
        self.logger.info(f"Arbitrage scan completed in {scan_duration:.2f} seconds")
    
    def _find_existing_opportunity(self, opportunity: ArbitrageOpportunity) -> Optional[ArbitrageOpportunity]:
        """Check if similar opportunity already exists in database"""
        # Look for existing opportunity with same token and exchange pair within last hour
        cutoff_time = datetime.utcnow() - timedelta(hours=1)
        
        # This method is called within app context, so no need to wrap again
        existing = ArbitrageOpportunity.query.filter(
            ArbitrageOpportunity.token_id == opportunity.token_id,
            ArbitrageOpportunity.buy_exchange == opportunity.buy_exchange,
            ArbitrageOpportunity.sell_exchange == opportunity.sell_exchange,
            ArbitrageOpportunity.timestamp >= cutoff_time,
            ArbitrageOpportunity.is_active == True
        ).first()
        
        return existing
    
    def _send_notifications(self, opportunities):
        """Send notifications to users for new arbitrage opportunities"""
        try:
            # Get all users with notification preferences
            users_to_notify = self.user_manager.get_users_for_notifications()
            
            if not users_to_notify:
                self.logger.info("No users configured for arbitrage notifications")
                return
                
            self.logger.info(f"Sending notifications to {len(users_to_notify)} users")
            
            for user in users_to_notify:
                try:
                    # Get user settings for filtering
                    user_settings = {
                        'subscription_tier': getattr(user, 'subscription_tier', 'free'),
                        'preferred_exchanges': getattr(user, 'preferred_exchanges', []),
                        'preferred_assets': getattr(user, 'preferred_assets', []),
                        'min_profit_percent': getattr(user, 'min_profit_percent', 0.5)
                    }
                    
                    # Filter opportunities based on user preferences
                    user_opportunities = self.user_manager.filter_opportunities_for_user(
                        opportunities, user_settings
                    )
                    
                    if user_opportunities:
                        # Send notification for each relevant opportunity
                        for opportunity in user_opportunities:
                            self.notification_manager.send_arbitrage_notification(
                                user, opportunity
                            )
                            
                        self.logger.info(f"Sent {len(user_opportunities)} notifications to user {user.id}")
                        
                except Exception as e:
                    self.logger.error(f"Error sending notifications to user {user.id}: {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error in notification process: {str(e)}", exc_info=True)
    
    def get_status(self):
        """Get current status of the background scanner"""
        return {
            'is_running': self.is_running,
            'scan_interval': self.scan_interval,
            'min_dollar_profit': self.min_dollar_profit,
            'thread_alive': self.scan_thread.is_alive() if self.scan_thread else False
        }


# Global instance
background_scanner = BackgroundArbitrageScanner()