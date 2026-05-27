"""Integration tests for admin API endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from fastapi import FastAPI

from app.infra.database import Base, get_session
from app.infra.models import DeviceModel, ConversationModel, MusicCatalogModel  # noqa
from app.core.config import settings
from app.api.routes_admin import router as admin_router
from app.services.admin_auth_service import authenticate_admin, seed_admin_user


@pytest.fixture
async def engine():
    eng = create_async_engine(settings.database_url, echo=False, pool_size=5)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture
def test_app(engine):
    app = FastAPI()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.include_router(admin_router)
    return app


@pytest.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def admin_token():
    seed_admin_user()
    return authenticate_admin(settings.admin_username, settings.admin_password)


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestAdminLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, client):
        response = await client.post("/api/admin/login", json={
            "username": settings.admin_username,
            "password": settings.admin_password,
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["username"] == settings.admin_username

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client):
        response = await client.post("/api/admin/login", json={
            "username": settings.admin_username,
            "password": "wrong_password",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_user(self, client):
        response = await client.post("/api/admin/login", json={
            "username": "unknown",
            "password": "any",
        })
        assert response.status_code == 401


class TestAdminDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_requires_auth(self, client):
        response = await client.get("/api/admin/dashboard")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_dashboard_with_auth(self, client, auth_headers):
        response = await client.get("/api/admin/dashboard", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "online_devices" in data
        assert "total_devices" in data
        assert "active_connections" in data
        assert "recent_conversations" in data


class TestAdminDevices:
    @pytest.mark.asyncio
    async def test_list_devices(self, client, auth_headers, session):
        # Create a device
        device = DeviceModel(device_id="AA:BB:CC:DD:EE:AA", status="ONLINE")
        session.add(device)
        await session.commit()

        response = await client.get("/api/admin/devices", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["devices"]) >= 1

    @pytest.mark.asyncio
    async def test_get_device_detail(self, client, auth_headers, session):
        device = DeviceModel(device_id="AA:BB:CC:DD:EE:BB", status="OFFLINE", brightness=75)
        session.add(device)
        await session.commit()

        response = await client.get("/api/admin/devices/AA:BB:CC:DD:EE:BB", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == "AA:BB:CC:DD:EE:BB"
        assert data["brightness"] == 75


class TestAdminConversations:
    @pytest.mark.asyncio
    async def test_list_conversations(self, client, auth_headers, session):
        # Create device + conversation
        device = DeviceModel(device_id="AA:BB:CC:DD:EE:CC")
        session.add(device)
        await session.commit()

        conv = ConversationModel(
            device_id="AA:BB:CC:DD:EE:CC",
            session_id="test-session",
            user_text="bật đèn",
            ai_response="Đã bật đèn.",
            intent="TURN_ON_LIGHT",
            latency_ms=100,
        )
        session.add(conv)
        await session.commit()

        response = await client.get("/api/admin/conversations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_search_conversations(self, client, auth_headers, session):
        device = DeviceModel(device_id="AA:BB:CC:DD:EE:DD")
        session.add(device)
        await session.commit()

        conv = ConversationModel(
            device_id="AA:BB:CC:DD:EE:DD",
            session_id="s1",
            user_text="phát nhạc mưa",
            ai_response="Đang phát nhạc.",
            intent="PLAY_MUSIC",
        )
        session.add(conv)
        await session.commit()

        response = await client.get(
            "/api/admin/conversations?search=nhạc mưa",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


class TestAdminMusic:
    @pytest.mark.asyncio
    async def test_list_music(self, client, auth_headers, session):
        track = MusicCatalogModel(
            id="test_01", title="Test Track", type="RAIN",
            source_url="http://example.com/test.mp3", duration_seconds=300,
        )
        session.add(track)
        await session.commit()

        response = await client.get("/api/admin/music", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["tracks"]) >= 1

    @pytest.mark.asyncio
    async def test_add_music_track(self, client, auth_headers):
        response = await client.post("/api/admin/music", headers=auth_headers, json={
            "id": "new_track_01",
            "title": "New Track",
            "type": "OCEAN",
            "source_url": "http://example.com/ocean.mp3",
            "duration_seconds": 600,
        })
        assert response.status_code == 200
        assert response.json()["id"] == "new_track_01"


class TestAdminInstructions:
    @pytest.mark.asyncio
    async def test_get_templates(self, client, auth_headers):
        response = await client.get("/api/admin/instructions/templates", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["templates"]) == 4
        names = [t["name"] for t in data["templates"]]
        assert "bedtime_companion" in names
        assert "general_assistant" in names

    @pytest.mark.asyncio
    async def test_update_instructions(self, client, auth_headers):
        response = await client.post("/api/admin/instructions", headers=auth_headers, json={
            "content": "Bạn là trợ lý thông minh.",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "updated"

        # Verify
        response = await client.get("/api/admin/instructions", headers=auth_headers)
        assert response.json()["content"] == "Bạn là trợ lý thông minh."

    @pytest.mark.asyncio
    async def test_instructions_history(self, client, auth_headers):
        # Update twice
        await client.post("/api/admin/instructions", headers=auth_headers, json={"content": "v1"})
        await client.post("/api/admin/instructions", headers=auth_headers, json={"content": "v2"})

        response = await client.get("/api/admin/instructions/history", headers=auth_headers)
        assert response.status_code == 200
        # History should have previous versions
        assert len(response.json()["history"]) >= 1
