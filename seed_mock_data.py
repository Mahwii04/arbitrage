"""Seed a test user and a mock arbitrage opportunity, then trigger notifications"""
from app import create_app, db
from app.models.user import User, UserPreferences, NotificationSettings
from app.models.arbitrage import ArbitrageOpportunity
from app.services.background_scanner import background_scanner

def ensure_test_user(email: str, username: str = "inttest") -> User:
    user = User.query.filter_by(email=email).first()
    if user:
        return user
    user = User(email=email, username=username)
    user.set_password("Test1234!")
    db.session.add(user)
    db.session.commit()
    prefs = UserPreferences(user_id=user.id, min_profit_percent=0.5)
    db.session.add(prefs)
    settings = NotificationSettings(user_id=user.id)
    settings.in_app_enabled = True
    settings.email_enabled = False
    settings.telegram_enabled = False
    settings.whatsapp_enabled = False
    settings.arbitrage_notifications = True
    settings.min_profit_threshold = 0.1
    db.session.add(settings)
    db.session.commit()
    return user

def build_mock_opportunity() -> ArbitrageOpportunity:
    return ArbitrageOpportunity(
        token_id="bitcoin",
        token_symbol="BTC",
        buy_exchange="binance",
        sell_exchange="kraken",
        buy_price=1.00,
        sell_price=1.02,
        raw_spread_percent=2.0,
        net_profit_percent=1.5,
        buy_fee=0.001,
        sell_fee=0.001,
        buy_slippage=0.0005,
        sell_slippage=0.0005,
        raw_price_difference=0.02,
        profit_on_500=7.5,
        profit_on_1000=15.0,
        profit_on_5000=75.0,
        profit_on_10000=150.0,
        min_investment_required=100.0
    )

def main():
    app = create_app()
    app.config['TESTING'] = True
    background_scanner.init_app(app)
    with app.app_context():
        user = ensure_test_user("inttest@example.com")
        opp = build_mock_opportunity()
        # Store and notify using scanner internals
        background_scanner._store_opportunities([opp])
        background_scanner._send_consolidated_notifications([opp])
        print("Seeded mock opportunity and triggered notifications for user:", user.email)

if __name__ == "__main__":
    main()