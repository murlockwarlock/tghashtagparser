import hashlib
import hmac
import time
import urllib.parse
import logging
from typing import Any, Dict

import aiohttp

from app.db.models import Exchange
from app.services.crypto import decrypt_secret

logger = logging.getLogger(__name__)

BINGX_API_URL = "https://open-api.bingx.com"


class BingXError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"BingX API Error [{code}]: {message}")


def generate_signature(api_secret: str, params: Dict[str, Any]) -> str:
    """
    Generates HMAC-SHA256 signature for BingX API based on sorted query string.
    """
    # Sort parameters alphabetically by key
    sorted_params = sorted(params.items())
    # URL encode parameters
    query_string = urllib.parse.urlencode(sorted_params)
    
    # Hash the query string using HMAC-SHA256 with the secret key
    signature = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature


class BingXClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = BINGX_API_URL):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url

    @classmethod
    def from_exchange_model(cls, exchange: Exchange) -> "BingXClient":
        if not exchange.api_key or not exchange.api_secret:
            raise ValueError(f"Exchange {exchange.name} is missing API credentials")
        return cls(
            api_key=decrypt_secret(exchange.api_key),
            api_secret=decrypt_secret(exchange.api_secret)
        )

    def _prepare_params(self, params: Dict[str, Any] = None) -> str:
        if params is None:
            params = {}
        # Ensure timestamp is set in milliseconds
        if "timestamp" not in params:
            params["timestamp"] = int(time.time() * 1000)
            
        # Clean up None values
        clean_params = {k: str(v) for k, v in params.items() if v is not None}
        
        signature = generate_signature(self.api_secret, clean_params)
        clean_params["signature"] = signature
        return urllib.parse.urlencode(clean_params)

    async def _request(self, method: str, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        query_string = self._prepare_params(params)
        url = f"{self.base_url}{path}?{query_string}"
        
        headers = {
            "X-BX-APIKEY": self.api_key
        }
        
        async with aiohttp.ClientSession() as session:
            logger.debug("BingX %s %s", method, path)
            async with session.request(method, url, headers=headers) as response:
                data = await response.json()
                
                # BingX success response usually has code == 0
                if data.get("code") != 0:
                    raise BingXError(data.get("code", -1), data.get("msg", "Unknown error"))
                
                return data.get("data", {})

    async def get_balance(self) -> Dict[str, Any]:
        """
        Query Perpetual Swap Account Balance.
        GET /openApi/swap/v2/user/balance
        """
        return await self._request("GET", "/openApi/swap/v2/user/balance")

    async def set_leverage(self, symbol: str, leverage: int, side: str) -> Dict[str, Any]:
        """
        Set Leverage.
        POST /openApi/swap/v2/trade/leverage
        side: LONG or SHORT
        """
        params = {
            "symbol": symbol,
            "leverage": leverage,
            "side": side
        }
        return await self._request("POST", "/openApi/swap/v2/trade/leverage", params)

    async def place_order(
        self,
        symbol: str,
        side: str,
        position_side: str,
        order_type: str,
        quantity: float = None,
        price: float = None
    ) -> Dict[str, Any]:
        """
        Place an Order (Perpetual Swap).
        POST /openApi/swap/v2/trade/order
        side: BUY or SELL
        position_side: LONG or SHORT
        order_type: MARKET or LIMIT
        """
        params = {
            "symbol": symbol,
            "side": side,
            "positionSide": position_side,
            "type": order_type
        }
        if quantity is not None:
            params["quantity"] = quantity
        if price is not None:
            params["price"] = price
            
        return await self._request("POST", "/openApi/swap/v2/trade/order", params)
