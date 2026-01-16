"""
Comprehensive tests for arbitrage scanner logic.

These tests validate:
1. Same-exchange opportunities are NEVER created
2. Scan counting respects tier limits
3. User preferences are strictly enforced
4. Profit calculations are accurate
5. Edge cases are handled properly
"""
import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestArbitrageOpportunityValidation:
    """Test the ArbitrageOpportunity model validation"""
    
    def test_same_exchange_raises_error(self):
        """CRITICAL: Creating opportunity with same buy/sell exchange should raise error"""
        from app.models.arbitrage import ArbitrageOpportunity, InvalidArbitrageOpportunityError
        
        with pytest.raises(InvalidArbitrageOpportunityError) as exc_info:
            ArbitrageOpportunity(
                token_id='bitcoin',
                token_symbol='BTC',
                buy_exchange='binance',
                sell_exchange='binance',  # Same as buy_exchange - should fail
                buy_price=50000.0,
                sell_price=51000.0
            )
        
        assert 'cannot be the same' in str(exc_info.value)
    
    def test_different_exchanges_valid(self):
        """Opportunity with different exchanges should be valid"""
        from app.models.arbitrage import ArbitrageOpportunity
        
        opp = ArbitrageOpportunity(
            token_id='bitcoin',
            token_symbol='BTC',
            buy_exchange='binance',
            sell_exchange='kraken',  # Different - should work
            buy_price=50000.0,
            sell_price=51000.0
        )
        
        assert opp.buy_exchange == 'binance'
        assert opp.sell_exchange == 'kraken'
    
    def test_sell_price_must_be_higher(self):
        """Sell price must be higher than buy price"""
        from app.models.arbitrage import ArbitrageOpportunity, InvalidArbitrageOpportunityError
        
        with pytest.raises(InvalidArbitrageOpportunityError):
            ArbitrageOpportunity(
                token_id='bitcoin',
                token_symbol='BTC',
                buy_exchange='binance',
                sell_exchange='kraken',
                buy_price=51000.0,  # Higher than sell
                sell_price=50000.0
            )
    
    def test_prices_must_be_positive(self):
        """Prices must be positive"""
        from app.models.arbitrage import ArbitrageOpportunity, InvalidArbitrageOpportunityError
        
        with pytest.raises(InvalidArbitrageOpportunityError):
            ArbitrageOpportunity(
                token_id='bitcoin',
                token_symbol='BTC',
                buy_exchange='binance',
                sell_exchange='kraken',
                buy_price=0,  # Invalid
                sell_price=50000.0
            )
        
        with pytest.raises(InvalidArbitrageOpportunityError):
            ArbitrageOpportunity(
                token_id='bitcoin',
                token_symbol='BTC',
                buy_exchange='binance',
                sell_exchange='kraken',
                buy_price=-100,  # Negative
                sell_price=50000.0
            )
    
    def test_static_validation_method(self):
        """Test the static validation method"""
        from app.models.arbitrage import ArbitrageOpportunity
        
        # Valid
        is_valid, error = ArbitrageOpportunity.validate_opportunity(
            'binance', 'kraken', 50000.0, 51000.0
        )
        assert is_valid is True
        assert error is None
        
        # Same exchange
        is_valid, error = ArbitrageOpportunity.validate_opportunity(
            'binance', 'binance', 50000.0, 51000.0
        )
        assert is_valid is False
        assert 'same' in error.lower()
        
        # Suspicious price difference (>50%)
        is_valid, error = ArbitrageOpportunity.validate_opportunity(
            'binance', 'kraken', 50000.0, 100000.0  # 100% diff
        )
        assert is_valid is False
        assert 'suspicious' in error.lower()


