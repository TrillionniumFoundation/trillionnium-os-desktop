"""Narrow actual local ext4 and parser controls; never invokes production main()."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reason_candidate_under_test', ROOT / 'read_reason.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

result = {'schema': 1, 'scope': 'LOCAL_OWNED_EXT4_NEW_REASON_PATH_ONLY', 'passed': False,
          'remote_collection_executed': False, 'production_main_executed': False,
          'input_configuration_fixture': 'Local debugfs 1.47.0 banner/path/SHA substituted; remote 1.47.2 remains untested.',
          'cases': [], 'children': 0, 'source_sha256': hashlib.sha256((ROOT / 'read_reason.py').read_bytes()).hexdigest()}


def record(name, **details):
    result['cases'].append({'name': name, 'passed': True, **details})


def local(command):
    child = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=10,
                           env={'PATH': '/usr/sbin:/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'})
    assert child.returncode == 0, child.stderr
    return child


def streams_checked(report):
    for row in report['commands']:
        assert row['capture_complete'] and row['joined'] and not row['forced_kill'] and not row['errors']
        for name in ('stdout', 'stderr'):
            raw = base64.b64decode(row[name]['base64'], validate=True)
            assert len(raw) == row[name]['bytes'] and hashlib.sha256(raw).hexdigest() == row[name]['sha256']
            assert row[name]['eof']
    result['children'] += len(report['commands'])


with tempfile.TemporaryDirectory(prefix='owned-ext4-control-', dir=ROOT) as work:
    work = Path(work)
    image_path = work / 'metadata.img'
    with image_path.open('wb') as output:
        output.truncate(16 * 1024 * 1024)
    local(['/usr/sbin/mke2fs', '-q', '-t', 'ext4', '-F', '-L', 'owned-control', str(image_path)])
    tool_path = Path('/usr/sbin/debugfs')
    tool_fd = os.open(tool_path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    image_fd = os.open(image_path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        m.DEBUGFS = dict(m.DEBUGFS, path=str(tool_path), sha256=hashlib.sha256(tool_path.read_bytes()).hexdigest())
        banner = local([str(tool_path), '-R', 'stat /', str(image_path)]).stderr
        assert banner == b'debugfs 1.47.0 (5-Feb-2023)\n', banner
        m.DEBUGFS_BANNER = banner
        result['local_tool'] = {'path': str(tool_path), 'bytes': tool_path.stat().st_size,
                                'sha256': m.DEBUGFS['sha256'], 'banner': banner.decode()}

        def mutate(request):
            local([str(tool_path), '-w', '-R', request, str(image_path)])

        def collect():
            report = {'commands': [], 'image': {}, 'reason_read_attempted': False}
            stamp = m.stamp(os.fstat(image_fd))
            held = [(image_fd, None, str(image_path), stamp, 'file')]
            complete = m.collect_reason(tool_fd, image_fd, os.pread(image_fd, 4096, 0),
                                        held, report, time.monotonic() + 20)
            streams_checked(report)
            return complete, report

        mutate('mkdir /bootstat')
        complete, report = collect()
        assert complete and len(report['commands']) == 6 and not report['reason_body_collected']
        assert not report['reason_observation']['eligible_for_bounded_reason_read']
        assert not report['reason_observation']['absence_inferred']
        record('actual_missing_target_retains_error_output_no_body_or_absence_claim', commands=6)

        body = work / 'reason.txt'
        body.write_bytes(b'reboot,owned-control\n')
        mutate(f'write {body} {m.IMAGE_REASON_PATH}')
        complete, report = collect()
        assert complete and len(report['commands']) == 7 and report['reason_body_collected']
        assert report['reason_stat_unchanged_before_after']
        assert base64.b64decode(report['reason']['base64']) == body.read_bytes()
        assert report['reason_observation']['stat_observations'][2]['type'] == 'regular'
        record('actual_regular_reason_exact_body_one_cat_seven_reaped_children', commands=7)
        successful_stat = report['commands'][2]

        # Parser-only counterexamples; no syscall output is represented as remote evidence.
        wrong_banner = json.loads(json.dumps(successful_stat))
        wrong_banner['stderr'] = m.stream_record(b'debugfs 0.0 (wrong)\n', True, 8192)
        assert m.parse_stat(wrong_banner, 'regular') is None
        duplicate = json.loads(json.dumps(successful_stat))
        raw = m.command_bytes(duplicate, 'stdout')
        duplicate['stdout'] = m.stream_record(raw + raw.splitlines(keepends=True)[0], True, 4096)
        assert m.parse_stat(duplicate, 'regular') is None
        record('unknown_banner_and_duplicate_stat_are_not_body_authority', parser_seam=True)

        mutate(f'rm {m.IMAGE_REASON_PATH}')
        body.write_bytes(b'x' * 4097)
        mutate(f'write {body} {m.IMAGE_REASON_PATH}')
        complete, report = collect()
        assert complete and len(report['commands']) == 6 and not report['reason_body_collected']
        assert report['reason_observation']['stat_observations'][2]['bytes'] == 4097
        record('actual_4097_byte_file_never_cat', commands=6)

        mutate(f'rm {m.IMAGE_REASON_PATH}')
        mutate(f'symlink {m.IMAGE_REASON_PATH} /unapproved-target')
        complete, report = collect()
        assert complete and len(report['commands']) == 6 and not report['reason_body_collected']
        assert report['reason_observation']['stat_observations'][2] is None
        assert b'Type: symlink' in m.command_bytes(report['commands'][2], 'stdout')
        record('actual_symlink_target_never_cat', commands=6)

        for operation, path in (('cat', '/bootstat/other'), ('dump', m.IMAGE_REASON_PATH),
                                ('stat', '/other'), ('cat', m.IMAGE_REASON_PATH + '\nstat /')):
            try:
                m.reason_argv(tool_fd, image_fd, operation, path)
            except RuntimeError:
                pass
            else:
                raise AssertionError('outside fixed scope accepted')
        record('four_out_of_scope_requests_rejected_before_spawn')

        # Actual retained records are used without device access.
        evidence = ROOT.parent / 'root-recovery-20261104-02/evidence'
        prepared_raw = (evidence / 'owner15-normal01-prepared-read01/prepared.json').read_bytes()
        runtime_raw = (evidence / 'owner15-normal01-runtime-read01/runtime-result.json').read_bytes()
        for name, raw in [('prepared.json', prepared_raw), ('runtime-result.json', runtime_raw)]:
            assert (len(raw), hashlib.sha256(raw).hexdigest()) == m.RECORDS[name]
        binding = m.validate_records(json.loads(prepared_raw), json.loads(runtime_raw))
        assert binding['original_cleanup_bound'] and binding['original_runtime_success'] is False
        record('actual_retained_prepared_runtime_and_metadata_image_identity_bound', retained_records_only=True)
    finally:
        os.close(image_fd)
        os.close(tool_fd)

result['passed'] = True
print(json.dumps(result, sort_keys=True, indent=2))
