"""
Interactive Brokers client using ib_insync library.
Handles connection to TWS/IB Gateway.
"""
from typing import Any

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)


class IBKRClient:
    """
    IBKR client wrapper using ib_insync.

    Handles connection and basic operations with Interactive Brokers.
    """

    def __init__(self):
        """Initialize IBKR client (lazy connection)."""
        self.ib = None
        self.connected = False

    def connect(self) -> bool:
        """
        Connect to IBKR TWS or IB Gateway.

        Returns:
            True if connection successful
        """
        try:
            from ib_insync import IB

            self.ib = IB()

            logger.info(
                f"Connecting to IBKR at {config.IBKR_HOST}:{config.IBKR_PORT} "
                f"(client_id={config.IBKR_CLIENT_ID}, mode={config.TRADING_MODE})"
            )

            self.ib.connect(
                host=config.IBKR_HOST,
                port=config.IBKR_PORT,
                clientId=config.IBKR_CLIENT_ID,
                readonly=False,
            )

            self.connected = True
            logger.info("Successfully connected to IBKR")

            # Log account info
            accounts = self.ib.managedAccounts()
            logger.info(f"Connected accounts: {accounts}")

            return True

        except ImportError:
            logger.error(
                "ib_insync not installed. Install with: pip install ib_insync"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            self.connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from IBKR."""
        if self.ib and self.connected:
            try:
                self.ib.disconnect()
                logger.info("Disconnected from IBKR")
            except Exception as e:
                logger.error(f"Error disconnecting from IBKR: {e}")
            finally:
                self.connected = False

    def ensure_connected(self) -> bool:
        """
        Ensure connection is active, reconnect if needed.

        Returns:
            True if connected
        """
        if not self.connected or not self.ib or not self.ib.isConnected():
            return self.connect()
        return True

    def get_stock_contract(self, ticker: str, exchange: str = "SMART") -> Any:
        """
        Create a stock contract for a ticker.

        Args:
            ticker: Stock ticker symbol
            exchange: Exchange (default: SMART for smart routing)

        Returns:
            IB Stock contract
        """
        from ib_insync import Stock

        return Stock(ticker, exchange, "USD")

    def get_market_price(self, ticker: str) -> float | None:
        """
        Get current market price for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Current price or None if unavailable
        """
        if not self.ensure_connected():
            return None

        try:
            contract = self.get_stock_contract(ticker)
            self.ib.qualifyContracts(contract)

            # Request market data
            ticker_data = self.ib.reqMktData(contract, "", False, False)
            self.ib.sleep(2)  # Wait for data

            # Get last price
            if ticker_data.last and ticker_data.last > 0:
                price = ticker_data.last
            elif ticker_data.close and ticker_data.close > 0:
                price = ticker_data.close
            else:
                price = None

            # Cancel market data subscription
            self.ib.cancelMktData(contract)

            return price

        except Exception as e:
            logger.error(f"Failed to get market price for {ticker}: {e}")
            return None

    def get_account_value(self, tag: str = "NetLiquidation") -> float:
        """
        Get account value.

        Args:
            tag: Account value tag (NetLiquidation, TotalCashValue, etc.)

        Returns:
            Account value
        """
        if not self.ensure_connected():
            return 0.0

        try:
            account_values = self.ib.accountValues()

            for av in account_values:
                if av.tag == tag and av.currency == "USD":
                    return float(av.value)

            logger.warning(f"Account value tag '{tag}' not found")
            return 0.0

        except Exception as e:
            logger.error(f"Failed to get account value: {e}")
            return 0.0

    def get_positions(self) -> list[dict[str, Any]]:
        """
        Get current IBKR positions.

        Returns:
            List of position dicts
        """
        if not self.ensure_connected():
            return []

        try:
            positions = self.ib.positions()

            result = []
            for pos in positions:
                result.append(
                    {
                        "ticker": pos.contract.symbol,
                        "qty": pos.position,
                        "avg_cost": pos.avgCost,
                        "market_value": pos.position * pos.marketPrice
                        if pos.marketPrice
                        else 0,
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


# Global client instance
_ibkr_client: IBKRClient | None = None


def get_ibkr_client() -> IBKRClient:
    """Get or create global IBKR client instance."""
    global _ibkr_client
    if _ibkr_client is None:
        _ibkr_client = IBKRClient()
    return _ibkr_client
