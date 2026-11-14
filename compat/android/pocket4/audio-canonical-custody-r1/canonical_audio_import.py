"""Consume immutable offload evidence through independently pinned local copies.

The original paths, file identities, process IDs and cgroups stay historical.
The destination reader observes only destination files, and returns those
actual pins to the stage gate. No source-host identity becomes a local one.
"""
import json
from pathlib import PurePosixPath
import re
import stat

FLAGS = ('normal_complete_audio_apex_build', 'signature_and_hashtree_verified',
         'payload_file_contents_verified', 'payload_membership_verified',
         'payload_contents_verified', 'complete_apex_qualified')
JSON_ROLES = frozenset(('qualification', 'contents', 'compiled', 'H_request',
                       'H_started', 'H_exit', 'source_manifest', 'specification'))
ROLES = JSON_ROLES | {'whole_apex', 'H_stdout', 'H_stderr',
                      'source_qualifier', 'source_join'}


def need(value, message):
    if not value:
        raise ValueError(message)


def normal_path(value):
    need(type(value) is str and value and '\0' not in value,
         'explicit normal absolute path required')
    path = PurePosixPath(value)
    need(path.is_absolute() and str(path) == value and '..' not in path.parts,
         'noncanonical file path refused')
    return path


def pin(row, *, empty=False):
    need(type(row) is dict and {'path', 'bytes', 'sha256'} <= set(row),
         'complete file pin required')
    normal_path(row['path'])
    need(type(row['bytes']) is int and row['bytes'] >= (0 if empty else 1),
         'strict file length required')
    need(type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']),
         'exact SHA256 required')
    return {key: row[key] for key in ('path', 'bytes', 'sha256')}


def content_equal(left, right, *, empty=False):
    a, b = pin(left, empty=empty), pin(right, empty=empty)
    return (a['bytes'], a['sha256']) == (b['bytes'], b['sha256'])


