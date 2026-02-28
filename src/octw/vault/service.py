from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from octw.db.tables import SecretRow, TenantDEKRow
from octw.models.secret import SecretMetadata, SecretType
from octw.vault.envelope import EnvelopeVault


class VaultService:
    def __init__(self, vault: EnvelopeVault) -> None:
        self._vault = vault

    async def ensure_tenant_dek(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> bytes:
        row = await session.get(TenantDEKRow, tenant_id)
        if row:
            return self._vault.decrypt_dek(row.encrypted_dek, row.dek_nonce)
        dek = self._vault.generate_dek()
        enc_dek, nonce = self._vault.encrypt_dek(dek)
        session.add(TenantDEKRow(
            tenant_id=tenant_id, encrypted_dek=enc_dek, dek_nonce=nonce
        ))
        await session.flush()
        return dek

    async def store_secret(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        name: str,
        plaintext: str,
        secret_type: SecretType = SecretType.ENV,
        target_env_var: str | None = None,
    ) -> SecretMetadata:
        dek = await self.ensure_tenant_dek(session, tenant_id)
        ct, nonce = self._vault.encrypt_value(dek, plaintext.encode())

        existing = (
            await session.execute(
                select(SecretRow).where(
                    SecretRow.tenant_id == tenant_id, SecretRow.name == name
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.ciphertext = ct
            existing.nonce = nonce
            existing.secret_type = secret_type.value
            existing.target_env_var = target_env_var
        else:
            session.add(SecretRow(
                tenant_id=tenant_id,
                name=name,
                ciphertext=ct,
                nonce=nonce,
                secret_type=secret_type.value,
                target_env_var=target_env_var,
            ))
        await session.flush()
        return SecretMetadata(
            name=name,
            tenant_id=tenant_id,
            type=secret_type,
            target_env_var=target_env_var,
        )

    async def get_decrypted_secrets(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> dict[str, str]:
        dek = await self.ensure_tenant_dek(session, tenant_id)
        rows = (
            await session.execute(
                select(SecretRow).where(SecretRow.tenant_id == tenant_id)
            )
        ).scalars().all()
        result: dict[str, str] = {}
        for row in rows:
            plaintext = self._vault.decrypt_value(dek, row.ciphertext, row.nonce)
            env_key = row.target_env_var or row.name
            result[env_key] = plaintext.decode()
        return result

    async def list_secret_metadata(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> list[SecretMetadata]:
        rows = (
            await session.execute(
                select(SecretRow).where(SecretRow.tenant_id == tenant_id)
            )
        ).scalars().all()
        return [
            SecretMetadata(
                name=r.name,
                tenant_id=r.tenant_id,
                type=SecretType(r.secret_type),
                target_env_var=r.target_env_var,
                algorithm=r.algorithm,
                key_version=r.key_version,
                last_rotated_at=r.last_rotated_at,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    async def delete_secret(
        self, session: AsyncSession, tenant_id: uuid.UUID, name: str
    ) -> bool:
        row = (
            await session.execute(
                select(SecretRow).where(
                    SecretRow.tenant_id == tenant_id, SecretRow.name == name
                )
            )
        ).scalar_one_or_none()
        if row:
            await session.delete(row)
            await session.flush()
            return True
        return False
