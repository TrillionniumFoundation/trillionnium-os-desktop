# Native builder468 provider closure: compile03

State: **SOURCE_ONLY_UNRUN**. This package is a minimal successor to the Root-reviewed compile02 source. It contains a reviewable, bounded static compiler request; it has not been dispatched by this agent. Root is the sole Hepta dispatcher.

## Exact change

The compiler no longer sets the child environment variable HOME to /home/alex. Its only other source changes are the create-only work root and the report scope label for attempt 03. CARGO_HOME, the pinned Rust and Cargo tools, all command and cleanup gates, and the source compilation plan remain unchanged. compiler02-to03.patch contains all three changed lines. stage02-to03.patch changes only the new ROOT and the two copies of the compiler pin; transport02-to03.patch changes only the exact wire and stage pins.

The new root is /home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106. The idempotency key is pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106. Attempt 02 and its request remain immutable and unrun. Nothing from this later derivation is added to the fixed CP19 cutoff.

## Executable source binding

exact-request.json is the complete process_start argument object. Its stdin is plain JSON with the exact stage and 30 UTF-8 source files. The unchanged stage reads another 11 precisely named, already-owned authority files under the original held/named/hash guards, before create-only staging of all 41 files. All 41 staged source bodies are available here as either new blobs or exact reused compile02 blobs. baseline02-bindings.json gives their origin tree, path, size and both hashes.

The 29 transferred files other than compile_builder.py are byte-for-byte identical to compile02. That includes the 491-file expected builder manifest, both Rust files, the source lock, all 24 whole Android.bp fixtures, and the source closure proof. The original 70 fixed upstream reference bodies remain reachable in predecessor tree 04251621f70cc29d3a5f3f862bb1a0b337c31b94. No source delta, provider stanza, target, or dependency gate changed in this revision.

## Verification and execution boundary

The V8 derivation verified the complete original request hash, every transferred file pin, all 11 authority metadata bindings, the new packet and wrappers, and whole-byte inverses back to compile02. derive-compile03.js reproduces the change from that exact original request using the previously preserved hash utility (blob 443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d). No local process or Python/Rust compiler was available or invoked.

The request retains CPU quota 100%, memory maximum 1 GiB, nice 15, process timeout 600 seconds and controller deadline 550 seconds. It requires enough CPUs to leave two logical CPUs free. Its stdin is 886361 bytes, below the tool's 1 MiB limit. The original owned resource, command-child, source/tool/configuration, and final cleanup gates remain exactly as in compile02.

The source expects 62 command records and 24 focused controls (15 updater plus 9 source-resume). These are pending execution, not passed test results. The retained closure comprises 224 locked projects and 59 projected provider stanzas from 24 pinned whole BP fixtures. The locked robolectric-native-prebuilt directory is selected, but its full BP body remains unobserved. A successful static compiler run will still not qualify real source reuse, a strict Soong build, a framework implementation JAR, or the Android JNI object and final link.

This request performs no normal Android/Soong build, no Main service action, no installation and no UI work. The old Main epoch remains invalid; no new epoch is authorized by this source package. Whole-app readiness remains 0/45.
