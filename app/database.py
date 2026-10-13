"""SQLAlchemy database connection and session management."""

import logging
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


# Ensure sqlite parent directory exists
if settings.DATABASE_URL.startswith("sqlite"):
    db_file_path = settings.DATABASE_URL.replace("sqlite:///", "")
    Path(db_file_path).parent.mkdir(parents=True, exist_ok=True)

connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

pool_kwargs = {}
if "sqlite:///:memory:" not in settings.DATABASE_URL:
    pool_kwargs = {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_pre_ping": True,
    }

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    **pool_kwargs,
)

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)

Base = declarative_base()


@event.listens_for(engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    """Fired when a physical database connection is established."""
    if settings.DATABASE_URL.startswith("sqlite"):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()
        except Exception as e:
            logger.warning("Failed to configure SQLite PRAGMAs: %s", e)
    logger.debug(
        "Successfully connected to database and initialized connection pool entry."
    )


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Fired when a pooled connection is checked out for a request or task."""
    logger.debug("Database connection checked out from pool.")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Fired when a connection is returned to the pool for reuse."""
    logger.debug("Database connection returned to pool.")


@event.listens_for(engine, "invalidate")
def receive_invalidate(dbapi_connection, connection_record, exception):
    """Fired when a connection encounters a fatal error and is discarded."""
    logger.error("Database connection invalidated due to error: %s", exception)


@event.listens_for(engine, "close")
def receive_close(dbapi_connection, connection_record):
    """Fired when a connection is closed during pool cleanup, recycle, or shutdown."""
    logger.debug("Database connection closed by pool.")


def get_db():
    """Dependency to yield a database session."""
    with SessionLocal() as db:
        yield db


def get_task_db_session():
    """Retrieve database session for background/Celery tasks, respecting FastAPI dependency overrides."""
    try:
        import sys

        main_mod = sys.modules.get("app.main")
        if main_mod and hasattr(main_mod, "app"):
            fastapi_app = main_mod.app
            if (
                hasattr(fastapi_app, "dependency_overrides")
                and get_db in fastapi_app.dependency_overrides
            ):
                gen = fastapi_app.dependency_overrides[get_db]()
                return next(gen)
    except Exception:
        pass
    return SessionLocal()
