"""FastAPI application entrypoint for the ExpenseFlow API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create database tables on startup if they don't already exist."""
    init_db()
    yield


app = FastAPI(title="ExpenseFlow API", lifespan=lifespan)
app.include_router(router)
