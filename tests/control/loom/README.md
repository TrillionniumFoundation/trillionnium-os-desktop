# os-control Loom development harness

This standalone manifest is a concurrency harness for
[os-control](../../../libs/os-control/README.md), not a second implementation
of its state machine. [run-models.py](run-models.py) stages the real production
modules and substitutes only the default synchronization shim. The public
backend variant injects Loom through the actual public `LockBackend` API.

## Run and maintain

```sh
python3 tests/control/loom/run-models.py /tmp/a03-loom-current
```

Run from the repository root with the toolchain described in
[control validation](../VALIDATION.md). Use this driver rather than invoking
the manifest without its generated source tree. The output directory contains
the exact staged sources, commands, schedule counts and exits. A source change
requires a new run; old schedule totals cannot qualify the new source.

[models.rs](models.rs) covers shared state under the substituted default lock;
[models_public.rs](models_public.rs) covers public lock injection and real
native owner handles. Add races at real admission, publication, namespace loss
and retirement transitions. Reducing a model's bounds needs an explicit reason
and a corresponding report of the lost interleavings.

## Scope, authority and failures

The model owns only fixture threads and modeled in-memory synchronization.
Synthetic owner/capability values convey no OS authority. A model failure must
preserve its counterexample and staged source; it is not resolved by skipping
that execution. Loom does not prove kernel IRQ/preemption/SMP behavior, actual
allocation failure, persistent storage, process death or Hepta crash recovery.
Those need the independent kernel and original-writer gates.
