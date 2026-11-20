#!/usr/bin/python3
"""Read ai395's exact direct symbol providers; execute no downloaded ELF."""
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/home/qq/work/current2367-cli-preparation-20261120-3b9d-r1')
IMPORTS_SHA = ''  # Only the new actual nineteen-ELF import inspection may freeze this.
PARSER_SHA = 'ee7d12c317672046547a5ca7ebb90cd6e30fc3fb9cb3b925d038b21f2bd9cced'
PROCESS_SHA = 'c045a56847ff90d8a72b0d72dbb1ee312a02d2a21e14b62ab213ce8a9f3e1d82'
CURRENT = {'tree': 'fd0ef624e436d1eb5c8d2c4083335088811a6a42', 'files': 2367, 'bytes': 45262277}
HEAD = ''  # Actual successful GitHub checkout head, not yet frozen.


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def f9(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def read(path, cap=64 * 1024**2):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, 'resolved canonical library or evidence required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= cap,
             'bounded independent regular input required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(before.st_size + 1)
        need(len(raw) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()),
             'whole input changed during held read')
        return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'identity': f9(before)}, raw
    finally:
        os.close(fd)


def module(path, expected):
    before, raw = read(path)
    need(before['sha256'] == expected, 'fixed complete inspector module required')
    spec = importlib.util.spec_from_file_location('p4_abi_' + path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    need(read(path)[0] == before, 'inspector changed during import')
    return result, before


def write_new(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return read(path)[0]


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == 1000 and os.uname().machine == 'x86_64',
         'ordinary ai395 account and native x86_64 architecture required')
    need(len(IMPORTS_SHA) == len(PARSER_SHA) == 64, 'actual current import input is not frozen')
    imports_ref, raw = read(ROOT / 'BINARY-IMPORTS.json')
    need(imports_ref['sha256'] == IMPORTS_SHA, 'complete actually inspected current imports required')
    request = json.loads(raw)
    need(request['schema'] == 'p4-current19-actual-static-import-inputs-v1'
         and request['head'] == HEAD and request['source'] == CURRENT and request['binary_count'] == 19,
         'same actual current source and release identity')
    parser, parser_ref = module(ROOT / 'elf_symbols.py', PARSER_SHA)
    process, process_ref = module(ROOT / 'owned_process.py', PROCESS_SHA)
    binaries = request['binaries']
    need(len(binaries) == len({r['binary'] for r in binaries}) == 19
         and all(re.fullmatch(r'[a-z0-9-]+', r['binary']) for r in binaries), 'all nineteen distinct exact binaries')
    needed = sorted(set().union(*(set(r['needed']) for r in binaries)))
    need(needed == request['needed_sonames'] and len(needed) == 8
         and all(re.fullmatch(r'[A-Za-z0-9_.-]+', n) for n in needed), 'eight exact direct SONAME providers')
    need(all(r['interpreter'] == '/lib64/ld-linux-x86-64.so.2' for r in binaries), 'same actual interpreter')
    wanted = set().union(*(set(r['strong_imports']) | set(r['weak_imports']) for r in binaries))
    cpus = sorted(os.sched_getaffinity(0))
    need(len(cpus) >= 3, 'leave at least two logical CPUs unused')
    os.sched_setaffinity(0, {cpus[0]})
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2, 8 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    need(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, 'owned child subreaper')
    need(not process.owned_children(), 'no unrelated child may enter the inspector scope')
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(signum, process.interrupted)
    signal.alarm(120)
    output = ROOT / 'abi'
    output.mkdir(mode=0o700)
    result = {'schema': 'p4-current19-static-direct-import-compatibility-v1', 'host': 'ai395',
        'hostname_observed': os.uname().nodename, 'uid': os.getuid(), 'source': CURRENT, 'head': HEAD,
        'binary_count': 19, 'host_libraries': 8, 'libraries': [], 'host_abi_inputs': [], 'binaries': [],
        'commands': [], 'errors': [], 'passed_direct_symbols_only': False,
        'dynamic_transitive_loading_tested': False, 'runtime_qualified': False, 'production_ready': False,
        'activated': False, 'target_executions': 0, 'target_binaries_executed': 0,
        'network_operations': False, 'source_locks_acquired': False,
        'affinity': [cpus[0]], 'reserved_cpus': cpus[1:], 'started_ns': time.time_ns(),
        'inputs': [imports_ref, parser_ref, process_ref], 'all_original_children_reaped': False}

    def command(name, argv, timeout):
        started = time.time_ns()
        stdout, stderr = output / (name + '.stdout'), output / (name + '.stderr')
        with stdout.open('xb') as out, stderr.open('xb') as err:
            observed = process.execute_child(argv, ROOT, {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'},
                                             out, err, timeout)
        outref, raw = read(stdout, 4 * 1024**2)
        errref, errraw = read(stderr, 1024**2)
        row = {'name': name, 'argv': argv, 'started_ns': started, 'finished_ns': time.time_ns(),
               **observed, 'stdout': outref, 'stderr': errref}
        result['commands'].append(row)
        write_new(output / (name + '.command.json'), row)
        need(row['exit_code'] == 0 and row['actual_child_reaped'] and row['original_pidfd_held_until_reaped']
             and row['error'] is None and not row['timed_out'] and not row['cleanup_errors']
             and not row['owned_descendants_remaining'] and not row['retired_descendants'] and errraw == b'',
             'actual ordinary provider inspection or retirement failed')
        return raw, row

    try:
        binary_before = {}
        for row in binaries:
            item, body = read(ROOT / 'bin' / row['binary'])
            need((item['bytes'], item['sha256']) == (row['bytes'], row['sha256'])
                 and item['identity'][2] == stat.S_IFREG | 0o755 and item['identity'][3:6] == [1000, 1000, 1]
                 and body[:7] == bytes.fromhex('7f454c46020101') and body[18:20] == bytes.fromhex('3e00'),
                 'complete currently deployed ordinary ELF must match actual local import inspection')
            binary_before[row['binary']] = item
        cache, cache_command = command('ldconfig-read-cache', ['/usr/sbin/ldconfig', '-p'], 5)
        candidates = {name: {} for name in needed}
        for line in cache.decode('utf-8', 'strict').splitlines():
            match = re.fullmatch(r'\s*(\S+)\s+\(([^)]+)\)\s+=>\s+(/\S+)\s*', line)
            if match and match[1] in candidates and 'x86-64' in match[2].split(','):
                alias = Path(match[3])
                resolved = alias.resolve(strict=True)
                candidates[match[1]].setdefault(str(resolved), set()).add(str(alias))
        interpreter = Path('/lib64/ld-linux-x86-64.so.2').resolve(strict=True)
        loader = 'ld-linux-x86-64.so.2'
        need(loader in candidates, 'actual loader must remain an explicit needed provider')
        if not candidates[loader]:
            candidates[loader][str(interpreter)] = {'/lib64/ld-linux-x86-64.so.2'}
        need(set(candidates[loader]) == {str(interpreter)}, 'actual program interpreter and cache provider differ')
        need(all(len(candidates[name]) == 1 for name in needed), 'a unique actual native cache provider for every SONAME')
        definitions = {}
        for name in needed:
            resolved, aliases = next(iter(candidates[name].items()))
            item, body = read(Path(resolved))
            need(body[:7] == bytes.fromhex('7f454c46020101') and body[18:20] == bytes.fromhex('3e00'),
                 'actual direct provider must be a native x86_64 ELF')
            raw, row = command('provider-' + name, ['/usr/bin/readelf', '--wide', '--dyn-syms', resolved], 8)
            parsed = parser.dynamic_symbols(raw)
            defined = set(parsed['definitions'])
            need(read(Path(resolved))[0] == item, 'whole provider changed across actual readelf')
            definitions[name] = defined
            result['libraries'].append({'soname': name, 'provider': item, 'resolved_from': min(aliases),
                'matched_required_symbols': sorted(defined & wanted), 'defined_symbol_count': len(defined),
                'dynamic_symbol_rows': parsed['dynamic_symbol_rows'], 'readelf_command': row})
        result['host_abi_inputs'] = sorted([r['provider'] for r in result['libraries']], key=lambda r: r['path'])
        need(len({r['path'] for r in result['host_abi_inputs']}) == 8, 'all eight independent actual provider paths')
        for row in binaries:
            available = set().union(*(definitions[name] for name in row['needed']))
            result['binaries'].append({'binary': row['binary'], 'sha256': row['sha256'], 'needed': row['needed'],
                'current_file': binary_before[row['binary']], 'strong_import_count': len(row['strong_imports']),
                'missing_strong': sorted(set(row['strong_imports']) - available),
                'unresolved_weak': sorted(set(row['weak_imports']) - available)})
        need(all(row['missing_strong'] == [] for row in result['binaries']), 'a direct strong import is absent from its needed providers')
        need(all(read(Path(item['path']))[0] == item for item in result['host_abi_inputs']), 'whole provider final bookend differs')
        need(all(read(ROOT / 'bin' / name)[0] == item for name, item in binary_before.items()), 'whole binary final bookend differs')
        need(all(read(Path(item['path']))[0] == item for item in result['inputs']), 'whole inspector input final bookend differs')
        need(not process.owned_children(), 'owned inspection child remains')
        result['all_original_children_reaped'] = True
        result['unique_strong_imports'] = len(set().union(*(set(r['strong_imports']) for r in binaries)))
        result['passed_direct_symbols_only'] = True
    except BaseException as failure:
        result['errors'].append({'type': type(failure).__name__, 'message': str(failure)})
    finally:
        signal.alarm(0)
        try:
            retired = process.reap_descendants()
            result['final_retirement'] = retired
            if retired or process.owned_children():
                result['passed_direct_symbols_only'] = result['all_original_children_reaped'] = False
                result['errors'].append({'type': 'RetirementError', 'message': 'unexpected descendant at final retirement'})
        except BaseException as failure:
            result['passed_direct_symbols_only'] = result['all_original_children_reaped'] = False
            result['errors'].append({'type': type(failure).__name__, 'message': str(failure)})
        result['finished_ns'] = time.time_ns()
        report_ref = write_new(output / 'HOST-DIRECT-SYMBOL-REVIEW.json', result)
    print(json.dumps({'passed_direct_symbols_only': result['passed_direct_symbols_only'],
                      'report': report_ref, 'errors': result['errors']}, sort_keys=True))
    return 0 if result['passed_direct_symbols_only'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
