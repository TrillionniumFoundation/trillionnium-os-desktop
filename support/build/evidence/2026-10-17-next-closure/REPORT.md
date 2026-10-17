# A01 next cloud closure — five actual QEMU guests

A01's current build, boot and SDK routing blockers are closed by actual source
builds and guest execution. This round contains **five new real QEMU guests**:
C4 reproduction, N2 ordinary boot, D1 TCP/GDB boot, OSTD and aster-core.
All five returned raw QEMU status33. Old A4 is a historical byte-comparison
input, not a sixth new guest. Cross-owner and environment gaps remain open in
[blockers.json](blockers.json). This is not all-project acceptance.

Branch: `agents/A01-asterinas-boot`; [PR22](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22)
targets main. Exact tested producer commits, selected unchanged runtime groups,
and final lock semantics are bound in [source-bridge.json](source-bridge.json).
Publication is frozen separately before this closure, without referring to its
own future commit or extrapolating the earlier CI snapshot to final-head green.

The fixed kernel remains complete Asterinas v0.19.0, original commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`; the derived kernel directory tree is
`6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. Rust remains
`nightly-2026-07-21`, full rustc commit
`87e5904f5eb6398af6b22eac2802c78934260c48`. No second kernel implementation
or owner runtime-core edit was introduced. Root README remains zero bytes.

The current cloud instance restored the pinned Rust/native tools into the
project's private prefixes from retained signed inputs. C4 then performed an
actual absent-target complete Rust kernel build and initramfs boot at historical
schema4 producer `4e8c7083575cec69efabe8d2250dfdd040c8dee8`: all eight controller
commands returned zero, live boot recheck passed, raw QEMU returned 33, no
timeout, and source/profile/code custody checks passed. Registry/toolchain
caches were reused; absent target does not mean all caches were cold.

The root independently compared all bytes of C4's actual loaded inputs with
the offline-verified reconstruction of prior A4 inputs. Complete ELF, initramfs,
and BIOS bytes are identical. ELF SHA256 is
`8c540288c6af2a1a97121031643c1af4c4db395d7e8b4082d6edc4604449849a`,
8,286,952 bytes. The observed instances have different hostnames/boot IDs
and host-kernel versions: old A4 `343e40cfefc1`, new C4 `24f0ea2620fe`.
This closes one concrete observed cross-instance reproduction attempt with the
same fixed source, toolchain and literal dependency/profile paths. Arbitrary
host reproducibility and an immutable whole environment remain open. Schema4's
own historical same-host receipt wording is retained as original evidence,
with the cross-instance comparison added separately.

The ordinary entry's global SDK mtime/root coupling is fixed in
`00a24cf5557d1b8e9663a19cc4961af81131d416`: every run owns an OSDK prefix,
uses locked installation with --root, and puts its bin before an explicit
shared Cargo-home bin entry. Real fixed Cargo tests exposed a parent-component
path counterexample; the final entry rejects those paths before work. Final
host executions are ordinary 40, -I 40, -I -O 40, supervisor -I 9 and schema4
profile -I 32: **161 host executions**, with no kernel/guest claim from them.
The old 38-test READY was withdrawn and preserved, together with its actual
counterexample and corrected independent reruns.

The downstream debug SDK identity regression is fixed in
`a5af45537dea32039ea172ad0d7e381400c07d95`. Its runner now observes only
the current boot/osdk/bin/cargo-osdk and verifies the installation receipt;
it records source directory/manifest/lock hashes and never falls back to global.
The complete debug host suite passed -I 16 and -I -O 16. Independent four-case
tests repeat a subset in both modes; old source fails all four expectations
and corrected source passes them. These are **32 additional host executions**,
separate from the 161 ordinary-entry executions. They validate the host mechanism. The separate real debug result below supplies
the actual TCP/GDB guest evidence.

Actual ordinary N2 source `0a7037fdde1e4c21884ea4f490ff28134082d0a2`
contains the private SDK code and merged main
`47288c4465720d125658b392efc655b333c90868`. Root session19957 completed
successfully: eleven controller subprocesses returned0, the absent-target
ordinary build emitted279 compilation lines, and its subsequent warm boot
emitted zero compilation lines and returned raw QEMU33. The full first-produced
and loaded kernel bytes are equal: 8,255,688 bytes, SHA256
`5c2cee2a8806baf873149ce07f752cc3b1c633efd4199e0c8c0ba20ef5f325f7`.
Original live boot/source rechecks passed and the worktree remained clean.
The two distinct private SDK installation paths/inodes contain equal complete
bytes: 8,560,432 bytes, SHA256
`94df3fd621055d9f99d3649c21a32d076448d68d8ea4b51d78c8b639a5d2adf0`.
Their binaries include the actual N2 source-root literal. The pre-existing
global SDK's SHA256 and stable-FD/path/stat observations remain unchanged at
`b5b92798bfcfb9416539fcaca3271cdc7017444affba26b34b7881d861171f2e`.
Its prelaunch binary payload was not retained, so no complete before/after
global byte comparison is claimed. The exact ordinary proof is in
`support/build/evidence/2026-10-17-private-sdk-native/REPORT.md`.

