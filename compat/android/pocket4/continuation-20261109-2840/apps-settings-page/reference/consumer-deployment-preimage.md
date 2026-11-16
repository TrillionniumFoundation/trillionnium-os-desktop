# UI consumer pin resolution

The installed-versus-prepared UI consumer hash difference is explained by the staged final deployment. It is a deployment precondition, not evidence of an unexplained modification or a reason to relax the existing leaf hashes.

The exact read-only deployment manifest is `/home/alex/work/pocket4-android-final/deployment/manifest.json`, 99500 bytes, SHA-256 `8df3d0fe6a40b9509155290e201c13afa96781e6e0425b1e0e78e6cf893e682c`. Read job `1a1c142b4fc-e62c-4b` finished with exit 0 and complete, durable logs. `current-vs-staged-consumer-deployment-readback.json` retains the exact JSON projection from the remote read without numeric conversion.

| Entry | Current installed source, verified independently | Staged candidate / selected leaf pin |
| --- | --- | --- |
| `/usr/local/bin/android-app` | `e775301b11960df8109f39ef1adfc662bebd8fc536414580c71c7aa0da263efe` | `4823c1a6d2434a9d102b2b6dbc369dd0cf192e7fc0a31384a68dddb370d0a340` |
| `/usr/local/libexec/android-digitalis-observe-helper` | `d1fc02bdbbd72c8e9ee440dbf81274662d60228a4e7ecc661484241d889d7bd4` | `76e9875d141f69976cbbafe469aa13439cf99c3214bc479a0c80cda740c8dcfa` |

Manifest payload entries 14 and 15 record these exact pairs: each `source.sha256` is the independently observed installed hash, while its payload and `candidate_input.sha256` are the hashes required by the existing `OriginalAPIs` adapters. The staged consumer manifest is `consumers/manifest.json`, SHA-256 `b8cdea5cff9e67d87cfc5a11418068e25bfec5975ed9bae51b7547e936e3729b`.

The earlier hypothesis of an unexplained consumer drift is withdrawn. An attempt to run those final-generation leaves before their staged consumers are deployed must still fail their pin check. No installed file, preparation, canonical manifest, shared source or CURRENT was changed. No hash was substituted in a selected leaf. The staged deployment is not a completed production deployment, and this resolution does not change the **0 of 42** application runtime acceptance count.

The exact candidate files and their manifest were then read with all three SHA-256 pins verified (`1a1c144b80a-e62c-4f`, exit 0, complete/durable). A full byte comparison found exactly one source-line change in each consumer: the expected DevelopmentCell owner command changes `--kill-child=TERM` to `--kill-child=KILL`. The rest of each source is identical. The manifest declares `production_installed:false` and `new_client_candidates_live_validation_pending:true`. This provides a concrete staged-source explanation while preserving the final-generation admission requirement.
