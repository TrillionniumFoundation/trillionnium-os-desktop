# D2I integrated-image qualification

D2I composes the exact D1 image substrate and exact pinned Servo runtime in one
Q35/TCG image with no network device. The permanent workflow is read-only and
runs without path filters on every pull request to `main` and every exact
`main` push.

The qualification runtime is generated deterministically from a tracked base
source into the Servo checkout. The transformation is itself tracked,
digest-bound, fail-closed on source-shape drift, and never changes a Git ref.
It removes the unsound requirement that Servo must emit a pipeline-crash
callback after an externally delivered `SIGKILL`.

Crash causality instead requires all of the following on the same guest run:

- exactly one direct content-process PID/start-time identity before fault;
- successful `SIGKILL` delivery to that identity;
- exact disappearance of the old identity;
- a measured zero-content-process intermediate state;
- generation-two recovery with exactly one distinct replacement identity;
- a recovered content screenshot while trusted native chrome survives.

The guest also proves systemd PID 1, udev, D-Bus, logind, Weston headless
Wayland, one logical content surface, image-local bounded Servo input/IME,
popup and external-navigation denial, no non-loopback network device, and the
product AgentPort remaining disabled and absent. Native host input remains the
separate D0A-02 headed-host claim and is not silently promoted into an
OS-native D2I claim.

A passing pull-request run is only a candidate. Promotion additionally requires
independent security review, protected `main`, reviewed merge, and a fresh
exact `refs/heads/main` run. D2I proves no BrowserActor, production AgentPort,
external effect, Secure Boot, hardware, signed update, or release readiness.
