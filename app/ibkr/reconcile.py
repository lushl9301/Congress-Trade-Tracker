"""
Reconciliation module for syncing IBKR state with local database.
Ensures consistency between broker and local tracking.
"""
from typing import Any

from app.config import config
from app.db import db
from app.ibkr.client import get_ibkr_client
from app.logging import get_logger
from app.portfolio import portfolio_manager

logger = get_logger(__name__)


class IBKRReconciler:
    """Reconcile IBKR positions and orders with local database."""

    def __init__(self):
        """Initialize reconciler."""
        self.client = get_ibkr_client()

    def reconcile_positions(self) -> dict[str, Any]:
        """
        Reconcile positions between IBKR and local database.

        Compares IBKR positions with local positions and reports discrepancies.

        Returns:
            Reconciliation summary
        """
        if not config.TRADING_ENABLED:
            logger.info("Trading disabled, skipping position reconciliation")
            return {
                "status": "skipped",
                "reason": "trading_disabled",
            }

        if not self.client.ensure_connected():
            logger.error("Cannot reconcile: not connected to IBKR")
            return {
                "status": "error",
                "reason": "not_connected",
            }

        try:
            # Get positions from IBKR
            ibkr_positions = self.client.get_positions()
            ibkr_tickers = {pos["ticker"] for pos in ibkr_positions}

            # Get positions from local DB
            local_positions = db.get_all_positions()
            local_tickers = {pos.ticker for pos in local_positions}

            # Find discrepancies
            only_in_ibkr = ibkr_tickers - local_tickers
            only_in_local = local_tickers - ibkr_tickers
            in_both = ibkr_tickers & local_tickers

            discrepancies = []

            # Check positions in both
            for ticker in in_both:
                ibkr_pos = next(p for p in ibkr_positions if p["ticker"] == ticker)
                local_pos = next(p for p in local_positions if p.ticker == ticker)

                if abs(ibkr_pos["qty"] - local_pos.qty) > 0.01:
                    discrepancies.append(
                        {
                            "ticker": ticker,
                            "type": "qty_mismatch",
                            "ibkr_qty": ibkr_pos["qty"],
                            "local_qty": local_pos.qty,
                        }
                    )

            # Report positions only in IBKR
            for ticker in only_in_ibkr:
                ibkr_pos = next(p for p in ibkr_positions if p["ticker"] == ticker)
                discrepancies.append(
                    {
                        "ticker": ticker,
                        "type": "only_in_ibkr",
                        "ibkr_qty": ibkr_pos["qty"],
                        "local_qty": 0,
                    }
                )

            # Report positions only in local
            for ticker in only_in_local:
                local_pos = next(p for p in local_positions if p.ticker == ticker)
                discrepancies.append(
                    {
                        "ticker": ticker,
                        "type": "only_in_local",
                        "ibkr_qty": 0,
                        "local_qty": local_pos.qty,
                    }
                )

            summary = {
                "status": "success",
                "ibkr_positions": len(ibkr_positions),
                "local_positions": len(local_positions),
                "discrepancies": len(discrepancies),
                "details": discrepancies,
            }

            if discrepancies:
                logger.warning(f"Found {len(discrepancies)} position discrepancies")
                for disc in discrepancies:
                    logger.warning(f"  {disc}")
            else:
                logger.info("Positions reconciled successfully, no discrepancies")

            return summary

        except Exception as e:
            logger.error(f"Failed to reconcile positions: {e}")
            return {
                "status": "error",
                "reason": str(e),
            }

    def reconcile_orders(self) -> dict[str, Any]:
        """
        Reconcile open orders between IBKR and local database.

        Returns:
            Reconciliation summary
        """
        if not config.TRADING_ENABLED:
            logger.info("Trading disabled, skipping order reconciliation")
            return {
                "status": "skipped",
                "reason": "trading_disabled",
            }

        if not self.client.ensure_connected():
            logger.error("Cannot reconcile: not connected to IBKR")
            return {
                "status": "error",
                "reason": "not_connected",
            }

        try:
            # Get open orders from IBKR
            ibkr_orders = self.client.ib.openOrders()

            logger.info(f"Found {len(ibkr_orders)} open orders in IBKR")

            # For each IBKR order, check if we have it locally
            # This is a simple check for MVP
            summary = {
                "status": "success",
                "ibkr_open_orders": len(ibkr_orders),
                "orders": [
                    {
                        "ibkr_order_id": order.orderId,
                        "ticker": order.contract.symbol,
                        "action": order.action,
                        "qty": order.totalQuantity,
                        "status": "open",
                    }
                    for order in ibkr_orders
                ],
            }

            return summary

        except Exception as e:
            logger.error(f"Failed to reconcile orders: {e}")
            return {
                "status": "error",
                "reason": str(e),
            }

    def get_account_summary(self) -> dict[str, Any]:
        """
        Get account summary from IBKR.

        Returns:
            Account summary
        """
        if not config.TRADING_ENABLED:
            return {
                "status": "skipped",
                "reason": "trading_disabled",
            }

        if not self.client.ensure_connected():
            logger.error("Cannot get account summary: not connected to IBKR")
            return {
                "status": "error",
                "reason": "not_connected",
            }

        try:
            net_liquidation = self.client.get_account_value("NetLiquidation")
            total_cash = self.client.get_account_value("TotalCashValue")
            buying_power = self.client.get_account_value("BuyingPower")

            return {
                "status": "success",
                "net_liquidation": net_liquidation,
                "total_cash": total_cash,
                "buying_power": buying_power,
                "mode": config.TRADING_MODE,
            }

        except Exception as e:
            logger.error(f"Failed to get account summary: {e}")
            return {
                "status": "error",
                "reason": str(e),
            }


def run_reconciliation() -> dict[str, Any]:
    """
    Run full reconciliation: positions, orders, and account summary.

    This is the main entry point for the 'reconcile' CLI command.

    Returns:
        Reconciliation summary
    """
    logger.info("Starting reconciliation")

    reconciler = IBKRReconciler()

    # Reconcile positions
    positions_result = reconciler.reconcile_positions()

    # Reconcile orders
    orders_result = reconciler.reconcile_orders()

    # Get account summary
    account_result = reconciler.get_account_summary()

    summary = {
        "status": "success",
        "positions": positions_result,
        "orders": orders_result,
        "account": account_result,
    }

    logger.info("Reconciliation complete")

    return summary


# Global reconciler instance
reconciler = IBKRReconciler()
