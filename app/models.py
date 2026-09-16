"""SQLAlchemy ORM model for the expenses table."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    """Return the current UTC time; used as the default for timestamp columns."""
    return datetime.now(timezone.utc)


class Expense(Base):
    """An expense submission, normalized to base currency (INR) and tracked through approval."""

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_expenses_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(nullable=False)
    amount_minor: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(nullable=False)
    submitted_by: Mapped[str] = mapped_column(nullable=False)
    amount_base_minor: Mapped[int] = mapped_column(nullable=False)
    base_currency: Mapped[str] = mapped_column(nullable=False, default="INR")
    fx_rate: Mapped[float] = mapped_column(nullable=False)
    fx_rate_fetched_at: Mapped[datetime] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decision_note: Mapped[str | None] = mapped_column(nullable=True)
