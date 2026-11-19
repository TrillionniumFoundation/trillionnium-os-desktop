#!/usr/bin/python3 -I
"""Explicit new-Main Camera photo entry; default inspection has no live actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

COMMON_PIN = (38256, '6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0')
SOURCE_NAMES = {'app_common.py', 'app_flow.py', 'app_runtime.py', 'camera_case.py', 'camera_entry.py',
    'camera_flow.py', 'camera_guard.py', 'camera_observations.py', 'camera_photo_model.py',
    'camera_photo_trial.py', 'camera_plan.py', 'camera_policy.py', 'camera_profiles.py',
    'camera_runtime.py', 'camera_session.py', 'camera_transport.py', 'camera_ui.py'}


def read(path, maximum):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise RuntimeError('EXACT_CANONICAL_CAMERA_SOURCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
            raise RuntimeError('BOUNDED_REGULAR_CAMERA_INPUT')
        raw = bytearray()
        while len(raw) < before.st_size:
            part = os.read(fd, min(65536, before.st_size - len(raw)))
            if not part:
                raise RuntimeError('SHORT_CAMERA_INPUT_READ')
            raw.extend(part)
        after = os.fstat(fd); named = path.lstat()
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if os.read(fd, 1) != b'' or not all(getattr(before, k) == getattr(after, k) == getattr(named, k) for k in fields):
            raise RuntimeError('CAMERA_INPUT_CHANGED_DURING_HELD_READ')
        return bytes(raw)
    finally:
        os.close(fd)


def bootstrap(args):
    if re.fullmatch('[0-9a-f]{64}', args.expect_preparation_sha256 or '') is None:
        raise RuntimeError('EXTERNAL_REVIEWED_CAMERA_PREPARATION_PIN_REQUIRED')
    raw = read(args.preparation, 131072)
    if hashlib.sha256(raw).hexdigest() != args.expect_preparation_sha256:
        raise RuntimeError('CAMERA_PREPARATION_PIN_CHANGED')
    packet = json.loads(raw)
    if (type(packet) is not dict or packet.get('schema') != 'pocket4-final-camera-app-preparation-v1'
            or type(packet.get('files')) is not list or len(packet['files']) != len(SOURCE_NAMES)
            or {Path(r['path']).name for r in packet['files']} != SOURCE_NAMES):
        raise RuntimeError('EXACT_REVIEWED_CAMERA_COMPONENT_SET')
    by_name = {Path(r['path']).name: r for r in packet['files']}
    # No task module is imported before the whole external source packet has
    # been read and verified. The fixed common library is independently pinned.
    source_bytes = {}
    for name, ref in by_name.items():
        if set(ref) != {'path', 'bytes', 'sha256'}:
            raise RuntimeError('EXACT_CAMERA_SOURCE_REF_FIELDS')
        value = read(ref['path'], 262144)
        if (len(value), hashlib.sha256(value).hexdigest()) != (ref['bytes'], ref['sha256']):
            raise RuntimeError('FROZEN_CAMERA_COMPONENT_CHANGED:' + name)
        source_bytes[name] = value
    if (by_name['app_common.py']['bytes'], by_name['app_common.py']['sha256']) != COMMON_PIN:
        raise RuntimeError('CAMERA_REQUIRES_THE_ORIGINAL_QUALIFIED_COMMON_LIBRARY')
    actual = read(Path(__file__).resolve(), 262144)
    if actual != source_bytes['camera_entry.py']:
        raise RuntimeError('ACTUAL_CAMERA_ENTRY_NOT_THE_REVIEWED_SOURCE')
    def load(name):
        value = types.ModuleType('camera_prepared_' + Path(name).stem); value.__file__ = by_name[name]['path']
        exec(compile(source_bytes[name], value.__file__, 'exec'), value.__dict__)
        return value
    c = load('app_common.py')
    prep = {'path': args.preparation, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    plan = load('camera_plan.py'); plan.preparation(c, prep)
    return c, packet, prep, plan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation', required=True); p.add_argument('--expect-preparation-sha256', required=True)
    p.add_argument('mode', choices=('inspect-source', 'identity', 'plan', 'execute'), nargs='?', default='inspect-source')
    p.add_argument('--request'); p.add_argument('--expect-request-sha256')
    p.add_argument('--role', choices=('camera', 'native-helper')); p.add_argument('--output')
    args = p.parse_args(); c, packet, prep, planner = bootstrap(args)
    if args.mode == 'inspect-source':
        c.need(args.request is None and args.expect_request_sha256 is None and args.role is None and args.output is None,
               'CAMERA_INSPECTION_HAS_NO_RUNTIME_INPUT')
        print(json.dumps({'source_preparation': prep, 'source_files': len(packet['files']),
            'scope': 'original_single_photo_two_normal_launches_and_persistence',
            'new_business_seconds': 360, 'new_cleanup_seconds': 40, 'native_launches': 2, 'shutters': 1,
            'Main_actions': 0, 'Android_UI_actions': 0, 'historical_runtime_authority_transferred': False,
            'video_audio_playback_preparation_pending': True, 'recovery_preparation_pending': True,
            'source_publication_authorizes_Android': False, 'whole_app_business_accepted': False}, sort_keys=True))
        return 0
    c.need(os.getuid() == os.geteuid() == 0 and args.request and args.expect_request_sha256
        and re.fullmatch('[0-9a-f]{64}', args.expect_request_sha256), 'EXPLICIT_CURRENT_MAIN_REQUEST_AND_PIN')
    raw, request_ref = c.regular(args.request, 131072)
    c.need(request_ref['sha256'] == args.expect_request_sha256, 'CAMERA_REQUEST_PIN_CHANGED')
    request = c.parse(raw)
    if args.mode == 'identity':
        c.need(args.role is not None and args.output is not None, 'CURRENT_CAMERA_METADATA_ONLY_IDENTITY_ARGUMENTS')
        profiles = planner.named(c, packet, 'camera_profiles.py')
        target = {'camera': profiles.CAMERA, 'native-helper': profiles.NATIVE_HELPER}[args.role]
        c.need(set(request) == {'baseline', 'qualification'} and
            c.parse(c.read_ref(request['qualification'])).get('source_manifest') == c.SUPPORT_REF,
            'CURRENT_R5_BASELINE_FOR_CAMERA_AND_NATIVE_HELPER_IDENTITIES')
        source = next(r for r in packet['files'] if Path(r['path']).name == 'camera_entry.py')
        result = c.collect_identity(request, args.output, target, source)
    elif args.mode == 'plan':
        c.need(args.role is None and args.output is not None, 'EXACT_NEW_CAMERA_PLAN_FACTORY_ARGUMENTS')
        result = planner.create(c, 'camera_photo', request, args.output, prep)
    else:
        c.need(args.role is None and args.output is None and request['source_preparation'] == prep,
               'EXECUTION_OF_ONLY_THIS_EXTERNALLY_REVIEWED_CAMERA_PLAN')
        task = planner.source_packet(c, request, packet)
        components = {Path(ref['path']).name: c.module(ref, 'camera_task_' + Path(ref['path']).stem)
                      for ref in task['files'] if Path(ref['path']).name != 'camera_entry.py'}
        ref, value = components['camera_case.py'].execute(c, request_ref, components)
        print(json.dumps({'result': ref, 'state': value['state'],
            'photo_capture_persistence_verified': value['photo_capture_persistence_verified'],
            'visual_review_required': True, 'whole_app_business_accepted': False}, sort_keys=True))
        return 0 if value['photo_capture_persistence_verified'] else 4
    print(json.dumps({'result': result, 'whole_app_business_accepted': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
