# Normal source-plan serialization guard

The normal Rust `PlannedProject.sparse_paths` field uses
`#[serde(default, skip_serializing_if = "Vec::is_empty")]`. A fully materialized
project therefore omits this key in its serialized manifest. An outer audit
which indexes the key directly raises `KeyError` after the normal reconcile
and verify-materialized commands have already succeeded.

This module accepts an omitted key as the normal empty vector. It rejects
null, scalar, boolean, duplicate, absolute, and escaping paths. The complete
project set, exact original commits/URLs/purposes, reviewed new projects,
and explicit cone additions must still agree. A complete old project cannot
be narrowed to selected cones.

Run the portable controls:

```sh
python3 -m unittest -v test_source_plan_guard
```

The 12 tests include a reproduction of the original exception and negative
controls for malformed fields, altered identities, narrowed projects,
unreviewed cones, and project-set changes. The guard was also replayed against
the actual 317- and 321-project normal manifests: 147 projects omitted the
empty sparse vector and all exact expansion checks passed. This audit is not
itself normal source or full-build qualification. A fresh normal CLI
verification and original-file checks are required before acceptance.
