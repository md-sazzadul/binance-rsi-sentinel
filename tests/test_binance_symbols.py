"""Unit tests for filtering Binance exchange information."""

import pytest

from app.binance import BinanceSpotClient


class FakeResponseClient(BinanceSpotClient):
    def __init__(self, payload):
        self.payload = payload

    async def _get_json(self, path, params=None):
        assert path == "/api/v3/exchangeInfo"
        return self.payload


@pytest.mark.asyncio
async def test_only_active_spot_usdt_symbols_are_returned():
    client = FakeResponseClient({
        "symbols": [
            {"symbol": "BTCUSDT", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": True},
            {"symbol": "ETHBTC", "quoteAsset": "BTC", "status": "TRADING", "isSpotTradingAllowed": True},
            {"symbol": "OLDUSDT", "quoteAsset": "USDT", "status": "BREAK", "isSpotTradingAllowed": True},
            {"symbol": "NO_SPOTUSDT", "quoteAsset": "USDT", "status": "TRADING", "isSpotTradingAllowed": False},
        ]
    })

    assert await client.get_spot_usdt_symbols() == ["BTCUSDT"]
