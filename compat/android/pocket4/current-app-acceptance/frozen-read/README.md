# Bound frozen application inputs before reading

The current native application acceptance reader can hang before its descriptor
checks run. A pathname admitted as a regular file can be replaced by a FIFO after
`symlink_metadata` and before `File::open`. Opening the FIFO for reading then waits
for a writer. Runtime-plan input pins use this same reader.

`native-frozen-read.patch` updates the current native
`runtime/droidloom-applications` source. It opens with `O_NONBLOCK`, `O_NOFOLLOW`
and `O_CLOEXEC`, then verifies that the opened descriptor is a bounded regular
file before reading. Existing inode, metadata, length and byte-identity checks
remain in place. The application crate gains its explicit workspace `libc`
dependency, and the native workspace lockfile records that dependency without
changing any dependency versions.

## Source identity

This packet is based on the original current native source exported from the
native source archive. It does not patch the older nested public continuation
copy. Apply the patch only to the matching native source generation.

| File | SHA-256 |
| --- | --- |
| Original `release.rs` | `df7eeb8d4b8e808a5273847eb61d28d986d02787c61755d5b674e5305192aa2b` |
| Candidate `release.rs` | `786383bce459c120cd7bf978d6ad313743ef8a66b6ca002e422cbb234d2b55f9` |
| Native patch | `8cef43de18dc4f6c767b62c720e7aecb6de06522854ddcc520bdd16c8f9945bc` |

`source-manifest.json` pins all packet files and the before/after application
Cargo manifests and native workspace lockfile. `fixtures/release-before.rs` is the exact original module used
as the required failing regression control. It is not an installable Android
runtime or an alternate retained application version.

## Replay the host regression

Use Linux with Python supporting `os.pidfd_open`, a C compiler, and the fixed
Rust **1.93.0** toolchain. Compiler processes are restricted to at most two
logical CPUs, with at least two other logical CPUs left free. From the repository root:

```sh
packet=compat/android/pocket4/current-app-acceptance/frozen-read
python3 -B "$packet/host-regression/run_regression.py" \
  --original "$packet/fixtures/release-before.rs" \
  --candidate "$packet/candidate-release.rs" \
  --output frozen-read-result.json
```

The default uses Cargo's offline cache and the committed lockfile. On a clean CI
runner, append `--allow-registry-fetch` to fetch the locked dependencies. The
output path must not already exist. The script creates and removes its own
temporary build directory and reports whether removal completed.

The regression imports each complete real source module into a small host
driver. The interposer waits immediately before the target's real `open`; it
does not replace metadata, file descriptors, or return values. The controller
replaces the admitted pathname with a real FIFO, then releases the open. The
original must block. The controller terminates and reaps only its own original
child and verifies retirement through the original pidfd. The candidate must
reject the FIFO promptly. A second candidate run must reject a final-component
symlink replacement. Ordinary and empty regular files must still read correctly.
The candidate's complete ten existing native release unit tests also run.

The fixed Rust 1.93.0 host run passed all ten tests and all three race controls.
This proves the reader correction on the pinned source. The complete native-crate regression runs independently in
`.github/workflows/pocket4-frozen-read.yml`: it checks out native commit
`9ecce4f94dec80500c05322106907e48a0668b05`, verifies its complete 2,118-file tree,
applies only this three-file patch, and requires all ten native release tests
to pass with `cargo +1.93.0 test --locked -p droidloom-applications --lib
release::tests::`. It also reruns the actual FIFO and symlink controls. Zero
matched tests are a failure. Build outputs stay under runner temporary storage. The packet performs **zero Android actions**, closes **zero application
business routes**, and grants no runtime or production-readiness qualification.