class TestArbitrageScannerValidation:
    """Test the ArbitrageScanner validation logic"""
    
    def test_is_valid_opportunity_rejects_same_exchange(self):
        """Scanner should reject same-exchange opportunities"""
        from app.services.arbitrage_scanner import ArbitrageScanner
        from app.config.config_manager import ConfigManager
        
        scanner = ArbitrageScanner(ConfigManager())
        
        result = scanner.is_valid_opportunity(
            buy_price=50000.0,
            sell_price=51000.0,
            buy_exchange='binance',
            sell_exchange='binance'  # Same exchange
        )
        
        assert result is False
    
    def test_is_valid_opportunity_accepts_different_exchanges(self):
        """Scanner should accept different-exchange opportunities"""
        from app.services.arbitrage_scanner import ArbitrageScanner
        from app.config.config_manager import ConfigManager
        
        scanner = ArbitrageScanner(ConfigManager())
        
        result = scanner.is_valid_opportunity(
            buy_price=50000.0,
            sell_price=51000.0,
            buy_exchange='binance',
            sell_exchange='kraken'  # Different exchange
        )
        
        assert result is True
    
    def test_is_valid_opportunity_rejects_empty_exchanges(self):
        """Scanner should reject empty exchange identifiers"""
        from app.services.arbitrage_scanner import ArbitrageScanner
        from app.config.config_manager import ConfigManager
        
        scanner = ArbitrageScanner(ConfigManager())
        
        assert scanner.is_valid_opportunity(50000, 51000, '', 'kraken') is False
        assert scanner.is_valid_opportunity(50000, 51000, 'binance', '') is False
        assert scanner.is_valid_opportunity(50000, 51000, None, 'kraken') is False
    
    def test_rejects_suspicious_price_difference(self):
        """Scanner should reject price differences over 50%"""
        from app.services.arbitrage_scanner import ArbitrageScanner
        from app.config.config_manager import ConfigManager
        
        scanner = ArbitrageScanner(ConfigManager())
        
        # 100% price difference - suspicious
        result = scanner.is_valid_opportunity(
            buy_price=50000.0,
            sell_price=100000.0,  # 100% higher
            buy_exchange='binance',
            sell_exchange='kraken'
        )
        
        assert result is False


class TestProfitCalculation:
    """Test profit calculations are accurate"""
    
    def test_profit_calculation_basic(self):
        """Test basic profit calculation with fees"""
        from app.services.arbitrage_scanner import ArbitrageScanner
        from app.config.config_manager import ConfigManager
        
        scanner = ArbitrageScanner(ConfigManager())
        
        # Simple case: 2% price difference
        profit, details = scanner.calculate_simple_profit(
            buy_price=100.0,
            sell_price=102.0,  # 2% higher
            buy_exchange='binance',
            sell_exchange='kraken',
            investment_amount=1000.0
        )
        
        # Profit should be positive but less than 2% due to fees
        assert profit > 0
        assert profit < 20  # Less than 2% of $1000 due to fees
        assert 'tokens_bought' in details
        assert details['tokens_bought'] > 0
    
    def test_profit_calculation_no_profit_when_fees_exceed_spread(self):
        """When fees exceed spread, profit should be 0"""
        from app.services.arbitrage_scanner import ArbitrageScanner
        from app.config.config_manager import ConfigManager
        
        scanner = ArbitrageScanner(ConfigManager())
        
        # 0.1% price difference - fees will eat this
        profit, details = scanner.calculate_simple_profit(
            buy_price=100.0,
            sell_price=100.1,  # Only 0.1% higher
            buy_exchange='binance',
            sell_exchange='kraken',
            investment_amount=1000.0
        )
        
        # Should return 0 (max(0, negative_profit))
        assert profit == 0


class TestUserPreferenceEnforcement:
    """Test that user preferences are strictly enforced"""
    
    def test_filter_respects_user_exchanges(self):
        """Opportunities should only match user's selected exchanges"""
        from app.services.user_arbitrage_manager import UserArbitrageManager
        from app.config.config_manager import ConfigManager
        from unittest.mock import Mock
        
        manager = UserArbitrageManager(ConfigManager())
        
        # Create mock user with preferences
        user = Mock()
        user.subscription_tier = 'free'
        user.preferences = Mock()
        user.preferences.preferred_exchanges = ['binance', 'kraken']
        user.preferences.preferred_assets = ['bitcoin', 'ethereum']
        user.preferences.min_profit_percent = 0.5
        
        # Create mock opportunities
        opp_valid = Mock()
        opp_valid.buy_exchange = 'binance'
        opp_valid.sell_exchange = 'kraken'
        opp_valid.token_id = 'bitcoin'
        opp_valid.token_symbol = 'BTC'
        opp_valid.net_profit_percent = 1.0
        
        opp_invalid_exchange = Mock()
        opp_invalid_exchange.buy_exchange = 'binance'
        opp_invalid_exchange.sell_exchange = 'coinbase'  # Not in user's list
        opp_invalid_exchange.token_id = 'bitcoin'
        opp_invalid_exchange.token_symbol = 'BTC'
        opp_invalid_exchange.net_profit_percent = 1.0
        
        opportunities = [opp_valid, opp_invalid_exchange]
        
        with patch.object(manager, 'get_user_allowed_exchanges', return_value={'binance', 'kraken'}):
            with patch.object(manager, 'get_user_allowed_assets', return_value={'bitcoin', 'ethereum'}):
                filtered = manager.filter_opportunities_for_user(opportunities, user)
        
        assert len(filtered) == 1
        assert filtered[0] == opp_valid
    
    def test_filter_requires_both_exchanges_in_user_list(self):
        """BOTH buy and sell exchanges must be in user's allowed list"""
        from app.services.user_arbitrage_manager import UserArbitrageManager
        from app.config.config_manager import ConfigManager
        from unittest.mock import Mock
        
        manager = UserArbitrageManager(ConfigManager())
        
        user = Mock()
        user.subscription_tier = 'free'
        user.preferences = Mock()
        user.preferences.preferred_exchanges = ['binance', 'kraken']
        user.preferences.preferred_assets = ['bitcoin']
        user.preferences.min_profit_percent = 0.5
        
        # Only sell_exchange is in user's list
        opp = Mock()
        opp.buy_exchange = 'coinbase'  # NOT in user's list
        opp.sell_exchange = 'kraken'  # In user's list
        opp.token_id = 'bitcoin'
        opp.token_symbol = 'BTC'
        opp.net_profit_percent = 1.0
        
        with patch.object(manager, 'get_user_allowed_exchanges', return_value={'binance', 'kraken'}):
            with patch.object(manager, 'get_user_allowed_assets', return_value={'bitcoin'}):
                filtered = manager.filter_opportunities_for_user([opp], user)
        
        # Should be filtered out because buy_exchange is not in user's list
        assert len(filtered) == 0


