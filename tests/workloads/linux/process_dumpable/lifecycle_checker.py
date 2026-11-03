"""Strict, source-bound guest transcript oracles. No guest success is fabricated.

Embed check_lifecycle(raw, raw_qemu_exit, timed_out) / check_stat(...) in the
standard runner. Both default to the existing Asterinas reset policy zero.
The host unit fixtures exercise checker rejection only, never qualify a guest.
"""
import json
import re


def _same(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':')) == json.dumps(b, sort_keys=True, separators=(',', ':'))


def _unique(pairs):
    value = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = entry
    return value


def _transcript(raw, code, timed_out):
    if type(code) is not int or code != 33 or timed_out is not False:
        raise ValueError('requires raw QEMU exit33 and no timeout')
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='strict')
    if type(raw) is not str or len(raw.encode()) > 2 * 1024 * 1024:
        raise ValueError('invalid or excessive raw transcript')
    lines = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r', '').splitlines()
    exits = [i for i, line in enumerate(lines) if 'DUMPABLE_LIFECYCLE_EXIT=' in line]
    boots = [i for i, line in enumerate(lines) if 'TRILLIONNIUM_A01_BOOT_OK' in line]
    if len(exits) != 1 or lines[exits[0]] != 'DUMPABLE_LIFECYCLE_EXIT=0':
        raise ValueError('requires one exact successful probe exit marker')
    if len(boots) != 1 or lines[boots[0]] != 'TRILLIONNIUM_A01_BOOT_OK' or exits[0] >= boots[0]:
        raise ValueError('requires one ordered final boot marker')
    values = []
    for i, line in enumerate(lines):
        if line.startswith('{'):
            if i >= exits[0]:
                raise ValueError('observation after completion marker')
            item = json.loads(line, object_pairs_hook=_unique)
            if type(item) is not dict:
                raise ValueError('expected JSON object')
            values.append(item)
    if not values:
        raise ValueError('missing observations')
    return values


def _case(name, actual=1):
    return {'case': name, 'actual': actual, 'expected': actual, 'passed': True}


