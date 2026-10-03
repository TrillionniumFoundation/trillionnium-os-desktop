# D2I integrated-image qualification

D2I composes the exact D1 image substrate and exact pinned Servo runtime in one
Q35/TCG image with no network device. The permanent workflow is read-only and
runs without path filters on every pull request to `main` and every exact
`main` push.

The qualification runtime is generated deterministically from a tracked base
source into the Servo checkout. The transformation is itself tracked,
digest-bound, fail-closed on source-shape drift, and never changes a Git ref.
It removes the unsound requirement that Servo must emit a pipeline-crash
callback after an externally delivered `SIGKILL`.

Crash causality instead requires all of the following on the same guest run:

- exactly one direct content-process PID/start-time identity before fault;
- successful `SIGKILL` delivery to that identity;
- exact disappearance of the old identity;
- a measured zero-content-process intermediate state;
- generation-two recovery with exactly one distinct replacement identity;
- a recovered content screenshot while trusted native chrome survives.

The guest also proves systemd PID 1, udev, D-Bus, logind, Weston headless
Wayland, one logical content surface, image-local bounded Servo input/IME,
popup and external-navigation denial, no non-loopback network device, and the
product AgentPort remaining disabled and absent. Native host input remains the
separate D0A-02 headed-host claim and is not silently promoted into an
OS-native D2I claim.

The image fixture must report its own completed document and focused input
before qualification input starts. The twelve original pointer, button,
wheel and keyboard events advance one step per native `about_to_wait` callback,
with at least 80 ms between steps and a Servo event-loop spin before the next
step. Each of the three distinct pointer moves also waits for its exact
`InputEventId` handled callback, so a slow script/rendering turn cannot merge
the moves into one pending input. The pointer positions remain inside the
fixture input field. The original floor of three handled events and the DOM,
three-event IME, popup, navigation and causal recovery requirements remain.

Replacement generation two obtains a new fixture readiness result and frame;
it resets input evidence and rejects callbacks from the retired `WebView`.
The same 90-second runtime deadline is checked before and after spinning Servo,
including pending readiness, DOM callbacks and process identity lookup. The
trusted-chrome recovery field is false before real recovery and becomes true
only after the replacement's current frame has actually been presented. Guest
and host acceptance both require this derived field and the three-event floor.

The host corpus compiles and executes the tracked sequencing module and the
generated JSON writer with repository Rust 1.93. It exercises readiness,
delayed acknowledgments, replacement isolation, deadline precedence and false
initial/unpainted recovery facts, plus deterministic transformation and source
drift refusal. These are source/process tests; only a fresh integrated QEMU
image run can establish the Wayland/Servo runtime result.

The D2I startup boundary also requires an actual `wayland-info` protocol round
trip under the renderer's UID and the same `XDG_RUNTIME_DIR` and
`WAYLAND_DISPLAY`. The bounded pre-start probe requires `wl_compositor`,
`wl_shm`, and `xdg_wm_base` globals and a successful client exit; a socket inode
or systemd's `Type=simple` started state does not establish this readiness.
Each client attempt has a two-second bound, its report has a 64 KiB bound, and
the runtime unit wraps the complete probe in a 22-second timeout. This proves
protocol availability only; the normal runtime must still prove every frame,
input, IME and causal recovery requirement above.

`trillionnium-d2i-acceptance.service` orders itself after the runtime with
`Wants`, so a failed runtime start still reaches the acceptance failure check.
D2I-specific compositor and runtime `OnFailure` edges activate one independent
root failure service. Acceptance failures request that same service rather
than independently shutting down during another capture. It stores bounded
runtime/compositor and acceptance journals, unit exit state, and the Weston
log in `/var/lib/trillionnium-d2i-diagnostics`, owned by root with mode 0700.
It reads Weston output after dropping to the renderer UID. Symlink or unsafe
directory/file custody is refused. The D2I-only runtime directory preservation
keeps volatile logs available until capture; the failure service synchronizes
the filesystem before requesting poweroff, and its stop hook also bounds a
failed/timed-out collector with a poweroff request. Missing causes remain
failed diagnostics, and never become a successful runtime receipt.

Successful root acceptance output and its runtime journal live separately in
`/var/lib/trillionnium-d2i-acceptance` with mode 0700. The renderer writes only
its existing runtime output under `/var/lib/trillionnium-d2i`; root does not
publish acceptance files into that renderer-owned directory. Host extraction
keeps the original receipt basenames and all normal verifier requirements.

