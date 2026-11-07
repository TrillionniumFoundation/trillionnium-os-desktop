# OwnerLease lifetime successor

This independent source revision includes the exact previously frozen Registry owner-destruction fix and repairs the same inherited-object RAII boundary in OwnerLease. The old dispatch, Registry, and OwnerLease source remain unchanged.

OwnerLease now stores its owned descriptors in a private Impl. Its destructor, getters and verification first prove that the caller is the original service main thread. The proof combines original live self PIDFD with the current thread identity read beneath a held, verified proc view. The numeric PID/TID equality check alone is insufficient across PID namespaces. Foreign destruction does not delete Impl, close its descriptors, assign the shared pointer, or change caller errno. Public move/copy is disabled. Object storage itself remains owner-controlled.

Initialize keeps Impl in a local unique_ptr until every authority check, held proc proof and idle owner-control check succeeds. Failed initialization therefore cleans temporary state without requiring an already-published ownership proof. The input control descriptor is consumed only on success. Legitimate destruction does not require the separate service owner still to be alive; only this object's original service thread ownership is needed. If the held ownership proof is lost, destruction fails closed until process lifetime reclaims the remaining resources.

## Scope and actual local evidence

Two strict local compiler invocations and the two default PLAN modes passed. Both ELF root controls remain NOT RUN. The comparison links the same repaired Registry and other core sources; only the preimage OwnerLease cc/h and the explicit test-arm macro differ. The actual local result is preserved verbatim with its source map and compiler pin.

The planned preimage has two cases: shared-VM/shared-FD destruction demonstrates the original close, and one-free-slot EMFILE verifies partial initialization cleanup. The candidate has four cases: shared-VM/shared-FD, shared-VM/private-FD, private fork, and the same EMFILE point. Each root-owner peer and foreign child is PIDFD-held and normally reaped. Preimage parent storage is deliberately abandoned after foreign destruction instead of reused. The fixture does not separately execute a numeric PID-namespace alias case.

No Hepta calls, root fixture execution, capability change, platform policy, Android, Main action, listener, or persistent service was performed. The existing root-peer and namespace authority gates stay intact. This repair is not activation of the Android early-fork protocol.
