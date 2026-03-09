from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from octw.api import auth
from octw.api.app_logic import build_user_tenant_name, build_user_tenant_slug
from octw.api.auth import TokenPayload
from octw.api.routers import app_router
from octw.api.routers.app_router import router as app_api_router
from octw.common.config import settings
from octw.models.tenant import Tenant, TenantStatus, VerificationStatus
from octw.orchestrator.docker_orch import DockerOrchestrator


@pytest.mark.asyncio
async def test_get_browser_user_bootstraps_from_trusted_proxy(monkeypatch):
    user_id = uuid.uuid4()

    async def fake_get_or_create_user(session, email: str):
        return SimpleNamespace(user_id=user_id, email=email)

    monkeypatch.setattr(settings, "trusted_proxy_enabled", True)
    monkeypatch.setattr(settings, "trusted_proxy_user_header", "X-Forwarded-Email")
    monkeypatch.setattr(settings, "trusted_proxy_ips", ["127.0.0.1/32"])
    monkeypatch.setattr(auth, "get_or_create_user", fake_get_or_create_user)

    request = Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-email", b"person@example.com")],
            "client": ("127.0.0.1", 1234),
        }
    )

    payload, issued = await auth.get_browser_user(request, session=object())
    assert issued is True
    assert payload.user_id == user_id
    assert payload.email == "person@example.com"


@pytest.mark.asyncio
async def test_get_browser_user_rehydrates_when_cookie_user_missing(monkeypatch):
    stale_user_id = uuid.uuid4()
    fresh_user_id = uuid.uuid4()
    stale_token = auth.create_access_token(stale_user_id, "person@example.com")

    async def fake_get_or_create_user(session, email: str):
        return SimpleNamespace(user_id=fresh_user_id, email=email)

    class FakeSession:
        async def get(self, model, user_id):
            assert user_id == stale_user_id
            return None

    monkeypatch.setattr(settings, "trusted_proxy_enabled", True)
    monkeypatch.setattr(settings, "trusted_proxy_user_header", "X-Forwarded-Email")
    monkeypatch.setattr(settings, "trusted_proxy_ips", ["127.0.0.1/32"])
    monkeypatch.setattr(auth, "get_or_create_user", fake_get_or_create_user)

    request = Request(
        {
            "type": "http",
            "headers": [
                (b"x-forwarded-email", b"person@example.com"),
                (b"cookie", f"octw_session={stale_token}".encode()),
            ],
            "client": ("127.0.0.1", 1234),
        }
    )

    payload, issued = await auth.get_browser_user(request, session=FakeSession())
    assert issued is True
    assert payload.user_id == fresh_user_id
    assert payload.email == "person@example.com"


def test_build_user_tenant_slug_is_deterministic():
    user_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
    assert build_user_tenant_slug(user_id) == "u-11111111222233334444"
    assert build_user_tenant_name("alice.smith@example.com") == "Alice Smith Workspace"


def test_app_session_sets_cookie(monkeypatch):
    app = FastAPI()
    app.include_router(app_api_router)

    class FakeTenantService:
        async def get_owner_tenant(self, session, user_id):
            return None

    class FakeSession:
        async def commit(self):
            return None

    async def fake_session_dep():
        yield FakeSession()

    async def fake_browser_user(request, session):
        return TokenPayload(uuid.uuid4(), "oidc@example.com"), True

    monkeypatch.setattr(app_router, "get_browser_user", fake_browser_user)
    monkeypatch.setattr(app_router, "create_access_token", lambda user_id, email: "session-token")
    app.dependency_overrides[app_router.get_session] = fake_session_dep
    app.dependency_overrides[app_router.get_tenant_service] = lambda: FakeTenantService()

    client = TestClient(app)
    response = client.get("/api/v1/app/session")

    assert response.status_code == 200
    assert response.json()["email"] == "oidc@example.com"
    assert response.cookies.get("octw_session") == "session-token"


def test_configure_tenant_sets_trusted_proxy(monkeypatch, tmp_path):
    tenant_id = uuid.uuid4()
    state_dir = tmp_path / str(tenant_id) / "state"
    state_dir.mkdir(parents=True)
    config_path = state_dir / "openclaw.json"
    config_path.write_text(
        '{"gateway": {"controlUi": {"dangerouslyAllowHostHeaderOriginFallback": true}}}'
    )

    monkeypatch.setattr(settings, "tenant_base_dir", str(tmp_path))
    monkeypatch.setattr(settings, "public_base_url", "https://chat.example.com")

    orch = DockerOrchestrator.__new__(DockerOrchestrator)
    orch.connect_edge_to_network = lambda tenant_id: "172.18.0.9"

    orch.configure_tenant(tenant_id, provider_spec=None)

    data = config_path.read_text()
    assert '"mode": "trusted-proxy"' in data
    assert '"trustedProxies": [' in data
    assert '"172.18.0.9"' in data
    assert '"allowedOrigins": [' in data
    assert 'dangerouslyAllowHostHeaderOriginFallback' not in data


def test_deploy_or_resume_reuses_existing_tenant(monkeypatch):
    app = FastAPI()
    app.include_router(app_api_router)

    tenant = Tenant(
        tenant_id=uuid.uuid4(),
        slug="u-tenant",
        name="Workspace",
        owner_user_id=uuid.uuid4(),
        status=TenantStatus.STOPPED,
        verification_status=VerificationStatus.VERIFIED,
    )

    class FakeTenantService:
        def __init__(self):
            self.wake_calls = 0

        async def get_owner_tenant(self, session, user_id):
            return tenant

        async def wake_tenant(self, session, tenant_id):
            self.wake_calls += 1
            return "container-id"

        async def verify_tenant(self, session, tenant_id):
            raise AssertionError("verified tenant should not be re-verified")

        async def get_tenant(self, session, tenant_id):
            return tenant.model_copy(update={"status": TenantStatus.RUNNING})

    fake_service = FakeTenantService()

    class FakeSession:
        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def fake_session_dep():
        yield FakeSession()

    async def fake_browser_user(request, session):
        return TokenPayload(tenant.owner_user_id, "oidc@example.com"), False

    monkeypatch.setattr(app_router, "get_browser_user", fake_browser_user)
    app.dependency_overrides[app_router.get_session] = fake_session_dep
    app.dependency_overrides[app_router.get_tenant_service] = lambda: fake_service
    app.dependency_overrides[app_router.get_orchestrator] = lambda: object()
    app.dependency_overrides[app_router.get_vault_service] = lambda: object()

    client = TestClient(app)
    response = client.post("/api/v1/app/deploy-or-resume")

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert fake_service.wake_calls == 1
