#!/usr/bin/python3 -I
"""Current Camera video entry. Default inspection has no runtime operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

COMMON_PIN = (38256, '6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0')
SOURCE_NAMES = {'app_common.py', 'app_flow.py', 'app_runtime.py', 'camera_audio_binding.py',
    'camera_audio_challenge.py', 'camera_audio_channel.py', 'camera_audio_runtime.py',
    'camera_audio_supervisor.py', 'camera_base_session.py', 'camera_case.py', 'camera_decode.py',
    'camera_entry.py', 'camera_flow.py', 'camera_guard.py', 'camera_observations.py',
    'camera_owner_core.py', 'camera_photo_model.py', 'camera_plan.py', 'camera_player_binding.py',
    'camera_policy.py', 'camera_profiles.py', 'camera_runtime.py', 'camera_session.py',
    'camera_sound_preservation.py', 'camera_transport.py', 'camera_ui.py', 'camera_video_driver.py',
    'camera_video_media.py', 'camera_video_state.py'}

def read(path, maximum):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path: raise RuntimeError('CANONICAL_CURRENT_VIDEO_INPUT')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
            raise RuntimeError('BOUNDED_REGULAR_CURRENT_VIDEO_INPUT')
        raw = bytearray()
        while len(raw) < before.st_size:
            block = os.read(fd, min(65536, before.st_size - len(raw)))
            if not block: raise RuntimeError('SHORT_CURRENT_VIDEO_INPUT')
            raw.extend(block)
        after, named = os.fstat(fd), path.lstat()
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if os.read(fd, 1) != b'' or not all(getattr(before, k) == getattr(after, k) == getattr(named, k) for k in keys):
            raise RuntimeError('CURRENT_VIDEO_INPUT_CHANGED_DURING_HELD_READ')
        return bytes(raw)
    finally: os.close(fd)

def bootstrap(args):
    if re.fullmatch('[0-9a-f]{64}', args.expect_preparation_sha256 or '') is None:
        raise RuntimeError('EXTERNAL_REVIEWED_VIDEO_PREPARATION_PIN_REQUIRED')
    raw = read(args.preparation, 131072)
    if hashlib.sha256(raw).hexdigest() != args.expect_preparation_sha256: raise RuntimeError('VIDEO_PREPARATION_PIN_CHANGED')
    packet = json.loads(raw)
    if type(packet) is not dict or packet.get('schema') != 'pocket4-current-camera-video-preparation-v1' or (
            type(packet.get('files')) is not list or len(packet['files']) != len(SOURCE_NAMES)
            or {Path(r['path']).name for r in packet['files']} != SOURCE_NAMES):
        raise RuntimeError('EXACT_CURRENT_VIDEO_SOURCE_SET')
    refs = {Path(r['path']).name: r for r in packet['files']}; sources = {}
    for name, ref in refs.items():
        if set(ref) != {'path', 'bytes', 'sha256'}: raise RuntimeError('EXACT_VIDEO_SOURCE_REFERENCE')
        data = read(ref['path'], 262144)
        if (len(data), hashlib.sha256(data).hexdigest()) != (ref['bytes'], ref['sha256']):
            raise RuntimeError('FROZEN_VIDEO_COMPONENT_CHANGED:' + name)
        sources[name] = data
    if (refs['app_common.py']['bytes'], refs['app_common.py']['sha256']) != COMMON_PIN:
        raise RuntimeError('EXACT_CURRENT_HOST_COMMON_LIBRARY')
    if read(Path(__file__).resolve(), 262144) != sources['camera_entry.py']:
        raise RuntimeError('ACTUAL_VIDEO_ENTRY_NOT_THE_REVIEWED_SOURCE')
    def load(name):
        module = types.ModuleType('camera_video_prepared_' + Path(name).stem); module.__file__ = refs[name]['path']
        exec(compile(sources[name], module.__file__, 'exec'), module.__dict__); return module
    c = load('app_common.py'); prep = {'path': args.preparation, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    planner = load('camera_plan.py'); planner.preparation(c, prep)
    return c, packet, prep, planner

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True); parser.add_argument('--expect-preparation-sha256', required=True)
    parser.add_argument('mode', choices=('inspect-source', 'identity', 'plan', 'execute', 'execute-worker'),
        nargs='?', default='inspect-source')
    parser.add_argument('--request'); parser.add_argument('--expect-request-sha256'); parser.add_argument('--output')
    parser.add_argument('--role', choices=('camera', 'player', 'native-helper'))
    parser.add_argument('--acoustic-fd', type=int); parser.add_argument('--acoustic-parent')
    parser.add_argument('--expect-acoustic-parent-sha256')
    args = parser.parse_args(); c, packet, prep, planner = bootstrap(args)
    acoustic_args = (args.acoustic_fd, args.acoustic_parent, args.expect_acoustic_parent_sha256)
    if args.mode == 'inspect-source':
        c.need(args.request is args.expect_request_sha256 is args.output is args.role is None
            and acoustic_args == (None, None, None), 'CURRENT_VIDEO_SOURCE_INSPECTION_HAS_NO_RUNTIME_INPUTS')
        witness = c.EvidenceWitness([prep])
        try: witness.verify(); count = len(witness.rows)
        finally: witness.close()
        print(json.dumps({'source_preparation': prep, 'source_files': len(packet['files']), 'evidence_files': count,
            'scope': 'one_current_recorded_clip_CAMCORDER_full_decode_exact_URI_Gallery_physical_audio_playback',
            'native_launches': 3, 'audio_challenge_emissions': 1, 'playback_phase_host_emissions': 0,
            'Main_actions': 0, 'Android_UI_actions': 0, 'runtime_qualified': False,
            'whole_app_business_accepted': False, 'camera_recovery_preparation_pending': True,
            'source_publication_authorizes_Android': False}, sort_keys=True)); return 0
    c.need(os.getuid() == os.geteuid() == 0 and args.request and args.expect_request_sha256
        and re.fullmatch('[0-9a-f]{64}', args.expect_request_sha256), 'EXPLICIT_ROOT_CURRENT_VIDEO_REQUEST_AND_PIN')
    raw, request_ref = c.regular(args.request, 131072)
    c.need(request_ref['sha256'] == args.expect_request_sha256, 'CURRENT_VIDEO_REQUEST_PIN_CHANGED'); request = c.parse(raw)
    if args.mode == 'identity':
        c.need(args.output and args.role and acoustic_args == (None, None, None), 'EXACT_CURRENT_VIDEO_IDENTITY_ARGUMENTS')
        profiles = planner.named(c, packet, 'camera_profiles.py')
        profile = {'camera': profiles.CAMERA, 'player': profiles.PLAYER, 'native-helper': profiles.HELPER}[args.role]
        c.need(set(request) == {'baseline', 'qualification'}
            and c.parse(c.read_ref(request['qualification']))['source_manifest'] == c.SUPPORT_REF, 'EXACT_CURRENT_HOST_MAIN_BASELINE')
        entry = next(r for r in packet['files'] if Path(r['path']).name == 'camera_entry.py')
        result = c.collect_identity(request, args.output, profile, entry)
    elif args.mode == 'plan':
        c.need(args.output and args.role is None and acoustic_args == (None, None, None), 'EXACT_NEW_CAMERA_VIDEO_FACTORY')
        result = planner.create(c, 'camera_video', request, args.output, prep)
    else:
        c.need(args.output is args.role is None and set(request) == {'base_plan'}, 'EXACT_CURRENT_VIDEO_EXECUTION_REQUEST')
        base = c.parse(c.read_ref(request['base_plan']))
        c.need(base['source_preparation'] == prep, 'ACTUAL_EXECUTION_PLAN_USES_THIS_EXTERNAL_PREPARATION')
        # This trusted planner checks every task copy against the external prep
        # before any copied task module can execute.
        task = planner.source_packet(c, base, packet)['camera']
        components = {Path(ref['path']).name: c.module(ref, 'camera_video_task_' + Path(ref['path']).stem)
            for ref in task['files'] if Path(ref['path']).name != 'camera_entry.py'}
        if args.mode == 'execute':
            c.need(acoustic_args == (None, None, None), 'ONLY_SUPERVISOR_CAN_SUPPLY_ACOUSTIC_AUTHORITY')
            supervisor = components['camera_audio_supervisor.py'].make_supervisor(components['camera_owner_core.py'])
            owner = supervisor(c, request['base_plan'], prep, components, request_ref, packet)
            ref, value = owner.run()
        else:
            c.need(type(args.acoustic_fd) is int and args.acoustic_fd > 2 and args.acoustic_parent
                and re.fullmatch('[0-9a-f]{64}', args.expect_acoustic_parent_sha256 or ''), 'ACTUAL_INHERITED_ACOUSTIC_PARENT_ONLY')
            parent = c.regular(args.acoustic_parent, 131072, contents=False)
            c.need(parent['sha256'] == args.expect_acoustic_parent_sha256, 'CURRENT_ACOUSTIC_PARENT_PIN')
            client = components['camera_audio_channel.py'].AcousticClient(c, components['app_runtime.py'],
                args.acoustic_fd, parent, request['base_plan'], prep, base)
            try:
                ref, value = components['camera_case.py'].execute(c, request['base_plan'], components, client)
            finally:
                # Admission can fail before the case installs its own finally.
                # This descriptor-only close never retries an acoustic action.
                if not client.closed: client.close()
        print(json.dumps({'result': ref, 'state': value['state'],
            'case_business_success_verified': value['case_business_success_verified'],
            'outcome_unknown': value['outcome_unknown'], 'whole_app_business_accepted': False}, sort_keys=True))
        return 0 if value['case_business_success_verified'] else (1 if args.mode == 'execute-worker' else 4)
    print(json.dumps({'result': result, 'whole_app_business_accepted': False}, sort_keys=True)); return 0

if __name__ == '__main__':
    raise SystemExit(main())
