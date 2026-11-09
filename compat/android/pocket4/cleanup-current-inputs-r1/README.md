# Pocket4 current inputs and cleanup reference observation

This source capsule supplies a read-only current-input verifier and a narrow
replacement for one cleanup helper function. It does not deploy Android,
retire a package, apply a live patch or authorize deletion. Existing cleanup
results and the active coordinator's deployment lease are unchanged.

## Actual selected-input readback

At **2026-11-09 04:10:06 UTC**, `verify_current_inputs.py` verified the real
selector's **13 preparations** and **721 retained file records**. Their union
is **723 files / 20,619,335 bytes**: two preparation files are outside the
retained list. Full SHA-256, size, single-link regular-file, every-component
no-symlink, held-descriptor and final named-path checks passed with zero errors.
`live_721_readback.json` contains the compact receipt and complete/exited-0 PTY
identity. `source-provenance.json` pins the inspected originals.

```sh
python3 -I -B verify_current_inputs.py --current /home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json
```

The actual schemas are `pocket4-linux-android-current-continuation-v1`,
`current-application-preparation-selection-v1`, and
`gallery-qpr1-current-source-final-retained-files-v1`. The verifier also requires
the coordinator and selector to bind the same retained manifest. Changed
content, generation, identity, schema or count; duplicate keys/paths;
symlinks; hardlinks; private signing material; and resource limits fail closed.
It reads input bodies without executing them and has no write or apply mode.

The 723-file readback is narrower than the active cleanup executor's 743-file
union, which includes 22 additional Camera inputs. It is not a substitute for
kernel/runtime validation or the **42-app** acceptance cohort.

## Reference-observer fix

The exact helper baseline is:

`cleanup/apps-old-root-retirement-20261108-8b88-r1/executor.py`

SHA-256: `22e7e85962c52a5cf44759dd99610d16293a0f8573ee68b8b9da4c89b1c7911a`.
The source was re-read from Pocket4; its hash was unchanged. Its exact bytes
are retained in `fixtures/executor-baseline.py` only for parsing and patch-scope
verification. **Never execute or import this historical retirement executor.**
The original function alone is retained as `fixtures/observed_live_references.py`
for before/after regression controls.

`reference_observer.patch` replaces **only `live_references(roots)`** using the
function in `reference_observer.py`. Its three existing caller veto lists
(`process_or_owner_hits`, `mount_hits`, `coverage_errors`) remain intact.
Target selection, signing-material release, current-manifest checks,
owner policy and deletion code are unchanged. The replacement:

- Enumerates every visible `/proc/PID/task/TID`, including the observer itself,
  and checks cwd, exe, root, FDs, maps, argument matches and mount namespaces.
- Inventories exact target metadata through descriptor-relative no-follow
  opens. Device/inode matching catches FD or map aliases without reading target
  bodies; mount-root translation catches binds of a target's parent directory.
- Marks unreadable, malformed, ambiguous, changing or out-of-bounds visibility
  `UNKNOWN`. Thread identity, namespace, root, FD sets, process/task sets,
  mount views and target metadata are rechecked. Stacked mounts with the same
  deepest mountpoint are ambiguous. Mounted descendants, symlinks and special
  target nodes are refused. Hardlink identity observation does not change any
  caller's hardlink deletion policy.
- Handles only a narrowly proved empty zombie as a non-holder: one leader,
  stable matching Z/X identity, empty FD/maps/cmdline, and absent namespace,
  cwd, exe and root. Namespace absence by itself remains `UNKNOWN`.

Limits include 128 exact roots, 100,000 target entries, 20,000 tasks,
500,000 descriptors, bounded reads/hit lists, and a 45-second cooperative time
budget. Inaccessible processes and churn can cause conservative `UNKNOWN`.
This remains a snapshot, not a lock against a future writer or new reference.
The current cleanup owner must qualify the replacement against its host,
review new source pins and preserve its independent execution guards before
considering live use. **The capsule has not applied the replacement on Pocket4.**

To reproduce patch-scope verification using the bundled exact baseline:

```sh
python3 -I -B verify_reference_patch.py
```

An explicit `--baseline /path/to/executor.py` may check another copy; its exact
SHA must match. This checks the baseline SHA, exact generated patch, syntax, unchanged AST
outside the function and byte-identical prefix/suffix. It executes no helper
source and applies no patch. `reference-patch-scope.json` records that scope
proof and an isolated temporary-copy patch application check.

## Validation

From this directory:

```sh
python3 -B -m unittest -v test_verify_current_inputs.py test_reference_observer.py
```

`test-results.json` records **40 passing tests**: 12 actual-schema input
verifier controls and 28 observer controls. The observer tests demonstrate
original misses and corrected detections for a non-leader FD, FD/map inode
aliases and a parent bind exposed in another task's namespace. They also
cover escaped mount paths, ambiguous overmounts, strict zombie handling,
FD/thread/namespace/identity changes, denial of visibility and bounds.
One integration control holds an actual local Linux FD and mmap and requires
both to be found. Unreadable unrelated processes remain `UNKNOWN` in that
control. The namespace/bind cases use proc-shaped fixtures; they do not claim
actual namespace creation or a whole-executor bypass.

## Last two retained roots

`remaining-roots-readback.json` records the final independent read-only checks.
The original fence remains 661 bytes with SHA-256
`6a98cf8d82ead8506afeb1ff831d1e9fd99d1c8e112f5f750c828125dc6debe1`.
Its original owner has no newly established positive terminal evidence.
A canonical backup and an absent historical H job/systemd unit do not establish
that owner's safe retirement.

Fresh, read-only extraction from the original Android image at **04:37 UTC**
confirmed that the package registry still exactly matches the reviewed
378,050-byte registry content. The Amazon QA package is
`org.droidloom.qa.amazon.r3`, version 1, app ID 10154, with certificate SHA-256
`801ad669c2075067b58ee7d277531e9eed7cd612a74f404a722c061cac66bf6d`.
It is excluded from the production cohort. No direct reference to its exact
package, signing root or certificate appeared among 723 pinned current inputs;
that is supporting evidence, not proof of runtime independence. The scoped
metadata check found two regular CE files totaling 1,104 bytes and empty
CE/DE cache directories. No app-data filenames or bodies are published.

Retirement has a concrete path: the active owner first verifies the ready
original profile, all Android users, exact package/signing identity and owned
QA data custody, then invokes Android PackageManager for that exact package
and version. The receipt specifies the proposed argv and postconditions.
The installed `droidloomctl` has no uninstall subcommand. An uninstall with
`-k` preserves data and may retain the package setting/signing dependency;
it cannot by itself release the signing root. PackageManager success must be
followed by absence of all registry, retained-data, code and signing consumers
before a newly reviewed exact-path root retirement. No offline registry edit,
raw app-directory deletion or lease bypass is proposed.

`FILES.json` is the complete publication whitelist, excluding only itself.
No process prototype, downloaded image/registry, private material, full app
roster or unrelated workspace artifact belongs to this capsule.
