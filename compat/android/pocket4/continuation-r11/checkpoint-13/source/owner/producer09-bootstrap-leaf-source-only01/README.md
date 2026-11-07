# Source-only bootstrap leaf layout candidate

This is an independent cgroup-v2 layout repair, not a claim to resolve the Owner08 journal mount EBUSY candidate. No new Rust compiler, host controls, device operation, Android or deployment has run for these three files. The paired holding-view repair is separate work.

The host creates one root-owned `init-bootstrap` leaf under the exact finite Android domain. Entry still joins the Android root first; existing CPU preparation then seals CLONE_NEWCGROUP at that root. Only after the mounted namespace root is checked does entry migrate itself with `0` into the precreated leaf. The root's local cgroup.procs must then be empty and the leaf must contain exactly init, while recursive populated/pids.current remain nonzero. No controller is enabled beneath the populated leaf and no finite budget changes.

Projection gains a permanent one-attempt state. Configure-init rejects missing/repeated projection, and its final pre-exec callback rechecks membership after CPU callbacks using fixed buffers and descriptor syscalls. Host Hello validation repeats the proof with the actual held init pidfd/parent/birth identity and host PID view. These exact membership checks apply before release, not to the ongoing Android runtime. Original whole-tree retirement/empty-descendant removal is retained.

Two Rust unit controls cover membership and final PID parsing. They are source only and require matching Cargo compilation/execution; no inherited test PASS is claimed. All original authority, process namespace, source artifacts, nonce, pressure policy and outer-domain limits remain in place.
