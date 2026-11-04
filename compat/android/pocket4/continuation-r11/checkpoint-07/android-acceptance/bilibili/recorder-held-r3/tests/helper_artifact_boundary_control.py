#!/usr/bin/env python3
"""Actual source_contract I/O against owned fixtures; never enters Android or executes a helper."""
import ast
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types

HERE = Path(__file__).resolve().parents[1]
SIZE = 4_366_312
ROWS = []


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + '\n')
    path.chmod(0o600)
    return digest(path)


def make_fixture(root):
    root.mkdir()
    source = root / 'owned-source.rs'
    source.write_bytes(b'owned synthetic source, never compiled or executed\n')
    source.chmod(0o600)
    helper = root / 'owned-helper'
    with helper.open('wb') as stream:
        chunk = bytes(range(256)) * 256
        count = 0
        while count < SIZE:
            part = chunk[:min(len(chunk), SIZE - count)]
            stream.write(part)
            count += len(part)
    helper.chmod(0o700)
    terminal = dict(state='succeeded', exit_code=0, cancelled=False, timed_out=False,
                    output_complete=True, output_durable=True, terminal_publication_confirmed=True)
    evidence = {}
    for name in ('host14', 'sixns', 'main_readonly'):
        p = root / (name + '.json')
        sha = json_file(p, {'owned_fixture': True, 'name': name})
        evidence[name] = {'path': str(p), 'sha256': sha, 'terminal': terminal}
    qualification = root / 'qualification.json'
    value = dict(schema=1, protocol='owned-held-namespace-entry-v1',
                 qualified_for_owned_namespace_entry=True,
                 helper_source_sha256=digest(source), helper_binary_sha256=digest(helper),
                 host_controls_passed=14, six_namespace_host_entry_passed=True,
                 Main_readonly_entry_passed=True, qualified_for_whole_process_tree_cleanup=False,
                 candidate_production_ready=False, evidence=evidence)
    json_file(qualification, value)
    return source, helper, qualification, evidence


def bind(module, fixture):
    source, helper, qualification, _ = fixture
    module.HELPER_SOURCE = source
    module.HELPER_PATH = helper
    module.HELPER_QUALIFICATION = qualification
    module.HELPER_SOURCE_SHA = digest(source)
    module.HELPER_SHA = digest(helper)
    module.HELPER_QUALIFICATION_SHA = digest(qualification)


def expect_failure(name, call, code=None, os_errno=None, diagnostic=None):
    try:
        call()
    except (RuntimeError, OSError) as error:
        if code is not None:
            assert isinstance(error, RuntimeError) and str(error).startswith(code), repr(error)
        if os_errno is not None:
            assert isinstance(error, OSError) and error.errno == os_errno, repr(error)
        if diagnostic is not None:
            data = json.loads(str(error).split(': ', 1)[1])
            for key, wanted in diagnostic.items():
                assert data[key] == wanted, (key, data, wanted)
        ROWS.append({'case': name, 'expected_rejection_observed': True,
                     'type': type(error).__name__, 'error': str(error)})
    else:
        raise AssertionError(name + ' unexpectedly passed')


