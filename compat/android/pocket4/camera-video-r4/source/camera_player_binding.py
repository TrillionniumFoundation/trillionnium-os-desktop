"""Current NuPlayer output decoding and renderer state, not a display counter.

In the locked source Decoder::onOutputBuffer increments frames-total before
the later render/release callback. Therefore this module never calls the
counter a presented frame. The caller additionally binds the actual fresh
MovieActivity, exact owned URI, foreground pixels and advancing Gallery audio.
"""
import copy
import hashlib
import re

COMMIT = '475269ec44acec82792be6b01fb8e16357d4d2c8'
SOURCES = {
    'MediaPlayerService.cpp': (106450, '697a7d9ff64aea3566fb97b75825d5d3ac02370baf9824b4a559bb9401e40bd3'),
    'NuPlayerDriver.cpp': (36842, 'c983b57847db567ac5148759420707a33fcda3d9ca4e757864ed60ef0cf3206c'),
    'NuPlayerDecoder.cpp': (47819, '8273880502d793581847b4d5f9c26b8eb02a81db432c2b06a3143eccaa5fce63'),
    'NuPlayerRenderer.cpp': (75685, 'c7cd36896c781284dc54a6a5c7c07627f5b16ca806ebf1abbb96bcd59805e06f'),
}

def need(value, why):
    if not value: raise RuntimeError(why)

def one(pattern, text):
    rows = re.findall(pattern, text, re.M)
    need(len(rows) == 1, 'ONE_ACTUAL_PLAYER_FIELD:' + pattern)
    return rows[0]

def parse(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 1048576, 'BOUNDED_ACTUAL_MEDIA_PLAYER_DUMP')
    text = raw.decode('utf-8', 'strict')
    need('Permission Denial' not in text and 'lock is taken' not in text, 'COMPLETE_CURRENT_PLAYER_DUMP')
    # Sources serialize current clients before recorder clients and process
    # mappings. No historical log or recorder block is a current player.
    body = re.split(r'^ (?:MediaRecorderClient pid\(|No media recorder client|Files opened and/or mapped:)', text, maxsplit=1, flags=re.M)[0]
    heads = list(re.finditer(r'^ Client\s*$', body, re.M)); need(len(heads) <= 64, 'FINITE_ACTUAL_PLAYER_CLIENTS')
    clients = []
    for i, h in enumerate(heads):
        segment = body[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        attr, conn, status, looping = one(r'^  AttributionSource\((.*)\), connId\(([0-9]+)\), status\((-?[0-9]+)\), looping\((true|false)\)$', segment)
        # AIDL's actual named attribution values are preserved as raw text.
        # Nested/multiple attribution chains are not silently collapsed.
        pids = re.findall(r'\bpid:\s*([0-9]+)\b', attr); uids = re.findall(r'\buid:\s*([0-9]+)\b', attr)
        need(len(pids) == len(uids) == 1, 'ONE_DIRECT_ACTUAL_PLAYER_ATTRIBUTION')
        row = {'connection': int(conn), 'pid': int(pids[0]), 'uid': int(uids[0]),
            'status': int(status), 'looping': looping == 'true', 'attribution': attr,
            'nuplayer': None, 'video': None}
        if re.search(r'^ NuPlayer\s*$', segment, re.M):
            state, eos, loop, auto, paused, offload = one(
                r'^  state\(([0-9]+)\), atEOS\(([01])\), looping\(([01])\), autoLoop\(([01])\), renderer\(paused\(([01])\), offloading\(([01])\), wakelock\(', segment)
            row['nuplayer'] = {'state': int(state), 'atEOS': eos == '1', 'looping': loop == '1',
                'autoLoop': auto == '1', 'paused': paused == '1', 'offloading': offload == '1'}
            tracks = re.split(r'^  mime\(', segment, flags=re.M)[1:]
            video = [t for t in tracks if t.startswith('video/')]
            need(len(video) <= 1, 'AT_MOST_ONE_VIDEO_DECODER_PER_CURRENT_PLAYER')
            if video:
                track = video[0]; mime = track.split(')', 1)[0]
                decoder = one(r'^    decoder\(([^\n()]+)\)$', track)
                width, height = one(r'^    resolution\(([1-9][0-9]*) x ([1-9][0-9]*)\)$', track)
                total, dropped, percentage = one(r'^    numFramesTotal\(([0-9]+)\), numFramesDropped\(([0-9]+)\), percentageDropped\(([0-9]+\.[0-9]{2})%\)$', track)
                total, dropped = int(total), int(dropped)
                need(0 <= dropped <= total, 'ACTUAL_DECODER_DROP_COUNTS')
                row['video'] = {'mime': mime, 'decoder': decoder, 'width': int(width), 'height': int(height),
                    'decoded_outputs': total, 'dropped_outputs': dropped, 'percentage_dropped': percentage}
        clients.append(row)
    need(len({r['connection'] for r in clients}) == len(clients), 'UNIQUE_CURRENT_PLAYER_CONNECTIONS')
    return {'raw_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'clients': clients,
        'framework_commit': COMMIT, 'physical_presented_frame_claim': False}

def select(current, baseline, *, guest_pid, width, height):
    need(type(guest_pid) is type(width) is type(height) is int and guest_pid > 0, 'CURRENT_PLAYER_PROCESS_AND_CLIP')
    need(not any(r['uid'] == 10064 for r in baseline['clients']), 'NO_OLD_GALLERY_PLAYER_TO_ADOPT')
    before = {r['connection'] for r in baseline['clients']}
    rows = [r for r in current['clients'] if r['uid'] == 10064]
    need(len(rows) == 1 and rows[0]['pid'] == guest_pid and rows[0]['connection'] not in before
        and {r['connection'] for r in current['clients']} == before | {rows[0]['connection']},
        'ONE_NEW_GALLERY_ATTRIBUTED_PLAYER_CONNECTION')
    row = rows[0]; state = row['nuplayer']; video = row['video']
    need(row['status'] == 0 and row['looping'] is False and state is not None and video is not None
        and all(state[k] is False for k in ('atEOS', 'looping', 'autoLoop', 'paused', 'offloading'))
        and (video['width'], video['height']) == (width, height), 'CURRENT_UNPAUSED_REAL_GALLERY_VIDEO_DECODER')
    return copy.deepcopy(row)

def advancing(first, second, baseline, *, guest_pid, width, height, elapsed_ns):
    need(type(elapsed_ns) is int and 200000000 <= elapsed_ns <= 8000000000, 'FINITE_PLAYER_OBSERVATION_INTERVAL')
    a = select(first, baseline, guest_pid=guest_pid, width=width, height=height)
    b = select(second, baseline, guest_pid=guest_pid, width=width, height=height)
    need(all(a[k] == b[k] for k in ('connection', 'pid', 'uid', 'attribution'))
        and all(a['video'][k] == b['video'][k] for k in ('mime', 'decoder', 'width', 'height')),
        'SAME_CURRENT_PLAYER_AND_DECODER_GENERATION')
    advanced = b['video']['decoded_outputs'] - a['video']['decoded_outputs']
    dropped = b['video']['dropped_outputs'] - a['video']['dropped_outputs']
    need(2 <= advanced <= 2400 and 0 <= dropped < advanced, 'LIVE_NON_DROPPED_DECODER_OUTPUT_PROGRESS')
    return {'first': a, 'second': b, 'elapsed_ns': elapsed_ns, 'decoded_outputs_advanced': advanced,
        'dropped_outputs_advanced': dropped, 'renderer_observed_unpaused': True,
        'physical_presented_frame_claim': False, 'runtime_qualified': False}
