#!/usr/bin/env python3
"""Actual-terminal-bound normal resume build logs; plain JSON, fixed read-only scope."""
import datetime, hashlib, json, os, stat
from pathlib import Path

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'bytes': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def observe(relative, limit):
    path = BASE / relative
    row = {'path': str(path), 'relative': relative, 'maximum_bytes': limit,
           'started_utc': utc(), 'complete': False}
    try:
        parents = {}
        for parent in path.parents:
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise RuntimeError('source ancestor is not a real directory: ' + str(parent))
            parents[str(parent)] = (info.st_dev, info.st_ino, info.st_mode)
        named_before = path.lstat()
        row['named_before'] = identity(named_before)
        if not stat.S_ISREG(named_before.st_mode) or named_before.st_size > limit:
            raise RuntimeError('source is not regular or exceeds its fixed bound')
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            row['held_before'] = identity(os.fstat(stream.fileno()))
            if row['held_before'] != row['named_before']:
                raise RuntimeError('named/held source identity differs before read')
            raw = stream.read(limit + 1)
            row['held_after'] = identity(os.fstat(stream.fileno()))
            row['named_after'] = identity(path.lstat())
            if not (row['held_before'] == row['held_after'] == row['named_after']):
                raise RuntimeError('source changed while held')
            if len(raw) != row['held_before']['bytes'] or len(raw) > limit:
                raise RuntimeError('source read is incomplete or exceeds its fixed bound')
            for name, expected in parents.items():
                info = Path(name).lstat()
                if (info.st_dev, info.st_ino, info.st_mode) != expected:
                    raise RuntimeError('source ancestor identity changed: ' + name)
            row['bytes'] = len(raw)
            row['sha256'] = digest(raw)
            row['text'] = raw.decode('utf-8', errors='strict')
            row['complete'] = True
    except Exception as error:
        row['error'] = {'type': type(error).__name__, 'message': str(error),
                        'errno': getattr(error, 'errno', None),
                        'filename': getattr(error, 'filename', None)}
    row['finished_utc'] = utc()
    return row


BASE = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-resume-build-01-20261106')
INNER_SHA = '80f3508bab1884421af6db2f6d87537fd950100be009265b7e2efabc9b97fcdc'
OUTER_SHA = '2c36ab1cc9ff6f181855f195f9c5b7bc0f58e7fb99d9c76e4871e64b143bf059'
CONTROLLER_SHA = '1d6f63947e5536c22978a6d30c3b35cc348d548409f772903eca1381d206e146'
PARENT_JOB = '1a1ae6b5a97-fc05-5f81'
SOURCES = (
    ('attempt-01/build.stdout', 16777216, 'f001d60ee86a9c0b5fe32ca98164b0bb1127826aa1e3c9ba97a7ce834c0d0e4e'),
    ('attempt-01/build.stderr', 16777216, '12c13559ad20843f350c14e16f32e149cf1c2c4f4ed339d9c862e0e1c2ad753b'),
)


def plan():
    return {'state': 'PLAN_FIXED_NORMAL_RESUME_BUILD_LOG_PAIR', 'base': str(BASE),
            'fixed_sources': [{'relative': name, 'maximum_bytes': bound, 'sha256': expected}
                              for name, bound, expected in SOURCES],
            'actual_parent_job': PARENT_JOB,
            'actual_outer_terminal_sha256': OUTER_SHA, 'actual_inner_terminal_sha256': INNER_SHA,
            'transport': 'plain JSON with exact original UTF8 log text',
            'full_file_only_within_original_16MiB_per_log_bound': True,
            'oversize_missing_changed_invalid_UTF8_or_digest_error_is_failure': True,
            'missing_files_preserved_as_errors': True, 'artifact_paths_not_invented': True,
            'terminal_journal_progress_or_artifact_reads': False,
            'Main_actions': 0, 'Android_actions': 0, 'source_or_binary_execution': False,
            'build_or_runtime_repeated': False, 'production_or_artifact_qualification': False}


def valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def collect():
    if not valid_sha(INNER_SHA) or not valid_sha(OUTER_SHA) or not all(valid_sha(row[2]) for row in SOURCES):
        raise RuntimeError('bind actual terminal and log pins before collecting; unknown is not absence')
    started = utc()
    rows = [observe(relative, limit) for relative, limit, expected in SOURCES]
    expected = {relative: digest_value for relative, limit, digest_value in SOURCES}
    errors = []
    for row in rows:
        row['expected_sha256_from_actual_inner_terminal'] = expected[row['relative']]
        row['actual_terminal_digest_match'] = False
        if not row['complete']:
            errors.append({'path': row['relative'], 'error': row.get('error')})
        elif row['sha256'] != expected[row['relative']]:
            errors.append({'path': row['relative'], 'error': 'actual terminal-declared log digest mismatch'})
        else:
            row['actual_terminal_digest_match'] = True
    bindings = {'actual_parent_job': PARENT_JOB,
                'actual_parent_state': 'FAILED', 'actual_parent_builder_returncode': 1,
                'actual_inner_terminal': {'bytes': 2246, 'sha256': INNER_SHA},
                'actual_outer_terminal': {'bytes': 1150, 'sha256': OUTER_SHA},
                'normal_controller_sha256': CONTROLLER_SHA,
                'expected_full_log_sha256': expected,
                'full_log_digests_bound': not errors,
                'raw_logs_exported_only_if_complete_bounded_UTF8': True,
                'no_terminal_or_progress_recollection': True,
                'normal_records_bound': False, 'observed_successful_normal_command': False,
                'Java_implementation_jar_qualified': False,
                'Android_JNI_TU_and_library_qualified': False,
                'cleanup_success_inferred_from_collection': False,
                'runtime_authorization_enabled': False, 'installation_performed': False}
    result = {'schema': 1, 'scope': 'actual normal framework resume01 build stdout/stderr pair only',
              'source_sha256': SOURCE_SHA256, 'started_utc': started, 'finished_utc': utc(),
              'collection_complete': not errors,
              'all_requested_files_present': all(row['complete'] for row in rows),
              'errors': errors, 'files': rows, 'bindings': bindings,
              'transport': 'plain-json-exact-utf8-text',
              'full_file_hash_and_stable_identity_required': True,
              'partial_or_tail_content_qualified': False,
              'logs_are_fixed_owned_normal_builder_outputs_not_App_UI': True,
              'collection_success_is_not_build_cleanup_or_runtime_success': True,
              'terminal_journal_progress_or_artifact_reads': False,
              'recursive_scan': False, 'source_execution': False, 'binary_execution': False,
              'Main_actions': 0, 'Android_actions': 0, 'files_written': 0,
              'retry_or_build_started': False, 'policy_or_resource_changes': 0,
              'prior_failures_preserved': True, 'production_ready': False}
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True) + '\n').encode()
    if len(raw) > 67108864:
        raise RuntimeError('fixed receipt transport exceeds original 64 MiB uncompressed bound')
    print(raw.decode('ascii'), end='', flush=True)
    return 0 if not errors else 1


def main():
    import sys
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps(plan(), sort_keys=True))
        return 0
    return collect()


if __name__ == '__main__':
    raise SystemExit(main())
