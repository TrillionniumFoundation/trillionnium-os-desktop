"""Canonical, non-authorizing PCI identity checks for A09 observations.

No device I/O. Linux PCI sysfs commonly writes 4 domain hex digits while
CUDA Driver API may return 8, e.g. 0000:01:00.0 vs 00000000:01:00.0.
Canonicalization is ONLY equality of observed identities; it does not
authenticate a device, IOMMU isolation, a driver or an executable lease.
"""
import re

_BDF = re.compile(
    r"^(?:([0-9a-fA-F]{4}|[0-9a-fA-F]{8})):"
    r"([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])$"
)


def canonical_bdf(value):
    """Return an 8-digit-domain PCI BDF or None for malformed input."""
    if not isinstance(value, str):
        return None
    match = _BDF.fullmatch(value)
    if match is None:
        return None
    domain, bus, slot, func = match.groups()
    dev = int(slot, 16)
    # A PCI device number has five bits, not eight.
    if dev > 0x1f:
        return None
    return f"{int(domain, 16):08x}:{int(bus, 16):02x}:{dev:02x}.{func}"


def canonical_nvidia_model(value):
    """Normalize optional NVIDIA/GeForce prefixes, never fuzzy substrings."""
    if not isinstance(value, str):
        return None
    name = " ".join(value.casefold().split())
    for prefix in ("nvidia geforce ", "geforce ", "nvidia "):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name or None


def matches_target_model(actual, requested):
    canonical_request = canonical_nvidia_model(requested)
    return (canonical_request is not None
            and canonical_request == canonical_nvidia_model(actual))
