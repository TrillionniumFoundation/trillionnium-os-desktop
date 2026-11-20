"""Freeze R24 from complete actual R23/R22 resource refusals; no build or source locks."""
from pathlib import Path
import ast
import hashlib
import json
import os
import resource
import signal
import stat
import sys
import types
sys.dont_write_bytecode = True
ROOT = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1')
PREP = Path('/home/qq/work/current2367-cli-preparation-20261120-3b9d-r1')
STAGE = Path('/home/qq/work/p4-r24-controller-preparation-20261120-3b9d-r1')
DEST = ROOT / 'control/vendor-build-20261120-9907-r24'
R23 = ROOT / 'control/vendor-build-20261120-9907-r23'
CURRENT = {'tree':'fd0ef624e436d1eb5c8d2c4083335088811a6a42','files':2367,'bytes':45262277}
INDEPENDENT_FREEZER_REVIEW_PIN = None
SOURCE_INPUT_PINS = {'r23_prebuild_admission.py': (20612, 'fe5511a7f22f17769c23cb8dbc18b31665556e358eb676575dfeac53c6ae0fa6'), 'R23-PREBUILD-ACTUAL-CONTROLS.json': (32987, 'c6511162ca1200f8523075c5706861e8bffcffcbe98138535082daaad95c1927'), 'test_r23_prebuild_actual.py': (12403, '52aab99fcb781b6466561401157b97bf021d5194991205bad825182257e8374b'), 'R23-PREBUILD-HELPER-INPUTS.json': (4629, '419b11a33e2ddd9bdc43cb16c9d44e442602e72586bbdce485cbfa21ea5c9f73'), 'R23-ACTUAL-FILE-INFO.json': (1785, 'f803b68c54f44107ce1a0214f3c344904e8c12ea807f721412d86b21ec47616a'), 'R23-PREBUILD-HELPER-HANDOFF.json': (3559, '427aa893bb5e9f2147163e3530b816471ed3d08980b71560f335b2c135149cb0'), 'SOURCE-INDEPENDENT-REVIEW.json': (3238, '1eee7c9c1a25dd442c49f970cb386320d31e3273ffc8e95a165c8a33a5cd7994'), 'SOURCE-CONSERVATION.json': (1477, '66b77c3bbb0ab2c31980507335ae236209c41c090c8e9b34f1404c52267d887f'), 'R24-BOOTSTRAP-ADMISSION.py': (11212, '59ff1334ea251f004f33100245b00bec3cc5b83ed4ead9b13daa205b23cbf185'), 'source-r24-template.py': (354072, 'b20145f9d8daee8616fb622aa63847e346d2afc188c12501f31c14f30c2bc5d1'), 'outer-r24-template.py': (35188, '7f1d71e782658d16c14c30f9c352025bf647f58e9c1aff289dcef5e5a935cb3c'), 'CLIENTS-RAW.json': (63259, '340d2afc32c11c1f20e6e099f79da2d31b5bd83bfe321e7929c2627d7e8536ee'), 'prepare_candidates.py': (5462, '3fa1a0f614f35a8ffe221213e9e030c7ff0e46f01d3c5415dfeb9de07fdc7ac1')}
CLIENT_ROSTER = (('r23-controller-stage', 'dpty-b89809e41cb901a245fe6013f91127c424c48dce4218317551df9599906f8647', 0), ('r23-input-freeze', 'dpty-53971af9e52fcec6420cbb9844a17ebee7cdbe09ec920328b2758f66db2f4054', 0), ('r23-original-supervisor', 'dpty-4b559da7e3cf112676f930f890b7262bafd2e4c230f6e8d459f06154abc7e4cc', 1), ('r23-resource-view-direct', 'dpty-e59704d903ae55b808d44a4958f3561834188af6f16069f984dbd2dd3c5c9ec4', 0), ('r23-resource-view-service', 'dpty-a84df6a9ab050331674763e5b3bff3a2aed21ae506f24903f4ae46c7349c9836', 0), ('r23-resource-stability', 'dpty-9c13917a5733cd6fa850017c983d72c17a29130325f4496cda1c0689c059c161', 0))
EXTRA_TARGETS = [{'scope': 'user', 'unit': 'p4-cp3a-vendor-supervisor-20261120-9907-r23.service', 'pids': []}, {'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r23.service', 'pids': []}, {'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r23-recovery.service', 'pids': []}, {'scope': 'user', 'unit': 'p4-r23-resource-view-20261120-3b9d-r1.service', 'pids': []}, {'scope': 'user', 'unit': 'p4-r23-resource-stability-20261120-3b9d-r1.service', 'pids': []}, {'scope': 'user', 'unit': 'p4-r24-resource-preflight-20261120-3b9d-r1.service', 'pids': []}]

