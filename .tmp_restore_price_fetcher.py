"""Enhanced price fetcher service with rate limiting and error handling"""
import time
import logging
from typing import Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from app.config.config_manager import ConfigManager

class EnhancedPriceFetcher:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.base_url = "https://api.coingecko.com/api/v3"
        self.session = self._create_session()
        self.logger = logging.getLogger(__name__)
        self.rate_limit_pause = 7  # seconds between requests
        self.last_request_time = 0
        self.max_retries = 3
        self.backoff_factor = 2
    
    def _create_session(self) -> requests.Session:
        """Create a robust session with retry strategy"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set headers
        session.headers.update({
            'User-Agent': 'ArbitrageBot/1.0',
            'Accept': 'application/json'
        })
        
        return session
    
    def _handle_rate_limit(self):
        """Handle rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_pause:
            sleep_time = self.rate_limit_pause - time_since_last
            self.logger.debug(f"Rate limit: Sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def fetch_prices(self, tokens: List[str], exchanges: List[str]) -> List[Dict]:
        """
        Fetch prices for specified tokens from specified exchanges
        Returns list of price data with exchange and token information
        """
        self.logger.info(f"Fetching prices for {len(tokens)} tokens across {len(exchanges)} exchanges")
        all_results = []
        failed_tokens = []
        
        for token in tokens:
            success = False
            retry_count = 0
            
            while not success and retry_count < self.max_retries:
                try:
                    self._handle_rate_limit()
                    
                    url = f"{self.base_url}/coins/{token}/tickers"
                    response = self.session.get(url, timeout=15)
                    
                    if response.status_code == 429:
                        wait_time = min(60 * (2 ** retry_count), 300)  # Exponential backoff, max 5 minutes
                        self.logger.warning(f"Rate limit hit for {token}, waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                        retry_count += 1
                        continue
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if 'tickers' in data:
                            token_results = []
                            coin_symbol = str(data.get('symbol', token)).upper()
                            # Filter tickers by our supported exchanges
                            for ticker in data['tickers']:
                                market = ticker.get('market', {})
                                exchange_id = market.get('identifier')
                                base = str(ticker.get('base', '')).upper()
                                target = str(ticker.get('target', '')).upper()
                                last = ticker.get('last')
                                converted_last = ticker.get('converted_last') or {}
                                
                                if not exchange_id:
                                    continue
                                
                                if exchange_id in exchanges:
                                    try:
                                        # Prefer Coingecko-provided USD conversion when available
                                        usd_price = None
                                        if isinstance(converted_last, dict) and 'usd' in converted_last:
                                            try:
                                                usd_price = float(converted_last['usd'])
                                            except (ValueError, TypeError):
                                                usd_price = None
                                        
                                        # Fallback: accept stablecoin quotes as USD equivalents
                                        allowed_usd_targets = {'USD', 'USDT', 'USDC', 'BUSD'}
                                        if usd_price is None and last is not None and target in allowed_usd_targets:
                                            usd_price = float(last)
                                        
                                        # If we still can't normalize to USD, skip this ticker to avoid extreme local currency values
                                        if usd_price is None:
                                            self.logger.debug(
                                                f"Skipping non-USD quote for {token} on {exchange_id}: base={base}, target={target}, "
                                                f"last={last}, converted_last={converted_last}"
                                            )
                                            continue
                                        
                                        # Volume handling
                                        volume = float(ticker.get('volume', 0)) if ticker.get('volume') is not None else 0.0
                                        if volume < 0:
                                            volume = 0.0
                                        
                                        # Validate normalized USD price
                                        if usd_price > 0:
                                            if usd_price < 0.00001:
                                                self.logger.warning(
                                                    f"Suspiciously low USD price for {token} on {exchange_id}: ${usd_price} "
                                                    f"(base={base}, target={target}, last={last})"
                                                )
                                                continue
                                            
                                            # Reject extreme outliers
                                            if usd_price > 500000:
                                                self.logger.warning(
                                                    f"Extremely high USD price rejected for {token} on {exchange_id}: ${usd_price} "
                                                    f"(base={base}, target={target}, last={last}, converted_last={converted_last})"
                                                )
                                                continue
                                            
                                            # Log unusual but possible high prices
                                            if usd_price > 200000:
                                                self.logger.warning(
                                                    f"Unusually high USD price for {token} on {exchange_id}: ${usd_price} "
                                                    f"(base={base}, target={target})"
                                                )
                                            
                                            # Non-Bitcoin assets shouldn't exceed $150K typically
                                            if token != 'bitcoin' and usd_price > 150000:
                                                self.logger.warning(
                                                    f"Suspiciously high USD price for non-Bitcoin asset {token} on {exchange_id}: ${usd_price}"
                                                )
                                                continue
                                            
                                            token_results.append({
                                                'token_id': token,
                                                'token_symbol': coin_symbol,
                                                'exchange_id': exchange_id,
                                                'price': usd_price,
                                                'volume': volume,
                                                'timestamp': time.time()
                                            })
                                        else:
                                            self.logger.warning(
                                                f"Invalid USD price (non-positive) for {token} on {exchange_id}: ${usd_price} "
                                                f"(base={base}, target={target}, last={last})"
                                            )
                                    except (ValueError, TypeError) as e:
                                        self.logger.warning(f"Invalid price data for {token} on {exchange_id}: {e}")
                                        continue
                            
                            all_results.extend(token_results)
                            success = True
                            self.logger.debug(f"Successfully fetched {len(token_results)} normalized USD prices for {token}")
                        else:
                            self.logger.warning(f"No tickers data for {token}")
                            success = True  # Don't retry for missing data
                    
                    elif response.status_code in [404, 400]:
                        self.logger.warning(f"Token {token} not found or invalid (status: {response.status_code})")
                        success = True  # Don't retry for client errors
                    
                    else:
                        self.logger.error(f"API Error for {token}: {response.status_code} - {response.text[:200]}")
                        retry_count += 1
                        if retry_count < self.max_retries:
                            wait_time = self.backoff_factor ** retry_count
                            self.logger.info(f"Retrying {token} in {wait_time} seconds... (attempt {retry_count + 1}/{self.max_retries})")
                            time.sleep(wait_time)
                        
                except requests.exceptions.Timeout:
                    self.logger.warning(f"Timeout fetching {token}, attempt {retry_count + 1}/{self.max_retries}")
                    retry_count += 1
                    if retry_count < self.max_retries:
                        time.sleep(self.backoff_factor ** retry_count)
                        
                except requests.exceptions.ConnectionError as e:
                    self.logger.error(f"Connection error for {token}: {str(e)}")
                    retry_count += 1
                    if retry_count < self.max_retries:
                        wait_time = self.backoff_factor ** retry_count
                        self.logger.info(f"Retrying {token} in {wait_time} seconds due to connection error...")
                        time.sleep(wait_time)
                        
                except Exception as e:
                    self.logger.error(f"Unexpected error fetching {token}: {str(e)}")
                    retry_count += 1
                    if retry_count < self.max_retries:
                        time.sleep(self.backoff_factor ** retry_count)
            
            if not success:
                failed_tokens.append(token)
                self.logger.error(f"Failed to fetch prices for {token} after {self.max_retries} attempts")
        
        if failed_tokens:
            self.logger.warning(f"Failed to fetch prices for {len(failed_tokens)} tokens: {failed_tokens}")
        
        self.logger.info(f"Successfully fetched {len(all_results)} price points from {len(tokens) - len(failed_tokens)}/{len(tokens)} tokens")
        return all_results
    
    def health_check(self) -> bool:
        """Check if the API is accessible"""
        try:
            response = self.session.get(f"{self.base_url}/ping", timeout=10)
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Health check failed: {str(e)}")
            return False
