from __future__ import annotations

from octw.orchestrator.docker_orch import DockerOrchestrator
from octw.orchestrator.tenant_service import TenantService
from octw.vault.envelope import EnvelopeVault
from octw.vault.service import VaultService

_orch: DockerOrchestrator | None = None
_vault: EnvelopeVault | None = None
_vault_service: VaultService | None = None
_tenant_service: TenantService | None = None


def get_orchestrator() -> DockerOrchestrator:
    global _orch
    if _orch is None:
        _orch = DockerOrchestrator()
    return _orch


def get_vault() -> EnvelopeVault:
    global _vault
    if _vault is None:
        _vault = EnvelopeVault()
    return _vault


def get_vault_service() -> VaultService:
    global _vault_service
    if _vault_service is None:
        _vault_service = VaultService(get_vault())
    return _vault_service


def get_tenant_service() -> TenantService:
    global _tenant_service
    if _tenant_service is None:
        _tenant_service = TenantService(get_orchestrator(), get_vault_service())
    return _tenant_service
