# Finite cgroup holding view and bootstrap leaf — paired source 01

Status: source frozen; C ordinary local controls only. Matching Rust/Android build and real Owner are not yet qualified. Main and installed files are unchanged.

## Concrete startup repair

The actual08 producer mounted its private finite cgroup2 domain at `/sys/fs/cgroup` before init. The device AOSP reference later attempts Android's original cgroup2 mount at that same target, with `memory_recursiveprot` then NULL fallback; failed setup returns before creating `/system` and `/apps`. The actual compat ELF's 29 dynamic symbols do not export a normal mount hook. Old Owner08 journal candidates remain unbound to a trusted sender; this source repair is not a retroactive cause claim.

ABI3 moves the handshake's cgroup view to the root-owned `/dev/.droidloom-cgroups/relay-v2` holding mount. Host and C peer both prove the original finite domain inode and finite policy through this view. Both require the stock `/sys/fs/cgroup` target to remain on the original private synthetic sys tmpfs. Android then performs its actual mount, permissions, controller setup and subdirectory creation. No mount return value is substituted, no EBUSY is swallowed, and no ancestor domain is exposed. LMKD still opens the original `/sys/fs/cgroup` path when Android starts it.

The independent leaf repair creates `init-bootstrap` inside the finite Android domain. Entry enters the Android root, seals its cgroup namespace there, proves the holding view, then moves only itself to the leaf. Local root cgroup.procs is empty before Android controller setup. Host checks the exact received init generation at HELLO; the final pre-exec callback repeats membership after CPU-placement callbacks. Leaf controllers remain disabled. Existing whole-tree retirement remains intact.

## Pairing and unchanged authority

Entry ABI is `droidloom-relay-entry-v3`; the init protocol is ABI3 / `P4IBV3!!`. Old ABI1/2 headers are rejected. The 128-byte frame, original 12 HELLO FDs, nonce, pidfd/credentials/namespace checks, and ABI2 detached socket PROJECT remain intact. The C DSO uses the same dependencies and exports. No private capability survives init release; holding view FDs are closed with the original HELLO ownership flow. No extra thread, process, new network operation, or execution entrance is introduced. Explicit finite CellSpec budgets and native PSI thresholds are unchanged. The normal None path has no new behavior.

## Actual local validation and limits

Seven local commands passed: strict build of the new holding controls, eight owned-directory/filesystem seam cases, strict build and seven existing projection/errno seam cases, ordinary transport and close-errno fixture compilation only, and the host DSO strict build. The initial local attempt called full collection and correctly failed ENOENT because this local environment lacks `/proc/self/ns/time` and `time_for_children`; the original failed source/result and the additive diagnosis are preserved. Production still requires all ten namespace FDs. The target/domain phase was extracted as one actual helper so ordinary file controls can exercise it without pretending the local namespace set is Android.

No new Rust control has executed locally. Two new Rust source tests cover exact leaf membership and final PID parsing. The old transport PASS belongs to older matching source; this source must run its own 20 transport, 20 close-errno, 7 projection and 8 holding controls on Pocket4, plus matching Rust tests. The repeated-mount kernel mechanism is a separate exact request under root review, not claimed here.

## Remaining qualification

A new actual init→broker enrollment→ACTIVE→Stop execution remains required. Original Owner08 failure/cleanup remains immutable. Boot-completed/property reinit, true native expiry after pressure relief, installed-hook deployment, and all app readiness remain open. Raw private journal records are not included. A new bounded init-specific log-capture plan remains separate; no global journal candidate is promoted by this source patch.
