#!/usr/bin/env python3
"""Create a separate lock from the complete actual three-root-tree observation.

This generator never contacts Git or the device and does not materialize source.
Root supplies the exact original report bytes/size/SHA after its unique reader.
The resulting source lock still requires normal droidloom-source validation and
the real strict framework/JNI build; it is not a dependency-closure receipt.
"""
import argparse
import base64
import copy
import hashlib
import json
import os
import re
import stat
from pathlib import Path

BASE_BYTES = 84522
BASE_SHA = '4d8f2d047254268305f4802d9dd67bebdfd162d836664c733ecc07e2f9ced178'
GIT_SHA = 'ed8b2df973b28c0fb773b9c0dc0816d3ee2b3835bb932d9153c21417bb51b362'
TOOL_AUTHORITY = '45d3a3307cf40c57c1835f1a275be7cb2e920f0d2b703880756ce0bd89386cfd'
AOSP = '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/'
PROJECTS = (
    ('frameworks/base', '94b4c163b7dfe5ce3607f7bb8456f9573f7de57d'),
    ('frameworks/native', 'ae266dcb706d083868578cfedce381ef44488a07'),
    ('external/skia', '508606366e71a3daa933a4e08bc49b84e387ec18'),
)


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def held(path, bound, expected_bytes=None, expected_sha=None):
    require(path.is_absolute() and path.resolve(strict=True) == path, 'input alias rejected')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= bound, 'input type/bound differs')
        chunks = []
        count = 0
        while True:
            block = os.read(fd, min(65536, bound + 1 - count))
            if not block:
                break
            count += len(block)
            require(count <= bound, 'input grew beyond bound')
            chunks.append(block)
        raw = b''.join(chunks)
        require(len(raw) == before.st_size and
                identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                'held/named input changed')
        require(expected_bytes is None or len(raw) == expected_bytes, 'input exact length differs')
        require(expected_sha is None or sha(raw) == expected_sha, 'input exact SHA differs')
        return raw
    finally:
        os.close(fd)


