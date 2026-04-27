import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.replace("sqlite:///", "", 1)
    Path(os.path.dirname(db_path) or ".").mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401 — register models on Base

    Base.metadata.create_all(bind=engine)
    _dev_alter_table_for_existing_sqlite()


# SQLite-only, dev-only column add. `create_all` won't touch existing tables,
# so adding columns to `campaigns` after Session 13 would otherwise require
# nuking the docker volume. Each ALTER is gated on PRAGMA so re-runs are no-ops.
# Drop this when we move to Postgres + Alembic in Session 16.
_DEV_ADD_COLUMNS = {
    "campaigns": [
        ("target_dmas", "TEXT"),
        ("start_date", "DATE"),
        ("end_date", "DATE"),
        ("protocol_fee_amount", "NUMERIC(18, 6)"),
        ("protocol_fee_tx_hash", "VARCHAR"),
    ],
}


def _dev_alter_table_for_existing_sqlite() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        for table, cols in _DEV_ADD_COLUMNS.items():
            existing = {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            for name, sql_type in cols:
                if name not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"
                    )
