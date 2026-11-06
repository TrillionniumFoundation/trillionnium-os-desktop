# Explicit namespace-identity comparison, revision 2

This is a new candidate. The frozen `host-stage-candidate-r1/` source and its actual failed host verification are retained unchanged. This candidate has not itself run on Pocket4, qualified a live task, or published a reconciliation.

## Actual failure and exact difference

The first host-only verifier, job `1a1b1df441d-fc05-7b41`, staged its source closure and closed its staging descriptors, then rejected the later inspection at `EXACT_HELD_R5_RUNTIME_APP_CLASSPATH_BINDING`. It did not enter Main, acquire a Main/Flow lock, or publish a reconciliation.

An independent host-only reader, job `1a1b1e2aaa2-fc05-7b54`, fully verified the same private bundle (1,218,042 bytes, SHA-256 `3c72bc43b2a32950a576405049b12cf6984ef790978638122ef2a7d4602941c8`). It decoded only the two held-binding rows, retained their original bytes, and found exactly five differences. The complete result is retained as `../actual-binding-diff-r1/stdout.raw.json` (2,294 bytes, SHA-256 `e62b639aa1dc226c27594479a594c8c8188b4ccc60d5bd752396dd399f02e601`). Its durable terminal succeeded with exit 0; all process descriptor identities were unchanged.

| Original binding | Bytes | SHA-256 |
| --- | ---: | --- |
| `steps/close-entry-popup-01/held-main-binding.json` | 55,032 | `dff8daff868d71e3389ee69bfb67b414bd67798f7312bcc01727c8074f3ba1bb` |
| `steps/inspect-after-close-02/held-main-binding.json` | 55,032 | `7529be9b82f289e197bef7071f28f9e734d9c77251d6f1a7e2912635dc85ffd9` |

Both original byte files are retained on the host under `/home/alex/work/pocket4-beike-held-binding-diff-20261106-r1/`, as `binding-00.original.json` and `binding-01.original.json`. They are also still present as original-byte rows in the unchanged private bundle. No original is reserialized or replaced.

| Exact path | Action observation | Later inspection observation |
| --- | ---: | ---: |
| `/classpath/zygote_mount_namespace/mtime_ns` | 1793983336230360940 | 1793984232364095317 |
| `/target/namespaces/cgroup/mtime_ns` | 1793983335936277591 | 1793984232119089854 |
| `/target/namespaces/ipc/mtime_ns` | 1793983335936277591 | 1793984232119089854 |
| `/target/namespaces/pid/mtime_ns` | 1793983335936277591 | 1793984232118089832 |
| `/target/namespaces/uts/mtime_ns` | 1793983335936277591 | 1793984232119089854 |

Every other field was exactly equal. The result proves this difference; it does not claim why the kernel assigned these observation timestamps.

## The frozen R5 contract

Sources are the actual deterministic reconstruction of the installed recorder closure, under `../../reconstructed/source-generation-r2/recorder/`. Their bytes match the real recorder manifest.

| Source and fixed SHA-256 | Relevant contract |
| --- | --- |
| `references/held_runtime_r5.py`, `72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4` | `fd_record` lines 41–45 records eight stat fields, including mtime. `HeldTarget.__init__` lines 131–155 admits exactly six namespace FDs: each must pass `NS_GET_NSTYPE` (`0xb703`) and match the corresponding held process namespace-link inode. |
| Same `held_runtime_r5.py` | `_verify_proc` / `verify`, lines 170–189, require the original live pidfd and exact process identity: PID, start ticks, UIDs, namespace PIDs, parent PID, all six namespace links, executable and cgroup. Root device/inode are rechecked. Namespace mtime is not an identity condition. |
| Same `held_runtime_r5.py` | `HeldZygoteRoot`, lines 341–356 and 373–387, admits a fixed zygote generation, PID/mount namespace links, mount FD type and inode, then rechecks its pidfd, complete process identity and root device/inode. |
| `main_binding.py`, `b7f7350f45e7c6764a6d101785dfda5febc43b679999a308718aa3534bd5eee4` | `main_classpaths`, lines 29–68, binds the zygote to the same init PID namespace and retains two specifically named mount-namespace FD records. Classpath files retain their paired held-root identity, metadata and streaming hashes. `MainBinding`, lines 125–173, retains process/App identity and rechecks package UID and CE/DE directory identity. |

No frozen R5, recorder, helper, runtime guard, classpath logic, or existing reconciliation branch is edited.

## The exact comparison change

The new pure function makes a copy and projects `mtime_ns` only from these closed, provenance-checked namespace-FD locations:

- `/target/namespaces/{mnt,pid,uts,ipc,net,cgroup}`
- `/classpath/command_mount_namespace`
- `/classpath/zygote_mount_namespace`

It requires the exact pinned R5 source identity and schema; exact namespace record field sets; integer fields; regular-file metadata; positive inode/link count; matching typed process namespace-link syntax and inode; matching init/zygote PID namespace; and matching command-mount/init-mount identity. It then requires the entire remaining binding dictionaries to be exactly equal. Namespace device, inode, mode, owner, size and link count remain exact. All other fields, including process start identity and every ordinary file, root, classpath, APK and App-data timestamp, remain exact.

The comparison does not acquire a namespace or itself prove an ioctl. Admission by `NS_GET_NSTYPE` is attributable to the fixed R5 producer; the later live publisher must still execute the original fresh held-R5 acquisition and guards. No unknown epoch or namespace is adopted.

The same function is used for each recorded step against its expected binding, for the action/observer pair, and, in live mode, for each original step against the new binding from the current R5 acquisition. The new proof retains all eight original observation-time pairs, the five actual differences, and both original held-binding file hashes. The canonical identity-projection hash is explicitly labelled and is not represented as a raw-file hash.

## Validation and next gate

`test_namespace_identity.py` ran four focused local control groups with exit 0 and unchanged complete process FD identities. The controlled binding fixture is synthetic; only the five timestamp pairs come verbatim from the actual diff. These controls verify inode/device/type/start changes reject, ordinary file/root/APK/data mtime changes reject, unknown namespace sites/fields/provenance reject, and original objects remain unchanged.

The remaining concrete gate is a new host-only verification of the unchanged private 177-file bundle, including every original raw helper assessment, command/transport record, execution envelope, and unique visible nonpassword home postcondition. The exact new packet is generated under `../host-stage-candidate-r2/`. It can only invoke `--verify-host-only`; it cannot publish a reconciliation. A successful host-only result would still require separate review and fresh held runtime/App/helper/task/foreground checks before the new producer may publish its new-decision envelope. The original action remains UNKNOWN throughout.
