"""Strict read-only TRACEME lifecycle oracle; common raw parser is frozen."""
from lifecycle_checker import _match
from lifecycle_checker import _transcript

PUBLIC_SENTINEL = 0x5341464544554d50


def check(raw, code, timed_out):
    try:
        values = _transcript(raw, code, timed_out)
        expected = [{'suite': 'dumpable-traceme-v1', 'observer_uid': 60001, 'observer_gid': 60001,
                     'cap_eff': 0, 'cap_prm': 0, 'nnp': 1, 'own_child_only': True}]
        for stage in range(3):
            enabled = stage == 1
            expected.extend([
                {'stage': stage, 'traceme_rc': 0, 'traceme_errno': 0, 'set_rc': 0,
                 'dumpable': int(enabled), 'expected': int(enabled), 'owned_child_stopped': True},
                {'case': 'exact_owned_child_stage_and_stop', 'passed': True},
                {'stage': stage, 'operation': 'peek_public_sentinel_only',
                 'rc': PUBLIC_SENTINEL if enabled else -1, 'errno': 0 if enabled else 5,
                 'denied_expected': not enabled, 'passed': True},
                {'stage': stage, 'operation': 'continue_owned_child', 'rc': 0, 'errno': 0, 'passed': True},
            ])
        expected.extend([{'case': 'owned_child_reaped', 'passed': True},
                         {'summary': True, 'violations': 0, 'all_children_reaped': True,
                          'production_isolation_qualified': False}])
        _match(values, expected)
        return {'passed': True, 'suite': 'traceme', 'observations': len(values),
                'all_children_reaped': True, 'raw_qemu_exit': 33, 'timed_out': False,
                'production_isolation_qualified': False}
    except (ValueError, TypeError, UnicodeError, KeyError) as error:
        return {'passed': False, 'suite': 'traceme', 'reason': str(error),
                'production_isolation_qualified': False}
