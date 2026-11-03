# Android original-device adapter: source and read-only qualification

## Exact scope

The adapter implementation at OS commit `4ccdc5a82975d56daaf9a0c8fe11620ab534e394`
(tree `95c1d38cbe2c7cb750e0d45dfed7fa8ab1e203ac`) passed an actual, read-only
qualification through the original Runtime operator target `pocket4`.
The receipt has 12 successful identity checks, no timeout, no retries, no UI
observation and zero device mutation attempts. Runtime job:
`1a167299965-1b6abb-3599`.

This qualifies the adapter's measured connection to the existing Droidloom
Android 17 / SDK 37 cell. It does not qualify a physical handset, Android on
Asterinas, ARM/BSP support, an original Hepta production effect owner, text
entry, clicks, app installation, or semantic action receiver binding.
Those fields remain explicitly false or `NOT_CONFIGURED` in the actual receipt.

## Measured deployment

| Component | SHA256 | Required / observed UID |
| --- | --- | --- |
| privileged helper | `8c9856a3791f0a208e59b00137547466c9f84d3a60d7a2cae700980de43f677b` | root / 0 |
| original Droidloom control | `aa1e415db5ddb865f600b0b201e5eea83715efab8d9c0db86902b568ec539376` | explicit original operator / 1000 |
| adapter | `d9e98427399533ab63fdd0d4aba2b903aa2adaae139c26bd4a18754a12a01973` | exact source bytes |
| bounded transport | `a203095a8e68460c3188e9b2cbd1fc3015cd7a8f7ed32e0a50b311615c725cea` | exact source bytes |

Both original tools were regular executable files with mode 0755. Their
ownership and permissions were not changed. The privileged helper remains
root-only. The control UID defaults to root, and an explicit alternative must
equal the original operator's actual effective UID. No UID or source hash is
learned from a device reply.

The positive invocation and raw receipt are under `pocket4/v2/`. The raw
qualification stdout SHA256 is
`8355d41b41a1bf16c336fc4933335b6f53045e53880c70ab3f3e376d0e4847df`.

## Preserved failures and source verification

The initial implementation at `16661308ee95547e7a479ec88954b12dbd9d4eca`
assumed a root-owned control executable. Its actual `pocket4/v1/` receipt
correctly rejects the UID-1000 control before attempting any transport
(`UNTRUSTED_TOOL_FILE`, exit 2). The explicit owner pin fixes that deployment
mismatch without widening the helper's authority.

The final source passes the complete A08 source-integrity check: 76 checked
files, 68 required files, zero errors. Its 20 adapter tests pass both normal
and optimized Python execution. The existing source-integrity regression
suite also passes. Tests cover tool pins/ownership, bounded output and time,
cleanup of a pipe-holding descendant after its leader exits, strict JSON,
conservative unknown outcomes, exact UTF-8 intent binding and rejection of
effect calls before privileged transport.

An initial attempt to invoke the repository test directly with Python `-I`
failed to import the repository's `support` package before any tests ran.
That failed invocation is retained in `source-gates/v2/`. The unchanged
source subsequently passed using the repository's unittest discovery entry
point with bytecode writes disabled; see `source-gates/v3/`. The full source
integrity result from v2 remains applicable to those identical bytes.

## Evidence identity and reproduction

`manifest.json` records every retained raw file, its original path, byte length
and SHA256. Files copied from pocket4 were hash-checked again on the repository
host. The archive commit adds evidence only; it does not relabel the executed
source commit or claim runtime qualification for a later source change.

The read-only adapter's documented command is:

```sh
python3 -B support/android/device_organ.py \
  --droidloomctl-sha256 aa1e415db5ddb865f600b0b201e5eea83715efab8d9c0db86902b568ec539376 \
  --droidloomctl-owner-uid 1000 qualify
```

Run that command only through the original, explicitly selected operator
target. The adapter's measurement is not hardware attestation and does not
establish the authority of an arbitrary host with the same file paths.
