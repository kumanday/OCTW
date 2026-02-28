from __future__ import annotations

import pytest
from pydantic import ValidationError

from octw.models.secret import AuditAction, SecretMetadata, SecretType
from octw.models.tenant import (
    ContainerState,
    IsolationMode,
    ResourceLimits,
    Tenant,
    TenantCreate,
    TenantPlan,
    TenantStatus,
)


class TestTenantCreate:
    def test_valid_slug(self):
        tc = TenantCreate(slug="acme-corp", name="Acme Corp")
        assert tc.slug == "acme-corp"

    def test_invalid_slug_uppercase(self):
        with pytest.raises(ValidationError):
            TenantCreate(slug="ACME", name="Acme")

    def test_invalid_slug_too_short(self):
        with pytest.raises(ValidationError):
            TenantCreate(slug="a", name="A")

    def test_defaults(self):
        tc = TenantCreate(slug="test-tenant", name="Test")
        assert tc.plan == TenantPlan.STANDARD
        assert tc.isolation_mode == IsolationMode.STANDARD
        assert tc.trusted_proxy_auth is True


class TestResourceLimits:
    def test_defaults(self):
        rl = ResourceLimits()
        assert rl.mem_limit == "1536m"
        assert rl.pids_limit == 512

    def test_custom(self):
        rl = ResourceLimits(mem_limit="2g", pids_limit=1024)
        assert rl.mem_limit == "2g"
        assert rl.pids_limit == 1024


class TestTenant:
    def test_creation(self):
        t = Tenant(slug="demo", name="Demo")
        assert t.status == TenantStatus.PROVISIONING
        assert t.tenant_id is not None


class TestSecretMetadata:
    def test_creation(self):
        import uuid
        sm = SecretMetadata(
            name="OPENAI_API_KEY",
            tenant_id=uuid.uuid4(),
            type=SecretType.ENV,
            target_env_var="OPENAI_API_KEY",
        )
        assert sm.algorithm == "AES-256-GCM"


class TestEnums:
    def test_tenant_status_values(self):
        assert TenantStatus.PROVISIONING.value == "provisioning"
        assert TenantStatus.RUNNING.value == "running"

    def test_container_state_values(self):
        assert ContainerState.NOT_FOUND.value == "not_found"

    def test_audit_actions(self):
        assert AuditAction.TENANT_CREATE.value == "tenant.create"
        assert AuditAction.SECRET_ROTATE.value == "secret.rotate"
