"""
octw-edge: Reverse proxy with tenant routing, authentication, and wake-on-request.

Runs as a standalone ASGI app using httpx for upstream proxying.
Routes tenants by path prefix: /<slug>/...
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from octw.api.auth import TokenPayload, decode_token
from octw.common.config import settings
from octw.common.logging import get_logger
from octw.orchestrator.docker_orch import OPENCLAW_GATEWAY_PORT

log = get_logger(__name__)

edge_app = FastAPI(title="OCTW Edge Proxy")

_http_client: httpx.AsyncClient | None = None
_INTERNAL_API = settings.api_internal_base_url.rstrip("/")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
_RESERVED_PATHS = {"api", "internal", "health", "metrics", "app", "t"}


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


def _authenticate_request(request: Request) -> TokenPayload | None:
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


def _authenticate_websocket(websocket: WebSocket) -> TokenPayload | None:
    auth = websocket.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            return decode_token(auth[7:])
        except Exception:
            pass
    cookie_header = websocket.headers.get("cookie", "")
    for chunk in cookie_header.split(";"):
        name, _, value = chunk.strip().partition("=")
        if name == "octw_session" and value:
            try:
                return decode_token(value)
            except Exception:
                pass
    return None


async def _check_access(slug: str, user: TokenPayload) -> None:
    client = await _get_client()
    resp = await client.get(f"{_INTERNAL_API}/internal/v1/tenants/{slug}/access/{user.user_id}")
    if resp.status_code == 403:
        raise HTTPException(status_code=403, detail="Forbidden")
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")


async def _resolve_and_ensure(slug: str, user: TokenPayload) -> str:
    client = await _get_client()
    await _check_access(slug, user)

    status_resp = await client.get(f"{_INTERNAL_API}/internal/v1/tenants/{slug}/status")
    if status_resp.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    data = status_resp.json()
    state = data.get("state", "not_found")
    ip = data.get("ip")

    if state == "running" and ip:
        return ip

    if state in ("paused", "stopped", "not_found"):
        ensure = await client.post(f"{_INTERNAL_API}/internal/v1/tenants/{slug}/ensure-running")
        if ensure.status_code == 200:
            status_resp = await client.get(f"{_INTERNAL_API}/internal/v1/tenants/{slug}/status")
            data = status_resp.json()
            ip = data.get("ip")
            if ip:
                return ip

    raise HTTPException(status_code=503, detail="Tenant is not available")


def _proxy_headers_from_request(request: Request, slug: str, user: TokenPayload) -> dict[str, str]:
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("origin", None)
    headers.pop("x-octw-user-email", None)
    headers.pop("x-forwarded-for", None)
    headers["x-octw-tenant-slug"] = slug
    headers["x-octw-user-id"] = str(user.user_id)
    headers["x-octw-user-email"] = user.email
    headers["x-forwarded-for"] = request.client.host if request.client else "unknown"
    headers["x-forwarded-proto"] = "https"
    headers["x-forwarded-host"] = request.headers.get("host", settings.edge_domain)
    origin = request.headers.get("origin")
    if origin:
        headers["origin"] = origin
    return headers


@edge_app.websocket("/t/{slug}/ws")
async def tenant_websocket(slug: str, websocket: WebSocket):
    if slug in _RESERVED_PATHS or not _SLUG_RE.match(slug):
        await websocket.close(code=4404)
        return

    user = _authenticate_websocket(websocket)
    if not user:
        await websocket.close(code=4401)
        return

    try:
        ip = await _resolve_and_ensure(slug, user)
    except HTTPException as exc:
        await websocket.close(code=4403 if exc.status_code == 403 else 4404)
        return

    await websocket.accept()
    upstream_headers = {
        "origin": settings.public_base_url.rstrip("/"),
        "x-octw-user-id": str(user.user_id),
        "x-octw-user-email": user.email,
        "x-forwarded-for": websocket.client.host if websocket.client else "unknown",
        "x-forwarded-proto": "https",
        "x-forwarded-host": websocket.headers.get("host", settings.edge_domain),
    }
    upstream_url = f"ws://{ip}:{OPENCLAW_GATEWAY_PORT}"

    try:
        async with websockets.connect(
            upstream_url, additional_headers=upstream_headers
        ) as upstream:
            async def client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        break
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def upstream_to_client() -> None:
                async for message in _iter_upstream_messages(upstream):
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_upstream()),
                    asyncio.create_task(upstream_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
    except ConnectionClosed:
        pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("tenant_ws_proxy_failed", slug=slug, error=str(exc))
        await websocket.close(code=1011)


async def _iter_upstream_messages(upstream) -> AsyncIterator[str | bytes]:
    while True:
        try:
            yield await upstream.recv()
        except ConnectionClosed:
            break


@edge_app.get("/health")
async def health():
    return {"status": "ok", "service": "octw-edge"}


@edge_app.api_route(
    "/{slug}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_path(slug: str, path: str, request: Request):
    if slug in _RESERVED_PATHS or not _SLUG_RE.match(slug):
        raise HTTPException(status_code=404, detail="Not found")

    user = _authenticate_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    ip = await _resolve_and_ensure(slug, user)
    upstream_url = f"http://{ip}:{OPENCLAW_GATEWAY_PORT}/{path}"
    if request.url.query:
        upstream_url += f"?{request.url.query}"

    client = await _get_client()
    headers = _proxy_headers_from_request(request, slug, user)

    body = await request.body()
    resp = await client.request(
        method=request.method,
        url=upstream_url,
        headers=headers,
        content=body,
    )

    response_headers = {
        key: value for key, value in resp.headers.items()
        if key.lower() not in {"content-encoding", "transfer-encoding", "connection"}
    }
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers,
    )


@edge_app.api_route(
    "/{slug}",
    methods=["GET"],
)
async def proxy_slug_root(slug: str, request: Request):
    if slug in _RESERVED_PATHS or not _SLUG_RE.match(slug):
        raise HTTPException(status_code=404, detail="Not found")
    return await proxy_path(slug, "", request)
