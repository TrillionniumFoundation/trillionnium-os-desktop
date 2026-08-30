# D0C-02 independent Agent transport reference evidence

> **HISTORICAL BASELINE / STALE_EVIDENCE:** This reference run records the
> independent Python transport oracle at its original checkpoint. The bound
> Rust host result and contract metadata are historical; rerun the exact-head
> gate before using either result for current promotion.

> **SUPERSEDED_HISTORICAL:** The unexecuted-Rust wording below describes the
> initial snapshot. Current Rust host validation and claim status are recorded
> in `docs/evidence/2026-08-28-d0c02-authenticated-uds.md` and the machine
> evidence under `docs/evidence/generated/`.

**Date:** 2026-08-28  
**Scope:** wire-contract reference and local AF_UNIX behavior only  
**Product listener:** not created  
**Browser payload semantics:** not interpreted  
**Rust execution gate:** historical host result exists; it is stale for the
current candidate
**Evidence lifecycle:** `STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN`

## Purpose

At this checkpoint the private-repository GitHub jobs failed before runner
assignment, so this evidence added a second implementation of the fixed
transport contract using only the Python standard library. A later historical
Rust host result is recorded separately; this reference remains independent
and does not replace the Rust format, Clippy, test or `hepta-browserd
--self-check` merge gate.

## Executed environment

```text
Python 3.13.5
Linux 6.18.35 x86_64 GNU/Linux
Linux-6.18.35-x86_64-with-glibc2.41
```

## Commands executed

```text
python3 -m unittest discover -s tests/transport -p 'test_*.py' -v
python3 tools/agent_transport_reference.py \
  --contract contracts/agent-transport.v1.json \
  --write-result docs/evidence/generated/d0c02-agent-transport-reference-result.json \
  --write-vector contracts/golden/agent-transport-request.v1.json
python3 -m py_compile \
  tools/agent_transport_reference.py \
  tests/transport/test_agent_transport_reference.py
```

## Observed result

All 15 tests passed. The executed corpus covered:

- contract/header-layout agreement;
- deterministic encode/decode and fixed wire hash;
- real `AF_UNIX/SOCK_STREAM` socketpair round trip;
- Linux `SO_PEERCRED` PID/UID/GID acquisition and policy rejection;
- maximum payload rejection before payload read;
- payload digest tamper rejection;
- non-zero reserved flag rejection;
- unknown frame kind rejection;
- invalid magic and unsupported version rejection;
- replayed and skipped sequence rejection;
- truncated payload rejection;
- all-zero nonce rejection;
- monotonic absolute deadline behavior.

Stable evidence hashes:

```text
reference source SHA-256:
  ad289a7a719475a77b259a542d23c88718c867f51ecd605f3477f38086947335
contract SHA-256:
  1fbabe2b324d4b5814a7feb7b462991adc4ad7661509b8aec732c37168a8ce80
reference result SHA-256:
  5ddc040cb0b666bdde1b6bd41981143912d722a2786685c129b87929fe9fc58e
golden vector SHA-256:
  c23c0a37c45188d5b224afd5659f18b68ce47cf3e62f108ad1d23c6bc2540011
deterministic encoded frame SHA-256:
  b9749d9789dab1e274e3ddee1355d0bb65c6df03ecce67e1bc78a317656bbcf0
```

## Claim ceiling

This evidence proves that an independent implementation agrees with the
machine-readable header contract and that the reference boundary behaves
fail-closed for the listed vectors on the recorded host. It does not prove that
the Rust crate compiles, that its tests pass, that a product listener exists,
that a Browser API request is decoded, that a BrowserActor dispatch occurs, or
that Servo is integrated.

PR merge readiness remains false until the exact Rust 1.93 commands recorded in
the contract pass against the exact candidate head.
