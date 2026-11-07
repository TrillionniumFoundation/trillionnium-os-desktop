#!/usr/bin/env python3
"""Pure local scope relation checks; never claims an installer or runtime PASS."""
import hashlib
import json
import re

EPOCH = 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9'
PRIOR48_SHA = '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'
PRIOR48_BYTES = 59259


def need(test, message):
    if not test:
        raise RuntimeError(message)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def decode(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 1048576, 'BOUNDED_ORIGINAL_SCOPE_BYTES')
    def reject_constant(value):
        raise RuntimeError('NONFINITE_JSON_NUMBER')
    value = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=no_duplicates,
                       parse_constant=reject_constant)
    need(type(value) is dict, 'EXACT_SCOPE_OBJECT')
    return value


def validate_preserved49(prior48_raw, future49_raw, future49_pin,
                         expected_new_helper_package, already_verified_installer_scope_row):
    """Check only data correspondence AFTER the actual installer joint gate.

    The last two arguments must come from that separately pinned successful
    installer/build chain. This function does not replace that gate. No
    executable request may be sealed until its actual schema adapter has been
    reviewed and real receipts supplied.
    """
    need(len(prior48_raw) == PRIOR48_BYTES and hashlib.sha256(prior48_raw).hexdigest() == PRIOR48_SHA,
         'EXACT_POST_ZBJ_PRIOR48_REFERENCE')
    old = decode(prior48_raw)
    need(type(future49_pin) is dict and set(future49_pin) == {'path', 'bytes', 'sha256'} and
         type(future49_pin['path']) is str and future49_pin['path'].startswith('/home/alex/work/') and
         type(future49_pin['bytes']) is int and 0 < future49_pin['bytes'] <= 1048576 and
         type(future49_pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', future49_pin['sha256']),
         'ACTUAL_PINNED_FUTURE_SCOPE_INPUT_REQUIRED')
    need(type(future49_raw) is bytes and len(future49_raw) == future49_pin['bytes'] and
         hashlib.sha256(future49_raw).hexdigest() == future49_pin['sha256'],
         'ACTUAL_SCOPE49_FULL_BYTES_MUST_MATCH')
    new = decode(future49_raw)
    need(old.get('schema') == new.get('schema') == 'pocket4-versioned-app-scope-v1' and
         old.get('runtime_epoch_sha256') == new.get('runtime_epoch_sha256') == EPOCH,
         'SAME_TYPED_RUNTIME_NO_AUTOMATIC_NEW_EPOCH')
    need(type(old.get('apps')) is dict and len(old['apps']) == 48 and
         type(new.get('apps')) is dict and len(new['apps']) == 49,
         'ACTUAL49_REQUIRED_CURRENT48_IS_NOT_A_SUBSTITUTE')
    need(type(expected_new_helper_package) is str and expected_new_helper_package not in old['apps'] and
         re.fullmatch(r'org\.droidloom\.qa\.successor\.[A-Za-z0-9_.]+', expected_new_helper_package),
         'ACTUAL_NEW_HELPER_PACKAGE_FROM_REVIEWED_INSTALL_REQUIRED')
    need(set(new['apps']) == set(old['apps']) | {expected_new_helper_package}, 'EXACT49_SET_NO_EXTRA_OR_MISSING_PACKAGE')
    need(all(new['apps'][package] == row for package, row in old['apps'].items()), 'ALL_48_PRIOR_PACKAGE_ROWS_MUST_REMAIN_EXACT')
    helper = new['apps'][expected_new_helper_package]
    need(type(already_verified_installer_scope_row) is dict and helper == already_verified_installer_scope_row and
         helper.get('package') == expected_new_helper_package and type(helper.get('uid')) is int and helper['uid'] > 0 and
         type(helper.get('apks')) is list and len(helper['apks']) > 0,
         'REAL_NEW_HELPER_ROW_MUST_EQUAL_ALREADY_VERIFIED_INSTALLER')
    return {'schema': 'pocket4-local-scope49-correspondence-only-v1', 'scope': future49_pin,
        'packages': sorted(new['apps']), 'prior48_rows_exact': True, 'new_helper': helper,
        'installer_joint_gate_performed_by_this_function': False,
        'runtime_guard_or_scope_observation_performed_by_this_function': False,
        'new_permissions_observed': False, 'may_seal_executable_request_without_actual_joint_gates': False}
