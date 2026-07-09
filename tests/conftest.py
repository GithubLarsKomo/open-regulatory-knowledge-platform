"""Test fixtures and configuration for ORKP database tests."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from orkp.db.models import Base


# SQLite doesn't support MySQLBinary, so we use a type adapter
@pytest.fixture(scope="session")
def engine():
    """Create a SQLite in-memory engine for testing."""
    e = create_engine("sqlite:///:memory:", echo=False)

    # Register a listener to adapt MySQLBinary to SQLite BLOB
    @event.listens_for(e, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(e)
    return e


@pytest.fixture
def session(engine):
    """Create a fresh database session for each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def repo(session):
    """Create a RegulatoryObjectRepository for testing."""
    from orkp.db.repository import RegulatoryObjectRepository
    return RegulatoryObjectRepository(session)