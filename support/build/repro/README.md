# Opt-in component path projection

Normal `kernel.sh` behavior is unchanged. This opt-in entry builds the kernel
from its actual checkout and projects compiler-origin
paths and the pinned component macro's Cargo metadata into one virtual prefix.
The source files remain at distinct real checkout paths. The virtual directory
contains only the exact `Components.toml` input, never a second kernel source.

Schema 5 also binds the current project's one approved outside-kernel package,
`libs/os-control`. The kernel workspace dependency must resolve to that exact
same-checkout directory and identify package `os-control`. Its manifest, all
regular crate files (apart from real `target/` build output), and executable
modes contribute to a stable source digest. Relative names and content hashes
enter the reusable profile owner; actual paths and file/directory identities
remain separate in each run's policy. Those identities are checked when the
package is compiled, during component metadata projection and after the run.
Changed inputs require a new profile. These are observed source snapshots,
not an atomic compiler-time or privileged-adversary immutability guarantee.

Only two source-prefix maps are allowed: `kernel/asterinas` to
`virtual-asterinas`, and `libs/os-control` to the separate sibling
`virtual-os-control`. No source files or virtual crate are copied to the second
location. The separate prefix preserves the pinned Components macro's original
workspace membership test. Only the exact os-control manifest receives this
additional canonical identity; nested packages and any other actual compiler
unit inside the project checkout are refused. Registry and toolchain packages
outside the checkout retain their original Cargo metadata identities.
Metadata-only dev-dependency declarations such as `libs/os-abi` and os-control's
external test source paths remain untouched; they do not authorize compiling
an additional project package. Full codegen arguments and successful `--extern`
producer checks continue to apply to the added package and its kernel consumers.

Historical schema-4 byte-equality results belong to their original source
producer. Schema 5 now has its own exact-source cold builds, complete artifact
comparisons and real boots for the producer and prepared host recorded below.

## Verified schema-5 cold builds (2026-10-20)

Two clean, separate worktrees, `repro-c` and `repro-d`, used producer
`684c4c82bbe770d712da75a199b7f5757ee61191` and tree
`8dde0a4beb98f6749a529624aeb1d0b7c0f13a98`. Each began with absent kernel and
OSDK targets and a new run output. C created `repro5-profile-684`; D reused that
same owned, locked profile after C completed. Both rebuilt OSDK and the Rust
kernel with `nightly-2026-07-21` and ran `kernel.sh run_kernel` through this
launcher. Both commands exited 0; both actual QEMU processes exited raw 33,
without a timeout, and emitted the real initramfs `TRILLIONNIUM_A01_BOOT_OK`
marker. The elapsed cold runs were 439.446 seconds (C) and 473.830 seconds (D).

The independent audit read and compared the complete frozen files loaded by
QEMU, including every ELF section. All three pairs were byte-for-byte equal:

| Actual QEMU input | Bytes in each run | SHA256 in both runs |
| --- | ---: | --- |
| Kernel ELF | 8,410,560 | `00f3bfb76164fac3890c68115f5347e758820aeeffd42bb9021261900acca508` |
| Initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

Each run completed 340 actual Cargo compiler units, with 500 successful
`--extern` producer bindings and six exact locked Cargo metadata projections,
each checking 19 Components. Canonical local and unchanged external Cargo unit
identities matched across the two checkouts, including the actual
`libs/os-control` unit. Independent before/after inventories verified 3,131
present tracked files against Git bytes and executable/symlink modes, with no
source changes. Both executions used q35, TCG, `max`, one vCPU, 512 MiB and the
same fixed device configuration. Their real serial logs are separately retained;
serial timestamps need not be byte-identical.

The [published evidence report](../evidence/2026-10-20-blocker-closure/REPORT.md)
binds the logical runs `repro5-run-c` and `repro5-run-d`, their outer receipts,
and the retained original `completed-runs-684-audit.json`. Actual private
storage paths are retained separately. The independent report passed
855 checks and has SHA256
`4f4cf8697ec13a7f16fe676c12751356a735a20972e661e9085aa547f5221721`.
This establishes full-artifact repeatability for these two cold targets on one
prepared host using the selected profile and dependency inputs. Cross-host,
hardware and arbitrary-environment reproducibility remain unverified.

