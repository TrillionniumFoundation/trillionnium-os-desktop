#!/usr/bin/env python3
"""Actual r2 receipt consumer via an explicit local path map; no Android."""
import ast
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
BASE=Path('/workspace/scratch/94990735b266/android-bili-owned-inspect-01')
QA=Path('/workspace/scratch/94990735b266/owned-bili-qa-r2-window-01/source')
INSTALL=Path('/workspace/scratch/94990735b266/android-qa-r2-install-state-01')
ACTUAL=Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/qa-r2-install01')
BUILD=Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/qa-r2-build01')


def load(path):
    raw=path.read_bytes();ast.parse(raw,filename=str(path))
    value=types.ModuleType(path.stem);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    return value


def main():
    entry=load(HERE/'owned_inspect.py');prior=load(INSTALL/'install_state.py')
    adapter,qa,builder=[load(QA/n) for n in ('qa_adapter.py','qa_contract.py','build_candidate.py')]
    entry.require_actual_install_binding();entry.fixed_plan()
    assert entry.SELF==qa.SELF=='org.droidloom.qa.bili.r2' and entry.UID==10165
    manifest=adapter.own_source(prior.QA_MANIFEST)
    proof=adapter.qualified_build(types.SimpleNamespace(build_receipt=BUILD/'result.json',
        build_receipt_sha256=prior.BUILD_SHA,source_manifest_sha256=prior.QA_MANIFEST,
        apk_sha256=prior.APK_SHA,signer_certificate_sha256=prior.SIGNER_SHA),manifest,builder)
    proof['stage_receipt_sha256']=prior.STAGE_SHA
    raw=(ACTUAL/'reader-report.json').read_bytes()
    assert len(raw)==27615 and hashlib.sha256(raw).hexdigest()=='cf146b3ba8083380cfc3250d6ee157e668a25092915bb54c8bc61ce99b3e08b2'
    report=json.loads(raw);mapping={}
    for name,row in report['files'].items():
        b=(ACTUAL/name).read_bytes()
        assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'] and b.decode()==row['text']
        mapping[row['path']]=ACTUAL/name
    original_read=entry.read
    def mapped_read(path,*args,**kwargs):
        assert str(path) in mapping,'unexpected runtime read: '+str(path)
        return original_read(mapping[str(path)],*args,**kwargs)
    entry.read=mapped_read
    installed,admission=entry.actual_install(prior,qa,proof)
    assert installed==entry.EXPECTED_INSTALLED_IDENTITY and installed['uid']==10165
    assert admission['historical_state_reparsed'] is True and admission['historical_state_used_as_current_baseline'] is False
    checks=[{'case':'actual_r2_build_install_state_receipts_complete_consumer','outcome':'PASS',
             'reader_sha256':hashlib.sha256(raw).hexdigest(),'path_mapping_seam':True}]
    saved=entry.UID;entry.UID=None
    try:
        entry.require_actual_install_binding()
    except RuntimeError as error:
        assert str(error)=='ACTUAL_R2_INSTALL_UID_PENDING'
    else:
        raise AssertionError('pending UID admitted')
    finally:
        entry.UID=saved
    checks.append({'case':'pending_actual_UID_refused','outcome':'PASS'})
    saved=entry.UID;entry.UID=10164
    try:
        entry.require_actual_install_binding()
    except RuntimeError as error:
        assert str(error)=='ACTUAL_R2_INSTALL_UID_PENDING'
    else:
        raise AssertionError('r1 UID admitted')
    finally:
        entry.UID=saved
    checks.append({'case':'old_r1_UID_refused','outcome':'PASS'})
    saved=entry.INSTALL_RECORDS['worker'];entry.INSTALL_RECORDS['worker']=(saved[0],saved[1],'0'*64)
    try:
        entry.actual_install(prior,qa,proof)
    except RuntimeError as error:
        assert str(error).startswith('INPUT_SHA_CHANGED:')
    else:
        raise AssertionError('wrong worker pin admitted')
    finally:
        entry.INSTALL_RECORDS['worker']=saved
    checks.append({'case':'wrong_actual_worker_hash_refused','outcome':'PASS'})
    def functions(path):
        return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_bytes()).body
                if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    before,after=functions(BASE/'owned_inspect.py'),functions(HERE/'owned_inspect.py')
    added=sorted(set(after)-set(before));changed=sorted(n for n in before if before[n]!=after[n])
    assert added==['require_actual_install_binding']
    assert changed==['actual_install','assessment_summary','load_prior','worker'],changed
    assert functions(BASE/'stage_execute.py')==functions(HERE/'stage_execute.py')
    checks.append({'case':'original_coordinator_cleanup_scope_and_stage_AST_preserved','outcome':'PASS',
                   'changed_entry_functions':changed,'added_function':added})
    assert set(entry.PLAN['nonces'])=={'before','inspect','after'}
    assert entry.PLAN['operation']=='inspect' and entry.OLD_STATE_NONCE not in entry.PLAN['nonces'].values()
    assert entry.INSTALL_ROOT.name=='pocket4-owned-bili-qa-r2-install-state-01'
    assert entry.ROOT.name=='pocket4-bilibili-owned-r2-inspect-01'
    checks.append({'case':'fresh_exact_inspect_only_plan','outcome':'PASS'})
    print(json.dumps({'schema':1,'all_expected_outcomes':True,'checks':checks,
        'scope':'actual Python consumer and original actual receipts, explicit local path map',
        'Android_or_Hepta_calls':0,'new_launch_or_inspection_performed':False,
        'whole_app_ready':False},indent=2,sort_keys=True))


if __name__=='__main__':
    main()
