"""Database utilities for the option chain builder.

Imports are deliberately side-effect-free: the engine is created lazily on
first use, and ``create_all`` is wrapped so a temporarily-unreachable database
does not prevent the rest of the application (notably the MCP server) from
starting.
"""

import logging
from functools import lru_cache
from typing import List, Dict

from sqlmodel import Field, SQLModel, create_engine, Session, select
from sqlalchemy.exc import SQLAlchemyError

from settings.config import DATABASE_URL

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_engine():
    """Return a lazily-initialised SQLAlchemy engine.

    The engine is created the first time it's actually needed rather than at
    import time, so a temporary DB outage does not crash module imports.
    """
    return create_engine(DATABASE_URL)


def init_database() -> None:
    """Create the option chain tables if they do not yet exist.

    Best-effort: a failure is logged but does not raise — the MCP server
    should still be able to boot even when Postgres is briefly unavailable.
    Callers that need the tables to be present should re-invoke this method
    before issuing writes.
    """
    try:
        SQLModel.metadata.create_all(get_engine())
    except SQLAlchemyError as exc:
        logger.warning(
            "init_database: create_all failed (%s: %s). "
            "Tables may be missing until the DB is reachable.",
            type(exc).__name__, exc,
        )


class OptionChain(SQLModel, table=True):
    conid: str = Field(primary_key=True)
    symbol: str
    maturity_date: str
    strike: str
    right: str


def store_data(option_data: List[Dict[str, str | None]]) -> None:
    """Store option chain data in the database.

    Args:
        option_data: List of dictionaries containing option contract data

    A per-record ``try/except`` isolates individual bad rows so that one
    malformed record does not discard the entire batch.
    """
    if not option_data:
        return

    # Best-effort schema setup. If it has already run, this is a no-op.
    init_database()

    with Session(get_engine()) as orm_session:
        for data in option_data:
            try:
                # Filter out None values before creating OptionChain
                filtered_data = {k: v for k, v in data.items() if v is not None}
                if filtered_data:  # Only merge if we have valid data
                    orm_session.merge(OptionChain(**filtered_data))
            except (SQLAlchemyError, TypeError, ValueError) as exc:
                # Skip the bad row but keep the rest of the batch.
                logger.warning(
                    "store_data: skipping malformed record (%s: %s) data=%r",
                    type(exc).__name__, exc, data,
                )
                continue
        try:
            orm_session.commit()
        except SQLAlchemyError as exc:
            logger.error(
                "store_data: commit failed (%s: %s); rolling back batch.",
                type(exc).__name__, exc,
            )
            orm_session.rollback()
            raise


def query_option_chain(symbol: str) -> List[Dict[str, str]]:
    """
    Query option chain data from the database for a specific symbol (underlier).

    Args:
        symbol: Stock/ETF/Index symbol to query (e.g., "SPY", "CL", "ES")

    Returns:
        List of dictionaries containing option contract data for the symbol.
        Each dictionary contains: conid, symbol, maturity_date, strike, right

    Raises:
        sqlalchemy.exc.SQLAlchemyError: on database access failure. Callers
            are responsible for translating this into a user-facing message.
    """
    with Session(get_engine()) as orm_session:
        # Query all records matching the symbol
        statement = select(OptionChain).where(OptionChain.symbol == symbol)
        results = orm_session.exec(statement).all()

        # Convert to list of dictionaries
        data = []
        for result in results:
            data.append({
                "conid": result.conid,
                "symbol": result.symbol,
                "maturity_date": result.maturity_date,
                "strike": result.strike,
                "right": result.right
            })

        return data