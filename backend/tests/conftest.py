from collections.abc import Callable, Generator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.main import app


class HealthySession:
    """Minimal session double for a reachable database."""

    def execute(self, statement: object) -> object:
        return 1


class UnavailableSession:
    """Minimal session double for an unreachable database."""

    def execute(self, statement: object) -> object:
        raise SQLAlchemyError("simulated database outage")


def _override_with(session: object) -> Callable[[], Generator[object, None, None]]:
    def dependency() -> Generator[object, None, None]:
        yield session

    return dependency


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def healthy_client() -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = _override_with(HealthySession())
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def unavailable_client() -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = _override_with(UnavailableSession())
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
