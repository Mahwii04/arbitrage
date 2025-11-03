"""Quick DB check for arbitrage opportunities count"""
from app import create_app
from app.models.arbitrage import ArbitrageOpportunity

def main():
    app = create_app()
    with app.app_context():
        print("ArbitrageOpportunity count:", ArbitrageOpportunity.query.count())

if __name__ == "__main__":
    main()