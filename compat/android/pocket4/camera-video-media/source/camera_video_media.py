"""Exact owned Video MediaStore grammar, bounded full decode and clip identity.

No path is read by import. Decoding is dispatched only by a new case Session,
using its phase-cropped owned host runner. The caller must pass the held-copy
reference of the one video whose row was created by its known start/stop.
"""
import hashlib
import json
import math
import os
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET

PACKAGE = 'com.android.camera2'
URI = 'content://media/external_primary/video/media'
MAX_CLIP_BYTES = 128 * 1024 * 1024
MAX_DURATION_MS = 20_000
VIDEO_FIELDS = ('_id', '_data', '_display_name', 'title', 'mime_type', '_size',
    'width', 'height', 'duration', 'datetaken', 'date_added', 'is_pending', 'owner_package_name')
PREFERENCES = '/data/user/0/com.android.camera2/shared_prefs/com.android.camera2_preferences.xml'


def need(value, why):
    if not value:
        raise RuntimeError(why)


def mode(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 131072, 'BOUNDED_ORIGINAL_CAMERA_MODE_PREFERENCES')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise RuntimeError('CAMERA_PREFERENCES_XML_UNKNOWN') from error
    values = [n for n in root if n.get('name') == 'camera.startup_module']
    need(root.tag == 'map' and len(values) == 1 and values[0].tag == 'string'
        and values[0].text in ('0', '1'), 'EXACT_SOURCE_PHOTO0_VIDEO1_CURRENT_MODE')
    return {'module': values[0].text, 'preferences_sha256': hashlib.sha256(raw).hexdigest(),
            'direct_preference_writes': 0}


def one_new_video(before, after):
    need(type(before) is set and type(after) is set and all(type(i) is int and i > 0 for i in before | after)
        and before <= after, 'PREEXISTING_VIDEO_IDS_PRESERVED')
    created = after - before
    need(len(created) <= 1, 'MULTIPLE_NEW_VIDEOS_CANNOT_BE_ATTRIBUTED_TO_THIS_CASE')
    return next(iter(created)) if created else None


def video_row(content_rows, raw, identity, *, earliest_ms, latest_ms):
    need(type(identity) is int and identity > 0 and type(earliest_ms) is type(latest_ms) is int
        and 0 < earliest_ms <= latest_ms, 'KNOWN_NEW_VIDEO_ID_AND_RECORDING_TIME_WINDOW')
    rows = content_rows(raw, VIDEO_FIELDS)
    need(len(rows) == 1, 'EXACT_ONE_NEW_CAMERA_VIDEO_ROW')
    row = rows[0]
    for key in ('_id', 'datetaken', 'date_added', 'is_pending'):
        need(type(row[key]) is str and re.fullmatch('[0-9]+', row[key]), 'VIDEO_NUMERIC_ID_OR_DATE:' + key)
        row[key] = int(row[key])
    need(row['_id'] == identity and row['owner_package_name'] == PACKAGE
        and row['mime_type'] in ('video/mp4', 'video/3gpp') and row['is_pending'] in (0, 1),
        'CURRENT_CAMERA_OWNED_VIDEO_ROW_REQUIRED')
    need(earliest_ms - 3000 <= row['datetaken'] <= latest_ms + 3000
        and earliest_ms // 1000 - 3 <= row['date_added'] <= latest_ms // 1000 + 3,
        'VIDEO_ROW_NOT_CREATED_IN_THIS_KNOWN_RECORDING')
    # The original Camera2 title/display-name is VID_yyyyMMdd_HHmmss. The
    # provider appends the MIME extension when choosing its physical filename.
    need(re.fullmatch('VID_[0-9]{8}_[0-9]{6}(?:_[0-9]+)?', row['title'])
        and row['_display_name'] in (row['title'], row['title'] + '.mp4', row['title'] + '.3gp'),
        'ORIGINAL_CAMERA_GENERATED_VIDEO_NAME_REQUIRED')
    p = PurePosixPath(row['_data'])
    need(str(p) == row['_data'] and str(p.parent) in ('/storage/emulated/0/DCIM/Camera',
        '/storage/emulated/0/DCIM', '/storage/emulated/0/Movies')
        and p.name in (row['title'] + '.mp4', row['title'] + '.3gp')
        and row['_display_name'] in (p.name, row['title']), 'EXACT_NEW_CAMERA_VIDEO_PHYSICAL_PATH')
    if row['is_pending'] == 1:
        # Creation/open of this row precedes MediaRecorder.start in the actual
        # source. It conveys no successful recording or read authority.
        return None
    for key in ('_size', 'width', 'height', 'duration'):
        need(type(row[key]) is str and re.fullmatch('[1-9][0-9]*', row[key]), 'FINAL_VIDEO_NUMERIC_FIELD:' + key)
        row[key] = int(row[key])
    need(0 < row['_size'] <= MAX_CLIP_BYTES and 0 < row['width'] <= 8192
        and 0 < row['height'] <= 8192 and row['width'] * row['height'] <= 32_000_000
        and 1000 <= row['duration'] <= MAX_DURATION_MS,
        'FINAL_VIDEO_DIMENSIONS_DURATION_OR_SIZE_OUTSIDE_EXPLICIT_CASE_BOUND')
    row['uri'] = URI + '/' + str(identity)
    return row


