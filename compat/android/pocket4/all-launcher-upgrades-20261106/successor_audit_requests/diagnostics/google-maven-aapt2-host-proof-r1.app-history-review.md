# Independent static review of official AAPT2 host preparation

Reviewed locally on 2026-11-06. No host/remote tool, APK, Android namespace,
Main lock or UI operation was executed by this reviewer. No candidate file was
changed. **No blocking static defect was found in the reviewed new body and
limited binding/stager changes.** This conclusion does not substitute for the
actual host result, complete stdout and durable terminal.

## Exact candidate

`google-maven-aapt2-host-proof-r1/prepare_official_aapt2.py`: 49,119 bytes,
SHA256 `4ec8abf806934ba6c8bfde2b96487572d855a1f6e922bd333f413254f0b32530`.

The complete 15,098-byte new `worker_body.py`, the 1,983-byte BoundFile diff,
3,276-byte stager diff, 7,257-byte assembler and SOURCE_REVIEW were read.
All nine files listed by SOURCE_REVIEW were independently checked for exact
size and SHA256. The packet's embedded stage and stdin match the local original
files. AST extraction also confirmed:

- The 10,557-byte no-follow reader and 11,269-byte borrowed-FD ELF parser are
  embedded as exact original texts.
- `required`, `sha`, `canonical`, `frozen_module`, `EvidenceStore`,
  `in_system_library_root`, `search_paths` and `resolve_dependency` match the
  previously reviewed source definitions exactly.
- The assembled source ends with the complete exact new worker body.

## Findings

The owner-policy change is confined to the two fixed downloaded inputs. Each
must have its exact path, byte count, hash, UID1000 and expected mode. Resolve
mode is refused for these inputs. All sources, extracted tools, interpreters
and dependencies continue to require root ownership. The later full-stat and
hash equality checks retain the original UID/mode requirements; this is not a
general relaxation to arbitrary operator-owned dependencies.

The entire JAR is pinned to its actual HTTPS/checksum receipt and authoritative
successful terminal. Extraction accepts only the recorded four-member layout,
checks names/encryption/link form/compression, and opens only the root `aapt2`
member. It writes to a new root-private O_EXCL path, bounds output to 6,489,808
bytes, consumes the ZipExtFile completely so its CRC is checked, computes the
actual output hash and fsyncs the new root-owned 0500 file. No unrelated member
or existing tool is extracted or replaced. A failure leaves owned partial
evidence and does not proceed to candidate execution.

The static ELF traversal retains finite file, byte, graph and time bounds,
closed system-library search paths, unique dependency resolution, held file
and path-alias checks, and rejection of additional loader directives. It
correctly labels the graph as static analysis, not observation of the dynamic
loader's mappings. The first use of the candidate occurs only after all held
files have been rechecked and enough total budget remains.

The source binds the exact original `audit_successor_apks.py` runner
(29,242 bytes, `faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a`)
and supplies exactly `[candidate_absolute_path, "version"]`. This is path
execution with a concurrently held and rechecked file, as the report states;
it is not described as fd-exec. No APK, help, Android or Main command is passed.
The command row is retained before execution; actual return code, output
completeness, normal joining, pipe closure, timeout and retirement errors are
checked. Final file checks, owned FD closure and whole-process FD identity
restoration remain necessary before the outer result can be successful.

## Acceptance limits

`result.json` is written before the evidence-directory descriptor closes and
therefore remains an intermediate artifact. Only complete final stdout plus
the authoritative durable zero-exit terminal can accept this host preparation.
A version-command failure, failed closure or partial stream must remain a
failure. Existing b05 and other failed parser observations remain unchanged.

Even a successful actual version run establishes only this exact official
host-tool preparation. It does not establish Calendar resource compatibility,
APK integrity, permissions, business behavior or production readiness. A later
Calendar/Fcitx comparison must bind the actual new file/dependency/version
receipt and terminal to its independently held exact APK/current runtime
scope. No such comparison was run or claimed by this review.
