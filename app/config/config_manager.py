"""Configuration manager for the arbitrage scanner app"""
import json
import os
from typing import Dict, List, Any

class ConfigManager:
    def __init__(self, config_dir: str = "app/config"):
        self.config_dir = config_dir
        self.exchanges = self._load_json("exchanges.json")
        self.assets = self._load_json("assets.json")
        self.subscription_tiers = self._load_json("subscription_tiers.json")
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load a JSON configuration file"""
        file_path = os.path.join(self.config_dir, filename)
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Configuration file {filename} not found")
            return {}
    
    def get_enabled_exchanges(self) -> List[Dict[str, Any]]:
        """Get list of enabled exchanges"""
        return [ex for ex in self.exchanges.get("exchanges", []) if ex.get("enabled", False)]
    
    def get_enabled_assets(self) -> List[Dict[str, Any]]:
        """Get list of enabled assets"""
        return [asset for asset in self.assets.get("assets", []) if asset.get("enabled", False)]
    
    def get_subscription_tier(self, tier_name: str) -> Dict[str, Any]:
        """Get subscription tier details"""
        return self.subscription_tiers.get("subscription_tiers", {}).get(tier_name, {})
    
    def is_valid_notification_channel(self, tier_name: str, channel: str) -> bool:
        """Check if notification channel is valid for subscription tier"""
        tier = self.get_subscription_tier(tier_name)
        return channel in tier.get("notification_channels", [])