"""API routes for submitting, listing, and deciding on expenses."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.insights import generate_insight
from app.models import Expense
from app.schemas import DecisionIn, ExpenseCreate, ExpenseOut

router = APIRouter()


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(expense_in: ExpenseCreate, db: Session = Depends(get_db)) -> Expense:
    """Submit a new expense as PENDING, normalized to base currency (INR)."""
    now = datetime.now(timezone.utc)
    expense = Expense(
        description=expense_in.description,
        amount_minor=expense_in.amount_minor,
        currency=expense_in.currency,
        category=expense_in.category,
        submitted_by=expense_in.submitted_by,
        # TODO: replace with a real FX conversion (fx.py) once implemented.
        amount_base_minor=expense_in.amount_minor,
        base_currency="INR",
        fx_rate=1.0,
        fx_rate_fetched_at=now,
        status="PENDING",
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    status: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> list[Expense]:
    """List expenses, optionally filtered by status and/or category."""
    query = db.query(Expense)
    if status is not None:
        query = query.filter(Expense.status == status)
    if category is not None:
        query = query.filter(Expense.category == category)
    return query.all()


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, db: Session = Depends(get_db)) -> Expense:
    """Fetch a single expense by id."""
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.post("/expenses/{expense_id}/approve", response_model=ExpenseOut)
def approve_expense(
    expense_id: int, decision_in: DecisionIn = DecisionIn(), db: Session = Depends(get_db)
) -> Expense:
    """Approve a pending expense."""
    return _decide(expense_id, "APPROVED", decision_in.note, db)


@router.post("/expenses/{expense_id}/reject", response_model=ExpenseOut)
def reject_expense(
    expense_id: int, decision_in: DecisionIn = DecisionIn(), db: Session = Depends(get_db)
) -> Expense:
    """Reject a pending expense."""
    return _decide(expense_id, "REJECTED", decision_in.note, db)


@router.get("/reports/insights")
def get_insights(db: Session = Depends(get_db)) -> dict[str, str]:
    """Generate short spending insights across all expenses."""
    expenses = db.query(Expense).all()
    expense_dicts = [
        {
            "amount_base_minor": expense.amount_base_minor,
            "category": expense.category,
            "status": expense.status,
        }
        for expense in expenses
    ]
    return {"insight": generate_insight(expense_dicts)}


def _decide(expense_id: int, new_status: str, note: str | None, db: Session) -> Expense:
    """Transition a PENDING expense to APPROVED or REJECTED."""
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    if expense.status != "PENDING":
        raise HTTPException(status_code=409, detail="Expense is not pending")
    expense.status = new_status
    expense.decided_at = datetime.now(timezone.utc)
    expense.decision_note = note
    db.commit()
    db.refresh(expense)
    return expense
