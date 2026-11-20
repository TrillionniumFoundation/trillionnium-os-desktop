"""Original process resource limits; no Gallery install or ART replacement API."""
import os, resource
from pathlib import Path
PACKAGE = 'com.android.gallery3d'
APK_SHA = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
APK_BYTES = 7390425
def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def _local_resources():
    current = Path('/proc/self/cgroup').read_text().strip()
    need(current.startswith('0::/') and current != '0::/', 'OWN_BOUNDED_RESOURCE_SCOPE_REQUIRED')
    group = Path('/sys/fs/cgroup') / current[3:].lstrip('/')
    values = {key: (group / key).read_text().strip()
              for key in ('cpu.max', 'memory.max', 'memory.swap.max', 'pids.max')}
    quota, period = map(int, values['cpu.max'].split())
    need(0 < quota <= 2 * period and values['memory.max'].isdigit()
         and 0 < int(values['memory.max']) <= 2 * 1024**3 and values['memory.swap.max'] == '0'
         and values['pids.max'] == '64' and (group / 'memory.swap.current').read_text().strip() == '0'
         and os.sched_getaffinity(0) <= {20, 21}
         and resource.getrlimit(resource.RLIMIT_CORE) == (0, 0), 'OWN_RESOURCE_LIMIT_CHANGED')
    events = {key: int(value) for key, value in
              (line.split() for line in (group / 'memory.events').read_text().splitlines())}
    need(all(events.get(key, 0) == 0 for key in ('oom', 'oom_kill', 'oom_group_kill')),
         'OWN_GALLERY_RESOURCE_OOM')
    return {'cgroup': current, 'limits': values, 'affinity': sorted(os.sched_getaffinity(0)),
        'memory_events': events, 'memory_peak_bytes': int((group / 'memory.peak').read_text()),
        'swap_current_bytes': int((group / 'memory.swap.current').read_text())}


# Appended to the unchanged local resource checker by adapt_sources.py.
# The only binding caller is the pinned entry, which checks the exact validator
# class before supplying this live in-process lease object.
_RESOURCE_SCOPE = None


def bind_resource_scope(scope):
    global _RESOURCE_SCOPE
    need(_RESOURCE_SCOPE is None and type(scope).__name__ == 'OwnedLeafResources'
         and callable(getattr(scope, 'report', None)), 'ONE_LIVE_OWNED_NATIVE_RESOURCE_SCOPE_REQUIRED')
    _RESOURCE_SCOPE = scope


def resources():
    if _RESOURCE_SCOPE is None:
        return _local_resources()
    value = _RESOURCE_SCOPE.report()
    expected = {'schema', 'cgroup', 'limiting_ancestor', 'limits', 'child_local_limits', 'affinity',
                'memory_events', 'memory_peak_bytes', 'swap_current_bytes', 'native_parent_pid',
                'native_parent_start_ticks', 'hierarchy_is_within_original_native_retirement_scope'}
    need(type(value) is dict and set(value) == expected
         and value['schema'] == 'pocket4-held-effective-leaf-resources-v1',
         'EXACT_FRESH_OWNED_RESOURCE_REPORT')
    current = Path('/proc/self/cgroup').read_text().strip()
    need(type(value['cgroup']) is str and value['cgroup'] == current
         and current.startswith('0::/') and current != '0::/'
         and type(value['limiting_ancestor']) is str and value['limiting_ancestor'].startswith('0::/')
         and value['limiting_ancestor'] != '0::/'
         and Path(current[3:]).parent == Path(value['limiting_ancestor'][3:]),
         'ACTUAL_CHILD_AND_IMMEDIATE_NATIVE_ANCESTOR_REQUIRED')
    limits = value['limits']; keys = {'cpu.max', 'memory.max', 'memory.swap.max', 'pids.max'}
    need(type(limits) is dict and set(limits) == keys
         and all(type(item) is str for item in limits.values()), 'TYPED_EFFECTIVE_RESOURCE_LIMITS')
    cpu = limits['cpu.max'].split()
    need(len(cpu) == 2 and all(item.isdigit() for item in cpu)
         and int(cpu[1]) > 0 and 0 < int(cpu[0]) <= 2*int(cpu[1])
         and limits['memory.max'] == '2147483648' and limits['memory.swap.max'] == '0'
         and limits['pids.max'] == '64', 'ORIGINAL_EFFECTIVE_RESOURCE_LIMITS_REQUIRED')
    child = value['child_local_limits']
    need(type(child) is dict and set(child) <= keys
         and all(type(item) is str for item in child.values()), 'ACTUAL_OPTIONAL_CHILD_LIMITS_ONLY')
    for key, item in child.items():
        parts = item.split()
        if key == 'cpu.max':
            need(len(parts) == 2 and (parts[0] == 'max' or parts[0].isdigit() and int(parts[0]) > 0)
                 and parts[1].isdigit() and int(parts[1]) > 0, 'REAL_CHILD_CPU_LIMIT_SYNTAX')
        else:
            need(item == 'max' or item.isdigit(), 'REAL_CHILD_MEMORY_OR_PID_LIMIT_SYNTAX')
    affinity = sorted(os.sched_getaffinity(0))
    need(affinity and set(affinity) <= {20, 21} and value['affinity'] == affinity
         and resource.getrlimit(resource.RLIMIT_CORE) == (0, 0), 'ORIGINAL_SELF_AFFINITY_AND_CORE_REQUIRED')
    events = value['memory_events']
    need(type(events) is dict and all(type(key) is str and type(item) is int and item >= 0
                                    for key, item in events.items())
         and all(events.get(key) == 0 for key in ('oom', 'oom_kill', 'oom_group_kill')),
         'ACTUAL_ANCESTOR_MEMORY_EVENTS_WITHOUT_OOM_REQUIRED')
    need(type(value['memory_peak_bytes']) is int and value['memory_peak_bytes'] >= 0
         and type(value['swap_current_bytes']) is int and value['swap_current_bytes'] == 0
         and type(value['native_parent_pid']) is int and value['native_parent_pid'] == os.getppid()
         and type(value['native_parent_start_ticks']) is int and value['native_parent_start_ticks'] > 0,
         'ACTUAL_PARENT_PROCESS_AND_RESOURCE_NUMBERS_REQUIRED')
    # Admission comes from the held scope's real checks above. This returned
    # marker is recorded only; no caller can supply a saved JSON report here.
    return value
