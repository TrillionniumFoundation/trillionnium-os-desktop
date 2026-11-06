"""Local borrowed-stream controls; no original private file or Main access."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import types


def main():
    path = Path(__file__).with_name('summarize_recorded_entries.py')
    module = types.ModuleType('recorded_retention_summary_local_control')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    original_fds = module.census()
    stat_row = {'st_dev': 100, 'st_ino': 200, 'st_uid': 0, 'st_gid': 0, 'st_mode': 33024,
                'st_nlink': 2, 'st_size': 1234, 'st_mtime_ns': 1794006439318808766,
                'st_ctime_ns': 1794006439318808766, 'st_blocks': 8, 'allocated_bytes': 4096}
    refs = [{'id': 'path-0001', 'coordinate': 'host', 'path': '/reviewed/old-one.apk'},
            {'id': 'path-0002', 'coordinate': 'host', 'path': '/reviewed/old-two.apk'},
            {'id': 'path-0003', 'coordinate': 'held_android_init_root', 'path': '/reviewed/missing'}]
    targets = [{'reference_id': item['id'], 'package': 'local.test.' + str(n),
                'historical_retained_pin': {'bytes': 1234, 'sha256': 'a' * 64,
                                            'file': {key: stat_row[key] for key in module.STAT}}}
               for n, item in enumerate(refs[:2])]
    rows = []
    for phase in ('before', 'after'):
        for n, ref in enumerate(refs):
            row = {'reference_id': ref['id'], 'coordinate': ref['coordinate'], 'path': ref['path'], 'phase': phase}
            if n < 2:
                row.update(status='OBSERVED_METADATA', stat=stat_row, mount_id=33)
            else:
                row.update(status='ABSENT', error={'type': 'FileNotFoundError', 'errno': 2})
            rows.append(row)
    rows.insert(3, {'coordinate': 'host', 'tree_root': '/private-not-exported',
                    'path': '/private-not-exported/sensitive-name', 'status': 'OBSERVED_METADATA',
                    'stat': stat_row, 'mount_id': 33})
    checks = []

    def run(values, wrong_hash=False):
        raw = b''.join(module.canonical(row) + b'\n' for row in values)
        with tempfile.TemporaryFile() as stream:
            stream.write(raw)
            stream.flush()
            offset = stream.tell()
            request = {'entries': {'path': '/fixed-prior-observation/entries.private.jsonl', 'bytes': len(raw),
                                  'sha256': '0' * 64 if wrong_hash else hashlib.sha256(raw).hexdigest(),
                                  'file': module.metadata(stream.fileno())},
                       'references': refs, 'previous_APKs': targets,
                       'expected_reference_summary': {'count': 3, 'observed': 2, 'absent': 1, 'unresolved': 0},
                       'reference_path_changes': []}
            before = module.metadata(stream.fileno())
            try:
                return module.summarize_fd(stream.fileno(), request, time.monotonic() + 3)
            finally:
                assert stream.tell() == offset
                assert module.metadata(stream.fileno()) == before

    value = run(rows)
    assert len(value['previous_APKs']) == 2 and len(value['gap_references']) == 1
    assert value['selected_observation_allocated_bytes_sum'] == 8192
    assert value['selected_observation_allocated_bytes_unique_inode'] == 4096
    assert value['selected_unique_device_inode_pairs'] == 1
    assert value['tree_rows_omitted_without_path_or_content_export'] == 1
    assert b'private-not-exported' not in module.canonical(value)
    assert value['reclaimable_bytes'] is None and value['cleanup_eligible'] is False
    assert value['previous_APKs'][0]['before']['stat']['st_mtime_ns'] == 1794006439318808766
    checks.append({'name': 'real_borrowed_stream_full_hash_filter_hardlink_and_integer_preservation', 'passed': True})
    for name, fixture, damaged_hash, expected in (
        ('full_stream_hash_mismatch_rejected', rows, True, 'FULL_STREAM_BYTES_HASH_OR_STAT_CHANGED'),
        ('duplicate_reference_phase_rejected', rows + [copy.deepcopy(rows[0])], False, 'DUPLICATE_OR_UNKNOWN_REFERENCE_PHASE')):
        try:
            run(fixture, wrong_hash=damaged_hash)
        except RuntimeError as error:
            assert str(error) == expected
            checks.append({'name': name, 'passed': True})
        else:
            raise AssertionError('negative control admitted: ' + name)
    final_fds = module.census()
    assert original_fds == final_fds
    print(json.dumps({'schema': 'pocket4-recorded-retention-summary-local-controls-v1', 'ok': True, 'checks': checks,
        'borrowed_stream_offset_stat_and_liveness_preserved': True,
        'whole_process_descriptor_identities_restored': True,
        'FDs_before': len(original_fds), 'FDs_after': len(final_fds),
        'actual_root_path_reader_executed': False, 'original_private_stream_read': False,
        'target_or_Main_reads': 0, 'remote_submissions': 0, 'production_ready': False}, sort_keys=True))


if __name__ == '__main__':
    main()
