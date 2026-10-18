# Private dependency restoration on the next cloud instance

This phase records actual dependency recovery on `24f0ea2620fe`, Linux 6.18.55, with an exposed AMD EPYC 9V74 CPU. Its hostname, boot ID, kernel and CPU model differ from the preceding `343e40cfefc1` instance. This is a distinct observed execution instance; it is not physical-host attestation. Kernel compilation, cross-instance ELF equality and project-kernel boot acceptance belong to separate evidence.

## Actual results

| Operation | Observed result |
| --- | --- |
| Prior authenticated evidence | `python3 -I` and `python3 -I -O` verification both exited 0. |
| Fresh Ubuntu inputs | Three fresh signed InRelease files and six complete compressed Packages indexes verified. |
| Fixed package plan | New APT simulation matched all six identity fields of the complete original 57-package lock; 132,706,754 download bytes. |
| Actual private extraction | All 57 .deb downloads passed size/SHA/package identity checks; all 57 `dpkg-deb --extract` commands exited 0. No maintainer scripts ran. |
| Native tools/resources | Ten executable/guest-firmware identities matched the prior hashes. Nineteen native version, real Clang compilation, LLD linking, GDB Python, pkg-config and shared-library checks exited 0. |
| Paused QEMU availability | The owned q35/TCG, one-vCPU, 512 MiB child stayed alive, using explicit private SeaBIOS and `-L` data directory, with no resource warning. Only that child was terminated. No project kernel ran in this probe. |
| Fresh Rust inputs | Official rustup-init: 21,113,232 bytes, SHA256 `dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71`. Complete fresh nightly manifest: 929,653 bytes, SHA256 `c0b09f4e128768b2d6eab27050625a1ce974f8b39c07871370368cd82fbf8617`. |
| Rust/vDSO recovery | All eight original installation/version/binutils/vDSO operations and four additional component/target/identity checks exited 0. |

The public `/var/lib/dpkg/status` was byte-identical to the old baseline, SHA256 `315debd2c0d91242550234b1fc27842103bccdf4274aa75c59b6d1f51d07966e`. The Ubuntu archive keyring was also identical. The native prefix reuses that host baseline and system libc; it is not an immutable environment.

The compiler is `nightly-2026-07-21`, full rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48`. rust-src, rustc-dev, llvm-tools-preview, rustfmt, clippy and the `x86_64-unknown-none` target were installed. `cargo-binutils` used version `0.4.0 --locked`. The fixed vDSO is commit `8af571775a3d3a1df3e84fc9709b9d6b160c771a`, tree `8e0a300d78c2a020ccc79f1253bc27a8301416e6`, artifact SHA256 `27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3`.

## Commands and preserved inputs

The commands below identify the actual completed controllers. Their exact executed sources, command vectors, UTC start/end times, raw exits, selected environment, full logs and authenticated inputs are inside the archive. They are historical commands with original absolute paths, not a portable installer:

```sh
python3 -I /workspace/scratch/ae1a8cf05419/round-next/restore-native-controller.py
python3 -I /workspace/scratch/ae1a8cf05419/round-next/restore-rust-downloads.py
python3 -I /workspace/scratch/ae1a8cf05419/round-next/restore-native-validate.py
python3 -I /workspace/scratch/ae1a8cf05419/round-next/restore-rust-controller.py
```

The native controller copied the archived experimental restorer into the intended scratch working directory, verified fresh signatures/indexes and required exact equality with the existing lock before extraction. The new Rust controller retains the original eight operations, records the current inherited PATH with explicit private native/Rust entries, requires fresh exact installer and manifest hashes, and adds four identity/component checks. It does not reuse the obsolete temporary PATH segment from the prior replay environment. `source-bindings.json` explains these source relationships.

`archive.json` and `member-manifest.json` describe the complete deterministic archive, split into chunks no larger than 2 MiB. All **226** frozen regular files are retained. The complete fresh nightly manifest is both an archive member and a directly accessible gzip copy, `fresh-nightly-manifest.toml.gz`; the verifier checks they decompress to identical bytes. Raw signed Release bodies and all six full Packages indexes are preserved, including the large universe index.

The original freeze command reported 225 files because it excluded every file whose basename was `SHA256SUMS`, including the nested `prior-reference/SHA256SUMS`. No frozen file was deleted or rewritten. The captured manifest already included that nested file and was covered by the root checksum file. This phase corrects the count to 226 and verifies the nested file through that manifest and its independently fixed hash. The first strict packager consequently failed before archive creation. Its unchanged source, actual replayed exit-1 log and explicit correction are in `packaging-before/` and `packaging-correction.json`. This packaging failure is separate from the completed dependency commands, all of which passed.

## Offline verification

Requires Python 3 and `gpgv`. The phase may be moved to a different directory; the verifier locates all evidence relative to itself. It assembles chunks in memory, checks canonical regular tar members without extracting them, verifies the full frozen manifest/checksum coverage, checks fresh signatures and signed index/stanza bindings, and validates the original command/log receipts. Only a new owned temporary directory under the phase is created for `gpgv`, then removed.

```sh
python3 -I support/build/evidence/2026-10-17-cloud-restore-next/verify.py
python3 -I -O support/build/evidence/2026-10-17-cloud-restore-next/verify.py
```

The portable verifier performs no network access, tool installation, source compilation or VM launch. Its temporary files are not archive extraction. Captured preliminary verifier results are in `verification.json`. The actual relocation probe copied the complete checksum-listed phase into a new owned path and ran both isolated modes from `/`; both exited 0, with receipts in `relocation-verification.json`. Final post-freeze invocations were also checked before handoff.

## Omissions and limits

The 21 MiB rustup-init executable, 57 .deb payloads, extracted native/Rust trees, Cargo caches and vDSO binary remain outside this phase. Exact input identities, fresh download receipts, validation artifact hashes and all executed command logs are retained; `omitted-artifacts.json` states the scope. Reinstalling requires obtaining the omitted payloads. Offline verification checks the retained inputs and receipts rather than repeating installation.

No current dependency command failed. The preceding `2026-10-17-private-toolchain` phase retains the earlier `prepare-host.sh --apt` exit 100 and the resource-lookup warning from a QEMU probe without `-L`. This restoration did not repeat either command or relabel those failures. The packaging count failure above is retained here.

Capabilities remain zero, NoNewPrivs 1 and Seccomp 2. `/dev/kvm` is absent, default AF_UNIX socket creation still returns EPERM, and socketpair/IPv4 loopback passed. No system package, account, BIOS, GPU driver, service, namespace, capability or sandbox setting was changed. The SeaBIOS file is a QEMU guest input. Docker/Nix and a NixOS ISO were unnecessary. No global cargo-osdk was installed by these controllers. These facts do not close KVM, AF_UNIX, immutable-environment or native-feature blockers.
