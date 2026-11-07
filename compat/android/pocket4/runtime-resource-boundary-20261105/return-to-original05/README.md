# Return to the original Main resource baseline

The 17:42 USB metadata job stopped at the strict 6144-profile guard before reading
USB/provider state. It is retained as a failed job and supplies no current camera
presence result. Config05 then read the fixed Main identity twice at 17:48:42 UTC:
only pids.max differed from that profile, at 12288. CPU, memory and swap limits
matched. systemd TasksMax and EffectiveTasksMax were both 12288 with no pending
daemon reload, and both task-limit configuration files named 12288.

A separate owner's complete original transaction explains the change. Job
1a1accb66a0-fc05-56ed restored the original config90 content and applied
TasksMax=12288 once. Job 1a1acce7e5d-fc05-5704 independently collected the original
guard, all five limits, input metadata, boot and seven process identities after
that transaction. Both jobs succeeded with complete durable output; the latter
guard passed. Original bytes and terminal hashes are bound in RECONCILIATION.json.
Config05 independently corroborates their resulting configuration hashes.

No restart, daemon reload, engine deployment or original-guard change is reported
by that transaction. This work only reads and reconciles its saved evidence; it
does not repeat the configuration writes. New App operations use the unchanged
original b227/7e49 transaction/activation and must still pass its fresh full guard.
The former 6144 profile and all original failures remain historical evidence.
No whole-App or runtime-engine qualification follows from resource restoration.
