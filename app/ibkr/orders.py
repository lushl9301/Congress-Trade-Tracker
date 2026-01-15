"""
Order placement and management for IBKR.
Handles order creation, submission, and status tracking.
"""
import time
import uuid
from typing import Any, Literal

from app.config import config
from app.db import db
from app.ibkr.client import get_ibkr_client
from app.logging import get_logger
from app.models import Fill, Order

logger = get_logger(__name__)


class OrderManager:
    """Manages order placement and tracking with IBKR."""

    def __init__(self):
        """Initialize order manager."""
        self.client = get_ibkr_client()

    def place_order(
        self,
        ticker: str,
        side: Literal["BUY", "SELL"],
        qty: float,
        order_type: str = "MKT",
        limit_price: float | None = None,
        signal_id: str | None = None,
    ) -> Order | None:
        """
        Place an order with IBKR.

        Args:
            ticker: Stock ticker
            side: BUY or SELL
            qty: Quantity
            order_type: Order type (MKT, LMT, etc.)
            limit_price: Limit price (required for LMT orders)
            signal_id: Optional signal ID that triggered this order

        Returns:
            Order object if successful, None otherwise
        """
        # Safety check
        if not config.TRADING_ENABLED:
            logger.warning(
                f"TRADING_ENABLED=false, would place order: {side} {qty} {ticker} @ {order_type}"
            )
            # Create a mock order for tracking
            order = self._create_mock_order(ticker, side, qty, order_type, limit_price, signal_id)
            db.insert_order(order)
            return order

        # Connect to IBKR
        if not self.client.ensure_connected():
            logger.error("Cannot place order: not connected to IBKR")
            return None

        try:
            from ib_insync import MarketOrder, LimitOrder

            # Create contract
            contract = self.client.get_stock_contract(ticker)
            self.client.ib.qualifyContracts(contract)

            # Create order
            if order_type == "MKT":
                ib_order = MarketOrder(side, qty)
            elif order_type == "LMT":
                if limit_price is None:
                    logger.error("Limit price required for LMT order")
                    return None
                ib_order = LimitOrder(side, qty, limit_price)
            else:
                logger.error(f"Unsupported order type: {order_type}")
                return None

            # Place order
            logger.info(
                f"Placing order: {side} {qty} {ticker} @ {order_type} "
                f"(mode={config.TRADING_MODE})"
            )

            trade = self.client.ib.placeOrder(contract, ib_order)

            # Create order record
            order_id = str(uuid.uuid4())
            order = Order(
                order_id=order_id,
                ibkr_order_id=trade.order.orderId,
                ibkr_perm_id=trade.order.permId,
                ticker=ticker,
                side=side,
                qty=qty,
                order_type=order_type,
                limit_price=limit_price,
                tif="DAY",
                status="SUBMITTED",
                request_payload={
                    "ticker": ticker,
                    "side": side,
                    "qty": qty,
                    "order_type": order_type,
                    "limit_price": limit_price,
                },
                response_payload={
                    "ibkr_order_id": trade.order.orderId,
                    "ibkr_perm_id": trade.order.permId,
                    "status": trade.orderStatus.status,
                },
                signal_id=signal_id,
            )

            db.insert_order(order)
            logger.info(f"Order placed successfully: {order_id} (IBKR: {trade.order.orderId})")

            return order

        except ImportError:
            logger.error("ib_insync not installed. Cannot place orders.")
            return None
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return None

    def _create_mock_order(
        self,
        ticker: str,
        side: Literal["BUY", "SELL"],
        qty: float,
        order_type: str,
        limit_price: float | None,
        signal_id: str | None,
    ) -> Order:
        """Create a mock order when trading is disabled."""
        order_id = str(uuid.uuid4())

        return Order(
            order_id=order_id,
            ticker=ticker,
            side=side,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price,
            tif="DAY",
            status="MOCK_DISABLED",
            request_payload={
                "ticker": ticker,
                "side": side,
                "qty": qty,
                "order_type": order_type,
                "limit_price": limit_price,
                "note": "Trading disabled, order not submitted",
            },
            signal_id=signal_id,
        )

    def poll_order_status(self, order_id: str, timeout: int = 60) -> str:
        """
        Poll order status until terminal state or timeout.

        Args:
            order_id: Local order ID
            timeout: Timeout in seconds

        Returns:
            Final order status
        """
        order = db.get_order(order_id)
        if not order:
            logger.error(f"Order {order_id} not found")
            return "ERROR"

        if not config.TRADING_ENABLED or order.status == "MOCK_DISABLED":
            logger.info(f"Order {order_id} is mock/disabled, skipping status poll")
            return order.status

        if not self.client.ensure_connected():
            logger.error("Cannot poll order status: not connected to IBKR")
            return "ERROR"

        try:
            start_time = time.time()
            terminal_states = ["Filled", "Cancelled", "ApiCancelled", "Inactive"]

            while time.time() - start_time < timeout:
                # Get order status from IBKR
                trades = self.client.ib.trades()

                for trade in trades:
                    if trade.order.orderId == order.ibkr_order_id:
                        status = trade.orderStatus.status

                        # Update database
                        db.update_order_status(
                            order_id,
                            status,
                            response_payload={
                                "status": status,
                                "filled": trade.orderStatus.filled,
                                "remaining": trade.orderStatus.remaining,
                                "avg_fill_price": trade.orderStatus.avgFillPrice,
                            },
                        )

                        logger.info(f"Order {order_id} status: {status}")

                        # Check if terminal
                        if status in terminal_states:
                            # Process fills if filled
                            if status == "Filled" and trade.fills:
                                self._process_fills(order_id, trade.fills)

                            return status

                # Wait before next poll
                time.sleep(2)

            logger.warning(f"Order {order_id} status poll timed out")
            return "TIMEOUT"

        except Exception as e:
            logger.error(f"Error polling order status: {e}")
            return "ERROR"

    def _process_fills(self, order_id: str, ib_fills: list) -> None:
        """
        Process fills from IBKR and update database.

        Args:
            order_id: Local order ID
            ib_fills: List of IB Fill objects
        """
        order = db.get_order(order_id)
        if not order:
            return

        for ib_fill in ib_fills:
            fill_id = f"{order_id}_{ib_fill.execution.execId}"

            # Check if fill already processed
            existing_fills = db.get_fills_for_order(order_id)
            if any(f.ibkr_exec_id == ib_fill.execution.execId for f in existing_fills):
                continue

            # Create fill record
            fill = Fill(
                fill_id=fill_id,
                order_id=order_id,
                ibkr_exec_id=ib_fill.execution.execId,
                ticker=order.ticker,
                side=order.side,
                qty=ib_fill.execution.shares,
                price=ib_fill.execution.avgPrice,
                commission=ib_fill.commissionReport.commission
                if ib_fill.commissionReport
                else 0.0,
            )

            db.insert_fill(fill)

            # Update portfolio
            from app.portfolio import portfolio_manager

            portfolio_manager.process_fill(fill)

            logger.info(
                f"Processed fill: {fill.side} {fill.qty} {fill.ticker} @ {fill.price}"
            )

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Local order ID

        Returns:
            True if successful
        """
        order = db.get_order(order_id)
        if not order:
            logger.error(f"Order {order_id} not found")
            return False

        if not config.TRADING_ENABLED:
            logger.info(f"Trading disabled, marking mock order {order_id} as cancelled")
            db.update_order_status(order_id, "MOCK_CANCELLED")
            return True

        if not self.client.ensure_connected():
            logger.error("Cannot cancel order: not connected to IBKR")
            return False

        try:
            trades = self.client.ib.trades()

            for trade in trades:
                if trade.order.orderId == order.ibkr_order_id:
                    self.client.ib.cancelOrder(trade.order)
                    db.update_order_status(order_id, "Cancelled")
                    logger.info(f"Cancelled order {order_id}")
                    return True

            logger.warning(f"Order {order_id} not found in IBKR trades")
            return False

        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False


# Global order manager instance
order_manager = OrderManager()
