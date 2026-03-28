"""Validation helpers for CLI input."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{6,20}$")
VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_LIMIT"}


class ValidationError(ValueError):
    """Raised when user input validation fails."""


def _normalize_decimal(value: str, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a valid number.") from exc

    if parsed <= 0:
        raise ValidationError(f"{field_name} must be greater than 0.")

    return parsed


def decimal_to_plain_string(value: Decimal) -> str:
    """Return a Decimal as a plain string without scientific notation."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def validate_symbol(symbol: str) -> str:
    """Validate trading symbol format."""
    if not symbol:
        raise ValidationError("symbol is required.")

    normalized = symbol.strip().upper()
    if not SYMBOL_PATTERN.match(normalized):
        raise ValidationError(
            "symbol format is invalid. Use uppercase format like BTCUSDT."
        )

    return normalized


def validate_side(side: str) -> str:
    """Validate order side."""
    if not side:
        raise ValidationError("side is required.")

    normalized = side.strip().upper()
    if normalized not in VALID_SIDES:
        raise ValidationError("side must be BUY or SELL.")

    return normalized


def validate_order_type(order_type: str) -> str:
    """Validate order type."""
    if not order_type:
        raise ValidationError("type is required.")

    normalized = order_type.strip().upper()
    if normalized not in VALID_ORDER_TYPES:
        raise ValidationError("type must be MARKET, LIMIT, or STOP_LIMIT.")

    return normalized


def validate_quantity(quantity: str) -> Decimal:
    """Validate quantity as a positive decimal."""
    if quantity is None:
        raise ValidationError("quantity is required.")

    return _normalize_decimal(quantity, "quantity")


def validate_price(price: Optional[str], order_type: str) -> Optional[Decimal]:
    """Validate price for LIMIT orders."""
    if order_type == "LIMIT":
        if price is None or str(price).strip() == "":
            raise ValidationError("price is required for LIMIT orders.")
        return _normalize_decimal(str(price), "price")

    if order_type == "STOP_LIMIT":
        if price is None or str(price).strip() == "":
            raise ValidationError("price is required for STOP_LIMIT orders.")
        return _normalize_decimal(str(price), "price")

    if price is None or str(price).strip() == "":
        return None

    return _normalize_decimal(str(price), "price")


def validate_stop_price(stop_price: Optional[str], order_type: str) -> Optional[Decimal]:
    """Validate stop price for STOP_LIMIT orders."""
    if order_type == "STOP_LIMIT":
        if stop_price is None or str(stop_price).strip() == "":
            raise ValidationError("stop_price is required for STOP_LIMIT orders.")
        return _normalize_decimal(str(stop_price), "stop_price")

    if stop_price is None or str(stop_price).strip() == "":
        return None

    return _normalize_decimal(str(stop_price), "stop_price")


def validate_cli_inputs(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str,
    price: Optional[str],
    stop_price: Optional[str],
) -> dict[str, str]:
    """Validate and normalize CLI inputs."""
    validated_type = validate_order_type(order_type)
    validated_quantity = validate_quantity(quantity)
    validated_price = validate_price(price, validated_type)
    validated_stop_price = validate_stop_price(stop_price, validated_type)

    normalized: dict[str, str] = {
        "symbol": validate_symbol(symbol),
        "side": validate_side(side),
        "type": validated_type,
        "quantity": decimal_to_plain_string(validated_quantity),
    }

    if validated_price is not None:
        normalized["price"] = decimal_to_plain_string(validated_price)

    if validated_stop_price is not None:
        normalized["stop_price"] = decimal_to_plain_string(validated_stop_price)

    return normalized
