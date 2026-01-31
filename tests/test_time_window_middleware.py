"""Tests for TimeWindowMiddleware exemptions."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from api.middleware import TimeWindowMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TimeWindowMiddleware)

    @app.get("/admin/gateway/verify")
    def verify_gateway():
        return {"ok": True}

    @app.get("/api/admin/gateway/verify")
    def verify_gateway_prefixed():
        return {"ok": True}

    @app.get("/not-exempt")
    def not_exempt():
        return {"ok": True}

    return app


def test_time_window_allows_gateway_verify(monkeypatch) -> None:
    monkeypatch.setattr(TimeWindowMiddleware, "is_in_run_window", lambda self: False)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    assert client.get("/admin/gateway/verify").status_code == 200
    assert client.get("/api/admin/gateway/verify").status_code == 200


def test_time_window_blocks_non_exempt(monkeypatch) -> None:
    monkeypatch.setattr(TimeWindowMiddleware, "is_in_run_window", lambda self: False)
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/not-exempt")
    assert response.status_code != 200
    if response.headers.get("content-type", "").startswith("application/json"):
        detail = response.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("error") == "OUTSIDE_RUN_WINDOW"
