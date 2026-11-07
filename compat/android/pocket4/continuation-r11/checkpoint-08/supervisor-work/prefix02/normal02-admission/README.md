# Fresh prefix02 normal admission — staged execution is separate

This is a new source-repair attempt after the original prefix01 read-only preflight failure. Neither request in this directory has been submitted. The original source05-01, plan01, first failure and exact-PID diagnostic remain unchanged.

## Actual matching input

Prefix02 matching-only job `1a1a8b6dd54-fc05-2f8b` finished with authoritative exit 0 and durable output. Its complete 10,261-byte receipt has SHA-256 `767207e9c5e86321a57a27f62126da6f18b95a758c5f025b8c44287af5165c76`. Six frozen inputs match before and after; 16 actor and 27 coordinator Python controls passed. The source freeze manifest is `714518452e90c313c99c34094bc24c6a03265d15fcff62321b39998912a8609b`.

The native probe remains the original source05-01 artifact: 21,752 bytes, SHA-256 `79b30f9fa4a1e7635ae4786a50372b3fcaa84ad619269476e40a1badd65c0e82`, device 66306, inode 34481448, root UID/GID and mode 0700. Matching02 held and revalidated that exact FD, source/native receipt, hash, mode, file capabilities and pathname before and after the controls. No new native build or native controls were run; the prior six native controls are referenced through original receipt `1e70d9df93309ff5be991f0a20e4b5b4493e57a0b64fcc3881075e652a5ae712`.

## Fixed new plan and read-only gate

The already-frozen `normal-plan.json` is exactly SHA-256 `cc003f5e6bbb54e1c8a8cd86a78a50b65ee7598ac37992f64b5f89a32923a41f`. Relative to failed plan01 only nonce and source paths/digest differ. The Main fence, every historical process identity, original daemon InvocationID, framework epoch, installed artifacts, tool pins and resource limits remain unchanged. Those historical values must still match live held identities; they do not authorize replacement or recovery.

Nonce: `d5ac0c8b6b3250e8ab02a33f1d04fe9ea64f3a32667325dff1827499ba77336a`. The resulting netns is `p4-relay-prefix-d5ac0c8b6b3250e8ab02a33f`; the unit is `p4-relay-prefix-d5ac0c8b6b3250e8ab02a33f-normal.service`. The leaf under `/home/alex/work/pocket4-relay-prefix-r11-owned` and both once-claim locations are new. No existing namespace, route, address, veth, service or Main configuration is changed.

The stage request retains the original root-private source05-02/source, source05-01/bin and common base directories, validates the exact actual matching report and six inputs, binds the reused probe to both actual receipts, then creates only `source05-02/normal-plan-02.json` with O_EXCL. It invokes the existing coordinator's `--check` path only, which reads the original Main fence, tool/source pins and target freshness. Success or original failure/traceback is retained in `source05-02/normal-plan-02-preflight.json`. The outer stage is limited to CPU 25%, memory 128 MiB, nice 10 and 90 seconds.

The fixed reader differs from the approved plan01 reader only in its literal PATH. Use it only after authoritative terminal/summary publication, with the externally observed exact report SHA. A readback is collection, not runtime qualification. Unknown transport results reconcile the original job/key; no new source or second plan write is authorized.

## Separate normal runtime gate

`execute-request.json` is concrete but NOT_SUBMITTED and not authorized by preparing this packet. It needs parent review plus the complete successful preflight receipt before any dispatch. Its fixed mode is normal and predecessor is null; it cannot dispatch owner-kill or controller-loss. The owned runtime unit remains CPU 100%, memory 256 MiB, swap zero, TasksMax 32, RuntimeMaxSec 60 and TimeoutStopSec 8. The outer Hepta controller remains CPU 25%, memory 128 MiB, nice 10 and 120 seconds. These are host-fixture budgets, not proposed Android production budgets.

A normal runtime pass would require actual complete ip netns exec → native unshare → declared C probe inheritance, exact 4-FD/PIDFD/namespace proof, bound InvocationID/MainPID/cgroup identity, retirement and owned netns/cgroup removal, and the unchanged Main/source fence. It would not qualify actual Rust Owner, Android init/barrier constructor, LMKD, apps or production activation. Runtime failure remains failure after cleanup.

Offline validation here parses Python and checks exact CFG/request/source/actual-receipt bindings. It executes no coordinator, namespace, network, service, Android operation or extra native control.
