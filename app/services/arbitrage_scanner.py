"""Simplified and efficient arbitrage scanner service"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from app.config.config_manager import ConfigManager
from app.services.price_fetcher import EnhancedPriceFetcher
from app.models.arbitrage import ArbitrageOpportunity, InvalidArbitrageOpportunityError
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
            500: 10.0,    # $500 investment -> $10 profit (2.0%)
            1000: 50.0,   # $1000 investment -> $50 profit (5.0%)
            5000: 100.0,  # $5000 investment -> $100 profit (2.0%)
            10000: 500.0  # $10000 investment -> $500 profit (5.0%)
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
        slippage_rate = 0.001  # 0.1% conservative slippage per leg
        
        # Simple calculation:
        # 1. Calculate how many tokens we can buy after fees
        buy_fee = investment_amount * buy_fee_rate
        buy_slippage = investment_amount * slippage_rate
        net_investment = investment_amount - buy_fee - buy_slippage
        tokens_bought = net_investment / buy_price
        
        # 2. Calculate revenue from selling tokens
        gross_revenue = tokens_bought * sell_price
        sell_fee = gross_revenue * sell_fee_rate
        sell_slippage = gross_revenue * slippage_rate
        net_revenue = gross_revenue - sell_fee - sell_slippage
        
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
        Validate if this is a legitimate arbitrage opportunity.
        This is the CRITICAL validation gate - be strict here.
        """
        # Basic price validation
        if buy_price <= 0 or sell_price <= 0:
            self.logger.debug(f"Invalid prices: buy={buy_price}, sell={sell_price}")
            return False
        
        # CRITICAL: Exchanges must be different
        if buy_exchange == sell_exchange:
            self.logger.warning(
                f"REJECTED: Same exchange arbitrage attempt - buy_exchange={buy_exchange}, sell_exchange={sell_exchange}. "
                f"This should never happen - check data pipeline!"
            )
            return False
        
        # Validate exchange identifiers are not empty
        if not buy_exchange or not sell_exchange:
            self.logger.warning(f"Empty exchange identifier: buy={buy_exchange}, sell={sell_exchange}")
            return False
        
        # Validate exchange identifiers are strings
        if not isinstance(buy_exchange, str) or not isinstance(sell_exchange, str):
            self.logger.warning(f"Invalid exchange type: buy={type(buy_exchange)}, sell={type(sell_exchange)}")
            return False
        
        # Must have positive price difference (sell > buy)
        if sell_price <= buy_price:
            return False
            
        # Price difference should be reasonable (not more than 50% difference)
        # Anything above this is likely bad data or manipulation
        price_diff_pct = ((sell_price - buy_price) / buy_price) * 100
        if price_diff_pct > 50:
            self.logger.warning(
                f"REJECTED: Suspicious price difference {price_diff_pct:.2f}% between "
                f"{buy_exchange} (${buy_price}) and {sell_exchange} (${sell_price})"
            )
            return False
            
        # Minimum price difference should be at least 0.1% to be worth considering
        # Below this, fees will eat all profit
        if price_diff_pct < 0.1:
            return False
        
        # Additional sanity check: log unusual but valid opportunities
        if price_diff_pct > 10:
            self.logger.info(
                f"High-value opportunity detected: {price_diff_pct:.2f}% spread "
                f"between {buy_exchange} and {sell_exchange}"
            )
            
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

        # Group and consolidate prices by token and exchange
        token_prices: Dict[str, Dict[str, List[Dict]]] = {}
        for price in price_data:
            token_id = price['token_id']
            ex_id = price['exchange_id']
            token_prices.setdefault(token_id, {}).setdefault(ex_id, []).append(price)

        def median(values: List[float]) -> float:
            s = sorted(values)
            n = len(s)
            if n == 0:
                return 0.0
            mid = n // 2
            if n % 2 == 0:
                return (s[mid - 1] + s[mid]) / 2.0
            return s[mid]

        opportunities = []
        total_comparisons = 0
        valid_opportunities = 0

        # Find arbitrage opportunities using consolidated per-exchange prices
        min_volume_threshold = 1000.0
        for token_id, per_exchange in token_prices.items():
            token = next((t for t in enabled_assets if t['id'] == token_id), None)
            if not token:
                continue
            # Build consolidated price per exchange (median to reduce outliers)
            consolidated: List[Dict] = []
            for ex_id, entries in per_exchange.items():
                prices_usd = [e['price'] for e in entries if e['price'] > 0]
                volumes = [e.get('volume', 0.0) for e in entries]
                if not prices_usd:
                    continue
                consolidated.append({
                    'exchange_id': ex_id,
                    'price': median(prices_usd),
                    'volume': sum(v for v in volumes if v and v > 0)
                })

            # Need at least two exchanges with valid consolidated price
            if len(consolidated) < 2:
                continue
            # Compare consolidated exchange pairs
            for i in range(len(consolidated)):
                for j in range(i + 1, len(consolidated)):
                    buy = consolidated[i]
                    sell = consolidated[j]
                    
                    # SAFETY CHECK: Ensure we're comparing different exchanges
                    if buy['exchange_id'] == sell['exchange_id']:
                        self.logger.error(
                            f"BUG DETECTED: Same exchange in comparison loop! "
                            f"exchange={buy['exchange_id']}, i={i}, j={j}"
                        )
                        continue
                    
                    # build both directions
                    for bp, sp, be, se, bvol, svol in [
                        (buy['price'], sell['price'], buy['exchange_id'], sell['exchange_id'], buy['volume'], sell['volume']),
                        (sell['price'], buy['price'], sell['exchange_id'], buy['exchange_id'], sell['volume'], buy['volume'])
                    ]:
                        total_comparisons += 1
                        # volume guardrails
                        if bvol < min_volume_threshold or svol < min_volume_threshold:
                            continue
                        # Validate opportunity
                        if not self.is_valid_opportunity(bp, sp, be, se):
                            continue
                        # Check profit requirements
                        meets_requirements, profit_results = self.meets_profit_requirements(bp, sp, be, se)
                        if meets_requirements:
                            try:
                                # Create opportunity with validation
                                opportunity = ArbitrageOpportunity(
                                    token_id=token_id,
                                    token_symbol=token['symbol'],
                                    buy_exchange=be,
                                    sell_exchange=se,
                                    buy_price=bp,
                                    sell_price=sp
                                )
                                raw_price_diff = sp - bp
                                raw_spread_pct = (raw_price_diff / bp) * 100
                                opportunity.raw_spread_percent = raw_spread_pct
                                opportunity.raw_price_difference = raw_price_diff
                                opportunity.profit_on_500 = profit_results.get('profit_on_500', 0)
                                opportunity.profit_on_1000 = profit_results.get('profit_on_1000', 0)
                                opportunity.profit_on_5000 = profit_results.get('profit_on_5000', 0)
                                opportunity.profit_on_10000 = profit_results.get('profit_on_10000', 0)
                                details_1000 = profit_results.get('details_1000', {})
                                opportunity.net_profit_percent = details_1000.get('profit_percentage', 0)
                                opportunity.buy_fee = details_1000.get('buy_fee', 0)
                                opportunity.sell_fee = details_1000.get('sell_fee', 0)
                                # reflect slippage estimates
                                opportunity.buy_slippage = (details_1000.get('investment_amount', 0) * 0.001)
                                opportunity.sell_slippage = (details_1000.get('gross_revenue', 0) * 0.001)
                                opportunity.min_investment_required = 500
                                
                                valid_opportunities += 1
                                opportunities.append(opportunity)
                                self.logger.info(
                                    f"Found opportunity: {token['symbol']} {be} -> {se}, ${bp:.6f} -> ${sp:.6f}, "
                                    f"Profit: ${opportunity.profit_on_1000:.2f} on $1000"
                                )
                            except InvalidArbitrageOpportunityError as e:
                                # This should never happen if is_valid_opportunity works correctly
                                # but we catch it as a safety net
                                self.logger.error(
                                    f"Validation error creating opportunity (this is a bug): {e}"
                                )
                                continue
                            except Exception as e:
                                self.logger.error(f"Unexpected error creating opportunity: {e}")
                                continue

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
