"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from orkp.config import DatabaseConfig


def create_engine_from_config(db_config: DatabaseConfig):
    """Create a SQLAlchemy engine from database configuration."""
    return create_engine(
        db_config.connection_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )


def create_session_factory(engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine."""
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session(session_factory: sessionmaker[Session]) -> Session:
    """Get a new database session."""
    return session_factory()
