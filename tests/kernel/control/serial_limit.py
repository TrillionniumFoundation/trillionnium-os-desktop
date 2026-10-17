"""Linux child-only hard file-size cap for disposable QEMU serial evidence.

Called as a subprocess pre-exec hook. Do NOT change limits in the parent:
other workloads and the original host need their original resource limits.
"""
import resource

MAX_SERIAL_BYTES = 8 * 1024 * 1024


def limit_serial_file():
    """Before exec, cap all child file writes without raising inherited limits."""
    inherited_soft, inherited_hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    cap = MAX_SERIAL_BYTES
    for inherited in (inherited_soft, inherited_hard):
        if inherited != resource.RLIM_INFINITY:
            cap = min(cap, inherited)
    resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))