## Running the selected profile

```sh
python3 -I support/build/repro/run.py \
  --checkout /absolute/clean-project-worktree \
  --profile-root /absolute/new-owned-profile \
  --output /absolute/new-run-output
```

Use two isolated exact-source worktrees, an absent `kernel/asterinas/target` in
each, the same profile root and separate new output paths. Do not run another
builder in either proof worktree. The launcher acquires the existing kernel
workspace lock before creating a profile or output directory, then holds both
locks through command-group cleanup and result capture. The kernel worker
inherits the same locked open file description. Target absence is checked
again under that lease. Busy calls leave profile/output paths free for retry.
The caller prepares the fixed nightly, Cargo cache and vDSO in the usual way.
The profile rejects inherited Rust flags/wrappers and fixes timestamp, locale,
target path, compiler remap and explicitly selected embedded builder metadata.

`RUSTC_WRAPPER` retains the original OSDK codegen arguments, appends the canonical
`--remap-path-prefix` unless that identical flag is already present (before an
explicit `--` delimiter), and supplies the
metadata adapter through `CARGO` while compiling proc macros. Only the exact
`metadata --locked --format-version 1` command used by the current fixed component
macro is projected, and `--locked` is passed unchanged to the real Cargo. Original
and projected JSON, the executed argv, graph checks, component membership and
both source/mirror file identities are retained. All package-ID graph references
are mapped coherently, including a package located at the workspace root with a
`#name@version` fragment. Simple absolute paths without whitespace, URI escapes,
`=`, `#` or `@` are required. A virtual prefix containing `src/` or `tests/` is
rejected because the pinned runtime splits at the first such substring.

A successful launcher result additionally requires at least one complete metadata
projection with a configured workspace component. The launcher recomputes the
full projection and membership from the retained original JSON, verifies exact
mapped bytes and command/source/mirror binding, and rejects missing, partial,
refused or altered receipts. A cold schema-5 attempt at producer `cc8b72a` retained
an older unlocked-only command whitelist: the new `--locked` invocation bypassed
projection, leaving no metadata receipts and causing a real guest
`NotIncludeAllComponent` panic (QEMU raw 65). Its `repro5-attempt-a` and
`repro5-run-a` artifacts remain failed evidence; neither C nor D reused those
outputs or targets. This helper fix requires a fresh profile through its changed code hash;
it does not change the kernel macro or relax Components validation.

The compiler map is enforced in the wrapper, rather than relying on inherited
`RUSTFLAGS`. The pinned OSDK CLI appends environment flags to global `config.build`
after action configs were constructed, while kernel building reads
`config.run.build`. A real first kernel attempt compiled successfully but booted
into `NotIncludeAllComponent` because metadata keys were projected and the
actual kernel compiler arguments had no remap. That failure is retained. The
wrapper records both incoming and effective compiler arguments; `argv` denotes
the vector actually executed. Required OSDK flags remain in their original
order. An already present identical combined option is reused; an equivalent
split option is retained and may be followed by the identical combined form. New code hashes require a new profile directory and fresh targets; old
failed profiles and artifacts are never reused as passing evidence.

Two real schema-2 kernels subsequently booted, but their ELF bytes differed.
OSDK creates an independent run-base workspace whose external path dependencies
receive absolute-path-dependent Cargo `-Cmetadata` salts. Compiler path remapping
does not normalize those crate disambiguators. Schema 3 additionally replaces
only the metadata salt for Cargo packages inside this source root. Cargo's
`-Cextra-filename`, output names and real `--extern` paths remain untouched.
Registry and toolchain crates retain their original metadata salts.

