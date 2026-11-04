# Fixed original-owner archive contract

[PR #284](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/284) contains `00d1dfde8699fe70758519a5508c550476fd5f5c`, tree `7c81e102aba4971bcf36055d1666c002981cc9dc`, over a286. The [exact diff](candidate-diff.log), [main manifest](manifest.json) and [publication record](publication.json) cover only the runner, its ordinary host tests and the source profile documentation. Independently read file hashes and the complete published Git tree match the frozen main candidate.

The source-owned exact-a39 path binds the original base gzip/canonical cpio, original image size, two finite plans and a 64-hex-character nonce. It passes the fixed 22,268,496-byte envelope to the existing unpack function. The shared codec's 16 MiB default, legacy image limits, kernel code and image descriptor remain unchanged.

The [normal](normal-host-tests.log) and [optimized](normal-host-tests-optimized.log) runs each passed 6 cases: 3 archive and 3 quiet-packaging checks. The [original-image host roundtrips](actual-roundtrip.json) passed for 22,268,484-byte steady state and 22,268,496-byte manager-after-terminal archives. The [actual host job](process-status.json) exited 0. QEMU was not launched by these host checks.

The [previous preflight failure](../g2-a286-native-preflight-v1-20261104/README.md) remains recorded. This successor requires its own original owner/kernel records and native execution. Neither steady state nor manager exit after a durable terminal proves actual reply loss or effect-before-terminal recovery. See the [file index](evidence-index.json) for exact byte identities.
