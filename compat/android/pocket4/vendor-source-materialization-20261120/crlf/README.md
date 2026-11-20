# Verify Git CRLF checkout equivalence from committed attributes

The previous complete-source verifier rejected libopus `autogen.bat`: Git
materialized its committed 364-byte LF body as 377 bytes with thirteen CRLF
pairs. The committed attributes specify `eol=crlf` while `text` is unspecified.
Git enables text conversion in that case; see the official
[gitattributes documentation](https://git-scm.com/docs/gitattributes).

The successor changes one predicate in `committed_crlf_equivalence` to accept
`text` as `set` or `unspecified`, still requiring explicit committed `eol=crlf`.
It continues to reject explicit `-text`, `text=auto`, unknown values, custom
filters, ident and encoding conversion. It reads the entire body under the
original file identity checks, requires uniform CRLF, and compares the entire
normalized Git blob to the exact locked revision. No source conversion or
custom filter is executed by the verifier. Every other function is unchanged.

## Actual validation

The complete current 29-test report and raw streams are in `validation/`.
The actual libopus fixture is materialized by real Git checkout: the old
helper rejects it and the successor accepts it. Two complete source snapshots
have identical content hashes and leave the temporary repository clean.
Controls retain the pre-existing corruption, attribute override, filter,
encoding, mixed newline, symlink and sparse-absence refusals. The exact CRLF
fixture is marked `-text` in this packet so Git preserves its bytes.

The earlier two fixture-development failures are recorded separately with
original report hashes and failed cases. They are not counted as successful
runs. The helper did not change between those runs; the fixture was corrected
to force actual checkout conversion and refresh the index stat data.

Run from this directory, choosing a new output path:

```sh
sha256sum --check --strict FILES.sha256
python3 -I -B test_committed_crlf.py --result /tmp/p4-crlf-controls.json
```

All tests use disposable local repositories. This packet has zero Android
calls, native builds or operational source writes. Its success does not
qualify a source restoration, Android build or app for production. The live
source-restoration successor separately binds this exact helper, the original
651-project plan, all 2,822 missing bodies, original lock identities and
unchanged resource budgets; its actual result must be evaluated separately.
