# Trusted signed app bundles v1

`platform/trusted_apps.py` implements offline source admission for G5. It reads a
bounded ZIP snapshot, verifies every included resource against a signed complete
content index, checks an externally pinned publisher key using real Ed25519, and
returns immutable local asset responses. The default has no trust roots and
refuses admission. No production roots are supplied in this repository.

The machine contract is [trusted-app-bundle.v1.json](../../contracts/trusted-app-bundle.v1.json).
The existing [app manifest v1 schema](../../contracts/app-manifest.v1.schema.json)
defines the metadata field set; the source profile below narrows its paths,
versions, signature encoding and CSP. The origin follows
[ADR 0004](../adr/0004-trusted-app-origin-model.md). This module does not activate
an app, install an engine interceptor, create storage partitions, or qualify an
installed network boundary.

## Manifest and signature bytes

The archive contains one exact root `manifest.json` and 1–512 asset files. The
manifest is canonical JSON: ASCII output from recursively sorted object keys,
compact `,` and `:` separators, `ensure_ascii=true`, and no final newline.
Duplicate fields, unknown fields, floating point and nonfinite numbers are
rejected. Strings and metadata must also satisfy the closed v1 profile. Stable
versions have three uint32 components without leading zeros. App versions may
also have nonempty SemVer prerelease identifiers, with no leading zeros in
numeric identifiers. Version strings have at most 128 characters.

`signature.value` is canonical RFC4648 padded base64 of exactly 64 bytes. The
algorithm must be `ed25519`. The signature preimage is:

```text
UTF8("trillionnium.desktop.app-manifest-signature.v1\0") ||
canonical_json(complete_manifest_with_only_signature.value_deleted)
```

The `\0` is one NUL byte. `signature.algorithm` and `signature.key_id` remain in
the preimage. Every other field, including optional `data_schema_version`, the
exact origin, CSP, capabilities and minimum shell version, remains signed.
`manifest_signing_bytes(payload)` validates this profile and produces the exact
preimage; a producer can initially use base64 of 64 zero bytes for the value.
The tests also implement an independent literal preimage producer and generate
temporary real Ed25519 keys with system OpenSSL.

## Complete content index without self-reference

The logical index is a canonical JSON object with exactly `files` and `schema`.
Its schema is `trillionnium.desktop.trusted-app-content-index.v1`. Each file
record has exactly `path`, `sha256` and `size`. `files` contains every asset in
ASCII path order. SHA256 is the lowercase digest of the exact uncompressed bytes,
and size is their integer byte count. The manifest is excluded from this index:
it holds the root and signature and is never served as an asset. The root is:

```text
SHA256(UTF8("trillionnium.desktop.trusted-app-content-index.v1\0") ||
       canonical_json(complete_index))
```

The resulting lowercase hexadecimal digest must equal signed
`content_root_sha256`. Added, removed or changed assets fail admission.
`content_index_bytes(assets)` and `content_root_sha256(assets)` implement this
producer contract. Their inputs are mappings of canonical paths to immutable
`bytes`; mutable buffers and a `manifest.json` asset are rejected. ZIP timestamps
and record ordering do not contribute to the content root. The admitted object
also reports the SHA256 of the complete archive snapshot and canonical manifest.

## ZIP profile and filesystem custody

The parser accepts a deliberately bounded classic ZIP profile, without extraction
to disk. Local regular-file records occupy all bytes from offset zero to the
central directory. Every local record exactly agrees with its central entry. A
single-disk central directory is followed by its 22-byte EOCD at exact EOF.
Only stored and raw-deflate content is accepted. Length, CRC32, complete deflate
consumption and the signed index are all checked.

ZIP64, encryption, descriptors, extra fields, comments, explicit directory
records, symlinks, devices, FIFOs, sockets, setuid/setgid/sticky attributes,
preambles, gaps, overlap and trailing bytes are rejected. ZIP entries can omit
Unix file type metadata, as ordinary ZIP writers do, or specify a regular file.
Other file types cannot become assets. This profile is not a general ZIP
extractor; producers should write plain files with implicit directories.

Paths contain 1–512 ASCII characters. Each slash-separated segment contains
1–128 characters and matches `[A-Za-z0-9_-][A-Za-z0-9._-]*`, with no trailing dot
or Windows device basename such as `NUL.txt`. Empty or dot segments, hidden
segments, absolute paths, backslashes, colon, percent encoding, whitespace and
Unicode aliases are rejected. Duplicate paths, ASCII case-fold collisions and
file/directory prefix collisions are rejected before content decoding. The
entrypoint is an existing indexed path ending in lowercase `.html`.

