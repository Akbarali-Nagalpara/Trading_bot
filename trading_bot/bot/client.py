"""Binance Futures Testnet API client wrapper."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import urlencode

import requests


@dataclass
class BinanceAPIError(Exception):
    """Represents an error returned by Binance API."""

    message: str
    status_code: Optional[int] = None
    code: Optional[int] = None
    payload: Optional[dict[str, Any]] = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"status_code={self.status_code}")
        if self.code is not None:
            parts.append(f"code={self.code}")
        return " | ".join(parts)


class BinanceFuturesTestnetClient:
    """Client for Binance USDT-M Futures Testnet."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        base_url: str = "https://testnet.binancefuture.com",
        timeout: int = 15,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        if not api_key or not secret_key:
            raise ValueError("Both API key and secret key are required.")

        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.time_offset_ms = 0
        self.logger = logging.getLogger(self.__class__.__name__)

        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    def _sign(self, query_string: str) -> str:
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    @staticmethod
    def _summarize_payload(payload: Any, max_chars: int = 600) -> str:
        """Return a compact payload string for logs to avoid massive console output."""
        if isinstance(payload, dict) and isinstance(payload.get("symbols"), list):
            symbols = payload.get("symbols", [])
            sample = [item.get("symbol") for item in symbols[:5] if isinstance(item, dict)]
            summary = {
                "keys": sorted(payload.keys()),
                "symbolsCount": len(symbols),
                "symbolsSample": sample,
            }
            return str(summary)

        text = str(payload)
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}...<truncated>"

    def _current_timestamp_ms(self) -> int:
        """Return local time adjusted by server offset."""
        return int(time.time() * 1000) + self.time_offset_ms

    def _sync_server_time(self) -> None:
        """Sync local offset with Binance server time to avoid -1021 errors."""
        url = f"{self.base_url}/fapi/v1/time"
        response = self.session.get(url=url, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        server_time = int(data["serverTime"])
        local_time = int(time.time() * 1000)
        self.time_offset_ms = server_time - local_time

        self.logger.info(
            "Server time synchronized | serverTime=%s | offsetMs=%s",
            server_time,
            self.time_offset_ms,
        )

    def _request_with_retry(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        signed: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"

        for attempt in range(1, self.max_retries + 1):
            try:
                request_payload = dict(payload)
                if signed:
                    request_payload["timestamp"] = self._current_timestamp_ms()
                    query_string = urlencode(request_payload, doseq=True)
                    request_payload["signature"] = self._sign(query_string)

                self.logger.info(
                    "API request | method=%s | url=%s | payload=%s",
                    method,
                    url,
                    request_payload,
                )

                response = self.session.request(
                    method=method,
                    url=url,
                    data=request_payload,
                    timeout=self.timeout,
                )

                response_data: dict[str, Any]
                try:
                    response_data = response.json()
                except ValueError:
                    response_data = {"raw": response.text}

                self.logger.info(
                    "API response | status=%s | payload=%s",
                    response.status_code,
                    response_data,
                )

                if 200 <= response.status_code < 300:
                    return response_data

                code = response_data.get("code") if isinstance(response_data, dict) else None
                msg = (
                    response_data.get("msg")
                    if isinstance(response_data, dict)
                    else "Unexpected API error"
                )

                if code == -1021 and signed and attempt < self.max_retries:
                    self.logger.debug(
                        "Timestamp out of sync. Syncing server time and retrying | attempt=%s",
                        attempt,
                    )
                    try:
                        self._sync_server_time()
                    except requests.RequestException as exc:
                        self.logger.error(
                            "Failed to sync server time | error=%s",
                            str(exc),
                            exc_info=True,
                        )
                    sleep_for = self.backoff_seconds * attempt
                    time.sleep(sleep_for)
                    continue

                # Retry only for server-side failures.
                if response.status_code >= 500 and attempt < self.max_retries:
                    sleep_for = self.backoff_seconds * attempt
                    self.logger.debug(
                        "Retrying after server error | attempt=%s | sleep=%s",
                        attempt,
                        sleep_for,
                    )
                    time.sleep(sleep_for)
                    continue

                raise BinanceAPIError(
                    message=msg,
                    status_code=response.status_code,
                    code=code,
                    payload=response_data if isinstance(response_data, dict) else None,
                )
            except requests.RequestException as exc:
                self.logger.error(
                    "Network/API request failure | attempt=%s | error=%s",
                    attempt,
                    str(exc),
                    exc_info=True,
                )
                if attempt >= self.max_retries:
                    raise BinanceAPIError(
                        message="Failed to reach Binance API after retries.",
                    ) from exc

                sleep_for = self.backoff_seconds * attempt
                time.sleep(sleep_for)

        raise BinanceAPIError(message="Unexpected retry loop termination.")

    def public_request(
        self,
        path: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send a public (unsigned) GET request to Binance."""
        url = f"{self.base_url}{path}"
        query = dict(params or {})

        self.logger.info("Public API request | url=%s | params=%s", url, query)
        try:
            response = self.session.get(url=url, params=query, timeout=self.timeout)
            response_data = response.json()
        except requests.RequestException as exc:
            self.logger.error("Public API request failure | error=%s", str(exc), exc_info=True)
            raise BinanceAPIError("Failed to reach Binance public API.") from exc
        except ValueError as exc:
            self.logger.error("Public API non-JSON response", exc_info=True)
            raise BinanceAPIError("Unexpected non-JSON response from Binance public API.") from exc

        self.logger.info(
            "Public API response | status=%s | payload=%s",
            response.status_code,
            self._summarize_payload(response_data),
        )

        if 200 <= response.status_code < 300:
            return response_data if isinstance(response_data, dict) else {"data": response_data}

        code = response_data.get("code") if isinstance(response_data, dict) else None
        msg = (
            response_data.get("msg")
            if isinstance(response_data, dict)
            else "Unexpected public API error"
        )
        raise BinanceAPIError(message=msg, status_code=response.status_code, code=code)

    def get_mark_price(self, symbol: str) -> Decimal:
        """Return current mark price for a symbol."""
        data = self.public_request("/fapi/v1/premiumIndex", {"symbol": symbol})
        mark_price = data.get("markPrice")
        try:
            return Decimal(str(mark_price))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise BinanceAPIError("Unable to parse mark price from Binance response.") from exc

    def get_symbol_min_notional(self, symbol: str) -> Optional[Decimal]:
        """Return symbol min notional from exchange info if available."""
        data = self.public_request("/fapi/v1/exchangeInfo", {"symbol": symbol})
        symbols = data.get("symbols", []) if isinstance(data, dict) else []
        if not symbols:
            return None

        filters = symbols[0].get("filters", [])
        for item in filters:
            if item.get("filterType") in {"NOTIONAL", "MIN_NOTIONAL"}:
                value = item.get("notional") or item.get("minNotional")
                if value is None:
                    continue
                try:
                    return Decimal(str(value))
                except (InvalidOperation, TypeError, ValueError):
                    continue
        return None

    def get_symbol_quantity_precision(self, symbol: str) -> Optional[int]:
        """Return quantity precision for a symbol if available."""
        data = self.public_request("/fapi/v1/exchangeInfo", {"symbol": symbol})
        symbols = data.get("symbols", []) if isinstance(data, dict) else []
        if not symbols:
            return None

        precision = symbols[0].get("quantityPrecision")
        try:
            return int(precision)
        except (TypeError, ValueError):
            return None

    def get_symbol_step_size(self, symbol: str) -> Optional[Decimal]:
        """Return LOT_SIZE step size for a symbol if available."""
        data = self.public_request("/fapi/v1/exchangeInfo", {"symbol": symbol})
        symbols = data.get("symbols", []) if isinstance(data, dict) else []
        if not symbols:
            return None

        filters = symbols[0].get("filters", [])
        for item in filters:
            if item.get("filterType") == "LOT_SIZE":
                value = item.get("stepSize")
                if value is None:
                    return None
                try:
                    return Decimal(str(value))
                except (InvalidOperation, TypeError, ValueError):
                    return None
        return None

    def signed_request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send a signed request to Binance."""
        payload = dict(params or {})
        return self._request_with_retry(
            method=method,
            path=path,
            payload=payload,
            signed=True,
        )

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        price: Optional[str] = None,
        stop_price: Optional[str] = None,
        time_in_force: Optional[str] = None,
    ) -> dict[str, Any]:
        """Place an order on Binance Futures Testnet."""
        order_payload: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "recvWindow": 5000,
        }

        if order_type == "LIMIT":
            if not price:
                raise ValueError("price is required for LIMIT orders")
            order_payload["price"] = price
            order_payload["timeInForce"] = time_in_force or "GTC"

        if order_type in {"STOP", "TAKE_PROFIT"}:
            if not price:
                raise ValueError("price is required for STOP_LIMIT orders")
            if not stop_price:
                raise ValueError("stop_price is required for STOP_LIMIT orders")
            order_payload["price"] = price
            order_payload["stopPrice"] = stop_price
            order_payload["timeInForce"] = time_in_force or "GTC"
            order_payload["workingType"] = "CONTRACT_PRICE"
            return self.signed_request("POST", "/fapi/v1/order", order_payload)

        return self.signed_request("POST", "/fapi/v1/order", order_payload)
