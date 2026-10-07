from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


def test_frontend_assets_and_client_routes_are_served(tmp_path: Path) -> None:
    frontend_dir = tmp_path / "frontend_dist"
    assets_dir = frontend_dir / "assets"
    assets_dir.mkdir(parents=True)
    (frontend_dir / "index.html").write_text("<main>Portfel</main>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('ok')", encoding="utf-8")

    app = FastAPI()
    mount_frontend(app, frontend_dir)

    with TestClient(app) as client:
        assert client.get("/").text == "<main>Portfel</main>"
        assert client.get("/assets/app.js").text == "console.log('ok')"
        assert client.get("/portfolios/1").text == "<main>Portfel</main>"


@pytest.mark.parametrize("path", ["/api/unknown", "/api/auth/unknown"])
def test_frontend_does_not_intercept_api_routes(tmp_path: Path, path: str) -> None:
    frontend_dir = tmp_path / "frontend_dist"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text("<main>Portfel</main>", encoding="utf-8")

    app = FastAPI()
    mount_frontend(app, frontend_dir)

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


def test_frontend_rejects_path_traversal(tmp_path: Path) -> None:
    frontend_dir = tmp_path / "frontend_dist"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text("<main>Portfel</main>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")

    app = FastAPI()
    mount_frontend(app, frontend_dir)

    with TestClient(app) as client:
        response = client.get("/%2e%2e%2fsecret.txt")

    assert response.status_code == 404
