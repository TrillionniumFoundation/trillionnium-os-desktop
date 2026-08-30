# Runtime source boundary

The superseded `runtime/servo/hepta_workspace_runtime.rs` source has been
removed. It was not referenced by a build target, workflow, image recipe, or
qualification gate and contained an in-process content-process kill path that
could be confused with the D2I fault-injection contract.

The only canonical headed runtime source for the current D2I qualification is:

```text
experiments/servo-headed-runtime/src/main.rs
```

D2I uses one externally supervised injector,
`trillionnium-d2i-content-crash-proof.service`, and requires
`runtime_internal_injector: false`. Keep runtime changes in the canonical
experiment source and update its exact-source workflow and evidence together.
