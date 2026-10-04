# Managed evidence consumers

Five source tools consume `artifact_evidence.open_managed_file` directly:
D1 semantic snapshots and their complete retained readback, the D2I source
archive, resource-gate JSON and origin bytes, native-owner preparation inputs,
and S08 semantic source/patch/result inputs. The reader retains its private
descriptor owner through metadata, reading, context exit and object delivery.
These reader bodies neither pass a raw integer to `os.fdopen` nor expose a
borrowed descriptor. Existing raw opener aliases remain available for import
compatibility and are unused by these migrated bodies.

The precise existing reader signatures, bounds and source inventory are in
[`managed-evidence-consumers.v1.json`](../../contracts/managed-evidence-consumers.v1.json).
The underlying context/thread/process and cleanup contract remains
[`shared-managed-reader.v1.json`](../../contracts/shared-managed-reader.v1.json).
This package adds no peer, principal, signature or execution authority.

D1 payloads retain the 8 MiB limit and contract input the 64 KiB limit. Its final
scan keeps every managed reader in the existing `ExitStack` until all retained
metadata and named leaves have been compared. Resource evidence retains its
128 KiB limit and origin 64 bytes. Native source remains bounded at 2 MiB;
S08 source, patch and result limits remain 1 MiB, 256 KiB and 4096 bytes.
Existing single-link, no-follow, readback and strict parser checks stay in place.
Artifact JSON and digest limits remain 8 MiB and 8 GiB.

D2I now reads `source.tar` into at most 64 MiB of immutable bytes through the
same retained reader, comparing actual count and metadata before closing.
`tarfile` seeks in `io.BytesIO` over those bytes, and the receipt archive digest
is computed from those exact parsed bytes. This replaces the prior streaming
archive reader; larger source archives are refused before payload reading.
There is no disk extraction, decompression or added archive authority. Member
types, paths, duplicates, sizes, modes, content digests, reconstructed Git tree
and workflow bindings retain their existing checks. The full packet verifier
also checks output digests. A subsequent full-packet verification refuses a
substituted archive whose current bytes differ. A valid parsed snapshot is not
a promise that the pathname remains unchanged after the observed read checks.

The local regressions exercise managed opener/result loss, read/stat public
exceptional context reentry, real native close followed by integer reuse and
GC, no-follow special-file refusal, actual mutation during reading, original
Git archive builder/selector behavior and the whole-archive byte bound. Native
`open`, `read`, `close` and `dup2` calls in those FD tests are real. The two older
resource swap tests and D1 predecessor readback test update only opener seam
names, retaining their original path replacements and refusal assertions.
These tests provide source I/O evidence, not Servo, QEMU, boot or hardware
qualification. Product activation and `production_ready` remain false.

The old raw-integer APIs remain compatible and their raw return/caller
`fdopen` delivery gaps remain open. Other namespace, input, checkpoint, shell,
release and external raw consumers are outside this migration. Neither this
package nor the managed dependency promises every native call, opcode or
repeated cleanup interruption is protected. Caller use of private fields or
manual destructor invocation is not a supported reader operation. A source
contract is not an approved runtime diagnostic or production signing fact.
