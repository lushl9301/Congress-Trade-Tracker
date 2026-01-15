from datetime import date

from app.db import Database
from app.models import CongressTradeEvent
from app.strategy import generate_signals


def test_watch_signal_mapping() -> None:
    db = Database(":memory:")
    db.init_schema()

    event = CongressTradeEvent(
        event_id="event-2",
        source="finnhub",
        member_name="Test Member",
        member_id=None,
        owner="unknown",
        ticker="WATCH",
        asset_type="stock",
        transaction_type="BUY",
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 11),
        amount_low=5000,
        amount_high=7000,
        currency="USD",
        raw={"symbol": "WATCH"},
        delay_days=10,
        amount_mid=6000,
    )

    db.upsert_events([event])
    generate_signals(db)

    cursor = db._conn.cursor()
    cursor.execute("SELECT strength, action FROM signals WHERE event_id = ?", (event.event_id,))
    row = cursor.fetchone()
    assert row["strength"] == "WATCH"
    assert row["action"] == "BUY"
    db.close()
