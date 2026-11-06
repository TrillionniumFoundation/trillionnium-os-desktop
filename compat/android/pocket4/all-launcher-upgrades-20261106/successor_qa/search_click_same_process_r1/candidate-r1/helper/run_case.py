"""Bounded declarative case over the existing R9 Session.sequence path.

Each action has a separate fresh inspect/state restoration sequence afterwards
and an explicit observed UI postcondition before another decision. Original
action results remain unknown; this does not reconcile launch or failed work.
"""
import argparse
import json
import os
from pathlib import Path
import re
import time
import types

HERE = Path(__file__).resolve().parent
RECORDER_MANIFEST_SHA = '646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4'


def need(value, code):
    if not value:
        raise RuntimeError(code)


def validate_case(value, adapter, qa):
    need(type(value) is dict and set(value) == {'schema','name','steps'} and
         value['schema'] == 'pocket4-owned-scoped-qa-case-v1' and
         re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',value['name']) and
         type(value['steps']) is list and 1 <= len(value['steps']) <= 8,'CLOSED_BOUNDED_CASE')
    nonces = set()
    for entry in value['steps']:
        need(type(entry) is dict and set(entry) == {'plan','post_inspection','postcondition'},'CLOSED_CASE_STEP')
        plan = adapter.validate_plan(entry['plan'],qa)
        post = adapter.validate_plan(entry['post_inspection'],qa)
        need(plan['operation'] in ('inspect','click','set_text','reveal_controls','player_button','search_click') and
             post['operation'] == 'inspect','EXPLICIT_ACTION_AND_INDEPENDENT_POST_INSPECT')
        for selected in (plan,post):
            for nonce in selected['nonces'].values():
                need(nonce not in nonces,'CASE_NONCE_REUSE')
                nonces.add(nonce)
        condition = entry['postcondition']
        need(type(condition) is dict and condition and set(condition) <= {'resource_id','text','content_desc','class','enabled','clickable'} and
             any(type(condition.get(k)) is str and condition[k] for k in ('resource_id','text','content_desc')),
             'EXACT_OBSERVABLE_POSTCONDITION_REQUIRED')
        for key,item in condition.items():
            need(type(item) is (bool if key in ('enabled','clickable') else str) and
                 (type(item) is bool or 0 < len(item.encode('utf-8')) <= 256),'POSTCONDITION_VALUE_TYPE_OR_BOUND')
    return value


def match_postcondition(qa, inspected, condition):
    tree = qa.inspect_record(inspected)
    matching = [node for node in tree['nodes'] if node.get('package') == qa.PACKAGE and node.get('visible') is True and
        node.get('password') is False and all(node.get(k) == v for k,v in condition.items()) and
        all(node.get(k+'_truncated') is False for k in condition if type(condition[k]) is str)]
    need(len(matching) == 1,'ONE_FRESH_REAL_POSTCONDITION_NODE_REQUIRED')
    return {'node_path':matching[0]['path'],'node_sha256':matching[0]['node_sha256'],
            'tree_sha256':tree['tree_sha256'],'window_sha256':tree['window_sha256']}


