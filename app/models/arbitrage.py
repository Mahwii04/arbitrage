"""Models for arbitrage opportunities and related data"""
from datetime import datetime
from app.database import db

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
            'timestamp': self.timestamp.isoformat(),
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