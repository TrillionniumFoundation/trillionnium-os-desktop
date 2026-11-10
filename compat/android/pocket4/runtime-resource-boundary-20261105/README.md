# Observed Main task-limit change

The original activation binds pids.max12288. Gallery02 stopped at15:00:50UTC before any Android/UI/fixture operation because that value changed. A15:25 read found6144 with the same original host/init/presenter identities and unchanged CPU/memory limits. A15:49 read verified the complete original framework epoch and host process identities twice; the kernel and systemd both reported6144, task usage3244 and pids.events max0.

The manager journal records a reload requested by apt-daily-upgrade.service at14:57:58 and completed at14:57:59. The existing50-TasksMax.conf specifies12288 while the later named90-digitalis-validation-resources.conf specifies6144. Both original configuration files remain untouched. [systemd.unit](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit) documents filename ordering for drop-ins. The ordering and live observations explain the obsolete activation assumption; they do not identify who originally wrote either configuration.

Two earlier read-only diagnostic attempts failed on extra root-ownership assumptions. The exact pinned epoch source and the vendor unit are UID1000 files; content hashes, stable regular-file reads and canonical paths remain checked. The final diagnostic keeps ownership as observed metadata and still requires protected root-owned executable tools. No diagnostic changed Main, its limits, systemd configuration or the original activation/transaction.

The current limit is retained. Any later acceptance profile must be separately frozen, preserve all other activation fields and all guard logic, and grant no App or stability qualification merely by existing. The conflicting resource configuration remains a separate release concern.
