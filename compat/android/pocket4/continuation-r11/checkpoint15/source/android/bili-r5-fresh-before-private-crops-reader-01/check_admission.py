#!/usr/bin/env python3
"""Actual retained safe JSON predicates; never read pixels or perform copies."""
import ast,copy,hashlib,json,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=Path('/workspace/scratch/94990735b266')
OLD=ROOT/'android-bili-r5-geometry-private-crops-reader-01/read_private_crops.py'
RETAINED=ROOT/'root-recovery-20261104-02/evidence/bili-r5-player-fresh-before01-read01/originals'
def main():
    path=HERE/'read_private_crops.py';m=types.ModuleType('crop_control');m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
    values=[]
    for key,name in (('coordinator','coordinator.json'),('stage','stage.json'),('navigation','navigation.json'),('cleanup','cleanup.json')):
        raw=(RETAINED/name).read_bytes();assert (len(raw),hashlib.sha256(raw).hexdigest())==m.FILES[key][1:];values.append(json.loads(raw))
    rows=[]
    def run(name,change,accepted):
        v=copy.deepcopy(values);change(v);error=None
        try:m.validate_observations(*v)
        except RuntimeError as e:error=str(e)
        assert (error is None)==accepted,(name,error)
        rows.append({'case':name,'accepted':error is None,'expected_met':True,'error':error})
    samples=lambda v:v[2]['buffer_viewport_observation']['viewport_samples']
    run('retained_three_scoped_capture_successes_only',lambda v:None,True)
    run('reject_business_unknown_cleared',lambda v:v[2].update(outcome_unknown=False),False)
    run('reject_Main_change',lambda v:v[0]['Main_after'].update(Main_epoch_sha256='0'*64),False)
    run('reject_first_crop_unqualified',lambda v:samples(v)[0].update(scope_checked_before_and_after=False),False)
    run('reject_path_substitution',lambda v:samples(v)[0]['private_crop'].update(path='/other.png'),False)
    run('reject_within_capture_absolute_move',lambda v:samples(v)[1]['after_observation']['proof'].update(crop=[0,45,1200,720]),False)
    run('reject_previous_after_used_as_next_before',lambda v:samples(v)[1].update(before_observation=copy.deepcopy(samples(v)[0]['after_observation'])),False)
    run('reject_bad_finish',lambda v:samples(v)[2]['before_observation']['assessments']['inspect'].update(actual_instrumentation_finish_code=0),False)
    run('reject_missing_third_transaction',lambda v:samples(v).pop(),False)
    def defs(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    a,b=defs(OLD),defs(path);unchanged=['need','sha','open_directory','write_new','main']
    assert all(a[k]==b[k] for k in unchanged)
    # Reader only changed an error label naming the exact seven fixed paths.
    assert a['Reader'].replace('FIXED_SIX_INPUTS_ONLY','FIXED_SEVEN_INPUTS_ONLY')==b['Reader']
    assert sum(v[1] for v in m.FILES.values())==2004542<2097152
    print(json.dumps({'schema':1,'state':'PASS','controls':rows,'unchanged_source_definitions':unchanged,'Reader_changed_only_fixed_input_count_label':True,'exact_total_input_bytes':2004542,'total_bound':2097152,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'scope':'actual admission predicate on exact safe retained JSON plus explicit negative mutations; no filesystem reader or copy execution','PNG_or_commercial_tree_read':False,'private_copy_or_chown_or_namespace_or_Android_operations':0},sort_keys=True,indent=2))
if __name__=='__main__':main()
