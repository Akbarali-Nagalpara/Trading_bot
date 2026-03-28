"""Business logic for order placement."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .client import BinanceFuturesTestnetClient


@dataclass
class OrderResult:
    """Normalized order result used by the CLI output layer."""

    order_id: int | str | None
    status: str
    executed_qty: str
    avg_price: Optional[str]
    raw_response: dict[str, Any]


class OrderValidationError(ValueError):
    """Raised when order business validation fails before API placement."""


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, "", 0, "0"):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _derive_avg_price(response: dict[str, Any]) -> Optional[str]:
    avg_price = response.get("avgPrice")
    if avg_price not in (None, "", "0", 0):
        return str(avg_price)

    executed_qty = _safe_decimal(response.get("executedQty"))
    cum_quote = _safe_decimal(response.get("cumQuote"))

    if executed_qty is None or cum_quote is None or executed_qty <= 0:
        return None

    calculated = cum_quote / executed_qty
    return format(calculated.normalize(), "f")


def _normalize_order_result(response: dict[str, Any]) -> OrderResult:
    return OrderResult(
        order_id=response.get("orderId") or response.get("algoId") or response.get("clientOrderId"),
        status=str(response.get("status", "UNKNOWN")),
        executed_qty=str(response.get("executedQty", "0")),
        avg_price=_derive_avg_price(response),
        raw_response=response,
    )


def _validate_min_notional(
    client: BinanceFuturesTestnetClient,
    *,
    symbol: str,
    quantity: str,
    price: Optional[str],
) -> None:
    """Validate order notional against Binance symbol min notional, if provided."""
    min_notional = client.get_symbol_min_notional(symbol)
    if min_notional is None or min_notional <= 0:
        return

    try:
        qty_dec = Decimal(str(quantity))
        price_dec = Decimal(str(price)) if price is not None else client.get_mark_price(symbol)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OrderValidationError("Unable to validate order notional from input data.") from exc

    notional = qty_dec * price_dec
    if notional >= min_notional:
        return

    required_qty = (min_notional / price_dec).quantize(Decimal("0.000001"))
    raise OrderValidationError(
        (
            f"Order notional is too low for {symbol}. "
            f"Current notional={notional:.6f}, minimum={min_notional:.6f}. "
            f"Increase quantity to at least {required_qty} "
            f"(using reference price {price_dec:.6f})."
        )
    )


def place_market_order(
    client: BinanceFuturesTestnetClient,
    *,
    symbol: str,
    side: str,
    quantity: str,
) -> OrderResult:
    """Place a MARKET order."""
    _validate_min_notional(
        client,
        symbol=symbol,
        quantity=quantity,
        price=None,
    )

    response = client.place_order(
        symbol=symbol,
        side=side,
        order_type="MARKET",
        quantity=quantity,
    )
    return _normalize_order_result(response)


def place_limit_order(
    client: BinanceFuturesTestnetClient,
    *,
    symbol: str,
    side: str,
    quantity: str,
    price: str,
) -> OrderResult:
    """Place a LIMIT order."""
    _validate_min_notional(
        client,
        symbol=symbol,
        quantity=quantity,
        price=price,
    )

    response = client.place_order(
        symbol=symbol,
        side=side,
        order_type="LIMIT",
        quantity=quantity,
        price=price,
        time_in_force="GTC",
    )
    return _normalize_order_result(response)


def place_stop_limit_order(
    client: BinanceFuturesTestnetClient,
    *,
    symbol: str,
    side: str,
    quantity: str,
    price: str,
    stop_price: str,
) -> OrderResult:
    """Place a STOP_LIMIT order (Binance type=STOP)."""
    _validate_min_notional(
        client,
        symbol=symbol,
        quantity=quantity,
        price=price,
    )

    mark_price = client.get_mark_price(symbol)
    stop_price_dec = Decimal(stop_price)
    normalized_side = side.upper()

    # Binance requires choosing STOP vs TAKE_PROFIT based on trigger direction.
    if normalized_side == "BUY":
        conditional_type = "STOP" if stop_price_dec >= mark_price else "TAKE_PROFIT"
    else:
        conditional_type = "STOP" if stop_price_dec <= mark_price else "TAKE_PROFIT"

    response = client.place_order(
        symbol=symbol,
        side=side,
        order_type=conditional_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
        time_in_force="GTC",
    )
    return _normalize_order_result(response)
