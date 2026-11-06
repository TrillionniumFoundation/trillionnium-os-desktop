#!/usr/bin/env python3
"""Read-only source derivation verification; writes only this review directory."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=ROOT/'owned-12306-qa-r1-build01/source'
NEW=ROOT/'owned-ihg-qa-r1-build01/source'


def pin(path):
    raw=path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def main():
    before_manifest=pin(OLD/'SOURCE_PINS.json')
    after_manifest=pin(NEW/'SOURCE_PINS.json')
    assert before_manifest['sha256']=='6347d21db7018471ddfa96297f54a4bd77aa98b98a59588e3869bacdabd30632'
    assert after_manifest['sha256']=='ab971f5b361f1d97b8036c954a6b88734b7faedbeed6349b873ead85fa79d5f3'
    for root in (OLD,NEW):
        for name,wanted in json.loads((root/'SOURCE_PINS.json').read_bytes())['files'].items():
            actual=pin(root/name)
            assert {k:actual[k] for k in ('bytes','sha256')}==wanted
    prior=ROOT/'root-recovery-20261104-02/evidence/ticket-r1-build01/build-result.json'
    actual_build=pin(prior)
    assert actual_build['bytes']==17389 and actual_build['sha256']=='d97e05bb923be43ca427a0526fa581b59534d5c5cb0957f1a402ed0f194ca976'
    receipt=json.loads(prior.read_bytes())
    assert receipt['source_manifest_sha256']==before_manifest['sha256']
    assert receipt['source_sha256']=={k:v['sha256'] for k,v in json.loads((OLD/'SOURCE_PINS.json').read_bytes())['files'].items()}
    assert receipt['state']=='BUILT_STATIC_VERIFIED_ANDROID_UNRUN' and receipt['error'] is None
    assert len(receipt['commands'])==11 and all(c['returncode']==0 and c['owned_child_joined'] is True and c['error'] is None and c['secondary_errors']==[] for c in receipt['commands'])
    mapping=json.loads((NEW.parent/'derivation-substitutions.json').read_bytes())
    replacements=mapping['literal_substitutions']
    labels=[('Amazon','IHG'),('AMAZON','IHG'),('amazon','ihg')]
    exclusions={
        'qa_contract.py':('helper_uid not in (UID, 10129, 10117, 10125, 10164, 10165, 10166, 10169, 10170, 10175)',
            'helper_uid not in (UID, 10121, 10129, 10117, 10125, 10164, 10165, 10166, 10169, 10170, 10175, 10184, 10190)'),
        'qa_adapter.py':('helper_uid not in (10137,10129,10117,10125,10164,10165,10166,10169,10170,10175)',
            'helper_uid not in (10137,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190)')}
    rows=[];delta='';changed_methods={}
    files=json.loads((NEW/'SOURCE_PINS.json').read_bytes())['files']
    for name in files:
        if name.endswith('.json') or name=='README.md':continue
        old_name=name.replace('org/droidloom/qa/ihg/r1','org/droidloom/qa/ticket/r1')
        original=(OLD/old_name).read_text();expected=original
        for previous,current in replacements:expected=expected.replace(previous,current)
        if name.endswith('.py'):
            for previous,current in labels:expected=expected.replace(previous,current)
        actual=(NEW/name).read_text();reconstructed=expected
        if name in exclusions:
            previous,current=exclusions[name]
            assert expected.count(previous)==actual.count(current)==1
            reconstructed=expected.replace(previous,current)
        assert reconstructed==actual, name+' has an undeclared change'
        delta+=''.join(difflib.unified_diff(expected.splitlines(keepends=True),actual.splitlines(keepends=True),
            fromfile='fully-literal-derived/'+name,tofile='frozen-IHG/'+name))
        functions=[]
        if name.endswith('.py'):
            def definitions(text):
                found={}
                for node in ast.parse(text).body:
                    if isinstance(node,ast.FunctionDef):found[node.name]=ast.dump(node,include_attributes=False)
                    elif isinstance(node,ast.ClassDef):
                        for member in node.body:
                            if isinstance(member,ast.FunctionDef):found[node.name+'.'+member.name]=ast.dump(member,include_attributes=False)
                return found
            old_defs=definitions(expected);new_defs=definitions(actual)
            functions=sorted(k for k in set(old_defs)|set(new_defs) if old_defs.get(k)!=new_defs.get(k))
        changed_methods[name]=functions
        rows.append({'new_relative_path':name,'old':pin(OLD/old_name),'new':pin(NEW/name),
            'literal_derivation_plus_exact_declared_UID_exclusions_byte_identical':True,'residual_functions_or_methods':functions})
    assert changed_methods['qa_adapter.py']==['Session.__init__'] and changed_methods['qa_contract.py']==['parse_completed']
    assert all(v==[] for k,v in changed_methods.items() if k not in exclusions)
    delta_path=HERE/'normalized-logic-residual.patch'
    with delta_path.open('x') as stream:stream.write(delta)
    target=json.loads((NEW/'target-artifact-reference.json').read_bytes())
    observed=json.loads((NEW.parent/'references/ihg-result-reconstructed.json').read_bytes())
    assert target['package']==observed['package']=='com.ihg.apps.android' and target['uid']==observed['metadata_before']['uid']==10137
    assert target['current_artifacts']==observed['artifacts'] and target['current_launcher']==observed['launcher_resolution']
    assert target['commercial_signer_qualification'] is False
    report={'schema':1,'scope':'READ_ONLY_DERIVED_SOURCE_REVIEW_NO_NEW_CONTROLS_OR_RUNTIME',
        'baseline_source_manifest':before_manifest,'baseline_actual_build':actual_build,
        'new_source_manifest':after_manifest,'complete_replacement_map':replacements,
        'additional_Python_diagnostic_and_module_label_map':labels,
        'normalization_method':'Reconstruct each new code file from exact pinned old bytes using the full ordered literal map, then compare to frozen new bytes. This avoids ambiguous naive reverse replacement where both TICKET and AMAZON become IHG. The residual diff is equivalent to provenance-aware inverse normalization.',
        'all_seven_code_XML_Java_files_fully_reconstructed':True,'code_files':rows,
        'only_residual_logic':'Two helper-UID reject tuples add 10121 (old Ticket target), 10184 (known Bili R6 helper), 10190 (known Ticket R1 helper).',
        'normalized_logic_residual':pin(delta_path),
        'escaped_regex_bindings':[
            {'language':'Python raw string','old':r'com\.MobileTicket','new':r'com\.ihg\.apps\.android',
             'locations':['qa_contract.scope activity','qa_contract.validate_request unreachable text resource','qa_contract.select_unique_editable unreachable text resource','qa_adapter.validate_plan unreachable text resource']},
            {'language':'Java source string','old':r'com\\.MobileTicket','new':r'com\\.ihg\\.apps\\.android',
             'locations':['ActionRunner.validateScope activity','ActionRunner.onStart unreachable text resource']}],
        'new_regex_rule_or_scope_expansion':False,'all_new_package_dots_remain_literal':True,
        'original_Java_and_Session_sequence_and_instrument_bodies_unchanged_except_declared_target_literals':True,
        'metadata_only_files':['README.md','build-input-reference.json','target-artifact-reference.json'],
        'target_reference_matches_exact_actual_IHG_metadata':True,'commercial_signer_and_new_helper_identity_not_assumed':True,
        'frozen_source_request_or_manifest_modified':False,'new_control_cases':0,'Android_or_remote_actions':0}
    raw=(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    with (HERE/'review.json').open('xb') as stream:stream.write(raw)
    print(json.dumps({'review':pin(HERE/'review.json'),'residual':pin(delta_path),'methods':changed_methods}))


if __name__=='__main__':main()
