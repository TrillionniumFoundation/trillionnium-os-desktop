# Opt-in component path projection (candidate)

Normal `kernel.sh` behavior is unchanged. This experimental entry builds the
unchanged pinned kernel from its actual checkout and projects compiler-origin
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
producer. Schema 5 requires its own exact-source cold builds, complete artifact
comparisons and real boots before current-kernel reproducibility is accepted.

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
`metadata --format-version 1` command used by the pinned component macro is
projected. Original and projected JSON, graph checks, component membership and
both source/mirror file identities are retained. All package-ID graph references
are mapped coherently, including a package located at the workspace root with a
`#name@version` fragment. Simple absolute paths without whitespace, URI escapes,
`=`, `#` or `@` are required. A virtual prefix containing `src/` or `tests/` is
rejected because the pinned runtime splits at the first such substring.

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
created. Native test binaries establish mechanism behavior only; the next full
kernel builds and QEMU boots must independently validate this schema.

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
as evidence of a second host. Until actual full kernel builds, byte comparison
and QEMU boots pass, a successful native tiny fixture proves only the adapter
mechanism. No cross-host, hardware or arbitrary-environment reproducibility is
claimed. The forced fresh target also avoids claiming incremental-cache
correctness for compiler environment overrides.

```sh
python3 -I support/build/repro/test_profile.py
python3 -I -O support/build/repro/test_profile.py
```
