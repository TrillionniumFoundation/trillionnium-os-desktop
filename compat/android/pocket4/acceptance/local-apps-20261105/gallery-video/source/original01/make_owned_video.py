#!/usr/bin/env python3
"""Generate a silent, synthetic calibration clip; never read user media."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT, FPS, SECONDS = 640, 480, 10, 60
COLORS = ((255, 59, 48), (52, 199, 89), (0, 122, 255), (255, 204, 0))


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def frame(second):
    need(type(second) is int and 0 <= second < SECONDS, 'SECOND_OUT_OF_RANGE')
    result = bytearray(WIDTH * HEIGHT * 3)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if x < 8 or x >= WIDTH - 8 or y < 8 or y >= HEIGHT - 8:
                color = (0, 0, 0)
            elif abs(x - WIDTH // 2) < 8 or abs(y - HEIGHT // 2) < 8:
                color = (255, 255, 255)
            else:
                color = COLORS[(2 if y >= HEIGHT // 2 else 0) + (1 if x >= WIDTH // 2 else 0)]
            # Six visual time-code bits stay inside the horizontal white cross.
            # The first marker is at x100; bits are least significant first.
            if 235 <= y < 245:
                for bit in range(6):
                    if 100 + bit * 72 <= x < 132 + bit * 72:
                        color = (0, 0, 0) if second & (1 << bit) else (255, 255, 255)
                        break
            offset = (y * WIDTH + x) * 3
            result[offset:offset + 3] = bytes(color)
    return bytes(result)


def main():
    output = HERE / 'pattern.mp4'
    need(not output.exists() and not (HERE / 'video-provenance.json').exists(), 'CREATE_ONLY_OUTPUT')
    ffmpeg = Path('/usr/bin/ffmpeg').resolve(strict=True)
    ffprobe = Path('/usr/bin/ffprobe').resolve(strict=True)
    source = pin(Path(__file__))
    tools_before = {'ffmpeg': pin(ffmpeg), 'ffprobe': pin(ffprobe)}
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
    argv = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
            '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '640x480',
            '-framerate', str(FPS), '-i', 'pipe:0', '-an', '-map_metadata', '-1',
            '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '16',
            '-pix_fmt', 'yuv420p', '-profile:v', 'baseline', '-level:v', '3.0',
            '-g', str(FPS), '-keyint_min', str(FPS), '-sc_threshold', '0',
            '-movflags', '+faststart', str(output)]
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=environment)
    try:
        for second in range(SECONDS):
            raw = frame(second)
            for _ in range(FPS):
                process.stdin.write(raw)
        process.stdin.close()
        process.stdin = None
        stdout, stderr = process.communicate(timeout=30)
        need(process.returncode == 0 and stdout == b'' and stderr == b'', 'VIDEO_ENCODE_FAILED')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    probe = subprocess.run([str(ffprobe), '-v', 'error', '-show_streams', '-show_format',
                            '-of', 'json', str(output)], env=environment,
                           capture_output=True, timeout=10, check=True)
    need(probe.stderr == b'', 'VIDEO_PROBE_STDERR')
    metadata = json.loads(probe.stdout)
    streams = metadata['streams']
    need(len(streams) == 1 and streams[0]['codec_type'] == 'video'
         and streams[0]['codec_name'] == 'h264' and streams[0]['width'] == WIDTH
         and streams[0]['height'] == HEIGHT and streams[0]['pix_fmt'] == 'yuv420p'
         and int(streams[0]['nb_frames']) == FPS * SECONDS
         and float(streams[0]['duration']) == SECONDS, 'EXACT_CLIP_CONTRACT')
    need(output.stat().st_size < 524288, 'VIDEO_SIZE_BOUND')
    samples = []
    for second in (0, 1, 17, 59):
        decoded = subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-ss', str(second) + '.2', '-i', str(output), '-frames:v', '1', '-f', 'rawvideo',
            '-pix_fmt', 'rgb24', 'pipe:1'], env=environment, capture_output=True, timeout=10, check=True)
        need(decoded.stderr == b'' and len(decoded.stdout) == WIDTH * HEIGHT * 3, 'FRAME_DECODE_BOUND')
        def pixel(x, y):
            offset = (y * WIDTH + x) * 3
            return decoded.stdout[offset:offset + 3]
        for point, target in zip(((100, 100), (540, 100), (100, 380), (540, 380)), COLORS):
            need(all(abs(a - b) <= 6 for a, b in zip(pixel(*point), target)), 'DECODED_QUADRANT_CHANGED')
        bits = []
        for bit in range(6):
            value = pixel(116 + bit * 72, 240)
            need(all(v < 16 for v in value) or all(v > 239 for v in value), 'TIMECODE_NOT_BINARY')
            bits.append(int(all(v < 16 for v in value)))
        decoded_second = sum(bit << index for index, bit in enumerate(bits))
        need(decoded_second == second, 'VISUAL_SECOND_CODE_MISMATCH')
        samples.append({'second': second, 'visual_second_code': decoded_second,
                        'decoded_rgb_sha256': hashlib.sha256(decoded.stdout).hexdigest()})
    need(tools_before == {'ffmpeg': pin(ffmpeg), 'ffprobe': pin(ffprobe)}
         and source == pin(Path(__file__)), 'GENERATOR_INPUT_CHANGED')
    result = {'schema': 'pocket4-owned-silent-video-v1', 'state': 'GENERATED_LOCAL_ONLY',
              'width': WIDTH, 'height': HEIGHT, 'fps': FPS, 'seconds': SECONDS,
              'frame_count': FPS * SECONDS, 'video': pin(output), 'source': source,
              'tools': tools_before, 'codec': streams[0]['codec_name'],
              'profile': streams[0]['profile'], 'pix_fmt': streams[0]['pix_fmt'],
              'audio_tracks': 0, 'visual_clock': {'bits': 6, 'order': 'least-significant-first',
              'rectangles': [[100 + i * 72, 235, 132 + i * 72, 245] for i in range(6)]},
              'decoded_samples': samples, 'user_media_read': False,
              'host_native_library_closure_fully_pinned': False,
              'android_operations': 0, 'gallery_playback_qualified': False}
    with (HERE / 'video-provenance.json').open('x') as out:
        json.dump(result, out, indent=2); out.write('\n')
    print(json.dumps({k: result[k] for k in ('state', 'video', 'frame_count', 'audio_tracks', 'android_operations')}))


if __name__ == '__main__':
    main()