def _lifecycle_expected(policy_present):
    out = [{'suite': 'dumpable-lifecycle-v2', 'kernel': 'Linux',
            'release': lambda v: type(v) is str and 0 < len(v) < 128,
            'max_live_owned_children': 2}]
    if policy_present:
        out.append(_case('explicit_reset_policy_equals_readonly_actual_sysctl'))
    out.append({'reset_policy': 0, 'policy_sysctl_present': policy_present, 'no_sysctl_changed': True})
    groups = [
        [('uid_noop', 0), ('gid_noop', 0), ('uid_gid_noop_preserves_one', 1)],
        [('fsuid_query', 60001), ('fsgid_query', 60001), ('query_preserves_one', 1)],
        [('fsuid_noop', 60001), ('fsgid_noop', 60001), ('fsid_noop_preserves_one', 1)],
        [('failed_uid_change', -1), ('failed_uid_errno', 1), ('failed_uid_preserves_one', 1),
         ('failed_gid_change', -1), ('failed_gid_errno', 1), ('failed_gid_preserves_one', 1)],
        [('failed_fsuid_returns_old', 60001), ('failed_fsuid_unchanged', 60001),
         ('failed_fsgid_returns_old', 60001), ('failed_fsgid_unchanged', 60001), ('failed_fsid_preserves_one', 1)],
        [('effective_uid_change', 0), ('effective_uid_change_resets_to_policy', 0)],
        [('filesystem_uid_change', 60002), ('filesystem_uid_current', 60001), ('filesystem_uid_change_resets_to_policy', 0)],
        [('real_uid_only_change', 0), ('real_uid_only_preserves_one', 1)],
        [('saved_uid_only_change', 0), ('saved_uid_only_preserves_one', 1)],
        [('effective_gid_change', 0), ('effective_gid_change_resets_to_policy', 0)],
        [('filesystem_gid_change', 60002), ('filesystem_gid_current', 60001), ('filesystem_gid_change_resets_to_policy', 0)],
        [('real_gid_only_change', 0), ('real_gid_only_preserves_one', 1)],
        [('permitted_capability_decrease_preserves_one', 1)],
        [('exec_unequal_effective_real_uid_retains_identity', 60002), ('exec_unequal_real_uid', 60001),
         ('exec_unequal_ids_resets_to_policy', 0)],
    ]
    for i, cases in enumerate(groups):
        out.append(_case('cap_drop_set_one' if i == 12 else 'credential_set_one', 0))
        out.extend(_case(name, value) for name, value in cases)
        out.append(_case('credential_fixture_reaped'))
    out.append({'observer_uid': 60001, 'observer_gid': 60001, 'cap_eff': 0, 'cap_prm': 0, 'nnp': 1})
    local = [('set_zero', 0), ('get_zero', 0), ('invalid_set_rejected', -1), ('invalid_set_errno', 22),
             ('invalid_set_preserves_zero', 0), ('failed_exec', -1), ('failed_exec_errno', 2),
             ('failed_exec_preserves_zero', 0), ('self_dev_null_open', 1), ('dump0_self_fd_readlink', 1),
             ('dump0_self_fdinfo', 1), ('self_pidfd_open', 1), ('dump0_self_pidfd_readlink', 1),
             ('self_pidfd_link_identity', 1), ('dump0_self_pidfd_fdinfo', 1), ('self_pidfd_metadata_identity', 1),
             ('fork_copies_zero', 1), ('fork_child_change_not_shared', 0), ('pthread_create', 0),
             ('thread_inherits_zero', 0), ('thread_sets_one', 0), ('pthread_join', 0), ('thread_change_shared', 1),
             ('failed_exec_at_one', -1), ('failed_exec_at_one_errno', 2), ('failed_exec_preserves_one', 1),
             ('clone_vm_bounded_stack', 1), ('clone_vm_created', 1), ('clone_vm_child_reaped', 1),
             ('clone_vm_change_shared', 0), ('owned_child_pidfd_open', 1), ('retained_child_identity', 1)]
    out.extend(_case(name, value) for name, value in local)
    for stage, enabled in [('cross_child_set0', False), ('cross_child_set1', True),
                           ('cross_child_set0_again', False), ('ordinary_exec_resets_one', True)]:
        if stage == 'ordinary_exec_resets_one':
            out.extend(_case('old_image_fd_open_at_dump1') for _ in range(4))
            out.extend([_case('old_public_auxv_snapshot_exists'), _case('exec_preserves_owned_pid')])
        out.append(_case(stage, int(enabled)))
        for name in ['maps', 'mem', 'environ', 'auxv', 'fd', 'exe', 'ns/mnt', 'pidfd_getfd_dev_null']:
            expected_name = (lambda v: type(v) is str and re.fullmatch(r'fd/[0-9]{1,4}', v) is not None) if name == 'fd' else name
            if not enabled:
                count = -1
                error = lambda v: type(v) is int and v in (1, 13)
            else:
                count = 4 if name == 'mem' else 9 if name == 'fd' else 1
                if name in ('exe', 'ns/mnt'):
                    count = lambda v: type(v) is int and 0 < v <= 4096
                error = 0
            out.append({'stage': stage, 'operation': expected_name, 'rc': count, 'errno': error,
                        'denied_expected': not enabled, 'passed': True, 'own_child': True})
            if enabled and name == 'mem':
                out.append(_case('public_mem_sentinel_only', 0x5a17c0de))
        if enabled:
            out.append(_case('copied_own_dev_null_only'))
    for name in ['maps', 'mem', 'environ', 'auxv']:
        out.append(_case('old_proc_fd_rewind'))
        out.append(_case('old_auxv_is_empty_or_identical_old_snapshot') if name == 'auxv'
                   else _case(f'old_{name}_after_exec_empty', 0))
        length = (lambda v: type(v) is int and 0 <= v <= 4096 and v % 16 == 0) if name == 'auxv' else 0
        out.append({'operation': f'old_{name}_after_exec', 'read_bytes': length})
    out.extend([_case('sensitive_child_reaped'), _case('unprivileged_fixture_reaped'),
                {'summary': True, 'failed_fixtures': 0, 'all_children_reaped': True, 'production_isolation_qualified': False}])
    return out


