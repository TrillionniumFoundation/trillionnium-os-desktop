# Native sparse capacity and frozen source recipe

The final patch raises the sparse-path bound from 256 to 288, accommodating the original 279-cone CTS selection while still rejecting 289 paths and invalid, duplicate, absolute or traversal paths. It adds a Rust frozen-pair recipe and the exact original CTS fixture. The active 268-project source lock and project capacity of 272 were not changed.

Apply the [common base and native prerequisite](../source-prerequisites/README.md) before `source.patch`. The resulting 446 retained source files match the candidate byte-for-byte and by executable mode; `source-files.json` and `changed-files.json` record their identities.

## Actual checks

| Scope | Passed | Exact source scope |
| --- | ---: | --- |
| droidloom-source library | 25 | Published capacity candidate; lib SHA `a91cefb336b535b38196d03c2fc05752c32b42629db3f0a16a95826e40739627` |
| frozen_pair_recipe example | 6 | Published helper SHA `267be02695dfab430c3f1b014c30c89f8f237a825a9e382ee95cf44d75c28d01` |
| generated ordinary-pair source | 11 | Separate source tree after applying the frozen recipe output; exact generated source hashes are in result-summary.json |

The library controls include a real local Git checkout of 279 cones, exact selected-source preservation, exclusion of an unselected Blueprint, refusal of 289 cones, and the existing resume/restoration controls. The recipe was exercised against the unchanged 268-project frozen manifest, its emitted source patch was applied in isolation, and that generated source compiled and passed the 11 ordinary-pair controls.

The 11 generated-pair checks must not be attributed to the ungenerated capacity candidate. Their lib SHA is `f0ab3f8e45a36886c2fda692f30afe94d037875694df04e74bcd1e84c0def0c0` and pair-builder SHA is `1f924a673a40d30b3e2b06f9e7335017e8c26ac2b35f813dafd346e1461f8c31`. The first recipe replay returned 1 despite its unit tests passing; its failure receipt remains separately bound in the summary.

All three passing control groups used one CPU, a 1.5 GiB memory limit and zero swap, with no OOM. Their original receipt byte counts and SHA-256 values, resource observations and commands are in `result-summary.json`. The two direct candidate commands are:

```sh
cargo test --offline --locked -j1 -p droidloom-source --lib --target x86_64-unknown-linux-gnu -- --test-threads=1
cargo test --offline --locked -j1 -p droidloom-source --example frozen_pair_recipe --target x86_64-unknown-linux-gnu -- --test-threads=1
```

The original run used Rust 1.93.0 and an existing dependency cache. A new machine must first resolve Cargo.lock and the required toolchain; `--offline` alone does not supply them. Reproducing the generated-pair checks additionally requires the exact frozen manifest and superproject input identified by the recipe's hashes, then applying its emitted patch before running the recorded pair-test command.

No Soong build was started by these controls. Full AOSP source closure, complete native engine/ART artifacts, installation and runtime qualification remain pending. The repair does not enable runtime authorization or change the 0/45 original whole-application acceptance count.
