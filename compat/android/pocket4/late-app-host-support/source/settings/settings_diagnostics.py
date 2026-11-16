"""Package/process attribution is required: the shared system UID is insufficient."""
import re

PACKAGE = 'com.android.settings'

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def target_process(name):
    return name == PACKAGE or name.startswith(PACKAGE + ':')

def exit_events(text):
    need(text.startswith('ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)'), 'EXIT_INFO_HEADER_UNKNOWN')
    blocks = re.split(r'(?=^\s*ApplicationExitInfo #\d+:)', text, flags=re.M)[1:]
    if not blocks:
        need(re.search(r'^\s*(?:No records\.?|\(nothing\))\s*$', text, re.M) is not None, 'EXIT_INFO_EMPTY_FORMAT_UNKNOWN')
    result = set()
    for block in blocks:
        values = {}
        for key, pattern in {'timestamp':r'\btimestamp=([^\n]+)', 'pid':r'\bpid=(\d+)',
                'uid':r'\brealUid=(\d+)', 'reason':r'\breason=(\d+)\s*\(', 'process':r'\bprocess=([^\s]+)'}.items():
            rows = re.findall(pattern, block)
            need(len(rows) == 1, 'EXIT_INFO_FIELD_UNKNOWN'); values[key] = rows[0].strip()
        result.add(tuple(values[k] for k in ('timestamp','pid','uid','reason','process')))
    return result

def compare(before, after):
    added = exit_events(after['exits']) - exit_events(before['exits'])
    target = [r for r in added if target_process(r[4])]
    need(all(r[2] == '1000' for r in target), 'SETTINGS_PROCESS_UID_CHANGED')
    fatal = [r for r in target if int(r[3]) in (3,4,5,6,7)]
    events = []; stamps = []
    for line in after['events'].splitlines():
        stamp = re.match(r'^\s*(\d+\.\d+)\s+', line)
        if not stamp: continue
        value = float(stamp[1]); stamps.append(value)
        if value >= before['guest_seconds'] and re.search(r'\bam_(?:crash|anr)\s*:', line) \
                and re.search(r'(?:\[|,)\s*com\.android\.settings(?::[A-Za-z0-9_.]+)?\s*(?:,|\])',line):
            events.append(line)
    need(len(stamps) < 2048 or min(stamps) <= before['guest_seconds'], 'PACKAGE_EVENT_WINDOW_TRUNCATED')
    return {'new_target_exit_events':target, 'new_fatal_target_exits':fatal, 'new_package_crash_or_anr_events':events,
        'unrelated_shared_UID_exit_records':len(added)-len(target), 'shared_UID_alone_used_for_attribution':False,
        'continuous_sampling_or_soak_credit':False, 'clear':not fatal and not events}
