#!/usr/bin/env python3
"""Freeze one complete-package gate request. This script never dispatches it."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REV = HERE.parent
ROOT = '/home/alex/work/pocket4-blueprint-streaming-controls-03-20261105'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(name, data):
    if isinstance(data, str):
        data = data.encode()
    with (HERE/name).open('xb') as output:
        output.write(data)
    return {'path':name, 'bytes':len(data), 'sha256':sha(data)}

def main():
    names = ['run_control.py', 'owned_streaming_test.go', '0009-blueprint-stream-uncached-module-actions.patch']
    files = {n: (HERE/n if n != names[2] else REV/n).read_text() for n in names}
    pins = {n: {'bytes':len(s.encode()), 'sha256':sha(s.encode())} for n,s in files.items()}
    assert pins['0009-blueprint-stream-uncached-module-actions.patch']['sha256'] == '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307'
    assert pins['owned_streaming_test.go']['sha256'] in files['run_control.py']
    ast.parse(files['run_control.py'])
    stage = '''import hashlib, json, os, stat, sys
from pathlib import Path
ROOT = Path(%r)
EXPECTED = %r
def main(packet):
    if os.getuid() != 1000 or os.geteuid() != 1000:
        raise RuntimeError('ordinary operator UID 1000 required')
    if set(packet) != set(EXPECTED):
        raise RuntimeError('unexpected source packet members')
    for name, text in packet.items():
        raw = text.encode('utf-8')
        if len(raw) != EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest() != EXPECTED[name]['sha256']:
            raise RuntimeError('source packet pin mismatch')
    for directory in (ROOT.parent, *ROOT.parent.parents):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise RuntimeError('owned source parent aliases a non-directory')
    if ROOT.exists() or ROOT.is_symlink():
        raise RuntimeError('create-only source root already exists')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    source = ROOT/'source'
    source.mkdir(mode=0o700)
    for name, text in packet.items():
        fd = os.open(source/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(text.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
    with (ROOT/'stage-receipt.json').open('x') as out:
        json.dump({'schema':1, 'files':EXPECTED, 'Main_actions':0, 'only_owned_root_written':True}, out, indent=2)
        out.write('\\n')
        out.flush()
        os.fsync(out.fileno())
    os.execve('/usr/bin/python3', ['/usr/bin/python3','-I','-B',str(source/'run_control.py'),'--execute-once'], {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
''' % (ROOT, pins)
    ast.parse(stage)
    entry = stage + '\nPACKET = json.loads(' + repr(json.dumps(files, sort_keys=True)) + ')\nmain(PACKET)\n'
    ast.parse(entry)
    request = {'host':'pocket4', 'executable':'/usr/bin/python3', 'args':['-I','-B','-'],
               'stdin':entry, 'cwd':'/', 'cpu_quota_percent':100, 'memory_max_bytes':1073741824,
               'nice':15, 'timeout_seconds':600,
               'idempotency_key':'pocket4-blueprint-streaming-complete-package-control-03-20261105'}
    validation = {'schema':1, 'Go_compilation_performed':False, 'remote_dispatch_performed':False, 'python_AST_valid':True}
    p = subprocess.run(['/usr/bin/python3','-I','-B',str(HERE/'run_control.py')],capture_output=True,text=True)
    assert p.returncode == 0 and not p.stderr and json.loads(p.stdout)['mode'] == 'PLAN'
    validation['default_PLAN'] = {'returncode':p.returncode, 'stdout':p.stdout, 'stderr':p.stderr}
    with tempfile.TemporaryDirectory(prefix='patch-check-', dir=HERE) as directory:
        target = Path(directory)/'context.go'
        target.write_bytes((REV/'preimage/context.go').read_bytes())
        argv = ['/usr/bin/git','-C',directory,'apply','--check',str(REV/names[2])]
        check = subprocess.run(argv,capture_output=True,text=True)
        assert check.returncode == 0, check.stderr
        applied = subprocess.run(['/usr/bin/git','-C',directory,'apply',str(REV/names[2])],capture_output=True,text=True)
        assert applied.returncode == 0, applied.stderr
        result = target.read_bytes()
        assert result == (REV/'candidate/context.go').read_bytes()
        validation['actual_git_apply'] = {'check_returncode':check.returncode, 'apply_returncode':applied.returncode, 'complete_candidate_bytes_equal':True, 'candidate_sha256':sha(result)}
    plan = {'schema':1, 'state':'FROZEN_NOT_DISPATCHED', 'source_scope':'complete real Blueprint production package; upstream tests preserved separately, never substituted into production serializers',
            'resources':{'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':15,'timeout_seconds':600,'compiler_affinity_cpus':1,'at_least_other_allowed_cpus':2},
            'whole_output_cases':['zero','one','nine','ten','eleven','mixed37','large','enabled13'],
            'direct_serializer_cases':['empty','mixed','large'],
            'write_error_offsets':['0','11','half','last_byte'],
            'additional_controls':['real shard filesystem error and join','8MiB actual serializer allocation comparison','actual whole WriteBuildFile allocation comparison'],
            'required_top_level_tests':6,'required_leaf_cases':18,
            'comparisons':['preimage/candidate complete output filename set and SHA256/length','real buffered/streaming bytes in each executable','exact ENOSPC propagation from real streaming serializer','incremental-enabled fresh-generation arm','Go source and tool pins before/after','no leaked owned children'],
            'not_covered':['restored incremental-cache positive','complete upstream test suite','whole engine full build','OOM victim attribution','Android or Main deployment','NOFILE recovery controls'],
            'normal_builder_integration_required':True, 'whole_app_production_ready':False}
    rows = [save('stage.py',stage), save('exact-request.json',json.dumps(request,indent=2)+'\n'),
            save('LOCAL_VALIDATION.json',json.dumps(validation,indent=2)+'\n'), save('PLAN.json',json.dumps(plan,indent=2)+'\n')]
    rows += [{'path':n,'bytes':len((HERE/n).read_bytes()),'sha256':sha((HERE/n).read_bytes())} for n in ['run_control.py','owned_streaming_test.go','make_request.py']]
    manifest = save('SOURCE_PINS.json',json.dumps({'schema':1,'files':rows,'production_patch':pins[names[2]],'submitted':False},indent=2)+'\n')
    print(json.dumps({'manifest':manifest,'generated':rows,'packet_files':pins},indent=2))

if __name__ == '__main__':
    main()
