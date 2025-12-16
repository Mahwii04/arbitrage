"""Dashboard service for handling dashboard-related operations"""
from datetime import datetime, timedelta
from typing import Dict, List
from flask_login import current_user
from sqlalchemy import func
from app.models.user import (
    User, UserPreferences, ScanHistory, UserNotification,
    NotificationSettings
)
from app.models.arbitrage import ArbitrageOpportunity
from app.services.arbitrage_scanner import ArbitrageScanner
from app.config.config_manager import ConfigManager

class DashboardService:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.arbitrage_scanner = ArbitrageScanner(config_manager)
    
    def get_user_dashboard_data(self, user: User) -> Dict:
        """Get all dashboard data for a user"""
        return {
            'user_info': self._get_user_info(user),
            'scan_stats': self._get_scan_statistics(user),
            'active_opportunities': self._get_active_opportunities(user),
            'recent_notifications': self._get_recent_notifications(user),
            'subscription_info': self._get_subscription_info(user),
            'exchange_stats': self._get_exchange_statistics(user)
        }
    
    def _get_user_info(self, user: User) -> Dict:
        """Get user information and preferences"""
        preferences = user.preferences or UserPreferences(user_id=user.id)
        notification_settings = user.notification_settings or NotificationSettings(user_id=user.id)
        
        return {
            'username': user.username,
            'email': user.email,
            'subscription_tier': user.subscription_tier,
            'min_profit_threshold': preferences.min_profit_percent,
            'notification_channels': {
                'email': notification_settings.email_enabled,
                'telegram': notification_settings.telegram_enabled,
                'webapp': notification_settings.in_app_enabled,
                'whatsapp': notification_settings.whatsapp_enabled
            }
        }
    
    def _get_scan_statistics(self, user: User) -> Dict:
        """Get user's scanning statistics"""
        last_24h = datetime.utcnow() - timedelta(days=1)
        last_24h_scans = user.scan_history.filter(
            ScanHistory.created_at >= last_24h
        ).all()
        
        if not last_24h_scans:
            return {
                'total_scans': 0,
                'opportunities_found': 0,
                'avg_scan_duration': 0,
                'last_scan_time': None
            }
        
        last_time = max(scan.created_at for scan in last_24h_scans)
        return {
            'total_scans': len(last_24h_scans),
            'opportunities_found': sum(scan.opportunities_found for scan in last_24h_scans),
            'avg_scan_duration': sum(scan.scan_duration for scan in last_24h_scans) / len(last_24h_scans),
            # Serialize datetime to ISO string for JSON
            'last_scan_time': last_time.isoformat() if last_time else None
        }
    
    def _get_active_opportunities(self, user: User) -> List[Dict]:
        """Get active arbitrage opportunities for user with sensible fallbacks"""
        preferences = user.preferences
        # Base query: active opportunities ordered by profit desc and recency
        base_query = ArbitrageOpportunity.query.filter_by(is_active=True).order_by(
            ArbitrageOpportunity.net_profit_percent.desc(),
            ArbitrageOpportunity.timestamp.desc()
        )

        # No preferences: return top results
        if not preferences:
            return [opp.to_dict() for opp in base_query.limit(20).all()]

        # Apply user preference filters when present
        opportunities = base_query.all()
        filtered_opportunities: List[Dict] = []

        for opp in opportunities:
            if (
                opp.net_profit_percent >= preferences.min_profit_percent and
                (not preferences.preferred_exchanges or (
                    opp.buy_exchange in preferences.preferred_exchanges or
                    opp.sell_exchange in preferences.preferred_exchanges
                )) and
                (not preferences.preferred_assets or (
                    opp.token_symbol in preferences.preferred_assets or
                    opp.token_id in preferences.preferred_assets
                ))
            ):
                filtered_opportunities.append(opp.to_dict())

        # Fallback 1: if no matches, show top current active opportunities
        if not filtered_opportunities:
            filtered_opportunities = [opp.to_dict() for opp in base_query.limit(15).all()]

        # Fallback 2: include recent arbitrage notifications if still empty
        if not filtered_opportunities:
            recent_notifs = UserNotification.query.filter_by(
                user_id=user.id, notification_type='arbitrage_opportunity', status='sent'
            ).order_by(UserNotification.created_at.desc()).limit(10).all()
            for notif in recent_notifs:
                if notif.data and isinstance(notif.data, dict):
                    opp_data = notif.data.get('opportunity')
                    if opp_data:
                        filtered_opportunities.append(opp_data)

        return filtered_opportunities
    
    def _get_recent_notifications(self, user: User) -> List[Dict]:
        """Get user's recent notifications with title/message for UI"""
        recent_notifications = UserNotification.query.filter_by(
            user_id=user.id, channel='in_app'
        ).order_by(
            UserNotification.created_at.desc()
        ).limit(5).all()

        return [
            {
                'id': notif.id,
                'type': notif.notification_type,
                'status': notif.status,
                'title': notif.title,
                'message': notif.message,
                # Serialize datetimes to ISO strings for JSON
                'created_at': notif.created_at.isoformat() if notif.created_at else None,
                'sent_at': notif.sent_at.isoformat() if notif.sent_at else None,
                'opportunity': notif.opportunity.to_dict() if notif.opportunity else None
            }
            for notif in recent_notifications
        ]
    
    def _get_subscription_info(self, user: User) -> Dict:
        """Get user's subscription information"""
        tier_info = self.config_manager.get_subscription_tier(user.subscription_tier)
        scans_this_month = user.scan_history.filter(
            ScanHistory.created_at >= datetime.utcnow().replace(day=1)
        ).count()
        scans_limit = tier_info.get('scans_per_month', 100)
        scans_limit_display = 'Unlimited' if isinstance(scans_limit, int) and scans_limit == -1 else scans_limit
        return {
            'tier_name': tier_info.get('name', user.subscription_tier),
            'scans_used': scans_this_month,
            'scans_limit': scans_limit_display,
            'max_exchanges': tier_info.get('max_exchanges', 2),
            'max_assets': tier_info.get('max_assets', 10),
            'available_features': tier_info.get('notification_channels', ['webapp'])
        }
    
    def _get_exchange_statistics(self, user: User) -> Dict:
        """Get statistics for user's configured exchanges"""
        preferences = user.preferences
        if not preferences:
            return {}
            
        enabled_exchanges = self.config_manager.get_enabled_exchanges()
        exchange_stats = {}
        
        for exchange in enabled_exchanges:
            if exchange['id'] in preferences.preferred_exchanges:
                opportunities = ArbitrageOpportunity.query.filter(
                    (ArbitrageOpportunity.buy_exchange == exchange['id']) |
                    (ArbitrageOpportunity.sell_exchange == exchange['id'])
                ).filter_by(is_active=True).all()
                
                if not opportunities:
                    exchange_stats[exchange['id']] = {
                        'name': exchange['name'],
                        'active_opportunities': 0,
                        'avg_profit': 0,
                        'best_pair': None
                    }
                    continue
                
                best_opp = max(opportunities, key=lambda x: x.net_profit_percent)
                exchange_stats[exchange['id']] = {
                    'name': exchange['name'],
                    'active_opportunities': len(opportunities),
                    'avg_profit': sum(opp.net_profit_percent for opp in opportunities) / len(opportunities),
                    'best_pair': f"{best_opp.token_symbol} ({best_opp.net_profit_percent:.2f}%)"
                }
        
        return exchange_stats
