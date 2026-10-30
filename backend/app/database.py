from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record):  # pragma: no cover - dépend du pilote
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Applique les migrations Alembic, avec repli create_all pour un poste sans Alembic."""
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(settings.project_root / "backend" / "alembic.ini"))
        cfg.set_main_option("script_location", str(settings.project_root / "backend" / "migrations"))
        cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
        command.upgrade(cfg, "head")
    except Exception:
        from . import models  # noqa: F401  (enregistre les tables)

        Base.metadata.create_all(bind=engine)