Limits are 32 MiB of archive bytes, 64 MiB of total uncompressed content including
the manifest, 16 MiB per asset, 64 KiB of manifest bytes, 512 assets and a maximum
128:1 ratio against `max(1, compressed_size)`. Counts and declared sizes are
checked before decompression; actual output is separately bounded and checked.

`admit_bundle_file` requires an absolute canonical filesystem path. It opens
every ancestor with `O_DIRECTORY|O_NOFOLLOW` and the leaf with `O_NOFOLLOW`, then
requires a single-link regular file within the archive byte limit. Nonblocking
leaf opening prevents a FIFO from hanging the reader. It checks inode, device,
mode, link count, owner, size, nanosecond mtime and ctime before/after the bounded
read and against the named leaf in the pinned parent directory. Identity or
metadata drift refuses the snapshot. Parent directory renaming cannot redirect
an already open descriptor. After admission, resources come from immutable
memory; later pathname changes do not replace their signed bytes.

## External roots, rotation, revocation and time

`PublisherTrustRoot` contains the exact publisher, key ID, 32 raw immutable
Ed25519 public key bytes, their externally pinned SHA256, and a half-open validity
interval. An app cannot introduce its own root. `PublisherTrustPolicy` contains
an externally authenticated revision, freshness interval, immutable bounded root
tuple and revoked `(publisher, key_id)` tuples. The owner of provisioning must
authenticate this policy; a dataclass constructor does not authenticate operator
configuration. Keys are scoped to one exact publisher, even when another
publisher uses the same key ID. Policy and key validity use
`valid_from_unix <= trusted_now_unix < valid_until_unix`.

The verifier calls the fixed `/usr/bin/openssl pkeyutl -verify -rawin -pubin
-keyform DER` using the fixed Ed25519 SPKI prefix plus the pinned raw key. The
key, signature and preimage are passed through separate sealed Linux memfds and
`/proc/self/fd` paths. All four write/grow/shrink/seal seals are set before the
child receives the descriptors. This avoids a temporary pathname substitution
between pin checking and crypto verification. The child has a minimal fixed
environment with `OPENSSL_CONF=/dev/null`, closed other descriptors and a
5-second timeout. Missing OpenSSL, memfd/sealing support, malformed keys,
verification failure or timeout refuses admission. There is no test fallback
verifier or additional Python package dependency.

`replace_policy` requires a strictly greater revision in one admission owner,
preserves every prior revocation, and forbids rebinding a seen publisher/key ID
to different public key bytes. Rotation uses a new key ID. Current roots are
bounded to 256, cumulative revocations to 1024, and remembered key pins to 4096;
capacity exhaustion refuses replacement. Each admission and each asset response
checks the current root, revocation list and policy freshness. An admitted bundle
cannot keep serving after its key is revoked, removed or expired through this
API. A failed policy replacement leaves the previous policy intact.

The caller supplies trusted time. Admission, policy replacement and asset
responses require the creating process and Python thread; cross-thread use or a
forked copy refuses. Policy and remembered pins publish in one state assignment
after all replacement checks. A page, model or bundle must not choose the policy,
clock, shell version or owner. Callers must not reenter an owner from a signal
handler or callback; such attempts refuse, and callers must queue the work until
the current call returns. The guard clears on every return or exception.
Policy replacement does not acquire network data or authenticate a downloaded
policy. Durable revision/floor storage and externally protected antirollback
across process restart are remaining installed obligations. The source owner
does not claim that a new process can detect a replayed old operator snapshot.

## Exact local response contract

`asset_response` accepts only `GET` and an exact lowercase URL of the form
`https://<app_id>.<publisher>.apps.hepta.invalid/<indexed path>`, using the same
owner that admitted the bundle. There is no implicit root route, redirect or
network fallback. Different origin, userinfo, explicit port, query or fragment
(even empty), percent encoding, backslash, traversal, `manifest.json` and missing
assets are refused. The returned `asset_path` is the canonical index path, and
the immutable body is exactly its admitted content. Content type is chosen from
the closed extension table; `.bin` explicitly uses `application/octet-stream`.
Unknown extensions, including native executables such as `.exe`, refuse a
response even if their bytes are in the signed index. `HEAD` and all other
non-GET methods refuse. `nosniff` is always set. Responses include no permissive
CORS header.

