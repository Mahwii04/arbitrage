"""Background arbitrage scanner service with improved deduplication and proper scan counting"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple, Dict
from flask import Flask
from app.config.config_manager import ConfigManager
from app.services.arbitrage_scanner import ArbitrageScanner
from app.services.notification_service import NotificationManager
from app.services.user_arbitrage_manager import UserArbitrageManager
from app.models.arbitrage import ArbitrageOpportunity, InvalidArbitrageOpportunityError
from app.models.user import User, ScanHistory, UserNotification, NotificationSettings, UserPreferences
from app import db


class ScanLimitExceededError(Exception):
    """Raised when a user has exceeded their scan limit for the billing period"""
    pass


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
        
        # Cache for user scan counts to reduce DB queries
        self._user_scan_count_cache: Dict[int, Dict] = {}  # user_id -> {count, period_start, last_updated}
        self._cache_ttl_seconds = 60  # Cache TTL
        
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
        """
        Record scan participation for users with ACTIVE configurations.
        
        SCAN COUNTING LOGIC:
        - A scan counts when the user's account PARTICIPATES in a scan cycle
        - User participates if they have an active configuration (is_configuration_active=True)
        - Counts regardless of whether opportunities are found
        - Once at limit (e.g., 500/500 for free), user is excluded from future cycles
        """
        try:
            scan_duration = time.time() - scan_start_time
            
            # Get users with ACTIVE configurations who should participate in this scan
            from app.models.user import UserPreferences
            
            participating_users = User.query.join(UserPreferences).filter(
                User._is_active == True,
                UserPreferences.is_configuration_active == True
            ).all()
            
            users_counted = 0
            users_at_limit = 0
            
            for user in participating_users:
                # Check if user has remaining scans BEFORE counting
                has_remaining, scans_used, scans_limit = self._check_user_scan_limit(user)
                
                if not has_remaining:
                    # User has hit their limit - they shouldn't be participating
                    # Deactivate their configuration
                    users_at_limit += 1
                    self._handle_user_at_limit(user, scans_used, scans_limit)
                    continue
                
                # Record scan participation for this user
                scan_history = ScanHistory(
                    user_id=user.id,
                    scan_type='scheduled',
                    tokens_scanned=len(self.config_manager.get_enabled_assets()),
                    exchanges_scanned=exchanges_scanned,
                    opportunities_found=new_opportunities,
                    scan_duration=scan_duration
                )
                db.session.add(scan_history)
                users_counted += 1
                
                # Invalidate cache for this user
                if user.id in self._user_scan_count_cache:
                    del self._user_scan_count_cache[user.id]
            
            db.session.commit()
            self.logger.info(
                f"Scan cycle recorded: {users_counted} users participated, "
                f"{users_at_limit} users at limit, {new_opportunities} opportunities found"
            )
            
        except Exception as e:
            self.logger.error(f"Error recording scan history: {str(e)}")
            db.session.rollback()
    
    def _handle_user_at_limit(self, user: User, scans_used: int, scans_limit: int):
        """
        Handle a user who has reached their scan limit.
        - Deactivate their configuration so they don't participate in future scans
        - Send them a notification (once)
        """
        try:
            # Deactivate user's configuration
            if user.preferences and user.preferences.is_configuration_active:
                user.preferences.is_configuration_active = False
                db.session.add(user.preferences)
                
                # Send limit reached notification (check if already sent today)
                self._send_limit_reached_notification(user, scans_used, scans_limit)
                
                self.logger.info(
                    f"User {user.id} reached scan limit ({scans_used}/{scans_limit}). "
                    f"Configuration deactivated."
                )
        except Exception as e:
            self.logger.error(f"Error handling user at limit {user.id}: {str(e)}")
    
    def _get_user_scan_count_for_period(self, user_id: int) -> Tuple[int, datetime]:
        """
        Get user's scan count for the current billing period with caching.
        Returns (count, period_start_date)
        
        Counts ALL scan participations (scheduled scans where user had active config),
        not just notifications received.
        """
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Check cache first
        cached = self._user_scan_count_cache.get(user_id)
        if cached:
            cache_age = (now - cached.get('last_updated', datetime.min)).total_seconds()
            if cache_age < self._cache_ttl_seconds and cached.get('period_start') == period_start:
                return cached['count'], period_start
        
        # Query database - count ALL scan participations for the period
        count = ScanHistory.query.filter(
            ScanHistory.user_id == user_id,
            ScanHistory.created_at >= period_start
        ).count()
        
        # Update cache
        self._user_scan_count_cache[user_id] = {
            'count': count,
            'period_start': period_start,
            'last_updated': now
        }
        
        return count, period_start
    
    def _check_user_scan_limit(self, user: User) -> Tuple[bool, int, int]:
        """
        Check if user has remaining scans in their billing period.
        Returns (has_remaining, used_count, limit)
        """
        tier_info = self.config_manager.get_subscription_tier(user.subscription_tier)
        scans_limit = tier_info.get('scans_per_month', -1)
        
        # -1 means unlimited
        if scans_limit == -1:
            return True, 0, -1
        
        scans_used, _ = self._get_user_scan_count_for_period(user.id)
        has_remaining = scans_used < scans_limit
        
        return has_remaining, scans_used, scans_limit
    
    def _get_participating_users(self) -> List[User]:
        """
        Get users who should participate in the current scan cycle.
        
        A user participates if:
        1. Their account is active
        2. Their configuration is active (is_configuration_active=True)
        3. They have remaining scans in their billing period
        """
        from app.models.user import UserPreferences
        
        # Get users with active configurations
        users_with_config = User.query.join(UserPreferences).filter(
            User._is_active == True,
            UserPreferences.is_configuration_active == True
        ).all()
        
        participating = []
        for user in users_with_config:
            has_remaining, scans_used, scans_limit = self._check_user_scan_limit(user)
            if has_remaining:
                participating.append(user)
            else:
                # User hit limit - handle it
                self._handle_user_at_limit(user, scans_used, scans_limit)
        
        return participating
    
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
        """
        Send consolidated notifications to users who participated in this scan cycle.
        
        NOTE: Scan counting happens in _record_scan_history, not here.
        This method only handles notification delivery for users who:
        1. Already participated in the scan (were counted)
        2. Have matching opportunities based on their preferences
        """
        try:
            # Get users who participated in this scan (active config + have remaining scans)
            participating_users = self._get_participating_users()
            
            if not participating_users:
                self.logger.info("No users participating in this scan cycle")
                return
            
            # Group opportunities by token for consolidated notifications
            token_opportunities: Dict[str, List[ArbitrageOpportunity]] = {}
            for opp in opportunities:
                if opp.token_symbol not in token_opportunities:
                    token_opportunities[opp.token_symbol] = []
                token_opportunities[opp.token_symbol].append(opp)
            
            total_notifications_sent = 0
            users_no_matching = 0
            
            # Process each participating user
            for user in participating_users:
                try:
                    # Check if user has notification settings enabled
                    if not user.notification_settings:
                        continue
                    if not user.notification_settings.arbitrage_notifications:
                        continue
                    if not user.notification_settings.should_send_notification('arbitrage_opportunity'):
                        continue
                    
                    # Get user preferences and tier limits
                    prefs = user.preferences
                    tier_info = self.config_manager.get_subscription_tier(user.subscription_tier)
                    max_exchanges = tier_info.get('max_exchanges', 2)
                    max_assets = tier_info.get('max_assets', 3)
                    allowed_channels = tier_info.get('notification_channels', ['webapp'])
                    
                    # Determine user's allowed exchanges and assets
                    user_exchanges = set()
                    user_assets = set()
                    
                    if prefs and prefs.preferred_exchanges:
                        user_exchanges = set(prefs.preferred_exchanges[:max_exchanges] if max_exchanges > 0 else prefs.preferred_exchanges)
                    else:
                        all_exchanges = [ex['id'] for ex in self.config_manager.get_enabled_exchanges()]
                        user_exchanges = set(all_exchanges[:max_exchanges] if max_exchanges > 0 else all_exchanges)
                    
                    if prefs and prefs.preferred_assets:
                        user_assets = set(prefs.preferred_assets[:max_assets] if max_assets > 0 else prefs.preferred_assets)
                    else:
                        all_assets = [a['id'] for a in self.config_manager.get_enabled_assets()]
                        user_assets = set(all_assets[:max_assets] if max_assets > 0 else all_assets)
                    
                    min_profit = prefs.min_profit_percent if prefs else 0.5
                    
                    # Filter opportunities by user's preferences
                    user_filtered_opportunities: Dict[str, List[ArbitrageOpportunity]] = {}
                    
                    for token_symbol, token_opps in token_opportunities.items():
                        matching_opps = []
                        for opp in token_opps:
                            # STRICT CHECK: Both exchanges must be in user's allowed set
                            if opp.buy_exchange not in user_exchanges:
                                continue
                            if opp.sell_exchange not in user_exchanges:
                                continue
                            
                            # STRICT CHECK: Asset must be in user's allowed set
                            if opp.token_id not in user_assets and opp.token_symbol not in user_assets:
                                continue
                            
                            # Check minimum profit threshold
                            if opp.net_profit_percent < min_profit:
                                continue
                            
                            matching_opps.append(opp)
                        
                        if matching_opps:
                            user_filtered_opportunities[token_symbol] = matching_opps
                    
                    # No matching opportunities for this user's preferences
                    if not user_filtered_opportunities:
                        users_no_matching += 1
                        continue
                    
                    # Send notifications for matching opportunities
                    user_notifications_sent = 0
                    
                    for token_symbol, filtered_opps in user_filtered_opportunities.items():
                        # Get the best opportunity for this token
                        best_opportunity = max(filtered_opps, key=lambda x: x.profit_on_1000)
                        
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
                            'total_opportunities': len(filtered_opps)
                        }
                        
                        # Check notification channel is allowed
                        if 'webapp' not in allowed_channels and 'in_app' not in allowed_channels:
                            continue
                        
                        # Send notification
                        success = self.notification_manager.send_notification(
                            user.id, 'arbitrage_opportunity', title, message, data
                        )
                        
                        if success:
                            user_notifications_sent += 1
                            total_notifications_sent += 1
                    
                    if user_notifications_sent > 0:
                        self.logger.info(
                            f"Sent {user_notifications_sent} notifications to user {user.id} "
                            f"(tier: {user.subscription_tier})"
                        )
                    
                except Exception as user_error:
                    self.logger.error(f"Error sending notifications to user {user.id}: {str(user_error)}")
                    continue
            
            self.logger.info(
                f"Notification summary: {total_notifications_sent} sent to {len(participating_users)} participants, "
                f"{users_no_matching} had no matching opportunities"
            )
            
        except Exception as e:
            self.logger.error(f"Error in consolidated notifications: {str(e)}")
    
    def _send_limit_reached_notification(self, user: User, scans_used: int, scans_limit: int):
        """Send a notification when user reaches their scan limit (once per day)"""
        try:
            # Check if we already sent this notification today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            existing = UserNotification.query.filter(
                UserNotification.user_id == user.id,
                UserNotification.notification_type == 'limit_reached',
                UserNotification.created_at >= today_start
            ).first()
            
            if existing:
                return  # Already notified today
            
            # Create limit notification
            notification = UserNotification(
                user_id=user.id,
                notification_type='limit_reached',
                channel='in_app',
                title='📊 Monthly Scan Limit Reached',
                message=(
                    f'You have reached your monthly scan notification limit ({scans_used}/{scans_limit}). '
                    f'Upgrade to Pro for unlimited alerts and never miss an opportunity!'
                ),
                data={'scans_used': scans_used, 'scans_limit': scans_limit}
            )
            db.session.add(notification)
            notification.mark_as_sent()
            db.session.commit()
            
            self.logger.info(f"Sent limit reached notification to user {user.id}")
            
        except Exception as e:
            self.logger.error(f"Error sending limit notification to user {user.id}: {str(e)}")
            db.session.rollback()
    
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
