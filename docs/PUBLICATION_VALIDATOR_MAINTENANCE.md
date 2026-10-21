# Publication validator maintenance

The Markdown destination expression in the R11 publication validator allowed
`(` to enter both its bare-character branch and its parenthesized branch.
Malformed links could force exponential backtracking. The correction excludes
both parentheses from the bare-character branch. It also preserves the complete
destination in a link such as `[report](reports/run(1).md)` instead of truncating
it at the first closing parenthesis.

This is the minimal candidate supplied in the A01 owner handoff at
`aeb1784735aff9673d0524ff2c382ba97b02bd61`. It is applied to the unchanged
validator blob `9436bc8f94509cea3f9647d7934024744d4cf5d1` on main
`f2f5d5587ff3210c975ac4162e5094ad0abfb2cc`.

## Successor publication identity

This change creates a versioned successor of the published validator and its
outer distribution manifest. The original R11 bytes remain available at the
immutable baseline commit above; this is not a claim that the original archive
is unchanged.

| File | Original SHA-256 | Corrected SHA-256 |
| --- | --- | --- |
| `results/integration/2026-10-19-g1b-usage/source-publication/validate-publication.py` | `e42de9e6d03f0b3e6bbf57545c15cf6977dbf7ca9f6373ecc2e20a34e48c126f` | `2873ac7eef9c477a87e0d42ed1daa0c0d0f12ab9f1c02147da5e06eb1e891b48` |
| `results/integration/2026-10-19-g1b-usage/files-manifest.json` | `58c0b3d104776ecf2d6eef75c9d99c0b75b5827f191059ad8e796d4dfe01da97` | `0ca0012149f1a324b83b5959ad97f573178312cc2c8a102f519b45cf84a7de01` |

The validator grows from 25,812 to 25,813 bytes. The outer manifest changes only
this member's size and SHA-256 and the corresponding total, from 5,398,579 to
5,398,580 bytes. Its set of 288 paths and the other 287 member identities remain
unchanged. Producer manifests and historical `publication-validation.json`
remain byte-for-byte unchanged. The old outer `generated_at_utc` and
`executed_source_*` fields describe the original evidence provenance; they are
not execution identities for the corrected validator.

## Regression and revalidation boundary

Run the host regressions with:

```sh
python3 -I -B tests/spec/test_publication_links.py
python3 -I -O -B tests/spec/test_publication_links.py
```

They cover ordinary, image, angle, escaped, titled and reference links; excluded
code spans/fences; a complete parenthesized destination; and the malformed input
family that previously hit a watchdog at 28 repetitions. The corrected parser
must finish 100,000 repetitions within a separate-process watchdog. They also
verify the successor manifest and the unchanged historical identities.

The [successor revalidation record](../results/maintenance/2026-10-20-publication-links/validation.json)
binds the corrected validator to the exact current input map. It verifies 293
physical inputs, 1,002 member references in 13 manifests, and 427 local links
without a missing target. The bounded recursive scan expands 25,494,588 bytes
and finds no candidate secret patterns. These are maintenance checks; they are
not new kernel, device or product executions. The historical parser reaches
the one-second watchdog at 28 repetitions; the correction completes 100,000
repetitions in approximately 0.032 seconds on that run.

The historical `Review.scope()` remains specific to the original R11 delivery:
its fixed old base, three changed documents and a newly added report prefix.
Later main commits legitimately do not satisfy that scope. A maintenance run
may separately revalidate member identities, links and bounded recursive content
scanning, but must not relabel that result as a new pass of the historical full
publication gate or edit its old `passed` result. Write new results outside the
frozen report prefix and bind them to the new validator SHA and input identity.

This correction covers the reproduced ambiguous-alternative backtracking
family. It is not a general CommonMark parser or a proof of linear complexity
for every preprocessing expression. Deeply nested destinations remain outside
the parser's existing supported subset. CodeQL must analyze the actual new
commit; an old green run or an outdated discussion is not clearance of the fix.
