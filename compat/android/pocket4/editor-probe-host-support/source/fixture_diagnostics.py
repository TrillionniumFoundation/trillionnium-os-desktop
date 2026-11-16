"""Original bounded before/after UID crash and process-exit diagnostics.

This is synchronous evidence. It is not continuous sampling or a soak result.
"""
import re, time, types

def make_diagnostics(session, transaction, output):
    PACKAGE = session.active['target_profile']['package']
    write_new = transaction.write_new
    class Stop(RuntimeError):
        pass

    def require(value, reason):
        if not value:
            raise Stop(reason)

    def exit_events(text):
        events = set()
        require(text.startswith('ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)'),
                'EXIT_INFO_HEADER_UNKNOWN')
        blocks = re.split(r'(?=^\s*ApplicationExitInfo #\d+:)', text, flags=re.M)[1:]
        if not blocks:
            require(re.search(r'^\s*(?:No records\.?|\(nothing\))\s*$', text, re.M) is not None,
                    'EXIT_INFO_EMPTY_FORMAT_UNKNOWN')
        for block in blocks:
            fields = {}
            for name, pattern in {
                'timestamp': r'\btimestamp=([^\n]+)', 'pid': r'\bpid=(\d+)',
                'uid': r'\brealUid=(\d+)', 'reason': r'\breason=(\d+)\s*\(',
                'process': r'\bprocess=([^\s]+)',
            }.items():
                matches = re.findall(pattern, block)
                require(len(matches) == 1, 'EXIT_INFO_FIELD_UNKNOWN')
                fields[name] = matches[0].strip()
            events.add(tuple(fields[key] for key in ('timestamp', 'pid', 'uid', 'reason', 'process')))
        return events

    def fresh_crashes(before, after, uid, since):
        added = exit_events(after['exits']) - exit_events(before['exits'])
        require(all(int(row[2]) == uid and row[4] == PACKAGE for row in added), 'EXIT_INFO_UID_OR_PACKAGE_DIFFERS')
        fatal_exits = [row for row in added if int(row[3]) in (3, 4, 5, 6, 7)]
        fresh_uid_crash, fresh_events = [], []
        for key, target, limit in [('crash', fresh_uid_crash, 512), ('events', fresh_events, 2048)]:
            timed = []
            for line in after[key].splitlines():
                match = re.match(r'^\s*(\d+\.\d+)\s+', line)
                if match:
                    stamp = float(match[1]); timed.append(stamp)
                    if stamp >= since and (key == 'crash' or
                            (re.search(r'\bam_(?:crash|anr)\s*:', line) and PACKAGE in line)):
                        target.append(line)
            require(len(timed) < limit or min(timed) <= since, 'CRASH_OBSERVATION_WINDOW_TRUNCATED')
        return {'new_exit_events': len(added), 'new_crash_or_anr_exits': len(fatal_exits),
                'new_uid_crash_lines': len(fresh_uid_crash), 'new_package_crash_anr_events': len(fresh_events),
                'clear': not fatal_exits and not fresh_uid_crash and not fresh_events}

    class Trial:
        def __init__(self, session, transaction, output):
                self.s, self.tx, self.output = session, transaction, output
                self.owned = None
                self.sequence = 0
                self.shutter_calls = 0
                self.launch_calls = 0
                self.remove_calls = 0
                self.uncertain = False
                self.pending_effects = set()

        def record(self, stem, value):
                self.sequence += 1
                return write_new(self.output / ('%03d-' % self.sequence + stem + '.json'), value)

        def diagnostics(self, stem, uid):
                clock = self.s.android(['/system/bin/date', '+%s'], timeout=8).decode().strip()
                require(clock.isdigit() and abs(time.time() - int(clock)) <= 3, 'GUEST_CLOCK_UNVERIFIED')
                commands = {
                    'exits': ['/system/bin/dumpsys', 'activity', 'exit-info', PACKAGE],
                    'events': ['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'],
                    'crash': ['/system/bin/logcat', '--uid=' + str(uid), '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'],
                }
                result = {'guest_seconds': int(clock)}
                for key, command in commands.items():
                    raw = self.s.android(command, timeout=15)
                    require(len(raw) <= 4 * 1024 * 1024, 'DIAGNOSTIC_LIMIT_REACHED')
                    result[key] = raw.decode('utf-8', 'strict')
                self.record(stem, result)
                return result
    return types.SimpleNamespace(trial=Trial(session, transaction, output), exit_events=exit_events, fresh_crashes=fresh_crashes)
