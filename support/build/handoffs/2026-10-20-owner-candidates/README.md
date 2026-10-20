# Two owner-review candidates for PR #22

These are unapplied, independent, minimal patches. Adding this handoff under
`support/build/handoffs/` does not change either owner file. A00 coordinates
cross-owner integration under `docs/agents/PLAN.md`; A01 is not claiming that
either blocker is closed. No explicit A00 authorization was found in the
PR #215 issue comments or reviews checked on 2026-10-20, or in new PR #22
comments through 16:06 UTC.

## Exact scope and provenance

| Candidate | Only applicable owner path | Source and review |
| --- | --- | --- |
| `0001-a04-searchable-pivot-root.patch` | `tests/workloads/linux/permission_probe.c` | Extracted from [PR #215](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/215), exact head `233e1e998f8e05d51c132e42ca727c2f5c54db98` |
| `0002-publication-disjoint-destination.patch` | `results/integration/2026-10-19-g1b-usage/source-publication/validate-publication.py` | One-character-class correction proposed for [CodeQL discussion](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#discussion_r4325716911) |

The reviewed A01 producer is `8769a3e224fb97ce6d06fbcb1512281a7427156e`;
main was `0c1de23a3754bc3a6976fed53c7dfa0ec3778e57`.
PR #215 was open and unmerged with 52 changed paths. Its full branch must not
be imported as this two-file repair. It does not change the CodeQL validator.
An older approval or a PR description naming an older commit does not establish
approval of the current candidate.

`source-identities.json` supplies the exact before/after Git blob, SHA256 and
byte count for both candidates and the unchanged independent permission oracle.
`files-manifest.json` binds the handoff files. Do not apply a patch if its
baseline identity differs; ask the owner to reconcile the smallest current diff.

## A04 permission fixture

[A06 run 39446927309](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39446927309)
failed in the Linux-reference step before any Rust build. Its namespace was
private, all 32 cases completed, inputs were unchanged, and the sole failure was
`pivot_without_cap`: `rc=-1`, `errno=14` (`EFAULT`). The C fixture at line 227
passes two NULL pointers to `pivot_root`; its case table expects `EPERM`.
The independent Python oracle also requires `errno=1` (`EPERM`).

The same frozen ELF and recorded source-input hashes had produced 32/32 on
[earlier run 39443118416](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39443118416).
The reference kernel families were 6.17 and 7.0 respectively. This is direct
evidence of a fixture depending on error-check ordering, not of namespace
creation failure or an Asterinas guest failure. The evidence ELF SHA256 is
`38305a701165ae011303e5b8698b0e82952b5329a231901409b739ac33efec33`.

The candidate supplies the existing searchable `mountpoint` directory twice,
and asserts directory type and visible marker after capabilities were dropped.
It keeps `OTHER`, all capability masks at zero, `rc=-1`, `EPERM`, all 32 cases,
metadata/marker preservation and the independent Python oracle unchanged.
The owner must confirm the valid-path fixture on the affected reference kernel
and then freeze one new ELF for both Linux and the ordinary Asterinas guest.

### Required owner checks after coordination

From a complete repository checkout, inspect applicability without modifying it:

```bash
handoff=support/build/handoffs/2026-10-20-owner-candidates
git apply --stat "$handoff/0001-a04-searchable-pivot-root.patch"
git apply --check "$handoff/0001-a04-searchable-pivot-root.patch"
python3 -I -B "$handoff/check_candidates.py" --regex-check
```

The helper accepts only the exact old or candidate bytes. It does not apply a
patch or run a native probe. An owner may integrate either patch separately
after coordination; the applicability check must still match that actual source.

After the fixture is integrated, compile and run the reference on the disposable
Linux test host using the existing owner route. The output directory must be new.
The reference runner must create a fresh private mount namespace before the C
probe can perform mount operations. If this prerequisite fails, preserve the
failure and stop; do not fall back to running the probe in the host namespace.

```bash
A04_EVIDENCE=$(mktemp -d)
cc -O2 -std=c11 -Wall -Wextra -Werror -static \
  tests/workloads/linux/permission_probe.c -o "$A04_EVIDENCE/probe.elf"
A04_PROBE_SHA=$(sha256sum "$A04_EVIDENCE/probe.elf" | cut -d' ' -f1)
sudo python3 -I -B tests/workloads/linux/run_permission_guest.py reference \
  --probe-elf "$A04_EVIDENCE/probe.elf" \
  --expected-probe-sha256 "$A04_PROBE_SHA" \
  --output "$A04_EVIDENCE/reference"
python3 -I -B tests/workloads/linux/test_permission_guest.py
```

Require an actual exit 0, `PERMISSION_COMPLETE total=32 passed=32 failed=0`,
`private_mount_namespace=true`, unchanged probe/runner inputs,
`cases_complete=true`, `observations_passed=true`, and pivot observation
`rc=-1, errno=1` with zero effective/permitted/inheritable capability masks.
The 32/32 guest must use that same frozen ELF; regenerating a different guest
binary, skipping the case, accepting EFAULT, or editing an old receipt is not
a successful check.

This additional command checks the independent oracle still rejects the exact
wrong errno and related false observations, without launching a native probe:

```bash
python3 -I -B - <<'PY'
import runpy
test = runpy.run_path('tests/workloads/linux/test_permission_guest.py', run_name='owner_review')
observe, runner = test['observation'], test['runner']
assert runner.check_observation(observe('pivot_without_cap'))['passed']
for key, value in [('errno', 14), ('rc', 0), ('effective', 1 << 21), ('marker_after', 0)]:
    row = observe('pivot_without_cap')
    row[key] = value
    assert not runner.check_observation(row)['passed'], key
row = observe('pivot_without_cap')
row['after_ino'] += 1
assert not runner.check_observation(row)['passed']
print('pivot oracle rejects five false observations')
PY
```

These owner/native commands were not run as part of this handoff.
This candidate has not been natively qualified in this project's dedicated cloud
environment. Statements in an owner PR description are not substituted for such
source-bound evidence.

## Inherited publication-validator CodeQL finding

The source at line 64 still has overlapping alternatives: its bare-character
class admits `(`, which can also begin the parenthesized branch. The candidate
changes only `[^\s)\\]` to `[^\s()\\]`. The old/current blob is
`9436bc8f94509cea3f9647d7934024744d4cf5d1`; the proposed new blob is
`f9206934f690a837a5c6641221a4024bf27bf33d`.

The bounded reproducer is `'[](' + '(\\)' * n`. The baseline at 28 repetitions
hits a one-second watchdog; the candidate at 100,000 repetitions (300,003 bytes)
finishes with no link. `draft-validation.json` records the actual check. It also
checks eleven ordinary/image/angle/escaped/title/reference/code-filter cases.

There is a visible parser change to review: `[a](foo(bar).md)` previously yielded
the truncated destination `foo(bar`; the candidate yields `foo(bar).md`.
Deeper nesting such as `[a](foo(bar(baz)).md)` remains unsupported/truncated by
this existing parser. Malformed-parenthesis acceptance can also change. This
minimal patch is not a general Markdown parser replacement or proof of linear
time for the entire regex search and preprocessing pipeline.

### Required owner checks after coordination

```bash
handoff=support/build/handoffs/2026-10-20-owner-candidates
git apply --stat "$handoff/0002-publication-disjoint-destination.patch"
git apply --check "$handoff/0002-publication-disjoint-destination.patch"
python3 -I -B "$handoff/check_candidates.py" --regex-check
PUBLICATION_REVIEW=$(mktemp -d)
python3 -I -B results/integration/2026-10-19-g1b-usage/source-publication/validate-publication.py \
  --repo . --output "$PUBLICATION_REVIEW/review.json"
```

The last command executes the complete existing publication validator and must
run only after the owner has integrated the candidate into an identified source.
The owner must maintain any manifests that bind the validator and regenerate
new publication evidence rather than altering old evidence. Do not use
`--allow-pending-outer-manifest` to bypass a final check. Run the existing full
publication regression and adversarial-link coverage, including actual
parenthesized destinations, and obtain CodeQL analysis on the actual new commit.
The inherited discussion being marked outdated, or a newer workflow exiting
successfully, is not itself proof that this finding was repaired.

## Draft validation boundary

Only exact source identities, in-memory transforms, supported-link examples and
the bounded malformed-input control were checked here. The candidate C probe
was not compiled or executed, no guest was launched, the full publication
validator was not executed, and no owner file or workflow was changed.
The two patches remain review candidates until owner integration and the
required positive and negative evidence are complete.
