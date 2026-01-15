"""Database setup and models using SQLAlchemy."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from tracker.config import settings

# Create engine
engine = create_engine(settings.database_url, echo=False)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# Database Models
class DisclosureDB(Base):
    """Congressional trade disclosure table."""

    __tablename__ = "disclosures"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    source = Column(String, nullable=False, index=True)
    politician = Column(String, nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    transaction_type = Column(String, nullable=False)
    trade_date = Column(DateTime, nullable=True, index=True)
    disclosure_date = Column(DateTime, nullable=True, index=True)
    amount_min = Column(Float, nullable=False)
    amount_max = Column(Float, nullable=False)
    amount_estimate = Column(Float, nullable=False)
    delay_days = Column(Integer, nullable=True)
    raw_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    signals = relationship("SignalDB", back_populates="disclosure")


class SignalDB(Base):
    """Trading signal table."""

    __tablename__ = "signals"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    disclosure_id = Column(String, ForeignKey("disclosures.id"), nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    confidence = Column(String, nullable=False)
    score = Column(Integer, nullable=False)
    reasons = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    disclosure = relationship("DisclosureDB", back_populates="signals")
    orders = relationship("OrderDB", back_populates="signal")


class PositionDB(Base):
    """Portfolio position table."""

    __tablename__ = "positions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    ticker = Column(String, unique=True, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    avg_cost = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    unrealized_pnl = Column(Float, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    opened_by_signals = Column(JSON, nullable=False)  # List of signal UUIDs
    exit_strategy = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="OPEN", index=True)


class OrderDB(Base):
    """Trade order table."""

    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    signal_id = Column(String, ForeignKey("signals.id"), nullable=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    order_type = Column(String, nullable=False, default="MARKET")
    status = Column(String, nullable=False, default="PENDING", index=True)
    broker_order_id = Column(String, nullable=True)
    filled_price = Column(Float, nullable=True)
    filled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    signal = relationship("SignalDB", back_populates="orders")


class PortfolioSnapshotDB(Base):
    """Portfolio snapshot table."""

    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    total_value = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    positions_value = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False)
    realized_pnl = Column(Float, nullable=False)
    num_positions = Column(Integer, nullable=False)


def init_db():
    """Initialize the database (create all tables)."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
