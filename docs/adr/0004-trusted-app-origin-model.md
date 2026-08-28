# ADR 0004: Trusted apps use distinct synthetic HTTPS origins

- Status: Accepted
- Date: 2026-08-28

## Decision

Trusted origins are:

```text
https://shell.system.hepta.invalid/
https://<app-id>.<publisher>.apps.hepta.invalid/
```

The embedder intercepts these hosts locally; they never resolve through public
DNS. Each app receives a distinct tuple origin. A path-only custom scheme with
a shared host is not permitted because it cannot provide the required storage,
CSP, service-worker, and same-origin isolation without engine-specific rules.
