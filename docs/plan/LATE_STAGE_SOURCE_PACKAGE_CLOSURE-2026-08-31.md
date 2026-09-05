# D4–D9 unified source-package closure

The historical D4–D9 branches were stacked on mutable predecessor branches.
Their source packages have now been replayed without those ancestors onto the
current full-gap candidate and are tracked by
`manifests/late-stage-source-packages.v1.json`.

The unified package contains deterministic reference models, strict contracts,
attack corpora, read-only workflows, bounded evidence generation, and explicit
claim ceilings for:

- D4 human/Agent collaboration;
- D5 signed trusted applications;
- D6 capabilities and controlled egress;
- D7 effect reconciliation and A/B updates;
- D8 fixed-hardware evidence verification;
- D9 signed-release promotion verification.

`tools/validate_late_stage_source_packages.py` checks package order,
prerequisites, contract status, file custody, immutable workflow actions,
read-only permissions, and the non-claim boundary. The exact-head executable
corpus is centralized in `.github/workflows/d4-d9-source-suite.yml`.

These are source/reference packages. D4–D7 remain blocked on their upstream
integrated runtime gates. D8 cannot be promoted without independent physical
hardware evidence. D9 cannot be promoted without protected independent
approval, offline key custody, signing, and publication evidence. No fixture or
same-author CI result can satisfy those external facts.
