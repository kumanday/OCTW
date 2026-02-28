from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TenantStatus(enum.StrEnum):
    PROVISIONING = "provisioning"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    DELETING = "deleting"


class ContainerState(enum.StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    NOT_FOUND = "not_found"


class IsolationMode(enum.StrEnum):
    STANDARD = "standard"
    HARDENED = "hardened"


class TenantPlan(enum.StrEnum):
    STANDARD = "standard"
    PREMIUM = "premium"


class ResourceLimits(BaseModel):
    mem_limit: str = "1536m"
    cpu_quota: int = 100000
    cpu_period: int = 100000
    pids_limit: int = 512


class TenantCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$")
    name: str = Field(min_length=1, max_length=200)
    plan: TenantPlan = TenantPlan.STANDARD
    isolation_mode: IsolationMode = IsolationMode.STANDARD
    resource_limits: ResourceLimits | None = None
    trusted_proxy_auth: bool = True


class Tenant(BaseModel):
    tenant_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    slug: str
    name: str
    plan: TenantPlan = TenantPlan.STANDARD
    status: TenantStatus = TenantStatus.PROVISIONING
    isolation_mode: IsolationMode = IsolationMode.STANDARD
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    trusted_proxy_auth: bool = True
    container_id: str | None = None
    network_id: str | None = None
    openclaw_image: str | None = None
    openclaw_digest: str | None = None
    last_activity_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TenantRuntimeInfo(BaseModel):
    tenant_id: uuid.UUID
    state: ContainerState
    container_id: str | None = None
    last_activity_at: datetime | None = None
    limits: ResourceLimits = Field(default_factory=ResourceLimits)


class Role(enum.StrEnum):
    TENANT_ADMIN = "tenant_admin"
    TENANT_USER = "tenant_user"
    TENANT_VIEWER = "tenant_viewer"


class MemberCreate(BaseModel):
    email: str
    role: Role = Role.TENANT_USER


class Member(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: Role
    created_at: datetime = Field(default_factory=datetime.utcnow)
