# CPU group weight: explicit unsupported writes

The current scheduler does not implement cgroup-relative weight. A controller
write must therefore not acknowledge a policy or read back an arbitrary value
as if the scheduler applied it. This change removes the unused atomic weight
storage; it does not add group scheduling or change the original `cpu.max`
bandwidth owner.

## Public behavior

| Operation | Current result |
| --- | --- |
| Read active `cpu.weight` | `100\n`, including ordinary partial-read behavior |
| Write a value the original parser accepts in `1..=10000` | `EOPNOTSUPP`, including a write of `100` |
| Invalid, out-of-range or overflowing input | Original `EINVAL` |
| User-buffer copy fault | Original `EFAULT` |
| Inactive controller | Attribute remains absent; direct controller access retains its original attribute error |
| Disable and re-enable CPU controller | Weight remains the neutral `100`; no stored weight policy survives or appears |

The original parser still accepts its existing whitespace and leading-plus
forms. Invalid-input checking precedes the unsupported-operation result.
Reading `100` is a compatibility default, not evidence that group weight is
enforced. A client that requires a weight change must propagate the failed
write and keep the requested policy unapplied.

## Implementation and ownership

The original [CPU controller](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs)
retains the same attribute registration, input-copy boundary, range validation,
controller activation and bandwidth lock. Its unused `AtomicU32` weight field
is removed. A typed `OperationNotSupported` variant is added to the original
[system-tree error](../../kernel/asterinas/kernel/core/comps/systree/src/lib.rs)
and translated by the original [kernel error conversion](../../kernel/asterinas/kernel/core/src/error.rs)
to Linux `EOPNOTSUPP`.

No bandwidth revision, consumed CPU, positive debt, entitlement, task nice,
grant, namespace, ledger or timer is changed by a weight write. Implementing
weight later requires actual runnable-group selection and its own parent/child,
contention, CPU-count, starvation, activation and update tests. Mapping a group
value to one thread's nice value would not establish that contract.

## Regression and evidence boundary

Two [kernel attribute tests](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/config_regressions.rs)
call the actual controller with `VmReader`/`VmWriter`. They verify legal writes
return the typed unsupported result and Linux errno, malformed writes retain
their prior errno, all offset reads preserve `100\n`, an inactive controller
remains absent, and the complete original bandwidth state stays unchanged.
They are mandatory in the [strict core checker](../../support/build/ktest/check.py),
which retains all earlier required names and raises its minimum by two.

The original [cgroup guest regression](../../kernel/asterinas/test/initramfs/src/regression/process/cgroup.sh)
now requires legal weight writes to fail and their readback to stay `100`.
It continues to exercise real `cpu.max` configuration and controller toggles.
No historical evidence file is rewritten. A source change, parser test or shell
syntax check does not constitute native execution; publish the final-source
QEMU raw exit, complete suite and serial evidence before claiming this version
ran. Existing successful `cpu.max` evidence is still evidence for its original
source and is not a weight-scheduling result.
