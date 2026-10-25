# Proc credential status guest probe

`run.py` builds and runs `probe.c` only inside an ordinary Asterinas guest. It
reuses the shared safety runner, including exact-source product admission,
bounded QEMU execution and complete raw evidence. It is not a host model test.

Run `python3 -B tests/kernel/proc-status/run.py --help` for options. See
[the credential status contract and cases](../../../support/kernel-safety/PROC_STATUS.md)
for the observed regression, privilege boundaries and expected behavior.
