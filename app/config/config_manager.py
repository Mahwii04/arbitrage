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
    
    def get_exchanges(self) -> List[Dict[str, Any]]:
        """Get list of all exchanges (enabled and disabled)"""
        return self.exchanges.get("exchanges", [])
    
    def get_enabled_exchanges(self) -> List[Dict[str, Any]]:
        """Get list of enabled exchanges"""
        return [ex for ex in self.exchanges.get("exchanges", []) if ex.get("enabled", False)]
    
    def get_assets(self) -> List[Dict[str, Any]]:
        """Get list of all assets (enabled and disabled)"""
        return self.assets.get("assets", [])
    
    def get_enabled_assets(self) -> List[Dict[str, Any]]:
        """Get list of enabled assets"""
        return [asset for asset in self.assets.get("assets", []) if asset.get("enabled", False)]
    
    def get_subscription_tier(self, tier_name: str) -> Dict[str, Any]:
        """Get subscription tier details"""
        tiers = self.subscription_tiers.get("subscription_tiers", {})
        # Return default free tier if tier not found
        return tiers.get(tier_name, tiers.get('free', {
            'name': 'Free',
            'max_exchanges': 2,
            'max_assets': 3,
            'scans_per_month': 500,
            'notification_channels': ['webapp']
        }))
    
    def get_all_subscription_tiers(self) -> Dict[str, Dict[str, Any]]:
        """Get all subscription tier configurations"""
        return self.subscription_tiers.get("subscription_tiers", {})
    
    def is_valid_notification_channel(self, tier_name: str, channel: str) -> bool:
        """Check if notification channel is valid for subscription tier"""
        tier = self.get_subscription_tier(tier_name)
        channels = tier.get("notification_channels", [])
        # Map 'in_app' to 'webapp' for compatibility
        if channel == 'in_app':
            return 'webapp' in channels or 'in_app' in channels
        return channel in channels
    
    def get_tier_limits(self, tier_name: str) -> Dict[str, Any]:
        """Get tier limits in a structured format"""
        tier = self.get_subscription_tier(tier_name)
        return {
            'max_exchanges': tier.get('max_exchanges', 2),
            'max_assets': tier.get('max_assets', 3),
            'scans_per_month': tier.get('scans_per_month', 500),
            'notification_channels': tier.get('notification_channels', ['webapp']),
            'is_unlimited_exchanges': tier.get('max_exchanges', 2) == -1,
            'is_unlimited_assets': tier.get('max_assets', 3) == -1,
            'is_unlimited_scans': tier.get('scans_per_month', 500) == -1
        }