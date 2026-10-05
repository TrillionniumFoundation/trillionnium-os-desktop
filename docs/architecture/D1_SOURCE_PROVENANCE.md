# D1 portable source identity

This is a source candidate. The v4 D1 receipt requires a carried source tar and
the raw tested Git commit. The reader rehashes both payloads, rebuilds every Git
blob and the complete tree from regular source bytes and executable modes, and
recomputes the raw commit object ID. It binds the commit tree to the receipt.
For a PR, the commit must have exactly two parents in base/head order. For push
and manual checkout lanes, the recorded base is the first parent; a root test
fixture uses the zero SHA. The permanent production qualification runner still
requires a real parent. Producer workflow hashes remain bound to the same source
manifest and tested commit. No locally available Git objects or network call is
used by the offline reader.

The actual earlier v3 packet accepted an otherwise unchanged receipt whose tree
SHA was replaced by forty zeros. Source SHA256 maps alone cannot reconstruct a
Git tree or bind a commit, because they omit Git blob object IDs and modes. v3
has no qualified compatibility fallback. Historical v3 packets remain historical
evidence and require a new exact-source workflow run for v4 qualification.
The D2I finalizer requires the same v4 D1 subreceipt, in addition to its existing
independent source-archive tree check. A source-only retrofit of an old packet
is a decoder probe, never a new image-build or guest-run qualification.

## Bounds and refusal

The source archive is uncompressed tar, inspected without extraction. Its
payload is at most 64 MiB, the raw commit at most 1 MiB, and each tracked source
file at most 8 MiB. At most 4096 files, 4096 UTF-8 bytes per path and 64 path
components are accepted. Every manifest path must occur exactly once. Links,
special files, unknown file names, duplicate members, unsupported Git modes,
missing source inputs and file/directory conflicts are refused. Empty directory
headers and non-executable tar metadata do not create tracked Git objects.

Proof reads retain their private descriptor owner through the whole bounded
read. The owner is never returned as a raw integer or exposed as a public
reader. Reads reject symlinked ancestry, nonregular files, multiple hard links,
oversized files and changes to file metadata or byte count during the read.
This does not claim atomic hostile filesystem snapshots, C-call or opcode
interruption safety, repeated cleanup-fault safety, or privacy against arbitrary
inspection of private Python frames. The historical external raw-FD consumer
gap remains separate from this decoder.

## Evidence limits

The checks establish internal consistency of carried bytes, Git modes, raw
commit identity and ordered PR parents. They do not authenticate an external
repository, GitHub run, human reviewer, signature or release authority. An
independent reviewer still binds the official artifact and run metadata to the
live expected PR/main identities. Rebinding all bytes to an entirely different
valid Git commit is not proof that GitHub tested that commit.

The packet still omits full rootfs/ext4/kernel/initrd and executable binary
payloads. Their carried metadata is compared but absent payloads are not
independently rehashed by this reader. Same-run two-build identity does not
establish cross-run or hermetic reproducibility. No product AgentPort activation,
new native runtime, installed image, hardware, signing or release is authorized.

## Tests and changes

`tests/test_d1_source_provenance.py` executes native Git for its tree/commit
oracle and tests receipt-only identity changes, fully rebound archive bytes and
modes, raw commit mutation, ordered parent failures, unsafe tar entries, strict
bounds and optimized-Python CLI refusal. Existing D1/D2I adversarial tests keep
their original assertions. Their shared fixture now carries valid source bytes
and an actual raw Git commit instead of an invented tested object ID; the real
D2I-finalizer fixture refreshes its proof from the actual private test repository.
The original D1 portable semantic and image claim ceilings remain in force.

The directory-bound successor validates raw exposed tar/PAX path bytes before
removing one optional directory terminator. Only ancestors of declared files
are allowed as directory headers. This rejects a directory nested beneath a
regular file in either order and repeated PAX terminators that previously hid
an overlong spelling. Actual ordinary native-Git directory headers still pass;
untracked empty directories cannot add source-tree structure or bypass checks.

The reader also checks physical 512-byte tar headers before tarfile directory
normalization. It rejects repeated raw directory terminators, unsupported GNU
longname/longlink/sparse or GNU magic, malformed header sizes/checksums,
truncation and nonzero data after the end marker. Native Git USTAR and PAX
archives remain supported, including PAX effective paths and global comments.

PAX records are validated before tarfile interprets their metadata: each header
is at most 1 MiB with at most 4096 unique, well-formed keys. GNU.sparse.* keys
(local or global), decoded sparse maps, size overrides, duplicate or malformed
records are refused. Git source files are already limited to 8 MiB, so native
Git exports do not need a PAX size override. This closes the genuine PAX sparse
map accepted by the prior frozen directory-bound decoder.
