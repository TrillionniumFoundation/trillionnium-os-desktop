# Bound frozen application inputs before reading

The native application reader checks file identity before and after reading. Its
open operation also needs to remain bounded when an admitted pathname changes.
The correction opens with `O_NONBLOCK`, `O_NOFOLLOW` and `O_CLOEXEC`, then verifies
that the opened descriptor is a bounded regular file. Original inode, metadata,
length and content checks remain required.

This revision targets the complete current native commit
`b2a0e4eb9eea33fec219049975b413877fed3f59`, tree
`c1d0fc0aa364e64fe0538582e57e055a5e38887f`, with **2,130 tracked files**.
The original reader, application Cargo manifest and workspace lockfile are
byte-identical to the corresponding three files used by the earlier patch.
The explicit workspace `libc` dependency is the only lockfile dependency change;
no resolved versions or package checksums change.

## Current packet

`source-manifest.json` binds this packet, the workflow, the complete native Git
index, and the three source files before and after applying
`native-frozen-read.patch`. The patch contains the original reader correction
and four ordinary native tests: regular content, empty input, a directory
rejection, and a static declared-size bound.

The previous 9ec-based packet and its observed results remain in commit
`2e3d48a77f539e2ab3dc56e349c6a286af50f476`. The current packet retains the existing
ten release tests and adds four ordinary tests. Historical race executors and
duplicate original/candidate modules have been removed from the current packet.
The current workflow performs no race reproduction or Android operation.

## Complete native source validation

`.github/workflows/pocket4-frozen-read.yml` checks out the exact native commit
separately from the reviewed packet. It verifies the complete Git index and
every original tracked blob and mode, applies only the three declared changes,
and checks their resulting SHA-256 values. It then uses Rust **1.93.0** with
Cargo `--locked` to compile the actual application crate and require all
**14 named release tests**, followed by `cargo check --all-targets` on that
same crate. Source and lockfile identities are checked again after the commands.
Zero tests, a different set of test names, ignored tests, modified unrelated
source, or a changed lockfile cannot satisfy this workflow.

Compiler processes use at most two logical CPUs and leave at least two logical
CPUs free. Build outputs are isolated under runner temporary storage and removed
afterward. Complete-source checks and logs are retained as CI artifacts.

For an isolated clean checkout of the exact native commit, use the existing
application helper before running the focused native commands:

```sh
python3 -B compat/android/pocket4/current-app-acceptance/frozen-read/host-regression/apply_native_patch.py \
  --native-root /absolute/path/to/native-checkout --output /absolute/path/to/before-tests.json
```

After the commands, use the same helper with `--verify-applied` and a different
unused output path. The workflow contains the complete resource and named-test
checks. Results apply only to this exact source generation and patched files.

The packet grants no application business-route, Android startup, deployment or
production-readiness acceptance. Those gates remain separate and pending.
