# Rust Browser API codec

**Checkpoint:** `TOS-D0C-03`  
**Product crate:** `crates/hepta-browser-codec`  
**Status:** source implemented; trusted Rust execution pending

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

Current demonstrated evidence:

```text
Python reference:        27/27 PASS
Python py_compile:       PASS
Rust static source audit: 96/96 PASS
Rust fmt:                UNEXECUTED
Rust Clippy:             UNEXECUTED
Rust tests:              UNEXECUTED
browserd self-check:     UNEXECUTED
```

Static or reference evidence does not imply that the Rust crate compiles. The
PR remains draft and non-merge-ready until all exact-head Rust commands pass.
