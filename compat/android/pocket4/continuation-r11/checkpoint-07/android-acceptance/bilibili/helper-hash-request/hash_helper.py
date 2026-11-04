#!/usr/bin/env python3
"""Read one already-qualified helper artifact by exact observed identity; never execute it."""
import argparse
import hashlib
import json
import os
import stat
import time

PATH = '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry'
EXPECTED_BYTES = 4_366_312
EXPECTED_SHA256 = '21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689'
EXPECTED = {
    'st_dev': 66306, 'st_ino': 34351801, 'st_size': EXPECTED_BYTES,
    'st_mode': 33216, 'st_nlink': 1, 'st_uid': 1000, 'st_gid': 1000,
    'st_mtime_ns': 1793813011502010027, 'st_ctime_ns': 1793813011503010028,
}
QUALIFICATION_SHA256 = '3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3'
PRIOR_METADATA_STDOUT_SHA256 = '476686a05d49afb8c300a0b81445d07eabc1946f301d459fce5abb86764b88ec'
SECONDS = 5


def identity(value):
    return {key: getattr(value, key) for key in EXPECTED}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true')
    args = parser.parse_args()
    report = {
        'schema': 1, 'path': PATH, 'expected_bytes': EXPECTED_BYTES,
        'expected_sha256': EXPECTED_SHA256,
        'previous_metadata_stdout_sha256': PRIOR_METADATA_STDOUT_SHA256,
        'original_qualification_sha256': QUALIFICATION_SHA256,
        'original_generic_limit_unchanged': True,
        'no_content_bytes_exported': True, 'helper_executed': False,
        'original_flow_replayed': False, 'Android_UI_audio_actions': 0,
        'whole_app_production_ready': False,
    }
    if not args.inspect:
        report['state'] = 'PLAN_ONLY'
        print(json.dumps(report, sort_keys=True))
        return 0
    descriptor = None
    report.update(state='FAILED', secondary_errors=[], content_bytes_read=0)
    started = time.monotonic()
    try:
        descriptor = os.open(PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        before = os.fstat(descriptor)
        report['before'] = identity(before)
        require(stat.S_ISREG(before.st_mode) and identity(before) == EXPECTED,
                'EXACT_PREVIOUSLY_OBSERVED_ARTIFACT_IDENTITY_CHANGED')
        hasher = hashlib.sha256()
        count = 0
        while count < EXPECTED_BYTES:
            require(time.monotonic() - started <= SECONDS, 'READ_DEADLINE_EXCEEDED')
            data = os.read(descriptor, min(65536, EXPECTED_BYTES - count))
            require(bool(data), 'UNEXPECTED_EARLY_EOF')
            hasher.update(data)
            count += len(data)
            report['content_bytes_read'] = count
        require(time.monotonic() - started <= SECONDS, 'READ_DEADLINE_EXCEEDED')
        after = os.fstat(descriptor)
        report['after'] = identity(after)
        require(identity(after) == EXPECTED and count == EXPECTED_BYTES,
                'ARTIFACT_CHANGED_DURING_BOUNDED_READ')
        report['actual_sha256'] = hasher.hexdigest()
        require(report['actual_sha256'] == EXPECTED_SHA256,
                'HELPER_DIFFERS_FROM_ORIGINAL_QUALIFIED_ARTIFACT')
        report['content_matches_original_qualified_helper'] = True
        report['state'] = 'EXACT_ORIGINAL_HELPER_HASH_MATCH'
    except BaseException as error:
        report['primary_error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except BaseException as error:
                report['secondary_errors'].append({'type': type(error).__name__, 'message': str(error)})
        report['seconds'] = time.monotonic() - started
        if report['secondary_errors']:
            report['state'] = 'FAILED'
    print(json.dumps(report, sort_keys=True))
    return 0 if report['state'] == 'EXACT_ORIGINAL_HELPER_HASH_MATCH' else 1


if __name__ == '__main__':
    raise SystemExit(main())
