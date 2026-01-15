from datetime import date

from app.db import Database
from app.models import CongressTradeEvent
from app.strategy import generate_signals


def test_strong_buy_scoring() -> None:
    db = Database(":memory:")
    db.init_schema()

    event = CongressTradeEvent(
        event_id="event-1",
        source="finnhub",
        member_name="Test Member",
        member_id=None,
        owner="member",
        ticker="XYZ",
        asset_type="stock",
        transaction_type="BUY",
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 2),
        amount_low=200000,
        amount_high=300000,
        currency="USD",
        raw={"symbol": "XYZ"},
        delay_days=1,
        amount_mid=250000,
    )

    db.upsert_events([event])
    summary = generate_signals(db)
    assert summary["inserted"] == 1

    cursor = db._conn.cursor()
    cursor.execute("SELECT strength, action FROM signals WHERE event_id = ?", (event.event_id,))
    row = cursor.fetchone()
    assert row["strength"] == "STRONG"
    assert row["action"] == "BUY"
    db.close()
