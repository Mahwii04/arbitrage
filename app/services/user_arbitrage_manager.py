"""Service for managing user-specific arbitrage notifications"""
import logging
from typing import Dict, List
from app.config.config_manager import ConfigManager
from app.models.arbitrage import ArbitrageOpportunity

class UserArbitrageManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.logger = logging.getLogger(__name__)
    
    def filter_opportunities_for_user(
        self,
        opportunities: List[ArbitrageOpportunity],
        user_settings: Dict
    ) -> List[ArbitrageOpportunity]:
        """
        Filter arbitrage opportunities based on user preferences and subscription tier
        """
        # Get user's subscription tier limits
        tier = self.config_manager.get_subscription_tier(user_settings.get('subscription_tier', 'free'))
        max_exchanges = tier.get('max_exchanges', 2)
        max_assets = tier.get('max_assets', 10)
        
        # Get user's preferred exchanges and assets
        user_exchanges = set(user_settings.get('preferred_exchanges', []))
        user_assets = set(user_settings.get('preferred_assets', []))
        min_profit = user_settings.get('min_profit_percent', 0.5)
        
        # If user hasn't set preferences, use defaults up to their tier limits
        if not user_exchanges:
            exchanges = self.config_manager.get_enabled_exchanges()
            user_exchanges = set(ex['id'] for ex in exchanges[:max_exchanges])
        
        if not user_assets:
            assets = self.config_manager.get_enabled_assets()
            user_assets = set(asset['id'] for asset in assets[:max_assets])
        
        # Filter opportunities
        filtered_opportunities = []
        for opp in opportunities:
            # Check if opportunity matches user's preferences
            if (opp.buy_exchange in user_exchanges and 
                opp.sell_exchange in user_exchanges and
                opp.token_id in user_assets and
                opp.net_profit_percent >= min_profit):
                filtered_opportunities.append(opp)
        
        return filtered_opportunities
    
    def get_notification_channels(self, user_settings: Dict) -> List[str]:
        """Get available notification channels for user's subscription tier"""
        tier = self.config_manager.get_subscription_tier(user_settings.get('subscription_tier', 'free'))
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