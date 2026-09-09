# hepta-agent-port

**Work package:** S04 / D0C-04  
**Claim ceiling:** one canonical request over one authenticated connected stream,
with bounded lifecycle observation; no listener, semantic principal, BrowserActor,
Servo, capability, external effect, installed image, hardware, signing, or release.

## Request path

```text
connected authenticated stream using OS entropy
  -> canonical Browser API decode
  -> immutable request-bound DispatchContext
  -> requested lifecycle observation
  -> dispatched lifecycle observation
  -> at most one typed handler invocation
  -> terminal or interrupted observation
  -> canonical request-bound response
  -> at most one response frame
```

The handler cannot author protocol, request ID, session identity, transport
sequence, or connection nonce. AgentPort exposes no nonce-source injection API;
all production serving enters through `ServerConnection::accept`, whose public
transport facade is OS-entropy-only. Handler result bytes are bounded before
response construction. Late results are discarded, and a response is never
committed after the effective monotonic deadline.

## Lifecycle observer

The observer records mechanism facts only. Failure to record `requested` stops
before handler invocation. Failure to record `dispatched` or terminal state stops
response publication. A terminal fact is recorded before response transport
commit. This crate does not itself persist receipts; S05 owns durable storage and
S06/S08 own real BrowserActor integration.

## Logging and privacy

`DispatchContext` uses the transport's redacted `PeerIdentity` formatter. Raw PID,
UID, GID and nonce values are never included in public transport/connection error
text. `AgentPortError::Handler` retains the direct caller's error value but formats
only a fixed redacted message so handler-provided page text or credentials are not
accidentally logged through `Display` or `Debug`.

## Effect ceiling

The D0 fixture accepts health only, denies potential external effects, and reports
browser-dependent operations unsupported. Classification is not authorization and
no indeterminate effect is retried automatically.

## Verification

```bash
python3 tools/validate_s04_transport_custody.py
cargo test --locked -p hepta-agent-port
cargo clippy --locked -p hepta-agent-port --all-targets -- -D warnings
```
