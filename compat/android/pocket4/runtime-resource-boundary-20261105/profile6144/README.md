# Strict profile for the observed task budget

The actual host-only preparation succeeded at 16:03:40 UTC. It created a separate profile binding the observed `pids.max=6144` budget. All other activation fields and all guard logic remain identical. The old profile and transaction remain unchanged and still reject the changed task limit. The new guard verified the same original framework/host epoch twice. No Android command, namespace entry, UI action, package action, configuration write, resource change or restart occurred.

The exact remote before/after activation files and new transaction were independently downloaded and checked in full. The only semantic activation change is `limits.pids.max` from `12288` to `6144`; the independently reconstructed transaction matches all 29,085 bytes. Original activation payloads stay private. The selected proof records their full hashes and sizes.

Future jobs must explicitly bind the new transaction `e65a47be…` and activation `91c7a4a9…`. This does not repair the conflicting resource configuration, restore 12,288 tasks, or establish an App/runtime/stability release pass.
