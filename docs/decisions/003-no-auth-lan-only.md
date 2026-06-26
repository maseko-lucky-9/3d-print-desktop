# ADR-003: No authentication — LAN-only behind K8s NetworkPolicy

**Date:** 2026-06-26  
**Status:** Accepted

## Context

The companion backend (`print-calc`) runs in a home-lab Kubernetes cluster exposed only via
Tailscale (hostname `print-calc.homelab`). The desktop app needs to decide whether to
implement token-based auth, mTLS, or rely on network isolation.

## Decision

**No application-layer auth.** The backend is unreachable from the public internet;
access is gated entirely by the K8s NetworkPolicy and Tailscale ACLs.

## Rationale

- The cluster is single-user, home-lab only — no multi-tenant risk.
- Tailscale provides device-identity auth at the network layer.
- Adding token auth would require secret storage on the client (Keychain) and rotation
  logic on the server — cost not justified for a private, single-operator tool.
- If the backend is ever exposed beyond Tailscale, this decision must be revisited and
  token/mTLS auth added before any public exposure.

## Consequences

- Any device on the Tailscale network can reach the backend — acceptable for home use.
- The `ApiClient` has a `ca_path` parameter for custom CA pinning if the backend ever
  moves to a self-signed cert, keeping mTLS adoption cheap.
- This decision is explicitly a security boundary: **never expose `print-calc` without
  revisiting this ADR.**
