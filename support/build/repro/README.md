# Opt-in component path projection (candidate)

Normal `kernel.sh` behavior is unchanged. This experimental entry builds the
unchanged pinned kernel from its actual checkout and projects compiler-origin
paths and the pinned component macro's Cargo metadata into one virtual prefix.
The source files remain at distinct real checkout paths. The virtual directory
contains only the exact `Components.toml` input, never a second kernel source.

```sh
python3 -I support/build/repro/run.py \
  --checkout /absolute/clean-project-worktree \
  --profile-root /absolute/new-owned-profile \
  --output /absolute/new-run-output
```

Use two isolated exact-source worktrees, an absent `kernel/asterinas/target` in
each, the same profile root and separate new output paths. Do not run another
builder in either proof worktree. The profile lock serializes users of the same
virtual input; the public kernel entry retains its own workspace lock. Target
absence is checked at launcher entry, before the public entry acquires that
workspace lock. Independent invocations must therefore own their worktrees.
The caller prepares the fixed nightly, Cargo cache and vDSO in the usual way.
The profile rejects inherited Rust flags/wrappers and fixes timestamp, locale,
target path, compiler remap and explicitly selected embedded builder metadata.

`RUSTC_WRAPPER` forwards every compiler argument unchanged and supplies the
metadata adapter through `CARGO` while compiling proc macros. Only the exact
`metadata --format-version 1` command used by the pinned component macro is
projected. Original and projected JSON, graph checks, component membership and
both source/mirror file identities are retained. All package-ID graph references
are mapped coherently, including a package located at the workspace root with a
`#name@version` fragment. Simple absolute paths without whitespace, URI escapes,
`=`, `#` or `@` are required. A virtual prefix containing `src/` or `tests/` is
rejected because the pinned runtime splits at the first such substring.

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
