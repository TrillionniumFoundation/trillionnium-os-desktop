#!/usr/bin/env python3
"""Pin the published CP3A source postimages into new, isolated preparations.

This is a source preparation bridge, not an Android execution admission.
All live selectors, original files, and runtime prerequisites remain untouched.
Only the fixed task directory below is writable by this program.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys

ROOT = Path('/home/alex/work/p4-cp3a-bootstrap-20261120-runtimeaudit-r1')
INPUT_SHA = 'c38a0ef25c51497f2056169ca130d3ff6e13fa710d3159444604341af33c4b25'
INPUT_SIZE = 454653
COMMIT = '1af163b21f5c7dcaaf94084d7cc1ef19aed05ae1'
REPO = 'TrillionniumFoundation/trillionnium-os-desktop'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns')
ENTRIES = {
    'business-system-cases-runtime-inputs-20261108-8b88-r2': 'system_entry.py',
    'calendar-reminder-runtime-inputs-20261108-8b88-r2': 'system_entry.py',
    'camera-app-photo-preparation-resume-20261107-r4': 'camera_entry.py',
    'clock-remaining-runtime-inputs-20261108-8b88-r2': 'clock_entry.py',
    'ihg-5.111.1-r1': 'app_entry.py',
    'documents-saf11-runtime-inputs-20261108-8b88-r2': 'documents_entry.py',
    'documents-search-sort-runtime-inputs-20261108-8b88-r2': 'documents_entry.py',
}
RETIRED = (
    ('gallery-album-current-preparation-20261107-r6/video_entry.py', 'main'),
    ('gallery-new-runtime-preparation-20261107-r7/gallery_current_entry.py', 'main'),
    ('gallery-new-runtime-preparation-20261107-r7/gallery_current_install.py', 'verify_art_receipt'),
    ('gallery-new-runtime-preparation-20261107-r7/gallery_current_install.py', 'execute'),
    ('gallery-new-runtime-preparation-20261107-r7/gallery_current_verify.py', 'execute'),
    ('gallery-rotation-current-preparation-20261107-r7/gallery_rotation_entry.py', 'main'),
)
RETIRE_REASON = 'CP3A_OFFICIAL_FULL_GSI_ONLY_OLD_MODIFIED_CANDIDATE_RUNTIME_ENTRY_RETIRED'


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(value):
    return [getattr(value, name) for name in FIELDS]


def ref(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def read(path, expected=None, maximum=16 * 1024 * 1024):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, 'CANONICAL_INPUT_REQUIRED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and 0 < before.st_size <= maximum, 'BOUNDED_SINGLE_LINK_INPUT_REQUIRED')
        chunks = []
        size = 0
        while size <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - size))
            if not block:
                break
            chunks.append(block)
            size += len(block)
        raw = b''.join(chunks)
        need(len(raw) == before.st_size and metadata(before) == metadata(os.fstat(fd))
             == metadata(path.lstat()), 'INPUT_CHANGED_DURING_READ')
        observed = ref(path, raw)
        if expected is not None:
            need(observed == expected, 'INPUT_PIN_CHANGED:' + str(path))
        return raw, observed, metadata(before)
    finally:
        os.close(fd)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode()


def mkdir(path):
    need(path.is_relative_to(ROOT) and path != ROOT, 'OUTPUT_OUTSIDE_FIXED_TASK_DIRECTORY')
    if path.parent != ROOT and not path.parent.exists():
        mkdir(path.parent)
    need(path.parent.resolve() == path.parent, 'OUTPUT_PARENT_NOT_CANONICAL')
    path.mkdir(mode=0o700)


def write(path, raw):
    need(path.is_relative_to(ROOT) and path != ROOT, 'OUTPUT_OUTSIDE_FIXED_TASK_DIRECTORY')
    if not path.parent.exists():
        mkdir(path.parent)
    need(path.parent.resolve() == path.parent, 'OUTPUT_PARENT_NOT_CANONICAL')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    try:
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    return read(path, ref(path, raw))[1]


def relative(path, prefix):
    p = PurePosixPath(path)
    need(p.parts[0] == prefix and len(p.parts) == 3
         and all(part not in ('', '.', '..') for part in p.parts), 'EXACT_SOURCE_RELATIVE_PATH')
    return '/'.join(p.parts[1:])


def load_inputs():
    raw, input_ref, _ = read(ROOT / 'reviewed-inputs.json',
        {'path': str(ROOT / 'reviewed-inputs.json'), 'bytes': INPUT_SIZE, 'sha256': INPUT_SHA})
    value = json.loads(raw)
    need(value['commit'] == COMMIT and value['repository'] == REPO, 'EXACT_REVIEWED_SOURCE_COMMIT')
    manifest = value['original_manifest']
    need(manifest['source_only'] is True and manifest['Android_calls'] == 0
         and len(manifest['source_files']) == 224 and len(manifest['preparation_bookends']) == 11,
         'COMPLETE_REVIEWED_ORIGINAL_CLOSURE')
    blobs = {}
    need(len(value['files']) == 26, 'COMPLETE_REVIEWED_POSTIMAGE_PACKET')
    for row in value['files']:
        name = row['path']
        need(name not in blobs, 'DUPLICATE_REVIEWED_INPUT')
        data = row['text'].encode()
        git_blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        need(len(data) == row['bytes'] and git_blob == row['git_blob'], 'REVIEWED_GIT_BLOB_CHANGED')
        blobs[name] = data
    transform = json.loads(blobs['prepared/TRANSFORM.json'])
    need(transform['combined_postimages'] == 24 and transform['original_files_covered'] == 224
         and transform['provider_transform_control_flow_UID_limits_unchanged'] is True,
         'EXACT_REVIEWED_TRANSFORM_SCOPE')
    postimages = {name.removeprefix('prepared/postimages/'): raw for name, raw in blobs.items()
                  if name.startswith('prepared/postimages/')}
    need(len(postimages) == 24, 'EXACT_TWENTY_FOUR_POSTIMAGES')
    return manifest, blobs, postimages, input_ref


def bookend(rows):
    for row in rows:
        _, _, current = read(row['ref']['path'], row['ref'])
        need(current == row['f9'], 'ORIGINAL_INPUT_METADATA_CHANGED:' + row['ref']['path'])


def prepare():
    destination = ROOT / 'candidate'
    need(not destination.exists(), 'CREATE_ONLY_CANDIDATE_ALREADY_EXISTS')
    manifest, blobs, postimages, input_ref = load_inputs()
    originals = {}
    bookends = []
    for row in manifest['source_files']:
        name = relative(row['local'], 'originals')
        need(name not in originals, 'DUPLICATE_ORIGINAL_SOURCE')
        raw, pin, f9 = read(row['origin']['path'], row['origin'])
        originals[name] = (raw, pin)
        bookends.append({'ref': pin, 'f9': f9})
    need(set(postimages).issubset(originals), 'POSTIMAGE_HAS_NO_REVIEWED_ORIGINAL')
    source = {name: postimages.get(name, raw) for name, (raw, _) in originals.items()}
    for name, raw in source.items():
        if name.endswith('.py'):
            compile(raw, name, 'exec')
    for name, function in RETIRED:
        tree = ast.parse(source[name])
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
        # The old runtime entry must still refuse before its original first action.
        raises = [n for n in node.body[:2] if isinstance(n, ast.Raise)]
        need(len(raises) == 1 and RETIRE_REASON in ast.unparse(raises[0]), 'GALLERY_RETIREMENT_GUARD_MISSING')
    preparations = {}
    skipped = []
    for row in manifest['preparation_bookends']:
        raw, pin, f9 = read(row['pin']['path'], row['pin'], maximum=131072)
        bookends.append({'ref': pin, 'f9': f9})
        packet = json.loads(raw)
        group = Path(pin['path']).parent.name
        if group not in ENTRIES:
            skipped.append({'group': group, 'original_preparation': pin,
                'adopted': False, 'reason': 'Original display wrapper needs its own binding' if group.startswith('camera')
                else 'Old modified Gallery runtime remains retired; current official image consumer is separate'})
            continue
        need(isinstance(packet['files'], list) and isinstance(packet['origins'], list)
             and packet['Android_execution_authorized_by_publication'] is False
             and packet['whole_app_business_accepted'] is False, 'ORIGINAL_PREPARATION_SOURCE_ONLY_REQUIRED')
        for old_ref in packet['files']:
            name = group + '/' + Path(old_ref['path']).name
            need(name in originals and old_ref == originals[name][1], 'EXACT_ORIGINAL_PREPARATION_MEMBERSHIP')
        for old_ref in packet['origins']:
            _, origin_ref, origin_f9 = read(old_ref['path'], old_ref)
            bookends.append({'ref': origin_ref, 'f9': origin_f9})
        preparations[group] = (packet, pin)
    need(set(preparations) == set(ENTRIES), 'EXACT_SEVEN_PREPARATION_CLOSURES')
    bookend(bookends)
    mkdir(destination)
    metadata_refs = [input_ref]
    for name in ('SOURCE-CONTRACT.json', 'TRANSFORM.json'):
        metadata_refs.append(write(destination / 'metadata' / name, blobs['prepared/' + name]))
    sources = {}
    for name, raw in sorted(source.items()):
        sources[name] = write(destination / 'sources' / name, raw)
    new_preps = []
    for group, (original, original_ref) in sorted(preparations.items()):
        packet = copy.deepcopy(original)
        packet['files'] = [sources[group + '/' + Path(row['path']).name] for row in original['files']]
        packet['origins'] += [original_ref] + metadata_refs
        packet['source_rebind'] = {
            'schema': 'pocket4-cp3a-reviewed-source-bootstrap-rebind-v1', 'commit': COMMIT,
            'original_preparation': original_ref, 'reviewed_input_packet': input_ref,
            'source_only': True, 'Android_actions': 0, 'runtime_qualified': False,
            'whole_app_business_accepted': False, 'historical_runtime_credit_transferred': False,
            'runtime_prerequisites_preserved': True,
        }
        if 'source_graph_generation' in packet:
            packet['source_graph_generation'] = 'CP3A-review-20261120-runtimeaudit-r1'
        preparation_ref = write(destination / 'preparations' / (group + '.json'), encoded(packet))
        new_preps.append({'group': group, 'source_files': len(packet['files']),
            'preparation': preparation_ref, 'entry': sources[group + '/' + ENTRIES[group]],
            'inspection': 'existing-bootstrap-function' if ENTRIES[group] == 'app_entry.py' else 'existing-inspect-source-CLI'})
    bookend(bookends)
    result = {'schema': 'pocket4-cp3a-source-bootstrap-materialization-v1',
        'source_only': True, 'repository': REPO, 'commit': COMMIT, 'inputs': input_ref,
        'source_files': sources, 'source_file_count': len(sources), 'postimage_count': len(postimages),
        'original_input_bookends': bookends, 'preparations': new_preps, 'unadopted_preparations': skipped,
        'Android_actions': 0, 'runtime_qualified': False, 'production_ready': False,
        'current_or_selector_updated': False, 'gallery_retirement_guards': len(RETIRED),
        'remaining_runtime_prerequisites': [
            'Original apexd preconfiguration target OFD and valid provider/guest association',
            'Real BLKRASET/sysfs, dm-verity/EIO and original APEX activation',
            'Fresh CP3A Calendar install/data custody and provider cleanup qualification',
            'Current official Gallery runtime image consumer and visual/business acceptance',
            'All required original application business acceptance cases on current Main',
        ]}
    manifest_ref = write(destination / 'MANIFEST.json', encoded(result))
    print(json.dumps({'manifest': manifest_ref, 'source_files': len(sources),
                      'preparations': len(new_preps), 'source_only': True}, sort_keys=True))


IHG_INSPECT = '''import json,sys,types
from pathlib import Path
p=Path(sys.argv[1]); raw=p.read_bytes()
m=types.ModuleType("cp3a_source_inspection"); m.__file__=str(p)
exec(compile(raw,str(p),"exec"),m.__dict__)
c,packet,ref=m.bootstrap(types.SimpleNamespace(preparation=Path(sys.argv[2]),expect_preparation_sha256=sys.argv[3]))
print(json.dumps({"source_preparation":ref,"source_files":len(packet["files"]),"source_entrypoints_present":True,"Android_UI_actions":0,"source_publication_authorizes_Android":False,"whole_app_business_accepted":False,"inspection":"existing-bootstrap-function"},sort_keys=True))
'''


def run_inspection(entry, preparation, expected=None):
    # Exact fixed metadata-only modes. Never forward arbitrary requests or argv.
    argv = ['/usr/bin/python3', '-I', '-B']
    if Path(entry['path']).name == 'app_entry.py':
        argv += ['-c', IHG_INSPECT, entry['path'], preparation['path'], expected or preparation['sha256']]
    else:
        argv += [entry['path'], '--preparation', preparation['path'], '--expect-preparation-sha256',
                 expected or preparation['sha256'], 'inspect-source']
    run = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
                         env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, check=False)
    need(len(run.stdout) + len(run.stderr) <= 65536, 'INSPECTION_OUTPUT_BOUND')
    return {'returncode': run.returncode, 'stdout': run.stdout.decode(), 'stderr': run.stderr.decode(),
            'mode': 'existing-bootstrap-function' if Path(entry['path']).name == 'app_entry.py' else 'inspect-source'}


def verify(expected_manifest_sha256):
    manifest_path = ROOT / 'candidate' / 'MANIFEST.json'
    raw, manifest_ref, _ = read(manifest_path)
    need(manifest_ref['sha256'] == expected_manifest_sha256, 'EXTERNAL_MANIFEST_PIN_CHANGED')
    manifest = json.loads(raw)
    load_inputs()
    for pin in manifest['source_files'].values():
        read(pin['path'], pin)
    bookend(manifest['original_input_bookends'])
    result = {'schema': 'pocket4-cp3a-original-source-bootstrap-verification-v1',
        'manifest': manifest_ref, 'source_only': True, 'positive': [], 'negative': [],
        'Android_actions': 0, 'runtime_qualified': False, 'production_ready': False,
        'current_or_selector_updated': False}
    for row in manifest['preparations']:
        read(row['entry']['path'], row['entry'])
        read(row['preparation']['path'], row['preparation'])
        run = run_inspection(row['entry'], row['preparation'])
        need(run['returncode'] == 0, 'ORIGINAL_SOURCE_BOOTSTRAP_FAILED:' + row['group'] + ':' + run['stderr'])
        value = json.loads(run['stdout'])
        need(value['source_preparation'] == row['preparation']
             and value['source_files'] == row['source_files']
             and value['Android_UI_actions'] == 0
             and value['source_publication_authorizes_Android'] is False
             and value['whole_app_business_accepted'] is False, 'INSPECTION_OUTPUT_SCOPE_CHANGED')
        if Path(row['entry']['path']).name == 'camera_entry.py':
            need(value['Main_actions'] == 0 and value['historical_runtime_authority_transferred'] is False
                 and value['scope'] == 'original_single_photo_two_normal_launches_and_persistence',
                 'CAMERA_INSPECTION_OUTPUT_SCOPE_CHANGED')
        else:
            need(value['source_entrypoints_present'] is True, 'SOURCE_ENTRYPOINTS_MISSING')
        result['positive'].append({'group': row['group'], **run})
    chosen = next(row for row in manifest['preparations'] if row['group'].startswith('business-system-'))
    old_raw, _, _ = read(chosen['preparation']['path'], chosen['preparation'])
    good = json.loads(old_raw)
    errors = [
        ('wrong-external-preparation-sha', good, '0' * 64, 'EXTERNAL_FROZEN_SYSTEM_PREPARATION_PIN_REQUIRED'),
        ('duplicate-common-source', copy.deepcopy(good), None, 'ONE_FROZEN_COMMON_SOURCE_REQUIRED'),
        ('wrong-profile-source-sha', copy.deepcopy(good), None, 'REFERENCE_CHANGED'),
        ('wrong-preparation-schema', copy.deepcopy(good), None, 'COMPLETE_REVIEWED_NEW_SYSTEM_SOURCE_REQUIRED'),
        ('publication-must-not-authorize-android', copy.deepcopy(good), None, 'COMPLETE_REVIEWED_NEW_SYSTEM_SOURCE_REQUIRED'),
    ]
    errors[1][1]['files'].append(next(row for row in good['files'] if Path(row['path']).name == 'app_common.py'))
    next(row for row in errors[2][1]['files'] if Path(row['path']).name == 'system_profiles.py')['sha256'] = '0' * 64
    errors[3][1]['schema'] = 'not-a-preparation'
    errors[4][1]['Android_execution_authorized_by_publication'] = True
    for name, packet, expected, reason in errors:
        pin = write(ROOT / 'negative-controls' / (name + '.json'), encoded(packet))
        run = run_inspection(chosen['entry'], pin, expected)
        need(run['returncode'] != 0 and reason in run['stderr'] and not run['stdout'],
             'NEGATIVE_CONTROL_DID_NOT_REFUSE:' + name)
        result['negative'].append({'name': name, 'preparation': pin, 'expected_error': reason, **run})
    # A second materialization must refuse; it may never overwrite even our own candidate.
    try:
        prepare()
    except RuntimeError as error:
        need(str(error) == 'CREATE_ONLY_CANDIDATE_ALREADY_EXISTS', 'UNEXPECTED_CREATE_ONLY_ERROR')
        result['negative'].append({'name': 'refuse-existing-candidate', 'expected_error': str(error), 'refused': True})
    else:
        raise RuntimeError('CREATE_ONLY_CANDIDATE_WAS_OVERWRITTEN')
    bookend(manifest['original_input_bookends'])
    for pin in manifest['source_files'].values():
        read(pin['path'], pin)
    for row in manifest['preparations']:
        read(row['preparation']['path'], row['preparation'])
    result['original_input_bookends_unchanged'] = True
    result['positive_count'] = len(result['positive'])
    result['negative_count'] = len(result['negative'])
    result['verified'] = True
    result_ref = write(ROOT / 'verification.json', encoded(result))
    print(json.dumps({'verification': result_ref, 'positive_count': result['positive_count'],
        'negative_count': result['negative_count'], 'source_only': True,
        'Android_actions': 0, 'runtime_qualified': False}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify'))
    parser.add_argument('--expect-manifest-sha256')
    args = parser.parse_args()
    need(ROOT.is_dir() and ROOT.resolve() == ROOT, 'EXISTING_FIXED_TASK_DIRECTORY_REQUIRED')
    os.umask(0o077)
    if args.mode == 'prepare':
        need(args.expect_manifest_sha256 is None, 'PREPARATION_HAS_NO_EXISTING_MANIFEST_PIN')
        prepare()
    else:
        need(isinstance(args.expect_manifest_sha256, str)
             and len(args.expect_manifest_sha256) == 64
             and all(c in '0123456789abcdef' for c in args.expect_manifest_sha256),
             'EXTERNAL_MANIFEST_PIN_REQUIRED')
        verify(args.expect_manifest_sha256)


if __name__ == '__main__':
    main()
