"""Create separate IHG helper sources from a verified, actual final Main.

render() is a pure byte transformation for host controls. create() is the only
production construction entry: it first loads and guards BusinessBaseline,
then renders exact values from that object. No old source/global/nonce changes.
The Java and Python bodies retain the original public-input protocol checks.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re

SELF = 'org.droidloom.qa.ihg.finalmain.r1'
PROTOCOL = 'pocket4-owned-ihg-qa-final-main-v1'
OLD_SELF = 'org.droidloom.qa.ihg.r4'
OLD_PROTOCOL = 'pocket4-owned-ihg-qa-v4'
SCHEMA = 'pocket4-final-business-baseline-v1'
OLD = {'MAIN_EPOCH': '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c',
       'MAIN_BASELINE_SCHEMA': 'pocket4-main-current-baseline-v2',
       'MAIN_BASELINE_SHA': '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364',
       'MAIN_BASELINE_QUALIFICATION_SHA': 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'}
ORIGINAL_ROOT = '/home/alex/work/pocket4-android-final/qualification/app-runtime-dependencies-20261108-8b88-r2/runtime-inputs/pocket4-owned-ihg-qa-r4-source-01/source'
ORIGINALS = {
    'qa_contract.py': (28757, '5d83ba26324fd180abfd9069538a077a90a661d94c7a3d123694197b39430405'),
    'ActionRunner.java': (42244, '8b94f47113e435c013715ac8b3d623755e88d140fdae8c71cefa95240aff5117'),
    'AndroidManifest.xml': (713, 'f351faacc98ae4428f2f42f0c4dfbcf2ce72cfd8b14cf430565ce204c6de3246')}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def actual_values(baseline):
    need(baseline.value['schema'] == SCHEMA, 'ACTUAL_DISTINCT_FINAL_BASELINE_REQUIRED')
    return {'MAIN_EPOCH': baseline.value['framework_epoch']['sha256'],
        'MAIN_BASELINE_SCHEMA': baseline.value['schema'],
        'MAIN_BASELINE_SHA': baseline.baseline_ref['sha256'],
        'MAIN_BASELINE_QUALIFICATION_SHA': baseline.qualification_ref['sha256']}


def render(originals, values):
    need(set(originals) == set(ORIGINALS) and set(values) == set(OLD), 'EXACT_RENDER_INPUT_SET_REQUIRED')
    need(values['MAIN_BASELINE_SCHEMA'] == SCHEMA and all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v)
         for k, v in values.items() if k != 'MAIN_BASELINE_SCHEMA'), 'TYPED_NEW_MAIN_VALUES_REQUIRED')
    need(all(values[k] != OLD[k] for k in OLD), 'HISTORICAL_MAIN_VALUES_MUST_NOT_REAUTHORIZE')
    output = {}; changes = {}
    for name, raw in originals.items():
        size, expected = ORIGINALS[name]
        need(type(raw) is bytes and len(raw) == size and hashlib.sha256(raw).hexdigest() == expected,
             'EXACT_ORIGINAL_HELPER_SOURCE_REQUIRED:' + name)
        text = raw.decode('utf-8'); counts = {}
        for old, new in ((OLD_SELF, SELF), (OLD_PROTOCOL, PROTOCOL)):
            count = text.count(old)
            need(count >= (1 if old == OLD_SELF else 0), 'ORIGINAL_LITERAL_MISSING')
            text = text.replace(old, new); counts[old] = count
        if name != 'AndroidManifest.xml':
            for key, old in OLD.items():
                need(text.count(old) == 1, 'ORIGINAL_MAIN_LITERAL_NOT_UNIQUE:' + key)
                text = text.replace(old, values[key]); counts[key] = 1
        if name == 'qa_contract.py':
            needle = '10196, 10153, 10156)'
            need(text.count(needle) == 1, 'ORIGINAL_HELPER_UID_EXCLUSION_SET_CHANGED')
            text = text.replace(needle, '10196, 10153, 10156, 10158)', 1)
            counts['previous_actual_r4_helper_UID_excluded'] = 1
            # Reverse exactly the declared changes; every other AST node stays original.
            reverse = text.replace('10196, 10153, 10156, 10158)', needle)
            for key, old in OLD.items():
                reverse = reverse.replace(values[key], old)
            reverse = reverse.replace(SELF, OLD_SELF).replace(PROTOCOL, OLD_PROTOCOL)
            need(ast.dump(ast.parse(reverse), include_attributes=False) ==
                 ast.dump(ast.parse(raw), include_attributes=False), 'UNDECLARED_PYTHON_PROTOCOL_CHANGE')
        else:
            reverse = text
            for key, old in OLD.items():
                reverse = reverse.replace(values[key], old)
            reverse = reverse.replace(SELF, OLD_SELF).replace(PROTOCOL, OLD_PROTOCOL)
            need(reverse.encode() == raw, 'UNDECLARED_JAVA_OR_MANIFEST_CHANGE')
        output[name] = text.encode(); changes[name] = counts
    return output, changes


def create(common, request, output, source_packet_ref):
    need(os.getuid() == os.geteuid() == 0 and set(request) == {'baseline', 'qualification'},
         'EXPLICIT_ACTUAL_FINAL_MAIN_REFERENCES_REQUIRED')
    packet = common.parse(common.read_ref(source_packet_ref))
    need(packet['schema'] == 'pocket4-final-app-preparation-source-v1'
         and packet['Android_execution_authorized_by_publication'] is False,
         'FROZEN_PREPARATION_PACKET_REQUIRED')
    for row in packet['files'] + packet['origins']:
        common.read_ref(row)
    _, modules = common.support()
    baseline = modules['business_baseline.py'].BusinessBaseline(request['baseline'], request['qualification'])
    before = baseline.guard(); originals = {}
    for name, (size, digest) in ORIGINALS.items():
        relative = 'src/org/droidloom/qa/ihg/r4/ActionRunner.java' if name == 'ActionRunner.java' else name
        originals[name] = common.read_ref({'path': ORIGINAL_ROOT + '/' + relative,
                                          'bytes': size, 'sha256': digest})
    rendered, changes = render(originals, actual_values(baseline))
    root = Path(output)
    need(root.parent == common.FINAL / 'qualification' and
         re.fullmatch(r'business-ihg-helper-source-[0-9a-f]{32}', root.name),
         'NEW_HELPER_SOURCE_ROOT_REQUIRED')
    root = common.private_dir(root, create=True)
    result = {'schema': 'pocket4-final-ihg-helper-source-v1', 'state': 'SOURCE_GENERATED_ANDROID_UNRUN',
        **request, 'framework_epoch_sha256': baseline.value['framework_epoch']['sha256'],
        'package': SELF, 'protocol': PROTOCOL, 'target_package': 'com.ihg.apps.android', 'target_uid': 10137,
        'source_packet': source_packet_ref, 'declared_transformations': changes,
        'files': {}, 'APK': None, 'installed_UID': None, 'Android_UI_actions': 0,
        'old_runtime_authority_transferred': False, 'whole_app_business_accepted': False}
    for name, raw in rendered.items():
        result['files'][name] = common.write_new(root / name, raw, 0o400)
    for name in ('ihg_helper_build.py', 'ihg_helper_controls.py', 'ihg_session.py', 'app_runtime.py',
                 'ihg_check_baseline.py', 'ihg_check_input.py'):
        refs = [row for row in packet['files'] if Path(row['path']).name == name]
        need(len(refs) == 1, 'EXACT_GENERATED_HELPER_SUPPORT_SOURCE_REQUIRED:' + name)
        result['files'][name] = common.write_new(root / name, common.read_ref(refs[0]), 0o400)
    result['Main_before'] = before; result['Main_after'] = baseline.guard()
    need(result['Main_before'] == result['Main_after'], 'MAIN_CHANGED_DURING_SOURCE_CONSTRUCTION')
    for row in packet['files'] + packet['origins']:
        common.read_ref(row)
    return common.write_new(root / 'source.json', result, 0o400)
