# Successor installer revision 2 — source review candidate

This is a new source revision. Original revision 1 and the JD rejection remain unchanged. Nothing in this directory establishes that a candidate was installed or that Main is business-ready.

## Changes requiring review

- Add only com.ss.android.ugc.aweme with the reviewed HTTPS host imtt.dd.qq.com. The same official verifier, current signer, monotonic version, complete 46-package scope, native owner and data identity checks apply.
- Retain the single-base predecessor rule for every existing target. The only added multi-APK predecessor is com.jingdong.app.mall, UID 10126, versionCode 102810, and exactly the two observed filenames, byte lengths and SHA256 values hardcoded in REVIEWED_JD_OLD_APKS. A different UID, version, package, filename, third APK, or bytes is rejected.
- Calculate retained capacity from the sum of all old APKs. Open and compare every old APK's full stat; copy every old APK to a new immutable private file. The v2 install scope lists the complete original and retained sets. Existing data is neither read nor copied.
- Before writing an installation intent, invoke the existing fixed host aapt dump xmltree through its held executable FD against the held verified private candidate. Record raw stdout/stderr, hash and recheck the candidate, tool, resolved tool path and dependency file before/after. Require a decoded single manifest root without a split/configForSplit marker, a uses-split element, or a true isFeatureSplit/isSplitRequired flag.
- The owned process runner gains only optional host-tool path/output-limit metadata. Every existing native call retains the original defaults and arguments. The native install command, receipt checks, post-install all-46 readback, exact signer/UID/CE+DE identity, non-target package preservation, Meituan saved location comparison, Bili UNKNOWN pins, and late-UNKNOWN/no-retry logic remain unchanged.
- The final result still requires exactly one installed APK with the exact complete official candidate hash. The daemon retains its original signature, package-manager and platform integrity checks. No install-multiple, uninstall, -g, -d, UI, ADB or lifecycle command is added.

## Interface and evidence

The immutable request remains pocket4-successor-single-native-upgrade-v1. New install scope schema is pocket4-successor-explicit-install-scope-v2 with old_apks, retained_old_apks and complete_candidate_manifest. The result uses previous_apks_retained (a complete list) in place of revision 1's singular previous_apk_retained.

The new host parser controls use explicit synthetic aapt output. They are not production APK evidence. One control runs two owned local Python children through the same held-FD runner to prove output capture, successful/failed exit joining and descriptor closure without reading Main. Root must independently review this source, actual host test outputs and the official candidates, then stage a fresh root-owned source and request before any new runtime action.

The earlier JD job 1a1b1068699-fc05-750c was reported by root as durable failed/exit1 with action_attempted=false, commands=[], all FDs closed. A new JD request may be considered only after the coordinator has retained its authoritative no-action/no-intent evidence. This source does not rewrite or retry that job.
