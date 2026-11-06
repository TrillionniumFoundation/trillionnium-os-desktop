# Fixed reader for the completed task 878 inspection

This is a host-only reader candidate, not a new QA command. The completed original
job is `1a1b2537fa5-fc05-7d8c`: its two original stdout lines total 14,794 bytes,
SHA-256 `11a958010bb7dbaa4865385018a72fef9d6abe12b378805da84f3006fd4f25c3`.
The actual controller terminal is complete, durable and exit 0. Its original
733 bytes are embedded unchanged and SHA checked. This terminal was already
read by the root agent; the reader does not claim to query the controller again.

The operator `file_info` attempt on the original assessment received EACCES.
No permission or ownership was changed and no binary read was attempted. This
candidate uses the existing authorized root host execution boundary to read
only the exact completed files, without any Main operation.

## Frozen historical scope

- Flow: `/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe`.
- Step: `inspect-new-session-01`; task 878; Beike UID 10143; helper UID 10157.
- Inspect nonce: `8f3efa4249d24d303984ec1887d5914b`.
- Wire SHA-256: `cb49f560bdc90f13fa5a314019e4f2948d4c9e63e3b62571c8f0a4cc37fe4647`.
- The 13,629-byte joint artifact has SHA-256
  `7ad76e72aa20919fa8695899c27233b89a9794e0446379db9f282553b671f9dc`.
- The original 6,362-byte step result has SHA-256
  `4979b991b411d2d5f2eca82e5130faeef871a1796d0bd5502aeef18c468fd8b9`.

Exactly 21 fixed host files are read: five pinned source files; the actual joint,
step result, scope, launch scope and plan; and eleven exact step files covering
the intent, held binding, nonce request/assessment, command-005's four files and
transport-006's three files. No directory scan selects evidence and no other
flow, window dump, user data or APK is read.

The five source files are the actual root read utilities, offline evidence core,
pure `qa_contract.py`, original transport definitions (only environment validation
is called), and the original owned UI source (read for identity, not executed).
The bootstrap is byte-identical to the previously executed frozen reusable UI
source. No `Flow`, `Session`, `HeldTarget`, guard, native command, subprocess,
namespace entry or instrumentation is instantiated or invoked.

## Verification

The reader recomputes the actual parent stdout from the pinned joint artifact
and original stage line and checks its full original hash. The result explicitly
calls this deterministic reconstruction, not a fresh remote stdout read. It
checks the held-pidfd normal exit evidence of the historical child 1308652 and
the original adapter result, helper build/signature/APK and installed UID evidence.

The reader verifies the recorded command's exact seven authority descriptors,
parent PID, clean environment, classpaths and instrumentation argv. It requires
normal joined exit 0 and the matching original transport intent, command result,
lease release and post-guard receipt. The **unchanged** `qa.parse_completed` then
reparses `command-005.stdout`, checks the nonce and helper UID, and recomputes
the saved assessment and fixed wire hash. The original complete tree/node hashes
are verified before any node summary is emitted.

All parent components are opened with no-follow semantics. Each final file must
be a bounded, root-owned regular file with one link and no group/world write.
Its full bytes and stat are rechecked after all validation. Initial and final
whole-process FD identities must be equal. The complete finite read set is at
most 4 MiB, with a 90-second internal bound and 120-second process bound. There
are no child processes, signals, locks, file writes or automatic retries.

## Privacy and meaning of the output

**The successful stdout contains private UI node text. Do not put it in Git.**
It emits every recorded visible, non-password, unredacted node with its original
strings and original truncation flags. It never silently truncates strings.
Password or invisible nodes are omitted; their count is reported. A field that
was originally truncated is explicitly ineligible as an exact selector field.
The output is bounded to 1 MiB; excess output causes rejection, not truncation.
Raw instrumentation and original tree bytes remain in their existing root-private
host paths; the reader neither copies nor modifies them and does not write a new
private bundle.

The output is a read of the **historical completed observation**. It does not
prove the current foreground or grant current mutation authority. Any subsequent
plan must still use the unchanged original helper's fresh inspection, foreground,
runtime/App/task/UID guards and Flow UNKNOWN gate. The original task 876 UNKNOWN,
Bili boundary, Meituan permission restriction and production count remain unchanged.

## Local preparation and execution boundary

`prepare_packet.py` was run locally once. It bound the actual Python-decoded
original evidence without JavaScript integer conversion, inserted the exact
frozen bootstrap, compiled the reader and created the fixed process request.
It is deliberately one-time: the finalized reader has no placeholders and the
packet/proof files are created with exclusive mode. Do not rerun it on the
finalized source. The five small local controls cover Unicode preservation,
password/invisible exclusion, truncation handling and exact packet scope; they
do not claim to have read the target's private tree.

The root agent must review `read_completed_inspect878.py` and
`process-request.review-only.json` before one submission. The packet invokes
`sudo -n /usr/bin/python3 -I -B -c <exact source>` with no stdin, one new fixed
idempotency key, CPU 100%, 256 MiB memory and 120 seconds. No remote submission
has been made by this agent. Success requires the actual complete stdout plus
authoritative durable exit 0, not a local control result or source review.
