# Unprivileged TRACEME establishment deadlock

One owned child exposes only a public read-only sentinel. Linux passes15 actual
observations as UID60001/caps0/NNP1: after TRACEME and stops, PEEK returns EIO,
the exact public sentinel, then EIO as dumpability changes0→1→0. The child is reaped.

The original0252 guest times out at the original120s limit before establishing
the relationship. Its parent alarm is observed, but guest-child reaping is not
proven. The disposable QEMU child is reaped by the wrapper. This result is not
evidence of an established-relationship PEEK bypass. Source inspection identifies
the lock cycle: TRACEME holds child.parent while its original default Yama
ancestry check tries to lock the same child.parent. Existing Root tests take a
capability shortcut and do not cover this unprivileged cycle.

The original failed wrapper/assertion, complete serial, exact source blobs,
Linux observations and3 strict checker tests rejecting24 mutations are retained.
The checker also rejects this actual timed-out guest. Fixed-kernel qualification
must pass the same complete Linux-backed15-observation oracle at the original
limit. PTRACE_ATTACH, injection and unrelated process reads are outside scope.
See [the complete manifest](publication.json). The unchanged shared checker is
in [the lifecycle publication](../kernel-dumpable-lifecycle-counterexample/README.md).
