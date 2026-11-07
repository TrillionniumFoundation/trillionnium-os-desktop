#!/usr/bin/env python3
"""Local final binding checks; execute only an in-memory PLAN variant."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'action-lock-main-fds-readonly-01'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def pin(path):
    body=path.read_bytes();body.decode('utf-8','strict')
    return dict(path=path.name,bytes=len(body),sha256=sha(body),
                git_blob_sha1=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest(),
                mode='100644',encoding='utf-8')


def put(name,value):
    with (HERE/name).open('xb') as f:
        f.write((json.dumps(value,sort_keys=True,indent=2)+'\n').encode())


def functions(body):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(body).body
            if isinstance(n,(ast.FunctionDef,ast.ClassDef))}


def main():
    request=json.loads((HERE/'exact-request.json').read_bytes())
    packet_raw=(HERE/'request-stdin.json').read_bytes();packet=json.loads(packet_raw)
    wrapper=(HERE/'wrapper.py').read_text()
    manifest=json.loads((HERE/'source-manifest.json').read_bytes())
    assert set(packet)=={'schema','files'} and packet['schema']==1 and len(packet['files'])==3
    assert set(packet['files'])=={r['path'] for r in manifest['files']}
    for r in manifest['files']:
        assert r==pin(HERE/r['path']) and packet['files'][r['path']].encode()==(HERE/r['path']).read_bytes()
    assert request['stdin'].encode()==packet_raw and len(packet_raw)<=131072
    assert request['args']==['-n','/usr/bin/python3','-I','-B','-c',wrapper]
    assert request['host']=='pocket4' and request['executable']=='/usr/bin/sudo' and request['cwd']=='/'
    assert request['env']=={'PYTHONDONTWRITEBYTECODE':'1'}
    assert (request['cpu_quota_percent'],request['memory_max_bytes'],request['nice'],request['timeout_seconds'])==(100,134217728,10,30)
    assert request['idempotency_key']=='p4-action-lock-visible-fds-readonly01-'+sha(packet_raw)[:16]
    assert str(len(packet_raw)) in wrapper and repr(sha(packet_raw)) in wrapper
    assert (HERE/'read_main_identity.py').read_bytes()==(OLD/'read_main_identity.py').read_bytes()
    assert (HERE/'prior-ticket-launch.json').read_bytes()==(OLD/'prior-ticket-launch.json').read_bytes()
    source=(HERE/'read_visible_lock_fds.py').read_bytes()
    original=(OLD/'read_main_lock_fds.py').read_bytes()
    assert (len(source),sha(source))==(41061,'8fed4dffbfb67467571189895f6dc56e8bd13aba0fba094107260526a697200e')
    assert (len(original),sha(original))==(36349,'db4916ebee6e6094482236e10ed2ecd3030d7f245de18f53c8a0cfd9c50a2cb0')
    delta=''.join(difflib.unified_diff(original.decode().splitlines(True),source.decode().splitlines(True),
                    fromfile='main7/read_main_lock_fds.py',tofile='visible/read_visible_lock_fds.py')).encode()
    assert delta==(HERE/'main7-to-visible-PIDs.patch').read_bytes()
    a,b=functions(original),functions(source)
    identical=sorted(k for k in a.keys()&b.keys() if a[k]==b[k]);assert len(identical)==18
    old_collect=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='collect')
    new_collect=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='collect')
    old_guard=next(n for n in old_collect.body if isinstance(n,ast.FunctionDef) and n.name=='guard')
    new_guard=next(n for n in new_collect.body if isinstance(n,ast.FunctionDef) and n.name=='guard')
    assert ast.dump(old_guard,include_attributes=False)==ast.dump(new_guard,include_attributes=False)
    controls=json.loads((HERE/'controls01.stdout.json').read_bytes())
    receipt=json.loads((HERE/'controls01-receipt.json').read_bytes())
    assert controls['count']==5 and all(r['passed'] for r in controls['results'])
    assert controls['source_sha256']==sha(source) and receipt['returncode']==0
    for n,k in [('controls01.stdout.json','stdout'),('controls01.stderr.txt','stderr'),('check_new_controls.py','controls')]:
        actual=pin(HERE/n);assert receipt[k]==dict(bytes=actual['bytes'],sha256=actual['sha256'])
    for n in ('read_visible_lock_fds.py','read_main_identity.py','make_request.py','check_new_controls.py','wrapper.py'):
        ast.parse((HERE/n).read_bytes())
    assert wrapper.count("['--collect-once']")==1
    plan_wrapper=wrapper.replace("['--collect-once']",'[]')
    result=subprocess.run(['/usr/bin/python3','-I','-B','-c',plan_wrapper],input=packet_raw,
                          capture_output=True,cwd='/',timeout=10,check=False)
    assert result.returncode==0 and not result.stderr
    plan=json.loads(result.stdout)
    assert plan['state']=='PLAN_ONLY' and plan['runtime_authorized'] is False and plan['remote_actions']==0
    for n,body in [('plan.stdout.json',result.stdout),('plan.stderr.txt',result.stderr)]:
        with (HERE/n).open('xb') as f:f.write(body)
    value=dict(schema=1,passed=True,source=pin(HERE/'read_visible_lock_fds.py'),
        original=pin(OLD/'read_main_lock_fds.py'),delta=pin(HERE/'main7-to-visible-PIDs.patch'),
        request=pin(HERE/'exact-request.json'),stdin=pin(HERE/'request-stdin.json'),wrapper=pin(HERE/'wrapper.py'),
        runtime_member_count=3,all_members_byte_equal=True,request_stdin_exact=True,original_support_and_prior_exact=True,
        unchanged_helper_AST=identical,original_Main_guard_function_AST_unchanged=True,
        changed_functions=sorted(k for k in a.keys()&b.keys() if a[k]!=b[k]),
        added_functions=sorted(b.keys()-a.keys()),removed_functions=sorted(a.keys()-b.keys()),
        controls=pin(HERE/'controls01-receipt.json'),PLAN_actual_returncode=0,PLAN_stdout=pin(HERE/'plan.stdout.json'),
        PLAN_variant_changed_only_collect_argument=True,collect_executed=False,live_proc_reads=False,
        remote_calls=False,qualification=False)
    put('packet-validation.json',value)
    print(json.dumps(dict(passed=True,request=pin(HERE/'exact-request.json'),stdin=pin(HERE/'request-stdin.json'),
                          validation=pin(HERE/'packet-validation.json'),idempotency_key=request['idempotency_key']),sort_keys=True))


if __name__=='__main__':
    main()
