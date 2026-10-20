# Private toolchain restoration evidence — 2026-10-17

The fresh host recovered the fixed Rust nightly and native build tools using a task-private prefix. This directory records the restoration experiment. Kernel compilation and guest acceptance belong to the separate build/boot evidence.

## Actual outcomes

| Operation | Observed result |
| --- | --- |
| Original `bash support/build/prepare-host.sh --apt` | Exit 100: the restricted host could not set groups/drop to `_apt`; full original controller and log retained in `before/`. |
| Signed Ubuntu snapshot | Three InRelease signatures verified using the host's Ubuntu public archive keyring; six `Packages.xz` sizes/SHA256 values matched their authenticated Release metadata. |
| Missing-package solution | Read-only `/usr/bin/apt-get --simulate --no-install-recommends` selected 57 packages, totaling 132,706,754 download bytes. |
| Private recovery | All 57 downloads matched signed package size/SHA256 and package identity; all 57 `dpkg-deb --extract` operations exited 0. |
| Native checks | 26 of 27 checks passed. The paused QEMU probe without `-L` retained a missing `kvmvapic.bin` resource warning and is recorded as a failed resource-lookup check despite raw process exit 0. |
| Rust restoration | All eight original controller commands exited 0, including the fixed nightly install, version checks, locked cargo-binutils 0.4.0 install and fixed vDSO checkout. |

The native prefix is `/workspace/scratch/ae1a8cf05419/native-tools/root`. No package maintainer scripts, system library installation, accounts, services, namespace changes, privilege changes or APT sandbox changes were used for this private recovery. System libc was reused. Missing dependencies therefore depend on the host package baseline; `host-dpkg-status.gz` is a posthoc public baseline snapshot, not an invented original pre-install capture.

Recovered versions are Clang/LLD 18.1.3, QEMU 8.2.2, GDB 15.1, BusyBox 1.36.1, cpio 2.15, pkgconf 1.8.1 and OpenSSL 3.0.13. Exact executable and guest SeaBIOS hashes are in `experimental-native/native-environment.json`. GDB's version/resource checks establish tool availability, without claiming host ptrace access.

## Authentication and commands

The source is the fixed official snapshot `https://snapshot.ubuntu.com/ubuntu/20260828T000000Z/`, suites noble/noble-updates/noble-security and main/universe. `signatures/` preserves the three exact signed InRelease files and the public keyring. Its SHA256 is `80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31`; the observed signer fingerprint is `F6ECB3762474EDA9D21B7022871920D1991BC93C`. This is a fixed snapshot, not a claim to provide the latest packages.

`index-storage.json` binds all six complete compressed indexes. The 15,037,908-byte noble/universe index is stored in 2 MiB chunks; it is reconstructed and verified before parsing. `package-lock.json` binds each of the 57 selected package records to an exact original signed stanza in `selected-stanzas/`. The retained controller, download/extraction receipts, solver output and complete command logs are under `experimental-native/`.

The original experimental phase commands were run from `/workspace/scratch/ae1a8cf05419`:

```sh
python3 /workspace/scratch/ae1a8cf05419/native-tools-restore/restore.py
python3 /workspace/scratch/ae1a8cf05419/native-tools-restore/restore.py --extract
```

`restore.py` is the final experimental source after adding extraction and fixing a cwd logging error. Original receipts remain unchanged; `controller-cwd-correction.json` identifies the initial entries affected by that metadata error. This archived script is evidence of the recovery approach, not a production installer. Its original absolute paths are preserved and it must not be run in place inside this archive.

Offline verification requires Python 3 and gpgv, uses a temporary directory, and performs no network access, installation or VM launch:

```sh
python3 -I support/build/evidence/2026-10-17-private-toolchain/verify.py
```

## Runtime paths and limitations

The actual command/environment receipts are authoritative. Native validation used the private `usr/bin` and `usr/lib/llvm-18/bin` in PATH, private shared-library directories in LD_LIBRARY_PATH, private `QEMU_MODULE_DIR`, and private pkg-config paths/sysroot. A minimal paused QEMU q35/TCG/one-vCPU probe with explicit private SeaBIOS and `-L .../usr/share/qemu` remained running until its owned child was terminated. It did not execute an Asterinas kernel. Repeating that probe without `-L` exposed the retained resource warning. The private guest BIOS is a file input to QEMU, not a change to host BIOS.

The host reported zero capabilities, NoNewPrivs 1, Seccomp mode 2 and no `/dev/kvm`. An earlier AF_UNIX socket creation returned EPERM; no policy or namespace workaround was attempted. These host restrictions remain separate from native tool availability. The fresh host had no Docker or Nix, and neither was installed or required for this native recovery. No NixOS ISO was downloaded.

## Fixed Rust and vDSO

`rust-restore/` preserves `restore-rust.py`, `rust-commands.json` and its eight complete logs from `round2-restore/`. The compiler is nightly-2026-07-21, commit `87e5904f5eb6398af6b22eac2802c78934260c48`; this recovery explicitly installed the x86_64-unknown-none target. No claim is made that other target architectures were restored. rust-src, rustc-dev, llvm-tools-preview, rustfmt and clippy were requested explicitly.

The official rustup-init executable is omitted; its observed 21,113,232-byte size and SHA256 `dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71` are retained with its official URL. The fixed nightly manifest was actually fetched and observed as HTTP 200, 929,653 bytes, SHA256 `c0b09f4e128768b2d6eab27050625a1ce974f8b39c07871370368cd82fbf8617` in the earlier environment probe. That fresh response body was not retained; `rust-restore/inputs.json` explicitly labels this as a posthoc transcription of the observation. The earlier 2026-10-16 archived manifest is a reference, not a replacement presented as a new download. The Rust restoration controller did not itself record a fresh manifest SHA.

The vDSO checkout is commit `8af571775a3d3a1df3e84fc9709b9d6b160c771a`, with artifact SHA256 `27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3`. Only its original command receipts and input metadata are included. Full inherited environment was not captured by the original Rust controller; selected variables and the executed PATH construction remain visible.

No .deb payloads, extracted tools, rustup-init executable, vDSO binary or build target/cache tree is committed here. Their input identities and omitted validation-artifact hashes are retained for review. SHA256SUMS covers the evidence files except itself.

The final offline verifier ran with `python3 -I` and `python3 -I -O`; both exited 0. Original captured outputs/statuses and verifier SHA are in `verification.json` and `verification-*.log`. These runs rechecked the authenticated metadata and retained receipts; they did not rerun installers, native probes or guests.
