import pytest
import hmac
import hashlib
from app.services.bingx import generate_signature

def test_generate_signature():
    # Example signature test based on standard HMAC-SHA256
    api_secret = "test_secret_key"
    params = {
        "symbol": "BTC-USDT",
        "timestamp": 1610000000000,
        "type": "MARKET"
    }
    
    # Expected behavior: 
    # sorted_params: symbol=BTC-USDT, timestamp=1610000000000, type=MARKET
    # query_string: "symbol=BTC-USDT&timestamp=1610000000000&type=MARKET"
    # HMAC-SHA256("test_secret_key", "symbol=BTC-USDT&timestamp=1610000000000&type=MARKET")
    
    # Calculate expected signature manually here
    import hmac
    import hashlib
    expected = hmac.new(
        b"test_secret_key",
        b"symbol=BTC-USDT&timestamp=1610000000000&type=MARKET",
        hashlib.sha256
    ).hexdigest()
    
    signature = generate_signature(api_secret, params)
    assert signature == expected

def test_generate_signature_empty_params():
    signature = generate_signature("secret", {})
    expected = hmac.new(b"secret", b"", hashlib.sha256).hexdigest()
    assert signature == expected
