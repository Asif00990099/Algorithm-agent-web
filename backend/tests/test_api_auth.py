"""API integration tests: auth flow, RBAC, watchlist, health."""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_register_login_me(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "alice@test.com", "username": "alice",
        "password": "StrongPass123"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "alice@test.com"
    assert body["role"] == "trader"
    assert body["demo_balance"] == 100_000.0

    resp = await client.post("/api/v1/auth/login", json={
        "email": "alice@test.com", "password": "StrongPass123"})
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    resp = await client.get("/api/v1/users/me",
                            headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"

    # refresh flow
    resp = await client.post("/api/v1/auth/refresh",
                             json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_weak_password_rejected(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "bob@test.com", "username": "bob123", "password": "onlyletters"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_email_rejected(client):
    payload = {"email": "carol@test.com", "username": "carol", "password": "StrongPass123"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    resp = await client.post("/api/v1/auth/register",
                             json={**payload, "username": "carol2"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_bad_login(client):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "ghost@test.com", "password": "whatever123"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_token(client):
    assert (await client.get("/api/v1/users/me")).status_code == 401
    assert (await client.get("/api/v1/users/me",
                             headers={"Authorization": "Bearer bogus"})).status_code == 401


@pytest.mark.asyncio
async def test_admin_route_forbidden_for_trader(client, auth_headers):
    resp = await client.get("/api/v1/admin/stats", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_watchlist_crud(client, auth_headers):
    resp = await client.post("/api/v1/users/me/watchlist",
                             json={"symbol": "btcusdt", "asset_type": "crypto"},
                             headers=auth_headers)
    assert resp.status_code == 201
    item_id = resp.json()["id"]

    resp = await client.get("/api/v1/users/me/watchlist", headers=auth_headers)
    symbols = [i["symbol"] for i in resp.json()]
    assert "BTCUSDT" in symbols

    resp = await client.delete(f"/api/v1/users/me/watchlist/{item_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_alerts_validation(client, auth_headers):
    resp = await client.post("/api/v1/users/me/alerts",
                             json={"symbol": "BTCUSDT", "condition": "sideways",
                                   "target_price": 50000},
                             headers=auth_headers)
    assert resp.status_code == 422  # invalid condition rejected


@pytest.mark.asyncio
async def test_strategies_seeded(client, auth_headers):
    resp = await client.get("/api/v1/strategies", headers=auth_headers)
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert "Trend Rider" in names
