# Original Agentd workflow expression regression

The first single-ARM workflow candidate was rejected before GitHub created a
job. Job-level `env` used `runner.temp`, but that expression context is not
available there. YAML parsing, `bash -n` and Python AST parsing had passed;
those checks did not validate GitHub Actions context rules.

The exact failure was reproduced with the hash-verified actionlint 1.7.12
release. `before-fix.log` reports the disallowed context at line 26; the
unchanged command exits 0 on the corrected complete workflow. The five
upstream/local tool receipt files were copied byte-for-byte; their hashes and
both workflow identities are in `receipt.json`. An empty `after-fix.log`
means actionlint emitted no diagnostics; its exit status is recorded separately.

The fix constructs the same private path from `RUNNER_TEMP` in the first run
step and records it in `GITHUB_ENV` for later steps. The original fixed source,
8 GiB build admission, compiler versions, read-only acceptance checks, error
exit propagation and three-ELF runtime/hash qualification were retained.

- [GitHub's expression context table](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability)
- [First rejected candidate](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39032341629)
- [Corrected workflow run](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39032688536)

At the recorded snapshot, the corrected PR event had created an ARM-labelled
job but remained queued, with `runner_id=0` and no steps. This is evidence of
accepted workflow semantics, not original-Agentd build or runtime success.
Later runs must retain their own source identity and actual status.
