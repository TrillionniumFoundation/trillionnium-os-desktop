#!/usr/bin/env python3
"""Bind all original full-runner gates to the complete current2359 source."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'current-runtime-cohort-20261120'
SOURCE = HERE.parent / 'current-runtime-successor-20261120'
PARENT_VERIFIER_SHA = 'd81a4160496ef388559a598ba24e9faa0807b0deafb1536f586ca5b98427ba20'
PARENT_RUNNER_SHA = 'd21fd07e788614e2200ac5c73b3cc9a6a3207fa285d448f043bf99e1828f80ae'
PARENT_INVENTORY = '9c1c330bd29ea6d2bdbcde0ead6e27bafaaab07177fb22a6f90ef81c967466a2'
PARENT_TREE = '7bfb70d7107cb5c95e9aec307124e1369aa735d1'
SOURCE_INVENTORY = '62a7b8182ac751f9e0f104fdf1a2fda4865a82acdbc78ff899f219bbd0cd8a29'
SOURCE_VERIFIER_SHA = 'e6a14326b1aa1ccc17d606c60bfc9bdf525f47bb2ccafffc86a054c55dd06219'
HEAD_TREE = '4d78aae1aba2ec9952c37153069cca85c5a87953'
HEAD_COMMIT = None
PARENT_COMMIT = None
SOURCE_FILES = 2359
SOURCE_BYTES = 44737433
SOURCE_CHAIN = {'current_tree': '4d78aae1aba2ec9952c37153069cca85c5a87953', 'leaf_inventory_sha256': 'b932f58f5a3eaf7feea4d458fbd67d2e248a29a5aeb45eb940c6f2c7450f6374', 'materialization_inventory_sha256': 'ea75a0a28022944b80acebb65aca9ce49c9c66fbd519531da7677bbd114ed35e', 'materialization_tree': '454a50a52837f80a50d39815da91b0c8cd7a1e4c', 'original_inventory_sha256': '075affecd123cc60e30eadf70ae95cc9ec34d5686694bedf0914014c36d04c0b', 'original_tree': '64f57a4de88053fea58cfa5112cd089e45b20be6', 'parent_current_tree': '7bfb70d7107cb5c95e9aec307124e1369aa735d1', 'parent_cohort_inventory_sha256': '9c1c330bd29ea6d2bdbcde0ead6e27bafaaab07177fb22a6f90ef81c967466a2', 'combined_source_inventory_sha256': '62a7b8182ac751f9e0f104fdf1a2fda4865a82acdbc78ff899f219bbd0cd8a29'}
EXPECTED_ADDITIONS = [{'component': 'image_custody', 'package': 'droidloom-applications', 'target': 'droidloom_applications', 'tests': ['runtime_plan::image_custody_consumer_tests::consumer_rejects_a_different_actual_package_or_user', 'runtime_plan::image_custody_consumer_tests::gallery_legacy_metadata_cannot_substitute_for_the_owned_image_producer', 'runtime_plan::image_custody_consumer_tests::unchanged_non_gallery_identity_shape_remains_available']}, {'component': 'lint', 'package': 'droidloom-source', 'target': 'droidloom-source', 'tests': ['tests::source_cli_requires_explicit_complete_healthfitness_lint_profile']}, {'component': 'lint', 'package': 'droidloom-source', 'target': 'droidloom_source', 'tests': ['production_lint::tests::lint_operations_reject_incomplete_scope_before_any_source_io', 'production_lint::tests::lint_profile_extends_only_the_complete_original_lint_directory', 'production_lint::tests::lint_profile_rejects_partial_provider_repin_and_wrong_project', 'production_lint::tests::lint_profile_rejects_unrelated_projects_metadata_and_policy_changes', 'production_lint::tests::lint_verification_never_rewrites_the_original_cmake_manifest']}, {'component': 'image_custody', 'package': 'droidloom-supervisor', 'target': 'droidloom_supervisor', 'tests': ['control::application_custody::tests::complete_wire_model_is_coherent_without_granting_live_custody', 'control::application_custody::tests::current_owner_and_all_original_namespaces_are_bound', 'control::application_custody::tests::custody_wire_rejects_an_added_authority_field', 'control::application_custody::tests::missing_reordered_or_unreaped_commands_do_not_replay_as_observations', 'control::application_custody::tests::optional_response_preserves_legacy_wire_but_request_cannot_import_custody', 'control::application_custody::tests::whole_image_and_same_inode_are_required_even_with_matching_apk_hash', 'control::application_custody::tests::wire_observation_cannot_promote_data_or_release_gates', 'control::progress::tests::complete_three_mib_response_uses_the_unchanged_four_mib_bound', 'control::progress::tests::only_exact_user_zero_gallery_inspection_gets_the_longer_response_wait', 'production_application::custody::tests::image_gallery_never_adopts_an_installed_replacement', 'production_application::custody::tests::image_gallery_query_scope_keeps_the_existing_finite_read_boundary']}, {'component': 'lint', 'package': 'droidloom-update', 'target': 'droidloom-update', 'tests': ['android::production_source::tests::original_cmake_manifest_requires_explicit_complete_lint_reconciliation']}]
UNCHANGED_METADATA = ('EXPECTED-TARGETS.json', 'EXPECTED-BINS.json', 'EXTRA-TARGETS.json', 'UPDATER-EXACT64.json', 'test_runner.py')


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


_parent_raw = _bootstrap(PARENT / 'verify.py', PARENT_VERIFIER_SHA)
_spec = importlib.util.spec_from_file_location('current2359_parent_cohort_verifier', PARENT / 'verify.py')
PARENT_SOURCE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PARENT_SOURCE)
if _bootstrap(PARENT / 'verify.py', PARENT_VERIFIER_SHA) != _parent_raw:
    raise RuntimeError('complete parent verifier changed during import')

BASE = PARENT_SOURCE.BASE
decode = PARENT_SOURCE.decode
digest = PARENT_SOURCE.digest
f9 = PARENT_SOURCE.f9
need = PARENT_SOURCE.need
regular = PARENT_SOURCE.regular
safe = PARENT_SOURCE.safe
source_snapshot = PARENT_SOURCE.source_snapshot
successful_cargo_stream = PARENT_SOURCE.successful_cargo_stream
test_terminal = PARENT_SOURCE.test_terminal
OVERLAY = PARENT_SOURCE.OVERLAY


def fresh_destination(path, protected):
    return PARENT_SOURCE.fresh_destination(path, [*protected, PARENT, SOURCE])


def write_report(path, value, protected):
    return PARENT_SOURCE.write_report(path, value, [*protected, PARENT, SOURCE])


def current_catalog(parent, additions):
    need(isinstance(parent, list) and len(parent) == 49, 'all49 parent targets are required')
    mapped = {}
    for row in parent:
        need(set(row) == {'package', 'target', 'all', 'ignored'}, 'exact complete parent catalog fields required')
        key = (row['package'], row['target'])
        need(key not in mapped and row['all'] == sorted(set(row['all']))
             and row['ignored'] == sorted(set(row['ignored'])) and set(row['ignored']) <= set(row['all']),
             'distinct complete parent catalog required')
        mapped[key] = dict(row, all=list(row['all']), ignored=list(row['ignored']))
    need(sum(len(r['all']) for r in parent) == 1564 and sum(len(r['ignored']) for r in parent) == 30,
         'the complete1534 ordinary/30 ignored parent is required')
    exact_parent = decode(regular(PARENT / 'EXPECTED-CATALOG.json'))
    need(parent == exact_parent, 'an original target, case or ignored identity changed')
    need(additions == EXPECTED_ADDITIONS, 'only the21 reviewed source-declared new cases may be added')
    seen = set()
    for row in additions:
        need(set(row) == {'component', 'package', 'target', 'tests'}, 'exact new source catalog fields required')
        key = (row['package'], row['target'])
        need(key in mapped and key not in seen and row['tests'] == sorted(set(row['tests']))
             and not set(row['tests']).intersection(mapped[key]['all']), 'distinct additive cases on original targets required')
        seen.add(key)
        mapped[key]['all'] = sorted(mapped[key]['all'] + row['tests'])
    result = [mapped[(r['package'], r['target'])] for r in parent]
    need(sum(len(r['all']) for r in result) == 1585 and sum(len(r['ignored']) for r in result) == 30,
         'complete1555 ordinary/30 unchanged ignored catalog required')
    return result


def verify_packet(expected_inventory_sha):
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory_sha), 'external current cohort inventory SHA required')
    index = regular(HERE / 'FILES.sha256', 65536)
    need(hashlib.sha256(index).hexdigest() == expected_inventory_sha, 'external current cohort packet pin differs')
    inventory = {}
    for line in index.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        need(match and match[2] not in inventory and match[2] != 'FILES.sha256', 'distinct exact cohort packet member required')
        inventory[match[2]] = match[1]
    names, _ = BASE.member_names(HERE)
    need(names == set(inventory) | {'FILES.sha256'}, 'complete successor cohort packet membership differs')
    for name, expected in inventory.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == expected, 'cohort member differs: ' + name)
    manifest = decode(regular(HERE / 'MANIFEST.json'))
    need(manifest['schema'] == 'p4-current2359-full-cohort-source-v1'
         and manifest['source_chain'] == SOURCE_CHAIN
         and manifest['source'] == {'tree': HEAD_TREE, 'files': SOURCE_FILES, 'bytes': SOURCE_BYTES}
         and manifest['required'] == {'packages': 28, 'targets': 49, 'ordinary': 1555, 'ignored_not_run': 30,
                                     'catalog': 1585, 'release_binaries': 19, 'example_binaries': 3,
                                     'recipe_tests': 9, 'doc_targets': 20}
         and manifest['new_cases_source_declared_until_actual_compiled_catalog'] is True
         and manifest['fresh_current_rust_run_in_this_packet'] is False
         and manifest['production_ready'] is False and manifest['runtime_qualified'] is False,
         'complete current source and every original full-cohort gate are required')
    need(hashlib.sha256(regular(PARENT / 'run_ci.py')).hexdigest() == PARENT_RUNNER_SHA,
         'complete original current runner source required')
    for name in UNCHANGED_METADATA:
        need(regular(HERE / name) == regular(PARENT / name), 'original target/example/control source changed: ' + name)
    need(decode(regular(HERE / 'NEW-TESTS.json')) == EXPECTED_ADDITIONS, 'reviewed21-case source delta differs')
    return manifest


def verify_capsule(expected_inventory_sha):
    """Keep the original full runner interface and require the closed new source."""
    manifest = verify_packet(expected_inventory_sha)
    parent = PARENT_SOURCE.verify_capsule(PARENT_INVENTORY)
    need(PARENT_SOURCE.HEAD_TREE == PARENT_TREE and parent['rows'] == decode(regular(SOURCE / 'PARENT-SOURCE-ROWS.json')),
         'the complete original2352 source parent differs')
    raw = _bootstrap(SOURCE / 'verify.py', SOURCE_VERIFIER_SHA)
    spec = importlib.util.spec_from_file_location('current_combined_source_verifier', SOURCE / 'verify.py')
    source = importlib.util.module_from_spec(spec); spec.loader.exec_module(source)
    need(_bootstrap(SOURCE / 'verify.py', SOURCE_VERIFIER_SHA) == raw, 'combined source verifier changed during import')
    packet = source.verify_packet(SOURCE_INVENTORY)
    need(packet['before'] == parent['rows']
         and packet['manifest']['successor'] == {'source_tree': HEAD_TREE, 'source_files': SOURCE_FILES,
                                               'source_bytes': SOURCE_BYTES},
         'complete current combined producer source required')
    expected = current_catalog(decode(regular(PARENT / 'EXPECTED-CATALOG.json')),
                               decode(regular(HERE / 'NEW-TESTS.json')))
    need(decode(regular(HERE / 'EXPECTED-CATALOG.json')) == expected, 'current exact49-target catalog differs')
    replay = source.strict_patch(regular(PARENT / 'run_ci.py'), regular(HERE / 'RUNNER.patch'), 'run_ci.py')
    need(replay == regular(HERE / 'run_ci.py'), 'current runner is not its exact authenticated parent patch replay')
    before_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(regular(PARENT / 'run_ci.py')).body
                        if isinstance(n, ast.FunctionDef)}
    after_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(replay).body
                       if isinstance(n, ast.FunctionDef)}
    need(set(before_functions) == set(after_functions)
         and all(before_functions[name] == after_functions[name] for name in before_functions
                 if name not in ('configuration', 'main')), 'an original shared runner gate changed')
    unchanged_module = lambda body: [ast.dump(node, include_attributes=False) for node in ast.parse(body).body
                                    if not (isinstance(node, ast.FunctionDef) and node.name in ('configuration', 'main'))]
    need(unchanged_module(regular(PARENT / 'run_ci.py')) == unchanged_module(replay),
         'an original runner import, constant or module entry changed')
    verify_packet(expected_inventory_sha)
    return {'rows': packet['after'], 'source_chain': SOURCE_CHAIN,
            'source_packet_snapshot': packet['packet_snapshot'],
            'inventory_sha256': expected_inventory_sha, 'manifest': manifest}
