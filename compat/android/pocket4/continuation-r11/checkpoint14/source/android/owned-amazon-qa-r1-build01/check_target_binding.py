#!/usr/bin/env python3
"""Local actual Python predicates; no build, child, namespace or Android action."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent


def load(name):
    path = HERE / 'source' / name
    module = types.ModuleType(name.replace('.', '_')); module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def main():
    qa, adapter, builder = (load(n) for n in ('qa_contract.py', 'qa_adapter.py', 'build_candidate.py'))
    rows = []

    def check(name, function, accepted):
        error = None
        try:
            function()
        except Exception as exc:
            error = {'type': type(exc).__name__, 'message': str(exc)}
        assert (error is None) == accepted, (name, error)
        rows.append({'case': name, 'accepted': error is None, 'expected_met': True, 'error': error})

    scope = {'package': qa.PACKAGE, 'uid': 10129, 'user': 0, 'display': 0,
             'activity': qa.PACKAGE + '/OwnedSyntheticActivity', 'window_token': 'aa11',
             'main_epoch_sha256': qa.MAIN_EPOCH}
    check('exact_Amazon_scope', lambda: qa.scope(dict(scope)), True)
    for name, key, value in (
        ('reject_Bili_package', 'package', 'tv.danmaku.bili'),
        ('reject_Bili_UID', 'uid', 10117),
        ('reject_other_display', 'display', 1),
        ('reject_other_Main_epoch', 'main_epoch_sha256', '0' * 64),
        ('reject_regex_wildcard_package', 'activity', 'comXamazonXmShopXandroidXshopping/OwnedSyntheticActivity'),
    ):
        check(name, lambda key=key, value=value: qa.scope({**scope, key: value}), False)
    request = {'protocol': qa.PROTOCOL, 'nonce': '1' * 32, 'op': 'set_text', 'scope': scope,
               'inspection_nonce': '2' * 32, 'inspection_sha256': '3' * 64,
               'node_path': '0/1', 'node_sha256': '4' * 64,
               'node_resource_id': qa.PACKAGE + ':id/owned_synthetic_search',
               'value': 'usb c cable'}
    check('exact_public_query_request_synthetic_resource', lambda: qa.validate_request(request), True)
    for name, key, value in (
        ('reject_Bili_edit_resource', 'node_resource_id', 'tv.danmaku.bili:id/search_src_text'),
        ('reject_other_text', 'value', 'not the fixed public query'),
        ('reject_old_protocol', 'protocol', 'pocket4-owned-bili-qa-v5'),
    ):
        check(name, lambda key=key, value=value: qa.validate_request({**request, key: value}), False)
    check('actual_XML_manifest_contract', builder.manifest_contract, True)
    check('standalone_legacy_flow_execution_always_denied', lambda: adapter.execute(None), False)

    source = HERE / 'source' / 'build_candidate.py'
    tree = ast.parse(source.read_bytes())
    require = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'require')
    build = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_once')
    reasons = {'actual self instrumentation target required', 'one exact actual instrumentation component required'}
    gates = {}
    for n in ast.walk(build):
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)):
            continue
        call = n.value
        if not (isinstance(call.func, ast.Name) and call.func.id == 'require' and len(call.args) == 2
                and isinstance(call.args[1], ast.Constant) and call.args[1].value in reasons):
            continue
        gates[call.args[1].value] = compile(ast.fix_missing_locations(
            ast.Module(body=[copy.deepcopy(require), copy.deepcopy(n)], type_ignores=[])), str(source), 'exec')
    assert set(gates) == reasons
    xml = (HERE / 'references' / 'actual-bili-r5-manifest.stdout').read_bytes()
    assert hashlib.sha256(xml).hexdigest() == '825a53459b0fc3406d328aad3350624f9b658b150a2fbf56f3a908f46de4185d'
    derived = xml.replace(b'org.droidloom.qa.bili.r5', b'org.droidloom.qa.amazon.r1')
    assert derived != xml
    for name, code in gates.items():
        check('actual_Bili_manifest_rejected:' + name,
              lambda code=code: exec(code, {'re': re, 'PACKAGE': builder.PACKAGE, 'xml': xml}), False)
        check('derived_Amazon_manifest_predicate:' + name,
              lambda code=code: exec(code, {'re': re, 'PACKAGE': builder.PACKAGE, 'xml': derived}), True)
    print(json.dumps({'schema': 1, 'state': 'PASS', 'controls': rows,
          'actual_Android_or_build_actions': 0,
          'synthetic': ['OwnedSyntheticActivity', 'owned_synthetic_search', 'Amazon XML derived only for actual Python gates'],
          'actual_manifest_reference_sha256': hashlib.sha256(xml).hexdigest(),
          'actual_Amazon_Javac_D8_APK_or_signer_qualification': False}, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
