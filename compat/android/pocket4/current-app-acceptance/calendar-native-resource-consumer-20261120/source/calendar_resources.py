"""Original reminder22 host owner resource contract."""
from pathlib import Path
import os

def need(ok,why):
    if not ok:raise RuntimeError(why)

def _local_own_resources():
    raw=Path('/proc/self/cgroup').read_text()
    lines=[line for line in raw.splitlines() if line.startswith('0::/')]
    need(len(lines)==1,'OWN_HOST_CGROUP_REQUIRED')
    rel=lines[0][3:];need('..' not in Path(rel).parts,'OWN_CGROUP_PATH_UNSAFE')
    directory=Path('/sys/fs/cgroup')/rel.lstrip('/')
    files={}
    for name in ('cpu.max','cpu.stat','memory.max','memory.current','memory.peak',
                 'memory.events','memory.swap.max','memory.swap.current','pids.current'):
        value=(directory/name).read_text();need(len(value)<=8192,'OWN_CGROUP_FIELD_BOUND')
        files[name]=value.strip()
    return {'host_pid':os.getpid(),'cgroup':raw,'directory':str(directory),'files':files}

def resource_limits(value):
    fields=value['files'];quota,period=fields['cpu.max'].split()
    need(quota.isdecimal() and period.isdecimal() and 0<int(quota)*100<=int(period)*50,
         'ACTUAL_OWN_CPU_LIMIT_REQUIRED')
    need(fields['memory.max']=='536870912','ACTUAL_OWN_MEMORY512MIB_LIMIT_REQUIRED')

def memory_events(value):
    rows=[line.split() for line in value['files']['memory.events'].splitlines()]
    need(all(len(r)==2 and r[1].isdecimal() for r in rows),'MEMORY_EVENTS_SHAPE')
    return {k:int(v) for k,v in rows}


# Added only to the new Calendar resource module. The pinned entry checks the
# exact class from its pinned validator before binding this live object.
_RESOURCE_SCOPE = None


def bind_resource_scope(scope):
    global _RESOURCE_SCOPE
    need(_RESOURCE_SCOPE is None and type(scope).__name__ == 'OwnedLeafResources'
         and callable(getattr(scope,'report',None)), 'ONE_LIVE_CALENDAR_RESOURCE_SCOPE_REQUIRED')
    _RESOURCE_SCOPE = scope


def own_resources():
    if _RESOURCE_SCOPE is None:
        return _local_own_resources()
    value = _RESOURCE_SCOPE.report()
    need(type(value) is dict and value.get('schema') == 'pocket4-held-effective-calendar-resources-v1',
         'FRESH_HELD_CALENDAR_RESOURCE_REPORT_REQUIRED')
    current = Path('/proc/self/cgroup').read_text().strip()
    need(value.get('cgroup') == current and current.startswith('0::/') and current != '0::/'
         and type(value.get('limiting_ancestor')) is str and value['limiting_ancestor'].startswith('0::/')
         and value['limiting_ancestor'] != '0::/'
         and Path(current[3:]).parent == Path(value['limiting_ancestor'][3:]),
         'ACTUAL_CHILD_AND_HELD_IMMEDIATE_CALENDAR_ANCESTOR')
    need(type(value.get('native_parent_pid')) is int and value['native_parent_pid'] == os.getppid()
         and type(value.get('native_parent_start_ticks')) is int and value['native_parent_start_ticks'] > 0,
         'ACTUAL_NATIVE_CALENDAR_PARENT_REQUIRED')
    fields = value.get('ancestor_files')
    required = {'cpu.max','cpu.stat','memory.max','memory.current','memory.peak',
                'memory.events','memory.swap.max','memory.swap.current','pids.current'}
    need(type(fields) is dict and set(fields) == required
         and all(type(item) is str and 0 < len(item) <= 8192 for item in fields.values()),
         'ALL_NINE_ORIGINAL_REAL_CALENDAR_RESOURCE_METRICS')
    limits = value.get('limits')
    need(type(limits) is dict and set(limits) == {'cpu.max','memory.max','memory.swap.max','pids.max'}
         and all(type(item) is str for item in limits.values())
         and all(fields[key] == limits[key] for key in ('cpu.max','memory.max','memory.swap.max'))
         and limits['memory.swap.max'] == fields['memory.swap.current'] == '0'
         and limits['pids.max'] == '64', 'REAL_EFFECTIVE_CALENDAR_LIMITS_AND_ZERO_SWAP')
    need(all(fields[key].isdecimal() for key in ('memory.current','memory.peak','pids.current')),
         'REAL_CALENDAR_MEMORY_AND_PID_NUMBERS')
    rows = [row.split() for row in fields['memory.events'].splitlines()]
    need(all(len(row) == 2 and row[1].isdecimal() for row in rows)
         and len({row[0] for row in rows}) == len(rows), 'EXACT_REAL_CALENDAR_MEMORY_EVENT_ROWS')
    events = {key:int(item) for key,item in rows}
    need(all(events.get(key) == 0 for key in ('oom','oom_kill','oom_group_kill')),
         'ACTUAL_CALENDAR_RESOURCE_ANCESTOR_OOM')
    result = {'host_pid':os.getpid(), 'cgroup':current+'\n',
              'directory':str(Path('/sys/fs/cgroup')/value['limiting_ancestor'][3:].lstrip('/')),
              'files':dict(fields), 'own_cgroup_directory':str(Path('/sys/fs/cgroup')/current[3:].lstrip('/')),
              'resource_observation_scope':'actual_held_immediate_native_ancestor',
              'native_resource_binding':value}
    # Keep the original CPU <= 50% and exact 512 MiB check itself unchanged.
    # system_case also invokes it before and after the complete business scope.
    resource_limits(result)
    return result
