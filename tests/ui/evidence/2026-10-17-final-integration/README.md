# Final integration: process guard and CI, 2026-10-17

The final combination adds the original-Agentd qualification harness, its
process identity fix, archived regressions, and two checks in the existing A10
workflow. It does not change the production UI or observer code qualified by
the [137-test host and Weston record](../2026-10-17-rust188-owner-sync/README.md).

## Actual new execution

- Six disposable Linux child-process regressions passed, zero failures or
  skips, in **0.199 seconds**. See the unedited [log](process-guard.log).
- The workflow parsed with PyYAML 6.0.3 and all **eight** embedded Bash blocks
  passed `bash -n`. These are local static checks, not a GitHub Actions result.
- The combined fixed harness files match all five SHA-256 values in the
  [original process-guard receipt](../../../integration/hepta/evidence/2026-10-17-process-guard/receipt.json).
- The root README remains zero bytes. UI and support/UI files are unchanged
  from the earlier successful source; the only services/hepta-os change is
  RUN.md. The two existing Python fixture/source-contract checks are unchanged.

The [receipt](receipt.json) records exact source identities, commands, times,
source and log hashes. The actual [verifier source](verifier.py.txt) is retained
byte for byte. Its first two static setup assertions were corrected before any
process test ran: permit the exact RUN.md documentation change and select the
actual existing Python checks instead of assuming Rust manifests at that path.
No repository implementation was changed to satisfy those corrections.

## Source identity and scope

| Record | Local commit | Published commit | Identical tree |
| --- | --- | --- | --- |
| Earlier full host / Weston / Clippy success | `9b13dfbcb006a7f8af7cccd338e03174df74bad5` | `865ecf381dc8ddb70470ee173add9bd3b4a6a29a` | `00923201e6550280e68a5ca662a8a3c3a165a29c` |
| This six-test and workflow check | `5f14fded1a9dd3d9f0485520e5dc70bda3a1ff48` | `7e7f4d34f6138d7b42d01765b3422f33b5905b54` | `025da39cc0d45e846dbcf3fa38263c71426334fc` |

The new checks are pinned Rust 1.88 UI workspace/all-target Clippy with
`--locked --offline -- -D warnings`, and:

```sh
python3 -B -m unittest discover -s tests/integration/hepta \
  -p 'test_original_process_guard.py' -v
```

The archived verifier contains its original absolute paths; adjust only the
checkout and fresh output directory for a reproduction. Do not overwrite the
historical receipt or logs.

The full 137-test Rust host gate, Weston and Clippy were not repeated after
these harness/workflow additions. Their results retain the earlier full-tree
identity; this record establishes the unchanged relevant implementation bytes
and separately qualifies the new process guard combination. Original Agentd,
authenticated objectives, owner effects, Asterinas UI, mobile devices, CJK/IME,
GPU pixels and X11 remain outside these new checks. Original Agentd live
qualification is still **`not_run`**.
