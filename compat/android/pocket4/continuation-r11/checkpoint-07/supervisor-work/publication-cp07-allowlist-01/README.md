# CP07 LMKD/supervisor source and evidence selection

This is a UTF-8 allowlist for the next additive repository checkpoint. Its parent is `bef03784ba3fb4948cef0b128092bda769a6364b`; the parent's 1,858 payload files are retained unchanged. This directory does not perform Git operations. `allowlist.json` gives local relative paths, exact byte lengths and SHA-256 values. All selected original files retain their original bytes.

## Actual host evidence

| Revision | Supervisor Rust controls | Relay Rust controls | Ordinary IPC controls | Exact receipt SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Core01 predecessor | 103 | 23 | 7 | `bd5e2d48769b8ec69791178695831fa13d30b437f0cb668ee6a8a6eed05eb97e` |
| Peer02 predecessor | 109 | 23 | 7 | `edd9e0d07e967f9c0a2743235e49a824cc4331e2351a67f6e77e61c3da19e9c7` |
| Producer03 | 118 | 23 | 7 | `cc0209eca13b637a47ae0a7b397f56071baaaca650bd34576ab1f5aa9c6f4bc1` |
| Producer04 | 121 | 23 | 7 | `0a8db6485bd5352d120365c921a67d8d7332d6205c9609860390b996deb3ba5e` |
| Producer05 | 122 | 23 | 7 | `1623811c108a7cac8af3460d828c063ed9e7064519d2d4e41d70bce4ab25e64c` |

The original frozen manifests and validation text describe the state at their freeze times. They are not rewritten after a later matching build. The raw successful build receipts provide the later results and before/after input hashes. Some submitted Rust modules were subsequently formatted by the matching builder; the submitted-file SHA and the compiled-file SHA must not be conflated. This selection contains source overlays and their receipts, not a separately materialized complete build checkout.

Producer04 preserves a generation's runtime failure after successful retirement, fixes generated LMKD service-line indentation, and restricts the final init command to direct `/init second_stage`. Producer05 selects absolute native ip/unshare for the explicit relay path, retaining the original argv for a None policy. The actual compatibility shim source proves that its extra `subprocess.Popen` does not preserve the inherited four-descriptor contract. Source/read-only tool evidence is included; none of these statements claims that the new installed startup path has run.

The host-prefix preparation really compiled the frozen C probe and passed 40 Python controls and six native ordinary controls. Its complete receipt is 11,910 bytes with SHA-256 `1e70d9df93309ff5be991f0a20e4b5b4493e57a0b64fcc3881075e652a5ae712`; the actual probe SHA-256 is `79b30f9fa4a1e7635ae4786a50372b3fcaa84ad619269476e40a1badd65c0e82`. Source bytes match before and after. The fixed root reader returned those exact bytes, independently SHA-verified by the client. There were zero namespace, runtime-unit, network, Android or Main actions in that preparation.

## Failure and review history

The frozen prefix source includes the initial local interpreter-ownership/PID-view failures and the actual unexpected-SCM_PIDFD leak reproduction, together with their original source and the correction. The final source explicitly owns and closes unexpected received descriptors before rejecting them. Ordinary host tests do not establish namespace or Android behavior.

The narrow Bilibili frontend review is included as an independent source-review receipt. It covers the once claims, original action lock, retained primary failure and unchanged cleanup AST. It performed no device, UI or audio operation and does not grant commercial-app acceptance.

An earlier pre-producer first-compile failure receipt has not been recovered into this local allowlist. It remains an explicit missing historical artifact; no later successful receipt is presented as that original failure. The source closure inventory and this selection's exclusions make that limitation reviewable.

## Normal plan snapshot: NOT_SUBMITTED

At this checkpoint's selection time, both requests for the concrete fresh normal prefix plan are **NOT_SUBMITTED**. The plan SHA-256 is `dd9c420ae36678e3dc6fc4cbac4b08730a133a6b4b37ae11496c6f4b46babaef`. The plan changes only the frozen example's fresh nonce and actual compiled-probe digest. Its original Main identities are historical observations that must still pass the live read-only held-identity check before execution.

The normal plan, human-readable stage template, fixed preflight reader, direct execute request, validation and original manifest are selected. The instantiated stage source/request contains a base64 transport copy of the plan and is excluded; its exact original hashes remain in the frozen manifest. No secret, executable binary, APK, archive, cache or commercial raw log is included. `exclusions.json` records those deliberate transport/duplication omissions.

Full prefix execution, actual Rust Owner entry, real Android init constructor/HELLO/READY/COMMIT/enrollment, abandoned-generation recovery, installed activation and commercial-app gates remain open. The init-barrier source and matching Android DSO build were already delivered in CP06 and are not duplicated here. Native expiry and pressure thresholds remain unchanged; previous pressure qualifications retain their original narrow scope.
