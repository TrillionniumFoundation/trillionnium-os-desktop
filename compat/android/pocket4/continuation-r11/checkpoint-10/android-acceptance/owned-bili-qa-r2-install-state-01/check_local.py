#!/usr/bin/env python3
"""Narrow offline checks of actual source/receipt consumers; no Android calls."""
import ast
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
BASE = Path('/workspace/scratch/94990735b266/android-qa-install-state-02')
QA = Path('/workspace/scratch/94990735b266/owned-bili-qa-r2-window-01/source')
ACTUAL = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/qa-r2-build01')


def load(path):
    raw = path.read_bytes(); ast.parse(raw, filename=str(path))
    value = types.ModuleType(path.stem); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def main():
    entry = load(HERE/'install_state.py')
    adapter, contract, builder = [load(QA/name) for name in ('qa_adapter.py','qa_contract.py','build_candidate.py')]
    manifest = adapter.own_source(entry.QA_MANIFEST)
    build_raw = (ACTUAL/'result.json').read_bytes()
    stage_raw = (ACTUAL/'stage_result.json').read_bytes()
    assert len(build_raw) == entry.BUILD_BYTES and hashlib.sha256(build_raw).hexdigest() == entry.BUILD_SHA
    assert len(stage_raw) == entry.STAGE_BYTES and hashlib.sha256(stage_raw).hexdigest() == entry.STAGE_SHA
    proof = adapter.qualified_build(types.SimpleNamespace(build_receipt=ACTUAL/'result.json',
        build_receipt_sha256=entry.BUILD_SHA, source_manifest_sha256=entry.QA_MANIFEST,
        apk_sha256=entry.APK_SHA, signer_certificate_sha256=entry.SIGNER_SHA),manifest,builder)
    assert proof['APK'] == {'path':str(entry.APK),'bytes':entry.APK_BYTES,'sha256':entry.APK_SHA}
    stage = json.loads(stage_raw)
    assert stage['source_manifest_sha256'] == entry.QA_MANIFEST and stage['build_result'] == {
        'path':str(entry.BUILD),'bytes':entry.BUILD_BYTES,'sha256':entry.BUILD_SHA}
    assert stage['error'] is None and stage['secondary_errors'] == [] and stage['build_returncode'] == 0
    checks = [{'case':'actual_complete_r2_build_receipt_consumer','outcome':'PASS',
               'build_sha256':entry.BUILD_SHA,'stage_sha256':entry.STAGE_SHA}]
    old, new = load(BASE/'session_binding.py'),load(HERE/'session_binding.py')
    flow = types.SimpleNamespace(contract=types.SimpleNamespace(sha256=entry.RECORDER_MANIFEST),
                                 _private_backend_transport=False)
    try:
        old.new_session(adapter,flow,None,contract,proof,10165)
    except RuntimeError as error:
        assert str(error) == 'ACTUAL_BUILT_QA_BASE_ADAPTER_REQUIRED'
    else:
        raise AssertionError('old R3 constructor incorrectly accepted r2')
    checks.append({'case':'old_shim_rejects_actual_r2_dependency','outcome':'EXPECTED_RED_REPRODUCED'})
    session = new.new_session(adapter,flow,None,contract,proof,10165)
    assert type(session) is adapter.Session and session.nonces == set()
    checks.append({'case':'new_binding_uses_unmodified_actual_Session','outcome':'PASS',
                   'UID_10165_is_synthetic_not_an_actual_install_claim':True})
    for uid in (10117,10125,10164):
        try:
            new.new_session(adapter,flow,None,contract,proof,uid)
        except RuntimeError as error:
            assert str(error) == 'EXACT_NEW_OWNED_HELPER_UID_REQUIRED'
        else:
            raise AssertionError('forbidden UID accepted')
    checks.append({'case':'commercial_legacy_and_r1_UIDs_rejected','outcome':'PASS'})
    try:
        new.new_session(adapter,flow,None,contract,{**proof,'source_manifest_sha256':'0'*64},10165)
    except RuntimeError as error:
        assert str(error) == 'ACTUAL_BUILT_R2_R4_ADAPTER_REQUIRED'
    else:
        raise AssertionError('wrong source accepted')
    checks.append({'case':'wrong_source_proof_rejected','outcome':'PASS'})
    assert entry.uid_from(b'package:org.droidloom.qa.bili.r2 uid:10165\n') == 10165
    try:
        entry.uid_from(b'package:org.droidloom.qa.bili.r2 uid:10164\n')
    except RuntimeError as error:
        assert str(error) == 'NEW_APP_UID_REQUIRED'
    else:
        raise AssertionError('r1 UID accepted by actual package parser')
    assert entry.INSTALL == ['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',entry.SELF,entry.GUEST_APK]
    assert entry.PACKAGE_LIST == ['/system/bin/cmd','package','list','packages','-u','-U','--user','all',entry.SELF]
    checks.append({'case':'actual_UID_parser_and_nonreplacement_install_contract','outcome':'PASS'})
    def functions(path):
        return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_bytes()).body
                if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    before,after=functions(BASE/'install_state.py'),functions(HERE/'install_state.py')
    assert set(before)==set(after)
    assert [name for name in before if before[name]!=after[name]] == ['uid_from']
    assert functions(BASE/'stage_execute.py') == functions(HERE/'stage_execute.py')
    assert functions(BASE/'make_request.py') == functions(HERE/'make_request.py')
    checks.append({'case':'inherited_actions_guards_lifecycle_cleanup_AST_unchanged_except_UID_rejection','outcome':'PASS'})
    print(json.dumps({'schema':1,'checks':checks,'all_expected_outcomes':True,
        'scope':'actual source and actual build receipts; synthetic constructor arguments only',
        'Android_or_Hepta_calls':0,'actual_APK_bytes_read_locally':False,
        'actual_install_UID':None,'install_or_UI_qualified':False},indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
