"""Phase 3 acceptance tests — client/vehicle/device CRUD via API."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.security.password import hash_password


@pytest_asyncio.fixture
async def http_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register_and_login(http_client: AsyncClient, slug_suffix: str) -> tuple[str, str]:
    """Register a fresh tenant and return (access_token, client_id_str)."""
    slug = f"crud-test-{slug_suffix}"
    email = f"owner-{slug_suffix}@example.com"
    password = "CrudPass456!"
    reg = await http_client.post(
        "/clients",
        json={
            "name": f"CRUD Co {slug_suffix}",
            "slug": slug,
            "owner_email": email,
            "owner_password": password,
        },
    )
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["id"]

    login = await http_client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"], client_id


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_register_client(http_client):
    suffix = uuid.uuid4().hex[:8]
    resp = await http_client.post(
        "/clients",
        json={
            "name": "New Tenant",
            "slug": f"new-tenant-{suffix}",
            "owner_email": f"owner-{suffix}@example.com",
            "owner_password": "Password123!",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == f"new-tenant-{suffix}"
    assert "id" in data


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_register_duplicate_slug(http_client):
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": "Dup Tenant",
        "slug": f"dup-slug-{suffix}",
        "owner_email": f"dup-{suffix}@example.com",
        "owner_password": "Password123!",
    }
    r1 = await http_client.post("/clients", json=payload)
    assert r1.status_code == 201
    payload["owner_email"] = f"dup2-{suffix}@example.com"
    r2 = await http_client.post("/clients", json=payload)
    assert r2.status_code == 409


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_vehicle_crud(http_client):
    token, _ = await _register_and_login(http_client, uuid.uuid4().hex[:8])
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    create = await http_client.post(
        "/vehicles",
        headers=headers,
        json={"vin": "1HGBH41JXMN109186", "make": "Honda", "model_name": "Civic", "year": 2021},
    )
    assert create.status_code == 201
    vehicle_id = create.json()["id"]

    # Read
    get = await http_client.get(f"/vehicles/{vehicle_id}", headers=headers)
    assert get.status_code == 200
    assert get.json()["vin"] == "1HGBH41JXMN109186"

    # List
    lst = await http_client.get("/vehicles", headers=headers)
    assert lst.status_code == 200
    assert any(v["id"] == vehicle_id for v in lst.json())

    # Update
    patch = await http_client.patch(
        f"/vehicles/{vehicle_id}", headers=headers, json={"year": 2022}
    )
    assert patch.status_code == 200
    assert patch.json()["year"] == 2022

    # Soft-delete
    delete = await http_client.delete(f"/vehicles/{vehicle_id}", headers=headers)
    assert delete.status_code == 204


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_device_crud_and_provision(http_client):
    token, _ = await _register_and_login(http_client, uuid.uuid4().hex[:8])
    headers = {"Authorization": f"Bearer {token}"}

    # Create a vehicle first (device needs a vehicle)
    v = await http_client.post(
        "/vehicles",
        headers=headers,
        json={"vin": "JM1GJ1W56G1431274", "make": "Mazda", "model_name": "3", "year": 2016},
    )
    assert v.status_code == 201
    vid = v.json()["id"]

    # Create device
    dev = await http_client.post(
        "/devices", headers=headers, json={"vehicle_id": vid, "serial": f"ESP32-{uuid.uuid4().hex[:8].upper()}"}
    )
    assert dev.status_code == 201
    device_id = dev.json()["id"]

    # List
    lst = await http_client.get("/devices", headers=headers)
    assert any(d["id"] == device_id for d in lst.json())

    # Provision — returns a JWT token for the device
    prov = await http_client.post(f"/devices/{device_id}/provision", headers=headers)
    assert prov.status_code == 200
    pdata = prov.json()
    assert "provisioning_token" in pdata
    assert pdata["device_id"] == device_id

    # Register cert fingerprint
    cert = await http_client.post(
        f"/devices/{device_id}/cert",
        headers=headers,
        json={"cert_fingerprint": "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"},
    )
    assert cert.status_code == 200
    assert cert.json()["cert_fingerprint"] == "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_unauthenticated_cannot_list_vehicles(http_client):
    resp = await http_client.get("/vehicles")
    assert resp.status_code == 401


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_invalid_token_rejected(http_client):
    resp = await http_client.get(
        "/vehicles", headers={"Authorization": "Bearer this.is.garbage"}
    )
    assert resp.status_code == 401
