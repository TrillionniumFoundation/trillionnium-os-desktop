# Audio released SDK source reconciliation

The original source-only r2 command completed successfully on desktop at 2026-11-09T15:23:43.031Z. The durable H record reports exit 0, complete untruncated output, no cancellation and no timeout. The exact recipe is `557bff5c84eef7eea9af4533ac7391e3ae676d0f`; its source lock remains `aab71dbce304aba849ac592b5d9cdc2a339cf9208c47faca98f27350c462437d`. All 430 upstream project revisions are retained.

The materialized manifest is the included 265,411-byte `materialized-after.json`, SHA256 `8e2ea62993d6278287005a6adc4d00552026ea923d689bbb84ff4e2b154b4a95`. An independent terminal check finished at 2026-11-09T15:28:08.236Z. Under the same three original lock inodes, it reread all 55 SDK files and recomputed both whole-file SHA256 and Git blob identities against the original pinned upstream blobs. It also verified the physical source unit was absent and acquired and released each original lock with nonblocking exclusive locking.

The original controller, independent verifier, complete receipts, source-ready binding and durable H request/start/exit records are retained unchanged. `INDEX.json` authenticates those nine input files; the enclosing capsule manifest also authenticates this README and the index. These historical SDK inputs are required by the current source consumers.

This closes the stated source materialization and retirement work only. No new full APEX build, Android start, application acceptance or production readiness is claimed. The separately qualified normal-tool successor is documented under `../normal-source-update`.
