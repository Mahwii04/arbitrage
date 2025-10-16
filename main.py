import pandas as pd
import os
from datetime import datetime
from config import Config
from arbitrage_finder import CryptoArbitrageFinder

class CryptoArbitrageApp:
    def __init__(self):
        self.config = Config()
        self.finder = CryptoArbitrageFinder(self.config)
    
    def setup_api_key(self):
        """Setup or update API key"""
        print("\n=== CoinGecko API Key Setup ===")
        print("Get your free API key from: https://www.coingecko.com/en/api/pricing")
        print("This will significantly increase your rate limits.")
        
        choice = input("Do you want to add/update your API key? (y/n): ").lower()
        if choice == 'y':
            api_key = input("Enter your CoinGecko API key: ").strip()
            if api_key:
                self.config.save_api_key(api_key)
                self.finder = CryptoArbitrageFinder(self.config)  # Reinitialize with new key
            else:
                print("No API key provided.")
    
    def show_configuration(self):
        """Show current configuration"""
        print("\n=== Current Configuration ===")
        print(f"Enabled Assets: {len(self.config.get_enabled_assets())}")
        print(f"Included Exchanges: {len(self.config.get_included_exchanges())}")
        print(f"API Key: {'Configured' if self.config.api_key else 'Not configured (using free tier)'}")
        
        print("\nEnabled Assets:")
        for asset in self.config.assets['cryptocurrencies']:
            if asset.get('enabled', True):
                print(f"  - {asset['name']} ({asset['symbol'].upper()})")
        
        print("\nIncluded Exchanges:")
        for exchange in self.config.exchanges['included_exchanges']:
            print(f"  - {exchange}")
    
    def find_arbitrage(self):
        """Find and display arbitrage opportunities"""
        print("\n=== Arbitrage Opportunity Finder ===")
        
        try:
            min_profit = float(input("Enter minimum net profit percentage (default 0.1): ") or "0.1")
        except ValueError:
            min_profit = 0.1
            print("Using default minimum profit: 0.1%")
        
        print("\nScanning for opportunities... This may take a few minutes.")
        
        opportunities = self.finder.find_arbitrage_opportunities(min_net_profit=min_profit)
        
        if not opportunities.empty:
            print(f"\n🎯 Found {len(opportunities)} arbitrage opportunities!")
            print("\nTop Opportunities:")
            
            # Display top 10 opportunities
            display_columns = [
                'coin_id', 'buy_exchange', 'sell_exchange', 
                'buy_price', 'sell_price', 'net_profit_percentage'
            ]
            print(opportunities[display_columns].head(10).to_string(index=False))
            
            # Save full results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.config.data_dir, f"arbitrage_{timestamp}.csv")
            opportunities.to_csv(filename, index=False)
            print(f"\n📁 Full results saved to: {filename}")
            
            # Show summary statistics
            print(f"\n📊 Summary:")
            print(f"Best opportunity: {opportunities['net_profit_percentage'].iloc[0]:.4f}%")
            print(f"Average profit: {opportunities['net_profit_percentage'].mean():.4f}%")
            print(f"Total opportunities: {len(opportunities)}")
            
        else:
            print("❌ No significant arbitrage opportunities found.")
    
    def market_overview(self):
        """Show market overview across exchanges"""
        print("\n=== Market Overview ===")
        print("Fetching current market data...")
        
        overview = self.finder.get_market_overview()
        
        if not overview.empty:
            print(f"\n✅ Market Overview - {len(overview)} Assets")
            print("="*80)
            
            # Format for better display
            display_df = overview[['asset', 'exchanges', 'min_price', 'max_price', 'price_range_percentage', 'total_volume']].copy()
            display_df['min_price'] = display_df['min_price'].round(2)
            display_df['max_price'] = display_df['max_price'].round(2)
            display_df['total_volume'] = (display_df['total_volume'] / 1000000).round(1)  # Convert to millions
            display_df = display_df.rename(columns={
                'total_volume': 'volume (M$)',
                'price_range_percentage': 'range %'
            })
            
            display_df = display_df.sort_values('range %', ascending=False)
            print(display_df.to_string(index=False))
            
            # Show some insights
            if len(overview) > 0:
                max_range_asset = overview.loc[overview['price_range_percentage'].idxmax()]
                print(f"\n📊 Insights:")
                print(f"   Largest price range: {max_range_asset['asset']} ({max_range_asset['price_range_percentage']:.2f}%)")
                print(f"   Highest: {max_range_asset['highest_exchange']} (${max_range_asset['max_price']:.2f})")
                print(f"   Lowest: {max_range_asset['lowest_exchange']} (${max_range_asset['min_price']:.2f})")
            
            # Save overview
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.config.data_dir, f"market_overview_{timestamp}.csv")
            overview.to_csv(filename, index=False)
            print(f"\n📁 Market overview saved to: {filename}")
        else:
            print("❌ No market data available. This could be due to:")
            print("   - API rate limiting")
            print("   - Network issues") 
            print("   - No exchanges meeting filter criteria")
            print("   - Try again in a few moments")    
    def run(self):
        """Main application loop"""
        while True:
            print("\n" + "="*50)
            print("🔄 Crypto Arbitrage Finder")
            print("="*50)
            print("1. Find Arbitrage Opportunities")
            print("2. Market Overview")
            print("3. Show Configuration")
            print("4. Setup API Key")
            print("5. Exit")
            
            choice = input("\nSelect option (1-5): ").strip()
            
            if choice == '1':
                self.find_arbitrage()
            elif choice == '2':
                self.market_overview()
            elif choice == '3':
                self.show_configuration()
            elif choice == '4':
                self.setup_api_key()
            elif choice == '5':
                print("Goodbye!")
                break
            else:
                print("Invalid choice. Please try again.")
            
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    app = CryptoArbitrageApp()
    app.run()