The genuine D1 TCP/GDB retry at source
`a5af45537dea32039ea172ad0d7e381400c07d95` completed root session67862
with exit0 and all six controller commands0. GDB read32 bytes of `__ostd_main`
at `0xffffffff88422740`; they matched both the full symbol ELF and loaded boot
ELF, then detach succeeded and the guest finished with raw33. The target was
reused and emitted177 actual compilation lines: this is not a cold or
zero-compilation replay. Boot ELF SHA256 is
`dfb30f188cc0b6b4fad8dc6f8bb75c4a77768cbb94bf19612b06a50a8116d23f`;
full symbol ELF is
`4e95684449b048413c7b89c003ac82f0e484819c629f74e3da23cba12d069af4`.
The initial attempt failed prepare because the controller requested a missing
private-prefix nm path, before SDK/kernel/VM launch; its original bytes and
correction to `/usr/bin/x86_64-linux-gnu-nm` remain preserved. Packaging's initial
missing boot-source control failure and corrected exact Git membership proof
are also retained. Neither failed attempt counts as a passed guest.

The isolated ktest producer
`ff0d09a2c2e0cba1d528d11a06083f588989a9f3` completed root session79302
with outer0 and all six controller commands0. OSTD reported221 passed, zero
failed, with three soft VMX/EPT skips and218 exercised lower bound. aster-core
reported141 passed, zero failed and zero soft skips. Combined acceptance is
**362 reported / 3 soft skips / 359 exercised lower bound**, with two actual
raw33 guests. The reused target emitted54 OSTD and83 core compilation lines;
no cold target claim is made. Each invocation installs its private mode700 SDK
with a locked root and executes the owned absolute binary directly. The legacy
`--skip-osdk-install` flag fails before output/lock. Eleven host mock cases in
each of -I and -I -O are a separate mechanism check; lifecycle fixtures were
not rerun in that phase. Sources and worktrees remained clean around execution.

The exact A04 rootfs tar and all four manifest-pinned ELF inputs were recovered
from retained Git bytes. All 17 rootfs manifest files match. USTAR SHA256 is
`df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797`;
manifest SHA256 is
`55aa8369d4f912267139ef7626c752814d7dc833e49accc337529f2545fb94cb`.
This closes missing exact inputs and supplies the guarded materializer under
`support/build/handoffs/a04-exact-rootfs/`. It executes no payload and does not
close Linux compatibility. MSG_CMSG_CLOEXEC and RLIMIT_NOFILE/EMFILE remain
the owner's previously observed guest gaps; this round does not rerun them.

Exact main47288 host ABI acceptance passed all **13/13** required runner checks:
ordinary/optimized Python 52 each, Rust 74 unit/integration plus one doctest,
12 compiled mutants killed/17 expected negative assertions, fmt, strict Clippy,
and bare no_std. This validates the codec's new bounded response-snapshot
method and its source-bound tests. It does not validate kernel ioctl/copyout,
CapSpace, scheduler budgets, persistent effects, G1 or G2.

Fresh owner metadata in round-next/owner-readback.json leaves A05 PR87 Draft
at `224fcdde44b9c68163298623fd908e3009b1b2a6`, A06 PR18 Draft at
`57b23ede7e242711ef142b672f04c896383a264a`, issue63 open with no comments,
and A04 PR8 Draft at `17558f66a8de10ed51ca2e193f567540168c15a7`.
This is metadata readback, not a new owner guest test. Main docs retain genuine
historical QueryAbi-only guest acceptance of A05's earlier source/ELF; that is
not native trusted CapSpace or five-operation enforcement at the latest head.

KVM/VMX, default host AF_UNIX, arbitrary-host/immutable reproduction, the
unidentified same-user workspace writer, A05 trusted control, A06 final runtime
debit issue63/full G1, and A07 unique persistent K↔D/G2 remain open. The A06
weak-reference lifetime issue is source-grounded and has not been demonstrated
as a QEMU quota-bypass exploit. A01 does not edit these owners' core sources.
No queued/in-progress CI or historical check is counted as final-head CI pass.

The [phase index](phase-index.json) covers all eleven new evidence phases and
the exact A04 input handoff. Its frozen original-verifier I and I-O receipts
are offline evidence checks, not more compiler or guest runs. Run
`python3 -I support/build/evidence/2026-10-17-next-closure/verify.py` or add
`-O`; optional `--repo .` also checks the current selected source bytes and
final lock. Default verification uses saved proofs and lock data, so future
main metadata changes do not rewrite this historical acceptance.

The unknown writer remains unattributed. After quarantine inode1837852, the
same untracked, unexecuted10894-byte draft reappeared with inodes1859916 and
1859937, all SHA256
`ace2be2bc19503611f1bc87fd3b9a402c3f92d0ae3f514972d55a429babeae7e`.
The v1 diagnostic compared atime and could report its own read as mutation;
its correction is retained. The v2 observation recorded MOVED_FROM and no
reappearance for12 seconds; a later04:39 snapshot still found it absent.
These bounded observations do not identify the writer or establish permanent
prevention. N2/K isolated source worktrees contained no draft. Earlier wording
that no code existed was corrected: an untracked, unexecuted draft did exist.

The original publisher commit message for N2 mistakenly described the two ELF
copies as distinct without byte equality. [The preserved erratum](raw/publication/publisher-commit-message-erratum.json)
corrects that sentence: first and loaded kernel copies are fully byte-identical
at SHA5c2cee…, and SHA94df… identifies cargo-osdk. The native phase and payloads
were correct throughout; no amend, force push or original phase edit was used.
C4's retained content-addressed snapshots likewise do not attest immutable
custody of previously executed SDK bytes or the whole environment.
