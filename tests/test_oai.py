"""Tests for the admin HTTP routes implemented in this repository."""

from unittest.mock import MagicMock

from starlette.testclient import TestClient

import perplexity.server.admin as admin
from perplexity.server.app import app


def test_health_endpoint_returns_pool_summary(monkeypatch) -> None:
    pool = MagicMock()
    pool.get_status.return_value = {"total": 2, "available": 1}
    monkeypatch.setattr(admin, "get_pool", lambda: pool)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "perplexity-mcp",
        "pool": {"total": 2, "available": 1},
    }


def test_admin_page_serves_built_index(monkeypatch, tmp_path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    index_path = dist_dir / "index.html"
    index_path.write_text("<html><body>admin ok</body></html>", encoding="utf-8")
    monkeypatch.setattr(admin, "_ADMIN_DIST_DIR", dist_dir)
    monkeypatch.setattr(admin, "_ADMIN_INDEX_PATH", index_path)

    client = TestClient(app)
    response = client.get("/admin/")

    assert response.status_code == 200
    assert "admin ok" in response.text


def test_admin_page_returns_setup_instructions_when_build_missing(
    monkeypatch, tmp_path
) -> None:
    missing_dist = tmp_path / "dist"
    missing_index = missing_dist / "index.html"
    monkeypatch.setattr(admin, "_ADMIN_DIST_DIR", missing_dist)
    monkeypatch.setattr(admin, "_ADMIN_INDEX_PATH", missing_index)

    client = TestClient(app)
    response = client.get("/admin/")

    assert response.status_code == 503
    assert "Admin UI build missing" in response.text
    assert "npm run build" in response.text
