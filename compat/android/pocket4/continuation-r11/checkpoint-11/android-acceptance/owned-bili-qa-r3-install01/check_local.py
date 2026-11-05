#!/usr/bin/env python3
"""Narrow actual receipt/consumer checks; no Android command or installation."""
import ast
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
BASE = Path('/workspace/scratch/94990735b266/android-qa-r2-install-state-01')
QA = Path('/workspace/scratch/94990735b266/owned-bili-qa-r3-search-01/source')
ACTUAL = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/qa-r3-build01')
SOURCE_SHA = '4302cc8d64d8d1ba77f2dad0043c4ff04d3d88a431632b49a0ade917d296dfed'


def load(path):
    raw = path.read_bytes()
    ast.parse(raw, filename=str(path))
    value = types.ModuleType(path.stem)
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def main():
    entry = load(HERE/'install_state.py')
    entry.verify_source(SOURCE_SHA)
    adapter, contract, builder = [load(QA/name) for name in
                                ('qa_adapter.py','qa_contract.py','build_candidate.py')]
    manifest = adapter.own_source(entry.QA_MANIFEST)
    build_raw = (ACTUAL/'build-result.json').read_bytes()
    stage_raw = (ACTUAL/'stage-result.json').read_bytes()
    assert len(build_raw) == entry.BUILD_BYTES and hashlib.sha256(build_raw).hexdigest() == entry.BUILD_SHA
    assert len(stage_raw) == entry.STAGE_BYTES and hashlib.sha256(stage_raw).hexdigest() == entry.STAGE_SHA
    proof = adapter.qualified_build(types.SimpleNamespace(build_receipt=ACTUAL/'build-result.json',
        build_receipt_sha256=entry.BUILD_SHA, source_manifest_sha256=entry.QA_MANIFEST,
        apk_sha256=entry.APK_SHA, signer_certificate_sha256=entry.SIGNER_SHA),manifest,builder)
    assert proof['APK'] == {'path':str(entry.APK),'bytes':entry.APK_BYTES,'sha256':entry.APK_SHA}
    stage = json.loads(stage_raw)
    assert stage['source_manifest_sha256'] == entry.QA_MANIFEST and stage['build_result'] == {
        'path':str(entry.BUILD),'bytes':entry.BUILD_BYTES,'sha256':entry.BUILD_SHA}
    assert stage['error'] is None and stage['secondary_errors'] == [] and stage['build_returncode'] == 0
    checks = [{'case':'actual_complete_r3_build_receipt_consumer','outcome':'PASS',
               'build_sha256':entry.BUILD_SHA,'stage_sha256':entry.STAGE_SHA}]
    old, new = load(BASE/'session_binding.py'), load(HERE/'session_binding.py')
    flow = types.SimpleNamespace(contract=types.SimpleNamespace(sha256=entry.RECORDER_MANIFEST),
                                 _private_backend_transport=False)
    synthetic_uid = 19999
    try:
        old.new_session(adapter,flow,None,contract,proof,synthetic_uid)
    except RuntimeError as error:
        assert str(error) == 'ACTUAL_BUILT_R2_R4_ADAPTER_REQUIRED'
    else:
        raise AssertionError('old r2 shim accepted r3 dependency')
    checks.append({'case':'old_r2_shim_rejects_actual_r3_dependency','outcome':'EXPECTED_REJECTION'})
    session = new.new_session(adapter,flow,None,contract,proof,synthetic_uid)
    assert type(session) is adapter.Session and session.nonces == set()
    checks.append({'case':'new_binding_uses_actual_unmodified_R3_Session','outcome':'PASS',
                   'synthetic_UID_not_an_actual_install_claim':synthetic_uid})
    for uid in (10117,10125,10164,10165):
        try:
            new.new_session(adapter,flow,None,contract,proof,uid)
        except RuntimeError as error:
            assert str(error) == 'EXACT_NEW_OWNED_HELPER_UID_REQUIRED'
        else:
            raise AssertionError('old/commercial UID accepted')
    checks.append({'case':'commercial_legacy_R1_R2_UIDs_rejected','outcome':'PASS'})
    try:
        new.new_session(adapter,flow,None,contract,{**proof,'source_manifest_sha256':'0'*64},synthetic_uid)
    except RuntimeError as error:
        assert str(error) == 'ACTUAL_BUILT_R3_R4_ADAPTER_REQUIRED'
    else:
        raise AssertionError('wrong source proof accepted')
    checks.append({'case':'wrong_source_proof_rejected','outcome':'PASS'})
    assert entry.uid_from(b'package:org.droidloom.qa.bili.r3 uid:19999\n') == synthetic_uid
    for uid in (10164,10165):
        try:
            entry.uid_from(('package:org.droidloom.qa.bili.r3 uid:'+str(uid)+'\n').encode())
        except RuntimeError as error:
            assert str(error) == 'NEW_APP_UID_REQUIRED'
        else:
            raise AssertionError('old helper UID accepted by actual parser')
    assert entry.INSTALL == ['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',entry.SELF,entry.GUEST_APK]
    assert entry.PACKAGE_LIST == ['/system/bin/cmd','package','list','packages','-u','-U','--user','all',entry.SELF]
    checks.append({'case':'actual_UID_parser_and_nonreplacement_install_contract','outcome':'PASS'})

    def functions(path):
        return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_bytes()).body
                if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    before, after = functions(BASE/'install_state.py'), functions(HERE/'install_state.py')
    assert set(before) == set(after)
    assert [name for name in before if before[name] != after[name]] == ['uid_from']
    assert functions(BASE/'stage_execute.py') == functions(HERE/'stage_execute.py')
    assert functions(BASE/'make_request.py') == functions(HERE/'make_request.py')
    checks.append({'case':'all_inherited_actions_guards_error_and_cleanup_AST_unchanged_except_UID_rejection','outcome':'PASS'})
    print(json.dumps({'schema':1,'checks':checks,'all_expected_outcomes':True,
        'scope':'actual source and actual build receipts; synthetic constructor arguments only',
        'Android_or_Hepta_calls':0,'actual_APK_bytes_read_locally':False,
        'actual_install_UID':None,'install_or_UI_qualified':False},indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
