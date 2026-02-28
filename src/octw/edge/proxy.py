"""
octw-edge: Reverse proxy with tenant routing, authentication, and wake-on-request.

Runs as a standalone ASGI app using httpx for upstream proxying.
Routes tenants by path prefix: /<slug>/...
"""
from __future__ import annotations

import re

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

from octw.api.auth import TokenPayload, decode_token
from octw.common.logging import get_logger
from octw.orchestrator.docker_orch import OPENCLAW_GATEWAY_PORT

log = get_logger(__name__)

edge_app = FastAPI(title="OCTW Edge Proxy")

_http_client: httpx.AsyncClient | None = None
_INTERNAL_API = "http://127.0.0.1:8000"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
_RESERVED_PATHS = {"api", "internal", "health", "metrics"}


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


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


async def _resolve_and_ensure(slug: str) -> str:
    """Resolve tenant slug to container IP, waking if necessary."""
    client = await _get_client()

    # Look up tenant by slug to get tenant_id
    await client.get(f"{_INTERNAL_API}/api/v1/tenants", params={"slug": slug})

    # Check current status
    status_resp = await client.get(
        f"{_INTERNAL_API}/internal/v1/tenants/{slug}/status"
    )
    if status_resp.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    data = status_resp.json()
    state = data.get("state", "not_found")
    ip = data.get("ip")

    if state == "running" and ip:
        return ip

    if state in ("paused", "stopped", "not_found"):
        ensure = await client.post(
            f"{_INTERNAL_API}/internal/v1/tenants/{slug}/ensure-running"
        )
        if ensure.status_code == 200:
            # Re-fetch IP after wake
            status_resp = await client.get(
                f"{_INTERNAL_API}/internal/v1/tenants/{slug}/status"
            )
            data = status_resp.json()
            ip = data.get("ip")
            if ip:
                return ip

    raise HTTPException(status_code=503, detail="Tenant is not available")


@edge_app.api_route(
    "/{slug}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_path(slug: str, path: str, request: Request):
    if slug in _RESERVED_PATHS or not _SLUG_RE.match(slug):
        raise HTTPException(status_code=404, detail="Not found")

    user = _authenticate(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    ip = await _resolve_and_ensure(slug)
    upstream_url = f"http://{ip}:{OPENCLAW_GATEWAY_PORT}/{path}"
    if request.url.query:
        upstream_url += f"?{request.url.query}"

    client = await _get_client()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers["x-octw-tenant-slug"] = slug
    headers["x-octw-user-id"] = str(user.user_id)
    headers["x-octw-user-email"] = user.email
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


@edge_app.api_route(
    "/{slug}",
    methods=["GET"],
)
async def proxy_slug_root(slug: str, request: Request):
    """Handle /<slug> without trailing slash."""
    if slug in _RESERVED_PATHS or not _SLUG_RE.match(slug):
        raise HTTPException(status_code=404, detail="Not found")
    return await proxy_path(slug, "", request)


@edge_app.get("/health")
async def health():
    return {"status": "ok", "service": "octw-edge"}
