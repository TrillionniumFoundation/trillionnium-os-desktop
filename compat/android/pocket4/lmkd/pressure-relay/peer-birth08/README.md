# Required lifecycle peer process generation — candidate 08

This independent candidate adds a mandatory lifecycle-owned `ProcessPin` to the role policy. It does not modify the frozen 06a/07b sources, the one completed host PSI event, Android LMKD, or Main. It is not an installed supervisor patch.

The original owner library authenticates the actual accepted socket using `SO_PEERPIDFD`, real proc identity, all ten namespace descriptors, UID/GID, executable, root, exact cgroup membership and projection. Those checks alone admit a second process sharing that entire class. The intended process must also be named independently by the trusted lifecycle. The new field retains that expected PID/birth/pidfd/proc generation, checks its continued liveness, and matches the accepted kernel-bound process before and after every peer snapshot. Replacement requires a fresh immutable authority generation. No kernel identity check or fallback is relaxed.

The focused real-kernel control creates an owned child A, first makes its mount propagation private, and binds only its existing bounded job cgroup read-only. The parent pins A through its own `Child` before accepting its connection. It then spawns a different direct child B into A's held and rechecked mount namespace before executing the identical binary. Both remain in their original job cgroup. Independent proc reads prove identical ten namespaces, UID/GID, executable, root, membership and projection, while their PID/birth tuples differ. A must authenticate and survive B's precise rejection. Both close normally.

The negative builds the exact original library `063a54453e2062b2094ccf702d26a072e8e2d4518c00144cee90992e39ee97d9`. Its test source differs only by omitting the new field from the `RolePolicy` initializer to match the old API. The same real preconditions and exact rejection assertion remain. It must fail because it actually authenticates and revalidates B, then clean both children and all resources before returning the expected failure. This is not a fake socket, modified namespace policy, or a semantic approximation of the old library.

The runner permits only ordinary and private mount controls under the existing job's 1 CPU/512 MiB upper bounds. It never selects the PSI, allocation, Android, or cgroup-creation test modes. It checks job process generations, original budgets, namespace/projection, local memory events, controllers, hierarchy and direct children after both arms. A failure or timeout is retained as failure rather than qualified by partial evidence.

## Remaining integration gates

The constructor here holds a trusted host `std::process::Child`. Adopting the intended guest LMKD process from a real cell lifecycle, passing the Android recipient FD, proving installed supervisor source lineage and stable listener ancestors, and qualifying actual LMKD victim decisions remain separate work. No new pressure event is authorized or performed by this candidate. The old r7 foreground-loss failure remains open, b099 remains prohibited for Main, and the earlier host PSI event cannot qualify Android foreground protection.

Source, execution evidence and publication status are frozen separately. This document initially describes the prepared controls, not an execution result.
