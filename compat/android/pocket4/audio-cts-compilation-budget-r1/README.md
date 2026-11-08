# Audio CTS compilation provider and actual Go budget

The normal strict Audio graph failed because the appsecurity profile and dm
consumers referenced defaults from an omitted original CTS compilation cone.
This source patch adds that entire cone at the unchanged CTS commit. All 316
project revisions and previously selected paths remain fixed. It does not remove
consumers, accept missing dependencies, or substitute successful metadata for a
complete build.

The same actual run exposed Blueprint resetting GOMAXPROCS to NumCPU after the
environment probe. The new source projection honors an explicit positive
GOMAXPROCS value, preserves the upstream behavior when unset, and reads actual
runtime scheduler, memory and GC limits on entry and deferred exit. The public
log consumer requires complete matching records from an actually observed Soong
PID, including 2 / 5 GiB / 50 values. These are boundary observations, not a claim
of continuous runtime measurement.

`audio316-cts-compilation-provider.patch` applies to the exact 431-file public
Audio316 source recorded in `baseline-public-source-files.json`. The resulting
435 public files are fully pinned in `updated-public-source-files.json`. The
four added files include original AOSP fixtures and the reversible Blueprint
patch. `source-delta.json` records all seven changed or added files. Apply the
patch to the existing exact public source; do not fabricate a new source tree
by applying it to an unrelated repository revision.

The rebuilt normal tools passed 16 source tests and 26 audio tests under the
locked offline Rust toolchain. The tests exercise monotonic source extension,
original provider/consumer preservation, explicit Go projection and restoration.
The Python marker controls run with:

```sh
python3 -B -m unittest -v test_go_runtime_budget.py
```

Full build, compiled translation-unit, whole APEX signatures/contents and device
runtime qualification remain separate requirements. This public package contains
no private host identities, credentials, raw execution logs or transfer allowlists.
