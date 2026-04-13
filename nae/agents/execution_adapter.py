"""
NAE Execution Adapter (derived from Optimus architecture)

User-controlled order routing to supported brokers.
Every order requires explicit user confirmation (unless disabled in config).
No autonomous trading. No self-initiated orders. No strategy execution.

The user decides what to trade, when, and how much.
NAE simply relays the user's explicit instructions to the broker API.
"""

import os
import datetime
import json
import logging
import hashlib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

from nae.core.feature_gates import get_gates

logger = logging.getLogger("nae.execution")


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"
    BUY_TO_OPEN = "buy_to_open"
    SELL_TO_CLOSE = "sell_to_close"
    BUY_TO_CLOSE = "buy_to_close"
    SELL_TO_OPEN = "sell_to_open"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    PENDING_CONFIRMATION = "pending_confirmation"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class Order:
    """Represents a user-initiated order."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING_CONFIRMATION
    broker_order_id: Optional[str] = None
    created_at: str = ""
    filled_at: Optional[str] = None
    fill_price: Optional[float] = None
    user_confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["order_type"] = self.order_type.value
        d["status"] = self.status.value
        return d


class ExecutionAdapter:
    """
    User-controlled broker execution adapter.

    This adapter:
    - Accepts explicit orders from the user (via CLI)
    - Validates order parameters against configured safety limits
    - Requires user confirmation before submission
    - Routes to the configured broker API
    - Logs all activity for audit

    This adapter does NOT:
    - Generate orders autonomously
    - Suggest trades
    - Execute strategies without user input
    - Make any trading decisions
    """

    def __init__(self, log_dir: str = "./logs"):
        self._gates = get_gates()
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._order_history: List[Order] = []
        self._broker_client = None
        self._order_counter = 0

    def _generate_order_id(self) -> str:
        self._order_counter += 1
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"NAE-{ts}-{self._order_counter:04d}"

    def _get_broker(self):
        """Lazy-initialize broker connection."""
        if self._broker_client is not None:
            return self._broker_client

        broker_name = self._gates.get("broker.name")
        if not broker_name:
            raise RuntimeError("No broker configured in config.yaml")

        if broker_name == "tradier":
            self._broker_client = TradierClient(
                api_key=self._gates.get("broker.api_key", ""),
                sandbox=self._gates.get("broker.sandbox", True),
            )
        elif broker_name == "alpaca":
            self._broker_client = AlpacaClient(
                api_key=self._gates.get("broker.api_key", ""),
                api_secret=self._gates.get("broker.api_secret", ""),
                sandbox=self._gates.get("broker.sandbox", True),
            )
        else:
            raise RuntimeError(
                f"Unsupported broker: {broker_name}. "
                f"Supported: tradier, alpaca"
            )

        return self._broker_client

    def _validate_order(self, order: Order) -> List[str]:
        """Validate order against safety limits. Returns list of issues."""
        issues = []
        max_size = self._gates.get("execution.max_order_size_usd", 1000.0)

        if order.price and order.quantity:
            est_value = order.price * order.quantity
            if est_value > max_size:
                issues.append(
                    f"Estimated order value ${est_value:,.2f} exceeds "
                    f"configured limit ${max_size:,.2f}"
                )

        if order.quantity <= 0:
            issues.append("Quantity must be positive")

        if order.order_type == OrderType.LIMIT and not order.price:
            issues.append("Limit orders require a price")

        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and not order.stop_price:
            issues.append("Stop orders require a stop price")

        return issues

    def _audit_log(self, event: str, details: Dict[str, Any]) -> None:
        """Append to immutable audit log."""
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event": event,
            **details,
        }
        log_file = self._log_dir / "execution_audit.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def create_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "market",
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """
        Create an order for user review and confirmation.

        The order is NOT submitted until the user explicitly confirms.
        """
        self._gates.require_execution()

        order = Order(
            order_id=self._generate_order_id(),
            symbol=symbol.upper(),
            side=OrderSide(side.lower()),
            order_type=OrderType(order_type.lower()),
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        issues = self._validate_order(order)
        if issues:
            for issue in issues:
                logger.warning(f"Order validation: {issue}")
            raise ValueError(f"Order validation failed: {'; '.join(issues)}")

        self._order_history.append(order)
        self._audit_log("order_created", order.to_dict())
        return order

    def confirm_and_submit(self, order: Order) -> Order:
        """
        Submit an order to the broker after user confirmation.

        If confirmation is required (default), the user must
        interactively approve the order.
        """
        self._gates.require_execution()

        paper = self._gates.paper_mode
        mode_label = "PAPER" if paper else "LIVE"

        # Confirmation gate
        desc = (
            f"[{mode_label}] {order.side.value.upper()} {order.quantity} "
            f"{order.symbol} @ {order.order_type.value}"
        )
        if order.price:
            desc += f" ${order.price:,.2f}"

        confirmed = self._gates.require_confirmation(desc)
        if not confirmed:
            order.status = OrderStatus.CANCELLED
            self._audit_log("order_cancelled_by_user", {"order_id": order.order_id})
            logger.info(f"Order {order.order_id} cancelled by user")
            return order

        order.user_confirmed = True

        if paper:
            order.status = OrderStatus.FILLED
            order.fill_price = order.price or 0.0
            order.filled_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            order.broker_order_id = f"PAPER-{order.order_id}"
            self._audit_log("paper_order_filled", order.to_dict())
            logger.info(f"[PAPER] Order filled: {order.order_id}")
        else:
            try:
                broker = self._get_broker()
                result = broker.submit_order(order)
                order.broker_order_id = result.get("id", "unknown")
                order.status = OrderStatus.SUBMITTED
                self._audit_log("order_submitted", order.to_dict())
                logger.info(f"[LIVE] Order submitted: {order.order_id}")
            except Exception as e:
                order.status = OrderStatus.FAILED
                self._audit_log("order_failed", {
                    "order_id": order.order_id,
                    "error": str(e),
                })
                logger.error(f"Order failed: {e}")
                raise

        return order

    def get_order_history(self) -> List[Dict[str, Any]]:
        """Return all orders placed in this session."""
        return [o.to_dict() for o in self._order_history]

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        for order in self._order_history:
            if order.order_id == order_id and order.status == OrderStatus.SUBMITTED:
                try:
                    if not self._gates.paper_mode:
                        broker = self._get_broker()
                        broker.cancel_order(order.broker_order_id)
                    order.status = OrderStatus.CANCELLED
                    self._audit_log("order_cancelled", {"order_id": order_id})
                    return True
                except Exception as e:
                    logger.error(f"Cancel failed: {e}")
                    return False
        return False


class TradierClient:
    """Minimal Tradier broker client for order routing."""

    def __init__(self, api_key: str, sandbox: bool = True):
        self.api_key = api_key
        self.base_url = (
            "https://sandbox.tradier.com/v1"
            if sandbox
            else "https://api.tradier.com/v1"
        )
        self.sandbox = sandbox

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def submit_order(self, order: Order) -> Dict[str, Any]:
        import requests
        account_id = os.environ.get("TRADIER_ACCOUNT_ID", "")
        if not account_id:
            raise RuntimeError("TRADIER_ACCOUNT_ID environment variable not set")

        payload = {
            "class": "equity",
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": str(order.quantity),
            "type": order.order_type.value,
            "duration": "day",
        }
        if order.price:
            payload["price"] = str(order.price)
        if order.stop_price:
            payload["stop"] = str(order.stop_price)

        resp = requests.post(
            f"{self.base_url}/accounts/{account_id}/orders",
            data=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json().get("order", {})

    def cancel_order(self, broker_order_id: str) -> None:
        import requests
        account_id = os.environ.get("TRADIER_ACCOUNT_ID", "")
        resp = requests.delete(
            f"{self.base_url}/accounts/{account_id}/orders/{broker_order_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()


class AlpacaClient:
    """Minimal Alpaca broker client for order routing."""

    def __init__(self, api_key: str, api_secret: str, sandbox: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = (
            "https://paper-api.alpaca.markets/v2"
            if sandbox
            else "https://api.alpaca.markets/v2"
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Content-Type": "application/json",
        }

    def submit_order(self, order: Order) -> Dict[str, Any]:
        import requests
        payload = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.value,
            "type": order.order_type.value,
            "time_in_force": "day",
        }
        if order.price:
            payload["limit_price"] = str(order.price)
        if order.stop_price:
            payload["stop_price"] = str(order.stop_price)

        resp = requests.post(
            f"{self.base_url}/orders",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def cancel_order(self, broker_order_id: str) -> None:
        import requests
        resp = requests.delete(
            f"{self.base_url}/orders/{broker_order_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