def qualify(io, witness, receipt, expected_artifact, *, allowed_root,
            origin_host, destination_host, canonical_owner_uid,
            reviewed_source_hashes, guard):
    """Validate a source-bound import without opening an original host path.

    ``receipt`` must already have been read through the caller's pinned stage
    witness. ``guard`` supplies the existing strict raw-exit and complete-APEX
    validators, loaded from the stage's reviewed source manifest. This function
    performs no writes, process inspection, build, installation or deployment.
    """
    need(type(receipt) is dict
         and receipt.get('schema') == 'pocket4-audio-canonical-whole-apex-qualification-v1'
         and receipt.get('state') == 'CANONICAL_BYTES_BOUND_RUNTIME_PENDING',
         'actual canonical import receipt required')
    need(type(origin_host) is str and type(destination_host) is str
         and origin_host and destination_host and origin_host != destination_host
         and receipt['origin_build_host'] == origin_host
         and receipt['destination_host'] == destination_host,
         'explicit distinct build and destination hosts required')
    need(receipt['origin_host_authority_inherited'] is False
         and receipt['runtime_qualified'] is False
         and receipt['production_deployment_performed'] is False
         and receipt['all_canonical_copies_read_back'] is True,
         'copied evidence cannot grant local process or runtime authority')
    need(all(receipt[name] is True for name in FLAGS), 'canonical complete APEX is pending')
    root = normal_path(receipt['canonical_root'])
    allowed = normal_path(str(allowed_root))
    need(root != allowed and root.is_relative_to(allowed), 'owned canonical child directory required')
    need(type(canonical_owner_uid) is int and canonical_owner_uid >= 0,
         'explicit destination owner required')
    need(type(reviewed_source_hashes) is dict and set(reviewed_source_hashes)
         == {'qualify_audio_whole_apex.py', 'apex_evidence_join.py'},
         'both independently reviewed qualifier sources required')
    mappings = receipt['files']
    need(type(mappings) is dict and set(mappings) == ROLES, 'exact complete custody role set required')
    documents, actual, origins = {}, {}, {}
    source_paths, local_paths = set(), set()
    for role in sorted(ROLES):
        pair = mappings[role]
        need(type(pair) is dict and set(pair) == {'origin', 'canonical'}, 'explicit origin/local pair required')
        empty = role == 'H_stderr'
        origin = pin(pair['origin'], empty=empty)
        # Origin identity metadata is deliberately not accepted as a local pin.
        need(set(pair['origin']) == {'path', 'bytes', 'sha256'}, 'historical identity must not impersonate a destination file')
        local = pin(pair['canonical'], empty=empty)
        path = normal_path(local['path'])
        need(path != root and path.is_relative_to(root)
             and local['path'] != origin['path']
             and origin['path'] not in source_paths and local['path'] not in local_paths,
             'unique explicit destination copies required')
        source_paths.add(origin['path']); local_paths.add(local['path'])
        need(content_equal(origin, local, empty=empty), 'canonical copy differs from the original bytes')
        value, observed = witness.read(pair['canonical'], json=role in JSON_ROLES)
        need(pin(observed, empty=empty) == local, 'witness read another canonical file')
        identity = observed.get('identity')
        need(type(identity) is list and len(identity) == 9 and all(type(x) is int for x in identity)
             and stat.S_ISREG(identity[2]) and identity[3] == canonical_owner_uid
             and identity[5] == 1 and stat.S_IMODE(identity[2]) & 0o022 == 0,
             'actual canonical regular-file ownership or protection differs')
        origins[role] = origin; actual[role] = observed
        if role in JSON_ROLES:
            documents[role] = value
    need(pin(expected_artifact) == pin(actual['whole_apex']),
         'candidate artifact is not the actual canonical copy')
    qualification = documents['qualification']
    need(qualification['schema'] == 'pocket4-audio-whole-apex-qualification-v1'
         and qualification['state'] == 'COMPLETE_APEX_QUALIFIED_RUNTIME_PENDING'
         and qualification['errors'] == [] and qualification['signals'] == []
         and qualification['all_command_children_retired'] is True
         and qualification['resource_gate_passed'] is True
         and qualification['original_build_host'] == origin_host
         and qualification['host_generation_inherited'] is False,
         'actual complete retired source-host qualification required')
    for name in FLAGS:
        need(qualification[name] is True, 'original APEX qualification is incomplete')
    need(pin(qualification['actual_apex']) == origins['whole_apex']
         == pin(qualification['copy']['source']), 'whole APEX original provenance differs')
    payload = qualification['payload_contents']
    need(pin(payload['actual_file_contents_result']) == origins['contents']
         and pin(payload['compiled_bridge_binding_result']) == origins['compiled']
         and payload['compiled_bridge_binding'] == documents['compiled'],
         'copied parser/compiled evidence does not match the immutable original')
    guard.validate_complete_apex(qualification, origins['whole_apex'], documents['contents'])
    need(pin(qualification['qualifier_source_manifest']) == origins['source_manifest']
         and pin(qualification['specification']) == origins['specification'],
         'qualifier source/specification provenance differs')
    sources = documents['source_manifest']
    need(sources['schema'] == 'audio-whole-apex-qualification-sources-v1'
         and set(sources['files']) == set(reviewed_source_hashes), 'complete original source manifest required')
    for name, role in (('qualify_audio_whole_apex.py', 'source_qualifier'),
                       ('apex_evidence_join.py', 'source_join')):
        need(pin(sources['files'][name]) == origins[role]
             and origins[role]['sha256'] == reviewed_source_hashes[name],
             'actual qualifier source differs from independently reviewed bytes')
    request, started, exited = (documents[key] for key in ('H_request', 'H_started', 'H_exit'))
    guard.validate_raw_exit(exited, request, started, expected_exit_code=0,
        expected_at_unix_ms=exited['at_unix_ms'],
        expected_stream_bytes={key: actual['H_' + key]['bytes'] for key in ('stdout', 'stderr')})
    need(request['executable'] == '/usr/bin/python3' and request['args'] == [
        '-I', '-B', origins['source_qualifier']['path'], '--spec', origins['specification']['path'],
        '--sources', origins['source_manifest']['path'], '--output',
        str(normal_path(origins['qualification']['path']).parent)],
        'actual source-host H did not execute this exact qualifier generation')
    need(type(started['at_unix_ms']) is int and started['at_unix_ms'] > 0
         and all(type(qualification[name]) is int for name in ('started_ns', 'finished_ns'))
         and started['at_unix_ms'] * 1000000 <= qualification['started_ns']
         <= qualification['finished_ns'] < (exited['at_unix_ms'] + 1) * 1000000,
         'original result time is outside the actual qualifier process')
    for stream in ('stdout', 'stderr'):
        # This is a second held read of the already witnessed destination inode.
        observed, raw = io.pinned(actual['H_' + stream], contents=True, single=True)
        need(pin(observed, empty=stream == 'stderr') == pin(actual['H_' + stream], empty=stream == 'stderr'),
             'canonical runtime stream changed')
        if stream == 'stdout':
            lines = raw.decode('utf-8').splitlines()
            need(lines and len(lines) <= 16, 'complete bounded qualifier stdout required')
            terminal = json.loads(lines[-1])
            need(terminal['state'] == qualification['state']
                 and pin(terminal['result']) == origins['qualification']
                 and terminal['complete_apex_qualified'] is True
                 and terminal['runtime_qualified'] is False and terminal['errors'] == [],
                 'actual complete H stdout did not bind this original result')
    specification = documents['specification']
    need(set(specification) == {'full_generation', 'compiled_qualification', 'verifier_controls'}
         and pin(specification['compiled_qualification']['result']) == origins['compiled']
         and qualification['full_raw_H'] == specification['full_generation']['H']
         and qualification['payload_contents']['compiled_qualification_H']
             == specification['compiled_qualification']['H'],
         'whole qualification was built from another source-host generation')
    # Return actual destination JSON pins. Stage gates never reopen source-host
    # paths and never compare copied /proc, cgroup or inode IDs to this machine.
    return {role: pin(actual[role]) for role in sorted(JSON_ROLES)}
