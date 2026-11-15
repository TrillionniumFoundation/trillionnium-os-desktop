# Cold R9 source fixes

This packet repairs three source problems from the failed R9 disposable cold observation. It is a source candidate for a new owner-admitted generation. It does not change R9's failed result, certify a new boot, or grant production, Android, MAC, Ready or host-survival qualification.

## Finite JSON follow-up

The existing `unique_json` rejected the non-standard NaN and Infinity constants, but its default decimal-number conversion could produce a non-finite Python float. The helper now supplies a finite `parse_float` conversion and rejects values outside the finite float range. Normal finite float behavior, signed zero, underflow, exact integers, JSON strings and duplicate-field rejection stay unchanged. No framing, namespace, socket, policy, producer unit, guest source or controller entrypoint is changed by this follow-up.

The public packet at commit `627a7a2fa8b367c4ba226a93b04cdaae8bc35136` contained the exact same 361-byte `unique_json` function as the independently read R10 controller: SHA256 `2507842bfa0f822d08cd53ce54b08921a2025bdc909f8be0e41d8fd0480f7487`. The complete controllers are different: the original public candidate is 105,530 bytes / `7d05eb4df2af432231470482cba8e49461a85c08cf08c4d01da80006aa159596`, while the observed R10 controller is 104,551 bytes / `e1905e0d75467e3c08cd9e54303628b68586e37badaddd563c11d17e8ec73f51`. Only the helper's source identity is shared.

`finite-json-helper.patch` is the incremental helper-only patch against that previous public controller. `cold-source.patch` remains the complete original-fixture patch; its existing service and Rust sections are byte-for-byte unchanged. The candidate manifest now pins the updated controller and function while retaining the prior native validation with its original controller hash, explicitly marked as historical and not inherited by this change.

Run `python3 -I -B compat/android/pocket4/current-app-acceptance/r17-current-fixes/test_cold_json.py` for nine public unit tests. They execute only the `need` and `unique_json` helpers on short synthetic JSON and check the exact source scope and manifest. They do not replay the original UART, invoke the full parser, compile a guest or grant runtime qualification. The existing fifteen synthetic source controls remain separately runnable; their unchanged-helper assertion now excludes the deliberately strengthened JSON helper, whose stronger contract is covered by the new tests.

Canonical R21 records that the owner's R10 component and retirement passed on source head `6b4ff636e42f6e016f40e9941b09adfd1553c852`; the R10 root acceptance SHA256 is `2683c212b2c17d0244a05a5c12bc0110de980e3d53f8c2763e42e9ce7e4dae35`. R10 has zero Android starts and no production/runtime qualification. The latest source head is `b2a0e4eb9eea33fec219049975b413877fed3f59`, whose cold-component refresh remains pending. This numeric check is not established as a cause of an observed R10 failure, and its tests do not replace any current-head or production acceptance gate.

## Changes and evidence

1. **Keep systemd terminal queries off the raw COM2 record channel.** The observer unit now uses `StandardInput=null`, `StandardOutput=null` and `StandardError=null`, with every `TTY*` setting removed. In the exact systemd 259.9 sources, `exec_context_has_tty()` is true for a configured `tty_path` or terminal standard stream; `setup_term_environment()` can then call `query_term_for_tty()` and send a DCS terminfo request even when `TTYReset=no`. The existing observer first authenticates, requires NNP1, then opens and checks COM2 itself. Its stdout handoff is unchanged. Timeouts, cgroup kill policy and all other service settings remain unchanged. The raw parser still rejects DCS; it does not strip, decode or tolerate it.

2. **Check the original socket against the source-derived 0700 mode and report refused metadata.** The exact systemd 259.9 `bus_init_private()` binds the original private socket under `WITH_UMASK(0077)`, with no intervening chmod. The matched kernel source initializes the socket inode with 0777 permissions and applies the process umask to the pathname socket. This derives an expectation of 0700. **R9 did not emit the actual refused socket mode, so 0700 is not a retrospective claim about its measured mode.** An ordinary caller-owned AF_UNIX bind control separately observed 0700; it did not authenticate PID1. The guest emits the held nine-field node before the exact root:root, socket type, 0700 and link-count-one check. The new metadata has exactly four keys, is explicitly unauthenticated and records zero label mutations. The controller accepts it only at its fixed lifecycle position and requires its node to equal both the inode report and the eventual authenticated detail. Existing SO_PEERCRED, live SO_PEERPIDFD, SELinux/AppArmor, held ELF, private connection, deadline and post-authentication revalidation remain required.

