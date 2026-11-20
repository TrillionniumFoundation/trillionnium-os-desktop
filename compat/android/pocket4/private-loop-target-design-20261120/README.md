# Original apexd private loop target: implementation input

Status on 2026-11-20: **design and a passing userspace protocol model only**. The missing native target issuer remains a production blocker. This packet changes no runtime gate, production binary, kernel, security policy, image, app, or CURRENT pointer.

The inspected implementation can configure an ordinary host loop device and retain its backing file. It cannot give the unchanged original apexd a genuinely isolated, unconfigured, O_RDWR block open-file description, obtain the real `LOOP_CONFIGURE(fd=-1)` EBADF probe result, and then configure that same open-file description under the required ownership and retirement rules. Renaming a host loop node does not supply isolation.

## Contents

- `DESIGN.md`: exact source findings, minimum kernel/runtime contract, implementation order, native acceptance, and the conventional VM comparison.
- `INPUTS.json`: exact host paths, byte lengths, SHA256 values, repository base, and bounded search coverage. Source snapshots are references; the 15 reviewed source files are deliberately not copied into this packet.
- `protocol_model.rs`: pure Rust finite state model. Fact inputs are assumptions. It performs no syscall, device, process, filesystem, or network operation.
- `MODEL-VALIDATION.json`: actual bounded model compile/test outputs, including the initial failed arbitrary coverage threshold and its correction. Final result is 19/19 model tests and a fixed point of 71 states / 1349 transitions; native kernel and Android qualification remain false.
- `HANDOFF.json`: the next concrete source task, dependency order, and actions that must not be retried or performed during the active vendor build.

## Start here

The first implementation task is the narrowly scoped Rust identity decomposition in `DESIGN.md` task R0. It separates the stable apexd actor/epoch identity from the individual seccomp notification, preserving all current checks and keeping the target issuer unconstructible. The two genuine ioctl requests necessarily have different notification IDs; today's generation type includes the notification. Do not simply remove that field from equality or weaken request validation.

The subsequent kernel work needs a separate reviewed patch series. No incomplete block-device patch is supplied as an allegedly safe implementation. Ordinary global loop instances, the existing one-shot namespace grant, ublk, cgroup device permissions, or a fake EBADF response do not provide the missing contract.

The estimated native interface effort is **2–4 engineering weeks with two experienced kernel/runtime engineers**, conditional on an authorized isolated qualification environment. That is an engineering estimate for this interface, not work completed in this turn and not a date for full Android or all 39 apps to become production ready. The prior privileged VM fixture approval rejection remains in force; this packet does not authorize retrying it or substituting a differently named action.
