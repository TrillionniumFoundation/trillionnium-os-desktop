# Pocket4 APK content identity

These tools bind an Android source input to its complete signed bytes, binary manifest, SDK signature verification and exact native input inventory. They produce source receipts for the normal application installer. A receipt never establishes installation, translated execution, login, a business flow, or production readiness.

## Verification paths

| Input | Entry point | Candidate |
| --- | --- | --- |
| Standalone APK with ordinary native libraries or the existing narrowly specified v3 payloads | `verify_apk.py` | Existing v1/v2/v3 candidate schemas, including the explicit no-native-directory schema |
| Complete base and split APK set | `verify_apk_set.py` | `pocket4-official-apk-set-candidate-v1` |
| Standalone APK with exact publisher resource payloads | `verify_publisher_apk.py` | `pocket4-official-apk-candidate-v4` |

Each CLI takes the original input path and the following required options:

```sh
python3 -I -B verify_publisher_apk.py /absolute/application.apk \
  --build-tools /absolute/android-sdk/build-tools/37.0.0 \
  --candidate /absolute/application-candidate.json \
  --expect-candidate-sha256 EXACT_CANDIDATE_SHA256 \
  --receipt-output /absolute/new-source-receipt.json
```

Use `verify_apk_set.py` with the original complete `.apks` container. The exact set, including required ABI and density splits, is verified as a unit. Its receipt and returned native-input fragment preserve the members' identities. Installation must later submit the complete selected set together.

The SDK `apksigner` invocation, binary manifest and `aapt2` output must agree on the externally pinned application identity. Application signing certificates and source-stamp certificates remain separate. The strongest actually verified signing scheme determines the accepted application signer. No APK is resigned or modified. Candidate and source files are held with no-follow descriptors and rechecked for identity, length and full SHA-256. Receipts are bounded to 8 MiB and published atomically with no replacement of an existing output.

## Binary manifest and split handling

The structural AXML parser checks the package, long version code, SDK fields and real root split/dependency declarations. A class or service name containing `.split.` is not a manifest split. This fixes the false rejection of the current standalone Taobao APK without accepting a real incomplete split set.

`targetSdkVersion` selects Android compatibility behavior and can be lower than `minSdkVersion`; it is not the upper endpoint of a runtime version interval. Both values still have strict type/range checks and must match the actual signed manifest. Existing support for the official platform target value 1000 is retained.

An APK without native code must explicitly use the no-native-directory candidate schema. An empty declared ABI list does not turn a legacy native schema into a no-native candidate. Every declared ABI in a native candidate needs an actual ELF header with the corresponding class and machine.

## Publisher payloads

Some signed publishers store resource containers, compressed code or helper binaries under names ending in `.so`. The v4 verifier accepts at most 64 exact payload entries, each with a literal path, format, byte length, full SHA-256 and canonical observation SHA-256. It walks the complete outer ZIP and verifies all member CRCs and bounds. Unknown or unpinned native-directory files remain errors.

`native_publisher_payloads.py` implements the bounded ZIP, version marker, WeChat CSOP/CSOS/metadata and DEX035 observations. ZIP members are read without executing code. CSOP records the Zstandard frame structure and compressed bytes; it does not claim decompression or decoded-checksum verification. The narrow Meituan versioned containers explicitly retain `body_format_verified: false`; observing their bounded headers is not a claim about their opaque bodies or native execution. Inner ZIP data is authenticated through the verified outer APK; it is not described as independently signed.

`seven_zip04_payload.py` handles the actual 12306 7z 0.4 resource form: one regular file, one LZMA2 stream and an unencoded header. It limits input to 64 MiB, header to 4096 bytes, dictionary to 32 MiB and decoded output to 128 MiB. It checks canonical integers, header CRC, exact ranges, the safe `.so` basename, regular mode, full decoding, output CRC and SHA-256, and decoder EOF. Encrypted streams, external metadata, additional files/streams, trailing data and over-limit inputs are rejected. Decoded bytes are hashed in memory; the decoder writes no extracted executable file and executes nothing. The existing v3 7z 0.3 parser is unchanged.

The two mixed-ISA v4 forms reuse the existing strict v3 interpreter-tagged ET_DYN and dual-dynamic-library parsers. They require an actual machine/class different from the directory ABI and an exact complete layout digest. Their presence is recorded as a source payload, never counted as a library for that directory ABI. These observations do not prove that the publisher's dispatch path selects or can execute the helper.

## Fresh source controls

The current local run completed all 146 cases with exit 0 and no skips under `python3 -I -B`:

| Test file | Cases |
| --- | ---: |
| `test_candidate.py` | 41 |
| `test_dual_dynamic_elf.py` | 9 |
| `test_native_resource_payloads.py` | 20 |
| `test_apk_set.py` | 14 |
| `test_native_publisher_payloads.py` | 22 |
| `test_verify_publisher_apk.py` | 20 |
| `test_seven_zip04_payload.py` | 13 |
| `test_mixed_publisher_payloads.py` | 7 |

These include malformed manifests, absent/duplicate/incompatible splits, wrong package/version/signer, native ABI mismatches, unsafe ZIP paths, CRC errors, missing or extra pinned payloads, file-identity changes, receipt limits and no-replace publication. SDK failure controls use bounded test doubles; actual publisher receipts are separate real SDK invocations. `VALIDATION.json` records the exact executed source and control results. `SOURCE_MANIFEST.json` pins every file in this component. The host workflow executes all eight test files directly, so omission cannot silently shrink discovery.

## Current signed inputs

Actual SDK 37 verification has completed for these newly obtained or replaced current inputs. Original complete APKs are kept in the current input archives, not committed to this repository.

| Application | Version | Version code | Form |
| --- | --- | ---: | --- |
| JD | 16.1.50 | 102918 | Standalone v4 |
| Taobao | 10.69.0 | 866 | Standalone v4 |
| WeChat | 8.0.80 | 3220 | Standalone v4 |
| Bilibili | 9.20.0 | 9200300 | Standalone v3 |
| Zhubajie | 9.5.20 | 370 | Standalone v3 |
| Amazon Shopping | 32.20.2.100 | 1243262206 | Complete base + arm64 + xxhdpi set |
| Air China | 7.53.4 | 75304 | Standalone v3 |
| DiDi | 8.0.20 | 1208002005 | Standalone v3 |
| Railway 12306 | 5.9.6.8 | 280 | Standalone v4 |

The latest 12306 replaces the previously acquired 5.9.4.5 input. The 16 current compatible third-party source inputs also include Firefox, Fcitx, SZZC, Ctrip, Beike, China Eastern and microG. The Companion dependency remains outside the selected 42 / required 39 application denominator. The ten official system APKs have separate original-GSI source receipts; their final image selection and runtime qualification remain pending.

Current-source availability and runtime qualification are distinct. The release scope retains exactly three exclusions: `com.enflick.android.TextNow`, `com.pinger.textfree`, and `com.ubercab`. No other package becomes exempt because a current compatible APK is still unavailable. An older version, ARM32-only variant, different package, lower-code channel variant or changed signer cannot substitute silently for the required current input. Freshness/channel differences and unresolved acquisition are preserved in the current acceptance data.

## Remaining production gates

The normal installer must verify the receipt and selected bytes again, preserve application data, reject unauthorized signer/channel downgrades, and execute on the final qualified Android image. Native translation, original policy, APEX activation, service health, restart persistence, user login and required business flows need actual device evidence. All source receipts retain false installation/runtime/production flags until those separate gates pass.
