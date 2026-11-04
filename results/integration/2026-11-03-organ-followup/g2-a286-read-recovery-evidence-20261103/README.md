# a286 recovered reads and fixed nightly cache admission

This supplements the frozen 28-file a286 build/cache archive. It leaves every earlier failed attempt and frozen source unchanged.

The original kernel v2 job is authoritatively failed with exit 1, not timed out or cancelled. The complete OSDK log confirms that original a286 cargo-osdk 0.19.0 finished and installed successfully. Its kernel command remains failed on missing offline getopts 0.2.24; it did not complete the kernel build.

The actual generated Cargo.lock is 41,937 bytes, SHA e54bc99b3df5e21a1fdcd88d89b32ac478e73c7b4bf69ae0b1084f59d56fc506, and equals the canonical 204-package product lock byte for byte. This is a generated-file observation. Full locked graph/build admission remains false until the original build and its original validator succeed.

The installed nightly-2026-07-21 library lock was read completely: 9,835 bytes, SHA 9e87d1ac04edbf5fa61e27cb21984a83566573a007767713868965fba70acb6d, 49 packages including 30 registry versions. Its getopts 0.2.24 checksum is cfe4fbac503b8d1f88e6676011885f34b7174f46e59956bba534ba83abded4df. This is a separate standard-library lock; neither source lock was changed.

A read-only inventory exited 0. All 30 exact index versions are present. Four missing archives existed in the known old F1 cache with exact library checksums: getopts, libc, memchr and rustc-literal-escaper. After the independent seed quiet window ended, a separate create-only admission copied those four archives, 954,962 bytes, into the task-private cache and exited 0. The 13 other missing archives are not assumed necessary or unnecessary without the actual build. The source cache, indices, source files and locks were not changed.

Retained original SDK payload bytes accompany decoded files. The multiple-file read explicitly reports independent snapshots, not an atomic pair. An async metadata read of an existing job was explicitly rejected as not_submitted. Authoritative job states came from their original direct process_status APIs. No build was replayed by a read.

One original kernel v3 pipeline was then launched, job 1a1a3ceade8-96a-776b, with canonical Desktop a286e0f922bf8e439e8951ae1538abeac0b26477 and Hepta a39a0871d9601ffccb5e0d95d8f39d54b3a63360. It uses the official Cargo --target-dir option to reuse its own v2 OSDK cache while still executing the source-owned cargo install --locked --offline and original kernel.sh. The source, default features, original limits and owner image are unchanged. The launch acknowledgement is not a completion result.

This archive grants no completed kernel build, locked graph acceptance, guest execution, native owner cycle, finite memory observation, lost reply, effect-before-terminal recovery, whole-guest peak, global reserve or complete G2 qualification. Any v3 completion and guest outcome require separate actual receipts.
