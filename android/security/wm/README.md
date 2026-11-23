# Official WindowManager source corrections

The three patch files retain the complete upstream diffs byte for byte. Each logical fix uses one official branch variant. SOURCE.json records the selected frameworks/base pin, whole original and fixed Java identities, unchanged build providers, official commits, and source-only scope. The six fixtures are original public AOSP files copied from the selected Git blobs with their license headers preserved.

The normal Android producer applies these corrections whenever its requested targets include services, services.core, or WmTests. The default full target set includes services. The focused build_wm_security entry requests services and the existing upstream WmTests through the same normal Strict source profile. It does not widen the audio or native-only source profiles.

Projection uses the existing recoverable journal. All three original Java files and three original build providers are checked before application, effective full bytes are checked after all projections, and restored originals are checked after the build. The user/cp2a source and ALLOW_MISSING_DEPENDENCIES=false, SELINUX_IGNORE_NEVERALLOWS=false settings remain explicit.

Run the ordinary host checks with `cargo test --locked -j 1 -p droidloom-update wm_security::tests -- --test-threads=1`. They apply the official patches to complete original source copies and verify normal restoration and journal recovery, and inspect the real normal producer command construction. They do not execute Android, construct exploit inputs, install artifacts, or qualify runtime security.

A normal build receipt records only the successful command and restored source. The produced services artifact, WmTests execution, full method semantics, signing and the actual coherent runtime must still be qualified separately. CP2A source or source tests do not establish QPR1 identity, CVE closure, or production readiness.
