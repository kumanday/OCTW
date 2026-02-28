"""
octw-edge: Reverse proxy with tenant routing, authentication, and wake-on-request.

Runs as a standalone ASGI app using httpx for upstream proxying.
Supports subdomain routing (<slug>.domain) and path routing (/t/<slug>/...).
"""
from __future__ import annotations

import re

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

from octw.api.auth import TokenPayload, decode_token
from octw.common.config import settings
from octw.common.logging import get_logger
from octw.orchestrator.docker_orch import OPENCLAW_GATEWAY_PORT

log = get_logger(__name__)

edge_app = FastAPI(title="OCTW Edge Proxy")

_http_client: httpx.AsyncClient | None = None
_INTERNAL_API = "http://127.0.0.1:8000"


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


def _extract_slug_subdomain(host: str) -> str | None:
    domain = settings.edge_domain
    if host.endswith(f".{domain}"):
        slug = host[: -(len(domain) + 1)]
        slug = slug.split(":")[0]
        if slug and re.match(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$", slug):
            return slug
    return None


def _extract_slug_path(path: str) -> tuple[str | None, str]:
    m = re.match(r"^/t/([a-z0-9][a-z0-9\-]*[a-z0-9])(/.*)?$", path)
    if m:
        return m.group(1), m.group(2) or "/"
    return None, path


def _authenticate(request: Request) -> TokenPayload | None:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            return decode_token(auth[7:])
        except Exception:
            pass
    cookie = request.cookies.get("octw_session")
    if cookie:
        try:
            return decode_token(cookie)
        except Exception:
            pass
    return None


async def _resolve_tenant_ip(slug: str) -> str:
    client = await _get_client()
    resp = await client.get(f"{_INTERNAL_API}/internal/v1/tenants/{slug}/status")
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")
    data = resp.json()
    ip = data.get("ip")
    if not ip or data.get("state") == "not_found":
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not available")
    return ip


async def _ensure_running_by_slug(slug: str) -> str:
    client = await _get_client()
    # Look up tenant by slug via internal API
    await client.get(f"{_INTERNAL_API}/api/v1/tenants?slug={slug}")
    # Fallback: use slug-based status endpoint
    status_resp = await client.get(f"{_INTERNAL_API}/internal/v1/tenants/{slug}/status")
    if status_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Cannot resolve tenant")

    data = status_resp.json()
    state = data.get("state", "not_found")
    ip = data.get("ip")

    if state == "running" and ip:
        return ip

    # Try to wake via internal ensure-running (needs tenant_id, not slug)
    # For now, return error and let caller retry
    raise HTTPException(status_code=503, detail="Tenant is waking up, retry shortly")


@edge_app.api_route(
    "/t/{slug}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_path(slug: str, path: str, request: Request):
    user = _authenticate(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    ip = await _resolve_tenant_ip(slug)
    upstream_url = f"http://{ip}:{OPENCLAW_GATEWAY_PORT}/{path}"
    if request.url.query:
        upstream_url += f"?{request.url.query}"

    client = await _get_client()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers["x-octw-tenant-slug"] = slug
    headers["x-octw-user-id"] = str(user.user_id)
    headers["x-octw-user-email"] = user.email
    # Sanitize forwarded headers
    headers.pop("x-forwarded-for", None)
    headers["x-forwarded-for"] = request.client.host if request.client else "unknown"
    headers["x-forwarded-proto"] = "https"

    body = await request.body()
    resp = await client.request(
        method=request.method,
        url=upstream_url,
        headers=headers,
        content=body,
    )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


@edge_app.get("/health")
async def health():
    return {"status": "ok", "service": "octw-edge"}
