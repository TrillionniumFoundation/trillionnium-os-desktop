"""Bounded nonce correlation of only the new Camera clip or owned playback.

The four-frequency, 16-symbol detector follows physical_audio_client.rs
(e02bce153294554c8cc4bf8075c2f14431ab6ffa7e14e6171473699a4b3d1a3a).
It receives current bytes; it never accepts that predecessor's old receipt.
Pure correlation is only one predicate. It cannot qualify Android/HAL input,
the physical source, a playback session or an application's whole release.
"""
import array
import hashlib
import math
import re
import sys
import time

RATE = 48000
BLOCK = 480
SYMBOL_BLOCKS = 8
SYMBOLS = 16
LEADING_BLOCKS = 150
AMPLITUDE = 4096.0
FREQUENCIES = (700.0, 1100.0, 1700.0, 2300.0)
DECOY_XOR = 0xa0761d6478bd642f
MASK = (1 << 64) - 1
MAX_PCM_BYTES = RATE * 2 * 21


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def sequence(nonce):
    need(type(nonce) is str and re.fullmatch('[0-9a-f]{16}', nonce), 'EXACT_FRESH_64_BIT_NONCE')
    seed = int(nonce, 16)
    if seed == 0:
        seed = 0x9e3779b97f4a7c15
    result = []
    for i in range(SYMBOLS):
        seed ^= (seed << 13) & MASK
        seed ^= seed >> 7
        seed ^= (seed << 17) & MASK
        value = seed % 4
        if i > 0 and value == result[-1]:
            value = (value + 1 + (seed // 4) % 3) % 4
        result.append(value)
    return result


def waveform(nonce):
    """Same finite 2.78s stereo S16LE signal; does not play or open a device."""
    out = array.array('h', [0]) * (LEADING_BLOCKS * BLOCK * 2)
    for symbol in sequence(nonce):
        for n in range(SYMBOL_BLOCKS * BLOCK):
            edge = min(n, SYMBOL_BLOCKS * BLOCK - 1 - n, 240) / 240.0
            value = AMPLITUDE * edge * math.sin(math.tau * FREQUENCIES[symbol] * n / RATE)
            # Rust f64.round rounds a half away from zero.
            sample = math.floor(value + .5) if value >= 0 else math.ceil(value - .5)
            out.extend((sample, sample))
    need(len(out) == 266880 and max(abs(x) for x in out) <= 4096, 'EXACT_ORIGINAL_CHALLENGE_FRAME_AND_AMPLITUDE_BOUND')
    if sys.byteorder != 'little':
        out.byteswap()
    return out.tobytes()


def powers(raw, deadline):
    need(type(raw) is bytes and 2 * BLOCK * SYMBOL_BLOCKS * SYMBOLS <= len(raw) <= MAX_PCM_BYTES
        and len(raw) % 2 == 0, 'BOUNDED_OWNED_MONO_S16LE_DECODE')
    need(type(deadline) in (int, float) and math.isfinite(deadline), 'FINITE_ANALYSIS_DEADLINE')
    samples = array.array('h'); samples.frombytes(raw)
    if sys.byteorder != 'little':
        samples.byteswap()
    sines = [[math.sin(math.tau * f * n / RATE) for n in range(BLOCK)] for f in FREQUENCIES]
    cosines = [[math.cos(math.tau * f * n / RATE) for n in range(BLOCK)] for f in FREQUENCIES]
    result = []
    for start in range(0, len(samples) - BLOCK + 1, BLOCK):
        need(time.monotonic() < deadline, 'OWNED_AUDIO_CORRELATION_DEADLINE_EXPIRED')
        part = samples[start:start + BLOCK]; bands = []
        for k in range(4):
            real = sum(part[n] * cosines[k][n] for n in range(BLOCK))
            imag = sum(part[n] * sines[k][n] for n in range(BLOCK))
            bands.append(4.0 * (real * real + imag * imag) / (BLOCK * BLOCK))
        result.append(bands)
    return result


def detect(bands, expected, first, last, deadline):
    need(type(first) is type(last) is int and 0 <= first <= last
        and len(expected) == SYMBOLS and all(type(x) is int and 0 <= x < 4 for x in expected),
        'BOUNDED_CURRENT_CHALLENGE_ALIGNMENT')
    best = {'passed': False, 'offset_blocks': None, 'matched_symbols': 0,
            'mean_frequency_fraction': 0.0, 'minimum_matched_amplitude': 0.0}
    for offset in range(first, min(last, len(bands) - SYMBOLS * SYMBOL_BLOCKS) + 1):
        need(time.monotonic() < deadline, 'OWNED_AUDIO_ALIGNMENT_DEADLINE_EXPIRED')
        matched = 0; fractions = 0.0; smallest = math.inf
        for index, symbol in enumerate(expected):
            p = [sum(r[k] for r in bands[offset + index * SYMBOL_BLOCKS + 2:
                offset + index * SYMBOL_BLOCKS + 6]) / 4.0 for k in range(4)]
            total = sum(p); fraction = p[symbol] / total if total > 0 else 0.0
            amplitude = math.sqrt(p[symbol])
            if fraction >= .65 and amplitude >= 4.0:
                matched += 1
            fractions += fraction; smallest = min(smallest, amplitude)
        mean = fractions / SYMBOLS
        if matched > best['matched_symbols'] or (matched == best['matched_symbols'] and mean > best['mean_frequency_fraction']):
            best = {'passed': matched >= 15 and mean >= .75, 'offset_blocks': offset,
                    'matched_symbols': matched, 'mean_frequency_fraction': mean,
                    'minimum_matched_amplitude': smallest}
    return best


def analyze(raw, nonce, *, tone_window_ms, baseline_end_ms, deadline):
    """Match a new finite tone in its measured window plus two real negatives.

    Window/baseline times must be computed from actual current start and tone
    release boundaries by the caller. A broad all-file search is forbidden.
    This intentionally returns no physical or Android qualification flag.
    """
    need(type(tone_window_ms) is list and len(tone_window_ms) == 2
        and all(type(x) is int for x in tone_window_ms)
        and 1500 <= tone_window_ms[0] <= tone_window_ms[1] <= 19000
        and tone_window_ms[1] - tone_window_ms[0] <= 2500
        and type(baseline_end_ms) is int and 1280 <= baseline_end_ms < tone_window_ms[0],
        'ACTUAL_CURRENT_TONE_AND_QUIET_BASELINE_TIME_WINDOWS')
    bands = powers(raw, deadline)
    need(baseline_end_ms // 10 <= len(bands), 'COMPLETE_PRETONE_BASELINE_REQUIRED')
    expected = sequence(nonce)
    positive = detect(bands, expected, tone_window_ms[0] // 10,
                      (tone_window_ms[1] + 9) // 10, deadline)
    baseline = detect(bands[:baseline_end_ms // 10], expected, 0,
                      baseline_end_ms // 10 - SYMBOLS * SYMBOL_BLOCKS, deadline)
    decoy_nonce = f'{int(nonce, 16) ^ DECOY_XOR:016x}'
    decoy_symbols = sequence(decoy_nonce)
    need(decoy_symbols != expected, 'INDEPENDENT_DECOY_CHALLENGE')
    decoy = detect(bands, decoy_symbols, 0, len(bands) - SYMBOLS * SYMBOL_BLOCKS, deadline)
    return {'schema': 'pocket4-camera-current-audio-correlation-v1', 'nonce': nonce,
        'pcm_sha256': hashlib.sha256(raw).hexdigest(), 'pcm_bytes': len(raw), 'sample_rate': RATE,
        'channels': 1, 'sample_format': 'S16LE', 'tone_window_ms': list(tone_window_ms),
        'baseline_end_ms': baseline_end_ms, 'positive': positive, 'baseline': baseline, 'decoy': decoy,
        'matched': bool(positive['passed'] and not baseline['passed'] and not decoy['passed']),
        'baseline_negative_passed': not baseline['passed'], 'decoy_negative_passed': not decoy['passed'],
        'Android_HAL_or_physical_source_qualification': False,
        'historical_host_nonce_or_receipt_used': False, 'whole_app_business_accepted': False}
