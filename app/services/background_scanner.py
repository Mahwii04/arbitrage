"""Background arbitrage scanner service with improved deduplication"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple
from flask import Flask
from app.config.config_manager import ConfigManager
from app.services.arbitrage_scanner import ArbitrageScanner
from app.services.notification_service import NotificationManager
from app.services.user_arbitrage_manager import UserArbitrageManager
from app.models.arbitrage import ArbitrageOpportunity
from app.models.user import User, ScanHistory
from app import db

class BackgroundArbitrageScanner:
    def __init__(self, app: Flask = None, scan_interval: int = 300, min_dollar_profit: float = 10.0):
        self.app = app
        self.scan_interval = scan_interval  # Default 5 minutes
        self.min_dollar_profit = min_dollar_profit
        self.is_running = False
        self.stop_event = threading.Event()
        self.scan_thread = None
        self.logger = logging.getLogger(__name__)
        
        # Initialize services
        self.config_manager = ConfigManager()
        self.scanner = ArbitrageScanner(self.config_manager)
        # Defer NotificationManager initialization until app context is available
        self.notification_manager = None
        self.user_manager = UserArbitrageManager(self.config_manager)
        
        # Track recent opportunities to prevent duplicates within scan cycles
        self.recent_opportunities: Set[Tuple[str, str, str]] = set()  # (token, buy_exchange, sell_exchange)
        self.last_cleanup = datetime.utcnow()
        
    def start(self, app: Flask = None):
        """Start the background scanner"""
        if app:
            self.app = app
            
        if self.is_running:
            self.logger.warning("Background scanner is already running")
            return
            
        if not self.app:
            raise ValueError("Flask app instance is required")
            
        self.logger.info(f"Starting background arbitrage scanner with {self.scan_interval}s interval")
        self.is_running = True
        self.stop_event.clear()
        
        # Start scanning thread
        self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()
        
    def stop(self):
        """Stop the background scanner"""
        if not self.is_running:
            self.logger.warning("Background scanner is not running")
            return
            
        self.logger.info("Stopping background arbitrage scanner...")
        self.is_running = False
        self.stop_event.set()
        
        # Wait for thread to finish
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=10)
            
        self.logger.info("Background scanner stopped")
        
    def _scan_loop(self):
        """Main scanning loop"""
        self.logger.info("Background scanning loop started")
        
        while not self.stop_event.is_set():
            try:
                # Perform scan within app context
                with self.app.app_context():
                    self._perform_scan()
                    
            except Exception as e:
                self.logger.error(f"Error during background scan: {str(e)}", exc_info=True)
            
            # Clean up old opportunities from memory every hour
            if datetime.utcnow() - self.last_cleanup > timedelta(hours=1):
                self._cleanup_recent_opportunities()
            
            # Wait for next scan or stop signal
            if self.stop_event.wait(timeout=self.scan_interval):
                break
                
        self.logger.info("Background scanning loop ended")

    def init_app(self, app: Flask):
        """Initialize with Flask app context and config"""
        self.app = app
        with self.app.app_context():
            # Ensure database tables exist
            from app.database import db as _db
            _db.create_all()
            self.logger.info("Database tables initialized")
            # Refresh services if needed
            self.config_manager = ConfigManager()
            self.scanner = ArbitrageScanner(self.config_manager)
            self.notification_manager = NotificationManager()
            self.user_manager = UserArbitrageManager(self.config_manager)
            # Read configuration values (support both legacy and new keys)
            self.scan_interval = app.config.get('ARBITRAGE_SCAN_INTERVAL', app.config.get('SCANNER_INTERVAL', self.scan_interval))
            self.min_dollar_profit = app.config.get('MIN_DOLLAR_PROFIT', self.min_dollar_profit)
        self.logger.info(f"Background arbitrage scanner initialized with {self.scan_interval}s interval")
    
    def _perform_scan(self):
        """Perform a single arbitrage scan with improved deduplication"""
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
            
            # Find arbitrage opportunities using the new simplified scanner
            opportunities = self.scanner.find_arbitrage_opportunities()
            
            if not opportunities:
                self.logger.info("No arbitrage opportunities found")
                # Still record the scan with 0 opportunities
                self._record_scan_history(0, 0, 0, scan_start)
                return
                
            self.logger.info(f"Found {len(opportunities)} potential arbitrage opportunities")
            
            # Filter out duplicates and recently processed opportunities
            new_opportunities = self._filter_duplicate_opportunities(opportunities)
            
            if not new_opportunities:
                self.logger.info("All opportunities were duplicates, skipping notifications")
                # Record scan with 0 new opportunities
                self._record_scan_history(len(opportunities), 0, 0, scan_start)
                return
                
            self.logger.info(f"Processing {len(new_opportunities)} new opportunities")
            
            # Store new opportunities in database
            self._store_opportunities(new_opportunities)
            
            # Send consolidated notifications to users
            self._send_consolidated_notifications(new_opportunities)
            
            # Record scan history for all users
            self._record_scan_history(len(opportunities), len(new_opportunities), 
                                    len(self.config_manager.get_exchanges()), scan_start)
                    
        except Exception as e:
            self.logger.error(f"Error during arbitrage scan: {str(e)}", exc_info=True)
            db.session.rollback()
        
        scan_duration = time.time() - scan_start
        self.logger.info(f"Arbitrage scan completed in {scan_duration:.2f} seconds")
    
    def _filter_duplicate_opportunities(self, opportunities: List[ArbitrageOpportunity]) -> List[ArbitrageOpportunity]:
        """Filter out duplicate opportunities from current scan and recent history"""
        new_opportunities = []
        current_scan_keys = set()
        
        for opp in opportunities:
            # Create unique key for this opportunity
            opp_key = (opp.token_id, opp.buy_exchange, opp.sell_exchange)
            
            # Skip if we've already processed this combination in current scan
            if opp_key in current_scan_keys:
                self.logger.debug(f"Skipping duplicate in current scan: {opp.token_symbol} {opp.buy_exchange} -> {opp.sell_exchange}")
                continue
                
            # Skip if we've processed this combination recently
            if opp_key in self.recent_opportunities:
                self.logger.debug(f"Skipping recently processed opportunity: {opp.token_symbol} {opp.buy_exchange} -> {opp.sell_exchange}")
                continue
                
            # Check database for recent similar opportunities
            if self._find_recent_database_opportunity(opp):
                self.logger.debug(f"Skipping opportunity found in recent database: {opp.token_symbol} {opp.buy_exchange} -> {opp.sell_exchange}")
                continue
            
            # This is a new opportunity
            current_scan_keys.add(opp_key)
            self.recent_opportunities.add(opp_key)
            new_opportunities.append(opp)
            
        return new_opportunities
    
    def _find_recent_database_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Check if similar opportunity exists in database within last 30 minutes"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=30)
        
        existing = ArbitrageOpportunity.query.filter(
            ArbitrageOpportunity.token_id == opportunity.token_id,
            ArbitrageOpportunity.buy_exchange == opportunity.buy_exchange,
            ArbitrageOpportunity.sell_exchange == opportunity.sell_exchange,
            ArbitrageOpportunity.timestamp >= cutoff_time
        ).first()
        
        return existing is not None

    def _record_scan_history(self, total_opportunities: int, new_opportunities: int, 
                           exchanges_scanned: int, scan_start_time: float):
        """Record scan history for all users"""
        try:
            scan_duration = time.time() - scan_start_time
            
            # Get all active users
            users = User.query.filter(User._is_active == True).all()
            
            for user in users:
                # Create scan history record
                scan_history = ScanHistory(
                    user_id=user.id,
                    scan_type='scheduled',
                    tokens_scanned=total_opportunities,
                    exchanges_scanned=exchanges_scanned,
                    opportunities_found=new_opportunities,
                    scan_duration=scan_duration
                )
                db.session.add(scan_history)
            
            db.session.commit()
            self.logger.info(f"Recorded scan history for {len(users)} users: {new_opportunities} opportunities found")
            
        except Exception as e:
            self.logger.error(f"Error recording scan history: {str(e)}")
            db.session.rollback()
    
    def _store_opportunities(self, opportunities: List[ArbitrageOpportunity]):
        """Store new opportunities in database"""
        try:
            # Clean up old opportunities (older than 2 hours)
            cutoff_time = datetime.utcnow() - timedelta(hours=2)
            deleted_count = ArbitrageOpportunity.query.filter(
                ArbitrageOpportunity.timestamp < cutoff_time
            ).delete()
            
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old opportunities")
            
            # Store new opportunities
            for opp in opportunities:
                db.session.add(opp)
            
            db.session.commit()
            self.logger.info(f"Stored {len(opportunities)} new opportunities in database")
            
        except Exception as e:
            self.logger.error(f"Error storing opportunities: {str(e)}")
            db.session.rollback()
    
    def _send_consolidated_notifications(self, opportunities: List[ArbitrageOpportunity]):
        """Send consolidated notifications to users (one per token per user)"""
        try:
            # Get users with arbitrage notifications enabled and active
            users_with_notifications = User.query.join(User.notification_settings).filter(
                User.notification_settings.has(arbitrage_notifications=True),
                User._is_active == True
            ).all()
            
            if not users_with_notifications:
                self.logger.info("No users have arbitrage notifications enabled")
                return
            
            # Group opportunities by token to send consolidated notifications
            token_opportunities = {}
            for opp in opportunities:
                if opp.token_symbol not in token_opportunities:
                    token_opportunities[opp.token_symbol] = []
                token_opportunities[opp.token_symbol].append(opp)
            
            total_notifications_sent = 0
            
            # Send notifications to each user
            for user in users_with_notifications:
                try:
                    # Enforce scans per month limits by tier
                    from app.config.config_manager import ConfigManager
                    tier_info = ConfigManager().get_subscription_tier(user.subscription_tier)
                    scans_limit = tier_info.get('scans_per_month', -1)
                    scans_used = user.scan_history.filter(
                        ScanHistory.created_at >= datetime.utcnow().replace(day=1)
                    ).count()
                    if isinstance(scans_limit, int) and scans_limit != -1 and scans_used >= scans_limit:
                        # Optionally notify the user about hitting the limit
                        try:
                            notif = UserNotification(
                                user_id=user.id,
                                notification_type='system_update',
                                channel='in_app',
                                title='Plan Limit Reached',
                                message=f'You have reached your monthly scan notification limit ({scans_limit}). Upgrade to Pro for unlimited alerts.'
                            )
                            db.session.add(notif)
                            notif.mark_as_sent()
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
                        continue
                    
                    # Check notification settings and limits
                    if not user.notification_settings.should_send_notification('arbitrage_opportunity'):
                        continue
                    
                    # Filter opportunities by user preferences (strict for free tier)
                    prefs = user.preferences
                    
                    user_notifications_sent = 0
                    
                    # Send one notification per token (best opportunity)
                    for token_symbol, token_opps in token_opportunities.items():
                        # Apply preference filters: limit to selected exchanges/assets if set
                        filtered = []
                        if prefs:
                            for opp in token_opps:
                                ex_ok = (not prefs.preferred_exchanges) or (
                                    opp.buy_exchange in prefs.preferred_exchanges or
                                    opp.sell_exchange in prefs.preferred_exchanges
                                )
                                asset_ok = (not prefs.preferred_assets) or (
                                    opp.token_symbol in prefs.preferred_assets or
                                    opp.token_id in prefs.preferred_assets
                                )
                                if ex_ok and asset_ok:
                                    filtered.append(opp)
                        else:
                            filtered = token_opps
                        if not filtered:
                            continue
                        # Get the best opportunity for this token (highest profit on $1000)
                        best_opportunity = max(filtered, key=lambda x: x.profit_on_1000)
                        
                        # Create notification content
                        title = f"🚀 Arbitrage: {best_opportunity.token_symbol}"
                        message = (
                            f"Buy on {best_opportunity.buy_exchange}: ${best_opportunity.buy_price:.6f}\n"
                            f"Sell on {best_opportunity.sell_exchange}: ${best_opportunity.sell_price:.6f}\n"
                            f"Profit on $1000: ${best_opportunity.profit_on_1000:.2f}\n"
                            f"Profit on $5000: ${best_opportunity.profit_on_5000:.2f}"
                        )
                        
                        data = {
                            'opportunity': best_opportunity.to_dict(),
                            'profit_1000': best_opportunity.profit_on_1000,
                            'profit_5000': best_opportunity.profit_on_5000,
                            'total_opportunities': len(token_opps)
                        }
                        
                        # Send notification
                        success = self.notification_manager.send_notification(
                            user.id, 'arbitrage_opportunity', title, message, data
                        )
                        
                        if success:
                            user_notifications_sent += 1
                            total_notifications_sent += 1
                    
                    if user_notifications_sent > 0:
                        self.logger.info(f"Sent {user_notifications_sent} notifications to user {user.id}")
                    
                except Exception as user_error:
                    self.logger.error(f"Error sending notifications to user {user.id}: {str(user_error)}")
                    continue
            
            self.logger.info(f"Total notifications sent: {total_notifications_sent}")
            
        except Exception as e:
            self.logger.error(f"Error in consolidated notifications: {str(e)}")
    
    def _cleanup_recent_opportunities(self):
        """Clean up old entries from recent opportunities tracking"""
        # Clear the set periodically to prevent memory buildup
        # In a production system, you might want to use a more sophisticated approach
        # like a time-based cache with TTL
        self.recent_opportunities.clear()
        self.last_cleanup = datetime.utcnow()
        self.logger.info("Cleaned up recent opportunities tracking")
    
    def get_status(self):
        """Get current status of the background scanner"""
        return {
            'is_running': self.is_running,
            'scan_interval': self.scan_interval,
            'min_dollar_profit': self.min_dollar_profit,
            'thread_alive': self.scan_thread.is_alive() if self.scan_thread else False,
            'recent_opportunities_count': len(self.recent_opportunities)
        }


# Global instance
background_scanner = BackgroundArbitrageScanner()
