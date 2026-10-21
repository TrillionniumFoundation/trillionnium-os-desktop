#!/usr/bin/env python3
"""Read-only source/patch audit and bounded, in-memory Markdown regression check.

Does not apply patches, execute the publication validator, compile a probe,
create mount namespaces, or launch a kernel. Source arguments are read only.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import signal
import time


HERE = Path(__file__).resolve().parent
PIVOT_PATH = 'tests/workloads/linux/permission_probe.c'
ORACLE_PATH = 'tests/workloads/linux/run_permission_guest.py'
VALIDATOR_PATH = 'results/integration/2026-10-19-g1b-usage/source-publication/validate-publication.py'
PIVOT_OLD = '    REQUIRE(!mounts || before_marker >= 0);\n'
PIVOT_NEW = PIVOT_OLD + '''    if (test->operation == PIVOT_DENIED) {
        // The marker lookup proves this real directory is searchable after dropping caps.
        // Linux may resolve both pivot_root paths before checking CAP_SYS_ADMIN.
        REQUIRE(S_ISDIR(before.st_mode) && before_marker == 1);
    }
'''
PIVOT_REPLACEMENTS = [
    (PIVOT_OLD, PIVOT_NEW),
    ('syscall(SYS_pivot_root, NULL, NULL)',
     'syscall(SYS_pivot_root, "mountpoint", "mountpoint")'),
]
REGEX_REPLACEMENTS = [(r'[^\s)\\]', r'[^\s()\\]')]


def identity(data):
    header = b'blob ' + str(len(data)).encode() + b'\0'
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'git_blob': hashlib.sha1(header + data).hexdigest()}


def require(value, message):
    if not value:
        raise ValueError(message)


def replace_once(text, before, after):
    require(text.count(before) == 1, 'source replacement is not unique')
    return text.replace(before, after, 1)


def variants(data, expected_old, expected_new, replacements):
    actual = identity(data)
    text = data.decode('utf-8')
    if actual == expected_old:
        old = text
        new = text
        for before, after in replacements:
            new = replace_once(new, before, after)
        state = 'baseline'
    elif actual == expected_new:
        new = text
        old = text
        for before, after in reversed(replacements):
            old = replace_once(old, after, before)
        state = 'candidate'
    else:
        raise ValueError('source identity differs; do not apply a stale candidate')
    require(identity(old.encode()) == expected_old, 'baseline identity mismatch')
    require(identity(new.encode()) == expected_new, 'candidate identity mismatch')
    return old, new, state


def link_function(source):
    functions = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name == 'link_destinations']
    require(len(functions) == 1, 'missing unique link_destinations function')
    isolated = ast.Module(body=functions, type_ignores=[])
    namespace = {'re': re, '__builtins__': {'len': len}}
    exec(compile(isolated, '<isolated-link-function>', 'exec'), namespace)
    return namespace['link_destinations']


def bounded(function, text, seconds):
    def expired(_signum, _frame):
        raise TimeoutError('bounded adversarial regression watchdog')
    previous = signal.signal(signal.SIGALRM, expired)
    start = time.perf_counter()
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        matches = function(text)
        return {'timed_out': False, 'matches': matches,
                'seconds': time.perf_counter() - start, 'bytes': len(text.encode())}
    except TimeoutError:
        return {'timed_out': True, 'seconds': time.perf_counter() - start,
                'bytes': len(text.encode())}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def regex_checks(old, new):
    baseline, candidate = link_function(old), link_function(new)
    cases = [
        ('[a](file.md)', ['file.md']),
        ('![x](images/a.png)', ['images/a.png']),
        ('[a](<space path.md>)', ['space path.md']),
        (r'[a](foo\)bar.md)', [r'foo\)bar.md']),
        ('[a](foo.md "title")', ['foo.md']),
        ("[a](foo.md 'title')", ['foo.md']),
        ('[a](one.md) [b](two.md)', ['one.md', 'two.md']),
        ('[a][ref]\n[ref]: file.md', ['file.md']),
        ('`[a](ignored.md)` [b](visible.md)', ['visible.md']),
        ('```md\n[a](ignored.md)\n```\n[b](visible.md)', ['visible.md']),
        ('~~~md\n[a](ignored.md)\n~~~\n[b](visible.md)', ['visible.md']),
    ]
    for text, expected in cases:
        require(baseline(text) == expected, 'baseline supported-link expectation differs')
        require(candidate(text) == expected, 'candidate supported-link regression')
    parenthesized = '[a](foo(bar).md)'
    require(baseline(parenthesized) == ['foo(bar'], 'baseline parenthesis behavior differs')
    require(candidate(parenthesized) == ['foo(bar).md'], 'parenthesized path regression')
    require(hasattr(signal, 'setitimer'), 'bounded check requires a POSIX signal timer')
    red = bounded(baseline, '[](' + '(\\)' * 28, 1.0)
    green = bounded(candidate, '[](' + '(\\)' * 100000, 2.0)
    require(red['timed_out'], 'baseline negative control did not hit watchdog')
    require(not green['timed_out'] and green['matches'] == [],
            'candidate failed bounded malformed-input control')
    return {'unchanged_positive_cases': len(cases),
            'corrected_parenthesis_case': {'baseline': ['foo(bar'],
                                           'candidate': ['foo(bar).md']},
            'baseline_negative': red,
            'candidate_negative': green,
            'scope': 'Only the reproduced exponential family and listed supported links; no whole-validator linear-time proof or CodeQL clearance.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-file', type=Path, default=Path(PIVOT_PATH))
    parser.add_argument('--oracle-file', type=Path, default=Path(ORACLE_PATH))
    parser.add_argument('--validator-file', type=Path, default=Path(VALIDATOR_PATH))
    parser.add_argument('--regex-check', action='store_true')
    args = parser.parse_args()
    expected = json.loads((HERE / 'source-identities.json').read_text())
    _, pivot, pivot_state = variants(args.probe_file.read_bytes(), expected['pivot_old'],
                                     expected['pivot_new'], PIVOT_REPLACEMENTS)
    old, new, regex_state = variants(args.validator_file.read_bytes(), expected['codeql_old'],
                                     expected['codeql_new'], REGEX_REPLACEMENTS)
    require(identity(args.oracle_file.read_bytes()) == expected['oracle'],
            'independent permission oracle changed')
    require('MOUNT_CASE("pivot_without_cap", PIVOT_DENIED, OTHER, 0, EPERM)' in pivot,
            'pivot capability contract changed')
    result = {'passed': True, 'pivot_source_state': pivot_state,
              'validator_source_state': regex_state, 'oracle_unchanged': True,
              'source_identities_verified': True, 'source_mutated': False,
              'native_probe_executed': False, 'publication_validator_executed': False}
    if args.regex_check:
        result['regex_checks'] = regex_checks(old, new)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
