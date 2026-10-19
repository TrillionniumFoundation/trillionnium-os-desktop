#!/usr/bin/env python3
"""Read fixed A06 evidence; apply declared diffs only to disposable text copies."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import ast
import hashlib
import importlib.util
import json
import lzma
import os
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
HEAD = '4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930'
TREE = '8eb809136a402cc54ba049b1e40dd174308c923f'
ZIP_SHA = 'ef5d93159c1663fb30d3cf8e39e969525bbfa03b4fedc4db10ef4c87b035d655'
REPO = ROOT.parents[1] / 'r11-g1b-usage'
OUT = ROOT / 'negative-independent-review'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def tree_hash(files):
    root = {}
    for path, row in files.items():
        node = root
        parts = path.split('/')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        assert parts[-1] not in node
        node[parts[-1]] = (row['mode'], row['git_blob'])

    def digest(node):
        pieces = []
        for name, value in sorted(node.items(), key=lambda kv: kv[0].encode() + (b'/' if isinstance(kv[1], dict) else b'')):
            mode, value_hash = ('40000', digest(value)) if isinstance(value, dict) else value
            pieces.append(mode.encode() + b' ' + name.encode() + b'\0' + bytes.fromhex(value_hash))
        data = b''.join(pieces)
        return hashlib.sha1(b'tree ' + str(len(data)).encode() + b'\0' + data).hexdigest()

    return digest(root)


def read_control_constants(source):
    """Evaluate only immutable data expressions; never import the product runner."""
    values = {'PATCH_NAME': 'cpu_owner_current_slot_negative.patch'}
    wanted = {'PATCH_SHA', 'CPU_PATH', 'SCHED_PATH', 'CLOCK_PATH', 'VDSO_PATH', 'PREFIX',
              'FAILED_NAMES', 'CLOCK_PREFIX', 'HANDOFF_PREFIX', 'USAGE_PREFIX', 'HANDOFF_NAMES', 'CONTROLS'}

    def value(node, local):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return local[node.id]
        if isinstance(node, ast.Attribute):
            assert isinstance(node.value, ast.Name) and node.value.id == 'PATCH' and node.attr == 'name'
            return local['PATCH_NAME']
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            items = [value(item, local) for item in node.elts]
            return tuple(items) if isinstance(node, ast.Tuple) else set(items) if isinstance(node, ast.Set) else items
        if isinstance(node, ast.Dict):
            return {value(k, local): value(v, local) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.BinOp):
            left, right = value(node.left, local), value(node.right, local)
            if isinstance(node.op, ast.Add):
                return left + right
            assert isinstance(node.op, ast.BitOr)
            return left | right
        if isinstance(node, ast.Subscript):
            return value(node.value, local)[value(node.slice, local)]
        if isinstance(node, ast.Slice):
            return slice(*(value(part, local) if part is not None else None for part in [node.lower, node.upper, node.step]))
        if isinstance(node, ast.SetComp):
            assert len(node.generators) == 1
            gen = node.generators[0]
            assert isinstance(gen.target, ast.Name) and not gen.ifs and not gen.is_async
            return {value(node.elt, dict(local, **{gen.target.id: item})) for item in value(gen.iter, local)}
        raise ValueError('Unsupported data expression: ' + type(node).__name__)

    for statement in ast.parse(source).body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            name = statement.targets[0].id
            if name in wanted:
                values[name] = value(statement.value, values)
    assert wanted <= values.keys()
    assert list(values['CONTROLS']) == ['owner-current-slot', 'clocksource-drop-fraction', 'vdso-drop-fraction', 'vdso-skip-fault-mode', 'handoff-drop-tail', 'handoff-eligibility-first', 'dequeue-drop-owner']
    assert [len(row[3]) for row in values['CONTROLS'].values()] == [3, 4, 3, 1, 4, 1, 2]
    return values


def main():
    started = datetime.now(timezone.utc).isoformat()
    OUT.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('independent_green_parser', ROOT / 'review-green-archive.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    source_raw = (ROOT / 'source-git-map.json').read_bytes()
    source = json.loads(source_raw)
    assert (source['head'], source['tree']) == (HEAD, TREE) and len(source['files']) == 7054
    assert tree_hash(source['files']) == TREE
    runner_path = 'tests/organ_backend/run_cpu_owner_negative.py'
    runner_raw = (ROOT / 'fixed-source' / runner_path).read_bytes()
    assert sha(runner_raw) == source['files'][runner_path]['sha256']
    constants = read_control_constants(runner_raw.decode())
    usage_path = 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native/usage_tests.rs'
    usage_raw = (ROOT / 'fixed-source' / usage_path).read_bytes()
    assert sha(usage_raw) == source['files'][usage_path]['sha256']
    usage_names = [constants['USAGE_PREFIX'] + name for name in re.findall(r'#\[ktest\]\s*fn\s+(\w+)\s*\(', usage_raw.decode())]
    assert len(usage_names) == len(set(usage_names)) == 19
    green_review_raw = (ROOT / 'green-independent-review/review.json').read_bytes()
    green_review = json.loads(green_review_raw)
    assert (green_review['head'], green_review['tree'], green_review['archive']['sha256']) == (HEAD, TREE, ZIP_SHA)
    green_core = next(crate for crate in green_review['crates'] if crate['crate'] == 'aster-core')
    green_names = {test['name'] for test in green_core['tests']}
    assert len(green_names) == 220 and set(usage_names) <= green_names
    assert all(test['outcome'] == 'ok' and not test['soft_skip_reasons'] for test in green_core['tests'])
    old_path = ROOT.parent / 'pr203-restored-artifact/green-independent-review/review.json'
    old_raw = old_path.read_bytes()
    assert sha(old_raw) == '02fe47643e57a0c6677d64a1fc0f90f2e5b84b3ae7b3b6f197a1529bdf9d4e3d'
    old = json.loads(old_raw)
    old_names = {test['name'] for crate in old['crates'] if crate['crate'] == 'aster-core' for test in crate['tests']}
    assert len(old_names) == 201 and old_names.isdisjoint(usage_names) and old_names | set(usage_names) == green_names
    records, selected, controls, elf_records = {}, [], [], []
    with (ROOT / 'original.zip').open('rb') as handle:
        archive_sha, archive_bytes, _ = helper.stream_sha(handle)
    assert (archive_sha, archive_bytes) == (ZIP_SHA, 154979607)
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
    with zipfile.ZipFile(ROOT / 'original.zip') as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        assert len(names) == len(set(names)) == 1172
        assert all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name for name in names)
        assert archive.testzip() is None

        def read(name, retain=False):
            info = archive.getinfo(name)
            assert info.file_size <= 16 * 1024 * 1024
            data = archive.read(name)
            assert len(data) == info.file_size
            row = {'archive_member': name, 'bytes': len(data), 'sha256': sha(data)}
            if name in records:
                assert records[name] == row
            records[name] = row
            if retain:
                path = OUT / 'selected' / (name + '.xz')
                path.parent.mkdir(parents=True, exist_ok=True)
                packed = lzma.compress(data, preset=6)
                assert lzma.decompress(packed) == data
                path.write_bytes(packed)
                selected.append({'path': str(path.relative_to(OUT)), 'bytes': len(packed), 'sha256': sha(packed), 'original': row})
            return data

        def obj(name, retain=False):
            return json.loads(read(name, retain))

        def kernel(name, expected_hash, expected_size, role):
            with archive.open(name) as handle:
                actual_hash, actual_size, header = helper.stream_sha(handle)
            assert (actual_hash, actual_size) == (expected_hash, expected_size)
            assert header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x03\x00'
            elf_records.append({'archive_member': name, 'sha256': actual_hash, 'bytes': actual_size, 'role': role, 'elf_class': 64, 'e_machine': 3, 'elf_note': 'OSDK x86_64 QEMU multiboot marker; not an i386 product claim.'})

        green_env = obj('_temp/a06-ktest/environment.json', True)
        assert green_env['git_head'] == HEAD and green_env['git_status'] == '' and green_env['test_name'] is None
        assert green_env['toolchain'] == 'nightly-2026-07-21'
        assert all(source['files'][p]['sha256'] == digest for p, digest in green_env['build_inputs_sha256'].items())
        green_inputs = obj('_temp/a06-ktest/source-inputs.json', True)
        assert green_inputs['passed'] and not green_inputs['errors']
        assert all(source['files']['kernel/asterinas/' + p]['sha256'] == digest for p, digest in green_inputs['input_sha256'].items())
        green_qemu = obj('_temp/a06-ktest/aster-core/guests/guest-001/qemu.json')
        green_commands = obj('_temp/a06-ktest/commands.json', True)
        core_commands = [row for row in green_commands if row.get('cwd', '').endswith('/kernel/asterinas/kernel/core')]
        assert len(core_commands) == 1
        source_root = green_qemu['cwd'].removesuffix('/kernel/asterinas')

        def normalized_argv(argv):
            return [re.sub(r'(?<=logfile=)[^,]+', '<recorded-serial-path>', arg) for arg in argv]

        for control, (patch_name, patch_sha, changed_path, expected_failed, original_minimum) in constants['CONTROLS'].items():
            prefix = '_temp/a06-owner-negative' if control == 'owner-current-slot' else '_temp/a06-clock-handoff-negative/' + control
            result = obj(prefix + '/result.json', True)
            assert result['control'] == control and result['passed'] and result['negative_control_detected']
            assert (result['candidate_head'], result['candidate_tree']) == (HEAD, TREE)
            assert result['declared_changed_path'] == changed_path and result['patch_sha256'] == patch_sha
            assert result['product_qualification'] is False and result['raw_qemu_exit'] == 65 and result['original_gate_exit'] == 1 and not result['timed_out']
            assert all(result[key] is True for key in ['source_snapshots_unchanged', 'all_other_source_files_unchanged', 'same_osdk_binary_and_source_path'])
            before = obj(prefix + '/candidate-source-before.json')
            after = obj(prefix + '/candidate-source-after.json')
            assert before == after and (before['head'], before['tree']) == (HEAD, TREE) and before['files'] == source['files']
            negative = obj(prefix + '/negative-source-before.json')
            negative_after = obj(prefix + '/negative-source-after.json')
            negative_archive = obj(prefix + '/negative-archive-source.json')
            assert negative == negative_after and set(negative['files']) == set(source['files'])
            assert (negative['head'], negative['tree']) == (result['negative_head'], result['negative_tree'])
            assert all(negative_archive[key] == negative[key] for key in ['schema', 'head', 'tree', 'files'])
            assert before['root'] == negative['root'] == source_root
            changes = [p for p in source['files'] if source['files'][p] != negative['files'][p]]
            assert changes == [changed_path]
            expected_tree = tree_hash(negative['files'])
            assert expected_tree == negative['tree']
            patch = read(prefix + '/declared-negative-control.patch', True)
            applied = read(prefix + '/applied-negative-control.patch', True)
            fixed_patch_path = 'tests/organ_backend/' + patch_name
            assert patch == (ROOT / 'fixed-source' / fixed_patch_path).read_bytes()
            assert sha(patch) == patch_sha == source['files'][fixed_patch_path]['sha256']
            original = subprocess.check_output(['git', 'cat-file', 'blob', HEAD + ':' + changed_path], cwd=REPO, env=env)
            assert blob(original) == source['files'][changed_path]['git_blob'] and sha(original) == source['files'][changed_path]['sha256']
            apply_records = []
            for label, diff in [('declared', patch), ('recorded-applied', applied)]:
                paths = re.findall(r'^diff --git a/(\S+) b/(\S+)$', diff.decode(), re.M)
                assert paths == [(changed_path, changed_path)]
                with tempfile.TemporaryDirectory(prefix='a06-read-only-patch-review-') as temp:
                    temp_root = Path(temp)
                    copied = temp_root / changed_path
                    copied.parent.mkdir(parents=True)
                    copied.write_bytes(original)
                    copied.chmod(int(source['files'][changed_path]['mode'], 8) & 0o777)
                    for args in [['git', 'apply', '--check', '--verbose', '-'], ['git', 'apply', '--verbose', '-']]:
                        call = subprocess.run(args, cwd=temp_root, input=diff, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
                        apply_records.append({'patch': label, 'argv': args, 'isolated_text_copy_only': True, 'exit_code': call.returncode, 'stdout': call.stdout.decode(), 'stderr': call.stderr.decode()})
                        assert call.returncode == 0
                    actual = copied.read_bytes()
                    assert [str(p.relative_to(temp_root)) for p in temp_root.rglob('*') if p.is_file()] == [changed_path]
                    row = {'mode': source['files'][changed_path]['mode'], 'git_blob': blob(actual), 'sha256': sha(actual), 'size': len(actual)}
                    assert row == negative['files'][changed_path]
            negative_env = obj(prefix + '/gate/environment.json', True)
            assert negative_env['git_head'] == negative['head'] and negative_env['git_status'] == '' and negative_env['test_name'] is None
            assert negative_env['osdk_install_skipped'] is True
            for key in ['toolchain', 'rustc', 'cargo', 'build_inputs_sha256', 'osdk_sha256', 'vdso_sha256', 'cargo_build_jobs']:
                assert negative_env[key] == green_env[key]
            assert obj(prefix + '/gate/source-inputs.json') == green_inputs
            assert obj(prefix + '/gate/commands.json', True) == core_commands
            command = obj(prefix + '/command.json', True)
            assert command['cwd'] == source_root and command['execution_head'] == negative['head']
            assert command['argv'][1:8] == ['-I', '-B', source_root + '/support/build/ktest/run.py', '--crate', 'aster-core', '--skip-osdk-install', '--output']
            assert len(command['argv']) == 9
            qemu = obj(prefix + '/gate/aster-core/guests/guest-001/qemu.json', True)
            serial = read(prefix + '/gate/aster-core/guests/guest-001/serial.log', True)
            parsed = helper.parse_tests(serial, 'aster-core')
            failed = sorted(t['name'] for t in parsed['tests'] if t['outcome'] == 'FAILED')
            assert set(t['name'] for t in parsed['tests']) == green_names and parsed['declared'] == 220
            assert parsed['soft_skipped'] == 0 and parsed['filtered'] == 0
            assert set(failed) == expected_failed and failed == sorted(result['negative_failed'])
            assert parsed['passed'] == result['negative_passed'] == 220 - len(expected_failed)
            assert result['total_core_tests'] == 220 and result['green_serial_sha256'] == green_core['serial_sha256']
            assert qemu['raw_exit_code'] == 65 and qemu['timed_out'] is False and qemu['serial_sha256'] == sha(serial) == result['negative_serial_sha256']
            assert qemu['cwd'] == green_qemu['cwd'] and qemu['profile'] == green_qemu['profile']
            assert normalized_argv(qemu['argv']) == normalized_argv(green_qemu['argv'])
            assert qemu['requested_osdk_args'] == green_qemu['requested_osdk_args']
            for key in ['qemu_sha256', 'qemu_version']:
                assert qemu[key] == green_qemu[key]
            assert qemu['artifacts']['-bios'] == green_qemu['artifacts']['-bios']
            assert obj(prefix + '/original-gate-exit.json', True) == {'exit_code': 1}
            gate_green = obj(prefix + '/green-core-validation.json', True)
            assert gate_green['passed'] == gate_green['declared'] == gate_green['observed_test_starts'] == 220
            assert gate_green['failed'] == gate_green['filtered'] == gate_green['soft_skipped'] == 0
            green_artifact = green_qemu['artifacts']['-kernel']
            negative_artifact = qemu['artifacts']['-kernel']
            assert green_artifact['path'] == negative_artifact['path']
            assert result['green_kernel_sha256'] == green_artifact['sha256'] and result['negative_kernel_sha256'] == negative_artifact['sha256']
            assert negative_artifact['sha256'] != green_artifact['sha256']
            kernel(prefix + '/green-core-kernel.elf', green_artifact['sha256'], green_artifact['size'], control + ':retained-original-green')
            kernel(prefix + '/negative-control-kernel.elf', negative_artifact['sha256'], negative_artifact['size'], control + ':negative')
            controls.append({'control': control, 'prefix': prefix, 'candidate_head': HEAD, 'candidate_tree': TREE,
                             'negative_recorded_commit': negative['head'], 'negative_tree_independently_recomputed': expected_tree,
                             'source_files': 7054, 'only_changed_path': changed_path, 'original_file': source['files'][changed_path],
                             'mutated_file': negative['files'][changed_path], 'declared_patch_sha256': sha(patch),
                             'recorded_applied_patch_sha256': sha(applied), 'isolated_git_apply_checks': apply_records,
                             'test_names_equal_complete_green_suite': True, 'complete_tests': 220, 'passed': parsed['passed'],
                             'failed': parsed['failed'], 'expected_exact_failed_names': failed, 'soft_skipped': 0, 'filtered': 0,
                             'original_runner_minimum_unchanged': original_minimum, 'independent_required_denominator': 220,
                             'raw_qemu_exit': 65, 'original_gate_exit': 1, 'timed_out': False,
                             'same_recorded_toolchain_osdk_qemu_profile_and_locks_as_green': True,
                             'candidate_restored_and_source_snapshots_equal': True, 'review_passed': True})
            print(json.dumps({'control': control, 'complete_tests': 220, 'failed': parsed['failed'], 'passed': parsed['passed'], 'review_passed': True}), flush=True)

        archive_index = [{'name': info.filename, 'bytes': info.file_size, 'compressed_bytes': info.compress_size, 'crc32': f'{info.CRC:08x}'} for info in infos]
        index_bytes = (json.dumps({'schema': 1, 'archive_sha256': ZIP_SHA, 'all_members_crc_validated': True, 'members': archive_index}, indent=2) + '\n').encode()
        (OUT / 'archive-member-index.json').write_bytes(index_bytes)
    report = {'schema': 1, 'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
              'kind': 'Independent read-only final A06 artifact review; no kernel build, QEMU run, or product test rerun.',
              'head': HEAD, 'tree': TREE, 'archive': {'artifact_id': 12182038203, 'run_id': 39240728276, 'path': str(ROOT / 'original.zip'), 'bytes': archive_bytes, 'sha256': archive_sha, 'members': 1172, 'all_crc_passed': True},
              'reviewed_fixed_runner': {'path': runner_path, 'sha256': sha(runner_raw), 'method': 'Restricted AST evaluation of immutable data assignments only; runner not imported or executed.'},
              'independent_source_map_sha256': sha(source_raw), 'independent_source_files': 7054, 'candidate_git_tree_recomputed': TREE,
              'green_review': {'path': 'green-independent-review/review.json', 'sha256': sha(green_review_raw)},
              'old_201_name_reference': {'path': str(old_path), 'sha256': sha(old_raw), 'head': old['head'], 'kind': 'Earlier independent read of byte-identical official #203 artifact; no old report identity fabricated.'},
              'new_usage_tests': {'source_path': usage_path, 'bytes': len(usage_raw), 'sha256': sha(usage_raw), 'names': usage_names, 'all_19_once_and_passed_green': True, 'green_names_exact_old_201_union_new_19': True},
              'controls': controls, 'negative_failed_counts_in_fixed_order': [row['failed'] for row in controls],
              'retained_elf_members_independently_stream_hashed': elf_records,
              'read_raw_member_identities': list(records.values()),
              'archive_member_index': {'path': 'archive-member-index.json', 'bytes': len(index_bytes), 'sha256': sha(index_bytes)},
              'scope_limits': ['The seven complete 220-test negative runs detect only the seven frozen production mutations and exact assertion sets.',
                               'Negative tree/blob contents were independently recomputed. Local negative commit IDs are recorded identities; original raw commit objects are absent from this artifact.',
                               'Build, OSDK and QEMU identities are bound by original recorded inputs and fixed source. Host tool executables not retained in the artifact are not independently rehashed.',
                               'Only declared patches were applied to isolated temporary text copies, never to a checkout or executable. No artifact code or ELF was executed.',
                               'This review does not promote A10, original Hepta Objective/Operations authority, G1-c/d, physical cross-CPU scheduler qualification, ARM/device support, or true Asterinas W1.'],
              'passed': True}
    report_raw = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    (OUT / 'review.json').write_bytes(report_raw)
    manifest = {'schema': 1, 'report': {'path': 'review.json', 'bytes': len(report_raw), 'sha256': sha(report_raw)},
                'index': report['archive_member_index'], 'selected': selected, 'selected_count': len(selected),
                'selected_bytes': sum(row['bytes'] for row in selected), 'original_archive_not_copied': True}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'passed': True, 'report_bytes': len(report_raw), 'report_sha256': sha(report_raw), 'controls': 7, 'new_tests': 19, 'selected_count': len(selected), 'selected_bytes': manifest['selected_bytes']}))


if __name__ == '__main__':
    main()
