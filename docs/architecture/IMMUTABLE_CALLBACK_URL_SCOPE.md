# Immutable callback URL scope v1

`contracts/immutable-callback-url-scope.v1.json` pins the additive API version
0.1.0 and its exact Rust signature:

```rust
pub fn closed_immutable_callback_engine_pair<R: CallbackPageRuntime>(
    runtime: R,
    waker: Arc<dyn EngineEventLoopWaker>,
) -> (EngineThreadRuntime, CallbackEngineOwner<R>)
```

This constructor selects the existing fixed read-only native document's URL.
It takes no URL, capability flag, principal or duration. Construct and pump the
owner on its creator engine thread. The caller must separately retain the
closed operation profile, original live peer custody and original deadline.
The returned actor endpoint is noncloneable; the native callback owner is neither
Send nor Sync. Selection supplies URL correspondence and grants no peer authority.

The original `engine_thread_pair` and `callback_engine_pair` keep their existing
D3 predicate: `about:blank` or loopback HTTP. The closed Servo profile selects
this additive constructor. Its private scope accepts the exact existing
immutable document URL and the exact `about:blank` empty document value already
used by the read-only bridge's source callback clients. An empty document reply
does not prove that the fixed native HTML has loaded. Other data documents, HTTP URLs, files, queries and
fragments fail closed. This scope travels inside the opaque actor endpoint,
callback owner and single-use completion. Actor preflight and dispatch check
owner URLs; both callback completion and owner polling check reply URLs.

An incorrect owner URL or invalid owner token/fixture identity returns
`PolicyDenied` before dispatch. An incorrect callback URL returns redacted
`Internal` and retires the pair. A reply with no URL remains available for the
existing health/uncertain close semantics. It cannot mint a URL or revive a
retired owner. Native success continues to derive `current_url` from the actual
owned `WebView::url()`. It does not substitute a constant or `about:blank` for
the engine's observed URL. Original five-second native and twenty-second
connection ceilings remain unchanged.

The prior bridge rejected the native fixed data document at its generic D3
reply URL guard. That path produced `Internal` after a real native completion;
the same D3 owner guard also rejected subsequent semantic observations.
The selected scope addresses both paths while preserving the D3 default.

Six Rust regressions exercise real local callback/channel dispatch with
explicit synthetic replies, including the original rejection, additive success,
subsequent owner snapshot, retained blank health/owner compatibility, other-URL
refusal and existing owner token checks for both accepted document values.
The source validator binds the closed contract, signature, opaque fields,
constructor defaults and guard propagation. These checks do not execute Servo,
expand Rust macros, approve a principal or qualify an installed product. Actual
fixed-PIN original four and approved two cases still require separate execution
on each complete candidate object. Installed, hardware, human approval and
release evidence remain separate.
