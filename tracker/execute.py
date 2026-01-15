"""Trade execution via Interactive Brokers."""

from typing import Any

from ib_insync import IB, MarketOrder, Stock, Trade

from tracker.config import settings
from tracker.database import OrderDB, SessionLocal
from tracker.logger import logger
from tracker.models import Order, OrderSide, OrderStatus, OrderType, Signal, SignalAction
from tracker.portfolio import PortfolioManager


class TradeExecutor:
    """Execute trades via Interactive Brokers."""

    def __init__(self):
        self.ib = IB()
        self.portfolio_manager = PortfolioManager()
        self.connected = False

    def connect(self) -> bool:
        """Connect to IBKR TWS/Gateway.

        Returns:
            True if connected successfully
        """
        if self.connected:
            return True

        try:
            self.ib.connect(
                host=settings.ibkr_host,
                port=settings.ibkr_port,
                clientId=settings.ibkr_client_id,
                readonly=not settings.trading_enabled,  # Read-only if trading disabled
            )
            self.connected = True
            logger.info(
                f"Connected to IBKR",
                host=settings.ibkr_host,
                port=settings.ibkr_port,
                mode=settings.account_mode,
            )
            return True

        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            return False

    def disconnect(self):
        """Disconnect from IBKR."""
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            logger.info("Disconnected from IBKR")

    def get_current_price(self, ticker: str) -> float | None:
        """Get current market price for a ticker.

        Args:
            ticker: Stock ticker

        Returns:
            Current price or None if unavailable
        """
        try:
            contract = Stock(ticker, "SMART", "USD")
            self.ib.qualifyContracts(contract)

            # Get market data
            ticker_data = self.ib.reqMktData(contract)
            self.ib.sleep(2)  # Wait for data

            # Get last price or close price
            price = ticker_data.last or ticker_data.close

            # Cancel market data subscription
            self.ib.cancelMktData(contract)

            if price and price > 0:
                return float(price)

            logger.warning(f"No valid price for {ticker}")
            return None

        except Exception as e:
            logger.error(f"Error getting price for {ticker}: {e}")
            return None

    def place_order(
        self, ticker: str, side: OrderSide, notional_usd: float, signal_id: str | None = None
    ) -> Order | None:
        """Place an order.

        Args:
            ticker: Stock ticker
            side: BUY or SELL
            notional_usd: Dollar amount to trade
            signal_id: Optional signal ID that triggered this order

        Returns:
            Order object if successful, None otherwise
        """
        # Safety check: Trading enabled?
        if not settings.trading_enabled:
            logger.info(
                "TRADING_DISABLED - would have placed order",
                ticker=ticker,
                side=side.value,
                notional=notional_usd,
            )
            return None

        # Get current price
        price = self.get_current_price(ticker)
        if not price:
            logger.error(f"Cannot place order - no price for {ticker}")
            return None

        # Calculate quantity
        quantity = notional_usd / price

        # Round to reasonable precision
        if quantity < 1:
            logger.warning(f"Quantity too small for {ticker}: {quantity}")
            return None

        quantity = int(quantity)  # Round down to whole shares

        logger.info(
            f"Placing order",
            ticker=ticker,
            side=side.value,
            quantity=quantity,
            price=price,
            notional=notional_usd,
        )

        try:
            # Create contract
            contract = Stock(ticker, "SMART", "USD")
            self.ib.qualifyContracts(contract)

            # Create order
            ib_order = MarketOrder(side.value, quantity)

            # Place order
            trade = self.ib.placeOrder(contract, ib_order)

            # Create Order object
            order = Order(
                signal_id=signal_id,
                ticker=ticker,
                side=side,
                quantity=quantity,
                order_type=OrderType.MARKET,
                status=OrderStatus.SUBMITTED,
                broker_order_id=str(trade.order.orderId) if trade.order else None,
            )

            # Save to database
            db = SessionLocal()
            try:
                self.save_order(order, db)
            finally:
                db.close()

            logger.info(f"Order placed successfully", order_id=str(order.id), broker_id=order.broker_order_id)

            return order

        except Exception as e:
            logger.error(f"Error placing order for {ticker}: {e}")
            return None

    def save_order(self, order: Order, db: Any) -> None:
        """Save order to database."""
        db_order = OrderDB(
            id=str(order.id),
            signal_id=str(order.signal_id) if order.signal_id else None,
            ticker=order.ticker,
            side=order.side.value,
            quantity=order.quantity,
            order_type=order.order_type.value,
            status=order.status.value,
            broker_order_id=order.broker_order_id,
            filled_price=order.filled_price,
            filled_at=order.filled_at,
        )

        db.add(db_order)
        db.commit()

    def update_order_status(self, order_id: str, status: OrderStatus, db: Any) -> None:
        """Update order status in database."""
        db_order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
        if db_order:
            db_order.status = status.value
            db.commit()

    def execute_signal(self, signal: Signal) -> Order | None:
        """Execute a trading signal.

        Args:
            signal: Trading signal to execute

        Returns:
            Order if executed, None otherwise
        """
        if signal.action not in [SignalAction.BUY, SignalAction.SELL]:
            logger.info(f"Signal action {signal.action} not executable", ticker=signal.ticker)
            return None

        # Connect to IBKR if needed
        if not self.connect():
            logger.error("Cannot execute signal - not connected to IBKR")
            return None

        # Get current price
        price = self.get_current_price(signal.ticker)
        if not price:
            return None

        db = SessionLocal()
        try:
            # For BUY signals
            if signal.action == SignalAction.BUY:
                # Calculate position size
                position_size = self.portfolio_manager.calculate_position_size(signal, price, db)

                if not position_size:
                    logger.info(f"Position size check failed for {signal.ticker}")
                    return None

                # Place buy order
                order = self.place_order(
                    ticker=signal.ticker,
                    side=OrderSide.BUY,
                    notional_usd=position_size,
                    signal_id=str(signal.id),
                )

                return order

            # For SELL signals
            elif signal.action == SignalAction.SELL:
                # Get current position
                position = self.portfolio_manager.get_position(signal.ticker, db)

                if not position:
                    logger.warning(f"Cannot sell {signal.ticker} - no position found")
                    return None

                # Place sell order for entire position
                notional = position.quantity * price

                order = self.place_order(
                    ticker=signal.ticker,
                    side=OrderSide.SELL,
                    notional_usd=notional,
                    signal_id=str(signal.id),
                )

                # Close position in portfolio
                if order:
                    self.portfolio_manager.close_position(
                        signal.ticker, "SIGNAL_TRIGGERED_SELL", db
                    )

                return order

        finally:
            db.close()

    def get_account_value(self) -> float | None:
        """Get total account value from IBKR.

        Returns:
            Account value in USD or None if unavailable
        """
        if not self.connected:
            if not self.connect():
                return None

        try:
            account_values = self.ib.accountValues()

            for av in account_values:
                if av.tag == "NetLiquidation" and av.currency == "USD":
                    return float(av.value)

            logger.warning("NetLiquidation not found in account values")
            return None

        except Exception as e:
            logger.error(f"Error getting account value: {e}")
            return None
