"""Service for managing user-specific arbitrage notifications"""
import logging
from typing import Dict, List, Set, Tuple, Optional
from app.config.config_manager import ConfigManager
from app.models.arbitrage import ArbitrageOpportunity
from app.models.user import User
from app import db

class UserArbitrageManager:
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self.logger = logging.getLogger(__name__)
    
    def get_users_for_notifications(self) -> List[User]:
        """Get all users who have enabled notifications"""
        try:
            # Query users who have any notification channel enabled
            from app.models.user import NotificationSettings
            users = User.query.join(NotificationSettings).filter(
                db.or_(
                    NotificationSettings.in_app_enabled == True,
                    NotificationSettings.email_enabled == True,
                    NotificationSettings.telegram_enabled == True,
                    NotificationSettings.whatsapp_enabled == True
                )
            ).all()
            return users
        except Exception as e:
            self.logger.error(f"Error getting users for notifications: {e}")
            # Fallback: return all users if notification settings table doesn't exist
            try:
                return User.query.all()
            except Exception as fallback_error:
                self.logger.error(f"Error getting all users: {fallback_error}")
                return []
    
    def get_user_allowed_exchanges(self, user: User) -> Set[str]:
        """
        Get the set of exchanges a user is allowed to receive notifications for.
        This respects both user preferences AND tier limits.
        """
        tier_info = self.config_manager.get_subscription_tier(user.subscription_tier)
        max_exchanges = tier_info.get('max_exchanges', 2)
        
        prefs = user.preferences
        
        if prefs and prefs.preferred_exchanges:
            # User has set preferences - respect them but limit by tier
            if max_exchanges == -1:  # Unlimited
                return set(prefs.preferred_exchanges)
            return set(prefs.preferred_exchanges[:max_exchanges])
        else:
            # No preferences - return default limited set
            all_exchanges = [ex['id'] for ex in self.config_manager.get_enabled_exchanges()]
            if max_exchanges == -1:  # Unlimited
                return set(all_exchanges)
            return set(all_exchanges[:max_exchanges])
    
    def get_user_allowed_assets(self, user: User) -> Set[str]:
        """
        Get the set of assets a user is allowed to receive notifications for.
        This respects both user preferences AND tier limits.
        """
        tier_info = self.config_manager.get_subscription_tier(user.subscription_tier)
        max_assets = tier_info.get('max_assets', 3)
        
        prefs = user.preferences
        
        if prefs and prefs.preferred_assets:
            # User has set preferences - respect them but limit by tier
            if max_assets == -1:  # Unlimited
                return set(prefs.preferred_assets)
            return set(prefs.preferred_assets[:max_assets])
        else:
            # No preferences - return default limited set
            all_assets = [a['id'] for a in self.config_manager.get_enabled_assets()]
            if max_assets == -1:  # Unlimited
                return set(all_assets)
            return set(all_assets[:max_assets])
    
    def filter_opportunities_for_user(
        self,
        opportunities: List[ArbitrageOpportunity],
        user: User
    ) -> List[ArbitrageOpportunity]:
        """
        Filter arbitrage opportunities based on user preferences and subscription tier.
        
        STRICT FILTERING:
        - BOTH buy_exchange AND sell_exchange must be in user's allowed exchanges
        - Asset must be in user's allowed assets
        - Profit must meet user's minimum threshold
        """
        user_exchanges = self.get_user_allowed_exchanges(user)
        user_assets = self.get_user_allowed_assets(user)
        
        prefs = user.preferences
        min_profit = prefs.min_profit_percent if prefs else 0.5
        
        filtered_opportunities = []
        for opp in opportunities:
            # STRICT: Both exchanges must be in user's allowed set
            if opp.buy_exchange not in user_exchanges:
                continue
            if opp.sell_exchange not in user_exchanges:
                continue
            
            # STRICT: Asset must be in user's allowed set (check both id and symbol)
            if opp.token_id not in user_assets and opp.token_symbol not in user_assets:
                continue
            
            # Check minimum profit threshold
            if opp.net_profit_percent < min_profit:
                continue
            
            filtered_opportunities.append(opp)
        
        return filtered_opportunities
    
    def validate_user_configuration(self, user: User) -> Tuple[bool, List[str]]:
        """
        Validate if user has a proper configuration to receive notifications.
        Returns (is_valid, list_of_issues)
        """
        issues = []
        
        # Check if user has preferences
        prefs = user.preferences
        if not prefs:
            issues.append("User preferences not configured")
            return False, issues
        
        # Check if user has notification settings
        if not user.notification_settings:
            issues.append("Notification settings not configured")
            return False, issues
        
        # Check if at least some notifications are enabled
        if not user.notification_settings.arbitrage_notifications:
            issues.append("Arbitrage notifications are disabled")
        
        # Check if user has selected at least 2 exchanges (needed for arbitrage)
        user_exchanges = self.get_user_allowed_exchanges(user)
        if len(user_exchanges) < 2:
            issues.append(f"At least 2 exchanges required for arbitrage, only {len(user_exchanges)} configured")
        
        # Check if user has selected at least 1 asset
        user_assets = self.get_user_allowed_assets(user)
        if len(user_assets) < 1:
            issues.append("At least 1 asset must be selected")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def get_notification_channels(self, user: User) -> List[str]:
        """Get available notification channels for user's subscription tier"""
        tier = self.config_manager.get_subscription_tier(user.subscription_tier)
        return tier.get('notification_channels', ['webapp'])
    
    def format_opportunity_notification(self, opportunity: ArbitrageOpportunity) -> Dict:
        """Format arbitrage opportunity for notification"""
        return {
            'title': f"Arbitrage Opportunity: {opportunity.token_symbol}",
            'message': (
                f"Buy {opportunity.token_symbol} on {opportunity.buy_exchange} at ${opportunity.buy_price:.2f}\n"
                f"Sell on {opportunity.sell_exchange} at ${opportunity.sell_price:.2f}\n"
                f"Net profit after fees: {opportunity.net_profit_percent:.2f}%"
            ),
            'data': opportunity.to_dict()
        }