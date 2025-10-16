"""Arbitrage scanner service for finding and analyzing opportunities"""
import logging
from typing import Dict, List, Optional
from datetime import datetime
from app.config.config_manager import ConfigManager
from app.services.price_fetcher import EnhancedPriceFetcher
from app.models.arbitrage import ArbitrageOpportunity
from app.models.user import User, NotificationSettings
from app.services.notification_service import NotificationManager
from app.services.user_arbitrage_manager import UserArbitrageManager
from app import db

class ArbitrageScanner:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.price_fetcher = EnhancedPriceFetcher(config_manager)
        self.logger = logging.getLogger(__name__)
        
    def calculate_dollar_profits(
        self,
        buy_price: float,
        sell_price: float,
        buy_exchange: str,
        sell_exchange: str,
        token: Dict
    ) -> tuple[float, Dict, Dict]:
        """Calculate dollar-based profits for different investment amounts"""
        # Get exchange configurations
        exchanges = {ex['id']: ex for ex in self.config_manager.get_enabled_exchanges()}
        buy_exchange_config = exchanges.get(buy_exchange, {})
        sell_exchange_config = exchanges.get(sell_exchange, {})
        
        # Get fee rates
        buy_fee_rate = buy_exchange_config.get('taker_fee', 0.001)
        sell_fee_rate = sell_exchange_config.get('maker_fee', 0.001)
        
        # Get slippage from token config or use default
        slippage_rate = token.get('slippage', self.config_manager.assets.get('metadata', {}).get('default_slippage', 0.002))
        
        # Calculate raw price difference
        raw_price_difference = sell_price - buy_price
        
        # Calculate dollar profits for different investment amounts
        investment_amounts = [500, 1000, 5000, 10000]
        dollar_profits = {}
        
        for amount in investment_amounts:
            # Calculate units that can be bought with this amount
            units = amount / buy_price
            
            # Calculate total costs (fees + slippage)
            buy_fee = amount * buy_fee_rate
            buy_slippage = amount * slippage_rate
            total_buy_cost = amount + buy_fee + buy_slippage
            
            # Calculate sell revenue
            sell_revenue = units * sell_price
            sell_fee = sell_revenue * sell_fee_rate
            sell_slippage = sell_revenue * slippage_rate
            total_sell_revenue = sell_revenue - sell_fee - sell_slippage
            
            # Net profit in dollars
            net_profit_dollars = total_sell_revenue - total_buy_cost
            dollar_profits[f'profit_on_{amount}'] = max(0, net_profit_dollars)
        
        # Calculate percentage profit (for backward compatibility)
        net_profit_pct = (raw_price_difference / buy_price) * 100 if buy_price > 0 else 0
        
        # Calculate minimum investment required (considering fees and slippage)
        min_investment = max(10, buy_price * (buy_fee_rate + slippage_rate) * 100)  # At least $10 or enough to cover costs
        
        costs = {
            'buy_fee_rate': buy_fee_rate,
            'sell_fee_rate': sell_fee_rate,
            'buy_slippage_rate': slippage_rate,
            'sell_slippage_rate': slippage_rate
        }
        
        profit_data = {
            'raw_price_difference': raw_price_difference,
            'profit_on_500': dollar_profits['profit_on_500'],
            'profit_on_1000': dollar_profits['profit_on_1000'],
            'profit_on_5000': dollar_profits['profit_on_5000'],
            'profit_on_10000': dollar_profits['profit_on_10000'],
            'min_investment_required': min_investment,
            'net_profit_percent': net_profit_pct
        }
        
        return net_profit_pct, costs, profit_data

    def find_arbitrage_opportunities(self, min_dollar_profit: float = 10.0) -> List[ArbitrageOpportunity]:
        """
        Find arbitrage opportunities across all enabled exchanges and tokens
        Returns opportunities with dollar profit > min_dollar_profit for $1000 investment
        """
        enabled_exchanges = [ex['id'] for ex in self.config_manager.get_enabled_exchanges()]
        enabled_assets = self.config_manager.get_enabled_assets()
        token_ids = [asset['id'] for asset in enabled_assets]

        self.logger.info(f"Scanning for arbitrage opportunities across {len(enabled_exchanges)} exchanges and {len(token_ids)} assets")

        # Get current prices
        price_data = self.price_fetcher.fetch_prices(token_ids, enabled_exchanges)

        if not price_data:
            self.logger.warning("No price data received from price fetcher")
            return []

        # Group prices by token
        token_prices: Dict[str, List[Dict]] = {}
        for price in price_data:
            token_id = price['token_id']
            if token_id not in token_prices:
                token_prices[token_id] = []
            token_prices[token_id].append(price)

        opportunities = []
        total_comparisons = 0

        # Find arbitrage opportunities
        for token_id, prices in token_prices.items():
            token = next((t for t in enabled_assets if t['id'] == token_id), None)
            if not token:
                continue
                
            # Compare prices across exchanges
            for buy_price_data in prices:
                for sell_price_data in prices:
                    if buy_price_data['exchange_id'] == sell_price_data['exchange_id']:
                        continue
                    
                    total_comparisons += 1
                    buy_price = buy_price_data['price']
                    sell_price = sell_price_data['price']
                    
                    if sell_price <= buy_price:
                        continue
                    
                    # Calculate raw spread percentage
                    raw_spread_pct = ((sell_price - buy_price) / buy_price) * 100
                    
                    # Calculate dollar-based profits
                    net_profit_pct, costs, profit_data = self.calculate_dollar_profits(
                        buy_price,
                        sell_price,
                        buy_price_data['exchange_id'],
                        sell_price_data['exchange_id'],
                        token
                    )
                    
                    # Apply strict profit thresholds for each investment level
                    # $500 investment must yield >= $10, $1000 >= $50, $5000 >= $100, $10000 >= $500
                    meets_thresholds = (
                        profit_data['profit_on_500'] >= 10.0 and
                        profit_data['profit_on_1000'] >= 50.0 and
                        profit_data['profit_on_5000'] >= 100.0 and
                        profit_data['profit_on_10000'] >= 500.0
                    )
                    
                    if meets_thresholds:
                        opportunity = ArbitrageOpportunity()
                        opportunity.token_id = token_id
                        opportunity.token_symbol = token['symbol']
                        opportunity.buy_exchange = buy_price_data['exchange_id']
                        opportunity.sell_exchange = sell_price_data['exchange_id']
                        opportunity.buy_price = buy_price
                        opportunity.sell_price = sell_price
                        opportunity.raw_spread_percent = raw_spread_pct
                        opportunity.net_profit_percent = net_profit_pct
                        
                        # Legacy fee fields (calculated for backward compatibility)
                        opportunity.buy_fee = buy_price * costs['buy_fee_rate']
                        opportunity.sell_fee = sell_price * costs['sell_fee_rate']
                        opportunity.buy_slippage = buy_price * costs['buy_slippage_rate']
                        opportunity.sell_slippage = sell_price * costs['sell_slippage_rate']
                        
                        # New dollar-based fields
                        opportunity.raw_price_difference = profit_data['raw_price_difference']
                        opportunity.profit_on_500 = profit_data['profit_on_500']
                        opportunity.profit_on_1000 = profit_data['profit_on_1000']
                        opportunity.profit_on_5000 = profit_data['profit_on_5000']
                        opportunity.profit_on_10000 = profit_data['profit_on_10000']
                        opportunity.min_investment_required = profit_data['min_investment_required']
                        
                        opportunities.append(opportunity)

        self.logger.info(f"Analyzed {total_comparisons} price comparisons, found {len(opportunities)} profitable opportunities")
        return opportunities

    def scan_and_store_opportunities(self, min_profit_percent: float = 0.5) -> List[ArbitrageOpportunity]:
        """
        Scan for arbitrage opportunities and store them in the database
        Returns list of new opportunities found
        """
        try:
            # Find new opportunities
            opportunities = self.find_arbitrage_opportunities(min_profit_percent)
            
            if opportunities:
                # Mark existing opportunities as inactive
                ArbitrageOpportunity.query.filter_by(is_active=True).update({'is_active': False})
                
                # Store new opportunities
                for opp in opportunities:
                    db.session.add(opp)
                
                db.session.commit()
                self.logger.info(f"Found and stored {len(opportunities)} new arbitrage opportunities")
                
                # Send notifications to users
                self._send_opportunity_notifications(opportunities)
            else:
                self.logger.info("No new arbitrage opportunities found")
            
            return opportunities
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error in scan_and_store_opportunities: {str(e)}")
            return []
    
    def _send_opportunity_notifications(self, opportunities: List[ArbitrageOpportunity]):
        """
        Send notifications to users for new arbitrage opportunities
        """
        try:
            # Get all users with arbitrage notifications enabled
            users_with_notifications = db.session.query(User).join(NotificationSettings).filter(
                NotificationSettings.arbitrage_notifications == True
            ).all()
            
            if not users_with_notifications:
                self.logger.info("No users have arbitrage notifications enabled")
                return
            
            notification_manager = NotificationManager()
            user_arbitrage_manager = UserArbitrageManager()
            
            for user in users_with_notifications:
                try:
                    # Filter opportunities based on user preferences
                    user_opportunities = user_arbitrage_manager.filter_opportunities_for_user(
                        user.id, opportunities
                    )
                    
                    if not user_opportunities:
                        continue
                    
                    # Check notification settings and limits
                    notification_settings = user.notification_settings
                    if not notification_settings.should_send_notification('arbitrage_opportunity'):
                        continue
                    
                    # Send notification for the best opportunity (highest profit)
                    best_opportunity = max(user_opportunities, key=lambda x: x.net_profit_percent)
                    
                    title = f"🚀 New Arbitrage Opportunity: {best_opportunity.token_symbol}"
                    message = (
                        f"Profit opportunity detected!\n"
                        f"Asset: {best_opportunity.token_symbol}\n"
                        f"Buy on {best_opportunity.buy_exchange} → Sell on {best_opportunity.sell_exchange}\n"
                        f"Expected Profit: {best_opportunity.net_profit_percent:.2f}%"
                    )
                    
                    data = {
                        'opportunity': best_opportunity.to_dict(),
                        'profit_percent': best_opportunity.net_profit_percent,
                        'total_opportunities': len(user_opportunities)
                    }
                    
                    # Send notification through all enabled channels
                    notification_manager.send_notification(
                        user.id, 'arbitrage_opportunity', title, message, data
                    )
                    
                    self.logger.info(f"Sent arbitrage notification to user {user.id} for {best_opportunity.token_symbol}")
                    
                except Exception as user_error:
                    self.logger.error(f"Error sending notification to user {user.id}: {str(user_error)}")
                    continue
            
        except Exception as e:
            self.logger.error(f"Error in _send_opportunity_notifications: {str(e)}")