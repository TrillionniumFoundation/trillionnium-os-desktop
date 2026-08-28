# Desktop threat model — D0 baseline

## Protected assets

- trusted shell identity and consent/recovery UI;
- user profile, cookies, app storage, and secrets;
- capability permits and service credentials;
- update/signing keys and rollback state;
- operation receipts and crash/effect evidence;
- host devices, filesystem, private network, and metadata services.

## Adversaries

- hostile external webpage and service worker;
- prompt-injected or compromised Agent context;
- malicious/compromised signed app publisher;
- unprivileged local process attempting to impersonate AgentPort;
- compromised browser renderer/content process;
- malicious network/DNS/redirect peer;
- corrupted update, disk, journal, or power-loss state;
- accidental mobile dependency/authority contamination.

## Primary controls

- separate trusted shell and content trust surfaces;
- distinct tuple origins for trusted apps;
- no ambient browser filesystem/device/secret/update authority;
- authenticated bounded local transport;
- formal Agent/human state machine and layered stale-reference checks;
- controlled browser network namespace and egress;
- short-lived audience/resource-bound capabilities;
- process/cgroup/LSM isolation;
- signed immutable updates with rollback and offline recovery;
- machine-readable claims and product-boundary CI.

## D0 residual risk

The current code has no browser or listener, so it does not yet expose webpage
attack surface. It also has no evidence that the planned Servo hooks, sandbox,
origin interception, UDS authentication, Debian image, or update chain work.
Those are stage gates, not assumptions.
