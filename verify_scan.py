from app.config.config_manager import ConfigManager
from app.services.arbitrage_scanner import ArbitrageScanner

cfg = ConfigManager()
sc = ArbitrageScanner(cfg)

print(f'Health check: {sc.price_fetcher.health_check()}')

ops = sc.find_arbitrage_opportunities()
print(f'Opportunities found: {len(ops)}')
for op in ops[:3]:
    print(f"Sample: {op.get('token_symbol')} buy {op.get('buy_exchange')} -> sell {op.get('sell_exchange')} profit={op.get('profit_percent')}%")
