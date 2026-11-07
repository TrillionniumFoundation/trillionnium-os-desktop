#!/usr/bin/env python3
"""Copy only two already qualified private PNGs to a new operator-private directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import time

ROOT = Path('/home/alex/work/pocket4-bilibili-r5-player-geometry-01')
FLOW = Path('/home/alex/work/pocket4-bilibili-owned-qa-r5-flow-9e7c2a173b34236b7f96abc662295fd4')
STEP = FLOW / 'steps/buffer-viewport-01'
OUTPUT = Path('/home/alex/work/pocket4-bilibili-r5-player-geometry-private-crops-01')
NONCE = '9e7c2a173b34236b7f96abc662295fd4'
SOURCE = '6620853a66d298cf1d85b16733f56e564654823bbe8c5e9e566bed4faa5b4ab6'
EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
FILES = {
    'coordinator': (ROOT / 'result.json', 6332, '61f0d5c97d12e9683be3237a813f60e03c2ab882a08b34f7d303e49168d3648b'),
    'stage': (ROOT / 'stage-result.json', 1773, '6c3114b2349c51fa65fad36b976ceb315bb40123db34e5eee09661e6eb667ed8'),
    'navigation': (STEP / 'result.json', 244237, '4ceb318717f554cf2779232846df77b5fe5871cc83e3ef1fff32e50920bbe80d'),
    'cleanup': (FLOW / 'steps/cleanup-01/result.json', 447, '372ebe75220d7a7415e1a2694b5bd4c71c003e4e206cb676ff43ca5302bcb01c'),
    'player-viewport-01.png': (STEP / 'player-viewport-01.png', 493547, '5146498065e5bad3e4bb5350108b40593ece312cb3cad7ec3610db745bac2c95'),
    'player-viewport-02.png': (STEP / 'player-viewport-02.png', 494153, 'dca103f1c5d4bd23355d69a43bdfa1dedc9ee49bff72b4ec78fd56a15dc5f608'),
}
SCOPE_KEYS = ('scope', 'window', 'window_sha256', 'crop', 'surface_bounds',
              'title_text_sha256', 'author_text_sha256', 'full_area_surface_bounds',
              'render_structure_sha256')


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def open_directory(path):
    need(path.is_absolute() and '..' not in path.parts, 'ABSOLUTE_FIXED_DIRECTORY_REQUIRED')
    current = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for name in path.parts[1:]:
            nxt = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                          dir_fd=current)
            os.close(current); current = nxt
        return current
    except BaseException:
        os.close(current)
        raise


class Reader:
    def __init__(self):
        self.started = time.monotonic(); self.total = 0

    def read(self, name):
        need(name in FILES, 'FIXED_SIX_INPUTS_ONLY')
        path, size, expected = FILES[name]
        parent = open_directory(path.parent); fd = None
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            first = os.fstat(fd)
            need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_uid == 0
                 and first.st_gid == 0 and first.st_size == size and size <= 1048576,
                 'EXACT_ROOT_SINGLE_REGULAR_INPUT_REQUIRED')
            chunks = []; count = 0
            while True:
                need(time.monotonic() - self.started < 10, 'READ_DEADLINE')
                part = os.read(fd, min(65536, size + 1 - count))
                if not part:
                    break
                chunks.append(part); count += len(part); self.total += len(part)
                need(count <= size and self.total <= 2097152, 'READ_BYTE_BOUND')
            last = os.fstat(fd)
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid',
                      'st_size', 'st_mtime_ns', 'st_ctime_ns')
            need(count == size and all(getattr(first, k) == getattr(last, k) for k in fields),
                 'ORIGINAL_INPUT_CHANGED_DURING_READ')
            raw = b''.join(chunks); need(sha(raw) == expected, 'EXACT_ORIGINAL_INPUT_HASH_REQUIRED')
            return raw
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)


def validate_observations(c, s, n, cleanup):
    for value in (c, s, n):
        need(value['nonce'] == NONCE and value['source_manifest_sha256'] == SOURCE,
             'ORIGINAL_ATTEMPT_SOURCE_NONCE_CHANGED')
        need(value['ok'] is False and value['secondary_errors'] == [], 'ORIGINAL_FAIL_MUST_STAY_FAIL')
    need(c['Main_before'] == c['Main_after'] == s['Main_before'] == s['Main_after']
         and c['Main_before']['Main_epoch_sha256'] == EPOCH, 'ORIGINAL_MAIN_CHAIN_CHANGED')
    need(s['coordinator_result']['sha256'] == FILES['coordinator'][2]
         and c['cleanup_result']['sha256'] == FILES['cleanup'][2], 'ORIGINAL_PARENT_CHAIN_CHANGED')
    need(n['error'] == {'phase': 'buffer_viewport_observation', 'type': 'RuntimeError',
                       'message': 'VIEWPORT_SCOPE_CHANGED_DURING_CAPTURE'}, 'ORIGINAL_FIRST_ERROR_CHANGED')
    need(n['final_Main_guard_passed'] and n['held_binding_released'] and n['action_lock_released']
         and c['source_and_artifact_unchanged'] and s['source_unchanged'], 'ORIGINAL_FINAL_GATES_REQUIRED')
    need(c['owned_task']['task'] == 920 and cleanup['ok'] and cleanup['new_leaf_removed_and_verified']
         and cleanup['other_tasks_preserved'] and cleanup['task_ids_after'] == [851],
         'ORIGINAL_EXACT_TASK_CLEANUP_REQUIRED')
    record = n['buffer_viewport_observation']
    need(len(record['reads']) == 1 and len(record['viewport_samples']) == 2,
         'EXACT_TWO_PUBLISHED_SAMPLES_REQUIRED')
    before = record['reads'][0]['proof']
    for index, sample in enumerate(record['viewport_samples'], 1):
        after = sample['after_observation']; proof = after['proof']; crop = sample['private_crop']
        name = 'player-viewport-%02d.png' % index; path, size, expected = FILES[name]
        need(sample['index'] == index and sample['private_crop_published'] is True
             and sample['scope_checked_before_and_after'] is True
             and sample['atomic_frame_attribution'] is False and sample['playback_verified'] is False
             and sample['audio_captured'] is False and after['after_state_completed'] is True
             and after['restoration_qualified'] is True, 'PRIOR_CROP_QUALIFICATION_CHAIN_REQUIRED')
        need(all(before[k] == proof[k] for k in SCOPE_KEYS), 'PRIOR_CROP_SCOPE_CHANGED')
        need(crop['path'] == str(path) and crop['bytes'] == size and crop['sha256'] == expected
             and crop['bounds'] == before['crop'] == [320, 45, 1520, 720]
             and crop['width'] == 1200 and crop['height'] == 675 and crop['must_not_enter_Git'] is True,
             'EXACT_PRIVATE_CROP_IDENTITY_REQUIRED')
        need(proof['scope']['package'] == 'tv.danmaku.bili' and proof['scope']['uid'] == 10117
             and proof['scope']['main_epoch_sha256'] == EPOCH, 'ORIGINAL_BILI_SCOPE_REQUIRED')
        before = proof
    failed = record['failed_capture']
    need(failed['index'] == 3 and failed['capture_attempted'] is True
         and failed['private_crop_published'] is False and 'private_crop' not in failed,
         'THIRD_FAILED_CAPTURE_IS_NOT_AN_EXPORT_INPUT')
    need(not all(before[k] == failed['after_observation']['proof'][k] for k in SCOPE_KEYS),
         'ORIGINAL_THIRD_CAPTURE_REJECTION_MUST_REMAIN')


def write_new(directory, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=directory)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view); need(count > 0, 'PRIVATE_EXPORT_SHORT_WRITE'); view = view[count:]
        os.fsync(fd); os.fchmod(fd, 0o400); os.fchown(fd, 1000, 1000)
        actual = os.fstat(fd)
        need(actual.st_uid == actual.st_gid == 1000 and actual.st_nlink == 1
             and actual.st_size == len(raw) and stat.S_IMODE(actual.st_mode) == 0o400,
             'NEW_OPERATOR_PRIVATE_FILE_IDENTITY_REQUIRED')
    finally:
        os.close(fd)


def collect():
    need(os.getuid() == os.geteuid() == 0, 'ROOT_FIXED_INPUT_READ_REQUIRED')
    reader = Reader()
    records = {name: json.loads(reader.read(name)) for name in ('coordinator', 'stage', 'navigation', 'cleanup')}
    validate_observations(records['coordinator'], records['stage'], records['navigation'], records['cleanup'])
    images = {name: reader.read(name) for name in ('player-viewport-01.png', 'player-viewport-02.png')}
    for raw in images.values():
        need(raw[:16] == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
             and struct.unpack('>II', raw[16:24]) == (1200, 675), 'EXACT_CROP_PNG_DIMENSIONS_REQUIRED')
    parent = open_directory(OUTPUT.parent); directory = None
    try:
        # Create-only; existing or partially completed exports are never overwritten.
        os.mkdir(OUTPUT.name, 0o700, dir_fd=parent)
        directory = os.open(OUTPUT.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=parent)
        first = os.fstat(directory)
        need(first.st_uid == 0 and stat.S_IMODE(first.st_mode) == 0o700, 'NEW_ROOT_PRIVATE_EXPORT_REQUIRED')
        manifest = {'schema': 1, 'state': 'EXACT_TWO_RETAINED_PRIVATE_CROPS_COPIED',
                    'original_attempt_still_failed': True, 'flow_nonce': NONCE,
                    'source_manifest_sha256': SOURCE, 'original_files_unchanged': True,
                    'private_commercial_UI': True, 'must_not_enter_Git_or_public_summary': True,
                    'third_failed_capture_or_full_screen_read': False,
                    'playback_or_audio_qualification_asserted': False,
                    'Android_or_process_actions': 0, 'bytes_read': reader.total,
                    'files': {name: {'path': str(OUTPUT / name), 'bytes': len(raw), 'sha256': sha(raw),
                                    'width': 1200, 'height': 675}
                              for name, raw in images.items()},
                    'original_input_pins': {name: {'path': str(row[0]), 'bytes': row[1], 'sha256': row[2]}
                                            for name, row in FILES.items()}}
        write_new(directory, 'once.claim.json', (json.dumps({'nonce': NONCE, 'automatic_retry': False}) + '\n').encode())
        for name, raw in images.items():
            write_new(directory, name, raw)
        data = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
        write_new(directory, 'copy-index.json', data)
        os.fsync(directory)
        os.fchown(directory, 1000, 1000); os.fchmod(directory, 0o700); os.fsync(parent)
        final = os.fstat(directory)
        named = os.stat(OUTPUT.name, dir_fd=parent, follow_symlinks=False)
        need((first.st_dev, first.st_ino) == (final.st_dev, final.st_ino)
             == (named.st_dev, named.st_ino) and stat.S_ISDIR(named.st_mode)
             and final.st_uid == final.st_gid == 1000 and stat.S_IMODE(final.st_mode) == 0o700,
             'EXACT_OPERATOR_PRIVATE_DIRECTORY_REQUIRED')
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    print(json.dumps({'schema': 1, 'state': manifest['state'], 'private_commercial_UI': True,
          'must_not_enter_Git_or_public_summary': True, 'original_attempt_still_failed': True,
          'metadata_path': str(OUTPUT / 'copy-index.json'), 'metadata_bytes': len(data), 'metadata_sha256': sha(data),
          'files': manifest['files'], 'pixels_or_base64_in_stdout': False,
          'Android_or_process_actions': 0, 'runtime_qualification_asserted': False}, sort_keys=True))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--collect-once', action='store_true')
    args = parser.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state': 'PLAN_ONLY', 'fixed_inputs': {k: str(v[0]) for k, v in FILES.items()},
              'new_private_output': str(OUTPUT), 'new_directory_mode': '0700', 'new_PNG_mode': '0400',
              'new_copy_owner_UID_GID': [1000, 1000], 'remote_actions': 0, 'original_files_modified': False,
              'private_UI_export_requires_exact_request_admission': True}, sort_keys=True))
        return 0
    return collect()


if __name__ == '__main__':
    raise SystemExit(main())