def need(value, message):
    if not value:
        raise RuntimeError(message)



def f9(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]



def read(path, cap=16*1024**2):
    path=Path(path)
    need(path.is_absolute() and path.resolve()==path,'canonical whole input')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=f9(os.fstat(fd))
        need(stat.S_ISREG(before[2]) and before[5]==1 and 0<=before[6]<=cap,'bounded regular input')
        with os.fdopen(os.dup(fd),'rb') as stream: body=stream.read(cap+1)
        need(len(body)==before[6] and f9(os.fstat(fd))==f9(path.lstat())==before,'whole original input bookend')
        return {'path':str(path),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'identity':before},body
    finally:
        os.close(fd)



def pinned(path, expected):
    reference,raw=read(path)
    need(type(expected) is tuple and (reference['bytes'],reference['sha256'])==expected,'exact frozen input: '+str(path))
    return reference,raw



def check(reference):
    actual,_=read(reference['path'])
    need(actual==reference,'original complete identity changed: '+reference['path'])
    return actual



def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))



def document(path):
    reference,raw=read(path)
    return reference,decode(raw)



def same_source_snapshot(actual, persisted):
    """Compare every native F9 integer across the original JSON tuple encoding."""
    need(set(actual)==set(persisted)=={'tree','files','directories'},'complete original source snapshot shape')
    need(actual['tree']==persisted['tree']==CURRENT['tree'],'exact complete source tree')
    for group in ('files','directories'):
        need(type(actual[group]) is dict and type(persisted[group]) is dict
             and actual[group].keys()==persisted[group].keys(),'exact original snapshot membership')
        for name,vector in actual[group].items():
            stored=persisted[group][name]
            need(type(vector) is tuple and type(stored) is list and len(vector)==len(stored)==9
                 and all(type(x) is int for x in (*vector,*stored)), 'nine native integer F9 fields')
            need(list(vector)==stored,'original source identity changed: '+name)
    return True



def module(path, expected):
    reference,raw=pinned(path,expected)
    value=types.ModuleType('r22_'+Path(path).stem);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    check(reference)
    return value,reference



def write(path, raw):
    need(path.parent.resolve()==path.parent,'canonical new parent')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return read(path)[0]



def save(path, value):
    return write(path,(json.dumps(value,indent=2,sort_keys=True)+'\n').encode())



def complete_clients(path):
    descriptor, raw = pinned(path, SOURCE_INPUT_PINS['CLIENTS-RAW.json'])
    values = decode(raw)
    need(type(values) is list and len(values) == len(CLIENT_ROSTER) == 6,
         'exact six already-completed original preparation clients')
    clients = []
    for item, expected in zip(values, CLIENT_ROSTER):
        need(type(item) is dict and set(item) == {'name', 'expected_exit_code', 'pages_raw'}
             and type(item['expected_exit_code']) is int
             and (item['name'], item['expected_exit_code']) == (expected[0], expected[2]),
             'fixed original client name and actual outcome')
        pages = [decode(value.encode()) for value in item['pages_raw']]
        need(len(pages) == 1, 'each of these six actual original clients fits its complete first page')
        original = pages[0]
        status = original['status']; cursor = 0; body = bytearray()
        need(original['session_id'] == expected[1]
             and status['state'] == 'exited' and status['exit_code'] == item['expected_exit_code']
             and type(status['exit_code']) is int and status['output_complete'] is True
             and status['capture_error'] is None, 'actual final original client state')
        for page in pages:
            need(page['session_id'] == original['session_id'] and page['status'] == status
                 and page['archive_path'] == original['archive_path'] and page['offset'] == cursor
                 and page['output_complete'] is True and page['utf8_pending'] is False
                 and page['text_is_lossy'] is False and page['truncated_before_offset'] is False,
                 'continuous complete original terminal byte pages')
            need(all(type(page[key]) is int for key in ('offset', 'next_offset', 'available_end'))
                 and all(type(status[key]) is int for key in ('bytes_seen', 'bytes_stored')),
                 'original byte offsets and totals are native integers')
            chunk = bytes.fromhex(page['bytes_hex'])
            need(len(chunk) == page['next_offset'] - cursor <= 16384
                 and hashlib.sha256(chunk).hexdigest() == page['chunk_sha256'],
                 'whole actual terminal page body')
            body.extend(chunk); cursor = page['next_offset']
        stdout, actual = read(original['archive_path'])
        need(bytes(body) == actual and cursor == original['available_end']
             == status['bytes_seen'] == status['bytes_stored'] == stdout['bytes'],
             'complete original stdout archive under whole F9 bookends')
        clients.append({'name': item['name'], 'session_id': original['session_id'],
            'expected_exit_code': item['expected_exit_code'], 'actual_status': status, 'stdout': stdout})
    need(len({x['session_id'] for x in clients}) == 6,
         'no duplicated or future preflight preparation client')
    return descriptor, clients


