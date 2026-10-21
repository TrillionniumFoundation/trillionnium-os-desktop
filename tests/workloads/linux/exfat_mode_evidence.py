#!/usr/bin/env python3
"""Independent verdicts for the bounded ExFAT disk/exec observation profile."""
import re


ACTOR = 65534
CASE_ORDER = ('root_mode', 'file_mode', 'directory_mode', 'exec_normal', 'exec_nnp')
STAT_KEYS = 'name rc errno mode type uid gid ino dev size'.split()
CREDENTIAL_KEYS = ('phase name ruid euid suid fsuid rgid egid sgid fsgid groups nnp '
                   'securebits effective permitted inheritable ambient bounding at_secure').split()
BOOT_MARKER = 'TRILLIONNIUM_A01_BOOT_OK'
PROBE_PATH = 'bin/exfat-mode-probe'


def parse_fields(line, marker, keys):
    parts = line.split(' ')
    if parts[0] != marker or len(parts) != len(keys) + 1:
        return None
    pairs = [part.split('=', 1) for part in parts[1:]]
    if any(len(pair) != 2 for pair in pairs) or [pair[0] for pair in pairs] != keys:
        return None
    result = {}
    for key, value in pairs:
        if key in ('name', 'phase', 'result'):
            if not re.fullmatch('[a-zA-Z_]+', value):
                return None
            result[key] = value
        else:
            if not re.fullmatch('-?[0-9]{1,20}', value):
                return None
            result[key] = int(value)
    return result


def evaluate(raw, *, guest, negative, process_exit, timed_out, probe_bytes, stderr=b''):
    """Require observations and their causal order; PASS/FAIL labels alone are insufficient.

    The negative is only the frozen old-mode kernel: three actual 07777 modes,
    a real normal-exec UID/GID transition, and an unaffected no_new_privs peer.
    Timeout, missing evidence, arbitrary failure and a kernel panic never qualify.
    """
    text = re.sub(r'\x1b\[[0-9;]*m', '', raw.decode(errors='replace'))
    lines = text.splitlines()
    observed = [line for line in lines if line.startswith('EXFAT_')]
    errors, rows = [], {}
    plan = [('fs', 'EXFAT_FS', ['type', 'flags']),
            ('copy', 'EXFAT_COPY', ['bytes', 'reread_equal'])]
    for name in CASE_ORDER[:3]:
        plan += [(name + '_stat', 'EXFAT_STAT', STAT_KEYS),
                 (name + '_case', 'EXFAT_CASE', ['name', 'result', 'exit', 'signal'])]
    for name in CASE_ORDER[3:]:
        plan += [(name + '_before', 'EXFAT_CREDENTIALS', CREDENTIAL_KEYS),
                 (name + '_after', 'EXFAT_CREDENTIALS', CREDENTIAL_KEYS),
                 (name + '_case', 'EXFAT_CASE', ['name', 'result', 'exit', 'signal'])]
    plan.append(('complete', 'EXFAT_COMPLETE', ['total', 'passed', 'failed']))
    expected_length = len(plan) + int(guest)
    if len(observed) != expected_length:
        errors.append('missing_duplicate_or_unknown_marker')
    for index, (name, marker, keys) in enumerate(plan):
        row = parse_fields(observed[index], marker, keys) if index < len(observed) else None
        if row is None:
            errors.append('malformed_or_reordered_' + name)
        else:
            rows[name] = row
    if len(rows) == len(plan):
        fs = rows['fs']
        if fs['type'] != (0xaa55 if guest else 0x2011bab0) or fs['flags'] < 0 or fs['flags'] & (2 | 8):
            errors.append('wrong_filesystem_or_nosuid_noexec')
        if not 0 < probe_bytes <= 16 * 1024 * 1024 or rows['copy'] != {'bytes': probe_bytes, 'reread_equal': 1}:
            errors.append('copy_identity_or_length')
        root = rows['root_mode_stat']
        for name in CASE_ORDER[:3]:
            row = rows[name + '_stat']
            expected = {'name': name, 'rc': 0, 'errno': 0, 'mode': 0o7777 if negative else 0o777,
                        'type': 0o100000 if name == 'file_mode' else 0o40000, 'uid': 0, 'gid': 0}
            if any(row[key] != value for key, value in expected.items()):
                errors.append('mode_or_ids_' + name)
            if not 0 < row['ino'] < 1 << 64 or not 0 <= row['dev'] < 1 << 64 or row['dev'] != root['dev']:
                errors.append('filesystem_identity_' + name)
            if not 0 <= row['size'] < 1 << 64 or name == 'file_mode' and row['size'] != probe_bytes:
                errors.append('stat_size_' + name)
        if len({rows[name + '_stat']['ino'] for name in CASE_ORDER[:3]}) != 3:
            errors.append('file_directory_root_inode_alias')
        for name in CASE_ORDER[3:]:
            for phase in ('before', 'after'):
                changed = negative and name == 'exec_normal' and phase == 'after'
                ids = {'ruid': ACTOR, 'rgid': ACTOR,
                       **{key: 0 if changed else ACTOR for key in ('euid', 'suid', 'fsuid', 'egid', 'sgid', 'fsgid')}}
                expected = {'phase': phase, 'name': name, **ids, 'groups': 0,
                            'nnp': int(name == 'exec_nnp'), 'securebits': 0,
                            'effective': 0, 'permitted': 0, 'inheritable': 0,
                            'ambient': 0, 'bounding': 0, 'at_secure': int(changed)}
                if rows[name + '_' + phase] != expected:
                    errors.append('credentials_' + name + '_' + phase)
        for name in CASE_ORDER:
            failed = negative and name != 'exec_nnp'
            expected = {'name': name, 'result': 'FAIL' if failed else 'PASS',
                        'exit': int(failed), 'signal': 0}
            if rows[name + '_case'] != expected:
                errors.append('case_status_' + name)
        if rows['complete'] != {'total': 5, 'passed': 1 if negative else 5, 'failed': 4 if negative else 0}:
            errors.append('summary_totals')
    if negative and not guest:
        errors.append('negative_is_only_the_fixed_guest_mutation')
    if guest:
        exit_line = 'EXFAT_PROCESS_EXIT=' + ('1' if negative else '0')
        if not observed or observed[-1] != exit_line or lines.count(BOOT_MARKER) != 1:
            errors.append('guest_exit_or_original_boot_missing')
        elif lines.index(exit_line) > lines.index(BOOT_MARKER):
            errors.append('guest_boot_precedes_probe')
        if re.search(r'(?i)kernel panic|panicked at|fatal exception', text):
            errors.append('kernel_panic')
    elif raw != ('\n'.join(observed) + '\n').encode() or stderr != b'':
        errors.append('reference_extra_output_or_stderr')
    if type(process_exit) is not int or process_exit != (33 if guest else 0) or timed_out is not False:
        errors.append('process_failed_or_timed_out')
    return {'passed': not errors, 'guest': guest, 'negative_control': negative,
            'observations': rows, 'failed_conditions': errors, 'expected_cases': list(CASE_ORDER)}
