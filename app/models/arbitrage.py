"""Models for arbitrage opportunities and related data"""
from datetime import datetime
from app.database import db


class InvalidArbitrageOpportunityError(Exception):
    """Raised when an arbitrage opportunity fails validation"""
    pass


class ArbitrageOpportunity(db.Model):
    __tablename__ = 'arbitrage_opportunities'
    
    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.String(50), nullable=False)
    token_symbol = db.Column(db.String(10), nullable=False)
    buy_exchange = db.Column(db.String(50), nullable=False)
    sell_exchange = db.Column(db.String(50), nullable=False)
    buy_price = db.Column(db.Float, nullable=False)
    sell_price = db.Column(db.Float, nullable=False)
    raw_spread_percent = db.Column(db.Float, nullable=False)
    net_profit_percent = db.Column(db.Float, nullable=False)  # After fees and slippage
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Calculated fees and slippage
    buy_fee = db.Column(db.Float, nullable=False)
    sell_fee = db.Column(db.Float, nullable=False)
    buy_slippage = db.Column(db.Float, nullable=False)
    sell_slippage = db.Column(db.Float, nullable=False)
    
    # Dollar-based profit calculations
    raw_price_difference = db.Column(db.Float, nullable=False, default=0.0)  # Absolute dollar difference
    profit_on_500 = db.Column(db.Float, nullable=False, default=0.0)  # Profit with $500 investment
    profit_on_1000 = db.Column(db.Float, nullable=False, default=0.0)  # Profit with $1000 investment
    profit_on_5000 = db.Column(db.Float, nullable=False, default=0.0)  # Profit with $5000 investment
    profit_on_10000 = db.Column(db.Float, nullable=False, default=0.0)  # Profit with $10000 investment
    min_investment_required = db.Column(db.Float, nullable=False, default=0.0)  # Minimum amount to execute
    
    # Database-level constraint to prevent same exchange opportunities
    __table_args__ = (
        db.CheckConstraint('buy_exchange != sell_exchange', name='check_different_exchanges'),
        db.CheckConstraint('buy_price > 0', name='check_buy_price_positive'),
        db.CheckConstraint('sell_price > 0', name='check_sell_price_positive'),
        db.CheckConstraint('sell_price > buy_price', name='check_sell_higher_than_buy'),
    )
    
    def __init__(self, **kwargs):
        """Initialize with validation"""
        # Validate BEFORE calling parent __init__
        buy_exchange = kwargs.get('buy_exchange')
        sell_exchange = kwargs.get('sell_exchange')
        buy_price = kwargs.get('buy_price', 0)
        sell_price = kwargs.get('sell_price', 0)
        
        # Critical validation: exchanges must be different
        if buy_exchange and sell_exchange and buy_exchange == sell_exchange:
            raise InvalidArbitrageOpportunityError(
                f"Invalid opportunity: buy_exchange ({buy_exchange}) and sell_exchange ({sell_exchange}) cannot be the same"
            )
        
        # Validate prices
        if buy_price <= 0:
            raise InvalidArbitrageOpportunityError(f"Invalid buy_price: {buy_price} must be positive")
        if sell_price <= 0:
            raise InvalidArbitrageOpportunityError(f"Invalid sell_price: {sell_price} must be positive")
        if sell_price <= buy_price:
            raise InvalidArbitrageOpportunityError(
                f"Invalid opportunity: sell_price ({sell_price}) must be greater than buy_price ({buy_price})"
            )
        
        # Set defaults for required fields if not provided
        if 'raw_spread_percent' not in kwargs:
            kwargs['raw_spread_percent'] = 0.0
        if 'net_profit_percent' not in kwargs:
            kwargs['net_profit_percent'] = 0.0
        if 'buy_fee' not in kwargs:
            kwargs['buy_fee'] = 0.0
        if 'sell_fee' not in kwargs:
            kwargs['sell_fee'] = 0.0
        if 'buy_slippage' not in kwargs:
            kwargs['buy_slippage'] = 0.0
        if 'sell_slippage' not in kwargs:
            kwargs['sell_slippage'] = 0.0
        
        super().__init__(**kwargs)
    
    @staticmethod
    def validate_opportunity(buy_exchange: str, sell_exchange: str, buy_price: float, sell_price: float) -> tuple:
        """
        Validate opportunity parameters before creation.
        Returns (is_valid: bool, error_message: str or None)
        """
        if not buy_exchange or not sell_exchange:
            return False, "Exchange identifiers cannot be empty"
        
        if buy_exchange == sell_exchange:
            return False, f"Buy and sell exchanges cannot be the same: {buy_exchange}"
        
        if buy_price <= 0:
            return False, f"Buy price must be positive: {buy_price}"
        
        if sell_price <= 0:
            return False, f"Sell price must be positive: {sell_price}"
        
        if sell_price <= buy_price:
            return False, f"Sell price ({sell_price}) must be greater than buy price ({buy_price})"
        
        # Check for suspicious price difference (more than 50%)
        price_diff_pct = ((sell_price - buy_price) / buy_price) * 100
        if price_diff_pct > 50:
            return False, f"Suspicious price difference: {price_diff_pct:.2f}% (max allowed: 50%)"
        
        return True, None
    
    def to_dict(self):
        """Convert opportunity to dictionary"""
        return {
            'id': self.id,
            'token_id': self.token_id,
            'token_symbol': self.token_symbol,
            'buy_exchange': self.buy_exchange,
            'sell_exchange': self.sell_exchange,
            'buy_price': self.buy_price,
            'sell_price': self.sell_price,
            'raw_spread_percent': self.raw_spread_percent,
            'net_profit_percent': self.net_profit_percent,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'is_active': self.is_active,
            'buy_fee': self.buy_fee,
            'sell_fee': self.sell_fee,
            'buy_slippage': self.buy_slippage,
            'sell_slippage': self.sell_slippage,
            'raw_price_difference': self.raw_price_difference,
            'profit_on_500': self.profit_on_500,
            'profit_on_1000': self.profit_on_1000,
            'profit_on_5000': self.profit_on_5000,
            'profit_on_10000': self.profit_on_10000,
            'min_investment_required': self.min_investment_required
        }