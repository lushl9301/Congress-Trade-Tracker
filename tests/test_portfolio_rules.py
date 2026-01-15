from app.portfolio import (
    DEFAULT_EXIT_RULE,
    DEFAULT_MAX_HOLD_DAYS,
    DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT,
    build_position_metadata,
)


def test_default_position_metadata() -> None:
    metadata = build_position_metadata()
    assert metadata["exit_rule"] == DEFAULT_EXIT_RULE
    assert metadata["max_hold_days"] == DEFAULT_MAX_HOLD_DAYS
    assert metadata["stop_loss_pct"] == DEFAULT_STOP_LOSS_PCT
    assert metadata["take_profit_pct"] == DEFAULT_TAKE_PROFIT_PCT
    assert metadata["opened_at"] == metadata["last_updated_at"]