The signed manifest must contain this exact CSP, also emitted on every response:

```text
default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; media-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-src 'none'; frame-ancestors 'none'; form-action 'none'; worker-src 'none'
```

Every response also includes `Cross-Origin-Resource-Policy: same-origin`,
`Referrer-Policy: no-referrer` and `Cache-Control: no-store`. This profile permits
local indexed scripts/styles/images/fonts/media, prohibits inline/eval scripts,
connect APIs, frames, forms and workers, and sets a closed default. Its actual
engine enforcement, navigation policy, DNS interception and protocol handling
still require installed tests. A Python response object cannot intercept Servo
or stop a direct socket on its own.

## Source API inventory v1

All refusals raise `AppAdmissionError`; there is no boolean success fallback or
partial response. File and verifier failures are converted to this error. Normal
process interrupts propagate and cannot produce an admitted bundle. The API
performs no external effect other than bounded local reads and the crypto child.

| API | Inputs and preconditions | Result and semantics |
| --- | --- | --- |
| `PublisherTrustRoot(...)` | Exact publisher/key ID, raw32 immutable key, externally pinned lowercase hash, valid bounded time interval | Immutable validated root; pin mismatch or malformed data refuses |
| `PublisherTrustPolicy(...)` | Bounded integer revision/times; exact tuples of distinct roots and revocation identities | Immutable closed snapshot; authentic provisioning remains caller responsibility |
| `TrustedAppAdmission(shell_version=..., policy=None)` | Stable uint32 shell version; optional authenticated policy | Creator-process/thread owner with no default authority; not an activation operation |
| `replace_policy(policy)` | Authenticated strictly newer policy with cumulative revocations and immutable seen key IDs | Atomically replaces this owner's policy after all checks, or refuses |
| `manifest_signing_bytes(payload)` | Canonical closed v1 JSON bytes with a canonical base64 signature value | Domain-separated signature preimage excluding only the value |
| `content_index_bytes(assets)` | 1–512 canonical paths and immutable byte values within limits; no manifest member | Complete sorted canonical index bytes |
| `content_root_sha256(assets)` | Same preconditions as the index helper | Domain-separated lowercase root digest |
| `admit_bundle_file(path, now_unix=...)` | Canonical absolute single-link regular file; current trusted clock/policy | Owner-issued immutable `VerifiedAppBundle` after full archive, index and real signature verification |
| `asset_response(bundle, url, now_unix=..., method="GET")` | This owner's admitted bundle; current trusted clock/policy; exact local GET URL | Immutable `LocalAssetResponse` with canonical asset path, exact bytes, fixed headers and status 200 |

`VerifiedAppBundle` reports publisher, app ID, version, entrypoint, exact origin,
content root, archive and manifest digests, signed capability declarations,
optional data schema version, `entrypoint_url` and sorted `asset_paths`. Its public
constructor refuses; admission retains immutable content bytes behind it.
`LocalAssetResponse` is response data, not a capability permit or proof of engine
interception. Python private fields are an internal API boundary; arbitrary
trusted Python code in the daemon is outside the hostile-bundle threat model.

## Remaining installed lifecycle

Before activation, the product must bind this verified object to its real engine
interceptor for every relevant load path, enforce no public DNS/network fallback
for synthetic hosts, enforce CSP/CORS/protocol/cache/worker/navigation policy,
and create distinct per-app storage partitions. It must define durable version
floors, upgrade/downgrade, data migration and uninstall semantics, revoke existing
execution contexts on policy changes, and use trusted capability approval.
This module grants none of those capabilities and performs no install or storage
mutation. The closure-plan G5 gate remains open until those installed paths and
their bypass corpus pass on the accepted product image.

The source corpus runs with only Python stdlib and system OpenSSL:

```sh
python3 -m unittest discover -s tests -p test_trusted_apps.py -v
```

It uses disposable keys, real signatures and controlled local archives. It
covers wrong keys/domains, signed field mutation, pin/publisher scope, root and
revocation validity, policy replay/rotation, full-index changes, malformed ZIP
and resource bounds, file custody races, immutable bytes, exact URL handling and
sealed verifier inputs. Passing these tests is source evidence, not installed
origin or storage qualification.
