# Camera2 release08 controlled update

This directory is a source candidate for root-agent review. It has not installed
an APK or performed device UI actions. `camera_transaction.py` defaults to an
inert plan. The separate Camera acceptance script consumes its `CameraSession`
and `ui_lock` interfaces.

## Fixed target and inputs

- Package: `com.android.camera2`, Android user 0, UID 10062, versionCode 20002000.
- Main host PID 3588089; init PID 3588093, birth ticks 80797014.
- Framework epoch SHA-256:
  `48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f`.
- Candidate: `/home/alex/work/pocket4-camera-release08-20261105-r12/signed-build-01/Camera2-pocket4-checked-disconnect.apk`.
- Candidate SHA-256:
  `0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e`.
- Required current release07 SHA-256:
  `0f6fb58ea0b81be5f588ee35796d35e4de65d19e866a51ea0e4ac79b26012c4e`.
- Both APKs: 11892407 bytes; v3 signer SHA-256
  `a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc`.
- Transaction directory: `/home/alex/work/pocket4-camera-release08-20261105-r12/install-01`.

The nonblocking existing UI action lock is acquired before creating the fixed,
exclusive transaction directory. A busy lock consumes no transaction. A second
invocation after the directory exists cannot dispatch an update. The provider
owner lock and provider service are never modified.

## Update and terminal states

The script checks the fixed Main epoch and executable/source pins, acquires the
already qualified held-root and six-namespace transport, and retains that exact
init generation. Each Android command uses held descriptors rather than a new
numeric-PID namespace entry. One initial read-only discovery obtains the Android
environment; every later helper discovery is rebound to the held generation.

Before updating, the actual active APK is read through that root and copied to
`release07-before.apk`. The source APK and this backup must have the exact pinned
hashes, matching certificate, and 1045 byte-identical non-dex entries. A current
Camera task causes refusal before installation. No task is closed by this script.

Native CLI calls run through `runuser -u alex` and the fixed daemon socket. The
CLI's `--user 0` selects the Android user, not the host cell. Separate `status`
calls must identify running cell u1000 and the fixed host PID. Installation uses
one standalone APK update through `droidloomctl install`; it never uninstalls,
clears data, grants permissions, restarts Main, or touches training/provider
processes.

`INSTALLED_VERIFIED` requires a joined rc=0 command with JSON `ok=true`, a matching
`host_pid` if the response includes it, exact installed release08 readback, equal
UID/version/first-install time/CE and DE directory identities/runtime permissions,
and final fixed-Main/caller checks. These checks prove data identity preservation;
they do not hash all application database contents or qualify Camera functionality.

A missing, failed, or timed-out response remains `INSTALL_OUTCOME_UNKNOWN` even
when the new APK is visible. It is never retried or automatically rolled back.
`--mode reconcile` only records current installed bytes and data identity, without
rewriting the original daemon outcome. Command timeout stops only the command's
new process group and joins its leader; daemon/Binder work is still unknown.

A known completed update whose exact release08 is present but whose data identity
differs permits one rollback to the exact saved release07; both the response and
readback must verify. A different current APK is not overwritten. After successful
installation, separately reviewed acceptance failure can use `--mode rollback
--execute`; it requires the original verified update, exact current release08 and
unchanged data identity, and permits one create-only rollback transaction.

## Invocation

Review `SOURCE_MANIFEST.json` and keep the source and `references` directory
together at the reviewed destination. Invoke with `/usr/bin/python3 -I`:

```text
camera_transaction.py --mode plan
camera_transaction.py --mode install --execute
camera_transaction.py --mode reconcile
camera_transaction.py --mode rollback --execute
```

Only root executes the last three modes. `plan` performs no remote operations.
Installation and rollback require the explicit execution flag. Do not manually
delete an attempt directory to permit another dispatch; reconcile the original
attempt and review any next action.

## Shared acceptance interface

```python
with ui_lock(), CameraSession(fresh_journal_directory) as session:
    session.guard()
    snapshot = session.snapshot('before')
    raw_bytes = session.android(['/system/bin/cmd', 'activity', 'stack', 'list'])
```

`run_host(label, argv, timeout=20, pass_fds=())` returns command metadata and binary
`stdout`/`stderr`. It does not raise for nonzero exit status; callers must inspect
that status. Labels use `[a-z0-9-]+`; an internal sequence prevents log-name reuse.
Output readback is bounded to 32 MiB stdout and 1 MiB stderr. This is a readback
bound, not a live disk-size limit. `android()` raises on timeout or nonzero status.
Use `target.read_file()` for a bounded new JPEG read and guard before/after it.
`helper.arun` and `helper.discover` are privately rebound; the installed helper
source is unchanged. Native UI launch must also use `ALEX_PREFIX`.

## Local verification and remaining device work

Twelve offline tests passed. They exercise actual dispatch count under response
loss, absent ACK, data mismatch, wrong APK, repeated invocation, busy action lock,
final identity failure, and exact preimage rollback. The timeout test creates a
real local child and uses a private inherited pipe to prove the command group's
holders exited. These tests do not contact Pocket4. The active-versus-hidden
package parser test is a synthetic fixture; a device format mismatch fails before
installation. Compilation and the inert plan also passed.

Device installation, photo capture, persistence, crash monitoring, and whole-app
production qualification remain separate runtime work. No offline test result
is represented as a successful device installation or Camera acceptance.
