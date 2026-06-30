"""Phase 3 acceptance tests — authentication and JWT lifecycle."""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

_SKIP = pytest.mark.skipif(
    os.environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)


@pytest_asyncio.fixture
async def http_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def registered_user(http_client):
    """Register a fresh tenant+owner via the API. Returns (email, password)."""
    suffix = uuid.uuid4().hex[:8]
    email = f"auth-owner-{suffix}@example.com"
    password = "SecurePass123!"
    resp = await http_client.post(
        "/clients",
        json={
            "name": f"Auth Test Co {suffix}",
            "slug": f"auth-test-{suffix}",
            "owner_email": email,
            "owner_password": password,
        },
    )
    assert resp.status_code == 201, resp.text
    return email, password


@_SKIP
async def test_login_success(http_client, registered_user):
    email, password = registered_user
    resp = await http_client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@_SKIP
async def test_login_wrong_password(http_client, registered_user):
    email, _ = registered_user
    resp = await http_client.post("/auth/login", json={"email": email, "password": "wrongpass"})
    assert resp.status_code == 401


@_SKIP
async def test_login_unknown_email(http_client):
    resp = await http_client.post(
        "/auth/login", json={"email": "nobody@nowhere.com", "password": "whatever"}
    )
    assert resp.status_code == 401


@_SKIP
async def test_refresh_returns_new_access_token(http_client, registered_user):
    email, password = registered_user
    login = await http_client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    resp = await http_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # single-field response


@_SKIP
async def test_refresh_invalid_token(http_client):
    resp = await http_client.post("/auth/refresh", json={"refresh_token": "not.a.valid.token"})
    assert resp.status_code == 401


@_SKIP
async def test_health_endpoint(http_client):
    resp = await http_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
