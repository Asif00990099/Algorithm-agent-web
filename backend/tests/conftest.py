import os
import pathlib

TEST_DB = pathlib.Path(__file__).parent / "test_quantpulse.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-0123456789")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.init_db import init_db
from app.db.session import engine
from app.main import app


@pytest_asyncio.fixture()
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_db(create_all=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    TEST_DB.unlink(missing_ok=True)


@pytest_asyncio.fixture()
async def auth_headers(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "trader@test.com", "username": "trader1",
        "password": "SuperSecure123"})
    resp = await client.post("/api/v1/auth/login", json={
        "email": "trader@test.com", "password": "SuperSecure123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
