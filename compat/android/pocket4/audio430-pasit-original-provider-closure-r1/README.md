# Audio430: original PASIT provider closure

The retained DesktopTestLibTestsMobly module used PASIT-defaults, whose original
source project was absent from Audio425. This patch appends exactly five projects
at their original commits in the same Android 17 superproject. The complete old
425-project prefix and all 1,519 earlier original Blueprint pins are preserved.

The provider closure contains the original PASIT libraries and utilities, its
Python gRPC and ChromiumOS-config inputs, snippet-uiautomator and mobly-snippet-lib.
Sixteen added original Blueprint files and the untouched consumer are included
as fixtures. Their original Git blob IDs, complete SHA256 values and public
superproject tree references are in original-inputs.json.

The normal Audio entry checks the exact original provider files before any source
projection. It rejects modified bytes, missing files and symlinks. The source
validator accepts the exact monotonic 425-to-430 lock change and reconstructs the
actual previous lock for historical tests. Project bound 432, sparse bound 368
and one-MiB lock size bound are unchanged.

## Production patch and normal tests

Apply audio430-pasit-original-provider-inputs.patch to the matching existing
Connectivity-projection recipe. It changes the Audio source lock, the normal
Audio input validator and the source-library historical-lock tests, and adds
the 17 original fixtures. The patch uses repository-relative paths.

Five new normal Rust regression tests cover:

- Reproducing the actual old 425-project omission.
- Requiring all five original complete source selections at their exact commits.
- Rejecting provider byte drift, absence and symlink substitutions.
- Retaining the original consumer, defaults and transitive module edges.
- Preserving the complete old lock while appending only the five approved projects.

The actual normal tool build completed 24 commands, 24 source tests and 45 selected
Audio tests with no failures or ignored tests. Both normal CLI binaries were
rebuilt and checked. Normal source reconciliation and verification then completed
17 commands for all 430 projects and 1,535 original Blueprint pins; every owned
child retired and no Git alternate remained. normal-qualification.json records
sanitized exact source/tool/result digests and counts. Private host paths,
accounts, job IDs, credentials and raw logs are excluded.

These are tool and source qualifications. The strict full Audio APEX, complete
artifact/signature/content qualification, current Android cohort compatibility
and actual runtime acceptance remain separate requirements.

## Recovery recipe binding correction

An independent review caught four stale outer-launcher bindings before a full
request was submitted: its working directory, recovery executable, recovery
source argument and recovery working directory still selected the old recipe.
A new, explicitly identified request changed all four to the new source/tool
generation; the defective request remained unlaunched.

recipe_epoch_bindings.py is a portable form of the actual preparation check.
Seven controls reproduce the four-path failure, accept the corrected launcher
and matching inner controller, and reject each independently reintroduced stale
role. They parse source with the current interpreter and do not depend on a
cross-Python-version AST hash.

Run the portable checks in a separate Python process:

    python3 -B -m unittest -v test_recipe_epoch_bindings

This static check covers the explicit ROOT-relative path literals in the reviewed
launcher/controller. It does not replace the complete frozen-source review,
actual executable/argv witnesses, work-lock ownership or recovery/retirement
proofs. It does not execute or simulate a full build.
