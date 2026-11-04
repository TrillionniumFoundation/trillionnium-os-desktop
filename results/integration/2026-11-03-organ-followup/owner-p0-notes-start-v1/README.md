# Installed fd/a39: first original Notes startup stopped before composition

The installed original Root was actually started, but returned exit 1 before
creating the Session, protected authority or any Notes request. This is a
retained startup failure, not a Notes effect or recovery result.

| Identity or observation | Actual value |
| --- | --- |
| Desktop / Hepta | `fd8d56c52b971c2d5d0e6430f296803b43ef60a3` / `a39a0871d9601ffccb5e0d95d8f39d54b3a63360` |
| Installed release | `/opt/trill-organ-20261103/releases/fd8d56c52b97-053cc1957b40` |
| One durable job | `1a1a3519eb3-96a-766e`, key `organ-owner-notes-live-fd-a39-v1-20261103` |
| Original Root command | `hepta-desktop-root initialize --config /root/trill-organ-owner-20261103/initialize.json` |
| Fresh isolated state | `/var/lib/trill/o1103n1`, private mount namespace, unchanged 300,000 ms input |
| Root / process result | Exit 1 / failed exit 1; no process timeout; complete retained output |
| Observed Root duration | 13,085 ms |
| Original Root stderr | `Error: "actual child did not exit within its bound"` |
| GUI write prompts | Zero |
| Effect, App-only readback, same-boot recovery, production | All unqualified |

The [original preparation](notes-prepare-v1-result.json) selected the actual
active local UID 1000 Wayland logind session, opened its real display and
checked the AT-SPI API. The Xauthority record contains metadata only, not
cookie bytes. The new private Root inputs and ordinary private-mount probe
passed. Preparation had not created an authority or sent a model turn.

The [actual run](notes-live-v1-result.json) reached only the
`initializing_original_root` phase. Its requested Notes text describes the
intended isolated acceptance task; the original GUI helper was never called.
The [authoritative process result](notes-live-v1-terminal-status.json) is
failed, exit 1, with complete 354-byte stdout and empty stderr. Root has its
own separate 52-byte stderr and empty stdout. A later inactive systemd unit's
`ExecMainStatus=0` is not a successful result for that failed process.

The [read-only postmortem](notes-live-v1-postmortem.json) found only the
original inputs and empty seed stdout/stderr in `admin/`. The completed thread
seed receipt, Session output, actual composition, human-provider receipt and
actual-artifact record were absent. No authority state directory or Session
socket existed, and the original Root process was gone. The original job unit
was inactive with no main PID or control group. The observer's namespace had
no prefix mount; it was not the departed private namespace, so this is not a
direct reinspection of that namespace.

In the frozen [seed implementation](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/fd8d56c52b971c2d5d0e6430f296803b43ef60a3/services/hepta-session-host/src/product_root/seed.rs),
the successful original Start/Resume is followed by client shutdown and
`ChildOwner::terminate` before the seed receipt is published. The
[original child owner](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/fd8d56c52b971c2d5d0e6430f296803b43ef60a3/services/hepta-session-host/src/product_root/process.rs)
reports this exact error when its held child has not exited within its fixed
bound. Those source locations and the absent later artifacts identify the
failed stage. The empty server logs do not establish a unique internal cause.
Subsequent signal-listener and drain analysis remains a separate source review
until a repaired actual seed lifecycle has its own result.

The failed prefix was preserved. The controller did not send a new Root or
Agentd signal, repair authority records, initialize a replacement into this
prefix or retry a possible effect. The original child owner's own Drop cleanup
is part of the frozen source; this run did not create an independent retained
seed-pidfd trace. No recovery phase or new user task was inferred from cleanup.

## Retained bytes and limits

The [original transfer index](source-index.json) and
[independent review](independent-review.json) cover 15 original files totaling
76,684 bytes. Every size and SHA-256 was independently checked. The exact
process request contains the same runner and GUI bytes retained here, the
complete job output matches the terminal metadata, and its reported result
digest matches the actual result file. Original files and false flags remain
unchanged. These scripts and their planned later phases are retained evidence,
not a reusable instruction to rerun the already attempted prefix.

The previous [optimized build, original tests and installation](../owner-p0-fd-v5/README.md)
remain successful within their own scope. This new execution closes the
unknown startup observation with a real failure; authenticated submission,
the Notes effect, independent application readback, durable terminal and
disconnect/restart reconciliation remain open.
