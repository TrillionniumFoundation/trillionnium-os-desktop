# Exact committed CRLF representation successor

This packet fixes a strict source-bookend false rejection of legitimate Git
checkouts with committed `text=auto eol=crlf`, including files whose committed
mode is `100755`. It preserves the previous R18 and implicit-text helpers and
their test sources as immutable historical inputs. It does not run a source
restore, build Android, install an APK, or qualify a runtime for production.

## Reproduce

Run from any directory on Linux with Python 3, `os.pidfd_open`, and `/usr/bin/git`:

```sh
python3 -I -B /path/to/packet/ci.py --output-dir /path/to/new/ci-output
```

The output directory must be new and outside this packet. No network or Python
packages are required. One CPU is sufficient. The real Git suite has a fixed
180-second deadline; the parent allows 200 seconds and reaps its actual child.
All Git repositories are temporary, isolated fixtures beneath the new output
directory and are removed after the tests. Result JSON and logs remain there.

`ci.py` verifies the complete `FILES.sha256` roster, checks the preserved actual
target result, runs 41 controls and all 440 source-derived checkouts, checks child
retirement, then verifies that every packet byte is unchanged. It records the
current Git version separately from the historical target's Git 2.53.0 result.
The suite also passed on local Git 2.47.3. Newer CI runs must produce their own
result; the archived target result is not used as a substitute.

## Exact permitted representation

Only the helper's `git` and `committed_crlf_equivalence` functions change.
`HELPER.patch` shows the complete difference against the preserved `89c48f7f…`
baseline. The final helper SHA256 is
`bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88`.

The existing bounded regular-file checks, whole raw SHA256 and F9 identity,
uniform CRLF requirement, exact normalized original Git blob, committed-only
attributes, and prohibition on filter/ident/encoding transformations remain.
The committed `100644` or `100755` mode must match the working executable bit.
Symlinks, other modes, NUL bytes, mixed endings, lone CR, `-text`, unknown text
values, and missing committed `eol=crlf` are rejected by this equivalence path.

For `text=auto`, the helper additionally asks Git itself for its content
classification through a separate, exact read-only `ls-files --format` gate.
It requires the literal path, original blob OID, exact mode, stage zero,
`eolinfo:index=lf` and `eolinfo:worktree=crlf`. The original committed-attribute
query allowlist is unchanged. Arbitrary filters or other commands cannot use
either restricted query mode. Environment and local attribute injection remain
rejected. A NUL-free binary control demonstrates why a plain CRLF-to-LF hash
match alone is insufficient for `text=auto`.

Git's documented text-auto classification and checkout rules are described in
[gitattributes](https://git-scm.com/docs/gitattributes); the built-in EOL content
fields are described in [git-ls-files](https://git-scm.com/docs/git-ls-files).
The implementation consumes Git's classifier instead of duplicating a binary
detection heuristic in Python.

## Preserved actual evidence

The failed R3 source restore rejected Mesa's `bin/people.csv` before any source
mutation. A complete, ordinary-account read-only classification found exactly
440 raw-versus-blob representations across 19 projects. Every row had canonical
LF in the committed blob and uniform CRLF in the working file; all other
content-transforming attributes were unspecified, and committed/effective
attributes agreed. The distribution was:

| Property | Count |
| --- | ---: |
| `text=auto eol=crlf` | 232 |
| `text` set, `eol=crlf` | 181 |
| `text` unspecified, `eol=crlf` | 27 |
| Committed mode `100644` | 436 |
| Committed mode `100755` | 4 |

`fixtures/actual-conversions.json.gz` contains the original committed file
bodies, attributes, modes, OIDs, working-file hashes and original source
identities. Each working body is reconstructed only by the already-proven LF
to CRLF mapping, then compared with its complete original hash. The tests build
actual Git trees and use normal checkout to reproduce all 440 byte sequences.
They also run the complete strict bookend over all 19 fixture projects.

`evidence/TARGET-CONTROLS.json.gz` is the lossless complete target result:
41 controls, 440 replays and 1,084 fixture Git commands, all successful and
reaped. `TARGET-EXECUTION.json`, the complete original client stdout/status,
test stdout/stderr, and independent retirement report bind the target binary,
input bytes, actual process IDs, unit and absent cgroups. The exact target Git
SHA256 is `ed8b2df973b28c0fb773b9c0dc0816d3ee2b3835bb932d9153c21417bb51b362`.
The two original execution/observation scripts are retained for audit and are
not run by CI. The prior failed attempt and other operational history remain
at their original immutable locations; this packet does not rewrite them.

All source-restoration, Vendor, Android, app and production acceptance gates
remain separate and require their own actual successful execution evidence.
