from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SecretType(enum.StrEnum):
    ENV = "env"
    SECRETREF = "secretref"


class SecretCreate(BaseModel):
    value: str
    type: SecretType = SecretType.ENV
    target_env_var: str | None = None


class SecretMetadata(BaseModel):
    name: str
    tenant_id: uuid.UUID
    type: SecretType
    target_env_var: str | None = None
    algorithm: str = "AES-256-GCM"
    key_version: int = 1
    last_rotated_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AuditAction(enum.StrEnum):
    TENANT_CREATE = "tenant.create"
    TENANT_DELETE = "tenant.delete"
    SECRET_SET = "secret.set"
    SECRET_ROTATE = "secret.rotate"
    SECRET_DELETE = "secret.delete"
    CONTAINER_START = "container.start"
    CONTAINER_STOP = "container.stop"
    CONTAINER_PAUSE = "container.pause"
    CONTAINER_WAKE = "container.wake"
    MEMBER_ADD = "member.add"
    MEMBER_REMOVE = "member.remove"
    ROUTE_CHANGE = "route.change"
    BACKUP_CREATE = "backup.create"
    BACKUP_RESTORE = "backup.restore"


class AuditEvent(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    action: AuditAction
    detail: dict | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
