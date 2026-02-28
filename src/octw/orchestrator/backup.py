from __future__ import annotations

import subprocess
import tarfile
import uuid
from datetime import datetime
from pathlib import Path

from octw.common.config import settings
from octw.common.logging import get_logger

log = get_logger(__name__)

BACKUP_DIR = Path("/var/lib/octw/backups")


class BackupService:
    def __init__(self) -> None:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    def backup_tenant(self, tenant_id: uuid.UUID) -> str:
        tenant_dir = Path(settings.tenant_base_dir) / str(tenant_id)
        if not tenant_dir.exists():
            raise FileNotFoundError(f"Tenant directory not found: {tenant_dir}")

        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        backup_path = BACKUP_DIR / str(tenant_id) / ts
        backup_path.mkdir(parents=True, exist_ok=True)

        archive = backup_path / "tenant_data.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(str(tenant_dir / "state"), arcname="state")
            tar.add(str(tenant_dir / "workspace"), arcname="workspace")

        log.info("tenant_backup_created", tenant_id=str(tenant_id), path=str(archive))
        return str(archive)

    def restore_tenant(self, tenant_id: uuid.UUID, archive_path: str) -> None:
        tenant_dir = Path(settings.tenant_base_dir) / str(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=str(tenant_dir))

        log.info("tenant_restored", tenant_id=str(tenant_id), archive=archive_path)

    def list_backups(self, tenant_id: uuid.UUID) -> list[str]:
        backup_dir = BACKUP_DIR / str(tenant_id)
        if not backup_dir.exists():
            return []
        return sorted(
            [str(p) for p in backup_dir.rglob("tenant_data.tar.gz")],
            reverse=True,
        )

    @staticmethod
    def backup_database(output_path: str) -> None:
        cmd = [
            "pg_dump",
            "--format=custom",
            "--file", output_path,
            settings.db_url.replace("+asyncpg", "").replace("postgresql", "postgresql"),
        ]
        subprocess.run(cmd, check=True)
        log.info("database_backup_created", path=output_path)