def absent_roots():
    need(ROOT.resolve() == ROOT, 'same original vendor parent path')
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(before[:5] == [66306, 72405100, 16832, 1000, 1000],
             'exact actual original vendor parent inode and authority')
        for name in ('producer-build-r23-9907', 'out-build-r23-9907', 'tmp-build-r23-9907',
                     'producer-build-r24-9907', 'out-build-r24-9907', 'tmp-build-r24-9907'):
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('pre-existing old or new generation root: ' + name)
        need(before == f9(os.fstat(fd)) == f9(ROOT.lstat()), 'held parent whole absence bookend')
        return {'parent': str(ROOT), 'parent_identity': before,
            'R23_roots_absent': ['producer-build-r23-9907','out-build-r23-9907','tmp-build-r23-9907'],
            'R24_roots_absent': ['producer-build-r24-9907','out-build-r24-9907','tmp-build-r24-9907']}
    finally:
        os.close(fd)


def source_conservation(old_raw, new_raw, old_outer, new_outer):
    old = old_raw.decode(); new = new_raw.decode()
    old_ast = ast.parse(old); new_ast = ast.parse(new)
    lines = old.splitlines(keepends=True)
    guards = [x for x in old_ast.body if isinstance(x, ast.If)
              and ast.unparse(x.test) == "__name__ == '__main__'"]
    need(len(guards) == 1, 'single unchanged original main guard')
    guard = guards[0]
    need(new.startswith(''.join(lines[:guard.lineno-1])) and new.endswith(''.join(lines[guard.lineno-1:])),
         'entire exact frozen R23 prefix and original main retained')
    original = {x.name: x for x in old_ast.body if isinstance(x, ast.FunctionDef)}
    successor = {x.name: x for x in new_ast.body if isinstance(x, ast.FunctionDef)}
    changed = [name for name in original
               if ast.dump(original[name], include_attributes=False)
               != ast.dump(successor[name], include_attributes=False)]
    need(sorted(changed) == ['r20_recovery_retirement', 'verify_serialized_retirement'],
         'only two explicitly reviewed existing definitions change')
    def text_of(node, text):
        return ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
    verify = text_of(original['verify_serialized_retirement'], old)
    anchor = "        successor = r23_successor_extra_admission()\n        return {'actual_R22_continuation': successor,"
    replacement = "        successor = r23_successor_extra_admission()\n        successor24 = r24_successor_extra_admission()\n        return {'actual_R23_continuation': successor24, 'actual_R22_continuation': successor,"
    need(verify.count(anchor) == 1 and text_of(successor['verify_serialized_retirement'], new)
         == verify.replace(anchor, replacement), 'one exact extra call within the original absolute deadline')
    retired = text_of(original['r20_recovery_retirement'], old)
    need(text_of(successor['r20_recovery_retirement'], new) == retired.replace(
        'p4-r23-original-build-retirement-before-recovery-v1',
        'p4-r24-original-build-retirement-before-recovery-v1'), 'only current retirement schema changes')
    need(new_outer == old_outer.replace(
        b"BUNDLE_SHA = '4cb03fae174dd725689f470b6c9d56badfe492dbc36203d59cb85b3c6c0634ca'",
        b"BUNDLE_SHA = 'UNFROZEN_SOURCE_ONLY'").replace(b'r23', b'r24').replace(b'R23', b'R24'),
        'original complete outer changes only generation literals and the pending bundle pin')
    return {'entire_frozen_R23_prefix_and_main_bytes_retained': True,
        'only_two_existing_definitions_changed': changed,
        'same_original_absolute_admission_deadline': True,
        'original_build_recovery_resource_and_lock_functions_unchanged': True}