3. **Compare stable nsfs object identity across exec.** Original R9 records have equal device, inode, mode, UID, GID, link count and size, but different mtime/ctime. The old full-record equality therefore rejects those records. The new helper retains and validates all nine uint64 fields, comparing the first seven only across the four fixed pre/post-exec nsfs observations. Namespace type/ID, path, label and the four exact EACCES controls still match. This change is limited to the cross-exec nsfs comparison; ordinary file identity, held-file checks and immediate guest revalidation keep their complete identity checks. The timestamp difference is observed evidence; no untraced kernel lifecycle is asserted as its cause.

`cold-BASE.json` records the exact original 11-file fixture, failed R9 result/stream hashes and matching primary-source hashes. The kernel source root's historical directory name was not used as version evidence: the actual release, configuration and bzImage were checked, and the image/configuration match R9's sealed inputs. This is an input binding, not a new reproducible kernel build.

## Packet layout and integration

- `systemd_cold.rs` and `p4-systemd-observe.service` are complete, exact final source files.
- `cold-source.patch` changes exactly the original `controller.py`, observer service and `src/systemd_cold.rs`. Apply it only to the complete original fixture whose file hashes match `cold-BASE.json`; then require every resulting full-file hash in `cold-CANDIDATE.json`. No fuzzy application or guessed base is qualified.
- `cold-controller-base.py` and `cold-controller-fragment.py` contain exact selected function slices, with per-function origin hashes. They omit deployment paths and the controller entrypoint. They are **not standalone controllers**. Full MAC/API validators called by the original parser are intentionally not stubbed or replaced. Do not substitute a fragment for the real controller.
- `cold-base-observe.service` is the exact original service for the public source comparison. The public test's namespace and socket records are explicitly synthetic and confer no authority.

The full native crate is the 11-file fixture pinned in `cold-BASE.json`, with the three changed files applied. `systemd_cold.rs` alone is not a standalone crate. The packet does not contain a built guest or a launchable sealed image. Before a new run, the owner must rebuild the exact guest, rebind the guest/source/image/policy/bundle inputs and authorize the new generation. The original controller's sealed bundle and namespace/lock guards cannot be reused as new-generation admission. No owner source, canonical CURRENT, lock, VM, live QMP session or deployment was changed by this work.

R9's actual sealed guest policy hash is `794f0839e5249818231d3759ba96f371842b3036099e146031adfec061abdca2`. The later R17 selected policy hash is `e30a63f7c4665a3a2a72495de18693cbcc4eca0c0e8c41e1ed1d0da244debf8b`. They are different inputs; no old A/B export or runtime qualification transfers between them.

## Validation boundaries

Run the self-contained public controls from any working directory:

```sh
python3 -I -B compat/android/pocket4/current-app-acceptance/r17-current-fixes/test_cold_source_fixes.py
```

These 15 data-only controls test exact public file pins, the unchanged raw framing loop, strict DCS rejection, stable nsfs comparison and its identity/type/label/uint64 negatives, socket metadata mode/type/owner/link/authentication negatives, and the service/guest ordering constraints. They never invoke a controller entrypoint, bind a socket, compile or run Rust, open QMP, or launch a VM. Their fixtures do not reproduce the original private stream and cannot produce an accepted whole cold-boot protocol.

Separate preserved native evidence records **17 Python controls and 11 Rust tests, all passed with no ignored Rust tests**. The Python controls used the exact original failed R9 bytes, actual pre/post namespace records and a real caller-owned AF_UNIX bind. The Rust suite contained eight original API tests plus three new metadata controls. Rust 1.93.0 compiled the actual complete crate offline and locked, with 21 dependency archives verified against Cargo.lock before bounded extraction. All 1,081 compiled inputs and original archives remained unchanged. The seven actual commands were reaped through their held PIDFDs; a later same-boot readback found the original supervisor, test runner and all seven command generations absent, with the original cgroup removed. CPU affinity was one logical CPU, CPUQuota 100%, MemoryMax 1 GiB, nice 15 and serial tests.

Original local AF_UNIX EPERM, the first native attempt's missing vendor-checksum assumption (zero commands/tests), and R9's failed observation remain recorded separately. The successful retry used whole locked `.crate` archives; no dependency lock or acceptance gate was relaxed. The public 15 controls, independent review's 16 pure controls and native 17+11 are distinct test sets and must not be added together as runtime evidence.

The raw framing limit, fixed lifecycle, full policy checks, fatal/critical-console checks, watchdogs, resource limits, original init, authentication and Ready gates are unchanged. A fresh owner-controlled cold run must still pass all of them before any corresponding runtime blocker can close.
