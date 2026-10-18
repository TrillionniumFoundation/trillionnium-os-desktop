#!/usr/bin/env python3
"""Preserve one actual command's raw output and source/resource receipt."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time

ROOT = Path('/workspace/scratch/98f315e377b2/next-ui')
OUT = Path('/workspace/scratch/98f315e377b2/next-tools/r3-evidence')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def binary_state():
    values = {}
    for path in Path('/workspace/scratch/98f315e377b2/r2-host-target/debug').glob('trill-*'):
        if path.is_file() and not path.name.endswith('.d'):
            stat = path.stat()
            values[path.name] = {'bytes': stat.st_size, 'mode': oct(stat.st_mode & 0o777),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == '--':
        command = command[1:]
    if not command:
        raise SystemExit('command required')
    OUT.mkdir(exist_ok=True)
    log = OUT / (args.label + '.log')
    receipt = OUT / (args.label + '.json')
    if log.exists() or receipt.exists():
        raise SystemExit('new case label required; old evidence is immutable')
    report = {'command': command, 'cwd': str(ROOT), 'source_commit': git('rev-parse', 'HEAD'),
        'source_tree': git('rev-parse', 'HEAD^{tree}'), 'source_status_before': git('status', '--short'),
        'started_unix_ns': time.time_ns(), 'free_bytes_before': shutil.disk_usage(ROOT).free,
        'binaries_before': binary_state()}
    minimum_free = [report['free_bytes_before']]
    done = threading.Event()

    def monitor():
        while not done.wait(.05):
            minimum_free[0] = min(minimum_free[0], shutil.disk_usage(ROOT).free)

    thread = threading.Thread(target=monitor)
    thread.start()
    try:
        with log.open('xb') as stream:
            completed = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
        report['exit_code'] = completed.returncode
    finally:
        done.set()
        thread.join()
        report.update({'finished_unix_ns': time.time_ns(), 'free_bytes_after': shutil.disk_usage(ROOT).free,
            'minimum_free_bytes': minimum_free[0], 'source_commit_after': git('rev-parse', 'HEAD'),
            'source_status_after': git('status', '--short'), 'binaries_after': binary_state()})
        if log.exists():
            report['raw_log_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
        receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'label': args.label, 'exit_code': report['exit_code'], 'source': report['source_commit'],
        'minimum_free_MiB': round(minimum_free[0] / 1024**2, 2), 'free_after_MiB': round(report['free_bytes_after'] / 1024**2, 2)}))
    raise SystemExit(report['exit_code'])


if __name__ == '__main__':
    main()
