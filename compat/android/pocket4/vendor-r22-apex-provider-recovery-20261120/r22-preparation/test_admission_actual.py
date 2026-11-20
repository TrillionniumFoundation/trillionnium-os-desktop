from pathlib import Path
import copy, hashlib, json, os, stat, sys, types, time

ROOT=Path(__file__).resolve().parent
R21=Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r21')
def f9(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def read(path):
    path=Path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=f9(os.fstat(fd));assert stat.S_ISREG(before[2]) and before[5]==1
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read()
        assert before==f9(os.fstat(fd))==f9(path.lstat())
        return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'identity':before},raw
    finally:os.close(fd)

module_pin,body=read(ROOT/'admission_r22.py')
assert module_pin['bytes']==20971 and module_pin['sha256']=='e8f407bae7c56f9f0b0c6147bc0150f5dd6dfdf7f3894554a1cf8c57d17f7097'
module=types.ModuleType('exact_r22_admission');exec(compile(body,str(ROOT/'admission_r22.py'),'exec'),module.__dict__)
names={'worker':'source.py','contract':'inputs/CONTRACT.json','bundle':'inputs/BUNDLE.json',
       'outer':'outer.py','terminal':'actual/outer-terminal.json','build':'actual/build-observation.json',
       'recovery':'actual/recovery-observation.json'}
refs={};values={}
for key,name in names.items():
    refs[key],raw=read(R21/name)
    assert (refs[key]['bytes'],refs[key]['sha256'])==module.HISTORY[key]
    if key not in ('worker','outer'):values[key]=json.loads(raw)
baseline={'manifest':module.MANIFEST,'locks':module.LOCKS}
assert read(module.MANIFEST['path'])[0]==module.MANIFEST
for lock in module.LOCKS:assert read(lock['path'])[0]==module.reference(lock)
actual=module.validate_r21_predecessor(values,refs,baseline)
fixture_pin,raw=read('/home/qq/work/p4-r22-apex-provider-fixture-20261120-3b9d-r2/RESULT.json')
assert (fixture_pin['bytes'],fixture_pin['sha256'])==(32156,'9ebec2991ebc71d055933f68250652f11eb708a55347f9e4ad3acc85074d7387')
fixture=json.loads(raw);actual_fixture=module.validate_original_git_fixture(fixture)
cases=[]
def reject(name,mutator):
    candidate=copy.deepcopy(values);pins=copy.deepcopy(refs);base=copy.deepcopy(baseline)
    mutator(candidate,pins,base)
    try:module.validate_r21_predecessor(candidate,pins,base)
    except (RuntimeError,KeyError,TypeError,ValueError):cases.append(name)
    else:raise AssertionError('negative admitted: '+name)
reject('failed build cannot become success',lambda v,p,b:v['terminal'].__setitem__('passed',True))
reject('missing original phase',lambda v,p,b:v['terminal']['phases'].pop())
reject('unreaped original outer child',lambda v,p,b:v['terminal']['children'][0].__setitem__('actual_reaped',False))
reject('missing original PIDFD',lambda v,p,b:v['terminal']['phases'][0]['client'].__setitem__('original_pidfd_held_until_reaped',False))
reject('false is not integer exit zero',lambda v,p,b:v['recovery']['commands'][0].__setitem__('exit_code',False))
reject('wrong original native source scope',lambda v,p,b:v['recovery'].__setitem__('native_source_926_members_and_git_provenance_unchanged',False))
reject('rounded nanosecond pin',lambda v,p,b:b['manifest']['identity'].__setitem__(7,b['manifest']['identity'][7]+1))
reject('different original source lock writer',lambda v,p,b:v['recovery']['commands'][0].__setitem__('pid',3972148))
reject('changed actual historical source hash',lambda v,p,b:p['worker'].__setitem__('sha256','0'*64))
for key,ref in refs.items():assert read(ref['path'])[0]==ref
assert read(module_pin['path'])[0]==module_pin and read(fixture_pin['path'])[0]==fixture_pin
assert read(module.MANIFEST['path'])[0]==module.MANIFEST
for lock in module.LOCKS:assert read(lock['path'])[0]==module.reference(lock)
result={'schema':'p4-r22-actual-predecessor-admission-controls-v1','passed':True,
        'module':module_pin,'predecessor_refs':refs,'actual_predecessor':actual,
        'actual_isolated_fixture':actual_fixture,'negative_cases':cases,
        'complete_original_inputs_bookended':True,'actual_new_ci_consumed':False,
        'children_started':0,'source_mutations':0,'Android_builds':0,'Android_starts':0,
        'runtime_qualified':False,'production_ready':False}
with (ROOT/'RESULT.json').open('x') as output:json.dump(result,output,indent=2);output.write('\n')
print(json.dumps({'passed':True,'negative_cases':len(cases),'source_mutations':0,'actual_new_ci_consumed':False}),flush=True)