def execute(args):
    need(args.interactive_production is True and os.getuid() == os.geteuid() == 0,'EXPLICIT_ROOT_INTERACTIVE_CASE')
    # Bootstrap uses a separately supplied source manifest. All subsequent
    # definitions are loaded only from its exact content closure.
    fd = os.open(HERE/'SOURCE_PINS.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        raw = os.read(fd,131073)
        need(len(raw) <= 131072,'SOURCE_MANIFEST_BOUND')
    finally:
        os.close(fd)
    import hashlib
    need(hashlib.sha256(raw).hexdigest() == args.source_manifest_sha256,'EXTERNAL_CASE_SOURCE_PIN')
    source = json.loads(raw)
    path = HERE/'qa_adapter.py'
    raw = path.read_bytes()
    need(len(raw) == source['files']['qa_adapter.py']['bytes'] and
         hashlib.sha256(raw).hexdigest() == source['files']['qa_adapter.py']['sha256'],'ADAPTER_BOOTSTRAP_PIN')
    adapter = types.ModuleType('successor_case_adapter')
    adapter.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),adapter.__dict__)
    manifest = adapter.own_source(args.source_manifest_sha256)
    qa = adapter.load(HERE/'qa_contract.py',manifest['files']['qa_contract.py']['sha256'],'successor_case_contract')
    builder = adapter.load(HERE/'build_candidate.py',manifest['files']['build_candidate.py']['sha256'],'successor_case_build')
    proof = adapter.qualified_build(args,manifest,builder)
    case_raw = adapter.pinned(args.case,args.case_sha256,65536)
    case = validate_case(json.loads(case_raw),adapter,qa)
    need(re.fullmatch(r'/home/alex/work/pocket4-successor-qa-flow-[0-9a-f]{32}',str(args.flow_dir)) and
         args.flow_dir.resolve() == args.flow_dir and args.recorder_root.resolve() == args.recorder_root,'NEW_FIXED_CASE_FLOW')
    manifest = json.loads(adapter.pinned(args.recorder_root/'source-manifest.json',RECORDER_MANIFEST_SHA,131072))
    recorder = adapter.load(args.recorder_root/'recorder.py',manifest['files']['recorder.py']['sha256'],'successor_case_recorder')
    mutation = any(entry['plan']['operation'] != 'inspect' for entry in case['steps'])
    scope = types.SimpleNamespace(operation='owned-qa-case',adapter_manifest_sha256=RECORDER_MANIFEST_SHA,
        flow_dir=args.flow_dir,epoch_module=args.recorder_root/'references/framework_epoch.py',
        task_source=args.recorder_root/'references/task_scope_baseline.py',step=args.step,
        request={'case':case,'case_sha256':args.case_sha256,'build':proof},unknown_step=None,observation_step=None,postcondition=None)
    result = {'schema':'pocket4-owned-scoped-qa-case-result-v1','ok':False,'case_sha256':args.case_sha256,
        'steps':[],'errors':[],'automatic_retry':False,'original_action_outcomes_rewritten':False,
        'business_success_verified':False,'production_ready':False}
    flow = lock = None
    try:
        flow = recorder.Flow(scope)
        flow.begin(scope,mutation)
        lock = recorder.lock_file(recorder.ACTION_LOCK)
        session = adapter.Session(flow,recorder,qa,proof,args.helper_uid)
        deadline = time.monotonic() + 180
        for index,entry in enumerate(case['steps']):
            need(time.monotonic() < deadline,'CASE_DEADLINE_BEFORE_NEXT_DECISION')
            flow.guard(attempted=flow.action_attempted)
            observed = session.sequence(entry['plan'])
            recorder.write_new(flow.step/('case-%02d-operation.json'%index),observed)
            post = session.sequence(entry['post_inspection'])
            post_nonce = entry['post_inspection']['nonces']['inspect']
            assessment = json.loads(adapter.bounded(flow.step/(post_nonce+'.assessment.json')))
            need(assessment['wire_sha256'] == post['inspection_wire_sha256'] and
                 assessment['helper']['nonce'] == post_nonce and assessment['helper']['op'] == 'inspect' and
                 assessment['helper']['action_attempted'] is False and post['restoration_qualified'] is True,
                 'INDEPENDENT_POST_INSPECTION_AND_RESTORATION_REQUIRED')
            matched = match_postcondition(qa,assessment['helper']['inspection'],entry['postcondition'])
            receipt = {'index':index,'post_nonce':post_nonce,'post_wire_sha256':post['inspection_wire_sha256'],
                       'matched':matched,'postcondition':entry['postcondition'],
                       'original_action_outcome':'unknown_retained' if entry['plan']['operation']!='inspect' else 'readonly',
                       'allows_next_declared_case_decision_only':True,'business_success_verified':False}
            recorder.write_new(flow.step/('case-%02d-postcondition.json'%index),receipt)
            result['steps'].append(receipt)
        result['ok'] = True
        result['declared_scoped_sequence_completed'] = True
    except BaseException as error:
        result['errors'].append({'type':type(error).__name__,'code':str(error)[:256]})
    finally:
        if flow is not None:
            for phase,operation in (('final_guard',lambda:flow.guard(attempted=flow.action_attempted)),('held_binding_close',flow.close)):
                try:
                    operation()
                except BaseException as error:
                    result['errors'].append({'phase':phase,'type':type(error).__name__})
        if result['errors']:
            result['ok'] = False
        result['action_attempted'] = bool(flow is not None and flow.action_attempted)
        result['outcome_unknown'] = result['action_attempted']
        result['ended_utc'] = recorder.now()
        if flow is not None:
            result['epoch_sha256'] = flow.scope['epoch_sha256']
        try:
            if flow is not None and flow.step is not None:
                recorder.write_new(flow.step/'result.json',result)
        finally:
            if lock is not None:
                os.close(lock)
    print(json.dumps(result,sort_keys=True,ensure_ascii=True),flush=True)
    return 0 if result['ok'] else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-once',action='store_true')
    p.add_argument('--interactive-production',action='store_true')
    for name in ('source-manifest-sha256','build-receipt-sha256','apk-sha256','signer-certificate-sha256','case-sha256','step'):
        p.add_argument('--'+name)
    for name in ('build-receipt','recorder-root','flow-dir','case'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--helper-uid',type=int)
    args = p.parse_args()
    if not args.execute_once:
        print(json.dumps({'status':'PLAN_ONLY','maximum_case_steps':8,'UI_admitted':False}))
        return 0
    os.umask(0o077)
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
