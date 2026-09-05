# Rust Browser API codec

**Checkpoint:** `TOS-D0C-03`  
**Product crate:** `crates/hepta-browser-codec`  
**Status:** current source audit is green; recorded Rust host result is
`STALE_EVIDENCE` until an exact-head rerun; no listener or dispatch

## Boundary

The transport layer hands opaque bytes to this crate. No caller may dispatch a
BrowserActor operation before `decode_request` succeeds. The decoder performs,
in order:

1. byte-size and UTF-8/BOM checks;
2. bounded JSON parsing with recursive duplicate-member rejection;
3. integer-only, signed-64-bit, depth-32 and aggregate-item-20,000 checks;
4. exact typed request or response conversion with unknown-field refusal;
5. session ID/generation, semantic reference, URL and operation validation;
6. sorted-key compact canonical re-encoding;
7. byte-for-byte equality with the received payload;
8. canonical SHA-256 publication for later receipts.

The parser is product-owned and uses only the already locked `sha2=0.10.9`
external closure. It does not add a general-purpose JSON or URL dependency.

## Authority ceiling

The crate classifies but never authorizes:

```text
observation
local_interaction
potential_external_effect
```

Every navigation is a potential external effect. Click, type, press and select
are also potential effects. Scroll is local interaction. The distinction is
passed to D0C-04; it is not a permit.

The crate has no `UnixListener`, `TcpListener`, WebDriver, Servo or BrowserActor
dependency. It may be called only after peer-authenticated transport admission.

## Conformance

The same contract is exercised by the standard-library Python reference and
six byte-exact golden request/response vectors. The reference now also rejects
integers outside the signed 64-bit domain, bringing its numeric contract into
line with the product parser.

Current source/reference checks:

```text
Python reference:        27/27 PASS
Python py_compile:       PASS
Rust static source audit: 107/107 PASS
Rust fmt:                PASS
Rust Clippy:             PASS
Rust tests:              PASS
browserd self-check:     PASS
```

The checked-in Rust 1.93 host result is a historical baseline bound to
`4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb`; it is explicitly marked
`STALE_EVIDENCE` because the current candidate changed codec source, contract,
and validation inputs. A fresh exact-head CI run and independent evidence
promotion are required before setting `merge_ready`. None of this implies a
listener, BrowserActor conversion or Servo dispatch; those remain later-stage
gates.
