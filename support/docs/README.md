# Module documentation verification

[check_modules.py](check_modules.py) reads the current working tree and the
reviewed [catalogue](../../docs/modules/catalogue.json). It covers every
non-archived first-party Cargo entry and the exact explicit members of the main
kernel workspace. A00–A10 cross-module areas additionally bind their real source,
owner, failure/recovery, scope and development/technical handoff. It does not
execute any command found in a document.

```sh
python3 -I -B support/docs/check_modules.py --report /tmp/trill-module-docs.json
python3 -I -B -m unittest discover -s support/docs -p 'test_*.py'
```

Run from the repository root with Python 3.11 or newer. The checker uses Git
only to discover tracked and unignored Cargo files and identify HEAD/dirty
state; it never fetches, changes the index, updates manifests or edits source.
`--report` is the only output mutation. An error returns a nonzero status.

## Contracts checked

- Each first-party Cargo manifest has exactly one mapping, the actual package
  name, existing source entries, substantive owner/recovery/scope descriptions,
  and local development/technical documents.
- Each current explicit kernel member has exactly one handbook section, its
  own manifest/source links and four concrete contract subsections. New members
  change the required set automatically; the number is not hardcoded to 57.
- Each cross-module development domain has a unique identity, actual source
  entries and concrete technical/development, owner, recovery and scope fields.
- Referenced contract documents contain substantive prose. Direct Markdown
  local targets and heading anchors exist, including Unicode, repeated headings
  and explicit HTML IDs. Fenced examples are excluded from link resolution.

The report's input digest includes the current catalogue, manifests, source
entries and checked documents. It is a review aid for those actual bytes; it
does not attribute dirty files to HEAD. The immutable
[kernel inventory](../../docs/modules/kernel-workspace/inventory.json) has a
separate source-commit contract and remains unchanged.

## Failures and limits

A missing package, source, contract or anchor is an error. Update the real
module documentation and the catalogue together, then rerun. Do not reduce the
discovered set or replace a failed contract with a title/TODO. The negative
[fixtures](test_check_modules.py) verify missing mappings, stale package names,
empty templates, absent recovery/technical/source contracts, broken anchors,
repository escapes and duplicated kernel entries.

External URLs are not fetched. Links are checked directly from the listed
documents without recursive expansion; code-line fragments in non-Markdown
files are not interpreted. The parser supports the repository's inline and
reference Markdown links, ATX headings and explicit `a`/`span` IDs; it is not a
general CommonMark renderer. It cannot judge whether prose matches behavior or
whether an execution claim is true. Review the module-specific contract and run
the actual relevant build, original-owner, compositor or device tests separately.