def _stat_expected():
    out = [{'suite': 'dumpable-stat-v3', 'observer_uid': 60001, 'cap_eff': 0, 'cap_prm': 0, 'nnp': 1}]
    for enabled in [0, 1, 0]:
        out.extend({'case': name, 'passed': True} for name in ['child_set_get_agree', 'stat_exact_52_fields_parsed',
                   'ordinary_starttime_stable_nonzero', 'ordinary_vsize_readable_nonzero', 'ordinary_rss_readable_bounded'])
        for field in [26, 27, 28, 45, 46, 47, 48, 49, 50, 51]:
            mask = int(field in (26, 27))
            out.append({'stage_dumpable': enabled, 'field': field, 'masked_value': 0 if enabled else mask,
                        'expected_mask': mask, 'passed': True})
        out.extend([{'case': 'live_child_exit_code_zero', 'passed': True},
                    {'stage_dumpable': enabled, 'ordinary_fields_remain_readable': True, 'only_owned_child': True}])
    out.extend([{'case': 'owned_child_reaped', 'passed': True}, {'summary': True, 'violations': 0, 'all_children_reaped': True}])
    return out


def _match(values, expected):
    if len(values) != len(expected):
        raise ValueError(f'exact observation count mismatch: {len(values)} != {len(expected)}')
    for i, (actual, wanted) in enumerate(zip(values, expected)):
        if actual.keys() != wanted.keys():
            raise ValueError(f'observation{i}: closed keys/order mismatch')
        for key, value in wanted.items():
            if not (value(actual[key]) if callable(value) else _same(actual[key], value)):
                raise ValueError(f'observation{i}: {key} mismatch')
    # All three pre-exec reports must identify the very same retained target FD.
    links = [v['operation'] for v in values if 'stage' in v and str(v.get('operation', '')).startswith('fd/')]
    if links and (len(links) != 4 or len(set(links[:3])) != 1):
        raise ValueError('retained pre-exec target FD changed')


def _check(raw, code, timed_out, suite):
    try:
        values = _transcript(raw, code, timed_out)
        if suite == 'lifecycle':
            policies = [v for v in values if 'reset_policy' in v]
            if len(policies) != 1 or type(policies[0].get('policy_sysctl_present')) is not bool:
                raise ValueError('requires exactly one explicit reset policy')
            expected = _lifecycle_expected(policies[0]['policy_sysctl_present'])
        else:
            expected = _stat_expected()
        _match(values, expected)
        return {'passed': True, 'suite': suite, 'observations': len(values),
                'all_children_reaped': True, 'raw_qemu_exit': 33, 'timed_out': False,
                'production_isolation_qualified': False}
    except (ValueError, TypeError, UnicodeError, KeyError) as error:
        return {'passed': False, 'suite': suite, 'reason': str(error), 'production_isolation_qualified': False}


def check_lifecycle(raw, code, timed_out):
    return _check(raw, code, timed_out, 'lifecycle')


def check_stat(raw, code, timed_out):
    return _check(raw, code, timed_out, 'stat')


def check(raw, code, timed_out):
    """Dispatch only when exactly one known suite marker appears."""
    text = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else raw
    if type(text) is not str:
        return {'passed': False, 'reason': 'raw must be bytes or str'}
    if text.count('"dumpable-lifecycle-v2"') == 1 and '"dumpable-stat-v3"' not in text:
        return check_lifecycle(raw, code, timed_out)
    if text.count('"dumpable-stat-v3"') == 1 and '"dumpable-lifecycle-v2"' not in text:
        return check_stat(raw, code, timed_out)
    return {'passed': False, 'reason': 'requires one known suite'}
