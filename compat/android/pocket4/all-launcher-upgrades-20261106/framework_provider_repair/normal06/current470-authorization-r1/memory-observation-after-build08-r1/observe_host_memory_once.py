"""One read of host meminfo after settled build08; no retry or build authority."""
import os
import sys
import time
import json
import hashlib
from datetime import datetime, timezone

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def parse_admission_meminfo(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 16384,
            "fixed meminfo byte bound differs")
    names = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "SwapCached"}
    memory = {}
    for line in raw.decode("ascii", "strict").splitlines():
        name, separator, value = line.partition(":")
        if name not in names:
            continue
        require(name not in memory, "duplicate required meminfo field")
        words = value.split()
        require(separator == ":" and len(words) == 2 and words[0].isdigit() and words[1] == "kB",
                "required meminfo field units differ")
        memory[name] = int(words[0]) * 1024
    require(set(memory) == names, "required meminfo fields incomplete")
    require(0 < memory["MemTotal"] and 0 <= memory["MemAvailable"] <= memory["MemTotal"] and
            0 <= memory["SwapFree"] <= memory["SwapTotal"] and memory["SwapCached"] >= 0,
            "required meminfo values inconsistent")
    return memory

require(sys.argv == ['-c', '--sample-once'], 'one fixed read-only invocation')
require(os.getuid() == os.geteuid() == 1000, 'existing operator identity required')
started = time.monotonic()
fd = os.open('/proc/meminfo', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
try:
    raw = os.read(fd, 16385)
finally:
    os.close(fd)
values = parse_admission_meminfo(raw)
require(time.monotonic() - started <= 5, 'bounded single meminfo observation')
print(json.dumps({'schema': 'pocket4-single-host-memory-observation-v1',
    'observed_utc': datetime.now(timezone.utc).isoformat(), 'raw_ascii': raw.decode('ascii'),
    'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest(), 'values_bytes': values,
    'original_minimum_bytes': 15 * 1024 ** 3,
    'difference_from_original_minimum_bytes': values['MemAvailable'] - 15 * 1024 ** 3,
    'fresh_build_resource_admission_replaced': False, 'build_or_retry_admitted': False,
    'Main_commands': 0, 'Android_commands': 0, 'signals': 0, 'writes': 0,
    'swap_or_resource_settings_changed': False, 'automatic_retry': False,
    'production_ready': False}, sort_keys=True))
