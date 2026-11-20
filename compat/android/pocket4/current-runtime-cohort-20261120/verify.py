#!/usr/bin/env python3
"""Bind the unchanged full runner gates to the complete current source chain."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / 'runtime-current-source-r1'
MATERIALIZATION = HERE.parent / 'vendor-source-materialization-20261120' / 'rust'
LEAF = HERE.parent / 'current-leaf-selection-20261120' / 'rust'
ORIGINAL_VERIFIER_SHA = '0a669e373aca985a7b3f86b4d5f02782e38fac57ebe098738692897eebf7f0e1'
ORIGINAL_RUNNER_SHA = '8daf16a61dcdf410088e595f858801e9af1aa40de0f123e76a1f5206136ad488'
ORIGINAL_INVENTORY = '075affecd123cc60e30eadf70ae95cc9ec34d5686694bedf0914014c36d04c0b'
MATERIALIZATION_INVENTORY = 'ea75a0a28022944b80acebb65aca9ce49c9c66fbd519531da7677bbd114ed35e'
LEAF_INVENTORY = 'b932f58f5a3eaf7feea4d458fbd67d2e248a29a5aeb45eb940c6f2c7450f6374'
LEAF_VERIFIER_SHA = '017c3fa3899f7bc2c1836f1fd748aa333387d3d48d56f9493c87907770b68aef'
HEAD_TREE = '7bfb70d7107cb5c95e9aec307124e1369aa735d1'
HEAD_COMMIT = None
PARENT_COMMIT = None
SOURCE_FILES = 2352
SOURCE_BYTES = 44260146
SOURCE_CHAIN = {'original_inventory_sha256': ORIGINAL_INVENTORY,
                'materialization_inventory_sha256': MATERIALIZATION_INVENTORY,
                'leaf_inventory_sha256': LEAF_INVENTORY,
                'original_tree': '64f57a4de88053fea58cfa5112cd089e45b20be6',
                'materialization_tree': '454a50a52837f80a50d39815da91b0c8cd7a1e4c',
                'current_tree': HEAD_TREE}
UNCHANGED_METADATA = ('EXPECTED-TARGETS.json', 'EXPECTED-BINS.json',
                      'EXTRA-TARGETS.json', 'UPDATER-EXACT64.json', 'test_runner.py')


def _bootstrap(path, expected_sha):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise RuntimeError('canonical original verifier required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= 65536:
            raise RuntimeError('bounded ordinary verifier required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(before.st_size + 1)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                                  value.st_gid, value.st_nlink, value.st_size,
                                  value.st_mtime_ns, value.st_ctime_ns)
        if (identity(before) != identity(os.fstat(fd)) or identity(before) != identity(path.lstat())
                or len(raw) != before.st_size or hashlib.sha256(raw).hexdigest() != expected_sha):
            raise RuntimeError('complete original verifier changed')
    finally:
        os.close(fd)
    return raw


_original_raw = _bootstrap(ORIGINAL / 'verify.py', ORIGINAL_VERIFIER_SHA)
_spec = importlib.util.spec_from_file_location('current_cohort_original_verifier', ORIGINAL / 'verify.py')
BASE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BASE)
if _bootstrap(ORIGINAL / 'verify.py', ORIGINAL_VERIFIER_SHA) != _original_raw:
    raise RuntimeError('original verifier changed during import')

# Explicitly reuse the original gate implementations. No generic proxy or
# replacement test/artifact parser is introduced by this source adapter.
decode = BASE.decode
digest = BASE.digest
f9 = BASE.f9
need = BASE.need
regular = BASE.regular
safe = BASE.safe
source_snapshot = BASE.source_snapshot
successful_cargo_stream = BASE.successful_cargo_stream
test_terminal = BASE.test_terminal
OVERLAY = BASE.OVERLAY


def fresh_destination(path, protected):
    return BASE.fresh_destination(path, [*protected, ORIGINAL, MATERIALIZATION, LEAF])


def write_report(path, value, protected):
    return BASE.write_report(path, value, [*protected, ORIGINAL, MATERIALIZATION, LEAF])


def current_catalog(original, source_cases, app_cases, extras):
    need(isinstance(original, list) and len(original) == 49, 'all49 original catalog targets required')
    mapped = {}
    for row in original:
        need(set(row) == {'package', 'target', 'all', 'ignored'}, 'exact original catalog fields required')
        key = (row['package'], row['target'])
        need(key not in mapped and row['all'] == sorted(set(row['all']))
             and row['ignored'] == sorted(set(row['ignored'])) and set(row['ignored']) <= set(row['all']),
             'distinct complete original catalog required')
        mapped[key] = dict(row, all=list(row['all']), ignored=list(row['ignored']))
    need(sum(len(r['all']) for r in original) == 1553 and sum(len(r['ignored']) for r in original) == 30,
         'exact historical1523 ordinary/30 ignored baseline required')
    changed, seen = {}, set()
    for package, cases in [('droidloom-source', source_cases), ('droidloom-applications', app_cases)]:
        for current in cases:
            need(set(current) == {'kind', 'target', 'tests', 'ignored'}, 'exact compiled current target catalog required')
            key = (package, current['target'])
            need(key not in seen, 'duplicate current catalog target')
            seen.add(key)
            if current['kind'] == 'example':
                recipe = extras['example_test']
                need(package == recipe['package'] and current['target'] == recipe['target']
                     and current['tests'] == recipe['tests'] and current['ignored'] == [],
                     'the original nine recipe cases must stay unchanged')
                continue
            need(key in mapped and current['kind'] in ('lib', 'bin'), 'unrequested current target added')
            old = mapped[key]
            need(current['tests'] == sorted(set(current['tests'])) and old['ignored'] == current['ignored']
                 and set(old['all']) <= set(current['tests']), 'old cases or ignored identities changed')
            added = sorted(set(current['tests']) - set(old['all']))
            if added:
                changed[key] = added
            old['all'] = list(current['tests'])
    need(seen == {('droidloom-source', 'droidloom_source'), ('droidloom-source', 'droidloom-source'),
                  ('droidloom-source', 'frozen_pair_recipe'),
                  ('droidloom-applications', 'droidloom_applications'),
                  ('droidloom-applications', 'droidloom-applications')},
         'complete two affected crate catalogs and the original example required')
    need(set(changed) == {('droidloom-source', 'droidloom_source'),
                         ('droidloom-applications', 'droidloom_applications')}
         and len(changed[('droidloom-source', 'droidloom_source')]) == 6
         and len(changed[('droidloom-applications', 'droidloom_applications')]) == 5,
         'only the11 actually compiled current source/application additions are permitted')
    result = [mapped[(row['package'], row['target'])] for row in original]
    need(sum(len(r['all']) for r in result) == 1564 and sum(len(r['ignored']) for r in result) == 30,
         'complete current1534 ordinary/30 unchanged ignored catalog required')
    return result


def verify_packet(expected_inventory_sha):
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory_sha), 'external cohort inventory SHA required')
    index = regular(HERE / 'FILES.sha256', 65536)
    need(hashlib.sha256(index).hexdigest() == expected_inventory_sha, 'external current cohort packet pin differs')
    inventory = {}
    for line in index.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        need(match and match[2] not in inventory and match[2] != 'FILES.sha256', 'distinct exact cohort packet member')
        inventory[match[2]] = match[1]
    names, _ = BASE.member_names(HERE)
    need(names == set(inventory) | {'FILES.sha256'}, 'complete cohort packet membership differs')
    for name, expected in inventory.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == expected, 'cohort member differs: ' + name)
    manifest = decode(regular(HERE / 'MANIFEST.json'))
    need(manifest['schema'] == 'p4-current2352-full-cohort-source-v1'
         and manifest['source_chain'] == SOURCE_CHAIN
         and manifest['source'] == {'tree': HEAD_TREE, 'files': SOURCE_FILES, 'bytes': SOURCE_BYTES}
         and manifest['required'] == {'packages': 28, 'targets': 49, 'ordinary': 1534, 'ignored_not_run': 30,
                                     'catalog': 1564, 'release_binaries': 19, 'example_binaries': 3,
                                     'recipe_tests': 9, 'doc_targets': 20},
         'complete current source and original full-cohort gates required')
    need(hashlib.sha256(regular(ORIGINAL / 'run_ci.py')).hexdigest() == ORIGINAL_RUNNER_SHA,
         'complete original runner source required')
    for name in UNCHANGED_METADATA:
        need(regular(HERE / name) == regular(ORIGINAL / name), 'original target/example/control source changed: ' + name)
    return manifest


def verify_capsule(expected_inventory_sha):
    """Keep the original runner interface while authenticating the entire chain."""
    manifest = verify_packet(expected_inventory_sha)
    original = BASE.verify_capsule(ORIGINAL_INVENTORY)
    need(BASE.tree_id(original['rows']) == SOURCE_CHAIN['original_tree'], 'original complete source tree differs')
    leaf_raw = regular(LEAF / 'verify.py')
    need(hashlib.sha256(leaf_raw).hexdigest() == LEAF_VERIFIER_SHA, 'fixed current source verifier required')
    spec = importlib.util.spec_from_file_location('current_cohort_leaf_verifier', LEAF / 'verify.py')
    leaf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(leaf)
    need(regular(LEAF / 'verify.py') == leaf_raw, 'current verifier changed during import')
    packet = leaf.verify_packet(LEAF_INVENTORY)
    materialization = leaf.verify_parent_packet(MATERIALIZATION, packet)
    need(materialization['before'] == original['rows'], 'materialization original source differs from complete capsule')
    need(packet['manifest']['successor'] == {'source_tree': HEAD_TREE, 'source_files': SOURCE_FILES,
                                          'source_bytes': SOURCE_BYTES}, 'complete2352 current source required')
    expected = current_catalog(decode(regular(ORIGINAL / 'EXPECTED-CATALOG.json')),
                               decode(regular(MATERIALIZATION / 'EXPECTED-CATALOG.json')),
                               decode(regular(LEAF / 'EXPECTED-CATALOG.json')),
                               decode(regular(HERE / 'EXTRA-TARGETS.json')))
    need(decode(regular(HERE / 'EXPECTED-CATALOG.json')) == expected, 'current exact49-target catalog differs')
    replay = leaf.strict_patch(regular(ORIGINAL / 'run_ci.py'), regular(HERE / 'RUNNER.patch'), 'run_ci.py')
    need(replay == regular(HERE / 'run_ci.py'), 'current runner is not the exact original-source patch replay')
    before_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(regular(ORIGINAL / 'run_ci.py')).body
                        if isinstance(n, ast.FunctionDef)}
    after_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(replay).body
                       if isinstance(n, ast.FunctionDef)}
    need(set(before_functions) == set(after_functions)
         and all(before_functions[name] == after_functions[name] for name in before_functions
                 if name not in ('configuration', 'main')), 'an original shared runner gate changed')
    unchanged_module = lambda body: [ast.dump(node, include_attributes=False) for node in ast.parse(body).body
                                    if not (isinstance(node, ast.FunctionDef)
                                            and node.name in ('configuration', 'main'))]
    need(unchanged_module(regular(ORIGINAL / 'run_ci.py')) == unchanged_module(replay),
         'an original runner import, constant or module entry changed')
    verify_packet(expected_inventory_sha)
    return {'rows': packet['after'], 'source_chain': SOURCE_CHAIN,
            'inventory_sha256': expected_inventory_sha, 'manifest': manifest}
