import pytest
from exchange.delta_client import DeltaExchangeClient

def test_delta_client_endpoints():
    client_demo = DeltaExchangeClient(is_demo=True)
    assert client_demo.base_url == "https://cdn-ind.testnet.deltaex.org"

    client_live = DeltaExchangeClient(is_demo=False)
    assert client_live.base_url == "https://api.india.delta.exchange"

def test_hmac_signature_generation():
    client = DeltaExchangeClient(api_key="test_key", api_secret="test_secret", is_demo=True)
    sig, ts = client.generate_signature(
        method="GET",
        path="/v2/wallet/balances",
        query_string="",
        body="",
        timestamp="1700000000"
    )
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA256 hex digest is 64 characters
    assert ts == "1700000000"

    headers = client._get_headers("GET", "/v2/wallet/balances")
    assert headers["api-key"] == "test_key"
    assert headers["timestamp"] is not None
    assert headers["signature"] is not None
