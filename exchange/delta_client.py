import hmac
import hashlib
import time
import json
import logging
from typing import Dict, Any, List, Optional
import aiohttp

logger = logging.getLogger("delta_client")

class DeltaExchangeClient:
    """
    Async REST Client for Delta Exchange India API.
    Supports both India Demo Environment and India Production REST endpoints.
    Implements HMAC SHA-256 request authentication and rate-limiting safeguards.
    """
    DEMO_REST_URL = "https://cdn-ind.testnet.deltaex.org"
    LIVE_REST_URL = "https://api.india.delta.exchange"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        is_demo: bool = True,
        base_url: Optional[str] = None,
        timeout_seconds: float = 8.0
    ):
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.is_demo = is_demo
        self.base_url = base_url or (self.DEMO_REST_URL if is_demo else self.LIVE_REST_URL)
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: Optional[aiohttp.ClientSession] = None
        self.consecutive_errors: int = 0

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def generate_signature(self, method: str, path: str, query_string: str = "", body: str = "", timestamp: Optional[str] = None) -> tuple[str, str]:
        """
        Delta Exchange HMAC SHA256 Signature calculation:
        signature = hmac_sha256(secret, method + timestamp + path + query_string + body)
        """
        ts = timestamp or str(int(time.time()))
        query = f"?{query_string}" if query_string else ""
        payload = f"{method.upper()}{ts}{path}{query}{body}"
        
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature, ts

    def _get_headers(self, method: str, path: str, query_string: str = "", body: str = "") -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DeltaAIScalper/1.0"
        }
        if self.api_key and self.api_secret:
            sig, ts = self.generate_signature(method, path, query_string, body)
            headers["api-key"] = self.api_key
            headers["timestamp"] = ts
            headers["signature"] = sig
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        authenticated: bool = False
    ) -> Dict[str, Any]:
        session = await self.get_session()
        url = f"{self.base_url}{path}"
        query_string = ""
        
        if params:
            # Sort params for deterministic signature string
            query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            
        body_str = json.dumps(data) if data else ""
        
        headers = {}
        if authenticated:
            if not (self.api_key and self.api_secret):
                raise ValueError("API credentials (api_key and api_secret) are required for authenticated endpoints.")
            headers = self._get_headers(method, path, query_string, body_str)
        else:
            headers = {"Content-Type": "application/json", "User-Agent": "DeltaAIScalper/1.0"}

        try:
            async with session.request(
                method=method,
                url=url,
                params=params,
                data=body_str if data else None,
                headers=headers
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    self.consecutive_errors += 1
                    logger.error(f"Delta API HTTP {response.status} Error on {method} {path}: {text}")
                    return {
                        "success": False,
                        "status_code": response.status,
                        "error": text
                    }
                
                self.consecutive_errors = 0
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"success": True, "raw": text}
                    
        except Exception as e:
            self.consecutive_errors += 1
            logger.error(f"Delta API Network Exception on {method} {path}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # ==========================================
    # PUBLIC MARKET DATA ENDPOINTS
    # ==========================================
    async def get_products(self) -> Dict[str, Any]:
        """Fetch all tradable derivatives products, symbols, and product IDs."""
        return await self._request("GET", "/v2/products")

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current mark price, index price, best bid/ask, and 24h stats."""
        return await self._request("GET", f"/v2/tickers/{symbol}")

    async def get_l2_orderbook(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
        """Fetch Level 2 resting limit order depth."""
        return await self._request("GET", f"/v2/l2orderbook/{symbol}", params={"depth": depth})

    async def get_trades(self, symbol: str) -> Dict[str, Any]:
        """Fetch latest public trades."""
        return await self._request("GET", f"/v2/trades/{symbol}")

    async def get_candles(
        self,
        symbol: str,
        resolution: str = "1m",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fetch OHLCV historical candlestick data.
        Resolution: 1m, 5m, 15m, 1h, 1d
        """
        now = int(time.time())
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "start": start_time or (now - 3600 * 4),
            "end": end_time or now
        }
        return await self._request("GET", "/v2/history/candles", params=params)

    # ==========================================
    # PRIVATE AUTHENTICATED ENDPOINTS
    # ==========================================
    async def get_wallet_balances(self) -> Dict[str, Any]:
        """Fetch account equity, available balance, and cash margin."""
        return await self._request("GET", "/v2/wallet/balances", authenticated=True)

    async def get_positions(self) -> Dict[str, Any]:
        """Fetch open margined positions with liquidation price and unrealized PnL."""
        return await self._request("GET", "/v2/positions/margined", authenticated=True)

    async def set_leverage(self, product_id: int, leverage: int) -> Dict[str, Any]:
        """Configure product leverage (max 25x allowed by Risk Manager)."""
        payload = {"leverage": str(leverage)}
        return await self._request("POST", f"/v2/products/{product_id}/orders/leverage", data=payload, authenticated=True)

    async def place_order(
        self,
        product_id: int,
        size: float,
        side: str,  # "buy" or "sell"
        order_type: str = "market_order",  # "limit_order" or "market_order"
        limit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place an order with atomic SL and TP parameters.
        """
        payload: Dict[str, Any] = {
            "product_id": product_id,
            "size": int(size) if isinstance(size, int) else round(size, 4),
            "side": side.lower(),
            "order_type": order_type
        }
        if limit_price is not None:
            payload["limit_price"] = str(round(limit_price, 2))
        if stop_loss_price is not None:
            payload["stop_loss_order"] = {
                "order_type": "market_order",
                "stop_price": str(round(stop_loss_price, 2))
            }
        if take_profit_price is not None:
            payload["take_profit_order"] = {
                "order_type": "market_order",
                "stop_price": str(round(take_profit_price, 2))
            }
        if client_order_id:
            payload["client_order_id"] = client_order_id

        return await self._request("POST", "/v2/orders", data=payload, authenticated=True)

    async def cancel_order(self, order_id: str, product_id: int) -> Dict[str, Any]:
        """Cancel an open limit or trigger order."""
        payload = {"product_id": product_id}
        return await self._request("DELETE", f"/v2/orders/{order_id}", data=payload, authenticated=True)

    async def cancel_all_orders(self, product_id: Optional[int] = None) -> Dict[str, Any]:
        """Emergency order cancel for all pending orders."""
        payload = {}
        if product_id is not None:
            payload["product_id"] = product_id
        return await self._request("DELETE", "/v2/orders/all", data=payload, authenticated=True)

    async def close_position(self, product_id: int) -> Dict[str, Any]:
        """Market close entire position for product."""
        payload = {"product_id": product_id}
        return await self._request("POST", "/v2/positions/close_all", data=payload, authenticated=True)
