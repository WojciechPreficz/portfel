import re
from collections.abc import Iterator
from pathlib import Path

import bcrypt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auth
from app import database, main


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    auth._login_attempts.clear()
    password_hash = bcrypt.hashpw(b"correct", bcrypt.gensalt(rounds=4)).decode("ascii")
    monkeypatch.setattr(auth, "PORTFEL_AUTH_DISABLED", False)
    monkeypatch.setattr(auth, "PORTFEL_PASSWORD_HASH", password_hash)
    monkeypatch.setattr(
        auth,
        "PORTFEL_SECRET_KEY",
        "test-secret-key-with-at-least-32-bytes",
    )
    monkeypatch.setattr(auth, "PORTFEL_COOKIE_SECURE", True)
    monkeypatch.setattr(auth, "PORTFEL_SESSION_HOURS", 12)
    yield password_hash
    auth._login_attempts.clear()


@pytest.fixture
def test_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    database_path = tmp_path / "auth-tests.sqlite3"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    test_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    monkeypatch.setattr(main, "DATABASE_PATH", database_path)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", test_session_local)
    monkeypatch.setattr(database, "SessionLocal", test_session_local)
    monkeypatch.setattr(main.scheduler, "add_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.scheduler, "start", lambda: None)
    monkeypatch.setattr(main.scheduler, "shutdown", lambda wait=False: None)
    yield database_path
    engine.dispose()


@pytest.fixture
def client(auth_settings: str, test_database: Path) -> Iterator[TestClient]:
    with TestClient(main.app, base_url="https://testserver") as test_client:
        yield test_client


def test_login_with_correct_password_sets_cookie_and_authenticates(
    client: TestClient,
) -> None:
    response = client.post("/api/auth/login", json={"password": "correct"})

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "secure" in cookie
    assert "max-age=43200" in cookie
    assert client.get("/api/auth/me").status_code == 200


def test_login_with_incorrect_password_returns_401(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_is_rate_limited_after_five_failed_attempts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_delay() -> None:
        pass

    monkeypatch.setattr(auth, "_delay_failed_login", no_delay)
    for _ in range(5):
        response = client.post("/api/auth/login", json={"password": "wrong"})
        assert response.status_code == 401

    blocked = client.post("/api/auth/login", json={"password": "wrong"})

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "900"


def test_all_api_endpoints_except_login_and_logout_require_authentication(
    client: TestClient,
) -> None:
    public_paths = {"/api/auth/login", "/api/auth/logout"}
    api_routes = [
        route
        for route in main.app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
    ]

    assert api_routes
    for route in api_routes:
        if route.path in public_paths:
            continue
        path = re.sub(r"\{[^{}]+\}", "1", route.path)
        for method in route.methods or set():
            response = client.request(method, path)
            assert response.status_code == 401, (
                f"{method} {path} returned {response.status_code}, expected 401"
            )


def test_logout_invalidates_the_current_session(client: TestClient) -> None:
    login_response = client.post("/api/auth/login", json={"password": "correct"})
    assert login_response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    ("missing_setting", "expected_message"),
    [
        ("PORTFEL_PASSWORD_HASH", "PORTFEL_PASSWORD_HASH"),
        ("PORTFEL_SECRET_KEY", "PORTFEL_SECRET_KEY"),
    ],
)
def test_application_startup_fails_when_auth_setting_is_missing(
    missing_setting: str,
    expected_message: str,
    auth_settings: str,
    test_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, missing_setting, None)

    with pytest.raises(RuntimeError, match=expected_message):
        with TestClient(main.app):
            pass


def test_application_can_start_without_auth_settings_when_auth_is_disabled(
    auth_settings: str,
    test_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "PORTFEL_PASSWORD_HASH", None)
    monkeypatch.setattr(auth, "PORTFEL_SECRET_KEY", None)
    monkeypatch.setattr(auth, "PORTFEL_AUTH_DISABLED", True)

    with TestClient(main.app):
        pass
