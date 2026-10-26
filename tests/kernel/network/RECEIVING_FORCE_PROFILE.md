# Receiving FAIR / affinity / IPC source profile

`receiving-force-v1` qualifies the separately reviewed composition of W2/W3A/W3B
with the receiving P1/P2/P3 scheduling and Binder D1 implementation. It starts
from receiving source `d3ae4b9a` and the W3 merge `38f4fc57`. The profile is source
admission for ordinary Unix tests; it does not grant native authority, implement
group weights, or preserve the validity of an old M5 receipt for a new kernel.

The new `run_unix_stream_receiving_guest.py` loads a private instance of the
historical engine after checking its literal SHA256. Only that private instance
adds the new profile name and data selector. The original `check_sources`,
source head/tree checks, ordinary build, ELF and artifact verification, nonce,
initramfs transform and Unix oracle execute unchanged. No verifier is replaced.
The public historical module and old engine, manifest and profile tests retain
their exact original bytes. Legacy profile names still delegate to the original
selector and honestly reject this composition.

Seventy fixed code-owned roles bind complete source bytes: original IPC backing
and owner paths, cgroup CPU owners, FAIR/RT queues and transaction state,
administration/permissions/static nice/user-policy snapshot and clone inheritance,
OSTD interrupt/switch/wait ownership, and the existing oracle/ordinary receipt
boundaries. Every role maps to one real unique source path and one literal SHA256.
No command-line manifest, additional source directory, wildcard or runtime current
source hash can admit a different composition. Changing a pinned path requires a
new explicit review and profile update. This bounded dependency set is not a
claim that every unchanged kernel file is covered by this profile; full-source
Git blob/mode and exact ordinary product binding remain separate requirements.

Use a clean frozen receiving source and a new external evidence directory:

```sh
python3 -I -B tests/kernel/network/run_unix_stream_receiving_guest.py \
  --expected-source-head FULL_HEAD --expected-source-tree FULL_TREE \
  --target-dir /independent/kernel/target --output /new/evidence \
  --source-profile receiving-force-v1 --variant positive --selection all
```

Run again with `--selection shutdown_race` and a different output directory.
These are new receipts, explicitly named `receiving-force-v1`. Historical
`race-fixed`, `race-stale` and `aux-zero-progress` mutation variants are refused
under this production profile. The old `ipc-memory-v1` still refuses the changed
cgroup owner and must not be used to label the new evidence.

The receiving host suite checks actual reviewed bytes, all 70 missing/drifting
path negatives, engine-byte tampering, unique paths, unknown names, mutation
refusal, old-profile refusal and original IPC owner coverage. Its synthetic
negatives prove source admission only. The historical M5 host test asserting
that the *working source* equals the old M5 profile remains unchanged and is
applicable to the frozen M5 tree; this new composition deliberately cannot satisfy
that old positive assertion. Its manifest and synthetic negative checks remain
separately usable. Real ordinary guests are still required for both selections.

The receiving merge preserves the actual target Process/namespace `SYS_NICE`
gate and all seven affinity permission cases. P2/P3 setters update declared nice
and Idle state without replacing affinity generation/pending request state.
Snapshot getters copy short state/policy without waiting on the pending writer
pin; fresh clone construction starts at generation zero with no pending request,
CPU ownership or inherited scheduling debt. Controlled merge regressions cover
these boundaries; actual multi-CPU and CPU-time tests remain required.
