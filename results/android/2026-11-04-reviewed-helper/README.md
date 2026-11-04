# Reviewed Pocket4 helper: actual bounded evidence

The source tested here is commit `5e70377956f585fdb9763d49a709841dc79d5924`,
tree `5e3b9f66ad07d428e994a5526fb63b030b475066`. The original execution
was made against that staged tree, which was published without changing any
file and then imported as the exact Git commit. The subsequent Pocket4 probe
uses the adapter and transport bytes from that published source.

The [manifest](manifest.json) retains original Runtime job identities and full
terminal output accounting. Execution, test logs, actual Java compiler
qualification, original-resource unsigned APK build and actual Pocket4
read-only qualification are retained as exact bytes with their original hashes.

| Gate | Actual result |
| --- | --- |
| Normal / optimized focused tests | 79 / 79 passed |
| Mandatory source inventory | 85 required files, 93 checked, no errors |
| Actual SDK 35 Java compilation | Passed |
| Original-resource unsigned APK | Built; original signer independently verified |
| Unsigned candidate signature | Invalid, as expected before signing |
| Current Pocket4 legacy helper | Exact reviewed 36,401-byte source pinned |
| Pocket4 read-only identity | Passed through original operator target |
| UI observation / device mutation | None |
| Same-signer installation / native effect / original-owner acceptance | Unqualified |

The generated strict helper is `a174edf91810b7dacb941ae3b3258457aefd2ee82f428d382a436f2ecedc36f2`.
The unsigned APK is `e32995b4d135b78d704c0f43ef35337b7360cadcb85508c626c637a6f270f4a1`.
It preserves the independently verified original binary manifest/resources.
The unchanged Java sources produce the same unsigned APK as the previous
frozen-source build; the helper's reviewed derivation changed independently.

This evidence does not qualify production Android writes. The host effect
guard remains closed. Original signing material, an installed strict receiver,
the retained authenticated original Runtime peer, the exact Android effect
lease and original FinalUse composition remain required. No key/password was
read, no APK/helper was installed and no application was launched.
