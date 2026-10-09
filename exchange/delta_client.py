import time
import hmac
import hashlib
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List
import aiohttp

logger = logging.getLogger("exchange.delta")

class DeltaRESTClient:
    """
    Delta Exchange REST API client (v2) supporting Global and India endpoints.
    Handles HMAC-SHA256 signature generation, products metadata, bracket orders,
    and dead-man switch timer (cancel_after).
    """
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        environment: str = "testnet",  # "global", "india", "testnet", "india_testnet"
        read_only: bool = True
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.read_only = read_only
        self.environment = environment

        # Endpoint mapping
        if environment == "global":
            self.base_url = "https://api.delta.exchange"
        elif environment == "india":
            self.base_url = "https://api.india.delta.exchange"
        elif environment == "india_testnet":
            self.base_url = "https://cdn-ind.testnet.delta.exchange"
        else:
            self.base_url = "https://testnet-api.delta.exchange"

        self.session: Optional[aiohttp.ClientSession] = None
        self.products_cache: Dict[str, Dict[str, Any]] = {}
        self.symbol_to_id: Dict[str, int] = {}

    async def init_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        await self.load_products()

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _generate_signature(self, method: str, path: str, timestamp: str, query: str = "", body: str = "") -> str:
        """
        Signature payload = method + timestamp + path + query + body
        HMAC-SHA256 signed with api_secret
        """
        message = f"{method.upper()}{timestamp}{path}{query}{body}"
        sig = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return sig

    def _get_headers(self, method: str, path: str, query: str = "", body: str = "") -> Dict[str, str]:
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AutonomousScalper/1.0"
        }
        if self.api_key and self.api_secret:
            sig = self._generate_signature(method, path, timestamp, query, body)
            headers["api-key"] = self.api_key
            headers["timestamp"] = timestamp
            headers["signature"] = sig
        return headers

    async def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.init_session()
        url = f"{self.base_url}{endpoint}"
        query_str = f"?{aiohttp.helpers.urlencode(params)}" if params else ""
        body_str = json.dumps(data) if data else ""
        
        headers = self._get_headers(method, endpoint, query_str, body_str)
        
        async with self.session.request(method, url, params=params, data=body_str if data else None, headers=headers) as resp:
            if resp.status == 429:
                logger.warning("Delta API Rate Limit Hit (429) - Backing off...")
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=429, message="Rate limit exceeded")
            
            res_json = await resp.json()
            if not resp.ok:
                logger.error(f"Delta API Error {resp.status}: {res_json}")
            return res_json

    async def load_products(self) -> Dict[str, Dict[str, Any]]:
        """Fetch and cache product metadata (lot_size, tick_size, contract_value, product_id)"""
        try:
            res = await self._request("GET", "/v2/products")
            products = res.get("result", [])
            for p in products:
                sym = p.get("symbol")
                p_id = p.get("id")
                if sym and p_id:
                    self.products_cache[sym] = {
                        "id": p_id,
                        "symbol": sym,
                        "contract_type": p.get("contract_type"),
                        "contract_value": float(p.get("contract_value", 0.001)),
                        "tick_size": float(p.get("tick_size", 0.1)),
                        "lot_size": int(p.get("lot_size", 1)),
                        "maker_commission_rate": float(p.get("maker_commission_rate", 0.0002)),
                        "taker_commission_rate": float(p.get("taker_commission_rate", 0.0005)),
                        "strike_price": float(p.get("strike_price")) if p.get("strike_price") else None
                    }
                    self.symbol_to_id[sym] = p_id
            logger.info(f"Loaded {len(self.products_cache)} products from Delta Exchange ({self.environment})")
            return self.products_cache
        except Exception as e:
            logger.error(f"Failed to fetch Delta products: {e}")
            return {}

    async def get_l2_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Fetch Level 2 Order Book snapshot"""
        return await self._request("GET", f"/v2/l2orderbook/{symbol}")

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch real-time mark and spot tickers"""
        return await self._request("GET", f"/v2/tickers/{symbol}")

    async def get_options_chain(self, underlying_asset: str = "BTC") -> List[Dict[str, Any]]:
        """Fetch full active options chain for GEX computation"""
        params = {"contract_types": "call_options,put_options", "underlying_asset": underlying_asset}
        res = await self._request("GET", "/v2/tickers", params=params)
        return res.get("result", [])

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch active open positions"""
        if self.read_only:
            return []
        res = await self._request("GET", "/v2/positions")
        return res.get("result", [])

    async def place_bracket_order(
        self,
        symbol: str,
        size_contracts: int,
        side: str,  # "buy" or "sell"
        limit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        post_only: bool = True
    ) -> Dict[str, Any]:
        """
        Places an exchange-native bracket order with attached Stop Loss and Take Profit.
        Protects the position on exchange side.
        """
        if self.read_only:
            raise PermissionError("Delta Client is in READ_ONLY mode. Live order submission blocked.")

        product_id = self.symbol_to_id.get(symbol)
        if not product_id:
            raise ValueError(f"Unknown symbol {symbol} for Delta Exchange")

        payload: Dict[str, Any] = {
            "product_id": product_id,
            "size": size_contracts,
            "side": side.lower(),
            "order_type": "limit_order" if limit_price else "market_order",
            "post_only": post_only if limit_price else False
        }
        if limit_price:
            payload["limit_price"] = str(limit_price)

        # Attach bracket stop-loss and take-profit
        bracket_order: Dict[str, Any] = {}
        if stop_loss_price:
            bracket_order["stop_loss_order"] = {
                "order_type": "market_order",
                "stop_price": str(stop_loss_price),
                "reduce_only": True
            }
        if take_profit_price:
            bracket_order["take_profit_order"] = {
                "order_type": "limit_order",
                "limit_price": str(take_profit_price),
                "reduce_only": True
            }
        if bracket_order:
            payload["bracket_order"] = bracket_order

        return await self._request("POST", "/v2/orders/bracket", data=payload)

    async def send_deadman_heartbeat(self, timeout_seconds: int = 15) -> Dict[str, Any]:
        """
        Dead-man switch: Calls /v2/orders/cancel_after.
        If the bot disconnects or crashes for > timeout_seconds, Delta auto-cancels all working orders.
        """
        if self.read_only:
            return {"status": "read_only_skip"}
        payload = {"timeout": timeout_seconds * 1000}
        return await self._request("POST", "/v2/orders/cancel_after", data=payload)

    async def cancel_all_orders(self, product_id: Optional[int] = None) -> Dict[str, Any]:
        """Cancel all open limit/stop orders"""
        if self.read_only:
            return {"status": "read_only_skip"}
        payload = {"product_id": product_id} if product_id else {}
        return await self._request("DELETE", "/v2/orders/all", data=payload)
