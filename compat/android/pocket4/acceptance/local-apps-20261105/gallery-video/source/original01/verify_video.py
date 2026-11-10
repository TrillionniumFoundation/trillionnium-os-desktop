"""Decode owned clip pixels in a full Gallery frame, without trusting text labels."""
from verify_pattern import verify_pattern


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def verify_video_frame(image):
    proof = verify_pattern(image)
    small = image.resize(tuple(proof['sample_size']), resample=0)
    left, top, right, bottom = proof['sample_pattern_bounds']
    # The color rectangles span source x8..631 and y8..471, inside the border.
    def position(x, y):
        return (round(left + (x - 8) * (right - left) / 624),
                round(top + (y - 8) * (bottom - top) / 464))
    bits, samples = [], []
    for bit in range(6):
        x, y = position(116 + bit * 72, 240)
        values = [small.getpixel((x + offset, y)) for offset in (-1, 0, 1)]
        black = all(all(v < 32 for v in pixel) for pixel in values)
        white = all(all(v > 223 for v in pixel) for pixel in values)
        need(black or white, 'VISUAL_TIMECODE_NOT_BINARY')
        bits.append(int(black)); samples.append({'sample_center': [x, y], 'values': values})
    second = sum(value << bit for bit, value in enumerate(bits))
    need(0 <= second < 60, 'VISUAL_TIMECODE_OUT_OF_CLIP')
    return {**proof, 'visual_second_code': second, 'visual_second_bits': bits,
            'timecode_samples': samples, 'audio_qualified': False}


def verify_advancing(before, after, elapsed_seconds):
    need(2.5 <= elapsed_seconds <= 12, 'ADVANCE_OBSERVATION_INTERVAL')
    advance = after['visual_second_code'] - before['visual_second_code']
    need(advance >= 2 and abs(advance - elapsed_seconds) <= 2, 'VIDEO_PIXELS_DID_NOT_ADVANCE_WITH_TIME')
    return {'pixel_timecode_advanced': True, 'elapsed_seconds': elapsed_seconds,
            'decoded_seconds_advanced': advance}


def verify_paused(before, after, elapsed_seconds):
    need(2.5 <= elapsed_seconds <= 12, 'PAUSE_OBSERVATION_INTERVAL')
    value = before['visual_second_code']
    need(0 < value < 58 and after['visual_second_code'] == value,
         'PAUSED_PIXELS_NOT_STABLE_OR_CLIP_BOUNDARY')
    return {'pixel_timecode_stable': True, 'elapsed_seconds': elapsed_seconds,
            'decoded_second': value, 'requires_independent_actual_pause_control_evidence': True}
