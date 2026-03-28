"""Trading bot package for Binance Futures Testnet."""

from .client import BinanceAPIError, BinanceFuturesTestnetClient
from .orders import OrderResult, place_limit_order, place_market_order, place_stop_limit_order

__all__ = [
    "BinanceAPIError",
    "BinanceFuturesTestnetClient",
    "OrderResult",
    "place_market_order",
    "place_limit_order",
    "place_stop_limit_order",
]