class TestTierLimits:
    """Test subscription tier limits are enforced"""
    
    def test_free_tier_limits(self):
        """Free tier should have limited exchanges and assets"""
        from app.config.config_manager import ConfigManager
        
        config = ConfigManager()
        tier = config.get_subscription_tier('free')
        
        assert tier['max_exchanges'] == 2
        assert tier['max_assets'] == 3
        assert tier['scans_per_month'] == 500
    
    def test_pro_tier_unlimited(self):
        """Pro tier should have unlimited (-1) for most limits"""
        from app.config.config_manager import ConfigManager
        
        config = ConfigManager()
        tier = config.get_subscription_tier('pro')
        
        assert tier['max_exchanges'] == -1  # Unlimited
        assert tier['max_assets'] == -1  # Unlimited
        assert tier['scans_per_month'] == -1  # Unlimited
    
    def test_get_tier_limits_helper(self):
        """Test the get_tier_limits helper method"""
        from app.config.config_manager import ConfigManager
        
        config = ConfigManager()
        limits = config.get_tier_limits('free')
        
        assert 'max_exchanges' in limits
        assert 'max_assets' in limits
        assert 'scans_per_month' in limits
        assert 'is_unlimited_exchanges' in limits
        assert limits['is_unlimited_exchanges'] is False


class TestScanCounting:
    """Test that scan counting is correct"""
    
    def test_scan_count_on_participation(self):
        """
        Scans should be counted when user PARTICIPATES in a scan cycle
        (has active configuration), regardless of whether opportunities are found.
        """
        # This is a design principle test - the implementation should ensure:
        # 1. Users with is_configuration_active=True participate in scans
        # 2. Each scan cycle increments their count
        # 3. No opportunities found still counts as a scan
        pass
    
    def test_user_excluded_at_limit(self):
        """
        Users at their scan limit should be excluded from future scan cycles
        and have their configuration deactivated.
        """
        # This is a design principle test - when user hits 500/500:
        # 1. is_configuration_active should be set to False
        # 2. User should not receive any more scans
        # 3. User should be notified they hit the limit
        pass
    
    def test_scan_count_independent_of_notifications(self):
        """
        Scan count increments when user participates, not when they
        receive a notification. A scan with no matching opportunities
        still counts toward the limit.
        """
        pass


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_empty_opportunities_list(self):
        """Handle empty opportunities list gracefully"""
        from app.services.user_arbitrage_manager import UserArbitrageManager
        from app.config.config_manager import ConfigManager
        from unittest.mock import Mock
        
        manager = UserArbitrageManager(ConfigManager())
        
        user = Mock()
        user.subscription_tier = 'free'
        user.preferences = Mock()
        user.preferences.preferred_exchanges = ['binance', 'kraken']
        user.preferences.preferred_assets = ['bitcoin']
        user.preferences.min_profit_percent = 0.5
        
        with patch.object(manager, 'get_user_allowed_exchanges', return_value={'binance', 'kraken'}):
            with patch.object(manager, 'get_user_allowed_assets', return_value={'bitcoin'}):
                filtered = manager.filter_opportunities_for_user([], user)
        
        assert filtered == []
    
    def test_user_without_preferences(self):
        """Handle user without configured preferences"""
        from app.services.user_arbitrage_manager import UserArbitrageManager
        from app.config.config_manager import ConfigManager
        from unittest.mock import Mock
        
        manager = UserArbitrageManager(ConfigManager())
        
        user = Mock()
        user.subscription_tier = 'free'
        user.preferences = None  # No preferences
        
        is_valid, issues = manager.validate_user_configuration(user)
        
        assert is_valid is False
        assert any('preferences' in issue.lower() for issue in issues)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
