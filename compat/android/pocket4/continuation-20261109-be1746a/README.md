# Pocket4 continuation: qualified tools, integrated supervisor and official input

This capsule records an independent continuation of Pocket4's Linux-hosted Droidloom repair. It preserves the current owner's mutable AOSP trees and coordinator state. It adds executable source repairs and actual host qualification; it does not declare Android, the final application set, or production admission accepted.

## Native ordinary tools

`native/` contains the exact owner-prepared recursive Tradefed cone patch, its isolated replay and the actual Rust 1.93 qualification. The patch restores complete original CTS Tradefed, CTS-V host, CHDTS, VTS-core Tradefed and Deqp CTS source cones, and updates the ordinary recipe's locked expectations and regression controls. It is not interchangeable with the earlier narrower source-lock-only delta.

The actual isolated source commit is `ff910cc50d842b5308b860340295bda44c28cf5a`, based on `fb55abd62b661b4c028f5a8fdf213f29b4f1ad8b`. All 16 native-pair tests and 26 source-library tests passed. Both ordinary dev tools built, and the new source tool verified 600 exact projects and eight root links. The first attempt's `/tmp` ENOSPC failure is preserved; the successful attempt uses its own TMPDIR with unchanged source inputs.

The owner still needs to consume the qualified tools through ordinary source reconcile/materialized verification and a serialized fresh full build. These host results grant no APEX or Android runtime acceptance.

## Audio discovered-module diagnostics

`audio/src/bin/droidloom-blueprint-defaults.rs` is a dependency-free, read-only Rust diagnostic over an explicit `Android.bp.list`. It inspects every listed module's literal direct `defaults` references, including modules outside the requested build target's dependency closure. It reports unsupported syntax and nonliteral expressions explicitly and always emits `graph_qualified=false`.

The actual Audio r9 failure was `DesktopTestLibTestsMobly` depending on absent `PASIT-defaults`. Seven regression tests pass with both Rust 1.95 and the repository-pinned Rust 1.93. The checked-in consumer and provider are exact original AOSP files, with their notices and provenance preserved.

The actual read-only scan of 8,584 restored-original Blueprint inputs recovered that edge. All input, discovery-list and materialized-manifest hashes were unchanged before and after. Its 767 absent-name candidates are not 767 established Soong failures: namespaces, module types, variants, generated providers, load hooks and inputs outside the list are outside this diagnostic. The earlier projected build state is not reconstructed by a later restored-original scan. A normal full build remains authoritative.

## Integrated supervisor

`broker/` combines the frozen namespace broker with sealed configuration input handling, then incorporates the current published lifecycle fixes. Its README and exact source manifest specify the patch chain, conflict resolutions, actual compiler results and privileged-control boundary. Apply the combined patch at its declared preimage; do not apply the old sealed-input patch a second time.

The current owner's later host-admission-tree work is outside this frozen combination. This capsule does not grant a HostAdmission token, allocate production IDs, change host accounts/grants or install a daemon.

## Physically delivered official Firefox input

`firefox/` records delivery of the exact selected official Firefox 159.0.1 x86_64 APK into the canonical QPR1 cohort on Pocket4. The current stable version was checked through Mozilla's [version API](https://product-details.mozilla.org/1.0/mobile_versions.json) and [release notes](https://www.firefox.com/en-US/firefox/android/159.0.1/releasenotes/).

The APK is 139,231,259 bytes, SHA-256 `dc4310b6193a5cadf3b7eff119e677aea006071c8484fa7a35874c2613fd18e1`. It exactly matches the previously signature-verified selected candidate. A separate complete readback confirms the same bytes and stable inode/metadata. This execution did not rerun apksigner, install Firefox, change the browser role or qualify an application workflow. The APK binary is deliberately not stored in Git.

## Verification and release boundary

`FILES.json` binds every source and receipt in this capsule. `verify.py` checks the complete file set, sizes, hashes and the stated qualification boundaries. A08 additionally compiles the current Rust diagnostic with Rust 1.93, executes all seven tests and exercises both real CLI outcomes against the exact original fixtures: missing PASIT returns 2, and its literal provider present returns 0 while `graph_qualified` stays false.

`observation.json` records a bounded direct host observation. Pocket4 actually runs `7.0.14-p4cred1`; the reboot and postboot qualification were performed by the existing owner and independently observed here. The later private r3 namespace control passed without granting production admission. No success claim is inferred from an older coordinator summary.

Still required are coherent final Native/Audio artifacts, an actual QPR1 Android boot on the repaired kernel, production namespace/daemon admission, accepted final application workflows, remaining official application deliveries, resolution of the existing signer conflict without destroying user data, and final reference-bound retirement. Production ready, runtime qualified, final candidate deployed and all blockers closed remain false.

Temporary diagnostic binaries from this continuation are retired as recorded in `audio/retirement-receipt.json`. Required source, exact patch inputs and qualification records remain available to the owner. No old user-data image or current owner build root is deleted on the basis of these host-only results.
