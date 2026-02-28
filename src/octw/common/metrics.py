from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

tenant_container_starts = Counter(
    "octw_tenant_container_starts_total",
    "Total tenant container start events",
    ["tenant_id"],
)

tenant_container_stops = Counter(
    "octw_tenant_container_stops_total",
    "Total tenant container stop events",
    ["tenant_id"],
)

tenant_wake_events = Counter(
    "octw_tenant_wake_events_total",
    "Total wake-on-request events",
    ["tenant_id"],
)

tenant_pause_events = Counter(
    "octw_tenant_pause_events_total",
    "Total tenant pause events",
    ["tenant_id"],
)

active_tenants = Gauge(
    "octw_active_tenants",
    "Number of currently running tenant containers",
)

proxy_request_duration = Histogram(
    "octw_proxy_request_duration_seconds",
    "Edge proxy request duration",
    ["tenant_slug", "method", "status"],
)

secret_operations = Counter(
    "octw_secret_operations_total",
    "Secret lifecycle operations",
    ["tenant_id", "operation"],
)

auth_failures = Counter(
    "octw_auth_failures_total",
    "Authentication failures",
    ["reason"],
)
