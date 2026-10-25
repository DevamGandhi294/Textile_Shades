"""Database connection: one engine for the app, one session per request."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import config

engine = create_engine(config.DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    """FastAPI dependency: `db: Session = Depends(get_db)`. Call db.commit() to save."""
    with SessionLocal() as db:
        yield db


@contextmanager
def session_scope():
    """For scripts and background jobs: commits at the end, rolls back on error."""
    with SessionLocal() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


__all__ = ["engine", "SessionLocal", "Session", "get_db", "session_scope"]
