# Scheduling escalation resource limits

The owned ordinary guest probe checks the actual Linux ABI, with a separate
short-lived process for each case. It observes return values and scheduling
attributes after refusal. Root prepares each target's real soft resource limits,
then the target drops all capabilities before exercising the self-service API.
No probe is executed on the host. The guest has no host disks or network.

Run `python3 -I -B tests/kernel/sched-policy-limits/run.py --smp 4 --output
/new/external/path` with this checkout's source-built OSDK and VDSO. An exact
clean ordinary product receipt may be supplied with `--product-evidence`.

The test-only first commit intentionally preserves vulnerable kernel bytes and
records failures before implementation. Cases cover zero and nonzero RTPRIO,
existing RT priority ceilings, `20 - nice` authorization, preserved nice values
for `sched_setscheduler`, and unsupported scheduling flags. This probe does not
qualify physical CPU migration, CPU-controller weights or real-time latency.
The independent `setpriority` ownership, limit conversion and ineffective Fair
update defects require the subsequent priority API stage; this stage does not
claim that bypass fixed.

References: [sched(7)](https://man7.org/linux/man-pages/man7/sched.7.html) and
[Linux v6.17 scheduling syscalls](https://github.com/torvalds/linux/blob/v6.17/kernel/sched/syscalls.c).

The extended probe keeps the original 58 return/state assertions and adds
consistent readback across all three scheduling getters, Normal nice 19 versus
declared Idle, retained static nice across RT and Idle, positive nice raises,
and full-width infinite soft limits. Forty scenarios produce 160 assertions.
Its separate before stage retains P2 policy checks while exposing the remaining
legacy getter conversion defects.
