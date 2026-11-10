#!/usr/bin/python3 -I
"""Read-only actual notification dump schema.

The inherited expired_heads_up_count name means timer records carrying a
full-screen PendingIntent; it is not evidence that any heads-up window appeared.
"""
import hashlib, re

def active_notifications(raw):
    """Only the active list; channel preferences/history are never delivery evidence."""
    lines = raw.splitlines()
    if not lines or lines[0] != "Current Notification Manager state (filtered to 'com.android.deskclock'):":
        return {'parsed': False, 'reason': 'EXACT_FILTER_HEADER_UNKNOWN'}
    starts = [i for i, line in enumerate(lines) if line == '  Notification List:']
    if len(starts) != 1:
        return {'parsed': False, 'reason': 'ACTIVE_LIST_HEADER_UNKNOWN'}
    body = []
    for line in lines[starts[0] + 1:]:
        if line.strip() and not line.startswith('    '):
            break
        body.append(line)
    joined = '\n'.join(body).strip()
    if not joined:
        return {'parsed': True, 'active_count': 0, 'expired_heads_up_count': 0, 'records': []}
    # The active record's own package/user/UID and channel must agree. Redacted
    # notification titles and text are intentionally neither parsed nor published.
    blocks = re.split(r'(?=^    NotificationRecord\()', '\n'.join(body), flags=re.M)
    if blocks[0].strip():
        return {'parsed': False, 'reason': 'ACTIVE_RECORD_SCHEMA_UNKNOWN'}
    records = []
    for block in blocks[1:]:
        header = block.splitlines()[0]
        if (not re.search(r'\bpkg=com\.android\.deskclock\b', header)
                or 'user=UserHandle{0}' not in header or not re.search(r'\buid=10063\b', block)):
            return {'parsed': False, 'reason': 'ACTIVE_RECORD_IDENTITY_UNKNOWN'}
        channel = bool(re.search(r'\bchannel=TimerModelNotification\b', block)
                       or "mId='TimerModelNotification'" in block)
        fullscreen = bool(re.search(r'\bfullscreenIntent=PendingIntent\{', block))
        records.append({'uid': 10063, 'user': 0, 'timer_channel': channel,
                        'full_screen_pending_intent': fullscreen,
                        'record_sha256': hashlib.sha256(block.encode()).hexdigest()})
    return {'parsed': True, 'active_count': len(records),
            'expired_heads_up_count': sum(x['timer_channel'] and x['full_screen_pending_intent'] for x in records),
            'records': records}
