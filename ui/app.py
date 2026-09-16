"""Streamlit front end for the ExpenseFlow API: submit expenses, list them, and view spending insights."""

import os

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")


def _show_connection_error(exc: httpx.RequestError) -> None:
    """Render a friendly message for connection failures instead of a stack trace."""
    st.error(f"Couldn't reach the ExpenseFlow API at {API_BASE}. Is it running? ({exc})")


def _show_api_error(exc: httpx.HTTPStatusError) -> None:
    """Render a friendly message for non-2xx API responses instead of a stack trace."""
    try:
        detail = exc.response.json().get("detail", exc.response.text)
    except ValueError:
        detail = exc.response.text
    st.error(f"The API returned an error: {detail}")


_STATUS_COLORS = {
    "APPROVED": "#d4edda",
    "REJECTED": "#f8d7da",
    "PENDING": "#fff3cd",
}


def _style_status(status: str) -> str:
    """Return a CSS background color for a status cell."""
    return f"background-color: {_STATUS_COLORS.get(status, '#ffffff')}"


def _decide_expense(expense_id: int, decision: str) -> None:
    """Call the approve/reject endpoint for an expense and refresh the page."""
    try:
        response = httpx.post(f"{API_BASE}/expenses/{expense_id}/{decision}", json={}, timeout=10.0)
        response.raise_for_status()
    except httpx.RequestError as exc:
        _show_connection_error(exc)
    except httpx.HTTPStatusError as exc:
        _show_api_error(exc)
    else:
        st.rerun()


st.set_page_config(page_title="ExpenseFlow", page_icon="\U0001F4B0")
st.title("ExpenseFlow")

st.header("Submit a new expense")
with st.form("submit_expense_form", clear_on_submit=True):
    amount = st.number_input("Amount", min_value=0.0, step=0.01, format="%.2f")
    currency = st.text_input("Currency", value="INR", max_chars=3)
    category = st.text_input("Category")
    description = st.text_input("Description")
    submitted_by = st.text_input("Submitted by")
    submitted = st.form_submit_button("Submit expense")

if submitted:
    payload = {
        "amount_minor": int(round(amount * 100)),
        "currency": currency,
        "category": category,
        "description": description,
        "submitted_by": submitted_by,
    }
    try:
        response = httpx.post(f"{API_BASE}/expenses", json=payload, timeout=10.0)
        response.raise_for_status()
    except httpx.RequestError as exc:
        _show_connection_error(exc)
    except httpx.HTTPStatusError as exc:
        _show_api_error(exc)
    else:
        st.success(f"Expense #{response.json()['id']} submitted.")

st.header("Review expenses")
try:
    response = httpx.get(f"{API_BASE}/expenses", params={"status": "PENDING"}, timeout=10.0)
    response.raise_for_status()
except httpx.RequestError as exc:
    _show_connection_error(exc)
except httpx.HTTPStatusError as exc:
    _show_api_error(exc)
else:
    pending_expenses = response.json()
    if not pending_expenses:
        st.info("No expenses are pending review.")
    for expense in pending_expenses:
        cols = st.columns([4, 1, 1])
        cols[0].write(
            f"**#{expense['id']}** {expense['description']} — "
            f"{expense['amount_base_minor'] / 100:.2f} {expense['base_currency']} "
            f"({expense['category']}, submitted by {expense['submitted_by']})"
        )
        if cols[1].button("Approve", key=f"approve_{expense['id']}"):
            _decide_expense(expense["id"], "approve")
        if cols[2].button("Reject", key=f"reject_{expense['id']}"):
            _decide_expense(expense["id"], "reject")

st.header("Existing expenses")
try:
    response = httpx.get(f"{API_BASE}/expenses", timeout=10.0)
    response.raise_for_status()
except httpx.RequestError as exc:
    _show_connection_error(exc)
except httpx.HTTPStatusError as exc:
    _show_api_error(exc)
else:
    expenses = response.json()
    if expenses:
        df = pd.DataFrame(expenses)
        df["amount_minor"] = (df["amount_minor"] / 100).round(2)
        df["amount_base_minor"] = (df["amount_base_minor"] / 100).round(2)
        df = df.rename(columns={"amount_minor": "amount", "amount_base_minor": "amount_base"})
        st.dataframe(
            df.style.map(_style_status, subset=["status"]),
            use_container_width=True,
            column_config={
                "amount": st.column_config.NumberColumn(format="%.2f"),
                "amount_base": st.column_config.NumberColumn(format="%.2f"),
            },
        )
    else:
        st.info("No expenses submitted yet.")

st.header("Insights")
if st.button("Generate insights"):
    try:
        response = httpx.get(f"{API_BASE}/reports/insights", timeout=30.0)
        response.raise_for_status()
    except httpx.RequestError as exc:
        _show_connection_error(exc)
    except httpx.HTTPStatusError as exc:
        _show_api_error(exc)
    else:
        st.markdown(response.json()["insight"])