Before the normal guest run, the permanent PR/main workflow executes the
explicit `boot-startup-negative` qualification lane. It copies the exact
prepared image, injects a runtime-only exit-73 fixture into that copy, and
binds a distinct negative pre-boot image digest. The original candidate digest
must remain unchanged. The actual QEMU guest must emit no D2I PASS marker,
persist the exact fixture cause and systemd runtime exit 73, keep each
diagnostic within its limit, and power off cleanly within 120 seconds. The
packet records source/run identities and both image identities, lives in a
separate startup-negative artifact, and explicitly denies normal runtime,
promotion and release qualification. After complete diagnostic readback and
post-boot digesting, the disposable negative clone is reclaimed before the
normal boot copy is allocated. The normal image contains no exit-73
override. Host text/command fixtures exercise refusal behavior; they are not
actual QEMU or installed evidence. Current-head CI must establish that lane.

Failed source head `3c3f20b918a44726b9ed8601462ada2c20d5b1d5`, tested as
synthetic merge `cc1530ba3bdf6ea0edfa209412341dbd2d81c373` in actual run
[37005677335](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/37005677335),
reported runtime exit 101, acceptance dependency failure, subsequent compositor
exit 1, and host QEMU timeout. Its diagnostics artifact contains the complete
serial log and explicit `debugfs` file-not-found records, but no runtime,
acceptance, or Weston journal/result. The earlier dependency suppressed the
acceptance failure trap and its diagnostic/poweroff work. Those facts establish
the missing diagnostic path; they do not identify which Rust panic or renderer
initialization caused exit 101. These source fixes need a fresh exact-head run.

The inherited D1 qualification binary classifies errors into a payload-free
`FailureCategory` enum before its logger, which accepts only that enum and emits
fixed category codes to operational stderr/journald. Underlying attestation identities, procfs
paths, socket paths, digests and I/O details are not forwarded into that sink.
Stdout receives only a fixed mode summary through another payload-free enum;
it receives no full identity/result JSON. The explicit `--output` qualification
file retains process identity and request facts with exclusive no-follow creation
and mode 0600. Host self-check collection uses this explicit file instead of
redirecting operational stdout. Server mode preserves actual attestation and
default-disabled/static-executable claim limits; its optional raw diagnostics
require explicit private output. A real Rust output-sink regression exercises sensitive
UID/GID mismatches, procfs errors, transport errors and socket-path mismatches.

The portable verifier independently requires typed true observed chrome
survival, exactly fifteen sent inputs (twelve ordinary and three IME composition
events) and at least three handled callbacks. Full
negative artifact fixtures rewrite the runtime and every affected boot/output
hash: missing fields, false claims, boolean/string/float counts and insufficient
counts still fail after complete digest rebinding. These verifier tests prove
validation behavior, not an actual guest runtime.

The verifier also rejects equal-valued floating-point identities inside the
pre-fault and recovery topology lists. Selected process, signal and topology
records have closed field sets; nested identity values retain exact integer
types. Runtime evidence must contain exactly three composition events, at least
two actual presented frames and a typed false simulated-recovery field. Guest
PID1, service, chrome, input and IME facts must agree with the accepted runtime;
its runtime and recovery screenshot digests bind the same downloaded bytes.
The receipt's claim and ceiling maps are closed and require exact boolean
values, so a rehashed packet cannot add release, hardware or AgentPort authority.
The nested D1 reader independently requires an integer source count, a closed
ceiling containing its six exact false booleans, and recursively typed equality
between receipt summaries and staged documents. Rehashing both receipt layers
cannot turn an integer into a float or a false ceiling into numeric zero,
remove a required ceiling, or attach an additional release claim.
The reader streams each archived file into Git's blob hash and reconstructs the
canonical directory tree from raw UTF-8 paths and tracked executable modes.
The rebuilt tree must match the declared tested Git tree; changing both the
source archive and every inner/outer manifest digest cannot retain a different
source object's tree identity. Fixture baseline trees come from the actual Git
CLI, independent of the reader's implementation. Paths are bounded to 4096
UTF-8 bytes and 128 components; links, conflicting paths and unsupported modes
remain refused without extracting the archive or executing its contents.
The full-fixture negative corpus rewrites every affected boot, guest and output
digest. Its results qualify the reader's refusals, never an actual QEMU boot or
production image. An actual downloaded image packet is verified separately.

Candidate run [37002984433](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/37002984433)
passed its actual integrated QEMU image workflow at source head
`bfe2664a52191ff6327e2cbd253ab02ce1527401`. Its earlier CodeQL stdout identity finding
still blocked that complete candidate. The enum logging boundary and stricter
portable verification are later source changes and need their own current-head
CI; neither inherits an earlier object's promotion or runtime authority.

A passing pull-request run is only a candidate. Promotion additionally requires
independent security review, protected `main`, reviewed merge, and a fresh
exact `refs/heads/main` run. D2I proves no BrowserActor, production AgentPort,
external effect, Secure Boot, hardware, signed update, or release readiness.
