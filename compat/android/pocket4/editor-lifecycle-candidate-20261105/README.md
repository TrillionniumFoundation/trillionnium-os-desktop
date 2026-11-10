# Editor lifecycle candidate: exact installed DEX, host verified

The installed EditorContract app refuses a normal Activity configuration replacement
because `onCreate` treats its existing claim and journal as a duplicate run. This is
a source-proven lifecycle gap. The old device tests used a new nonce after normal
task closure; they did not exercise configuration recreation and remain valid for
that narrower scope.

This candidate patches the six hash-pinned installed smali classes and adds a small
Java ownership/snapshot implementation. It does not claim to recover the original
Java source. The Activity obtains a one-use ticket only from the framework's live
nonconfiguration-instance channel. The replacement retains the same AtomicFile,
event array, creation timestamp, editor-action count, connection count, dropped
event count, plain UTF-16 text and selection. Text restoration occurs before the
editor listener is installed, so restoration does not synthesize Enter actions.

Every journal write and counter-changing input callback takes the same owner lock.
Detach removes the old Activity's writer authority before transfer. Only one
replacement can consume the ticket. A late old `onDestroy` cannot close the new
owner. The six original input/journal method bodies remain verbatim behind these
wrappers; three of the original six classes remain byte-identical in smali source.
The original manifest, resources, permissions and durable claim policy are not
rebuilt. No claim, journal, nonce or previous session is removed or reset.

## Actual host result

The unique build job `1a1ac9198f4-fc05-5560` completed with exit 0 and complete,
durable stdout/stderr on 2026-11-05 from 16:36:26.662900 to 16:36:32.568696 UTC.
`build01-result-original.json` is the original 25,543-byte result, SHA-256
`526c1378fd32d941fd7fdfea1b77fb01bd14f2a172a5557f195f95bd300f17a7`.

The build used the real SDK 31 `android.jar` and pinned Java/D8/smali tool closures.
It compiled the production Java sources, ran 22 single-writer checks and 21
retained-snapshot checks, converted the new code with D8 min API 26, assembled all
10 classes and 48 methods into one DEX, then disassembled it. Every class matched
the candidate's normalized instruction/annotation/register/exception-coverage IR.
The four added classes include the compiler-generated `SessionOwner$1`.
All source/tool hashes were rechecked after the build.

The new DEX is 16,496 bytes, SHA-256
`e2876293676838dbeec4dd61000aec9450226ae2b5c0671f21a4b252b91744ff`.
The build had one CPU (CPU 20), a 512 MiB memory cap, zero swap, and 128 tasks;
recorded peak memory was 504,803,328 bytes and all OOM counters were zero.
The host tests call the production classes. AtomicFile and JSONArray are explicitly
test-only identity shims; they do not simulate Android lifecycle, storage or JSON.

## Explicit limits and remaining work

- No APK was packaged or signed, and no candidate was installed. There were zero
  Android commands and zero UI inputs in this build.
- Real Activity recreation, current ART verification, IME composition and repeated
  device lifecycle behavior remain untested. Assembly and host tests are not those
  runtime qualifications.
- The transfer preserves plain text and selection. Active composing spans are not
  transferred by this candidate and remain a separate editor gate.
- Process death removes the in-memory ticket. A process restart therefore follows
  the original claim refusal and preserves the old journal; it does not silently
  reopen an old writer. New Intent delivery never transfers ownership.
- The original signing key has not been located. Bounded existing host-source
  searches found no confirmed original source/key, and Personal Context reported
  unavailable. The ZIP entry `JNI-ONLO.RSA` is not evidence of a particular key path
  or alias. No different certificate will be used to replace this installed app.

The installed APK baseline is SHA-256
`0d08f59024e4228e5d5b8f56742aafd1fbc04966d74224acd48542e09482743d`;
its verified certificate is
`df1808318c5ed4932aee812962be781f4946692074c998b06fbbbd0d8a3fa322`.
`CANDIDATE_STATUS.json`, `SOURCE_PINS.json`, `installed-lifecycle-recovery.patch`,
the production Java files, tests and original host receipts form the reviewable
candidate. No whole-app production readiness gate is granted by this result.
