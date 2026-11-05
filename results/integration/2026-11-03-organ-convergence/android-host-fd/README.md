# Final fd8 Android candidate: real host build, unsigned only

Source: Desktop `fd8d56c52b971c2d5d0e6430f296803b43ef60a3`, tree `347fbb7e9931006c749b5bef0e1550c54bc08f27`. The selected Hepta revision is `a39a0871d9601ffccb5e0d95d8f39d54b3a63360`; this build does not execute Hepta or confer original-owner device-effect qualification.

Remote job `1a1a22b7b68-96a-72fd` completed with exit 0 on configured host `main`. Output is `/data/trill-organ-android-fd8-20261103-kqt0e83g`. The isolated source checkout was clean before and after; all 172 tracked Android-related input hashes matched. The shared e1 source and deployed Android helper/APK were not modified.

## Executed checks

The unchanged `support/android/verify_host.py` passed all 257 offline tests and its real Linux C ABI and Java/JNI stages. A separate complete normal discovery and complete `python3 -O` discovery each ran 257 tests, all OK with zero skips. Their full named transcripts are retained. Existing Python 3.12.3/Pillow 10.2.0/Java tooling was used; no package installation occurred.

Java-only compilation, actual Java-to-DEX/unsigned APK build using the original APK resources, `aapt` package/version comparison and `zipalign -c 4` all returned 0. `apksigner verify` on the unsigned candidate returned the expected 1; this is an unsigned-package rejection, not a signing pass.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `unsigned/aligned.apk` | 19,402 | `e32995b4d135b78d704c0f43ef35337b7360cadcb85508c626c637a6f270f4a1` |
| `unsigned/dex/classes.dex` | 36,048 | `8afb8f4d5d5fdc9196e5e07756a3511d180bd825118a666c5ed3aa6db0f83394` |
| `unsigned/android-digitalis-observe-helper` | 49,912 | `3ff39160bad934df9a2e1057fd1c4f3c1e09d6377bb0c129ca4cb6fd85e8af7c` |
| `unsigned/build-record.json` | 2,537 | `3304ed22c985cadb5d2a314f3de3d09f8ec851b6bf4165142a7eb1a6be4dc57d` |
| `qualification.json` | 68,009 | `bcf64cd09e50f82bff9ca1bd1dcb629405ba3c9bf2c3134150e2452e3709dd87` |

Only the small raw receipts were copied locally. The APK, DEX and generated helper remain in the isolated remote output. Every copied raw receipt was verified against the returned size and SHA-256; the 68,009-byte qualification was read in two version-pinned chunks and reassembled without changing bytes. `receipt-index.json` records those identities.

## Original inputs and exact helper derivation

Original APK: 20,847 bytes, SHA-256 `a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058`, certificate SHA-256 `7c36bafbdb2789384aeae9dabf69cca6b468f6c1a2d75952ab315288b77ff7f7`. The retained original resources keep package `local.pocket4.actions.v2`, versionCode `2`.

The generator first verifies the frozen helper preimage `8c9856a3791f0a208e59b00137547466c9f84d3a60d7a2cae700980de43f677b`, performs the one exact legacy Enter keyboard-input-source edit, then requires the full intermediate hash `196fbfe525e9813a79a1582994445c63929f2998448d46ebee7c9ac582f66eec` before composing the strict organ extension. It does not import arbitrary live drift. The legacy three-command regression uses mocked transport only.

## Qualification boundaries

Binder is `binder_blocked_no_device`. The Asterinas source gate remains `source_review_blocked` for Binder, seccomp and MAC, with both kernel and Android runtime verification false. These Linux host passes do not qualify Android on Asterinas or a real phone effect.

No key/password was read, replacement key generated, APK signed or installed, live helper overwritten, Android cell restarted or phone UI operated. Only the documented historical keystore path was checked by metadata on `main` and `pocket4`; it was absent at that exact path. This does not claim that no original key exists elsewhere. An original signer and an explicitly reviewed device qualification remain required before deployment.

The old e1 focused and full-host receipts remain separate and unchanged. In particular, the e1 full-host outer wrapper exit 1 caused by its incorrect expected count of 240 is preserved alongside its independent count-review: the three original test commands actually passed 256 tests each. The fd8 build uses the correct 257-test expectation and its outer job returned 0.
