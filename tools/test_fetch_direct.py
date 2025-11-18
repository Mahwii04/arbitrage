import logging
import os
import sys
sys.path.insert(0, os.path.abspath('.'))
from app.config.config_manager import ConfigManager
from app.services.price_fetcher import EnhancedPriceFetcher

logging.basicConfig(level=logging.INFO)

def main():
    cm = ConfigManager()
    fetcher = EnhancedPriceFetcher(cm)
    tokens = ['bitcoin', 'ethereum']
    # Use a subset of common exchanges to test direct fallbacks
    exchanges = ['binance', 'coinbase', 'kraken', 'kucoin', 'bitfinex']
    prices = fetcher.fetch_prices(tokens, exchanges)
    print(f"Fetched {len(prices)} prices")
    for p in prices:
        print(p)

if __name__ == '__main__':
    main()