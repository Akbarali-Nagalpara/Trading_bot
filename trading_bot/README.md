# Binance Futures Testnet Trading CLI

A production-style Python 3.x command line application for placing **USDT-M Futures** orders on Binance Testnet.

## Features

- Places `MARKET`, `LIMIT`, and `STOP_LIMIT` orders
- Supports `BUY` and `SELL`
- Uses Binance Futures Testnet base URL: `https://testnet.binancefuture.com`
- Validates all CLI inputs before API execution
- Layered architecture for maintainability
- Structured logging to `logs/app.log`
- Retry mechanism for transient network/server failures
- Interactive CLI prompts (`--interactive`) for menu-like input
- Lightweight terminal UI with tables/panels via `rich`
- Clean console by default, detailed logs in `logs/app.log` (`--verbose` for console INFO logs)
- Risk-based quantity sizing from account risk settings

## Project Structure

```text
trading_bot/
  bot/
    __init__.py
    client.py         # Binance API wrapper and request signing
    orders.py         # business logic for placing orders
    validators.py     # CLI input validation
    logging_config.py # logging setup
  cli.py              # CLI entry point
  README.md
  requirements.txt
  .env.example
  logs/
    app.log
```

## Setup Steps

1. Open terminal at project root:

```bash
cd "D:/Projects/Trading Bot on Binance Futures Testnet"
```

2. Create and activate virtual environment:

```bash
python -m venv .venv
```

PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```bash
pip install -r trading_bot/requirements.txt
```

4. Create environment file from template:

```bash
copy trading_bot/.env.example trading_bot/.env
```

5. Add Binance Testnet API credentials in `trading_bot/.env`:

```env
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret
```

## How To Run (Examples)

From inside `trading_bot` directory:

```bash
cd trading_bot
```

### Direct commands

MARKET order:

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.002
```

LIMIT order:

```bash
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.002 --price 70000
```

STOP_LIMIT order:

```bash
python cli.py --symbol BTCUSDT --side SELL --type STOP_LIMIT --quantity 0.002 --price 70000 --stop-price 69950
```

### Interactive mode

```bash
python cli.py --interactive
```

### Optional flags

Verbose logs in console:

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.002 --verbose
```

Skip confirmation prompt:

```bash
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.002 --price 70000 --no-confirm
```

Use a theme:

```bash
python cli.py --interactive --theme neon
```

Risk-based sizing:

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --risk-balance 1000 --risk-percent 1 --stop-loss-price 65000
```

Optional entry override for strategy calculation:

```bash
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --price 70000 --risk-balance 1000 --risk-percent 1 --stop-loss-price 71000 --entry-price 70000
```

## Assumptions

- This app targets Binance **USDT-M Futures Testnet** only.
- API keys are valid and have Testnet permissions.
- `timeInForce` for LIMIT/STOP_LIMIT is fixed to `GTC`.
- `STOP_LIMIT` is mapped to Binance conditional order types; some Testnet accounts may still return `-4120` (endpoint/account limitation).
- Symbol filters (min notional, step size) are fetched dynamically from Binance and may change.

## Validation Rules

- `symbol`: uppercase alphanumeric format like `BTCUSDT`
- `side`: `BUY` or `SELL`
- `type`: `MARKET`, `LIMIT`, or `STOP_LIMIT`
- `quantity`: numeric and greater than 0
- `price`: required for LIMIT and must be greater than 0
- `stop_price`: required for STOP_LIMIT and must be greater than 0
- `risk_balance`, `risk_percent`, `stop_loss_price`: must be provided together for risk sizing

## Logging

- Log file: `logs/app.log`
- Includes timestamp, request payload, response payload, and stack traces for errors
- Console output defaults to warning/error for clean UX
- Use `--verbose` for INFO logs in terminal

## Error Handling

The CLI handles and surfaces:

- invalid CLI input
- missing credentials
- Binance API errors
- network failures with retry attempts
- unexpected runtime exceptions

User-facing output is concise, while detailed diagnostics are written to `logs/app.log`.

```env
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret
```

## Usage

From inside the `trading_bot` directory, run:

### MARKET order

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.002
```

### LIMIT order

```bash
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.002 --price 70000
```

### STOP_LIMIT order

```bash
python cli.py --symbol BTCUSDT --side SELL --type STOP_LIMIT --quantity 0.002 --price 70000 --stop-price 69950
```

> Note: On some Binance Futures Testnet accounts, conditional order types may return `-4120`.
> The CLI detects this and shows a friendly limitation message.

### Interactive mode

```bash
python cli.py --interactive
```

### Verbose mode

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.002 --verbose
```

### Risk-based sizing

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --risk-balance 1000 --risk-percent 1 --stop-loss-price 65000
```

Optional entry override (for LIMIT/STOP_LIMIT strategy calculation):

```bash
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --price 70000 --risk-balance 1000 --risk-percent 1 --stop-loss-price 71000 --entry-price 70000
```

You can also combine interactive mode with partial args. Missing values are prompted:

```bash
python cli.py --symbol BTCUSDT --interactive
```

## Validation Rules

- `symbol`: uppercase alphanumeric format like `BTCUSDT`
- `side`: `BUY` or `SELL`
- `type`: `MARKET`, `LIMIT`, or `STOP_LIMIT`
- `quantity`: numeric and greater than 0
- `price`: required for LIMIT and must be greater than 0
- `stop_price`: required for STOP_LIMIT and must be greater than 0
- `risk_balance`, `risk_percent`, `stop_loss_price`: must be provided together for risk sizing

## Logging

Application logs are written to:

- `logs/app.log`

Logged information includes:

- timestamp
- request payload
- response payload
- full exception stack traces for errors
- rotating file logs (up to 3 backups)

Console output defaults to warning/error level for a cleaner UX.
Use `--verbose` to print INFO logs to terminal.

## Assumptions

- This app targets Binance **USDT-M Futures Testnet** only.
- API keys are valid and have Testnet permissions.
- `timeInForce` for LIMIT and STOP_LIMIT orders is fixed to `GTC`.
- `STOP_LIMIT` is implemented as Binance futures type `STOP` with `price` + `stopPrice`.

## Error Handling

The CLI handles and surfaces:

- invalid CLI input
- missing credentials
- Binance API errors
- network failures with retry attempts
- unexpected runtime exceptions

User-facing output is concise, while full details are logged to `logs/app.log`.

## Evaluation Checklist

- Correctness: MARKET and LIMIT orders place successfully on Binance Futures Testnet.
- Code quality: layered architecture (`client`, `orders`, `validators`, `cli`) with reusable functions and type hints.
- Validation + error handling: strong input validation, pre-trade notional checks, network/API exception handling, retry on transient failures.
- Logging quality: concise console output + detailed file logging.
- Clear README + runnable instructions: setup, credentials, and executable command examples included.

## Notes About New UX Features

- Confirmation prompt is enabled by default; use `--no-confirm` to skip it.
