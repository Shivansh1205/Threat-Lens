"""Shared pytest fixtures.

Each test gets a fresh in-memory SQLite database. We override the app's
``get_db`` dependency so requests hit the test DB, and create all tables from
``Base.metadata`` before yielding a ``TestClient``.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Importing the models package ensures every table is registered on the
# metadata before create_all runs. Do this first; the bare ``import app.models``
# would otherwise rebind the name ``app`` and shadow the FastAPI instance.
import app.models  # noqa: F401

from app.database import Base, get_db
from app.detection.registry import reset_registry
from app.main import app as fastapi_app


@pytest.fixture(autouse=True)
def _fresh_detector_state() -> Generator[None, None, None]:
    """Wipe the detector-registry singleton around every test.

    Detectors carry in-memory state (sliding windows, known-IP sets). Without
    this, state leaks between tests and everything breaks in confusing ways.
    """
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """A fresh in-memory SQLite DB, torn down after each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """A TestClient whose ``get_db`` yields the per-test session."""

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()
