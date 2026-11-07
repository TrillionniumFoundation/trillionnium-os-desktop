#!/usr/bin/env python3
"""Bind actual framework terminal digests; create local source/request only."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

TEMPLATE_SHA = 'b1f04340281d7927fe5a40078ed8023895348380141dba659b8cb6afa70115fc'
KEY = 'pocket4-native-typed-framework-build01-fixed-results-readonly-01-20261105'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'bytes': len(raw), 'sha256': digest(raw),
            'git_blob_sha1': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}


def actual_sha(value):
    if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise argparse.ArgumentTypeError('expected actual SHA256')
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outer-sha', type=actual_sha, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--inner-sha', type=actual_sha)
    group.add_argument('--no-inner-terminal', action='store_true')
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    template = (Path(__file__).parent / 'read_result.template.py').read_bytes()
    assert digest(template) == TEMPLATE_SHA
    source = template.decode()
    for old, new in [('__ACTUAL_OUTER_TERMINAL_SHA256__', args.outer_sha),
                     ('__ACTUAL_INNER_TERMINAL_SHA256_OR_NONE__', args.inner_sha)]:
        assert source.count(repr(old)) == 1
        source = source.replace(repr(old), repr(new))
    ast.parse(source)
    raw = source.encode()
    source_sha = digest(raw)
    wrapper = ('import hashlib\nsource=' + repr(source) + '\n'
               'assert hashlib.sha256(source.encode()).hexdigest()==' + repr(source_sha) + '\n'
               "scope={'__name__':'__main__','__file__':'<fixed-framework-result-reader>',"
               "'SOURCE_SHA256':" + repr(source_sha) + '}\n'
               "exec(compile(source,'fixed_framework_results.py','exec'),scope,scope)\n")
    request = {'host': 'pocket4', 'executable': '/usr/bin/python3',
        'args': ['-I', '-B', '-', '--execute-once'], 'stdin': wrapper, 'cwd': '/',
        'cpu_quota_percent': 25, 'memory_max_bytes': 268435456, 'nice': 15,
        'timeout_seconds': 60, 'idempotency_key': KEY}
    request_raw = (json.dumps(request, indent=2) + '\n').encode()
    args.destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    files = {'read_result.py': raw, 'exact-request.json': request_raw}
    for name, content in files.items():
        with (args.destination / name).open('xb') as stream:
            stream.write(content)
    binding = {'schema': 1, 'actual_outer_terminal_sha256': args.outer_sha,
        'actual_inner_terminal_sha256': args.inner_sha,
        'absence_not_inferred_from_unknown': True,
        'template_sha256': TEMPLATE_SHA, 'read_only': True,
        'source_or_binary_execution': False, 'files': {name: pin(value) for name, value in files.items()},
        'stdin': pin(wrapper.encode()), 'idempotency_key': KEY,
        'request_executed': False}
    (args.destination / 'BINDING.json').write_text(json.dumps(binding, indent=2) + '\n')
    print(json.dumps(binding, indent=2))


if __name__ == '__main__':
    main()
