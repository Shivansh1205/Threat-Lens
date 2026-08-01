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

from app.ai import chatbot as chatbot_module
from app.database import Base, get_db
from app.detection.registry import reset_registry
from app.main import app as fastapi_app
from app.realtime.websocket_manager import reset_ws_manager


@pytest.fixture
def anyio_backend() -> str:
    """Restrict anyio's pytest plugin to the asyncio backend.

    anyio (a transitive dependency of fastapi/httpx/starlette — already
    installed, no new package added) ships a pytest plugin that lets
    ``async def`` tests be marked ``@pytest.mark.anyio`` and run directly,
    without adding pytest-asyncio. Left at its default, it parametrizes
    every such test across both "asyncio" and "trio" backends; trio isn't
    installed in this project, so without this override every async test
    would fail on the trio parametrization. Restricting to "asyncio" here
    matches what the app itself actually runs on.
    """
    return "asyncio"


@pytest.fixture(autouse=True)
def _fresh_detector_state() -> Generator[None, None, None]:
    """Wipe the detector-registry singleton around every test.

    Detectors carry in-memory state (sliding windows, known-IP sets). Without
    this, state leaks between tests and everything breaks in confusing ways.
    """
    reset_registry()
    yield
    reset_registry()


@pytest.fixture(autouse=True)
def _fresh_chatbot_history() -> Generator[None, None, None]:
    """Wipe the chatbot's module-level conversation history between tests —
    same rationale as ``_fresh_detector_state`` above.
    """
    chatbot_module._conversation_history.clear()
    yield
    chatbot_module._conversation_history.clear()


@pytest.fixture(autouse=True)
def _fresh_ws_manager() -> Generator[None, None, None]:
    """Drop the WebSocketManager singleton around every test — same
    rationale as ``_fresh_detector_state``: connected clients and the
    captured event loop are process-lifetime state and must not leak
    between tests.
    """
    reset_ws_manager()
    yield
    reset_ws_manager()


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
def client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    """A TestClient whose ``get_db`` yields the per-test session.

    Entered as a context manager (``with TestClient(...) as c``) rather than
    just constructed — this is what makes FastAPI's ``lifespan`` handler
    actually run for tests. That matters as of Phase 7a: the lifespan
    handler in main.py is what captures the app's event loop into
    ``WebSocketManager`` (see ``set_loop``/``schedule_broadcast``), and it's
    also required by Starlette for ``TestClient.websocket_connect(...)`` to
    work at all. Before this phase, nothing depended on lifespan running, so
    the plain (non-context-manager) form was fine.

    As of the time-based risk-decay feature, lifespan ALSO runs a decay pass
    once on startup (and would, given enough wall-clock time, via its
    scheduled interval job too) — see main.py's ``_run_decay_job``. That
    function opens its own DB session via the module-level
    ``app.main._decay_db_session_factory`` rather than the request-scoped
    ``get_db`` dependency (it isn't tied to any request), so overriding
    ``get_db`` alone does NOT redirect it. Without the monkeypatch below,
    every test using this fixture would open a real connection to whatever
    ``DATABASE_URL`` is configured (Postgres) purely as a side effect of
    lifespan startup — exactly what this feature's test constraints rule
    out.

    The replacement factory is a NEW sessionmaker bound to the same
    StaticPool engine ``db_session`` uses (StaticPool means every session
    from that engine shares the one underlying in-memory SQLite connection,
    so this sees the same data) rather than a lambda returning ``db_session``
    itself — ``_run_decay_job`` closes whatever session it's given when it's
    done, and closing the actual ``db_session`` object out from under the
    test, before the test body even runs, is exactly the kind of
    action-at-a-distance bug worth avoiding here. A dedicated sessionmaker
    keeps each call independent, matching how ``SessionLocal()`` behaves in
    production.
    """
    test_engine = db_session.get_bind()
    TestDecaySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr("app.main._decay_db_session_factory", TestDecaySessionLocal)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(fastapi_app) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.clear()