def parse_probe(raw, row):
    need(type(raw) is bytes and 0 < len(raw) <= 1048576, 'BOUNDED_OWNED_CLIP_PROBE')
    def pairs(values):
        result = {}
        for key, value in values:
            need(key not in result, 'DUPLICATE_PROBE_JSON_FIELD')
            result[key] = value
        return result
    def nonfinite(_):
        raise RuntimeError('NONFINITE_PROBE_JSON_NUMBER')
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    streams = result.get('streams'); fmt = result.get('format')
    need(type(streams) is list and len(streams) == 2 and type(fmt) is dict,
         'ONE_VIDEO_AND_ONE_AUDIO_STREAM_REQUIRED')
    video = [s for s in streams if s.get('codec_type') == 'video']
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    need(len(video) == len(audio) == 1, 'EXACT_VIDEO_AUDIO_STREAM_SET')
    v, a = video[0], audio[0]
    need(v.get('codec_name') in ('h264', 'hevc', 'mpeg4', 'h263')
        and a.get('codec_name') in ('aac', 'amr_nb', 'amr_wb')
        and type(v.get('width')) is int and type(v.get('height')) is int
        and (v['width'], v['height']) == (row['width'], row['height'])
        and int(a.get('sample_rate', '0')) in (8000, 16000, 22050, 24000, 32000, 44100, 48000)
        and type(a.get('channels')) is int and 1 <= a['channels'] <= 2,
        'SUPPORTED_ACTUAL_CAMERA_CODEC_DIMENSIONS_AND_AUDIO_GEOMETRY')
    durations = {}
    for label, obj in (('format', fmt), ('video', v), ('audio', a)):
        value = float(obj.get('duration', 'nan'))
        need(math.isfinite(value) and 0 < value <= 21
            and abs(value * 1000 - row['duration']) <= 1500, 'FULL_STREAM_DURATION_DIFFERS_FROM_OWNED_MEDIA:' + label)
        durations[label] = value
    need(int(fmt.get('size', '0')) == row['_size'], 'PROBED_CLIP_SIZE_DIFFERS_FROM_HELD_OWNED_FILE')
    need(type(v.get('nb_read_frames')) is str and re.fullmatch('[1-9][0-9]*', v['nb_read_frames'])
        and 2 <= int(v['nb_read_frames']) <= 2400, 'ACTUAL_FULL_VIDEO_FRAME_COUNT_REQUIRED')
    need(type(a.get('nb_read_frames')) is str and re.fullmatch('[1-9][0-9]*', a['nb_read_frames'])
        and 2 <= int(a['nb_read_frames']) <= 10000, 'ACTUAL_FULL_AUDIO_PACKET_DECODE_COUNT_REQUIRED')
    return {'streams': streams, 'durations': durations, 'frame_count': int(v['nb_read_frames']),
            'audio_frame_count': int(a['nb_read_frames']), 'video_codec': v['codec_name'],
            'audio_codec': a['codec_name'], 'audio_rate': int(a['sample_rate']), 'audio_channels': a['channels']}


def parse_framemd5(raw, expected_frames):
    need(type(raw) is bytes and 0 < len(raw) <= 1048576, 'BOUNDED_FULL_VIDEO_DECODE_HASHES')
    lines = raw.decode('ascii', 'strict').splitlines()
    need(lines and any(x.startswith('#format: frame checksums') for x in lines)
        and any(x == '#hash: MD5' for x in lines), 'ACTUAL_FFMPEG_FRAMEMD5_FORMAT')
    rows = []
    for line in lines:
        if line.startswith('#') or not line.strip():
            continue
        m = re.fullmatch(r'\s*0,\s*(-?\d+),\s*(-?\d+),\s*(\d+),\s*(\d+),\s*([0-9a-f]{32})\s*', line)
        need(m is not None, 'UNRECOGNIZED_VIDEO_DECODE_FRAME_LINE')
        dts, pts, duration, size = map(int, m.groups()[:4])
        need(duration > 0 and size > 0 and (not rows or pts > rows[-1]['pts']),
             'VIDEO_DECODE_TIMESTAMPS_NOT_ADVANCING')
        rows.append({'dts': dts, 'pts': pts, 'duration': duration, 'bytes': size, 'md5': m[5]})
    need(len(rows) == expected_frames, 'FULL_VIDEO_DECODE_FRAMESET_DIFFERS_FROM_PROBE')
    return {'frames': rows, 'count': len(rows), 'all_frames_decoded': True,
            'frame_hashes_sha256': hashlib.sha256(raw).hexdigest(),
            'distinct_decoded_frame_hashes': len({r['md5'] for r in rows})}


def decoder_argv(kind, held_path):
    match = re.fullmatch(r'/proc/(self|' + str(os.getpid()) + r')/fd/([0-9]+)', held_path) if type(held_path) is str else None
    need(match is not None and int(match[2]) >= 3,
         'DECODER_MUST_READ_THE_SAME_HELD_OWNED_DESCRIPTOR')
    if kind == 'probe':
        return ['/usr/bin/ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format',
                '-of', 'json', '-protocol_whitelist', 'file,pipe', '-f', 'mov', '-i', held_path]
    common = ['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-err_detect', 'explode',
              '-threads', '1', '-protocol_whitelist', 'file,pipe', '-f', 'mov', '-i', held_path]
    if kind == 'video':
        return common + ['-map', '0:v:0', '-an', '-vsync', '0', '-f', 'framemd5', 'pipe:1']
    if kind == 'audio':
        return common + ['-map', '0:a:0', '-vn', '-ac', '1', '-ar', '48000',
                         '-acodec', 'pcm_s16le', '-f', 's16le', 'pipe:1']
    raise RuntimeError('ONLY_THREE_OWNED_FULL_CLIP_DECODE_COMMANDS')
