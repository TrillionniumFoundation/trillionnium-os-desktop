"""Derive a fresh actual-bound BestBuy launch/inspection from the reviewed IHG flow.

Local source generation and pure receipt checks only. No remote or Android call.
"""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import types

B = Path('/workspace/scratch/94990735b266')
OLD = B / 'android-ihg-launch-inspect-01'
OUT = B / 'android-bestbuy-launch-inspect-01'
INSTALL = B / 'android-bestbuy-qa-r1-install-state-01'
EVIDENCE = B / 'root-recovery-20261104-02/evidence'
REMOTE_INSTALL = '/home/alex/work/pocket4-owned-bestbuy-qa-r1-install-state-01'
REMOTE_RESOLVER = '/home/alex/work/pocket4-bestbuy-artifact-launcher-readonly-01'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def pinned(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    return raw


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def write(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    path = OUT / name
    with path.open('xb') as stream:
        stream.write(raw)
    return raw


def assignment(source, name, value):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    assert len(nodes) == 1, name
    lines = source.splitlines(keepends=True)
    n = nodes[0]
    lines[n.lineno-1:n.end_lineno] = [name + '=' + repr(value) + '\n']
    return ''.join(lines)


def replace(source, before, after, count=1):
    assert source.count(before) == count, (before, source.count(before), count)
    return source.replace(before, after)


def baseline_names(source):
    return (source.replace('com.ihg.apps.android', 'com.bestbuy.android')
            .replace('ihg', 'bestbuy').replace('IHG', 'BESTBUY')
            .replace('amazon', 'bestbuy').replace('Amazon', 'BestBuy').replace('AMAZON', 'BESTBUY')
            .replace('UID=10137', 'UID=10130').replace('10196', '10198')
            .replace('399444a5b72d53139b880a4afefdb31a', NONCE))


assert not OUT.exists()
old_source_manifest = pinned(OLD/'SOURCE_PINS.json', 446,
    '704bf0640c6a207ad8177dfc0240896cc785b6fa6db34521fbea5cd02e42a6fd')
for name, row in json.loads(old_source_manifest)['files'].items():
    pinned(OLD/name, row['bytes'], row['sha256'])
pinned(OLD/'stage_execute.py', 4904, 'fa3620f6f48332fb58b77c28e5e1efc96cde2cdbc65b7f511802f952df7104f1')
pinned(OLD/'make_request.py', 3110, '8463b8ffb3551512a74b25dc924d4a70207d299c89f8b7abbf95a267fd79f0af')
install_manifest_raw = pinned(INSTALL/'SOURCE_PINS.json', 1447,
    '15d6495c30af3b765c9b4df99d8d170001e66ea54ab23327bfc7d785e192d2a4')
install_manifest = json.loads(install_manifest_raw)
for name, row in install_manifest['files'].items():
    pinned(INSTALL/name, row['bytes'], row['sha256'])

install_rows = {}
prior = {}
actual_pins = {}
for key, relative, size, digest in [
    ('coordinator', 'result.json', 3080, 'd0c777b87d5921d4e921ba9c2c207bb1acb907f32a128b8be28634e7fd1a8137'),
    ('stage', 'stage-result.json', 1618, '73ff0bda622585506a96385c7d71ea4381e323839413fe6d53602a991aec84c6'),
    ('worker', 'worker/result.json', 13345, '7aaff595b0774873aea64b82d0b6742ed80159093c9c790543b052c916a6c04c')]:
    path = EVIDENCE/'bestbuy-r1-install-read01'/(key+'.json')
    install_rows[key] = json.loads(pinned(path, size, digest))
    prior[key] = (relative, size, digest)
    actual_pins[key] = {'path': REMOTE_INSTALL+'/'+relative, 'bytes': size, 'sha256': digest}
resolver_rows = {}
resolver_records = {}
for key, relative, size, digest in [
    ('worker', 'result.json', 10112, 'bd394cac42b9ab536c3646c4c6e5c6e755658855c1a4525aa26b9b73cf80f073'),
    ('stage', 'stage-result.json', 1587, '424b8f32a7375b31928947b7d870d83bcc4848dc00e3d2fe4493a99aea165ecb')]:
    path = EVIDENCE/'bestbuy-artifact-launcher-readonly01'/(key+'.reconstructed-from-actual-stdout.json')
    resolver_rows[key] = json.loads(pinned(path, size, digest))
    resolver_records[key] = (relative, size, digest)
worker = install_rows['worker']
metadata = resolver_rows['worker']
installed = worker['installed_before_state']
assert installed == worker['installed_after_state'] and installed['uid'] == 10198
assert installed['held_file']['mtime_ns'] == 1793922580168836679
assert metadata['metadata_before'] == metadata['metadata_after'] == {
    'package':'com.bestbuy.android', 'uid':10130, 'user':0, 'version_code':2012312321}
assert len(metadata['artifacts']) == 3 and metadata['total_apk_bytes'] == 245511693
assert metadata['launcher_resolution']['component'] == 'com.bestbuy.android/.activity.SplashActivity'
NONCE = secrets.token_hex(16)
PLAN = {'schema':1, 'operation':'inspect', 'nonces':{k:secrets.token_hex(16) for k in ('before','inspect','after')}}
assert len({NONCE, *PLAN['nonces'].values()}) == 4

original = (OLD/'owned_inspect.py').read_text()
source = baseline_names(original)
for name, value in {
    'PLAN': PLAN, 'INSTALL_SOURCE_SHA': sha(install_manifest_raw),
    'UTIL_SHA': install_manifest['files']['install_state.py']['sha256'],
    'UTIL_BYTES': install_manifest['files']['install_state.py']['bytes'],
    'CONTEXT_SHA': install_manifest['files']['bestbuy_context.py']['sha256'],
    'TRANSPORT_SHA': install_manifest['files']['bestbuy_transport.py']['sha256'],
    'STATE_NONCE': worker['state_nonce'], 'STATE_WIRE': worker['state']['wire_sha256'],
    'INSTALLED': installed, 'PRIOR': prior,
    'RESOLVER_SHA': metadata['source_sha256'],
    'RESOLVER_BYTES': install_manifest['files']['references/read_bestbuy.py']['bytes'],
    'RESOLVER_NONCE': metadata['nonce'], 'RESOLVER_RECORDS':resolver_records,
}.items():
    source = assignment(source, name, value)
source = replace(source, "COMPONENT=PACKAGE+'/.activity.MainActivity'", "COMPONENT=PACKAGE+'/.activity.SplashActivity'")
source = replace(source, "RUNTIME_FILES=", 'EXPECTED_TARGET_ARTIFACTS='+repr(metadata['artifacts'])+'\nRUNTIME_FILES=')
source = replace(source, "'version_code':50023219", "'version_code':2012312321")
source = replace(source,
    "len(worker['artifacts'])==1 and worker['total_apk_bytes']==44999052 and\n         worker['artifacts'][0]['sha256']=='c12bb3bae3514c94caaca0a4ef6e8f1ad4491cbce57fd2a15be48b83b4c85b90'",
    "worker['artifacts']==EXPECTED_TARGET_ARTIFACTS and len(worker['artifacts'])==3 and\n         worker['total_apk_bytes']==245511693")
source = replace(source, "['held_APK_FDs_closed']==1", "['held_APK_FDs_closed']==3", 2)
source = replace(source, 'len(artifacts.records)==1', 'len(artifacts.records)==3')
source = replace(source, 'The original Ticket observation preceded this helper install',
                 'The original BestBuy observation preceded this helper install')
context = baseline_names((OLD/'ihg_task_context.py').read_text())
stage = baseline_names((OLD/'stage_execute.py').read_text())
for name, body in [('owned_inspect.py', source), ('bestbuy_task_context.py', context), ('stage_execute.py', stage)]:
    ast.parse(body)
    compile(body, name, 'exec')

# Exercise only the receipt qualifiers against full exact originals. No qualified()
# call or runtime loader is made: those require the new remote held source.
scope = types.ModuleType('bestbuy_launch_local_receipt_controls')
scope.__file__ = str(OUT/'owned_inspect.py')
exec(compile(source, scope.__file__, 'exec'), scope.__dict__)
install_qualification = scope.actual_install(install_rows)
resolver_qualification = scope.actual_resolver(resolver_rows, installed)
negative_controls = []
for label, alter in [
    ('missing split', lambda r:r['worker']['artifacts'].pop()),
    ('duplicate split', lambda r:r['worker']['artifacts'].__setitem__(2,copy.deepcopy(r['worker']['artifacts'][1]))),
    ('changed split hash', lambda r:r['worker']['artifacts'][1].__setitem__('sha256','0'*64)),
    ('changed split identity', lambda r:r['worker']['artifacts'][1]['held_file'].__setitem__('inode',1)),
    ('changed target version', lambda r:r['worker']['metadata_before'].__setitem__('version_code',1)),
]:
    changed = copy.deepcopy(resolver_rows)
    alter(changed)
    try:
        scope.actual_resolver(changed, installed)
    except RuntimeError:
        negative_controls.append(label)
    else:
        raise AssertionError(label+' was admitted')

inputs = json.loads((OLD/'INPUTS.json').read_bytes())
install_inputs = json.loads((INSTALL/'INPUTS.json').read_bytes())
actual_review = EVIDENCE/'bestbuy-r1-install-read01/root-actual-review.json'
pinned(actual_review, 1711, '9ef76f73055de2642824b4e575a5abb4137b9e4b2bc079b78a467f3397a846d7')
inputs.update({
    'actual_build': {'APK': install_inputs['APK'], 'build_receipt_sha256': install_inputs['build_receipt']['sha256'],
        'old_v2_provenance_inherited':False, 'self_instrumentation':True,
        'signer_certificate_sha256':install_inputs['signer_certificate_sha256'],
        'source_manifest_sha256':install_inputs['source_manifest_sha256']},
    'actual_install_job':'1a1ae1e3709-fc05-5d8f', 'actual_install_receipts':actual_pins,
    'actual_install_review':pin(actual_review), 'actual_install_source_manifest_sha256':sha(install_manifest_raw),
    'actual_target':{'artifacts':metadata['artifacts'], 'fresh_streaming_hashes':True,
        'metadata':metadata['metadata_before'], 'signer_independently_verified':False},
    'component':metadata['launcher_resolution']['component'],
    'frozen_install_request':pin(INSTALL/'exact-request.json'), 'helper_uid':10198,
    'installed_helper':installed, 'nonce':NONCE, 'read_only_inspection_plan':PLAN,
    'resolver_records':{k:{'relative_path':v[0],'bytes':v[1],'sha256':v[2]} for k,v in resolver_records.items()},
    'state':'ACTUAL_INSTALL_BOUND_FRESH_BESTBUY_LAUNCH_INSPECT_UNRUN',
    'state_wire_sha256':worker['state']['wire_sha256'], 'worker_receipt':actual_pins['worker']})
OUT.mkdir(mode=0o700)
write('owned_inspect.py', source)
write('bestbuy_task_context.py', context)
write('INPUTS.json', pretty(inputs))
manifest = {'schema':1,'files':{name:{k:v for k,v in pin(OUT/name).items() if k!='path'}
    for name in ('owned_inspect.py','bestbuy_task_context.py','INPUTS.json')}}
manifest_raw = write('SOURCE_PINS.json', pretty(manifest))
stage_raw = write('stage_execute.py', stage)
maker = baseline_names((OLD/'make_request.py').read_text())
for name,value in [('MANIFEST_SHA',sha(manifest_raw)),('STAGE_SHA',sha(stage_raw)),('STAGE_BYTES',len(stage_raw))]:
    maker = assignment(maker,name,value)
ast.parse(maker)
write('make_request.py', maker)
cp = subprocess.run([sys.executable,'-I',str(OUT/'make_request.py'),'--write-once',
                     '--output',str(OUT/'exact-request.json')],capture_output=True,timeout=10,check=True)
assert not cp.stderr
request_result = json.loads(cp.stdout)
write('request-pins.json', pretty(request_result))
request = json.loads((OUT/'exact-request.json').read_bytes())
old_request = json.loads((OLD/'exact-request.json').read_bytes())
assert {k:v for k,v in request.items() if k not in ('args','stdin','idempotency_key')} == {
    k:v for k,v in old_request.items() if k not in ('args','stdin','idempotency_key')}
assert request['args'][:-1] == old_request['args'][:-1]
packet=json.loads(request['stdin'])
assert packet['nonce']==NONCE and set(packet['files'])==set(manifest['files'])|{'SOURCE_PINS.json'}
for name,body in packet['files'].items():
    assert body.encode()==(OUT/name).read_bytes()
assert len(request['stdin'].encode())<=131072
diff = ''.join(difflib.unified_diff(original.splitlines(keepends=True),source.splitlines(keepends=True),
    fromfile='ihg/owned_inspect.py',tofile='bestbuy/owned_inspect.py'))
for old_name,new_name,newbody in [('ihg_task_context.py','bestbuy_task_context.py',context),
    ('stage_execute.py','stage_execute.py',stage),('make_request.py','make_request.py',maker)]:
    diff += ''.join(difflib.unified_diff((OLD/old_name).read_text().splitlines(keepends=True),newbody.splitlines(keepends=True),
        fromfile='ihg/'+old_name,tofile='bestbuy/'+new_name))
write('source.diff',diff)
review={'schema':1,'scope':'one fresh native BestBuy launch, no-action state/inspect/state, exact new-task retirement',
    'baseline_source_manifest':sha(old_source_manifest),'actual_install_source_manifest':sha(install_manifest_raw),
    'actual_install_qualified':install_qualification,'actual_resolver_qualified':resolver_qualification,
    'pure_negative_receipt_controls_rejected':negative_controls,
    'all_original_operation_task_Main_source_resource_cleanup_guards_preserved':True,
    'APK_cardinality_changed_from_one_to_exact_three':True,
    'all_three_historical_artifact_records_exactly_bound':True,
    'original_request_resources_and_timeout_unchanged':True,'packet_bytes':len(request['stdin'].encode()),
    'new_flow_nonce':NONCE,'new_inspect_nonces':PLAN['nonces'],
    'remote_calls':0,'request_submitted':False,'whole_app_production_ready':False}
write('local-source-review.json',pretty(review))
write('README.md', '# BestBuy actual-bound launch and inspection\n\nThis frozen request binds the actual helper UID 10198 and all three unchanged commercial APK records. It permits one fresh native launch, one read-only state/inspect/state sequence, and retirement of only that newly acknowledged task. It preserves the original Main identity, pids.max 12288, held source and target identities, and command budgets. No click, text, account, booking, purchase, screenshot, audio, settings, permission, or package operation is included. Historical resolution is not launch authority: current resolution is required immediately before the launch.\n\nThe source is derived from the reviewed IHG flow. All current BestBuy installation and metadata originals are pinned, including exact Python integer nanoseconds. Three-APK before/after and FD cleanup gates are explicit. Pure local receipt controls are not device results; this request is unexecuted and no whole-App production readiness is claimed.\n')
files={name:{k:v for k,v in pin(OUT/name).items() if k!='path'} for name in sorted(p.name for p in OUT.iterdir())}
frozen=write('FROZEN_FILES.json',pretty({'schema':1,'files':files,'device_calls':0,'request_submitted':False}))
print(json.dumps({'directory':str(OUT),'request':pin(OUT/'exact-request.json'),
    'source_manifest':pin(OUT/'SOURCE_PINS.json'),'frozen_manifest':pin(OUT/'FROZEN_FILES.json'),
    'source_diff':pin(OUT/'source.diff'),'local_source_review':pin(OUT/'local-source-review.json'),
    'key':request['idempotency_key'],'runtime_source_bytes':sum(r['bytes'] for r in manifest['files'].values()),
    'packet_bytes':len(request['stdin'].encode()),'device_calls':0},sort_keys=True))
