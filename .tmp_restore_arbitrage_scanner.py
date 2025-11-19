"""Simplified and efficient arbitrage scanner service"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
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
        
        # Simple profit thresholds based on your requirements
        self.profit_thresholds = {
            500: 10.0,    # $500 investment ΓåÆ $10 profit (2.0%)
            1000: 50.0,   # $1000 investment ΓåÆ $50 profit (5.0%)
            5000: 100.0,  # $5000 investment ΓåÆ $100 profit (2.0%)
            10000: 500.0  # $10000 investment ΓåÆ $500 profit (5.0%)
        }
        
    def calculate_simple_profit(self, buy_price: float, sell_price: float, 
                               buy_exchange: str, sell_exchange: str, 
                               investment_amount: float) -> Tuple[float, Dict]:
        """
        Calculate profit for a specific investment amount using simple logic:
        1. Buy tokens with investment amount (minus fees)
        2. Sell tokens on other exchange (minus fees)
        3. Return net profit in USD
        """
        if buy_price <= 0 or sell_price <= 0 or sell_price <= buy_price:
            return 0.0, {}
            
        # Get exchange configurations
        exchanges = {ex['id']: ex for ex in self.config_manager.get_enabled_exchanges()}
        buy_exchange_config = exchanges.get(buy_exchange, {})
        sell_exchange_config = exchanges.get(sell_exchange, {})
        
        # Get fee rates (use taker fees for conservative estimates)
        buy_fee_rate = buy_exchange_config.get('taker_fee', 0.001)
        sell_fee_rate = sell_exchange_config.get('taker_fee', 0.001)
        
        # Simple calculation:
        # 1. Calculate how many tokens we can buy after fees
        buy_fee = investment_amount * buy_fee_rate
        net_investment = investment_amount - buy_fee
        tokens_bought = net_investment / buy_price
        
        # 2. Calculate revenue from selling tokens
        gross_revenue = tokens_bought * sell_price
        sell_fee = gross_revenue * sell_fee_rate
        net_revenue = gross_revenue - sell_fee
        
        # 3. Calculate net profit
        net_profit = net_revenue - investment_amount
        
        # Return profit and calculation details
        calculation_details = {
            'investment_amount': investment_amount,
            'buy_fee': buy_fee,
            'sell_fee': sell_fee,
            'tokens_bought': tokens_bought,
            'gross_revenue': gross_revenue,
            'net_revenue': net_revenue,
            'net_profit': net_profit,
            'profit_percentage': (net_profit / investment_amount) * 100 if investment_amount > 0 else 0
        }
        
        return max(0, net_profit), calculation_details
    
    def is_valid_opportunity(self, buy_price: float, sell_price: float, 
                           buy_exchange: str, sell_exchange: str) -> bool:
        """
        Validate if this is a legitimate arbitrage opportunity
        """
        # Basic price validation
        if buy_price <= 0 or sell_price <= 0:
            return False
            
        # Must have positive price difference
        if sell_price <= buy_price:
            return False
            
        # Price difference should be reasonable (not more than 50% difference)
        price_diff_pct = ((sell_price - buy_price) / buy_price) * 100
        if price_diff_pct > 50:
            self.logger.warning(f"Suspicious price difference: {price_diff_pct:.2f}% between {buy_exchange} (${buy_price}) and {sell_exchange} (${sell_price})")
            return False
            
        # Minimum price difference should be at least 0.1% to be worth considering
        if price_diff_pct < 0.1:
            return False
            
        return True
    
    def meets_profit_requirements(self, buy_price: float, sell_price: float,
                                 buy_exchange: str, sell_exchange: str) -> Tuple[bool, Dict]:
        """
        Check if opportunity meets the profit requirements for any investment level
        """
        profit_results = {}
        meets_any_threshold = False
        
        for investment_amount, required_profit in self.profit_thresholds.items():
            actual_profit, details = self.calculate_simple_profit(
                buy_price, sell_price, buy_exchange, sell_exchange, investment_amount
            )
            
            profit_results[f'profit_on_{investment_amount}'] = actual_profit
            profit_results[f'details_{investment_amount}'] = details
            
            # Check if this investment level meets the threshold
            if actual_profit >= required_profit:
                meets_any_threshold = True
                
        return meets_any_threshold, profit_results

    def find_arbitrage_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        Find arbitrage opportunities using simplified logic
        """
        enabled_exchanges = [ex['id'] for ex in self.config_manager.get_enabled_exchanges()]
        enabled_assets = self.config_manager.get_enabled_assets()
        token_ids = [asset['id'] for asset in enabled_assets]

        self.logger.info(f"Scanning {len(token_ids)} assets across {len(enabled_exchanges)} exchanges")

        # Get current prices
        price_data = self.price_fetcher.fetch_prices(token_ids, enabled_exchanges)

        if not price_data:
            self.logger.warning("No price data received")
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
        valid_opportunities = 0

        # Find arbitrage opportunities
        for token_id, prices in token_prices.items():
            token = next((t for t in enabled_assets if t['id'] == token_id), None)
            if not token:
                continue
                
            # Skip if we don't have prices from at least 2 exchanges
            if len(prices) < 2:
                continue
                
            # Compare all exchange pairs
            for i, buy_price_data in enumerate(prices):
                for j, sell_price_data in enumerate(prices):
                    if i >= j:  # Avoid duplicate comparisons
                        continue
                        
                    total_comparisons += 1
                    
                    buy_price = buy_price_data['price']
                    sell_price = sell_price_data['price']
                    buy_exchange = buy_price_data['exchange_id']
                    sell_exchange = sell_price_data['exchange_id']
                    
                    # Try both directions (A->B and B->A)
                    for direction in [(buy_price, sell_price, buy_exchange, sell_exchange),
                                    (sell_price, buy_price, sell_exchange, buy_exchange)]:
                        
                        bp, sp, be, se = direction
                        
                        # Validate opportunity
                        if not self.is_valid_opportunity(bp, sp, be, se):
                            continue
                            
                        # Check profit requirements
                        meets_requirements, profit_results = self.meets_profit_requirements(bp, sp, be, se)
                        
                        if meets_requirements:
                            valid_opportunities += 1
                            
                            # Create opportunity object
                            opportunity = ArbitrageOpportunity()
                            opportunity.token_id = token_id
                            opportunity.token_symbol = token['symbol']
                            opportunity.buy_exchange = be
                            opportunity.sell_exchange = se
                            opportunity.buy_price = bp
                            opportunity.sell_price = sp
                            
                            # Calculate basic metrics
                            raw_price_diff = sp - bp
                            raw_spread_pct = (raw_price_diff / bp) * 100
                            
                            opportunity.raw_spread_percent = raw_spread_pct
                            opportunity.raw_price_difference = raw_price_diff
                            
                            # Store profit data for all investment levels
                            opportunity.profit_on_500 = profit_results.get('profit_on_500', 0)
                            opportunity.profit_on_1000 = profit_results.get('profit_on_1000', 0)
                            opportunity.profit_on_5000 = profit_results.get('profit_on_5000', 0)
                            opportunity.profit_on_10000 = profit_results.get('profit_on_10000', 0)
                            
                            # Use $1000 investment for main profit percentage
                            details_1000 = profit_results.get('details_1000', {})
                            opportunity.net_profit_percent = details_1000.get('profit_percentage', 0)
                            
                            # Legacy fields for compatibility
                            opportunity.buy_fee = details_1000.get('buy_fee', 0)
                            opportunity.sell_fee = details_1000.get('sell_fee', 0)
                            opportunity.buy_slippage = 0  # Not using slippage in simplified model
                            opportunity.sell_slippage = 0
                            opportunity.min_investment_required = 500  # Minimum we calculate for
                            
                            opportunities.append(opportunity)
                            
                            self.logger.info(f"Found opportunity: {token['symbol']} {be} -> {se}, "
                                           f"${bp:.6f} -> ${sp:.6f}, "
                                           f"Profit: ${opportunity.profit_on_1000:.2f} on $1000")

        self.logger.info(f"Analyzed {total_comparisons} comparisons, found {valid_opportunities} valid opportunities")
        return opportunities

    def scan_and_store_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        Scan for arbitrage opportunities and store them in the database
        """
        try:
            # Find new opportunities
            opportunities = self.find_arbitrage_opportunities()
            
            if opportunities:
                # Clear old opportunities (older than 1 hour)
                cutoff_time = datetime.utcnow() - timedelta(hours=1)
                ArbitrageOpportunity.query.filter(
                    ArbitrageOpportunity.timestamp < cutoff_time
                ).delete()
                
                # Store new opportunities
                for opp in opportunities:
                    db.session.add(opp)
                
                db.session.commit()
                self.logger.info(f"Stored {len(opportunities)} new arbitrage opportunities")
                
                # Send notifications
                self._send_opportunity_notifications(opportunities)
            else:
                self.logger.info("No arbitrage opportunities found")
            
            return opportunities
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error in scan_and_store_opportunities: {str(e)}")
            return []
    
    def _send_opportunity_notifications(self, opportunities: List[ArbitrageOpportunity]):
        """
        Send notifications to users for new arbitrage opportunities with deduplication
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
            
            # Group opportunities by token to avoid spam
            token_opportunities = {}
            for opp in opportunities:
                if opp.token_symbol not in token_opportunities:
                    token_opportunities[opp.token_symbol] = []
                token_opportunities[opp.token_symbol].append(opp)
            
            # Send only the best opportunity per token per user
            for user in users_with_notifications:
                try:
                    notification_settings = user.notification_settings
                    if not notification_settings.should_send_notification('arbitrage_opportunity'):
                        continue
                    
                    notifications_sent = 0
                    
                    # Send one notification per token (best opportunity)
                    for token_symbol, token_opps in token_opportunities.items():
                        # Get the best opportunity for this token (highest profit on $1000)
                        best_opportunity = max(token_opps, key=lambda x: x.profit_on_1000)
                        
                        title = f"≡ƒÜÇ Arbitrage: {best_opportunity.token_symbol}"
                        message = (
                            f"Buy on {best_opportunity.buy_exchange}: ${best_opportunity.buy_price:.6f}\n"
                            f"Sell on {best_opportunity.sell_exchange}: ${best_opportunity.sell_price:.6f}\n"
                            f"Profit on $1000: ${best_opportunity.profit_on_1000:.2f}\n"
                            f"Profit on $5000: ${best_opportunity.profit_on_5000:.2f}"
                        )
                        
                        data = {
                            'opportunity': best_opportunity.to_dict(),
                            'profit_1000': best_opportunity.profit_on_1000,
                            'profit_5000': best_opportunity.profit_on_5000
                        }
                        
                        # Send notification
                        notification_manager.send_notification(
                            user.id, 'arbitrage_opportunity', title, message, data
                        )
                        
                        notifications_sent += 1
                    
                    if notifications_sent > 0:
                        self.logger.info(f"Sent {notifications_sent} notifications to user {user.id}")
                    
                except Exception as user_error:
                    self.logger.error(f"Error sending notification to user {user.id}: {str(user_error)}")
                    continue
            
        except Exception as e:
            self.logger.error(f"Error in _send_opportunity_notifications: {str(e)}")
