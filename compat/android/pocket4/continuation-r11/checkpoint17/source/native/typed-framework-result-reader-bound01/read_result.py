#!/usr/bin/env python3
"""Fixed normal framework build receipts; terminal pins must be actual-bound."""
import base64, datetime, gzip, hashlib, json, os, stat
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


BASE = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-build-01-20261105')
WORK = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-work-01-20261105')
JOURNAL = WORK / 'source-projection.json'
OUTER_SHA = '3626270e88e72c4e46d8beee09b5351e1f7d53bab18043241204ca314855e04d'
INNER_SHA = '139163acad47d9db707faa950e4b4dcecaf3e72b655bce8b6b3db089ce542bdf'
CONTROLLER_SHA = '12a86ce8fc03b281193a5942a5b7be0c1d7531f7f4e489f1eeca8db9688d1307'
SOURCES = (
    ('attempt-01/terminal.json', 2097152),
    ('attempt-01/claim.json', 262144),
    ('attempt-01/input-bindings-before.json', 1048576),
    ('attempt-01/input-bindings-after.json', 1048576),
    ('attempt-01/build.stdout', 16777216),
    ('attempt-01/build.stderr', 16777216),
    ('build-fences-01/terminal.json', 131072),
    ('build-fences-01/claim.json', 131072),
    ('build-fences-01/before.json', 65536),
    ('build-fences-01/after.json', 65536),
    ('build-fences-01/before.stdout.json', 65536),
    ('build-fences-01/after.stdout.json', 65536),
    ('build-fences-01/before.stderr.txt', 65536),
    ('build-fences-01/after.stderr.txt', 65536),
    ('android-out/droidloom-role-ingress-attempt.json', 262144),
    ('android-out/droidloom-role-ingress-inputs.json', 8388608),
    ('android-out/droidloom-role-ingress-command.json', 65536),
)


def plan():
    return {'state': 'PLAN_FIXED_FRAMEWORK_RESULT_READER', 'base': str(BASE),
            'fixed_sources': [{'relative': name, 'maximum_bytes': bound} for name, bound in SOURCES],
            'journal': str(JOURNAL), 'journal_metadata_only': True,
            'actual_outer_terminal_binding_required': True,
            'actual_inner_terminal_binding_required_if_observed': True,
            'missing_files_preserved_as_errors': True, 'artifact_paths_not_invented': True,
            'Main_actions': 0, 'Android_actions': 0, 'source_or_binary_execution': False,
            'build_or_runtime_repeated': False, 'production_or_artifact_qualification': False}


def valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def collect():
    if not valid_sha(OUTER_SHA) or (INNER_SHA is not None and not valid_sha(INNER_SHA)):
        raise RuntimeError('bind the actual terminal pins before collecting; unknown is not absence')
    started = utc()
    rows = [observe(relative, limit) for relative, limit in SOURCES]
    errors = []
    byname = {row['relative']: row for row in rows}
    expected = {'build-fences-01/terminal.json': OUTER_SHA}
    if INNER_SHA is not None:
        expected['attempt-01/terminal.json'] = INNER_SHA
    for row in rows:
        if not row['complete']:
            errors.append({'path': row['relative'], 'error': row.get('error')})
        elif row['relative'] in expected and row['sha256'] != expected[row['relative']]:
            errors.append({'path': row['relative'], 'error': 'actual terminal digest mismatch'})
    journal = {'path': str(JOURNAL), 'observed_utc': utc(), 'metadata_only': True}
    try:
        parent_before = identity(JOURNAL.parent.lstat())
        if not stat.S_ISDIR(parent_before['mode']):
            raise RuntimeError('journal parent is not a real directory')
        journal['parent_identity'] = parent_before
        try:
            first = identity(JOURNAL.lstat())
            second = identity(JOURNAL.lstat())
            if first != second:
                raise RuntimeError('journal path changed during metadata observation')
            journal.update({'present': True, 'named_before': first, 'named_after': second})
        except FileNotFoundError as error:
            if error.filename != str(JOURNAL):
                raise
            journal.update({'present': False, 'errno': error.errno, 'filename': error.filename})
        if identity(JOURNAL.parent.lstat()) != parent_before:
            raise RuntimeError('journal parent changed during metadata observation')
    except Exception as error:
        journal['error'] = repr(error)
        errors.append({'path': str(JOURNAL), 'error': repr(error)})
    bindings = {'actual_terminal_digests': expected, 'normal_controller_sha256': CONTROLLER_SHA,
                'builder_log_digests_bound': False, 'normal_records_bound': False,
                'observed_successful_normal_command': False,
                'Java_implementation_jar_qualified': False,
                'Android_JNI_TU_and_library_qualified': False,
                'runtime_authorization_enabled': False, 'installation_performed': False}
    try:
        outer_row = byname['build-fences-01/terminal.json']
        if not outer_row['complete'] or outer_row['sha256'] != OUTER_SHA:
            raise RuntimeError('the actual outer terminal was not completely bound')
        outer = json.loads(outer_row['text'])
        bindings['outer_state'] = outer['state']
        bindings['outer_inner_returncode'] = outer['inner_returncode']
        if outer.get('installed') is not False or outer.get('production_ready') is not False:
            raise RuntimeError('outer terminal scope differs')
        inner_row = byname['attempt-01/terminal.json']
        if INNER_SHA is None:
            # This mode is explicitly chosen only after the actual outer record
            # shows that no inner terminal was returned. Missing paths are
            # still preserved above, and the collector cannot call this PASS.
            if inner_row['complete'] or outer['inner_returncode'] is not None \
                    or inner_row.get('error', {}).get('errno') != 2:
                raise RuntimeError('an unbound inner terminal exists; bind its actual digest')
        else:
            if not inner_row['complete'] or inner_row['sha256'] != INNER_SHA:
                raise RuntimeError('the actual inner terminal was not completely bound')
            inner = json.loads(inner_row['text'])
            bindings['inner_state'] = inner['state']
            bindings['builder_returncode'] = inner['builder_returncode']
            bindings['cleanup'] = inner['cleanup']
            bindings['resource_gate'] = inner.get('owned_resource_gate')
            bindings['journal_present_in_terminal'] = inner['source_projection_journal_present']
            for label in ('stdout', 'stderr'):
                row = byname['attempt-01/build.' + label]
                if not row['complete'] or row.get('sha256') != inner[label + '_sha256']:
                    raise RuntimeError('actual builder terminal/log digest mismatch: ' + label)
            bindings['builder_log_digests_bound'] = True
            if inner.get('complete_framework_Java_and_Android_TU_qualified') is not False \
                    or inner.get('runtime_authorization_enabled') is not False:
                raise RuntimeError('inner terminal claims a qualification outside this build scope')
            gate = inner.get('normal_command_completion_gate')
            if gate is not None:
                wanted = {
                    'droidloom-role-ingress-attempt.json',
                    'droidloom-role-ingress-inputs.json',
                    'droidloom-role-ingress-command.json',
                }
                if set(gate['records']) != wanted:
                    raise RuntimeError('normal command record set differs')
                for name, pin in gate['records'].items():
                    row = byname['android-out/' + name]
                    if not row['complete'] or row['sha256'] != pin['sha256'] \
                            or row['bytes'] != pin['bytes'] or row['path'] != pin['path']:
                        raise RuntimeError('normal command record was not bound: ' + name)
                bindings['normal_records_bound'] = True
            if inner['state'] == 'FRAMEWORK_COMMAND_COMPLETED_QUALIFICATION_PENDING':
                if inner['builder_returncode'] != 0 or inner['cleanup']['complete'] is not True \
                        or inner.get('input_after_qualified') is not True \
                        or inner['source_projection_journal_present'] is not False \
                        or journal.get('present') is not False or not bindings['normal_records_bound'] \
                        or outer['state'] != 'BUILD_AND_OBSERVED_MAIN_FENCES_PASSED' \
                        or outer['inner_returncode'] != 0:
                    raise RuntimeError('successful command/restoration/fence contract differs')
                bindings['observed_successful_normal_command'] = True
    except Exception as error:
        errors.append({'path': 'actual terminal/log/normal-record binding', 'error': repr(error)})
    result = {'schema': 1, 'scope': 'fixed normal framework build01 receipts and logs only',
              'source_sha256': SOURCE_SHA256, 'started_utc': started, 'finished_utc': utc(),
              'collection_complete': not errors,
              'all_requested_files_present': all(row['complete'] for row in rows),
              'errors': errors, 'files': rows, 'bindings': bindings, 'projection_journal': journal,
              'recursive_scan': False, 'source_execution': False, 'binary_execution': False,
              'Main_actions': 0, 'Android_actions': 0, 'files_written': 0,
              'retry_or_build_started': False, 'policy_or_resource_changes': 0,
              'prior_failures_preserved': True, 'production_ready': False}
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True) + '\n').encode()
    if len(raw) > 67108864:
        raise RuntimeError('fixed receipt/log transport exceeds 64 MiB uncompressed bound')
    packed = gzip.compress(raw, compresslevel=6, mtime=0)
    envelope = {'schema': 1, 'encoding': 'gzip+base64', 'uncompressed_bytes': len(raw),
                'sha256': digest(raw), 'gzip_bytes': len(packed), 'gzip_sha256': digest(packed),
                'collection_complete': not errors, 'payload': base64.b64encode(packed).decode('ascii')}
    print(json.dumps(envelope, sort_keys=True), flush=True)
    return 0 if not errors else 1


def main():
    import sys
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps(plan(), sort_keys=True))
        return 0
    return collect()


if __name__ == '__main__':
    raise SystemExit(main())
