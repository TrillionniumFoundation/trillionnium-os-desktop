#!/usr/bin/env python3
"""Local synthetic collector controls; never opens remote or device paths."""
import ast,base64,contextlib,copy,gzip,hashlib,io,json,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'android-ticket-launch-inspect02-launch-reader-01/read_summary.py'

def pin(path,raw):
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def encoded(value,size=None):
    raw=json.dumps(value,sort_keys=True).encode()
    assert size is None or len(raw)<=size
    return raw if size is None else raw+b' '*(size-len(raw))

def execute(mutate=None):
    m=types.ModuleType('synthetic_reader');m.__file__=str(HERE/'read_summary.py')
    exec(compile((HERE/'read_summary.py').read_bytes(),m.__file__,'exec'),m.__dict__)
    identity={'source_manifest_sha256':m.SOURCE_SHA,'nonce':m.NONCE,'package':'com.ihg.apps.android',
              'helper_package':'org.droidloom.qa.ihg.r1','helper_uid':10196,'uid':10137}
    values={name:dict(identity,phase=name[:-5]) for name in ('launch.json','inspect.json','cleanup.json')}
    values['cleanup.json']['ok']=False
    data={m.FILES[name]:encoded(v) for name,v in values.items()}
    c=dict(identity,flow=str(m.FLOW),retained_phase_results={})
    for phase,field in (('launch','launch_result'),('inspect','inspection_result'),('cleanup','cleanup_result')):
        p=pin(m.FILES[phase+'.json'],data[m.FILES[phase+'.json']]);c['retained_phase_results'][phase]=p;c[field]=p
    if mutate:mutate(m,c,data)
    raw=encoded(c,13631);data[m.FILES['coordinator.json']]=raw;csha=hashlib.sha256(raw).hexdigest()
    stage=dict(identity,coordinator_result=pin(m.FILES['coordinator.json'],raw))
    raw=encoded(stage,1710);data[m.FILES['stage.json']]=raw;ssha=hashlib.sha256(raw).hexdigest()
    reads=[]
    class FixedMemoryReader:
        def __init__(self):self.bytes=0
        def read(self,path,optional=False):
            reads.append(path);raw=data[path];self.bytes+=len(raw);return raw
    m.Reader=FixedMemoryReader;m.os=types.SimpleNamespace(getuid=lambda:0,geteuid=lambda:0)
    out=io.StringIO()
    with contextlib.redirect_stdout(out):m.collect(csha,ssha)
    envelope=json.loads(out.getvalue());bundle=json.loads(gzip.decompress(base64.b64decode(envelope['data'])))
    return m,reads,bundle

def reject(mutation,expected):
    try:execute(mutation)
    except RuntimeError as e:assert str(e)==expected;return
    raise AssertionError('expected denial')

def main():
    source=(HERE/'read_summary.py').read_text();base=BASE.read_text()
    assert hashlib.sha256(base.encode()).hexdigest()=='8e46dd685a65098783dd6e8bb1db242f6e26a519fd6917c3488f5cfd640a1e95'
    def nodes(s):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    a,z=nodes(base),nodes(source)
    for key in ('Reader','no_raw_ui','need','sha','main'):assert a[key]==z[key],key
    results=['original_reader_and_no_raw_ui_AST_unchanged']
    m,reads,bundle=execute()
    assert reads==[m.FILES[n] for n in ('coordinator.json','stage.json','launch.json','inspect.json','cleanup.json')]
    assert set(bundle['files'])==set(m.FILES) and json.loads(bundle['files']['cleanup.json']['text'])['ok'] is False
    results.append('five_fixed_paths_and_failed_child_original_preserved')
    def foreign(m,c,d):c['retained_phase_results']['launch']['path']=str(m.FLOW/'steps/foreign/result.json')
    reject(foreign,'ONLY_EXACT_PARENT_BOUND_PHASE_PATH_AND_BOUNDED_PIN:launch');results.append('foreign_child_path_rejected')
    def mismatch(m,c,d):c['inspection_result']=dict(c['inspection_result'],sha256='0'*64)
    reject(mismatch,'TWO_PARENT_PHASE_PINS_DIFFER:inspect');results.append('disagreeing_child_pins_rejected')
    def wire(m,c,d):d[m.FILES['cleanup.json']]+=b' '
    reject(wire,'PARENT_BOUND_PHASE_BYTES_CHANGED:cleanup');results.append('changed_child_bytes_rejected')
    def private(m,c,d):
        p=m.FILES['inspect.json'];v=json.loads(d[p]);v['nested']={'nodes':[]};d[p]=encoded(v)
        c['inspection_result']=c['retained_phase_results']['inspect']=pin(p,d[p])
    reject(private,'RAW_UI_FIELD_FORBIDDEN_IN_SUMMARY_EXPORT');results.append('nested_private_UI_rejected')
    report={'schema':1,'ok':True,'controls':results,'count':len(results),'remote_actions':0,'synthetic_only':True}
    print(json.dumps(report,sort_keys=True,indent=2))
if __name__=='__main__':main()
