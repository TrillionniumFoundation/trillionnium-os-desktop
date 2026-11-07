# Composer direct-registration host fixture 02

**SOURCE_ONLY / UNRUN.** This is an independent follow-up to the preserved host01 FAIL. It does not change the production coordinator patch, the host I/O fixtures, their Cargo manifest, or any of the 27 Rust test bodies.

## Actual failure repaired

Host01 passed its three owned-child lifecycle controls and 12 ordinary commands, then stopped before Rust compilation. Its empty new fixture had used cargo generate-lockfile --offline and selected five cached registry versions outside the immutable original lock: libc 0.2.191, syn 3.0.9, thiserror 2.0.21, thiserror-impl 2.0.21, and unicode-ident 1.0.27. Their exact original versions and checksums are retained in actual-host01/lock-diagnosis.json with the complete original result, two lock files, and Cargo metadata.

Host02 first copies the complete, held, verified original Cargo.lock into its new create-only fixture. A single cargo metadata --offline invocation may reconcile that fixture's graph. The next invocation remains --offline --locked. The unchanged dependency gate still requires exact original-lock package identities/checksums and the actual 45-archive source qualification before Rust can compile. It does not authorize the five newer versions.

The ordinary command count remains 42. The three lifecycle controls, 1 CPU, 1 GiB RAM, nice 15, 450-second work qualification and 600-second tool timeout remain unchanged. Swap remains observed rather than guaranteed disabled. Main, Android, Soong and network downloads remain outside the attempt.

## Honest baseline reporting

The three immutable fixture source leaves are captured before Cargo runs. The complete four-leaf baseline is committed only after the resulting lock and static source inventory pass. A failure before that point records NOT_ESTABLISHED or STATIC_SOURCE_ONLY_LOCK_NOT_QUALIFIED and cannot call an unobserved baseline unchanged. It also does not invent source drift. Any actual known source drift or missing full baseline on a purported PASS is still a failure.

## Remaining production blockers

This fixture tests the exact production coordinator methods against explicit I/O seams. It does not compile the Android Binder provider. The newly confirmed provider display/expected-object ownership gap is still a deployment blocker, regardless of a future 27-test PASS. The observed Denial protocol has no wire acknowledgement of Destroy completion; successful send, Close, Error and unknown-object responses are not remote completion proof. Provider repair and real-method ownership negative controls will be separate work.

The actual installed Main source, Bili/Amazon failure causality, full framework Java/JNI artifacts and app production acceptance remain unqualified.

## Review and execution

Root alone may dispatch exact-request.json once after review. reproduce-request.js regenerates every request, stdin, stage, and transport byte from this package. controller01-to02.patch reverses to the exact host01 controller; the normalized patch excludes only the new root string. Every code/source input and all original failure evidence are immutable Git text objects. No local Python/Rust execution or Hepta action was performed while preparing this package.