def main():
    old = load(HERE / 'references/source_contract_r2.py', 'old_contract')
    new = load(HERE / 'source_contract.py', 'new_contract')
    assert old.bounded_file.__defaults__ == new.bounded_file.__defaults__ == (131072,)
    assert new.HELPER_BYTES == SIZE
    assert old.HELPER_SHA == new.HELPER_SHA == '21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689'
    assert old.HELPER_SOURCE_SHA == new.HELPER_SOURCE_SHA
    assert old.HELPER_QUALIFICATION_SHA == new.HELPER_QUALIFICATION_SHA
    before_fds = set(os.listdir('/proc/self/fd'))
    with tempfile.TemporaryDirectory(prefix='pocket4-owned-helper-bound-') as temporary:
        root = Path(temporary)
        fixture = make_fixture(root / 'exact')
        bind(old, fixture)
        bind(new, fixture)
        expect_failure('original_r2_rejects_same_size_owned_fixture_at_4MiB',
                       old.verify_shared_helper, 'INPUT_SHAPE_OR_BOUND_CHANGED')
        value = new.verify_shared_helper()
        assert value['binary_sha256'] == digest(fixture[1])
        assert value['qualification_sha256'] == digest(fixture[2])
        assert value['whole_process_tree_cleanup_qualified'] is False
        ROWS.append({'case': 'new_exact_artifact_size_and_full_owned_qualification_pass',
                     'actual_verify_shared_helper_returned': True, 'helper_bytes': fixture[1].stat().st_size})

        for name in ('oversize', 'undersize', 'changed_hash', 'evidence_bound', 'hardlink', 'symlink'):
            fixture = make_fixture(root / name)
            bind(new, fixture)
            source, helper, qualification, evidence = fixture
            if name == 'oversize':
                with helper.open('ab') as stream:
                    stream.write(b'X')
                expect_failure('artifact_plus_one_rejected_with_exact_path_size_bound',
                               new.verify_shared_helper, 'INPUT_SHAPE_OR_BOUND_CHANGED:',
                               diagnostic={'path': str(helper), 'size_bytes': SIZE + 1, 'maximum_bytes': SIZE})
            elif name == 'undersize':
                with helper.open('r+b') as stream:
                    stream.truncate(SIZE - 1)
                expect_failure('artifact_minus_one_rejected_by_explicit_exact_size',
                               new.verify_shared_helper, 'HELD_HELPER_BINARY_SIZE_CHANGED')
            elif name == 'changed_hash':
                with helper.open('r+b') as stream:
                    stream.write(b'X')
                expect_failure('same_size_modified_content_still_rejected_by_hash',
                               new.verify_shared_helper, 'HELD_HELPER_BINARY_CHANGED')
            elif name == 'evidence_bound':
                target = Path(evidence['host14']['path'])
                with target.open('wb') as stream:
                    stream.truncate(4 * 1024 * 1024 + 1)
                expect_failure('evidence_file_keeps_original_4MiB_limit',
                               new.verify_shared_helper, 'INPUT_SHAPE_OR_BOUND_CHANGED:',
                               diagnostic={'path': str(target), 'maximum_bytes': 4 * 1024 * 1024})
            elif name == 'hardlink':
                os.link(helper, root / 'second-hardlink')
                expect_failure('helper_single_link_gate_preserved',
                               new.verify_shared_helper, 'INPUT_SHAPE_OR_BOUND_CHANGED:',
                               diagnostic={'path': str(helper), 'nlink': 2})
            elif name == 'symlink':
                alias = root / 'helper-symlink'
                alias.symlink_to(helper)
                new.HELPER_PATH = alias
                expect_failure('helper_final_symlink_still_rejected',
                               new.verify_shared_helper, os_errno=errno.ELOOP)
        unrelated = root / 'unrelated-input'
        with unrelated.open('wb') as stream:
            stream.truncate(131073)
        expect_failure('generic_default_stays_131072', lambda: new.bounded_file(unrelated),
                       'INPUT_SHAPE_OR_BOUND_CHANGED:',
                       diagnostic={'path': str(unrelated), 'size_bytes': 131073, 'maximum_bytes': 131072})
    assert set(os.listdir('/proc/self/fd')) == before_fds
    assert len(ROWS) == 9
    print(json.dumps({'schema': 1, 'state': 'NINE_OWNED_BOUNDARY_CONTROLS_PASS',
                      'actual_source_function': 'verify_shared_helper and bounded_file',
                      'old_source_sha256': digest(HERE / 'references/source_contract_r2.py'),
                      'new_source_sha256': digest(HERE / 'source_contract.py'),
                      'fixture_substitutions': 'Only HELPER paths and expected source/helper/qualification hashes are rebound to owned regular-file fixtures; actual os.open/fstat/read/close, parser and all qualification guards execute unchanged. No fake read/poll implementation.',
                      'fixture_is_original_helper_ELF': False,
                      'original_artifact_identity_evidence': 'Separate actual Pocket4 metadata and streaming-hash receipts, not these synthetic fixtures.',
                      'generic_default_unchanged': True, 'original_helper_pins_unchanged': True,
                      'owned_descriptors_restored': True, 'temporary_fixture_removed': True,
                      'rows': ROWS, 'Android_UI_audio_actions': 0,
                      'helper_execution': False, 'whole_app_production_ready': False}, indent=2))


if __name__ == '__main__':
    main()
