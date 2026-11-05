# Fresh NOFILE host controls, recovery03

This is a newly written 26-case host harness using the exact recovered production candidate and preimage. It does not restore the lost unpublished harness or inherit that harness's results. The candidate core and the 18 recovered inputs remain byte-for-byte pinned to recovery02; this revision changes only test code and evidence.

Fourteen existing R21 case function bodies are reused unchanged. The only edit to their full translation unit is a conditional include selecting the exact raw owner candidate or preimage. Twelve new cases address already-admitted ordinary descriptors under RLIMIT_NOFILE 0/1, warm address-space exhaustion, error atomicity, private and shared descriptor tables, clear-tid restarts, and fork boundaries.

Each positive run uses one fresh owned child per case, clears and verifies that child's capabilities, preserves the parent's capabilities, and requires bounded exact child reaping, Stop, both clear-tid words, and signal-mask restoration. The full candidate expects 26 function passes; the preimage expects 15 function passes and 11 specific EMFILE failures with unchanged output. Those are expected results, not observed positive results.

## Actual local validation

`local-build-attempt-03/result.json` records strict `-O2 -Wall -Wextra -Werror` compilation of both arms, their default PLAN calls, actual root admission rejection, and final ELF worker closure audits. All these limited gates passed. The root negative control observed EPERM at Start, ESHUTDOWN at Read, unchanged output and mask, and Stop success. The positive 26-case path was not executed locally or on Pocket4. Actual host matching build, non-root controls, independent review, and Android gates are still required.

The first local compile failure and the earlier output-format revision's successful local build are retained. They do not replace the final source's validation. ELF files and full disassembly are not publication payloads; reports bind their actual SHA values.

## Remaining boundaries

Initial admission after NOFILE=0 still cannot obtain the authoritative user-namespace pin and remains rejected. A private-fork child first started after NOFILE=0 remains rejected; the already-admitted parent has a separate control. Trusted virtual-file O_PATH reopening, factory-positive metadata, production ART lifecycle, arbitrary credential/root/mount/namespace transitions, and actual Android final binaries are not qualified by these host controls. No Main, commercial-app, service, or policy actions were performed.
