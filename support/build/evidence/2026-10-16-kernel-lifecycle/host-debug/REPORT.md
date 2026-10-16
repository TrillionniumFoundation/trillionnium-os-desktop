# Debug cancellation: host evidence only

Source: remote `9b381118fe8a1889d4523b4de999bbe45f1b0436`, tree
`af84f6dfedc3db7d8a9dc4498ea1e1681ea6940c` (same tree as local metadata
`873cad`). The two actual source files match `frozen.json` byte for byte.

These are host lifecycle fixtures. They perform **no Rust build, QEMU boot,
GDB execution or kernel acceptance**. The actual debug CLI runs from a copied
fixture project with explicit placeholder tools and a disposable driver that
holds a file lock and two TCP leases across a TERM-ignoring descendant.

The original CLI received SIGTERM, exited -15, wrote no result, and left both
owned pidfds live, both leases busy and its inherited lock held. Test cleanup
then used the retained pidfds. The first attempt had a missing `fcntl` import
in the test fixture; its complete failure is retained and is separate from the
corrected successful reproduction.

The fixed source passed **10/10 ordinary and 10/10 optimized host tests**.
Each mode actually exercised SIGTERM (143), SIGINT followed by SIGTERM (130),
and SIGTERM between Popen return and owner publication (143). In all six live
runs both pidfds exited, both TCP leases and the inherited lock were released,
leaders were reaped, and the CLI recorded `passed=false` with its first signal.
The optimized runs also execute their copied CLI with `-O`.

Handlers only record requests. Synchronous checks unwind after child ownership
has been published, while final cleanup receives no asynchronous exception.
Existing WNOWAIT/group-before-reap cleanup remains. `A01_KERNEL_WORKER=1`
explicitly keeps the Bash worker inside the debug runner's existing owned group;
this is lifecycle routing, not a security authorization flag.

`commands.json` contains actual invocation receipts. `observations.json` keeps
readable original/final process evidence. `raw-host-fixtures.tar.gz` retains all
raw logs, copied source and fixture scripts, per-run CLI commands/environment,
results and failure diagnostics. Every member is byte-checked against
`raw-members.json`. Generated Python caches are excluded and listed.
`restore-original.patch` transforms the two exact fixed source files back to
the original hashes; an actual `patch -p1` replay was verified in a disposable
subdirectory, with its receipt retained. No active parent build was touched.

Run `sha256sum -c SHA256SUMS` in this directory to verify this archive.