The first full schema-3 build failed before QEMU: a library consumer started
before its dependency's successful producer receipt was recorded. Metadata
pipelining is supported as the explanation by the controlled actual-Cargo
experiment. The retained A3 logs do not provide a code-generation phase clock;
the controlled experiment delays wrapper completion after real rustc exits.
The strict producer gate rejected the producer without a completed receipt.
Cargo's `build.pipelining=false` option is
deprecated and ignored. Schema 4 therefore fixes `CARGO_BUILD_JOBS=1` only in
this opt-in launcher, recording both the caller's value and actual selected
value in `policy.json`. The public kernel entry inherits that value; normal
build defaults are unchanged. A controlled actual-Cargo metadata-ready/delayed
producer experiment fails with two jobs, still fails with the deprecated
disable setting, and builds/runs successfully with one job. No producer check
is relaxed and no wait-on-producer loop is introduced.

Each replacement is a SHA256 of the canonical package name, version, manifest
path and parsed manifest (only dependency/workspace path prefixes are projected),
crate name/type, target, working directory, fixed compiler version identity and
the full argument vector. Features, cfgs and every behavior/codegen option,
including unknown future options, participate. The original opaque metadata,
extra filename, output directory and incremental cache location are excluded
from that descriptor; incremental compilation remains disabled. Explicit
`--extern` arguments bind to the canonical identity of one successful producer.
The only permitted implicit extern is `proc_macro`, bound to the recorded fixed
`rustc -vV` identity. No artifact filename hash is guessed or removed to infer a
dependency identity. Only Cargo's observed `-C metadata=...` and `-Cmetadata=...`
spellings are supported; metadata aliases or duplicate salts are refused.

The compiler helper supervises rustc and preserves inherited Cargo jobserver
file descriptors. Its separately locked `compiler-units.jsonl` ledger records
start reservations, completion status and artifact stat observations. A failed,
unfinished, ambiguous or stat-changed producer cannot satisfy a dependency.
Artifact observations bind device/inode/size/mtime, not a content-hash or
privileged-adversary immutability promise. Different incoming Cargo salts mapping
to one local descriptor in the same build are refused; repeated identical units
are allowed. `rustc.jsonl` retains one original/effective invocation record with
the descriptor and both metadata salts.

This is a pinned graph profile. Local `OUT_DIR` inputs and Cargo build-script
artifact paths are explicitly refused, because their generated directory salts
would need additional producer/content normalization. Neither occurred in the
actual schema-2 kernel compiler arguments. Arbitrary source `env!` inputs and
custom environment-driven code generation are not normalized. Compiler path
projection recognizes path prefixes and path-valued `=` arguments, leaving
neighboring directories and arbitrary quoted cfg strings distinct. Source
checkout paths remain genuinely different; no common staging source tree is
created. Native test binaries establish mechanism behavior only; the completed
full schema-5 kernel builds and real boots above validate the selected producer
and prepared-host scope separately.

The complete metadata root is projected along with package IDs. Changing only
package IDs can bypass the upstream missing-component check and is forbidden.
The adapter checks that every component has identical workspace membership
before and after projection, and enforces the original Components membership
rule before returning the projected view. Runtime matching and priority source
are unchanged; registration path keys receive the same path normalization as
compiler `file!()` data.

The first use exclusively creates an owned profile. Later uses require its exact
marker, code hashes and Components hash. Existing foreign files/directories are
never overwritten or deleted. The lock inode remains stable. Snapshots before
and after the build detect pathname/entry replacement, even if an old entry was
later restored. The profile is retained for inspection, with no cleanup unlink
that could remove a foreign replacement. This is a cooperative build profile,
not a boundary against a privileged actor changing the host during compilation.
The profile also exclusively materializes the exact three-file compiler-helper
closure with executable wrapper modes and verifies every byte against the source
hashes. Both builds execute that same retained closure. This makes runtime
execution independent of worktree permission restoration, while the Git wrapper
entries remain executable. Helper bytes and modes are included in custody checks.

`policy.json` separately records actual host username/nodename/UID and the chosen
embedded build identity. The latter is labelled build metadata and never used
as evidence of a second host. The two full kernel builds, complete byte
comparison and real QEMU boots above ran on one actual host. A successful native
tiny fixture alone proves only the adapter mechanism. Cross-host, hardware and
arbitrary-environment reproducibility remain unverified. The forced fresh target
also avoids claiming incremental-cache
correctness for compiler environment overrides.

```sh
python3 -I support/build/repro/test_profile.py
python3 -I -O support/build/repro/test_profile.py
```
