# Fixed-hardware beta qualification

## Status and claim boundary

This package defines the D8 evidence format, candidate hardware profile, numeric
thresholds, and offline verifier. It is blocked by D7. The source gate creates
only deterministic fixture evidence and is permanently ineligible for hardware
promotion.

A physical beta claim requires an independent hardware-lab signature over raw,
digest-bound evidence from the exact fixed device and exact release artifacts.
No QEMU run, fixture, simulated timer, manually written PASS summary, or source
unit test substitutes for that evidence.

## Fixed profile and bill of materials

The candidate profile identifier is
`trillionnium-x86_64-reference-appliance-v1`. Every qualification binds the
complete system, board, firmware, CPU and microcode, memory, storage and
firmware, GPU and driver, render mode, display EDIDs, input devices, audio
codecs, network devices, TPM, and Secure Boot state. Serial numbers are stored
only as stable hashes.

Changing any bound BOM field creates a different hardware profile and
invalidates the evidence.

## Exact software and artifact identity

The evidence binds source commit and release tree together with image, kernel,
initrd, package-lock, SBOM, license, provenance, and known-limitation digests.
The verifier recomputes every declared artifact digest and requires the
evidence directory to contain exactly the declared files—no missing, extra,
symlinked, or basename-remapped artifacts.

## Numeric gates

The candidate thresholds are machine-readable in
`contracts/hardware-beta-qualification.v1.json`. They include:

- cold boot to ready no more than 45 seconds;
- compositor to first frame no more than 5 seconds;
- native input p95 no more than 50 ms and p99 no more than 100 ms;
- Agent observe p95 no more than 500 ms and act p95 no more than 1 second;
- content crash recovery and suspend/resume p95 no more than 15 seconds;
- peak RSS no more than 4096 MiB, 4096 FDs, and 512 PIDs;
- RSS growth no more than 4 MiB per hour;
- metric sample gaps no greater than 120 seconds;
- at least 24 hours preliminary and 72 hours final stability;
- minimum cold-boot, crash, suspend, update, rollback, power-loss,
  accessibility, IME, display, and security corpus sizes.

These are candidate product gates, not measurements already achieved.
Threshold changes invalidate all prior D8 evidence.

## Raw evidence, not summary assertions

Metrics are canonical JSON Lines records. The verifier recomputes percentile,
peak, growth, temporal order, sample gap, and coverage values. Cycle files list
each measured boot, first-frame, crash recovery, suspend/resume, update,
rollback, and power-loss result. Subsystem files enumerate every required
scenario and case count. Security results enumerate required categories and
apply zero tolerance to critical failures, uncorrected corruption, unexpected
external effects, and network-policy bypasses.

The signed top-level document cannot override failures found in raw artifacts.

## Required subsystem coverage

Physical evidence covers hardware and software rendering, keyboard/pointer/
button/wheel/touchpad, audio, suspend/resume, cold boot and unexpected power
loss, accessibility, IME lifecycle, display hotplug/multi-monitor/scaling,
update/rollback/offline recovery, target-web, prompt-injection, origin-spoofing,
sandbox, controlled-egress, and signed-bundle regression.

A missing category, scenario, or minimum case count fails closed.

## Stability and power loss

Final eligibility requires at least 72 hours of timestamped samples with no
unbounded gap. Twenty cold boots, 100 content crashes, 100 suspend/resume
cycles, twenty update commits, twenty update rollbacks, and 100 unexpected
power-loss cycles are minimums. Each power-loss test must preserve the previous
healthy slot or recover through the D7 bounded protocol without silent data
corruption or duplicate external effects.

## Independent lab identity

Promotion requires the signed role `independent_hardware_lab` and a
production-enrolled lab key. Fixture keys and source-CI identities can validate
the file format only. They cannot set `physical_hardware`, production enrollment,
or hardware-beta truth.

## SBOM, CVE process, and known limitations

The exact artifact bundle includes SBOM, licenses, CVE handling process,
provenance, and known limitations. The limitations set cannot be omitted or
claimed empty without an independently identified review record. A limitation
may remain open or accepted, but its severity, mitigation, status, and reviewer
role are explicit and digest-bound.

## Promotion sequence

After D7 is independently merged and qualified:

1. freeze the exact hardware profile and release-candidate artifact set;
2. enroll an independent hardware-lab verification key outside source CI;
3. run the full physical corpus and produce raw artifacts;
4. sign the exact evidence manifest;
5. verify it offline with `--require-physical`;
6. obtain independent security and product review;
7. merge only through protected `main` and rerun exact-main metadata checks;
8. record hardware beta truth without claiming D9 release readiness.

The source package delivered here proves the verifier and attack corpus only.
