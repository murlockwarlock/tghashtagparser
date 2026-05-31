# BingX API Documentation (Perpetual Futures)

## Authentication

All authenticated endpoints require the `X-BX-APIKEY` header and a `signature` parameter in the query string.

### Signature Generation (HMAC-SHA256)
1. **Timestamp**: A `timestamp` parameter must be included in the query string (current time in milliseconds).
2. **Sorting**: Sort all query parameters alphabetically by key.
3. **Query String**: Join the sorted parameters with `&` to form the query string.
4. **Hashing**: Hash the query string using HMAC-SHA256 with the API `SECRET_KEY`.
5. **Appending**: Append `&signature=<hash>` to the query string.

**Python Example:**
```python
import hashlib
import hmac
import urllib.parse
import time

def generate_signature(api_secret: str, params: dict) -> str:
    query_string = urllib.parse.urlencode(sorted(params.items()))
    signature = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature
```

## Endpoints

### 1. Place Order (Standard Perpetual)
**URL**: `POST https://open-api.bingx.com/openApi/swap/v2/trade/order`

**Parameters (Query String)**:
- `symbol` (String): e.g., "BTC-USDT"
- `side` (String): "BUY" or "SELL"
- `positionSide` (String): "LONG" or "SHORT"
- `type` (String): "MARKET" or "LIMIT"
- `quantity` (Number): Optional (if `quoteOrderQty` is used for Market orders)
- `price` (Number): Required for LIMIT orders
- `timestamp` (Long): Current time in ms

**Response**:
```json
{
  "code": 0,
  "msg": "",
  "data": {
    "order": {
      "orderId": 123456789,
      "symbol": "BTC-USDT",
      "side": "BUY",
      "type": "MARKET"
    }
  }
}
```

### 2. Set Leverage
**URL**: `POST https://open-api.bingx.com/openApi/swap/v2/trade/leverage`

**Parameters**:
- `symbol` (String): "BTC-USDT"
- `leverage` (Integer): e.g., 20
- `side` (String): "LONG" or "SHORT"
- `timestamp` (Long)

### 3. Get Account Balance
**URL**: `GET https://open-api.bingx.com/openApi/swap/v2/user/balance`

**Parameters**:
- `timestamp` (Long)
