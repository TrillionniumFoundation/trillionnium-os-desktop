#!/usr/bin/python3
"""Prepare only independent source candidates; never access the vendor host."""
from pathlib import Path
import ast
import hashlib
import json

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'r23-preparation'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    old = (PREVIOUS / 'source-r23.py').read_bytes()
    need((len(old), hashlib.sha256(old).hexdigest()) ==
         (335019, '19f730767efb1afd3e065093f389e02c8ddfa41e62c19aa89e97574e6ff3dff8'),
         'exact actually frozen original R23 worker')
    old_outer = (PREVIOUS / 'outer-r23.py').read_bytes()
    need((len(old_outer), hashlib.sha256(old_outer).hexdigest()) ==
         (35232, '915355af4fce7ca741acb021d10c81ea252e6f76064ef051f0c1d89bbb130e36'),
         'exact actually executed original R23 outer')
    text = old.decode(); tree = ast.parse(text); lines = text.splitlines(keepends=True)
    guards = [x for x in tree.body if isinstance(x, ast.If)
              and ast.unparse(x.test) == "__name__ == '__main__'"]
    need(len(guards) == 1, 'single unchanged original main guard')
    main_guard = guards[0]
    prefix, suffix = ''.join(lines[:main_guard.lineno-1]), ''.join(lines[main_guard.lineno-1:])
    original = {x.name: x for x in tree.body if isinstance(x, ast.FunctionDef)}
    def source(name):
        node = original[name]
        return ''.join(lines[node.lineno-1:node.end_lineno])
    verify = source('verify_serialized_retirement')
    anchor = "        successor = r23_successor_extra_admission()\n        return {'actual_R22_continuation': successor,"
    replacement = "        successor = r23_successor_extra_admission()\n        successor24 = r24_successor_extra_admission()\n        return {'actual_R23_continuation': successor24, 'actual_R22_continuation': successor,"
    need(verify.count(anchor) == 1, 'single original in-deadline continuation anchor')
    verify = verify.replace(anchor, replacement)
    retirement = source('r20_recovery_retirement')
    need(retirement.count('p4-r23-original-build-retirement-before-recovery-v1') == 1,
         'only current R23 retirement schema')
    retirement = retirement.replace('p4-r23-original-build-retirement-before-recovery-v1',
                                    'p4-r24-original-build-retirement-before-recovery-v1')
    fragment = (HERE / 'R24-BOOTSTRAP-ADMISSION.py').read_text()
    candidate = prefix + '\n' + fragment + '\n\n' + verify + '\n\n' + retirement + '\n\nr24_bootstrap()\n\n' + suffix
    need(candidate.startswith(prefix) and candidate.endswith(suffix), 'complete original R23 prefix and main')
    ast_new = ast.parse(candidate)
    newer = {x.name: x for x in ast_new.body if isinstance(x, ast.FunctionDef)}
    changed = [n for n in original if ast.dump(original[n], include_attributes=False)
               != ast.dump(newer[n], include_attributes=False)]
    need(sorted(changed) == ['r20_recovery_retirement', 'verify_serialized_retirement'],
         'all other original definitions unchanged')
    outer_anchor = b"BUNDLE_SHA = '4cb03fae174dd725689f470b6c9d56badfe492dbc36203d59cb85b3c6c0634ca'"
    need(old_outer.count(outer_anchor) == 1, 'exact original bundle pin anchor')
    outer = old_outer.replace(outer_anchor, b"BUNDLE_SHA = 'UNFROZEN_SOURCE_ONLY'")
    outer = outer.replace(b'r23', b'r24').replace(b'R23', b'R24')
    reverse = outer.replace(b'r24', b'r23').replace(b'R24', b'R23')
    reverse = reverse.replace(b"BUNDLE_SHA = 'UNFROZEN_SOURCE_ONLY'", outer_anchor)
    need(reverse == old_outer, 'no outer resource, runner, deadline, lock or recovery change')
    compile(candidate, 'source-r24-template.py', 'exec')
    compile(outer, 'outer-r24-template.py', 'exec')
    with (HERE / 'source-r24-template.py').open('x') as output:
        output.write(candidate)
    with (HERE / 'outer-r24-template.py').open('xb') as output:
        output.write(outer)
    result = {'schema': 'p4-r24-source-conservation-v1',
        'source_base': pin(PREVIOUS / 'source-r23.py'),
        'source': pin(HERE / 'source-r24-template.py'),
        'outer': pin(HERE / 'outer-r24-template.py'),
        'entire_frozen_R23_prefix_and_main_bytes_preserved': True,
        'original_R22_R23_history_names_and_bytes_preserved': True,
        'existing_function_count': len(original), 'changed_existing_definitions': changed,
        'all_other_existing_definitions_AST_identical': True,
        'original_admission_only_adds_one_call_and_one_return_field': True,
        'same_original_absolute_150_second_deadline': True,
        'outer_only_current_generation_literals_and_unfrozen_bundle_pin_changed': True,
        'one_explicit_never_materialized_R23_lock_declaration_reclassified': True,
        'actual_historical_input_deleted': False,
        'external_resource_preflight_grants_admission': False,
        'host_execution': False, 'build_started': False,
        'runtime_qualified': False, 'production_ready': False}
    with (HERE / 'SOURCE-CONSERVATION.json').open('x') as output:
        json.dump(result, output, sort_keys=True, indent=2); output.write('\n')
    print(json.dumps({'source': result['source'], 'outer': result['outer'],
                      'conservation': pin(HERE / 'SOURCE-CONSERVATION.json')}))


if __name__ == '__main__':
    main()
