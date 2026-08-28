# ADR 0006: External interaction requires controlled egress and effect gates

- Status: Accepted; implementation pending D6
- Date: 2026-08-28

## Decision

Click, type, press, select, and navigation can cause external effects and are
not labelled read-only. External Agent mutation remains disabled until browser
traffic is confined through a controlled resolver/egress architecture that
checks DNS answers, actual peers, redirects, private/link-local/metadata ranges,
workers, WebSocket/QUIC, downloads, and external schemes.

Indeterminate dispatched effects are never retried automatically.
