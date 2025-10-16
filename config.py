import os
import json
from typing import Dict, List, Any

class Config:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_dir = os.path.join(self.base_dir, 'config')
        self.data_dir = os.path.join(self.base_dir, 'data')
        
        # Create directories if they don't exist
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Load API key from environment variable or file
        self.api_key = self._load_api_key()
        
        # Load configuration files
        self.exchanges = self._load_config_file('exchanges.json', self._default_exchanges())
        self.assets = self._load_config_file('assets.json', self._default_assets())
    
    def _load_api_key(self) -> str:
        """Load API key from environment variable or file"""
        # First try environment variable
        api_key = os.getenv('COINGECKO_API_KEY')
        if api_key:
            return api_key
            
        # Then try API key file
        api_key_file = os.path.join(self.config_dir, 'api_key.txt')
        if os.path.exists(api_key_file):
            with open(api_key_file, 'r') as f:
                return f.read().strip()
        
        print("Warning: No CoinGecko API key found. Using free tier (limited requests).")
        return ""
    
    def _load_config_file(self, filename: str, default_config: Dict) -> Dict:
        """Load configuration file or create with defaults if it doesn't exist"""
        filepath = os.path.join(self.config_dir, filename)
        
        if not os.path.exists(filepath):
            print(f"Creating default {filename}...")
            with open(filepath, 'w') as f:
                json.dump(default_config, f, indent=2)
            return default_config
        
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filename}: {e}. Using defaults.")
            return default_config
    
    def _default_exchanges(self) -> Dict:
        return {
            "included_exchanges": [
                "binance",
                "coinbase",
                "kraken",
                "kucoin",
                "gateio",
                "huobi",
                "bitfinex",
                "okex",
                "bybit",
                "bitstamp"
            ],
            "excluded_exchanges": [
                "some_low_volume_exchange"
            ],
            "settings": {
                "min_volume_usd": 10000,
                "require_trust_score": True,
                "min_trust_score": "green"
            }
        }
    
    def _default_assets(self) -> Dict:
        return {
            "cryptocurrencies": [
                {
                    "id": "bitcoin",
                    "symbol": "btc",
                    "name": "Bitcoin",
                    "enabled": True
                },
                {
                    "id": "ethereum", 
                    "symbol": "eth",
                    "name": "Ethereum",
                    "enabled": True
                },
                {
                    "id": "binancecoin",
                    "symbol": "bnb",
                    "name": "BNB",
                    "enabled": True
                },
                {
                    "id": "ripple",
                    "symbol": "xrp", 
                    "name": "XRP",
                    "enabled": True
                },
                {
                    "id": "cardano",
                    "symbol": "ada",
                    "name": "Cardano",
                    "enabled": True
                },
                {
                    "id": "solana",
                    "symbol": "sol",
                    "name": "Solana", 
                    "enabled": True
                },
                {
                    "id": "polkadot",
                    "symbol": "dot",
                    "name": "Polkadot",
                    "enabled": True
                },
                {
                    "id": "dogecoin",
                    "symbol": "doge",
                    "name": "Dogecoin",
                    "enabled": True
                },
                {
                    "id": "matic-network",
                    "symbol": "matic",
                    "name": "Polygon",
                    "enabled": True
                },
                {
                    "id": "litecoin",
                    "symbol": "ltc",
                    "name": "Litecoin",
                    "enabled": True
                }
            ],
            "settings": {
                "auto_discover_top_assets": True,
                "top_assets_limit": 20,
                "update_frequency_hours": 24
            }
        }
    
    def get_enabled_assets(self) -> List[str]:
        """Get list of enabled asset IDs"""
        return [asset['id'] for asset in self.assets['cryptocurrencies'] if asset.get('enabled', True)]
    
    def get_included_exchanges(self) -> List[str]:
        """Get list of included exchanges"""
        return self.exchanges['included_exchanges']
    
    def save_api_key(self, api_key: str):
        """Save API key to file"""
        api_key_file = os.path.join(self.config_dir, 'api_key.txt')
        with open(api_key_file, 'w') as f:
            f.write(api_key.strip())
        self.api_key = api_key.strip()
        print("API key saved successfully!")