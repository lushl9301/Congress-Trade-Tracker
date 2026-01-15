from datetime import date

from app.db import Database
from app.models import CongressTradeEvent


def test_event_deduplication() -> None:
    db = Database(":memory:")
    db.init_schema()

    event = CongressTradeEvent(
        event_id="abc",
        source="finnhub",
        member_name="Test Member",
        member_id=None,
        owner="member",
        ticker="ABC",
        asset_type="stock",
        transaction_type="BUY",
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 2),
        amount_low=10000,
        amount_high=20000,
        currency="USD",
        raw={"symbol": "ABC"},
        delay_days=1,
        amount_mid=15000,
    )

    inserted_first = db.upsert_events([event])
    inserted_second = db.upsert_events([event])

    assert inserted_first == 1
    assert inserted_second == 0
    db.close()
