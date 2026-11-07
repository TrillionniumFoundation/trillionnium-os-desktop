#!/usr/bin/env python3
"""Verify frozen encoding; execute only an explicit default-PLAN wrapper variant."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def record(path):
    raw = path.read_bytes()
    raw.decode('utf-8','strict')
    return dict(path=path.name, bytes=len(raw), sha256=digest(raw),
                git_blob_sha1=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),
                mode='100644', encoding='utf-8')


request_raw = (HERE/'exact-request.json').read_bytes()
packet_raw = (HERE/'request-stdin.json').read_bytes()
wrapper = (HERE/'wrapper.py').read_text()
request = json.loads(request_raw)
assert request['host']=='pocket4' and request['executable']=='/usr/bin/sudo'
assert request['args']==['-n','/usr/bin/python3','-I','-B','-c',wrapper]
assert request['cwd']=='/' and request['env']=={'PYTHONDONTWRITEBYTECODE':'1'}
assert request['stdin'].encode()==packet_raw
assert request['idempotency_key']=='p4-action-lock-differential02-'+digest(packet_raw)[:16]
assert {k:request[k] for k in ('cpu_quota_percent','memory_max_bytes','nice','timeout_seconds')} == {
    'cpu_quota_percent':100, 'memory_max_bytes':134217728, 'nice':10, 'timeout_seconds':30}
packet=json.loads(packet_raw)
manifest=json.loads((HERE/'source-manifest.json').read_bytes())
expected={row['path']:(row['bytes'],row['sha256']) for row in manifest['files']}
assert set(packet)=={'schema','files'} and type(packet['schema']) is int and packet['schema']==1
assert set(packet['files'])==set(expected)=={'probe_lock.py','read_main_identity.py','prior-ticket-launch.json','prior-admission.json'}
for name,value in packet['files'].items():
    body=value.encode()
    assert body==(HERE/name).read_bytes()
    assert (len(body),digest(body))==expected[name]
    if name.endswith('.py'):
        compile(body,name,'exec')
assignments={node.targets[0].id:node.value for node in ast.parse(wrapper).body
             if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)}
assert ast.literal_eval(assignments['EXPECTED'])==expected
assert repr(digest(packet_raw)) in wrapper and 'len(raw) != '+str(len(packet_raw)) in wrapper
assert wrapper.endswith("raise SystemExit(probe.main(support, bodies['prior-ticket-launch.json'], bodies['prior-admission.json'], ['--admit-once']))\n")
assert wrapper.count("['--admit-once']")==1
plan_wrapper=wrapper.replace("['--admit-once']",'[]')
plan=subprocess.run([sys.executable,'-I','-B','-c',plan_wrapper],input=packet_raw,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
assert plan.returncode==0 and not plan.stderr
plan_result=json.loads(plan.stdout)
assert plan_result['state']=='PLAN_ONLY' and plan_result['exclusive_attempts_per_arm']==1
assert plan_result['runtime_authorized'] is False and plan_result['Android_actions']==0
for name,raw in [('plan.stdout.json',plan.stdout),('plan.stderr.txt',plan.stderr)]:
    with (HERE/name).open('xb') as stream:
        stream.write(raw)
result=dict(schema=1, exact_packet_member_bytes=True, exact_wrapper_and_resource_binding=True,
            four_member_manifest=manifest['files'], exact_request=record(HERE/'exact-request.json'),
            stdin=record(HERE/'request-stdin.json'), wrapper=record(HERE/'wrapper.py'),
            default_PLAN=dict(exit_code=plan.returncode, stdout=record(HERE/'plan.stdout.json'),
                              stderr=record(HERE/'plan.stderr.txt'),
                              variant_sha256=digest(plan_wrapper.encode()),
                              change="only ['--admit-once'] -> []"),
            actual_collect_or_admit_executed=False, Hepta_calls=0)
with (HERE/'packet-validation.json').open('x') as stream:
    json.dump(result,stream,sort_keys=True,indent=2)
    stream.write('\n')
members=[record(path) for path in sorted(HERE.iterdir()) if path.is_file()]
assert all(path.suffix!='.pyc' for path in HERE.iterdir())
with (HERE/'FROZEN_FILES.json').open('x') as stream:
    json.dump(dict(schema=1,scope='one exact two-arm lock differential; no device execution',
                   files=members),stream,sort_keys=True,indent=2)
    stream.write('\n')
print(json.dumps(dict(payload_count=len(members), manifest=record(HERE/'FROZEN_FILES.json'),
                      request=record(HERE/'exact-request.json'),stdin=record(HERE/'request-stdin.json'),
                      idempotency_key=request['idempotency_key'],default_PLAN_exit_code=0),sort_keys=True))
