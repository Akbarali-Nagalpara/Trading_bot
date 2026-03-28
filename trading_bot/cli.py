"""CLI entry point for placing Binance Futures Testnet orders."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
from typing import Optional

import click
import typer
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from bot.client import BinanceAPIError, BinanceFuturesTestnetClient
from bot.logging_config import configure_logging
from bot.orders import (
    OrderResult,
    OrderValidationError,
    place_limit_order,
    place_market_order,
    place_stop_limit_order,
)
from bot.validators import ValidationError, validate_cli_inputs

app = typer.Typer(add_completion=False, help="Binance Futures Testnet trading CLI")
logger = logging.getLogger("cli")
console = Console()


@dataclass(frozen=True)
class UITheme:
    name: str
    header_accent: str
    header_border: str
    step_color: str
    request_header: str
    response_header: str
    review_header: str
    field_color: str
    info_border: str
    success_border: str
    warning_border: str
    error_border: str
    spinner_style: str


THEMES = {
    "classic": UITheme(
        name="classic",
        header_accent="bold cyan",
        header_border="bright_blue",
        step_color="bold blue",
        request_header="bold bright_white on blue",
        response_header="bold bright_white on green",
        review_header="bold white on magenta",
        field_color="bold cyan",
        info_border="cyan",
        success_border="green",
        warning_border="yellow",
        error_border="red",
        spinner_style="bold cyan",
    ),
    "neon": UITheme(
        name="neon",
        header_accent="bold bright_magenta",
        header_border="bright_magenta",
        step_color="bold bright_cyan",
        request_header="bold black on bright_cyan",
        response_header="bold black on bright_green",
        review_header="bold black on bright_magenta",
        field_color="bold bright_cyan",
        info_border="bright_cyan",
        success_border="bright_green",
        warning_border="bright_yellow",
        error_border="bright_red",
        spinner_style="bold bright_magenta",
    ),
    "minimal": UITheme(
        name="minimal",
        header_accent="bold white",
        header_border="white",
        step_color="bold white",
        request_header="bold white",
        response_header="bold white",
        review_header="bold white",
        field_color="bold white",
        info_border="white",
        success_border="white",
        warning_border="white",
        error_border="white",
        spinner_style="bold white",
    ),
}

CURRENT_THEME = THEMES["classic"]


def _set_theme(name: str) -> None:
    global CURRENT_THEME
    CURRENT_THEME = THEMES.get(name, THEMES["classic"])


def _style_side(value: str) -> str:
    upper = value.upper()
    if upper == "BUY":
        return "[black on bright_green] BUY [/black on bright_green]"
    if upper == "SELL":
        return "[black on bright_red] SELL [/black on bright_red]"
    return value


def _style_type(value: str) -> str:
    upper = value.upper()
    if upper == "MARKET":
        return "[black on bright_yellow] MARKET [/black on bright_yellow]"
    if upper == "LIMIT":
        return "[black on bright_blue] LIMIT [/black on bright_blue]"
    return f"[black on bright_magenta] {upper} [/black on bright_magenta]"


def _style_status(value: str) -> str:
    upper = value.upper()
    if upper in {"FILLED", "NEW", "PARTIALLY_FILLED"}:
        return f"[black on bright_green] {upper} [/black on bright_green]"
    if upper in {"REJECTED", "EXPIRED", "CANCELED"}:
        return f"[black on bright_red] {upper} [/black on bright_red]"
    return f"[black on bright_yellow] {upper} [/black on bright_yellow]"


def _print_trade_strip(payload: dict[str, str]) -> None:
    price = payload.get("price", "MKT")
    strip = (
        f"[dim]Trade Strip:[/dim] {payload['symbol']} | {_style_side(payload['side'])} | "
        f"{_style_type(payload['type'])} | qty={payload['quantity']} | price={price}"
    )
    console.print(strip)


def _print_direct_mode_card(payload: dict[str, str]) -> None:
    """Render a concise card for direct command runs."""
    price = payload.get("price", "Market")
    stop_price = payload.get("stop_price", "N/A")
    message = (
        f"Mode: Direct Command\n"
        f"Pair: {payload['symbol']}\n"
        f"Side / Type: {payload['side']} / {payload['type']}\n"
        f"Quantity: {payload['quantity']}\n"
        f"Price: {price}\n"
        f"Stop Price: {stop_price}"
    )
    console.print(
        Panel(
            message,
            title="Direct Order Snapshot",
            border_style=CURRENT_THEME.info_border,
            box=box.ROUNDED,
        )
    )


def _render_header() -> None:
    title = Text("Binance Futures Testnet Trader", style="bold white")
    subtitle = "Fast order placement with safer validation and terminal-first UX"
    console.print(
        Panel(
            f"[{CURRENT_THEME.header_accent}]{title}[/{CURRENT_THEME.header_accent}]\n"
            f"[dim]{subtitle}[/dim]\n"
            f"[dim]Theme: {CURRENT_THEME.name}[/dim]",
            border_style=CURRENT_THEME.header_border,
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def _to_decimal(value: str, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a valid number.") from exc

    if parsed <= 0:
        raise ValidationError(f"{field_name} must be greater than 0.")
    return parsed


def _decimal_to_string(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _wizard_step(current: int, total: int, title: str) -> None:
    console.print(
        f"[{CURRENT_THEME.step_color}]Step {current}/{total}[/{CURRENT_THEME.step_color}] "
        f"[dim]- {title}[/dim]"
    )


def _round_quantity_to_step(quantity: Decimal, step_size: Optional[Decimal]) -> Decimal:
    if step_size is None or step_size <= 0:
        return quantity
    return (quantity / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size


def _round_quantity_up_to_step(quantity: Decimal, step_size: Optional[Decimal]) -> Decimal:
    if step_size is None or step_size <= 0:
        return quantity
    return (quantity / step_size).to_integral_value(rounding=ROUND_UP) * step_size


def _get_interactive_defaults(
    client: Optional[BinanceFuturesTestnetClient],
    *,
    symbol: str,
    side: str,
    order_type: str,
) -> dict[str, Optional[str]]:
    """Build beginner-friendly quantity/price suggestions from live market data."""
    if client is None:
        return {
            "mark_price": None,
            "suggested_qty": "0.002",
            "suggested_price": None,
            "tip": "Using basic defaults (live market data unavailable).",
        }

    try:
        mark_price = client.get_mark_price(symbol)
        min_notional = client.get_symbol_min_notional(symbol)
        step_size = client.get_symbol_step_size(symbol)

        if min_notional and min_notional > 0:
            qty_by_notional = min_notional / mark_price
        else:
            qty_by_notional = Decimal("0.002")

        min_step = step_size if step_size and step_size > 0 else Decimal("0.001")
        suggested_qty_dec = max(qty_by_notional, min_step)
        suggested_qty_dec = _round_quantity_up_to_step(suggested_qty_dec, step_size)

        suggested_price_dec: Optional[Decimal] = None
        if order_type in {"LIMIT", "STOP_LIMIT"}:
            # Beginner-friendly pricing: slightly below mark for BUY and above mark for SELL.
            multiplier = Decimal("0.995") if side.upper() == "BUY" else Decimal("1.005")
            suggested_price_dec = (mark_price * multiplier).quantize(Decimal("0.1"))

        return {
            "mark_price": _decimal_to_string(mark_price),
            "suggested_qty": _decimal_to_string(suggested_qty_dec),
            "suggested_price": (
                _decimal_to_string(suggested_price_dec) if suggested_price_dec is not None else None
            ),
            "tip": (
                "Suggested values are computed from current mark price, min notional, and step size."
            ),
        }
    except BinanceAPIError:
        return {
            "mark_price": None,
            "suggested_qty": "0.002",
            "suggested_price": None,
            "tip": "Using fallback defaults (unable to fetch symbol rules right now).",
        }


def _print_request_summary(payload: dict[str, str]) -> None:
    table = Table(
        title="Order Request Summary",
        show_header=True,
        header_style=CURRENT_THEME.request_header,
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Field", style=CURRENT_THEME.field_color)
    table.add_column("Value")
    table.add_row("Symbol", payload["symbol"])
    table.add_row("Side", _style_side(payload["side"]))
    table.add_row("Type", _style_type(payload["type"]))
    table.add_row("Quantity", payload["quantity"])
    if payload.get("price"):
        table.add_row("Price", payload["price"])
    if payload.get("stop_price"):
        table.add_row("Stop Price", payload["stop_price"])
    console.print(table)


def _show_review_card(client: BinanceFuturesTestnetClient, payload: dict[str, str]) -> None:
    """Show final computed review details before submission."""
    qty = _to_decimal(payload["quantity"], "quantity")

    if payload["type"] == "MARKET":
        ref_price = client.get_mark_price(payload["symbol"])
    else:
        ref_price = _to_decimal(payload["price"], "price")

    estimated_notional = qty * ref_price
    estimated_fee = estimated_notional * Decimal("0.0004")

    min_notional = client.get_symbol_min_notional(payload["symbol"])
    if min_notional is None:
        min_notional_status = "UNKNOWN"
        min_notional_details = "Unable to fetch min notional"
    else:
        passed = estimated_notional >= min_notional
        min_notional_status = "PASS" if passed else "FAIL"
        min_notional_details = (
            f"min={_decimal_to_string(min_notional)} | "
            f"actual={_decimal_to_string(estimated_notional)}"
        )

    review = Table(
        title="Final Review",
        show_header=True,
        header_style=CURRENT_THEME.review_header,
        box=box.SIMPLE_HEAVY,
    )
    review.add_column("Item", style=CURRENT_THEME.field_color)
    review.add_column("Value")
    review.add_row("Order Type", _style_type(payload["type"]))
    review.add_row("Reference Price", _decimal_to_string(ref_price))
    review.add_row("Estimated Notional", _decimal_to_string(estimated_notional))
    review.add_row("Estimated Fee (0.04%)", _decimal_to_string(estimated_fee))
    review.add_row("Min Notional Check", f"{min_notional_status} ({min_notional_details})")
    console.print(review)


def _print_response(result: OrderResult) -> None:
    table = Table(
        title="Order Response",
        show_header=True,
        header_style=CURRENT_THEME.response_header,
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Field", style=CURRENT_THEME.field_color)
    table.add_column("Value")
    table.add_row("orderId", str(result.order_id))
    table.add_row("status", _style_status(result.status))
    table.add_row("executedQty", result.executed_qty)
    table.add_row("avgPrice", result.avg_price or "N/A")
    console.print(table)


def _show_input_error(title: str, message: str) -> None:
    panel = Panel(
        f"{message}\n\nTips:\n- Use BUY or SELL for side\n- Use MARKET, LIMIT, or STOP_LIMIT for type\n- LIMIT/STOP_LIMIT require --price\n- STOP_LIMIT also requires --stop-price",
        title=title,
        border_style=CURRENT_THEME.error_border,
    )
    console.print(panel)


def _show_api_error(exc: BinanceAPIError) -> None:
    """Render user-friendly API errors for known Binance edge cases."""
    if exc.code in {-4120, -5000}:
        message = (
            "STOP_LIMIT is not supported for this Binance Futures Testnet account/endpoint.\n\n"
            "Use MARKET or LIMIT orders in this environment."
        )
        console.print(
            Panel(message, title="Binance API Limitation", border_style=CURRENT_THEME.warning_border)
        )
        return

    console.print(Panel(f"{exc}", title="Binance API Error", border_style=CURRENT_THEME.error_border))


def _prompt_missing_inputs(
    symbol: Optional[str],
    side: Optional[str],
    order_type: Optional[str],
    quantity: Optional[str],
    price: Optional[str],
    stop_price: Optional[str],
    client: Optional[BinanceFuturesTestnetClient] = None,
) -> tuple[str, str, str, str, Optional[str], Optional[str]]:
    """Prompt user for missing order parameters."""
    console.print(
        Panel(
            "Interactive Mode\n\n"
            "Available order types:\n"
            "- MARKET\n"
            "- LIMIT\n"
            "- STOP_LIMIT",
            title="Guided Input",
            border_style=CURRENT_THEME.info_border,
            box=box.ROUNDED,
        )
    )

    _wizard_step(1, 5, "Choose symbol")
    chosen_symbol = symbol or typer.prompt("Symbol", default="BTCUSDT")

    _wizard_step(2, 5, "Choose side")
    chosen_side = side or typer.prompt(
        "Side",
        type=click.Choice(["BUY", "SELL"], case_sensitive=False),
    )

    _wizard_step(3, 5, "Choose order type")
    if order_type:
        chosen_type = order_type
    else:
        console.print(
            "Select order type: [bold]1[/bold]=MARKET, [bold]2[/bold]=LIMIT, [bold]3[/bold]=STOP_LIMIT"
        )
        type_choice = typer.prompt("Order Type Number", type=click.IntRange(1, 3))
        choice_map = {1: "MARKET", 2: "LIMIT", 3: "STOP_LIMIT"}
        chosen_type = choice_map[type_choice]

    defaults = _get_interactive_defaults(
        client,
        symbol=chosen_symbol.strip().upper(),
        side=chosen_side,
        order_type=chosen_type.strip().upper(),
    )

    guidance = (
        f"Mark Price: {defaults['mark_price'] or 'N/A'}\n"
        f"Suggested Quantity: {defaults['suggested_qty']}\n"
        f"Suggested Limit Price: {defaults['suggested_price'] or 'N/A'}\n"
        f"Tip: {defaults['tip']}"
    )
    console.print(
        Panel(guidance, title="Smart Suggestions", border_style=CURRENT_THEME.info_border, box=box.ROUNDED)
    )

    _wizard_step(4, 5, "Set quantity and pricing")
    chosen_quantity = quantity or typer.prompt(
        "Quantity (press Enter to accept suggested value)",
        default=defaults["suggested_qty"] or "0.002",
    )

    normalized_type = chosen_type.strip().upper()
    chosen_price = price
    chosen_stop_price = stop_price

    if normalized_type in {"LIMIT", "STOP_LIMIT"} and not chosen_price:
        suggested_price = defaults["suggested_price"]
        if suggested_price:
            chosen_price = typer.prompt(
                "Limit Price (press Enter to accept suggested value)",
                default=suggested_price,
            )
        else:
            chosen_price = typer.prompt("Limit Price")

    if normalized_type == "STOP_LIMIT" and not chosen_stop_price:
        chosen_stop_price = typer.prompt("Stop Trigger Price")

    return (
        chosen_symbol,
        chosen_side,
        chosen_type,
        chosen_quantity,
        chosen_price,
        chosen_stop_price,
    )


def _confirm_submission(payload: dict[str, str], confirm: bool, interactive_mode: bool) -> None:
    if interactive_mode:
        _wizard_step(5, 5, "Review and confirm")
    console.print(
        f"[bold cyan]Execution path:[/bold cyan] {payload['type']} order will be submitted."
    )

    if not confirm:
        return

    answer = typer.confirm("Submit this order now?", default=True)
    if not answer:
        console.print(
            Panel("Order cancelled by user.", title="Cancelled", border_style=CURRENT_THEME.warning_border)
        )
        raise typer.Exit(code=0)


def _build_client() -> BinanceFuturesTestnetClient:
    load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY")
    secret_key = os.getenv("BINANCE_SECRET_KEY")

    if not api_key or not secret_key:
        raise ValidationError(
            "Missing API credentials. Set BINANCE_API_KEY and BINANCE_SECRET_KEY in .env."
        )

    return BinanceFuturesTestnetClient(
        api_key=api_key,
        secret_key=secret_key,
        base_url="https://testnet.binancefuture.com",
        max_retries=3,
        backoff_seconds=1.0,
    )


def _apply_risk_sizing(
    client: BinanceFuturesTestnetClient,
    *,
    symbol: str,
    order_type: str,
    side: str,
    price: Optional[str],
    stop_loss_price: str,
    risk_balance: str,
    risk_percent: str,
    entry_price: Optional[str],
) -> str:
    """Calculate quantity from risk settings and return normalized string quantity."""
    _ = side  # reserved for future side-specific risk rules
    balance_dec = _to_decimal(risk_balance, "risk_balance")
    risk_percent_dec = _to_decimal(risk_percent, "risk_percent")
    stop_dec = _to_decimal(stop_loss_price, "stop_loss_price")

    if entry_price:
        entry_dec = _to_decimal(entry_price, "entry_price")
    elif order_type in {"LIMIT", "STOP_LIMIT"}:
        if not price:
            raise ValidationError("price is required to calculate risk-based quantity.")
        entry_dec = _to_decimal(price, "price")
    else:
        entry_dec = client.get_mark_price(symbol)

    per_unit_risk = abs(entry_dec - stop_dec)
    if per_unit_risk <= 0:
        raise ValidationError("entry and stop loss must be different for risk sizing.")

    risk_amount = balance_dec * (risk_percent_dec / Decimal("100"))
    raw_qty = risk_amount / per_unit_risk

    step_size = client.get_symbol_step_size(symbol)
    rounded_qty = _round_quantity_to_step(raw_qty, step_size)
    if rounded_qty <= 0:
        raise ValidationError("calculated quantity is too small after symbol step-size rounding.")

    calc_panel = Panel(
        (
            f"Risk sizing applied for {symbol}\n"
            f"Entry Price: {_decimal_to_string(entry_dec)}\n"
            f"Stop Loss: {_decimal_to_string(stop_dec)}\n"
            f"Risk Amount: {_decimal_to_string(risk_amount)}\n"
            f"Calculated Quantity: {_decimal_to_string(rounded_qty)}"
        ),
        title="Risk Calculator",
        border_style="cyan",
        box=box.ROUNDED,
    )
    console.print(calc_panel)

    return _decimal_to_string(rounded_qty)


@app.command()
def place_order(
    symbol: Optional[str] = typer.Option(None, "--symbol", help="Trading pair, e.g., BTCUSDT"),
    side: Optional[str] = typer.Option(None, "--side", help="BUY or SELL"),
    order_type: Optional[str] = typer.Option(
        None,
        "--type",
        help="MARKET, LIMIT, or STOP_LIMIT",
    ),
    quantity: Optional[str] = typer.Option(None, "--quantity", help="Order quantity"),
    price: Optional[str] = typer.Option(None, "--price", help="Required for LIMIT/STOP_LIMIT"),
    stop_price: Optional[str] = typer.Option(
        None,
        "--stop-price",
        help="Required for STOP_LIMIT orders",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive prompts for missing fields.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show INFO logs in console (full logs are always written to logs/app.log).",
    ),
    confirm: bool = typer.Option(
        True,
        "--confirm/--no-confirm",
        help="Ask for confirmation before submitting order.",
    ),
    risk_balance: Optional[str] = typer.Option(
        None,
        "--risk-balance",
        help="Account balance used for risk-based quantity calculation.",
    ),
    risk_percent: Optional[str] = typer.Option(
        None,
        "--risk-percent",
        help="Risk percentage per trade, e.g. 1 for 1%%.",
    ),
    stop_loss_price: Optional[str] = typer.Option(
        None,
        "--stop-loss-price",
        help="Stop loss price used by risk-based sizing.",
    ),
    entry_price: Optional[str] = typer.Option(
        None,
        "--entry-price",
        help="Optional entry price override for risk sizing.",
    ),
    theme: str = typer.Option(
        "classic",
        "--theme",
        help="UI theme: classic, neon, minimal.",
        case_sensitive=False,
        show_choices=True,
        click_type=click.Choice(["classic", "neon", "minimal"], case_sensitive=False),
    ),
) -> None:
    """Place MARKET, LIMIT, or STOP_LIMIT orders on Binance Futures Testnet."""
    try:
        _set_theme(theme.lower())
        _render_header()

        console_level = logging.INFO if verbose else logging.WARNING
        log_path = configure_logging(console_level=console_level)
        logger.debug("Logging initialized at %s", log_path)

        interactive_mode = interactive or any(
            value is None for value in [symbol, side, order_type, quantity]
        )

        # If interactive mode is requested (or required by missing values), prompt in-menu style.
        if interactive_mode:
            interactive_client: Optional[BinanceFuturesTestnetClient] = None
            try:
                interactive_client = _build_client()
            except ValidationError:
                logger.warning(
                    "Skipping live suggestions in interactive mode due to missing/invalid credentials."
                )

            (
                symbol,
                side,
                order_type,
                quantity,
                price,
                stop_price,
            ) = _prompt_missing_inputs(
                symbol,
                side,
                order_type,
                quantity,
                price,
                stop_price,
                client=interactive_client,
            )

        if symbol is None or side is None or order_type is None or quantity is None:
            risk_bundle = [risk_balance, risk_percent, stop_loss_price]
            using_risk = any(item is not None for item in risk_bundle)
            if not using_risk:
                raise ValidationError(
                    "Missing required fields. Provide --symbol --side --type --quantity or use --interactive."
                )
            if symbol is None or side is None or order_type is None:
                raise ValidationError(
                    "risk sizing still requires --symbol --side --type (or --interactive)."
                )

        risk_inputs = [risk_balance, risk_percent, stop_loss_price]
        using_risk = any(item is not None for item in risk_inputs)
        if using_risk and not all(item is not None for item in risk_inputs):
            raise ValidationError(
                "To use risk sizing, provide --risk-balance, --risk-percent, and --stop-loss-price together."
            )

        if using_risk and symbol and side and order_type:
            client_for_risk = _build_client()
            quantity = _apply_risk_sizing(
                client_for_risk,
                symbol=symbol.strip().upper(),
                side=side,
                order_type=order_type.strip().upper(),
                price=price,
                stop_loss_price=stop_loss_price or "",
                risk_balance=risk_balance or "",
                risk_percent=risk_percent or "",
                entry_price=entry_price,
            )

        if quantity is None:
            raise ValidationError("quantity is required when risk sizing is not used.")

        validated = validate_cli_inputs(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
        )

        if not interactive_mode:
            _print_direct_mode_card(validated)
        _print_trade_strip(validated)
        _print_request_summary(validated)

        review_client = _build_client()
        try:
            _show_review_card(review_client, validated)
        except BinanceAPIError as exc:
            logger.warning("Could not render full review card: %s", exc)
            console.print(
                Panel(
                    "Review card could not fetch live market data. Order can still proceed.",
                    title="Review Notice",
                    border_style=CURRENT_THEME.warning_border,
                    box=box.ROUNDED,
                )
            )

        _confirm_submission(validated, confirm=confirm, interactive_mode=interactive_mode)

        with console.status(
            f"[{CURRENT_THEME.spinner_style}]Submitting order to Binance Testnet..."
            f"[/{CURRENT_THEME.spinner_style}]"
        ):
            client = review_client

            if validated["type"] == "MARKET":
                result = place_market_order(
                    client,
                    symbol=validated["symbol"],
                    side=validated["side"],
                    quantity=validated["quantity"],
                )
            elif validated["type"] == "LIMIT":
                result = place_limit_order(
                    client,
                    symbol=validated["symbol"],
                    side=validated["side"],
                    quantity=validated["quantity"],
                    price=validated["price"],
                )
            else:
                result = place_stop_limit_order(
                    client,
                    symbol=validated["symbol"],
                    side=validated["side"],
                    quantity=validated["quantity"],
                    price=validated["price"],
                    stop_price=validated["stop_price"],
                )

        _print_response(result)

        if result.status.upper() in {"NEW", "FILLED", "PARTIALLY_FILLED"}:
            console.print(
                Panel(
                    "Order placed successfully.",
                    title="Success",
                    border_style=CURRENT_THEME.success_border,
                    box=box.ROUNDED,
                )
            )
        else:
            console.print(
                Panel(
                    f"Order request completed with status: {result.status}",
                    title="Order Status",
                    border_style=CURRENT_THEME.warning_border,
                    box=box.ROUNDED,
                )
            )

    except ValidationError as exc:
        logger.error("Validation error: %s", exc, exc_info=True)
        _show_input_error("Input Error", str(exc))
        raise typer.Exit(code=1) from exc
    except OrderValidationError as exc:
        logger.error("Order validation error: %s", exc, exc_info=True)
        _show_input_error("Order Validation Error", str(exc))
        raise typer.Exit(code=1) from exc
    except BinanceAPIError as exc:
        logger.error("Binance API error: %s", exc)
        logger.debug("Binance API exception details", exc_info=True)
        _show_api_error(exc)
        raise typer.Exit(code=2) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.error("Unexpected error: %s", exc, exc_info=True)
        console.print(
            Panel(
                "An unexpected error occurred. Check logs/app.log for details.",
                title="Unexpected Error",
                border_style=CURRENT_THEME.error_border,
            )
        )
        raise typer.Exit(code=99) from exc


if __name__ == "__main__":
    app()
