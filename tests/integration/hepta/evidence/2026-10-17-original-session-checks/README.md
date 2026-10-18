# Final-source Python gate checks — 2026-10-17

The actual command in [receipt.json](checks/receipt.json) passed **17/17 tests** with exit 0 at 23:09 UTC. The complete, unedited output is [python-gate-tests.log](checks/python-gate-tests.log): 17 tests in 0.649 seconds.

The execution used local source commit `145e94c364243789b88c23b1292f9d4d9ca9a0e9`, tree `98dee80a7ec855a84c777b350fed8ef675e31fc1`. The integration owner published the same tree as [299794f90d4557cec4ee9a7fc92c397031fced4f](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/299794f90d4557cec4ee9a7fc92c397031fced4f). The receipt preserves the actual local execution commit; it does not replace it with the published commit.

| Scope | Tests | Evidence boundary |
| --- | ---: | --- |
| External manifest and lock contract | 5 | Reads the unchanged fixed original source; positive generation and negative patch/resolver cases |
| Process ownership guard | 6 | Real disposable Linux child processes, with signal spies for deliberately stale identity cases |
| Session receipt validation | 6 | Explicit synthetic receipt fixtures and rejection cases |

This run does not compile Rust or launch original Agentd, Session, or Shell. Its fixtures do not qualify a daemon or a screenshot. Those qualifications are recorded separately by the actual original runtime and Shell capture archives.

The wrapper verifies the frozen desktop source and original Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` before and after the tests. Both remain clean with identical trees and input hashes. The bounded command exited normally and disarmed its owned-child guard. [MANIFEST.json](MANIFEST.json) binds eight exact input files, including the original raw log, execution receipt, executed wrapper/helper, and tested Python source files. No binary, cache, or private Agentd state is included.
