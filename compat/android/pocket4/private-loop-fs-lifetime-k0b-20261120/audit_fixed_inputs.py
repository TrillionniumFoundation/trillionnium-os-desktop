#!/usr/bin/python3
"""Read the exact matching K0a tree; never change it or run a compiler."""
from pathlib import Path
import hashlib
import json
import os
import re
import resource
import signal
import stat
import subprocess
import time

SOURCE = Path('/home/alex/work/p4-private-loop-k0a-compile-20261120-3b9d-r1/source/linux-6.18.64')
DEST = Path('/home/alex/work/p4-private-loop-k0b-20261120-3b9d-r1')
PATTERN = r'fs_cachep|free_fs_struct\(|copy_fs_struct\(|unshare_fs_struct\(|struct fs_struct\b|(?:fs|new_fs|old_fs|our_fs|this_fs|newfs|oldfs)->users|->fs->users'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def read(path):
    need(path.resolve() == path, 'exact source path without aliases')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(stat.S_ISREG(before[2]) and before[5] == 1 and before[6] <= 8 * 1024**2,
             'bounded actual single-link source file')
        with os.fdopen(os.dup(fd), 'rb') as source:
            raw = source.read(8 * 1024**2 + 1)
        need(len(raw) == before[6] and before == f9(os.fstat(fd)) == f9(path.lstat()),
             'actual full source body and identity bookends')
        return {'path': str(path), 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'identity': before}, raw
    finally:
        os.close(fd)


def main():
    need(os.getuid() == os.geteuid() == 1000, 'ordinary original Pocket4 owner')
    need(23 in os.sched_getaffinity(0), 'reserved independent CPU23 available')
    os.sched_setaffinity(0, {23})
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.alarm(120)
    need(not os.path.lexists(DEST), 'new isolated K0b workspace only')
    need(DEST.parent.resolve() == DEST.parent and SOURCE.resolve() == SOURCE,
         'unchanged canonical work/source parents')
    instructions = []
    for parent in [DEST.parent, *DEST.parent.parents, SOURCE, *SOURCE.parents]:
        candidate = parent / 'AGENTS.md'
        if candidate in instructions:
            continue
        instructions.append(candidate)
        need(not os.path.lexists(candidate), 'new applicable instructions need review: ' + str(candidate))
    preparation, raw = read(SOURCE.parent.parent / 'TREE-PREPARATION.json')
    need(preparation['sha256'] == '232793bb6e70cfdd0aba664c1a0be17f2a623d465cc2507a884582f65f18b243',
         'the actual prepared matching source tree')
    prior = json.loads(raw)
    # Confirm the fixed existing candidate and the already compiled K0a source
    # before inspecting every C/header occurrence in this complete source tree.
    original, raw = read(SOURCE.parent.parent / 'inputs/candidate-source-pins.json')
    need(original['sha256'] == '4b5b19d3cbcd3caa5eb48ec65bc0e5dc3f0e1651f5f41a26a434019ece8686e7',
         'exact final qualified 66-file source pin body')
    qualified = json.loads(raw)
    need(type(qualified) is list and len(qualified) == 66
         and len({x['path'] for x in qualified}) == 66,
         'complete final qualified source roster')
    confirmed = []
    for entry in qualified:
        path = SOURCE / entry['path']
        need(path.is_relative_to(SOURCE), 'qualified source remains in its original tree')
        reference, _ = read(path)
        need((reference['bytes'], reference['sha256'])
             == (entry['after_bytes'], entry['after_sha256']), 'actual final candidate body')
        confirmed.append(reference)
    for entry in prior['k0a_postimages']:
        reference, _ = read(SOURCE / entry['path'])
        need((reference['bytes'], reference['sha256'])
             == (entry['after']['bytes'], entry['after']['sha256']), 'unchanged compiled K0a body')
        confirmed.append(reference)
    DEST.mkdir(mode=0o700)
    argv = ['/usr/bin/rg', '-n', '--no-heading', '--color', 'never',
            '--glob', '*.[ch]', '--', PATTERN, str(SOURCE)]
    started = time.monotonic_ns()
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, close_fds=True)
    pidfd = os.pidfd_open(child.pid, 0)
    try:
        try:
            stdout, stderr = child.communicate(timeout=90)
        except BaseException:
            child.kill()
            child.communicate()
            raise
        need(child.returncode == 0 and not stderr and len(stdout) < 512 * 1024,
             'complete bounded original source search')
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        os.close(pidfd)
    finished = time.monotonic_ns()
    rows = {}
    for line in stdout.decode('utf-8', 'strict').splitlines():
        path, number, text = line.split(':', 2)
        p = Path(path)
        need(p.is_relative_to(SOURCE), 'search remains within exact matching tree')
        rows.setdefault(p, []).append({'line': int(number), 'text': text})
    complete = []
    for path, matches in sorted(rows.items()):
        ref, body = read(path)
        lines = body.decode('utf-8', 'strict').splitlines()
        need(all(lines[m['line'] - 1] == m['text'] for m in matches),
             'complete body matches actual original search observation')
        intervals = []
        for match in matches:
            lo, hi = max(1, match['line'] - 8), min(len(lines), match['line'] + 12)
            if intervals and lo <= intervals[-1][1] + 1:
                intervals[-1][1] = max(intervals[-1][1], hi)
            else:
                intervals.append([lo, hi])
        excerpts = [{'first_line': lo, 'last_line': hi,
                     'text': '\n'.join(lines[lo - 1:hi]) + '\n'} for lo, hi in intervals]
        complete.append({'reference': ref, 'matches': matches, 'excerpts': excerpts})
    # Read all selected originals again after the complete bounded audit.
    for entry in complete:
        after, _ = read(Path(entry['reference']['path']))
        need(after == entry['reference'], 'original source changed during allocation audit')
    need(read(SOURCE.parent.parent / 'TREE-PREPARATION.json')[0] == preparation,
         'original preparation remains unchanged')
    for reference in confirmed:
        need(read(Path(reference['path']))[0] == reference,
             'all final qualified and compiled K0a inputs remain unchanged')
    report = {'schema': 'p4-k0b-actual-fixed-fs-lifetime-source-audit-v1',
        'source': str(SOURCE), 'original_matching_preparation': preparation,
        'original_qualified_source_pins': original, 'search_pattern': PATTERN,
        'all_66_final_candidate_and_4_K0a_bodies_checked': confirmed,
        'actual_search': {'argv': argv, 'pid': child.pid, 'exit_code': child.returncode,
            'started_ns': started, 'finished_ns': finished,
            'original_pidfd_held_until_reaped': True, 'actual_child_reaped': True,
            'stdout_bytes': len(stdout), 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
            'stderr_bytes': len(stderr), 'stderr_sha256': hashlib.sha256(stderr).hexdigest()},
        'complete_selected_file_bodies_bookended': True, 'files': complete,
        'source_mutations': 0, 'compiler_started': False, 'device_operations': 0,
        'kernel_loaded': False, 'Android_started': False, 'VM_started': False,
        'runtime_qualified': False, 'production_ready': False}
    output = DEST / 'FIXED-FS-LIFETIME-AUDIT.json'
    with output.open('x') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    ref, _ = read(output)
    print(json.dumps({'audit': ref, 'files': len(complete),
                      'source_mutations': 0, 'compiler_started': False}), flush=True)


if __name__ == '__main__':
    main()