def root_directories(report):
    require(report['state'] == 'PASS_THREE_FIXED_COMMIT_ROOT_TREES' and
            report['first_error'] is None and not report['secondary_errors'] and
            report['all_started_children_joined'] is True,
            'actual reader did not complete all three fixed roots')
    require(report['source_lock_reference_sha256'] == BASE_SHA and
            report['tool_authority_sha256'] == TOOL_AUTHORITY and
            report['git_before'] == report['git_after'] and
            report['git_before']['sha256'] == GIT_SHA and
            report['git_before']['bytes'] == 4547768,
            'actual reader has different source/tool authority')
    require(report['owned_resource_gate']['pass'] is True and
            all(report['owned_memory_events_delta'][name] == 0
                for name in ['oom', 'oom_kill', 'oom_group_kill']),
            'actual reader resource gate did not pass')
    require(all(report[name] == 0 for name in
                ['Main_actions', 'fetches_requested', 'blob_reads_requested',
                 'recursive_git_reads', 'source_expansions', 'builds_started']),
            'actual reader scope differs')
    commands = report['commands']
    require(len(commands) == 3, 'actual reader did not return exactly three commands')
    result = {}
    for (relative, commit), row in zip(PROJECTS, commands):
        repo = AOSP + relative
        require(row['repository'] == repo and row['commit'] == commit and
                row['recursive'] is False and row['entry_bound'] == 128 and
                row['stdout_bound'] == row['stderr_bound'] == 32768,
                'actual root-tree command binding differs')
        require(row['argv'] == ['/usr/bin/git', '--no-pager', '--no-replace-objects',
                    '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
                    '-C', repo, 'ls-tree', '-z', commit],
                'actual ls-tree argv differs')
        require(row['returncode'] == 0 and row['joined'] is True and
                row['forced_kill'] is False and row['timed_out'] is False and
                row['error'] is None and not row.get('secondary_errors') and
                row['directory_before'] == row['directory_after'],
                'actual Git child, close or directory gate failed')
        outputs = {}
        for stream in ['stdout', 'stderr']:
            pin = row[stream]
            raw = base64.b64decode(pin['base64'], validate=True)
            require(pin['complete'] is True and len(raw) == pin['bytes'] and
                    len(raw) <= 32768 and sha(raw) == pin['sha256'],
                    'actual Git output is incomplete or its digest differs')
            outputs[stream] = raw
        raw = outputs['stdout']
        require(not outputs['stderr'] and raw and raw.endswith(b'\0'), 'actual root output malformed')
        entries = []
        seen = set()
        records = raw[:-1].split(b'\0')
        require(0 < len(records) <= 128, 'actual root entry count out of bound')
        for record in records:
            match = re.fullmatch(rb'([0-7]{6}) (tree|blob|commit) ([0-9a-f]{40})\t([^\x00]+)', record)
            require(match is not None, 'actual root entry format differs')
            mode, kind, oid, name = (part.decode('utf-8') for part in match.groups())
            require(name not in ('', '.', '..', '.git') and '/' not in name and name not in seen,
                    'actual root name is not a unique normal component')
            seen.add(name)
            require(kind != 'tree' or mode == '040000', 'actual root tree mode differs')
            entries.append({'mode': mode, 'type': kind, 'object': oid, 'name': name})
        directories = [entry['name'] for entry in entries if entry['type'] == 'tree']
        require(entries == row['entries'] and len(entries) == row['entry_count'] and
                directories == row['top_level_directories'],
                'actual root parsed rows do not match its complete stdout')
        result[relative] = {
            'commit': commit, 'directories': directories,
            'stdout_bytes': len(raw), 'stdout_sha256': sha(raw),
            'gitlinks_not_materialized_by_this_generator': [
                entry for entry in entries if entry['type'] == 'commit'],
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual-report', type=Path, required=True)
    parser.add_argument('--actual-bytes', type=int, required=True)
    parser.add_argument('--actual-sha256', required=True)
    parser.add_argument('--base-lock', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    require(0 < args.actual_bytes <= 1024 * 1024 and
            re.fullmatch('[0-9a-f]{64}', args.actual_sha256), 'actual result pin invalid')
    base_raw = held(args.base_lock, BASE_BYTES, BASE_BYTES, BASE_SHA)
    report_raw = held(args.actual_report, 1024 * 1024, args.actual_bytes, args.actual_sha256)
    roots = root_directories(json.loads(report_raw))
    base = json.loads(base_raw)
    expanded = copy.deepcopy(base)
    changes = []
    for relative, commit in PROJECTS:
        rows = [project for project in expanded['projects'] if project['path'] == relative]
        require(len(rows) == 1 and rows[0]['commit'] == commit, 'base lock project/commit differs')
        project = rows[0]
        before = list(project['sparse_paths'])
        require(before and len(before) == len(set(before)), 'base sparse paths malformed')
        added = sorted(name for name in roots[relative]['directories'] if name not in before)
        require(added and len(before) + len(added) <= 256, 'observed extension empty or over source-library bound')
        project['sparse_paths'] = before + added
        changes.append({'path': relative, 'commit': commit, 'old_count': len(before),
                        'new_count': len(project['sparse_paths']), 'added_root_directories': added,
                        'root_observation': roots[relative]})
    normalized = copy.deepcopy(expanded)
    old_by_path = {project['path']: project for project in base['projects']}
    for project in normalized['projects']:
        if project['path'] in roots:
            project['sparse_paths'] = old_by_path[project['path']]['sparse_paths']
    require(normalized == base, 'derived lock changed anything outside the three sparse arrays')
    require(held(args.base_lock, BASE_BYTES, BASE_BYTES, BASE_SHA) == base_raw and
            held(args.actual_report, 1024 * 1024, args.actual_bytes, args.actual_sha256) == report_raw,
            'generation authority changed')
    output = args.output_directory
    require(output.is_absolute() and output.parent.resolve(strict=True) == output.parent,
            'output parent must be an existing canonical directory')
    require(not output.exists() and not output.is_symlink(), 'output directory must be fresh')
    output.mkdir(mode=0o700)
    derived_raw = (json.dumps(expanded, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    receipt = {
        'schema': 1, 'state': 'DERIVED_THREE_PROJECT_SOURCE_EXTENSION_NOT_COMPILED',
        'base_lock_bytes': BASE_BYTES, 'base_lock_sha256': BASE_SHA,
        'actual_report_bytes': len(report_raw), 'actual_report_sha256': sha(report_raw),
        'derived_lock_bytes': len(derived_raw), 'derived_lock_sha256': sha(derived_raw),
        'changes': changes, 'other_lock_fields_unchanged': True,
        'original_lock_modified': False, 'source_materialized': False,
        'normal_source_library_validation_executed': False,
        'transitive_build_closure_qualified': False,
        'complete_framework_Java_and_Android_TU_compiled': False,
        'Main_actions': 0,
    }
    for name, raw in [('m2-role-ingress-source-lock.json', derived_raw),
                      ('derivation.json', (json.dumps(receipt, indent=2) + '\n').encode())]:
        with (output / name).open('xb') as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
