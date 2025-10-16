"""CoinGecko API utility functions"""
import requests
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

def get_supported_exchanges() -> List[Dict]:
    """Get list of supported exchanges with metadata"""
    exchanges = [
        {
            'id': 'binance',
            'name': 'Binance',
            'logo_url': 'https://assets.coingecko.com/markets/images/52/small/binance.jpg',
            'volume_24h': '12.5B',
            'pairs_count': 2000
        },
        {
            'id': 'coinbase',
            'name': 'Coinbase',
            'logo_url': 'https://assets.coingecko.com/markets/images/23/small/Coinbase.jpg',
            'volume_24h': '8.2B',
            'pairs_count': 500
        },
        {
            'id': 'kraken',
            'name': 'Kraken',
            'logo_url': 'https://assets.coingecko.com/markets/images/29/small/kraken.jpg',
            'volume_24h': '5.1B',
            'pairs_count': 400
        },
        {
            'id': 'kucoin',
            'name': 'KuCoin',
            'logo_url': 'https://assets.coingecko.com/markets/images/61/small/kucoin.jpg',
            'volume_24h': '3.2B',
            'pairs_count': 700
        },
        {
            'id': 'gate',
            'name': 'Gate.io',
            'logo_url': 'https://assets.coingecko.com/markets/images/60/small/gate_io.jpg',
            'volume_24h': '2.8B',
            'pairs_count': 1500
        },
        {
            'id': 'huobi',
            'name': 'Huobi',
            'logo_url': 'https://assets.coingecko.com/markets/images/25/small/huobi.jpg',
            'volume_24h': '4.5B',
            'pairs_count': 900
        }
    ]
    return exchanges

def get_supported_assets() -> List[Dict]:
    """Get list of supported assets with metadata"""
    assets = [
        {'id': 'bitcoin', 'name': 'Bitcoin', 'symbol': 'btc', 'market_cap': '1.2T', 'volume_24h': '28.5B', 'coingecko_image_id': '1'},
        {'id': 'ethereum', 'name': 'Ethereum', 'symbol': 'eth', 'market_cap': '450B', 'volume_24h': '15.2B', 'coingecko_image_id': '279'},
        {'id': 'solana', 'name': 'Solana', 'symbol': 'sol', 'market_cap': '42B', 'volume_24h': '4.8B', 'coingecko_image_id': '4128'},
        {'id': 'ripple', 'name': 'XRP', 'symbol': 'xrp', 'market_cap': '45B', 'volume_24h': '5.2B', 'coingecko_image_id': '44'},
        {'id': 'cardano', 'name': 'Cardano', 'symbol': 'ada', 'market_cap': '38B', 'volume_24h': '3.9B', 'coingecko_image_id': '975'},
        {'id': 'avalanche-2', 'name': 'Avalanche', 'symbol': 'avax', 'market_cap': '35B', 'volume_24h': '3.2B', 'coingecko_image_id': '12559'},
        {'id': 'polkadot', 'name': 'Polkadot', 'symbol': 'dot', 'market_cap': '32B', 'volume_24h': '2.8B', 'coingecko_image_id': '12171'},
        {'id': 'dogecoin', 'name': 'Dogecoin', 'symbol': 'doge', 'market_cap': '25B', 'volume_24h': '2.8B', 'coingecko_image_id': '5'},
        {'id': 'shiba-inu', 'name': 'Shiba Inu', 'symbol': 'shib', 'market_cap': '22B', 'volume_24h': '2.5B', 'coingecko_image_id': '11939'},
        {'id': 'matic-network', 'name': 'Polygon', 'symbol': 'matic', 'market_cap': '20B', 'volume_24h': '2.3B', 'coingecko_image_id': '4713'},
        {'id': 'chainlink', 'name': 'Chainlink', 'symbol': 'link', 'market_cap': '18B', 'volume_24h': '2.1B', 'coingecko_image_id': '877'},
        {'id': 'litecoin', 'name': 'Litecoin', 'symbol': 'ltc', 'market_cap': '15B', 'volume_24h': '1.9B', 'coingecko_image_id': '2'},
        {'id': 'bitcoin-cash', 'name': 'Bitcoin Cash', 'symbol': 'bch', 'market_cap': '14B', 'volume_24h': '1.8B', 'coingecko_image_id': '780'},
        {'id': 'uniswap', 'name': 'Uniswap', 'symbol': 'uni', 'market_cap': '12B', 'volume_24h': '1.6B', 'coingecko_image_id': '12504'},
        {'id': 'cosmos', 'name': 'Cosmos', 'symbol': 'atom', 'market_cap': '11B', 'volume_24h': '1.5B', 'coingecko_image_id': '1481'},
        {'id': 'stellar', 'name': 'Stellar', 'symbol': 'xlm', 'market_cap': '10B', 'volume_24h': '1.4B', 'coingecko_image_id': '100'},
        {'id': 'ethereum-classic', 'name': 'Ethereum Classic', 'symbol': 'etc', 'market_cap': '9B', 'volume_24h': '1.3B', 'coingecko_image_id': '5'},
        {'id': 'monero', 'name': 'Monero', 'symbol': 'xmr', 'market_cap': '8B', 'volume_24h': '1.2B', 'coingecko_image_id': '69'},
        {'id': 'filecoin', 'name': 'Filecoin', 'symbol': 'fil', 'market_cap': '7B', 'volume_24h': '1.1B', 'coingecko_image_id': '12817'},
        {'id': 'algorand', 'name': 'Algorand', 'symbol': 'algo', 'market_cap': '6B', 'volume_24h': '1.0B', 'coingecko_image_id': '4030'},
        {'id': 'eos', 'name': 'EOS', 'symbol': 'eos', 'market_cap': '5B', 'volume_24h': '0.9B', 'coingecko_image_id': '738'},
        {'id': 'aave', 'name': 'Aave', 'symbol': 'aave', 'market_cap': '4B', 'volume_24h': '0.8B', 'coingecko_image_id': '12645'},
        {'id': 'maker', 'name': 'Maker', 'symbol': 'mkr', 'market_cap': '3B', 'volume_24h': '0.7B', 'coingecko_image_id': '1518'},
        {'id': 'synthetix', 'name': 'Synthetix', 'symbol': 'snx', 'market_cap': '2B', 'volume_24h': '0.6B', 'coingecko_image_id': '5013'},
        {'id': 'compound-governance-token', 'name': 'Compound', 'symbol': 'comp', 'market_cap': '1B', 'volume_24h': '0.5B', 'coingecko_image_id': '10775'}
    ]
    return assets

def get_exchange_info(exchange_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific exchange"""
    url = f"https://api.coingecko.com/api/v3/exchanges/{exchange_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching exchange info for {exchange_id}: {str(e)}")
        return None

def get_asset_info(asset_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific asset"""
    url = f"https://api.coingecko.com/api/v3/coins/{asset_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching asset info for {asset_id}: {str(e)}")
        return None