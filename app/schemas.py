"""Pydantic v2 request and response models for the expenses API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExpenseCreate(BaseModel):
    """Request body for submitting a new expense."""

    description: str
    amount_minor: int = Field(gt=0)
    currency: str
    category: str
    submitted_by: str

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        """Uppercase and enforce a 3-letter ISO 4217-style currency code."""
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter code")
        return value


class DecisionIn(BaseModel):
    """Optional request body for approve/reject endpoints."""

    note: str | None = None


class ExpenseOut(BaseModel):
    """Response body representing a persisted expense."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    amount_minor: int
    currency: str
    category: str
    submitted_by: str
    amount_base_minor: int
    base_currency: str
    fx_rate: float
    fx_rate_fetched_at: datetime
    status: str
    created_at: datetime
    decided_at: datetime | None
    decision_note: str | None
