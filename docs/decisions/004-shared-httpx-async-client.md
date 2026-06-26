# ADR-004: Single shared httpx.AsyncClient per process

**Date:** 2026-06-26  
**Status:** Accepted

## Context

The app makes multiple sequential and concurrent HTTP calls (filament SKU list, job history,
polling, printer status). Options: create a new client per request, or share one client for
the process lifetime.

## Decision

One `httpx.AsyncClient` instance is created at app startup and closed at shutdown.
The `ApiClient` wrapper owns the instance and exposes `aclose()` for teardown.

## Rationale

- httpx recommends a single long-lived client for connection pooling and keep-alive reuse.
- The backend is a single host (no load-balancer diversity) — one connection pool is enough.
- Avoids the overhead of TLS handshakes on every call, which matters on slow Tailscale hops.
- Creating per-request clients leaks sockets if `aclose()` is ever missed.

## Consequences

- The client is not thread-safe; all calls must happen on the Qt/asyncio event loop thread
  (enforced by qasync — no `run_in_executor` escapes).
- Shutdown must call `await api_client.aclose()` before the Qt app exits.
