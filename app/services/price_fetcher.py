"""Enhanced price fetcher service with rate limiting and error handling"""
import time
import os
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
        # Primary session (tries Pro API first if key is present)
        self.session = self._create_session(use_api_key=True)
        # Public fallback session (no API key)
        self.public_session = self._create_session(use_api_key=False)
        self.logger = logging.getLogger(__name__)
        self.rate_limit_pause = 7  # seconds between requests
        self.last_request_time = 0
        self.max_retries = 3
        self.backoff_factor = 2
        # Circuit breaker to avoid hammering Coingecko during outages
        self.cg_failures_count = 0
        self.cg_circuit_open = False
        # Force public-only mode if env requests it or if no API key
        self.force_public = bool(str(os.environ.get('COINGECKO_FORCE_PUBLIC', '') or '').strip()) or not bool(self._get_api_key())
        if self.force_public:
            # Use public session for all requests
            self.session = self.public_session
    
    def _create_session(self, use_api_key: bool = False) -> requests.Session:
        """Create a robust session with retry strategy, optionally attaching Pro API key"""
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
        
        # Attach CoinGecko Pro API key if available and requested
        if use_api_key:
            api_key = self._get_api_key()
            if api_key:
                session.headers.update({'x-cg-pro-api-key': api_key})
            else:
                # No key; this session will behave like public
                pass
        
        return session
    
    def _get_api_key(self) -> str:
        """Retrieve CoinGecko API key from environment. Keep fetcher decoupled from Flask app config."""
        try:
            return str(os.environ.get('COINGECKO_API_KEY', '') or '')
        except Exception:
            return ''
    
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
                    # If Coingecko is consistently failing, skip to direct exchange fallbacks
                    if self.cg_circuit_open:
                        self.logger.warning("Coingecko circuit open; using direct exchange fallback")
                        token_results = self._fallback_fetch_from_exchanges(token, exchanges)
                        all_results.extend(token_results)
                        success = True
                        break
                    # Use primary session (public-only if force_public is True)
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
                            
                            # If Pro returned zero normalized tickers for this token, attempt public fallback once
                            if not token_results:
                                self.logger.debug(f"No normalized tickers from Pro API for {token}. Trying public fallback...")
                                pub_resp = self.public_session.get(url, timeout=15)
                                if pub_resp.status_code == 200:
                                    data = pub_resp.json()
                                    if 'tickers' in data:
                                        # Re-run the same normalization path with public data
                                        for ticker in data['tickers']:
                                            market = ticker.get('market', {})
                                            exchange_id = market.get('identifier')
                                            base = str(ticker.get('base', '')).upper()
                                            target = str(ticker.get('target', '')).upper()
                                            last = ticker.get('last')
                                            converted_last = ticker.get('converted_last') or {}
                                            if not exchange_id or exchange_id not in exchanges:
                                                continue
                                            try:
                                                usd_price = None
                                                if isinstance(converted_last, dict) and 'usd' in converted_last:
                                                    try:
                                                        usd_price = float(converted_last['usd'])
                                                    except (ValueError, TypeError):
                                                        usd_price = None
                                                allowed_usd_targets = {'USD', 'USDT', 'USDC', 'BUSD'}
                                                if usd_price is None and last is not None and target in allowed_usd_targets:
                                                    usd_price = float(last)
                                                if usd_price is None:
                                                    continue
                                                volume = float(ticker.get('volume', 0)) if ticker.get('volume') is not None else 0.0
                                                if volume < 0:
                                                    volume = 0.0
                                                if usd_price > 0:
                                                    if usd_price < 0.00001:
                                                        continue
                                                    if usd_price > 500000:
                                                        continue
                                                    if token != 'bitcoin' and usd_price > 150000:
                                                        continue
                                                    token_results.append({
                                                        'token_id': token,
                                                        'token_symbol': coin_symbol,
                                                        'exchange_id': exchange_id,
                                                        'price': usd_price,
                                                        'volume': volume,
                                                        'timestamp': time.time()
                                                    })
                                            except (ValueError, TypeError):
                                                continue
                                else:
                                    self.logger.warning(f"Public fallback request failed for {token}: {pub_resp.status_code}")
                                    # Secondary fallback: try direct exchange APIs
                                    direct_results = self._fallback_fetch_from_exchanges(token, exchanges)
                                    token_results.extend(direct_results)
                            
                            all_results.extend(token_results)
                            success = True
                            self.logger.debug(f"Successfully fetched {len(token_results)} normalized USD prices for {token}")
                        else:
                            self.logger.warning(f"No tickers data for {token}")
                            # Try direct exchange fallback to salvage data
                            token_results = self._fallback_fetch_from_exchanges(token, exchanges)
                            all_results.extend(token_results)
                            success = True
                    
                    elif response.status_code in [404, 400]:
                        self.logger.warning(f"Token {token} not found or invalid (status: {response.status_code})")
                        success = True  # Don't retry for client errors
                    
                    else:
                        # If Pro API error, attempt single immediate public fallback before backing off
                        self.logger.error(f"API Error for {token}: {response.status_code} - {response.text[:200]}")
                        # Update circuit breaker state
                        self.cg_failures_count += 1
                        if self.cg_failures_count >= 5:
                            self.cg_circuit_open = True
                            self.logger.error("Coingecko circuit opened due to repeated failures")
                        try:
                            pub_resp = self.public_session.get(url, timeout=15)
                            if pub_resp.status_code == 200:
                                data = pub_resp.json()
                                if 'tickers' in data:
                                    token_results = []
                                    coin_symbol = str(data.get('symbol', token)).upper()
                                    for ticker in data['tickers']:
                                        market = ticker.get('market', {})
                                        exchange_id = market.get('identifier')
                                        base = str(ticker.get('base', '')).upper()
                                        target = str(ticker.get('target', '')).upper()
                                        last = ticker.get('last')
                                        converted_last = ticker.get('converted_last') or {}
                                        if not exchange_id or exchange_id not in exchanges:
                                            continue
                                        try:
                                            usd_price = None
                                            if isinstance(converted_last, dict) and 'usd' in converted_last:
                                                try:
                                                    usd_price = float(converted_last['usd'])
                                                except (ValueError, TypeError):
                                                    usd_price = None
                                            allowed_usd_targets = {'USD', 'USDT', 'USDC', 'BUSD'}
                                            if usd_price is None and last is not None and target in allowed_usd_targets:
                                                usd_price = float(last)
                                            if usd_price is None:
                                                continue
                                            volume = float(ticker.get('volume', 0)) if ticker.get('volume') is not None else 0.0
                                            if volume < 0:
                                                volume = 0.0
                                            if usd_price > 0:
                                                if usd_price < 0.00001:
                                                    continue
                                                if usd_price > 500000:
                                                    continue
                                                if token != 'bitcoin' and usd_price > 150000:
                                                    continue
                                                token_results.append({
                                                    'token_id': token,
                                                    'token_symbol': coin_symbol,
                                                    'exchange_id': exchange_id,
                                                    'price': usd_price,
                                                    'volume': volume,
                                                    'timestamp': time.time()
                                                })
                                        except (ValueError, TypeError):
                                            continue
                                    all_results.extend(token_results)
                                    success = True
                                    self.logger.debug(f"Successfully fetched {len(token_results)} normalized USD prices for {token} via public fallback")
                                else:
                                    self.logger.warning(f"No tickers data for {token} from public fallback")
                                    # Final fallback: direct exchange APIs
                                    token_results = self._fallback_fetch_from_exchanges(token, exchanges)
                                    all_results.extend(token_results)
                                    success = True if token_results else False
                            else:
                                self.logger.warning(f"Public fallback error for {token}: {pub_resp.status_code}")
                                # Final fallback: direct exchange APIs
                                token_results = self._fallback_fetch_from_exchanges(token, exchanges)
                                all_results.extend(token_results)
                                success = True if token_results else False
                        except Exception as e:
                            self.logger.error(f"Public fallback exception for {token}: {str(e)}")
                            # Final fallback: direct exchange APIs
                            token_results = self._fallback_fetch_from_exchanges(token, exchanges)
                            all_results.extend(token_results)
                            success = True if token_results else False
                        
                        if not success:
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
                    # Update circuit breaker state
                    self.cg_failures_count += 1
                    if self.cg_failures_count >= 5:
                        self.cg_circuit_open = True
                        self.logger.error("Coingecko circuit opened due to repeated connection errors")
                    # Try direct exchange fallback immediately on connection errors
                    token_results = self._fallback_fetch_from_exchanges(token, exchanges)
                    if token_results:
                        all_results.extend(token_results)
                        success = True
                        continue
                    retry_count += 1
                    if retry_count < self.max_retries:
                        wait_time = self.backoff_factor ** retry_count
                        self.logger.info(f"Retrying {token} in {wait_time} seconds due to connection error...")
                        time.sleep(wait_time)
                        
                except Exception as e:
                    self.logger.error(f"Unexpected error fetching {token}: {str(e)}")
                    # Update circuit breaker state
                    self.cg_failures_count += 1
                    if self.cg_failures_count >= 5:
                        self.cg_circuit_open = True
                        self.logger.error("Coingecko circuit opened due to repeated unexpected errors")
                    # Try direct exchange fallback immediately on unexpected errors
                    token_results = self._fallback_fetch_from_exchanges(token, exchanges)
                    if token_results:
                        all_results.extend(token_results)
                        success = True
                        continue
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
            # Prefer lightweight public simple price first; ping endpoints are often rate-limited or 5xx
            sp = self.public_session.get(
                f"{self.base_url}/simple/price", params={"ids": "bitcoin", "vs_currencies": "usd"}, timeout=10
            )
            if sp.status_code == 200:
                return True
            # Then try ping on the active session (public-only if forced)
            response = self.session.get(f"{self.base_url}/ping", timeout=10)
            if response.status_code == 200:
                return True
            # Finally try public ping
            pub_resp = self.public_session.get(f"{self.base_url}/ping", timeout=10)
            return pub_resp.status_code == 200
        except Exception as e:
            self.logger.error(f"Health check failed: {str(e)}")
            # Attempt public ping even after exception
            try:
                sp = self.public_session.get(
                    f"{self.base_url}/simple/price", params={"ids": "bitcoin", "vs_currencies": "usd"}, timeout=10
                )
                if sp.status_code == 200:
                    return True
                pub_resp = self.public_session.get(f"{self.base_url}/ping", timeout=10)
                return pub_resp.status_code == 200
            except Exception:
                return False

    # ------------------ Direct Exchange Fallbacks ------------------
    def _symbol_for_exchange(self, token_id: str, exchange_id: str) -> Optional[str]:
        """Map asset to exchange-specific symbol/pair."""
        # Find asset symbol from config
        try:
            assets = self.config_manager.get_enabled_assets()
            asset = next((a for a in assets if a.get('id') == token_id), None)
            if not asset:
                return None
            sym = asset.get('symbol', '').upper()
        except Exception:
            return None
        # Per-exchange pair formats (vs USD/USDT)
        if exchange_id == 'binance':
            return f"{sym}USDT"
        if exchange_id == 'coinbase':
            return f"{sym}-USD"
        if exchange_id == 'kraken':
            kr_sym = 'XBT' if sym == 'BTC' else sym
            return f"{kr_sym}USD"
        if exchange_id == 'kucoin':
            return f"{sym}-USDT"
        if exchange_id == 'bitfinex':
            return f"t{sym}USD"
        if exchange_id == 'gateio':
            return f"{sym}_USDT"
        if exchange_id == 'okx':
            return f"{sym}-USDT"
        if exchange_id == 'bybit':
            return f"{sym}USDT"
        if exchange_id == 'huobi':
            return f"{sym.lower()}usdt"
        return None

    def _fetch_exchange_price(self, exchange_id: str, pair: str) -> Optional[float]:
        """Fetch last or mid price from a specific exchange's public API."""
        try:
            if exchange_id == 'binance':
                r = self.public_session.get(
                    'https://api.binance.com/api/v3/ticker/price', params={'symbol': pair}, timeout=10
                )
                if r.status_code == 200:
                    return float(r.json().get('price'))
            elif exchange_id == 'coinbase':
                r = self.public_session.get(
                    f'https://api.exchange.coinbase.com/products/{pair}/ticker', timeout=10
                )
                if r.status_code == 200:
                    j = r.json()
                    # Prefer last price; fall back to mid of bid/ask
                    price = j.get('price')
                    if price is not None:
                        return float(price)
                    bid = j.get('bid')
                    ask = j.get('ask')
                    if bid and ask:
                        return (float(bid) + float(ask)) / 2.0
            elif exchange_id == 'kraken':
                r = self.public_session.get(
                    'https://api.kraken.com/0/public/Ticker', params={'pair': pair}, timeout=10
                )
                if r.status_code == 200:
                    j = r.json()
                    res = j.get('result') or {}
                    if res:
                        first = next(iter(res.values()))
                        c = first.get('c')
                        if isinstance(c, list) and c:
                            return float(c[0])
                        a = first.get('a')
                        b = first.get('b')
                        if isinstance(a, list) and isinstance(b, list) and a and b:
                            return (float(a[0]) + float(b[0])) / 2.0
            elif exchange_id == 'kucoin':
                r = self.public_session.get(
                    'https://api.kucoin.com/api/v1/market/orderbook/level1', params={'symbol': pair}, timeout=10
                )
                if r.status_code == 200:
                    data = (r.json().get('data') or {})
                    price = data.get('price')
                    if price is not None:
                        return float(price)
            elif exchange_id == 'bitfinex':
                r = self.public_session.get(
                    f'https://api-pub.bitfinex.com/v2/ticker/{pair}', timeout=10
                )
                if r.status_code == 200:
                    arr = r.json()
                    if isinstance(arr, list) and len(arr) >= 7:
                        return float(arr[6])
            elif exchange_id == 'gateio':
                r = self.public_session.get(
                    'https://api.gateio.ws/api/v4/spot/tickers', params={'currency_pair': pair}, timeout=10
                )
                if r.status_code == 200:
                    arr = r.json()
                    if isinstance(arr, list) and arr:
                        last = arr[0].get('last')
                        if last is not None:
                            return float(last)
            elif exchange_id == 'okx':
                r = self.public_session.get(
                    'https://www.okx.com/api/v5/market/ticker', params={'instId': pair}, timeout=10
                )
                if r.status_code == 200:
                    data = (r.json().get('data') or [])
                    if data:
                        last = data[0].get('last')
                        if last is not None:
                            return float(last)
            elif exchange_id == 'bybit':
                r = self.public_session.get(
                    'https://api.bybit.com/v5/market/tickers', params={'category': 'spot', 'symbol': pair}, timeout=10
                )
                if r.status_code == 200:
                    data = (r.json().get('result') or {}).get('list') or []
                    if data:
                        last = data[0].get('lastPrice')
                        if last is not None:
                            return float(last)
            elif exchange_id == 'huobi':
                r = self.public_session.get(
                    'https://api.huobi.pro/market/detail/merged', params={'symbol': pair}, timeout=10
                )
                if r.status_code == 200:
                    tick = (r.json().get('tick') or {})
                    last = tick.get('close')
                    if last is not None:
                        return float(last)
        except Exception:
            return None
        return None

    def _fallback_fetch_from_exchanges(self, token_id: str, exchanges: List[str]) -> List[Dict]:
        """Attempt to fetch prices directly from supported exchange APIs as a last resort."""
        results = []
        coin_symbol = token_id.upper()
        for ex in exchanges:
            pair = self._symbol_for_exchange(token_id, ex)
            if not pair:
                continue
            price = self._fetch_exchange_price(ex, pair)
            if price and price > 0:
                # Normalize to USD: for USDT we accept as USD equivalent here
                results.append({
                    'token_id': token_id,
                    'token_symbol': coin_symbol,
                    'exchange_id': ex,
                    'price': float(price),
                    'volume': 0.0,
                    'timestamp': time.time()
                })
        if results:
            self.logger.info(f"Direct fallback fetched {len(results)} prices for {token_id}")
        return results