def main():
    need(type(INDEPENDENT_FREEZER_REVIEW_PIN) is tuple,
         'actual independent freezer source review must be frozen before preparation')
    need(os.getuid() == os.geteuid() == os.getgid() == 1000, 'ordinary original ai395 owner')
    need(18 in os.sched_getaffinity(0), 'original reserved preparation CPU18')
    os.sched_setaffinity(0, {18})
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8*1024**2, 8*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); signal.alarm(120)
    need(not os.path.lexists(DEST), 'fresh create-only R24 controller directory')
    absence = absent_roots()
    staged = {name: pinned(STAGE/name, pin)[0] for name, pin in SOURCE_INPUT_PINS.items()}
    review_ref, review_raw = pinned(STAGE/'FREEZER-INDEPENDENT-REVIEW.json', INDEPENDENT_FREEZER_REVIEW_PIN)
    review = decode(review_raw)
    need(review.get('passed_source_review') is True and review.get('host_execution') is False,
         'reviewed actual freezer source, without invented runtime credit')
    source_inputs = list(staged.values()) + [review_ref, read(Path(__file__))[0]]
    source_review = decode(read(STAGE/'SOURCE-INDEPENDENT-REVIEW.json')[1])
    need(source_review['schema'] == 'p4-r24-independent-source-and-nested-evidence-review-v1'
         and source_review['passed'] is True and source_review['host_execution'] is False
         and source_review['actual_R23_status_children_consumed'] == 135
         and source_review['actual_nested_R22_status_children_consumed'] == 132,
         'actual independent R24 source and nested evidence review')
    for reference in source_review['inputs']:
        name = Path(reference['path']).name
        need(name in staged and (reference['bytes'], reference['sha256']) == SOURCE_INPUT_PINS[name],
             'the independently reviewed source bodies are these exact staged inputs')
    old_worker, old_raw = pinned(R23/'source.py',
        (335019,'19f730767efb1afd3e065093f389e02c8ddfa41e62c19aa89e97574e6ff3dff8'))
    old_outer_ref, old_outer = pinned(R23/'outer.py',
        (35232,'915355af4fce7ca741acb021d10c81ea252e6f76064ef051f0c1d89bbb130e36'))
    template_ref, template = pinned(STAGE/'source-r24-template.py', SOURCE_INPUT_PINS['source-r24-template.py'])
    outer_ref, outer_template = pinned(STAGE/'outer-r24-template.py', SOURCE_INPUT_PINS['outer-r24-template.py'])
    conservation = source_conservation(old_raw, template, old_outer, outer_template)
    old = types.ModuleType('r24_exact_frozen_r23'); old.__file__ = old_worker['path']
    exec(compile(old_raw, old.__file__, 'exec'), old.__dict__)
    need(str(old.LOCK) == str(ROOT/'producer-build-r23-9907/android/manifest/production-full-apex-tests-source-lock.json'),
         'exact original never-created R23 planned producer lock')
    helper, helper_ref = module(STAGE/'r23_prebuild_admission.py', SOURCE_INPUT_PINS['r23_prebuild_admission.py'])
    r23_inputs = {}; raw_inputs = {}; nested_refs = []
    for name, (relative, size, sha, identity) in helper.HISTORY.items():
        reference, raw = pinned(R23/relative, (size,sha))
        need(reference['identity'] == identity, 'same complete original R23 historical file identity')
        r23_inputs[name] = reference; raw_inputs[name] = {'reference': reference, 'raw': raw}
    need(decode(raw_inputs['contract']['raw']) == old.R23, 'same actually executed original R23 operational contract')
    baseline = old.r23_current_baseline()
    helper22_ref, helper22_raw = read(old.R23['prebuild_helper']['path'])
    need(helper22_ref == old.R23['prebuild_helper'] == helper.R22_HELPER_REF,
         'original reviewed R22 helper whole body and original identity')
    raw_inputs['r22_helper'] = {'reference': helper22_ref, 'raw': helper22_raw}
    nested_refs.append(helper22_ref)
    raw_inputs['r22'] = {}
    for name, expected in old.R23['r22_inputs'].items():
        reference, raw = read(expected['path'])
        need(reference == expected, 'exact complete nested R22 original input')
        raw_inputs['r22'][name] = {'reference': reference, 'raw': raw}; nested_refs.append(reference)
    raw_inputs['r22']['preparation_outputs'] = {}
    for client in old.R22['preparation_clients']:
        reference, raw = read(client['stdout']['path'])
        need(reference == client['stdout'], 'complete original R22 preparation stdout identity')
        raw_inputs['r22']['preparation_outputs'][client['session_id']] = {'reference': reference, 'raw': raw}
        nested_refs.append(reference)
    raw_inputs['preparation_outputs'] = {}
    for client in old.R23['preparation_clients']:
        reference, raw = read(client['stdout']['path'])
        need(reference == client['stdout'], 'complete original R23 preparation stdout identity')
        raw_inputs['preparation_outputs'][client['session_id']] = {'reference': reference, 'raw': raw}
        nested_refs.append(reference)
    failure = helper.validate_r23_prebuild(raw_inputs, baseline)
    old.r23_current_baseline(); old.r23_validate_controls(); old.r22_validate_controls(); old.source_contracts()
    ci = old.r20_json(old.R22['release_ci'])
    for reference in old.R22['current_binaries'].values(): old.r20_check(reference)
    release = old.ADMISSION22.validate_current_release(ci, old.R22['current_binaries'], old.R22['ci_provenance'])
    abi = old.r20_json(old.R22['host_direct_abi'])
    for reference in old.ADMISSION22.validate_host_abi_custody(abi, old.R22['host_abi_inputs']):
        old.r20_check(reference)
    source_ref, source = document(PREP/'SOURCE_FREEZE.json')
    need((source_ref['bytes'],source_ref['sha256']) == (2243323,'2663841a3ff4d3b646bfbb67e4a54189ce23e47b364f08b32abb4efbf9dacba8'),
         'same complete actually prepared source freeze')
    rows_ref, rows = document(PREP/'SOURCE-ROWS.json')
    need((rows_ref['bytes'],rows_ref['sha256']) == (704250,'7c92d4a0cd08f33cac08fe051c8e7a569d0cf5f433d57b6db3afcc1dde72ff67'),
         'same full current source row list')
    source_helper, source_helper_ref = module(PREP/'source_helpers.py',
        (27232,'e6a14326b1aa1ccc17d606c60bfc9bdf525f47bb2ccafffc86a054c55dd06219'))
    need(same_source_snapshot(source_helper.source_snapshot(PREP/'producer', rows, CURRENT['tree']),
                              source['source_snapshot']), 'whole original current source remains unchanged')
    materialized = []
    for path, expected in old.PINS.items():
        if path == old.LOCK:
            continue
        actual = old.digest(path)
        need((actual['bytes'],actual['sha256']) == expected, 'every actual historical R23 pin remains unchanged')
        materialized.append(actual)
    need(len(materialized) == len(old.PINS)-1, 'one and only one unmaterialized planned declaration')
    client_descriptor, clients = complete_clients(STAGE/'CLIENTS-RAW.json')
    contract = {'schema':'p4-vendor-r24-prebuild-continuation-contract-v1',
        'operational_inputs_frozen':True, 'runtime_qualified':False, 'production_ready':False,
        'current_source':old.R23['current_source'], 'current_binaries':old.R23['current_binaries'],
        'baseline':old.R23['baseline'], 'r23_inputs':r23_inputs,
        'prebuild_helper':helper_ref, 'prebuild_controls':staged['R23-PREBUILD-ACTUAL-CONTROLS.json'],
        'root_authority':absence['parent_identity'][:5], 'actual_predecessor_absence':absence,
        'unmaterialized_R23_plan':{'lock_path':str(old.LOCK),'lock_bytes':400720,
            'lock_sha256':old.TRANSITION22.NEW_LOCK_SHA,'absent_roots':absence['R23_roots_absent']},
        'all_actual_R23_materialized_input_refs':materialized,
        'additional_live_retirement_targets':EXTRA_TARGETS,
        'preparation_clients':clients, 'source_inputs':source_inputs,
        'all_original_constraints_unchanged':True, 'source_conservation':conservation}
    # Finish every direct and complete producer bookend before creating DEST.
    direct = [*source_inputs, *r23_inputs.values(), *nested_refs, template_ref, outer_ref,
        source_ref, rows_ref, source_helper_ref, client_descriptor,
        *[x['stdout'] for x in clients], baseline['manifest'],
        *[{key: value for key, value in row.items() if key != 'body_hex'} for row in baseline['locks']]]
    for reference in direct: check(reference)
    for reference in materialized:
        need(old.digest(Path(reference['path'])) == reference, 'complete historical materialized input bookend')
    need(same_source_snapshot(source_helper.source_snapshot(PREP/'producer', rows, CURRENT['tree']),
                              source['source_snapshot']), 'complete actual producer final bookend')
    need(absent_roots() == absence, 'same actual parent and all uncreated generation roots')
    DEST.mkdir(mode=0o700); (DEST/'inputs').mkdir(mode=0o700)
    contract_ref = save(DEST/'inputs/CONTRACT.json', contract)
    anchor = b'R24_CONTRACT_PIN = None'; need(template.count(anchor)==1, 'one exact new contract anchor')
    frozen = template.replace(anchor, ('R24_CONTRACT_PIN = '+repr((contract_ref['bytes'],contract_ref['sha256']))).encode())
    worker_ref = write(DEST/'source.py', frozen)
    worker = types.ModuleType('r24_actual_frozen_worker'); worker.__file__ = worker_ref['path']
    exec(compile(frozen,worker.__file__,'exec'), worker.__dict__)
    need(worker.R24 == contract and worker.R23 == old.R23 and worker.R22 == old.R22
         and worker.TREE == CURRENT['tree'] and str(worker.CONTROL) == str(DEST/'actual'),
         'actual complete successor imports the same full current and historical inputs')
    worker.r24_failure_inputs(); controls = worker.r24_validate_controls(); worker.source_contracts()
    need(set(old.PINS)-set(worker.PINS) == {old.LOCK}
         and all(worker.PINS[p] == pin for p,pin in old.PINS.items() if p != old.LOCK),
         'all actual historical pins retained; only exact never-materialized planned path reclassified')
    bundle = {'schema':'pocket4-vendor-r24-launch-bundle-v1', 'dispatch_inputs_frozen':True,
        'source_tree':CURRENT['tree'], 'current_runtime_source':CURRENT, 'worker':worker_ref,
        'operational_contract':contract_ref, 'actual_current_CI':old.R22['release_ci'],
        'actual_R23_prebuild_failure':r23_inputs, 'original_budgets_unchanged':True,
        'new_vendor_build_not_yet_dispatched':True, 'previous_failed_build_replaced':False,
        'runtime_qualified':False, 'production_ready':False}
    bundle_ref = save(DEST/'inputs/BUNDLE.json', bundle)
    anchor = b"BUNDLE_SHA = 'UNFROZEN_SOURCE_ONLY'"; need(outer_template.count(anchor)==1, 'one exact new bundle anchor')
    frozen_outer = outer_template.replace(anchor, ("BUNDLE_SHA = '"+bundle_ref['sha256']+"'").encode())
    compile(frozen_outer,str(DEST/'outer.py'),'exec')
    outer_ref = write(DEST/'outer.py',frozen_outer)
    receipt = {'schema':'p4-r24-actual-complete-input-freeze-v1', 'contract':contract_ref,
        'worker':worker_ref, 'outer':outer_ref, 'bundle':bundle_ref, 'actual_R23_failure':failure,
        'actual_current_release':release, 'actual_prebuild_controls':controls,
        'historical_actual_inputs_count':len(materialized),
        'all_actual_R23_inputs_bookended_unchanged':True, 'complete_current_source_unchanged':True,
        'explicit_unmaterialized_R23_plan':contract['unmaterialized_R23_plan'],
        'all_preparation_clients_complete':True, 'build_started':False, 'source_mutations':False,
        'source_locks_acquired':False, 'live_retirement_admitted':False,
        'future_resource_preflight_output_frozen':False,
        'runtime_qualified':False, 'production_ready':False}
    receipt_ref = save(DEST/'PREPARATION.json',receipt)
    print(json.dumps({'passed':True,'preparation':receipt_ref,'worker':worker_ref,'outer':outer_ref,
        'build_started':False,'runtime_qualified':False,'production_ready':False}),flush=True)


if __name__ == '__main__':
    main()
