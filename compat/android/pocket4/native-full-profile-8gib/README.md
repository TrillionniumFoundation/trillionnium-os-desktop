# Native full build: 8 GiB with a 5 GiB host reserve

The original full-build profile required a 10 GiB cgroup cap and at least
15 GiB of fresh `MemAvailable`. The host could not reliably meet that admission
floor. This separately named profile caps its own job at **8 GiB**, retains the
**5 GiB host reserve**, and therefore requires at least **13 GiB** immediately
before the normal build. The old bound profile and historical receipts are not
rewritten.

The active profile is `native597-8gib-hostreserve5-20261108-r1`. It has separate
attempt, output, fence, admission, execution-binding and preflight paths. The
normal 597-project source, 515-file builder, seven required translation units,
two complete engine/ART targets, Strict dependency handling, two compiler jobs,
CPU quota, zero-swap requirement and 21600/23000-second inner/outer budgets remain
the same. The parent still retains Framework and Audio's four locks until the
Native job has retired and restoration checking has completed.

Two historical consumers previously compared their old observations against the
active admission constant. They now use an explicit historical 15 GiB constant.
Their original receipt hashes, old 10 GiB resource values, rejected-memory
sample, rejection text and exact difference remain unchanged.

The source files are the actual prepared implementation. `controller-profile.patch`
shows the narrow controller delta against the reviewed R11 template. The binder
performs the original current-source and original-builder checks before creating
the new frozen packet. It does not materialize source or invoke Soong. The
preflight template requires the actual new execution-binding bytes and SHA;
those two values must be filled from the completed binder, not from a predicted
result. The current preflight is revision 2 with its own 2 GiB cap; the full build
remains capped at 8 GiB. Preflight still obtains all six locks and checks the
13 GiB fresh-resource floor twice. It records `memory.stat` before and after
to distinguish anonymous and file-cache accounting. No max-limit pressure,
owned OOM event or swap use is accepted.

The original 1 GiB preflight completed source checks but reached its own cap
(`memory.events max=4727`, no OOM or swap) and correctly failed. Its original
failure is retained; this package keeps only a compact regression fixture, not
the obsolete runnable 1 GiB template. A later 2 GiB attempt also correctly failed
when the host had less than the required fresh 13 GiB, before the source scan.
Increasing the preflight cap does not guarantee a stable host admission window.

## Portable controls

From any working directory:

```sh
python3 -I -B /path/to/native-full-profile-8gib/tests/test_resource_profile.py
```

The 26 controls execute the actual admission function and check the one-byte
boundary, a mismatched hard cap, changed CPU quota, nonzero swap, a changed host
reserve, and the inability to count global swap as RAM. They also verify the
exact function delta, unchanged source/build/retirement functions, original
historical-budget semantics, frozen builder/target identity, and parent-lease
launcher relocation. The fixtures contain source-derived AST hashes, the old
plan and one original function needed by the exact timeout-delta control. They
contain no raw host, device or account logs and run no host commands.

AST fingerprints use a stable recursive field encoding, not `ast.dump`
formatting. Only the newly introduced empty `type_params` and absent type
parameter defaults are normalized; nonempty type parameters, default values,
other empty fields and scalar types remain distinct. Both historical baselines
were regenerated from their original SHA-pinned source files. Three controls
exercise those cross-version and semantic boundaries. Six further controls
execute the actual preflight predicates for the exact 2 GiB cap, clean resource
events, the observed historical max-pressure failure, every owned OOM counter,
nonzero swap and both 13 GiB admission boundaries.

This change permits a real bounded attempt. It does not prove that the entire
597-project graph fits in 8 GiB. Any failure must retain its actual terminal and
resource events. A failed or incomplete attempt yields no qualified pair, no
installation and no runtime/application acceptance.
