"""Phase 3 acceptance tests — cross-tenant data isolation (critical).

Proves that tenant A's vehicles/devices are invisible to tenant B's JWT,
even when B knows the exact UUID of A's resource.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def http_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register_and_login(http_client: AsyncClient, suffix: str) -> tuple[str, str]:
    email = f"iso-owner-{suffix}@example.com"
    resp = await http_client.post(
        "/clients",
        json={
            "name": f"Isolation Co {suffix}",
            "slug": f"iso-{suffix}",
            "owner_email": email,
            "owner_password": "IsoPass789!",
        },
    )
    assert resp.status_code == 201, resp.text
    client_id = resp.json()["id"]
    login = await http_client.post(
        "/auth/login", json={"email": email, "password": "IsoPass789!"}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"], client_id


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_tenant_cannot_read_other_tenant_vehicle(http_client):
    suffix_a = uuid.uuid4().hex[:8]
    suffix_b = uuid.uuid4().hex[:8]

    token_a, _ = await _register_and_login(http_client, suffix_a)
    token_b, _ = await _register_and_login(http_client, suffix_b)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant A creates a vehicle
    v = await http_client.post(
        "/vehicles",
        headers=headers_a,
        json={"vin": "WAUZZZ4G0DN123456", "make": "Audi", "model_name": "A4", "year": 2013},
    )
    assert v.status_code == 201
    vehicle_id = v.json()["id"]

    # Tenant B tries to read A's vehicle by its exact UUID → 404 (RLS hides it)
    get_b = await http_client.get(f"/vehicles/{vehicle_id}", headers=headers_b)
    assert get_b.status_code == 404, (
        f"Expected 404 but got {get_b.status_code}: RLS is not isolating tenants!"
    )

    # Tenant B's list should be empty (owns no vehicles)
    lst_b = await http_client.get("/vehicles", headers=headers_b)
    assert lst_b.status_code == 200
    assert vehicle_id not in [v["id"] for v in lst_b.json()]

    # Tenant A can still read its own vehicle
    get_a = await http_client.get(f"/vehicles/{vehicle_id}", headers=headers_a)
    assert get_a.status_code == 200


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_tenant_cannot_update_other_tenant_vehicle(http_client):
    suffix_a = uuid.uuid4().hex[:8]
    suffix_b = uuid.uuid4().hex[:8]

    token_a, _ = await _register_and_login(http_client, suffix_a)
    token_b, _ = await _register_and_login(http_client, suffix_b)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    v = await http_client.post(
        "/vehicles",
        headers=headers_a,
        json={"vin": "1G1BE5SM0G7210823", "make": "Chevrolet", "model_name": "Cruze", "year": 2016},
    )
    assert v.status_code == 201
    vehicle_id = v.json()["id"]

    # B tries to PATCH A's vehicle
    patch = await http_client.patch(
        f"/vehicles/{vehicle_id}", headers=headers_b, json={"year": 2099}
    )
    assert patch.status_code == 404, "RLS must prevent cross-tenant writes"


@pytest.mark.skipif(
    __import__("os").environ.get("DATABASE_URL") is None,
    reason="DATABASE_URL not set",
)
async def test_tenant_cannot_read_other_tenant_device(http_client):
    suffix_a = uuid.uuid4().hex[:8]
    suffix_b = uuid.uuid4().hex[:8]

    token_a, _ = await _register_and_login(http_client, suffix_a)
    token_b, _ = await _register_and_login(http_client, suffix_b)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # A creates vehicle + device
    v = await http_client.post(
        "/vehicles",
        headers=headers_a,
        json={"vin": "3VWF17AT0FM123789", "make": "VW", "model_name": "Jetta", "year": 2015},
    )
    assert v.status_code == 201
    vid = v.json()["id"]

    d = await http_client.post(
        "/devices", headers=headers_a, json={"vehicle_id": vid, "serial": f"ESP32-ISO-{uuid.uuid4().hex[:8].upper()}"}
    )
    assert d.status_code == 201
    device_id = d.json()["id"]

    # B cannot read A's device
    get_b = await http_client.get(f"/devices/{device_id}", headers=headers_b)
    assert get_b.status_code == 404, "RLS must isolate devices across tenants"

    # B cannot provision A's device
    prov_b = await http_client.post(f"/devices/{device_id}/provision", headers=headers_b)
    assert prov_b.status_code == 404, "RLS must prevent cross-tenant device provisioning"
