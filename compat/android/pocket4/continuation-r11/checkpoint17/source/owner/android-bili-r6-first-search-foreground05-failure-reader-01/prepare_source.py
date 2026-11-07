#!/usr/bin/env python3
"""Create a fixed Bili05 historical safe reader; local preparation only."""
import ast
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'android-bili-r6-content-ready04-failure-reader-01'
COORD_SHA='9b1246c7bd0e7c27baab6f489d644597e5a5d0dbe69d42fefee37e1330efb3de'
STAGE_SHA='6d656e3abdf5294cd01f25fb9c09c34df1d60c05650ea05f762745b17daee705'
KEY='pocket4-bilibili-r6-first-search-foreground05-five-safe-readonly-01-20261106'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw_json(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def put(name,raw):
    if isinstance(raw,str):raw=raw.encode()
    with (HERE/name).open('xb') as f:f.write(raw)
    return {'bytes':len(raw),'sha256':sha(raw)}
def exact(name,size,digest):
    raw=(BASE/name).read_bytes();assert len(raw)==size and sha(raw)==digest
    return raw.decode()

original=exact('read_summary.py',10442,'b7505a81e632f74cf66ca2ae607196ce3dad266a96eb7fc880d6bb0501122312')
maker_old=exact('make_summary_request.py',2547,'e4d77af60da2a1ee01e89a88f5cd499bf8b144ce7e68a4aa46712d8786a0258f')
mapping=[
    ('pocket4-bilibili-r6-pause-resume-04','pocket4-bilibili-r6-pause-resume-05'),
    ('a14743fa3566f851b6724a54b0509744','c54a6b039b42371f84903662e8e3762f'),
    ('a49770d55b487e4e172aa38ebc1a454220ec7e668c499f8c8d5b838962e9da42','1219f775585458f7905b7fcf544c0f5c5d2ae15bdb5c30fc09e65daf23362b67'),
    ('360fa744c2162c73c03fe0dd76e9b818544558b4ce732047cf84f208458a6ead',COORD_SHA),
    ('b0a199faa698e507c6a271968b5101663161276c1159e96f2f0f1d1d1e98f5ad',STAGE_SHA),
    ('7418','7407'),
]
normalized=original
for a,b in mapping:
    assert a in normalized
    normalized=normalized.replace(a,b)
reader=normalized
start=reader.index('    need(coordinator.get(\'cleanup_result\')==')
end=reader.index("    need(coordinator['Main_before']",start)
reader=reader[:start]+'''    need(coordinator.get('owned_task_absent_after_cleanup') is True,
         'ACTUAL_PARENT_CLEANUP_CLAIM_RETAINED_NOT_YET_INDEPENDENTLY_VERIFIED')
'''+reader[end:]
needle="         'ACTUAL_PARENT_MAIN_CHAIN')\n"
assert reader.count(needle)==1
reader=reader.replace(needle,needle+'''    return parent_phase_pins(coordinator)


def parent_phase_pins(coordinator):
    retained=coordinator.get('retained_phase_results')
    need(type(retained) is dict and set(retained)=={'launch','navigate'},
         'EXACT_TWO_RETAINED_WORKER_PINS_REQUIRED')
    pins={'launch.json':retained['launch'],'navigation.json':retained['navigate'],
          'cleanup.json':coordinator.get('cleanup_result')}
    for name,pin in pins.items():
        maximum=32768 if name=='launch.json' else 262144
        need(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and
             pin.get('path')==str(FILES[name]) and type(pin.get('bytes')) is int and
             0<pin['bytes']<=maximum and type(pin.get('sha256')) is str and
             re.fullmatch('[0-9a-f]{64}',pin['sha256']),
             'EXACT_PARENT_BOUND_PATH_BOUNDED_BYTES_AND_SHA_REQUIRED:'+name)
    need(coordinator.get('launch_result')==pins['launch.json'],
         'DUPLICATE_PARENT_LAUNCH_PIN_DIFFERS')
    if 'navigation_result' in coordinator:
        need(coordinator['navigation_result']==pins['navigation.json'],
             'DUPLICATE_PARENT_NAVIGATION_PIN_DIFFERS')
    return pins
''')
start=reader.index('        fixed_parent_binding(c,s);')
end=reader.index('    except Exception as failure:',start)
reader=reader[:start]+'''        pins=fixed_parent_binding(c,s);bindings['parent_chain']=True
        # Hashes come only from the already externally pinned parent bytes.
        # Preserve retirement first even if a later worker scope/export guard fails.
        pin=pins['cleanup.json']
        add('cleanup.json',pin['sha256'],pin['bytes']);bindings['cleanup_parent_pin']=True
        pin=pins['launch.json']
        launched=add('launch.json',pin['sha256'],pin['bytes']);bindings['launch_parent_pin']=True
        launch_binding(launched);bindings['launch_scope']=True
        pin=pins['navigation.json']
        worker=add('navigation.json',pin['sha256'],pin['bytes']);bindings['navigation_parent_pin']=True
        navigation_binding(worker);bindings['navigation_scope']=True
'''+reader[end:]
reader=reader.replace("'cleanup_external_pin':False,'launch_external_pin':False", "'cleanup_parent_pin':False,'launch_parent_pin':False")
reader=reader.replace("'navigation_external_pin':False", "'navigation_parent_pin':False")
reader=reader.replace("'fixed-r6-pause-resume-failure-and-retirement-only'", "'fixed-r6-first-search-foreground05-failure-and-retirement-only'")
reader=reader.replace("'independent_external_failed_navigation_hash_available':True", "'independent_external_failed_navigation_hash_available':False,\n        'child_hashes_derived_only_from_exact_external_parent_bytes':True")
assert len(reader.encode())<=16384
reader_pin=put('read_summary.py',reader)
maker=maker_old.replace('b7505a81e632f74cf66ca2ae607196ce3dad266a96eb7fc880d6bb0501122312',reader_pin['sha256'])
maker=maker.replace('pocket4-bilibili-r6-content-ready04-three-phase-failure-readonly-01-20261105',KEY)
maker=maker.replace('len(raw)==10442','len(raw)=='+str(reader_pin['bytes']))
put('make_summary_request.py',maker)
put('literal-rebindings.json',raw_json(mapping))
put('source.diff',''.join(difflib.unified_diff(original.splitlines(True),reader.splitlines(True),fromfile='Bili04/read_summary.py',tofile='Bili05/read_summary.py')))
put('normalized-semantic-residual.patch',''.join(difflib.unified_diff(normalized.splitlines(True),reader.splitlines(True),fromfile='Bili04-after-literal-bindings/read_summary.py',tofile='Bili05/read_summary.py')))

# No Reader.read, collect, Android, or remote calls: functions operate on a copied
# prior actual parent fixture. These cases do not claim any Bili05 child contents.
scope={'__name__':'local_bili05_pure_controls','__file__':str(HERE/'read_summary.py')}
exec(compile(reader,'read_summary.py','exec'),scope)
evidence=HERE.parent/'root-recovery-20261104-02/evidence/bili-r6-content-ready04-failure-read01'
c=(evidence/'coordinator.json').read_text();s=(evidence/'stage.json').read_text()
assert sha(c.encode())=='360fa744c2162c73c03fe0dd76e9b818544558b4ce732047cf84f208458a6ead'
assert sha(s.encode())=='b0a199faa698e507c6a271968b5101663161276c1159e96f2f0f1d1d1e98f5ad'
for a,b in mapping:c=c.replace(a,b);s=s.replace(a,b)
c=json.loads(c);s=json.loads(s);cases=[]
def case(name,mutate,expected):
    cc,ss=copy.deepcopy(c),copy.deepcopy(s);mutate(cc,ss)
    error=None
    try:scope['fixed_parent_binding'](cc,ss)
    except RuntimeError as failure:error=str(failure)
    assert (error is None if expected is None else error==expected),(name,error,expected)
    cases.append({'case':name,'passed':True,'error':error})
case('prior_actual_parent_shape_rebound_synthetic_not_Bili05_observation',lambda c,s:None,None)
case('reject_extra_retained_phase',lambda c,s:c['retained_phase_results'].update({'extra':{}}),'EXACT_TWO_RETAINED_WORKER_PINS_REQUIRED')
case('reject_child_path_escape',lambda c,s:c['retained_phase_results']['navigate'].update({'path':str(scope['FLOW']/'../other/result.json')}),'EXACT_PARENT_BOUND_PATH_BOUNDED_BYTES_AND_SHA_REQUIRED:navigation.json')
case('reject_boolean_size',lambda c,s:c['retained_phase_results']['navigate'].update({'bytes':True}),'EXACT_PARENT_BOUND_PATH_BOUNDED_BYTES_AND_SHA_REQUIRED:navigation.json')
case('reject_oversized_child',lambda c,s:c['retained_phase_results']['navigate'].update({'bytes':262145}),'EXACT_PARENT_BOUND_PATH_BOUNDED_BYTES_AND_SHA_REQUIRED:navigation.json')
case('reject_launch_over_original_small_cap',lambda c,s:c['retained_phase_results']['launch'].update({'bytes':32769}),'EXACT_PARENT_BOUND_PATH_BOUNDED_BYTES_AND_SHA_REQUIRED:launch.json')
case('reject_invalid_child_sha',lambda c,s:c['retained_phase_results']['navigate'].update({'sha256':'g'*64}),'EXACT_PARENT_BOUND_PATH_BOUNDED_BYTES_AND_SHA_REQUIRED:navigation.json')
case('reject_duplicate_launch_mismatch',lambda c,s:c['launch_result'].update({'sha256':'0'*64}),'DUPLICATE_PARENT_LAUNCH_PIN_DIFFERS')
case('reject_optional_duplicate_navigation_mismatch',lambda c,s:c.update({'navigation_result':{}}),'DUPLICATE_PARENT_NAVIGATION_PIN_DIFFERS')
case('reject_missing_cleanup_pin',lambda c,s:c.pop('cleanup_result'),'EXACT_PARENT_BOUND_PATH_BOUNDED_BYTES_AND_SHA_REQUIRED:cleanup.json')
case('reject_changed_stage_parent_pin',lambda c,s:s['coordinator_result'].update({'sha256':'0'*64}),'ACTUAL_PARENT_COORDINATOR_CHAIN')
case('reject_changed_Main_chain',lambda c,s:s['Main_after'].update({'three_host_processes_match':False}),'ACTUAL_PARENT_MAIN_CHAIN')
try:scope['no_raw_ui']({'nested':{'nodes':[]}})
except RuntimeError as failure:
    assert str(failure)=='RAW_UI_FIELD_FORBIDDEN_IN_SUMMARY_EXPORT'
    cases.append({'case':'reject_raw_UI_export','passed':True,'error':str(failure)})
else:raise AssertionError('raw_UI guard did not fail')
controls=put('binding-checks.json',raw_json({'schema':1,'passed':len(cases),'cases':cases,
    'fixture':'prior actual Bili04 parents with explicit synthetic literal rebindings only',
    'Bili05_child_hashes_sizes_contents_not_observed_or_guessed':True,
    'Reader_read_collect_Hepta_or_UI_calls':0}))

def functions(text):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a,b=functions(normalized),functions(reader)
unchanged=['need','sha','no_raw_ui','Reader','launch_binding','navigation_binding','main']
assert all(a[n]==b[n] for n in unchanged)
put('guard-correspondence.json',raw_json({'schema':1,'unchanged_AST_after_explicit_literal_rebinding':unchanged,
    'original_reader_pin':{'bytes':10442,'sha256':'b7505a81e632f74cf66ca2ae607196ce3dad266a96eb7fc880d6bb0501122312'},
    'reader_no_raw_export_and_FD_bounds_unchanged':True,'read_is_sequential_not_atomic':True,
    'new_child_pin_validation':'exact parent retained launch/navigate plus parent cleanup_result; duplicate pins agree; no externally guessed child values'}))
for name in ('read_summary.py','make_summary_request.py'):compile((HERE/name).read_text(),name,'exec')
plan=subprocess.run([sys.executable,'-I','-B',str(HERE/'read_summary.py')],check=True,capture_output=True)
assert not plan.stderr
put('default-plan.json',plan.stdout)
result=subprocess.run([sys.executable,'-I','-B',str(HERE/'make_summary_request.py'),'--write-once',
    '--coordinator-sha256',COORD_SHA,'--stage-sha256',STAGE_SHA,'--output',str(HERE/'exact-request.json')],check=True,capture_output=True)
assert not result.stderr
put('request-pins.json',result.stdout)
request=json.loads((HERE/'exact-request.json').read_bytes())
assert request['stdin'].encode()==reader.encode() and request['timeout_seconds']==30 and request['memory_max_bytes']==134217728
assert request['args'][:4]==['-n','/usr/bin/python3','-I','-c']
compile(request['args'][4],'<verified-wrapper>','exec')
put('README.md','Reads two exact Bili05 terminal parents, then only their bounded fixed owned launch/navigation/cleanup result pins. No child hash or size is guessed. Launch and optional navigation duplicate parent pins must agree. Original file/no-follow/FD/deadline/privacy gates are unchanged. Cleanup is collected first and retained if later worker validation fails. No private tree/assessment, Android, process, UI, input, replay, release, or qualification action.\n')
put('source-review.json',raw_json({'schema':1,'state':'FIVE_SAFE_READER_FROZEN_NOT_SUBMITTED',
    'terminal_job':'1a1ae3dae7f-fc05-5e65','actual_parent_pins':{
      'coordinator':{'bytes':7407,'sha256':COORD_SHA},'stage':{'bytes':1773,'sha256':STAGE_SHA}},
    'baseline_reader':{'path':str(BASE/'read_summary.py'),'bytes':10442,'sha256':'b7505a81e632f74cf66ca2ae607196ce3dad266a96eb7fc880d6bb0501122312'},
    'reader':reader_pin,'pure_controls':controls,'unchanged_AST_after_literal_normalization':unchanged,
    'runtime_changes':[
      'Replace external child literal hashes and sizes with same-script pins derived only from fixed external parent bytes.',
      'Require exactly two retained worker pins and parent cleanup pin at the three original fixed owned paths.',
      'Check duplicate launch and optional completed navigation pins before reads.',
      'Report child hashes as parent-derived, not independent external hashes.'],
    'original_bounds':{'seconds':8,'small_launch_file':32768,'other_single_file':262144,'total':2097152,'bundle':3145728,
      'stdin':16384,'request_seconds':30,'CPU_percent':100,'memory_bytes':134217728},
    'all_bound_files_mandatory':True,'no_actual_child_outcome_or_cleanup_qualification_assumed':True,
    'no_private_assessment_or_tree_reads':True,'Hepta_or_UI_calls':0}))
files={p.name:{'bytes':len(p.read_bytes()),'sha256':sha(p.read_bytes())} for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='FROZEN_FILES.json'}
put('FROZEN_FILES.json',raw_json({'schema':1,'payload_count':len(files),'files':files,'remote_actions':0}))
print(json.dumps({'state':'FROZEN_NOT_SUBMITTED','reader':reader_pin,'request':files['exact-request.json'],
    'source_review':files['source-review.json'],'frozen':{'bytes':(HERE/'FROZEN_FILES.json').stat().st_size,'sha256':sha((HERE/'FROZEN_FILES.json').read_bytes())},
    'payload_count':len(files),'pure_controls_passed':len(cases)},sort_keys=True))
