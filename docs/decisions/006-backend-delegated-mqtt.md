# ADR-006: Backend-delegated MQTT for "Send to Printer"

**Date:** 2026-06-26  
**Status:** Accepted

## Context

Sending a job to the Bambu P1S requires MQTT over the local LAN (Bambu's proprietary
protocol). The desktop app must decide whether to speak MQTT directly or delegate to the
backend.

## Decision

**Delegate entirely to the backend.** `ApiClient.send_to_printer(job_id)` POSTs to
`/api/jobs/{id}/send-to-printer`; the backend handles all MQTT framing and TLS.

## Rationale

- The Bambu MQTT protocol requires device credentials (serial, access code) that are
  already stored securely on the backend — duplicating them in the desktop app would be
  a credential-sprawl risk.
- MQTT connectivity is only needed from the server (same LAN segment as the P1S via k8s
  hostNetwork or NodePort); the desktop may be on a different Tailscale node.
- Backend centralises retry and error-reporting logic; the desktop only needs to surface
  the returned job status.
- Keeps the desktop dependency list clean — no `paho-mqtt` or async MQTT client needed.

## Consequences

- The desktop cannot send jobs if the backend is unreachable (same constraint as all other
  features — acceptable given the LAN-only design).
- Future direct-send capability (e.g., when running from the same LAN without the backend)
  would require adding MQTT credentials to the desktop's local settings store.
