#!/usr/bin/env python3
"""Create r2 with only owned invocation resource observations added to r1."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
import shutil
import subprocess

BASE = Path(__file__).resolve().parent
OLD = BASE/'blueprint-streaming-r1'
NEW = BASE/'blueprint-streaming-r2'

RESOURCE = r'''
def resource_text(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        raw = os.read(fd, 32769)
        require(len(raw) <= 32768, 'owned resource observation exceeds bound')
        return raw.decode('ascii').strip()
    finally:
        os.close(fd)

def resource_events(text):
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows), 'malformed owned memory.events')
    events = {row[0]:int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(k in events for k in ['oom','oom_kill','oom_group_kill']), 'incomplete or duplicate owned memory.events')
    return events

def resource_snapshot(directory_fd, membership):
    observed = Path('/proc/self/cgroup').read_text().strip()
    require(observed == membership, 'controller cgroup membership changed')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    held_st = os.fstat(directory_fd)
    named_st = path.lstat()
    require(stat.S_ISDIR(held_st.st_mode) and stat.S_ISDIR(named_st.st_mode) and
            (held_st.st_dev,held_st.st_ino) == (named_st.st_dev,named_st.st_ino), 'owned invocation cgroup identity changed')
    fields = {name:resource_text(directory_fd,name) for name in [
        'cgroup.procs','memory.events','memory.current','memory.peak','memory.high','memory.max',
        'memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max']}
    require(str(os.getpid()) in fields['cgroup.procs'].split(), 'controller is not in the held invocation')
    require(fields['memory.max'] == '1073741824' and fields['cpu.max'] == '100000 100000', 'owned resource limits do not match the request')
    for key in ['memory.current','memory.peak','memory.swap.current','memory.swap.peak']:
        require(fields[key].isdigit(), 'invalid owned resource counter: '+key)
    return {'observed_utc':utc(), 'membership':membership, 'path':str(path),
            'directory_identity':[held_st.st_dev,held_st.st_ino],
            'controller_pid':os.getpid(), 'fields':fields, 'events':resource_events(fields['memory.events'])}

def begin_resources():
    membership = Path('/proc/self/cgroup').read_text().strip()
    require('\n' not in membership and membership.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'), 'not the exact owned user invocation')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    require(path.name.startswith('hepta-runtime-job-') and path.name.endswith('.service') and '..' not in path.parts, 'unexpected owned unit path')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = resource_snapshot(fd,membership)
        require(all(before['events'][k] == 0 for k in ['oom','oom_kill','oom_group_kill']), 'owned invocation already recorded OOM before the control')
        return fd,before
    except BaseException:
        os.close(fd)
        raise

def finish_resources(directory_fd, before, report):
    after = resource_snapshot(directory_fd,before['membership'])
    report['owned_resources_after'] = after
    report['owned_memory_peak'] = int(after['fields']['memory.peak'])
    report['owned_memory_swap_peak'] = int(after['fields']['memory.swap.peak'])
    require(after['directory_identity'] == before['directory_identity'], 'owned cgroup object replaced')
    require(set(before['events']) == set(after['events']), 'owned memory event fields changed')
    delta = {key:after['events'][key]-value for key,value in before['events'].items()}
    report['owned_memory_events_delta'] = delta
    require(all(value >= 0 for value in delta.values()), 'owned memory event counters went backwards')
    require(all(delta[key] == 0 for key in ['oom','oom_kill','oom_group_kill']), 'owned OOM event occurred; control is not qualified')
    require(all(before['fields'][key] == after['fields'][key] for key in ['memory.max','memory.high','memory.swap.max','cpu.max']), 'owned cgroup limits changed during control')
    return {'pass':True, 'before':before, 'after':after, 'memory_events_delta':delta,
            'memory_peak':int(after['fields']['memory.peak']), 'memory_swap_peak':int(after['fields']['memory.swap.peak']),
            'resource_settings_changed':False, 'swap_max_observed_only':after['fields']['memory.swap.max']}
'''

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    with path.open('xb') as stream:
        stream.write(data)

def main():
    NEW.mkdir(mode=0o700)
    for relative in ['preimage/context.go','candidate/context.go','0009-blueprint-stream-uncached-module-actions.patch','controls/owned_streaming_test.go']:
        save(NEW/relative,(OLD/relative).read_bytes())
    source = (OLD/'controls/run_control.py').read_text()
    assert sha(source.encode()) == '25d4e7cf8bfb5b51e050f0c351fd51f4908e113bfdaaf5e9101f893031d18cf4'
    candidate = source.replace('pocket4-blueprint-streaming-controls-01-20261105','pocket4-blueprint-streaming-controls-02-20261105')
    assert candidate.count('\ndef execute():\n') == 1
    candidate = candidate.replace('\ndef execute():\n',RESOURCE+'\n\ndef execute():\n')
    anchor = "    input_rows = []\n    tool_rows = []\n    try:\n"
    replacement = ("    input_rows = []\n    tool_rows = []\n    resource_fd = -1\n    resource_before = None\n    try:\n"
                   "        resource_fd, resource_before = begin_resources()\n"
                   "        report['owned_resources_before'] = resource_before\n")
    assert candidate.count(anchor) == 1
    candidate = candidate.replace(anchor,replacement)
    anchor = "        report['finished_utc'] = utc()\n"
    replacement = ("        try:\n"
                   "            require(resource_fd >= 0 and resource_before is not None, 'owned resource admission was not observed')\n"
                   "            report['owned_resource_gate'] = finish_resources(resource_fd,resource_before,report)\n"
                   "        except Exception as error:\n"
                   "            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}\n"
                   "            report['state'] = 'FAIL'\n"
                   "        finally:\n"
                   "            if resource_fd >= 0:\n"
                   "                os.close(resource_fd)\n"
                   "        report['finished_utc'] = utc()\n")
    assert candidate.count(anchor) == 1
    candidate = candidate.replace(anchor,replacement)
    ast.parse(candidate)
    save(NEW/'controls/run_control.py',candidate)
    generator = (OLD/'controls/make_request.py').read_text().replace('pocket4-blueprint-streaming-controls-01-20261105','pocket4-blueprint-streaming-controls-02-20261105').replace('pocket4-blueprint-streaming-complete-package-control-01-20261105','pocket4-blueprint-streaming-complete-package-control-02-20261105')
    save(NEW/'controls/make_request.py',generator)
    save(NEW/'controls/r1-to-r2.patch',''.join(difflib.unified_diff(source.splitlines(True),candidate.splitlines(True),fromfile='r1/run_control.py',tofile='r2/run_control.py')))
    result = subprocess.run(['/usr/bin/python3','-I','-B',str(NEW/'controls/make_request.py')],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    print(result.stdout)
    print(json.dumps({'r1_unchanged':sha((OLD/'controls/run_control.py').read_bytes()) == '25d4e7cf8bfb5b51e050f0c351fd51f4908e113bfdaaf5e9101f893031d18cf4',
                      'tests_identical':(NEW/'controls/owned_streaming_test.go').read_bytes() == (OLD/'controls/owned_streaming_test.go').read_bytes(),
                      'resource_patch':{'bytes':(NEW/'controls/r1-to-r2.patch').stat().st_size,'sha256':sha((NEW/'controls/r1-to-r2.patch').read_bytes())}},indent=2))

if __name__ == '__main__':
    main()
