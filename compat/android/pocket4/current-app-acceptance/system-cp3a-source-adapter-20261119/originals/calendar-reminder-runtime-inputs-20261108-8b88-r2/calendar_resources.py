"""Original reminder22 host owner resource contract."""
from pathlib import Path
import os

def need(ok,why):
    if not ok:raise RuntimeError(why)

def own_resources():
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
