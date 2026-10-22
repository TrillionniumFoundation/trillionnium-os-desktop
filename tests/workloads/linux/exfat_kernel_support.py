#!/usr/bin/env python3
"""Prepare the running Linux kernel's ExFAT driver on a disposable CI host.

exfatprogs supplies the formatter, not this driver. This command never changes
the running kernel, selects another ABI, mounts a disk, or qualifies a workload.
The separate reference runner must still mount and execute the frozen observer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


LIMIT = 8 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def has_exfat(raw):
    """Match the registered block filesystem, not a substring or nodev entry."""
    return sum(line.split() == [b'exfat'] for line in raw.splitlines()) == 1


def read_filesystems():
    with Path('/proc/filesystems').open('rb') as stream:
        raw = stream.read(65537)
    require(len(raw) <= 65536, 'unexpectedly large /proc/filesystems')
    return raw


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def tool(name):
    path = shutil.which(name)
    require(path is not None, f'{name} is required on the disposable CI host')
    return path


def run(out, report, name, command, *, allowed=(0,), timeout=30):
    """Keep the real command, output and status even when setup fails."""
    report.setdefault('commands', []).append({'name': name, 'argv': command})
    write_json(out / (name + '.command.json'), command)
    with (out / (name + '.stdout.log')).open('xb') as stdout, \
            (out / (name + '.stderr.log')).open('xb') as stderr:
        process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stdout,
                                 stderr=stderr, timeout=timeout, check=False,
                                 env={**os.environ, 'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive'})
    (out / (name + '.exit-code.txt')).write_text(str(process.returncode) + '\n')
    require(process.returncode in allowed, f'{name} failed with exit {process.returncode}; see raw logs')
    outputs = []
    for suffix in ('stdout.log', 'stderr.log'):
        path = out / (name + '.' + suffix)
        require(path.stat().st_size <= LIMIT, f'{name} output exceeds limit')
        outputs.append(path.read_bytes())
    return process.returncode, *outputs


def package_candidate(raw):
    matches = re.findall(rb'^  Candidate: (\S+)$', raw, re.MULTILINE)
    require(len(matches) <= 1, 'ambiguous apt package candidate')
    if not matches or matches[0] == b'(none)':
        return None
    value = matches[0].decode('ascii')
    require(re.fullmatch(r'[0-9][A-Za-z0-9.+:~\-]*', value) is not None, 'unexpected apt version')
    return value


def prepare(out, report):
    release = os.uname().release
    require(re.fullmatch(r'[0-9][A-Za-z0-9.+\-]{0,127}', release) is not None, 'unexpected running kernel ABI')
    report.update(kernel_release=release, installed_packages=[], registered_before=False,
                  registered_after=False, commands=[])
    before = read_filesystems()
    (out / 'filesystems-before.log').write_bytes(before)
    report['registered_before'] = has_exfat(before)
    if not report['registered_before']:
        modinfo = tool('modinfo')
        status, stdout, stderr = run(out, report, 'module-before',
                                    [modinfo, '--set-version', release, '--filename', 'exfat'], allowed=(0, 1))
        if status == 1:
            require(stdout == b'' and stderr == b'modinfo: ERROR: Module exfat not found.\n',
                    'module lookup failed for an unclassified reason; refusing to guess a package repair')
            # Both names are bound to the currently running ABI. Never install
            # a generic/cloud metapackage that could select a different kernel.
            apt_cache = tool('apt-cache')
            packages = []
            for kind in ('linux-modules', 'linux-modules-extra'):
                package = kind + '-' + release
                _, policy, _ = run(out, report, kind + '-policy', [apt_cache, 'policy', package])
                candidate = package_candidate(policy)
                if candidate is not None:
                    packages.append(package + '=' + candidate)
            require(packages, f'no module package candidate for the running kernel {release}')
            run(out, report, 'module-install',
                [tool('apt-get'), 'install', '-y', '--no-install-recommends', '--', *packages], timeout=300)
            report['installed_packages'] = packages
            _, stdout, _ = run(out, report, 'module-after-install',
                               [modinfo, '--set-version', release, '--filename', 'exfat'])
        require(len(stdout.splitlines()) == 1 and bool(stdout.strip()), 'module lookup did not return one driver')
        report['module_filename'] = stdout.decode().strip()
        run(out, report, 'module-load', [tool('modprobe'), '--', 'exfat'])
    after = read_filesystems()
    (out / 'filesystems-after.log').write_bytes(after)
    report['registered_after'] = has_exfat(after)
    require(os.uname().release == release, 'running kernel changed during preparation')
    require(report['registered_after'],
            f'ExFAT is not registered by running kernel {release}; the real reference cannot run')
    report['passed'] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-ci', action='store_true',
                        help='explicitly permit module installation/loading on this disposable CI host')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink(), 'output must be a new directory')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'schema': 'a06.exfat-linux-support.v1', 'passed': False,
              'scope': 'running-kernel filesystem availability only',
              'linux_reference_passed': False, 'guest_passed': False,
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        require(args.disposable_ci, 'module setup requires --disposable-ci on a disposable CI host')
        require(os.geteuid() == 0, 'module setup requires root on the disposable CI host')
        prepare(out, report)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    write_json(out / 'result.json', report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
