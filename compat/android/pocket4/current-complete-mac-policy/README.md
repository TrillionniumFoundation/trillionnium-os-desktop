# Complete CP3A policy reconstruction and verification

This capsule preserves the saved complete policy, a fresh strict reconstruction, the official inputs and the actual verification programs and logs. The reconstruction exports the saved policy's full effective CIL using the pinned official libsepol, keeps those effective grants unchanged, restores the original CP3A type and attribute closure, and checks every original assertion plus explicit private-loop assertions.

The two policy binaries have different bytes. The fresh result is not presented as recovery of the missing historical authoring code.

## Exact policy identities

| Item | Bytes | SHA256 |
| --- | ---: | --- |
| Original saved complete binary | 760,303 | `4ffcd33846438bf2ced8ad1331c8e60233529ab033a683c2e1188e714471c730` |
| New strict rebuilt binary | 764,720 | `f0f9448e374771bdacd8fe4ecdc861b8e2a3d8f01970b976f4fed412e3c52d09` |
| Complete capsule | 5,474,575 | `a0a2b9312ac2a3c161511c6e32fbeb6269f7832abf7d015692d3797611c69eca` |

The seven CIL inputs were freshly read from the whole-hash-verified official CP3A system image. The official libsepol source is pinned to `a8c5e74f85f869bf236a01ba24181b78f5e39a52`. The capsule includes its actual source and build, reconstruction programs, both policy binaries, full ordinary and negative verification inputs, and their actual results.

## Actual verification

Strict compilation passed with 2,151 concrete types, 3,013 attributes and aliases, all 5,784 original neverallow assertions and 17 explicit private assertions. The exported effective grants were not edited. Each policy binary passed the 56 explicit access-vector and transition cases; the programs also checked every one of the 65,536 ioctl bits for each tested device against both binaries and checked named transitions.

Six independently injected CIL violations each produced the expected nonzero strict-compiler result and no successful output policy. The full input and output bodies are preserved, alongside the earlier binary-negative checks. Root independently verified all 136 regular archive members, the 135 frozen body hashes, exact safe names and modes, and held-file/path bookends.

These are actual offline policy decisions and compiler results. They do not establish a successful live-kernel policy load, a final vendor composition, a running Android guest or application readiness.

## Historical limits and next consumer

The old authored R9 assertion text, original derivation program, original 56-case source and lost Cloud offline1 logs remain unavailable. The newly authored tests explicitly restate the checked contract; they are not labeled as recovered historical tests. The original saved policy remains a separate identified binary.

The next production consumer must compose and verify the final selected vendor and runtime inputs, then perform the original live MAC, process, socket, init and APEX checks. No host provider-order change, permissions bypass, permissive-policy shortcut or Ready receipt is supplied by this archive. `SOURCE_FREEZE.json` and `ROOT-VERIFICATION.json` state these boundaries explicitly.
