# D2I integrated D1 plus headed Servo image

D2I is not satisfied by placing a green D1 run beside a green host Servo run.
The gate starts from the exact reproducible D1 ext4 image, injects one exact
headed Servo runtime and a bounded qualification-only systemd overlay twice,
and requires the resulting images to be byte-for-byte identical.

The tested image boots under QEMU q35/TCG with `-nic none`. systemd starts the
existing headless Weston service, then runs the headed workspace as the
unprivileged `hepta-desktop` user. The runtime has a private network namespace,
may use AF_UNIX for Wayland and Servo IPC, and has no product AgentPort
activation marker or socket.

Guest acceptance binds the result to:

- systemd, udev, D-Bus, logind and headless Wayland being active;
- one visible native workspace window with native trusted chrome;
- exactly one logical untrusted content surface;
- page-observed pointer, button, wheel and keyboard input;
- Servo IME composition start, update and end submission;
- a second recovered content generation and recovery screenshot;
- no QEMU network device and no active product AgentPort.

The first candidate intentionally records that the product runtime currently
proves controlled content-surface replacement, not an independently observed
content-process crash callback. D2I cannot be promoted to closed until the
runtime exercises and records a real crash boundary, the exact-head workflow
passes, digest-bound evidence is committed, independent review completes, and
the exact integrated `main` revision is rerun.
