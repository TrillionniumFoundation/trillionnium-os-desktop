# Explicit library-owned source generation, revision 2

This is a new source-preparation attempt. It preserves the original source
worker (`9db3af14…`), core, typed runtime guard, reader and generator byte for
byte. The original `77fe…` failed attempt and its generated files remain failed
and are not resumed, relabeled or overwritten. This candidate performs source
generation only: no build, install, UI, location grant, Bili acceptance,
Android lifecycle operation or cleanup is admitted.

## Actual cause and actual host proof

The separate host-only probe really completed successfully as job
`1a1b16bbf10-fc05-7891`. Its complete durable stdout is 14,135 bytes with SHA256
`c590487759f7a0e2e32dec8cdb16a7c42b7f932ed88154f760fdde477770ef94`;
its terminal receipt is 733 bytes with SHA256
`86c28f1ff58512f7b8f3b42c59eb1a62e7bb20ce52edd0a043d54792e35d6762`.
It recorded Python 3.14.4 and these deployed identities:

| File | Bytes | SHA256 |
|---|---:|---|
| Python executable | 7,477,160 | `52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41` |
| `_ctypes` extension | 158,368 | `140e837f2bc9344f3a98dea90e8bdf6f208370e45f3eccbac759c59e59d4d045` |
| `ctypes` Python source | 22,131 | `72f2df568380c275a5596944810953124ff2ee8d678c5f8ddcf50f0f77577eb3` |
| libffi | 64,184 | `1a0dc86f787f73e025a6e521056360afcbe70f2a82cd808132fefc2b4ee95daa` |

The `_ctypes` import alone added the one specific read-only/CLOEXEC libffi
descriptor. Importing `ctypes`, the frozen held-runtime source, and running GC
kept the complete descriptor set unchanged. The parent held the original child
pidfd before release, observed normal exit zero, sent no signal, closed its
own descriptors, and restored its original FD identities. This agrees with
CPython's import-time closure allocator initialization and libffi's retained
static-trampoline backing file. The probe's primary-source references are in
`../ffi_bootstrap_probe_r1/README.md`. Exact deployed libffi source tag ancestry
is not inferred from its SONAME or exported symbols.

## Admission and ownership

The outer source is initially an unsealed template with `CONFIG=None`.
Execution rejects before any Main read. Sealing copies the actual raw probe
stdout/terminal and an explicit new source-generation request into a new
root-private host stage. Their hashes, the actual probe job ID and the new
nonce are fixed in the candidate. The candidate's own source pin is passed by
the fixed stager argv and propagated unchanged to its child; it is not embedded
inside itself as an impossible circular hash.

Before Main admission the child verifies the successful probe's durable
terminal and its original held-pidfd retirement. It checks all three current
Python/ctypes files against that actual observation, verifies their import
origins, starts with only stdin/stdout/stderr, and imports `_ctypes` explicitly.
The sole added descriptor must match the observed libffi file, bytes/hash,
full stat, flags and ELF identity. Current maps are checked for that exact
file; cross-process virtual addresses are not treated as file identities.

After `ctypes` initialization the child freezes the complete FD identity set.
Only then does it invoke `worker.run(new_request)` from the original, pinned
source. The original count-equality checks and all original runtime/package,
Meituan and Bili guards remain in place. The wrapper additionally requires all
four native read clients joined successfully, every tracked observation and
lease FD closed, no prohibited action, unchanged original failure evidence,
and an unchanged full FD set/library binding at the end.

The stable set includes three transport descriptors and one explicitly proven
library-owned descriptor. No generic path allowlist or count increment is
accepted. Unknown/missing/replaced descriptors fail. Snapshots do not claim to
detect an unobserved close-and-reopen of the same file with indistinguishable
metadata; the frozen code does not close the library descriptor at all.

The parent invokes the child once through the exact already host-tested pidfd
helper. The child cannot begin before the parent has its pidfd. The parent
requires normal zero exit, readable original pidfd, bounded complete output,
no signals/timeouts, and restored parent descriptors. A successful inner
render without this parent evidence is ineligible for the next stage.

## Result authority and failure recovery

Only the joint outer result, its exact raw child result, and the new job's
complete durable successful terminal can qualify this new source publication
for a separately reviewed build. The generator's inner receipt alone is never
sufficient. Build/install entry points must bind that joint proof before use.
Source qualification is not runtime QA or production readiness.

The outer deadline is 1,000 seconds; the original worker keeps its own
900-second work budget and the original bounded native read clients. A parent
deadline/output failure causes at most one signal to the exact directly owned
worker pidfd, never Main or a process group. Such an attempt stays failed even
if that worker retires. Without the inner joined-client receipts, descendant
native-reader status is **UNKNOWN** and requires explicit reconciliation;
the wrapper does not claim killing its worker retired all descendants.
There is no automatic retry, reuse of the nonce, rollback, or removal of
partial source publications. Original failure records and any new incomplete
attempt stay available for review.

## Validation and status

The four real host subprocess/pidfd controls belong to the unchanged probe
helper and have both local and actual Pocket4 proof. This wrapper's local
controls parse the actual raw probe success, reject loss of durability,
timeout, wrong job identity and absent held-pidfd death, and execute the
unsealed template to confirm it rejects before spawning a child or reading
Main. They do not fake root-owned filesystem metadata. Run:

```
python3 -B test_template_controls.py
```

The sealed wrapper and its new source-generation request have not been
executed merely by generating a packet. The source worker, old Main guard and
framework epoch are unchanged. No application readiness or cleanup count is
increased by this preparation.
