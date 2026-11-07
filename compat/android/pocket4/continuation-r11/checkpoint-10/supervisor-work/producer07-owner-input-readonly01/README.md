# Private Rust Owner: bounded package configuration read

This request reads exactly eight root-owned, immutable RC files already listed by the pinned base package manifest. Seven unique contents total less than 64 KiB. The second init.rc copy is hashed and identified without repeating its content. No file discovery, application data, UID table, process action, subprocess, mount, namespace or service start is performed.

Purpose: determine the actual pre-overlay lmkd.rc and confirm its import/service relations in the existing paired init configuration. The real producer applies the admitted Android file/directory overrides before Entry::prepare_image checks and replaces lmkd.rc. It is therefore possible to use the exact legacy RC as a checked preimage without executing its service; this remains a proposal until the complete RC contents have been reviewed. The native generated relay service and LMKD digest remain unchanged.

Every file and ancestor is opened without symlink traversal; exact bytes, digest, ownership, 0444 mode and held/named identity are checked. A mismatch reports the original error and completed observations, with qualification always false. This read does not reserve a UID, authorize a filled CellSpec, prove a current Main identity, or qualify Android constructor execution.

The fixed request is CPU1/128MiB/nice10/30s. It has not been submitted. Only the parent scheduling owner may dispatch the exact key; an unknown response is reconciled under that key, not replayed under a new one.
