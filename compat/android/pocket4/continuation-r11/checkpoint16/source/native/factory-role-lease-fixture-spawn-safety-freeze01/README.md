# Lease fixture spawn observation safety

Only the fixture changes. The fixed-size vector of descriptor observations is fully allocated before fork/clone. After a successful spawn, the existing observation loop assigns already-present elements and opens no new descriptors before the original OwnedChild guard. This closes the reported allocation-exception window without hiding the preimage's closed descriptor numbers.

The same original/candidate two/four cases, expected states, deadlines, actual destruction and reaping assertions remain. Production OwnerLease, Registry, listener and snapshot bytes are unchanged. The old build01 and runtime request are preserved and are not admitted for execution after this source-level finding. No allocation exception was injected and no runtime leak was observed. The new matching build and all root controls are pending.
