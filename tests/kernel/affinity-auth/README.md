# Affinity authorization prerequisite

The ordinary SMP 2/4 guest forks a target UID 2001 and an attacker UID 2002.
The attacker must receive `EPERM`, the target's affinity mask must retain its
exact original bits, and the target must complete on its original CPU after
the denied request. Every child is reaped. Target CPU is read through the real
`getcpu` syscall; no libc vDSO implementation is assumed.

The setter checks the caller's effective UID against the target's real/effective
UID, otherwise invokes the existing LSM `SYS_NICE` check in the target process's
user namespace before storing the mask. No PID-table lock spans that check.
This is an authorization prerequisite, not a claim of forced live migration or
hierarchical `cpu.weight` support.

```sh
python3 -I -B tests/kernel/affinity-auth/run.py --smp 2 --output /new/evidence
```

The inherited runner retains raw serial, guest probe binaries, source and boot
artifact digests. It never executes the probe on the host.
