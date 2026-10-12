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

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, echo=False)

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)

Base = declarative_base()


@event.listens_for(engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    """Fired when a physical database connection is established."""
    logger.info("Successfully connected to the master database server.")


@event.listens_for(engine, "invalidate")
def receive_invalidate(dbapi_connection, connection_record, exception):
    """Fired when a connection encounters a fatal error and is discarded."""
    logger.error(f"Master connection invalidated due to error: {exception}")


@event.listens_for(engine, "close")
def receive_close(dbapi_connection, connection_record):
    """Fired when a connection is closed."""
    logger.error("Master connection closed")


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
