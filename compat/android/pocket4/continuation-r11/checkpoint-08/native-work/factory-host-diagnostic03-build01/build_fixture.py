#!/usr/bin/env python3
"""One-attempt, task-owned host build. No service or namespace execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys
import time
import traceback

CANDIDATE = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/overlay-reconstruction-09/candidate-05')
MANIFEST = CANDIDATE.parent / 'candidate-05-source-manifest.json'
MANIFEST_SHA = '4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba'
COMPILER = Path('/usr/bin/x86_64-linux-gnu-g++-15')
COMPILER_SHA = 'e6718f7e0c7d057c3ff77b550c603da9bc4030e3ede3c053705acce1293dbe4d'
SOURCE_RECEIPT = CANDIDATE.parent / 'candidate-05-report.json'
SOURCE_RECEIPT_SHA = '33697d93292428c660f69c629ab9851248f5e5e1c3653f9531e5382f49479d36'
MATCHED_GATE = CANDIDATE.parent / 'combined-ancillary-controls-07/report.json'
MATCHED_GATE_SHA = 'e53c3e9e5846d36f971bae6140c394b837fa54525c0e2df4ac153c9ef5540803'
EXACT_SOURCE = Path('/home/alex/work/pocket4-owned-factory-v2-host-source-03')
EXACT_OUT = Path('/home/alex/work/pocket4-owned-factory-v2-host-build-03')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path) -> dict:
    resolved = path.resolve(strict=True)
    before = resolved.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 128 * 1024 * 1024:
        raise RuntimeError('unexpected build input: ' + str(path))
    data = resolved.read_bytes()
    after = resolved.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode')
    if any(getattr(before, key) != getattr(after, key) for key in fields):
        raise RuntimeError('input changed while read: ' + str(path))
    return {'path': str(path), 'resolved_path': str(resolved), 'bytes': len(data),
            'sha256': digest(data), 'device': after.st_dev, 'inode': after.st_ino,
            'mtime_ns': after.st_mtime_ns, 'ctime_ns': after.st_ctime_ns,
            'mode': stat.S_IMODE(after.st_mode)}


def save(path: Path, value: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def matched_gate_contract() -> None:
    source_raw = SOURCE_RECEIPT.read_bytes()
    gate_raw = MATCHED_GATE.read_bytes()
    if digest(source_raw) != SOURCE_RECEIPT_SHA or digest(gate_raw) != MATCHED_GATE_SHA:
        raise RuntimeError('actual candidate05 receipts changed')
    source, gate = json.loads(source_raw), json.loads(gate_raw)
    if not (source['source_manifest_sha256'] == MANIFEST_SHA and
            gate['state'] == 'MATCHED_SMALL_GATES_PASSED' and gate['source_manifest_sha256'] == MANIFEST_SHA and
            gate['source_unchanged'] is True and gate['all_commands_pass'] is True and
            gate['actual_host_adapter_checks'] == 8 and gate['actual_ancillary_cases'] == 34 and
            gate['actual_listener_inheritance_fixed'] is True and len(gate['commands']) == 8 and
            all(row['returncode'] == 0 for row in gate['commands'])):
        raise RuntimeError('actual candidate05 matched gate is incomplete')


def inventory() -> dict[str, str]:
    matched_gate_contract()
    raw = MANIFEST.read_bytes()
    if digest(raw) != MANIFEST_SHA:
        raise RuntimeError('combined manifest changed')
    manifest = json.loads(raw)
    expected = manifest['files']
    if len(expected) != 948 or sum(name.startswith('engine/') for name in expected) != 925:
        raise RuntimeError('combined manifest shape differs')
    observed = {}
    for path in sorted(CANDIDATE.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('unexpected candidate symlink')
        if path.is_file():
            observed[str(path.relative_to(CANDIDATE))] = digest(path.read_bytes())
    if observed != expected:
        raise RuntimeError('combined source bytes differ')
    return observed


def dependencies(path: Path) -> list[Path]:
    text = path.read_text().replace('\\\n', ' ')
    _, separator, values = text.partition(':')
    if not separator:
        raise RuntimeError('invalid compiler dependency file')
    result = sorted({Path(value).resolve(strict=True) for value in shlex.split(values)}, key=str)
    if not result or len(result) > 2000:
        raise RuntimeError('unexpected dependency closure size')
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--out', type=Path)
    arguments = parser.parse_args()
    if not arguments.execute:
        print(json.dumps({'state': 'PLAN_ONLY', 'candidate_manifest': MANIFEST_SHA,
                          'service_started': False, 'Android_execution': False}))
        return 0
    if os.geteuid() == 0:
        raise RuntimeError('the host build must run as the existing unprivileged operator')
    out = arguments.out
    if out != EXACT_OUT:
        raise RuntimeError('fresh task-owned build output required')
    if out.exists() or out.is_symlink():
        raise RuntimeError('build output already claimed; no automatic retry')
    source = Path(__file__).resolve().parent
    if source != EXACT_SOURCE:
        raise RuntimeError('exact fresh fixture source03 required')
    source_before = inventory()
    if pin(COMPILER)['sha256'] != COMPILER_SHA:
        raise RuntimeError('observed host compiler changed')
    own_sources = [source / name for name in ('client_control.cc', 'bionic_branch_view.cc', 'audit_worker_binary.py', 'build_fixture.py')]
    own_before = {str(path): pin(path) for path in own_sources}
    out.mkdir(mode=0o700)
    report = {'schema': 1, 'scope': 'actual combined candidate host factory and client ELF build only',
              'candidate_manifest_sha256': MANIFEST_SHA, 'candidate_files': 948, 'engine_files': 925,
              'actual_source_receipt_sha256': SOURCE_RECEIPT_SHA, 'matched_gate_sha256': MATCHED_GATE_SHA,
              'prior_build02_receipt_sha256': 'fd4a8d8a3b4b037bdf9ee72992cda69544ce8c94ea44e46696d028c0ad041142',
              'failure_only_self_namespace_diagnostic': True,
              'service_started': False, 'Android_execution': False, 'production_ready': False,
              'success': False, 'commands': [], 'started_monotonic': time.monotonic(),
              'input_source_pins': own_before, 'compiler': pin(COMPILER)}

    def command(name: str, argv: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
        started = time.monotonic()
        run = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             timeout=timeout, check=False, env={**os.environ, 'LC_ALL': 'C'})
        stdout, stderr = run.stdout, run.stderr
        (out / (name + '.stdout')).write_bytes(stdout)
        (out / (name + '.stderr')).write_bytes(stderr)
        report['commands'].append({'name': name, 'argv': argv, 'returncode': run.returncode,
                                   'seconds': time.monotonic() - started,
                                   'stdout_sha256': digest(stdout), 'stderr_sha256': digest(stderr),
                                   'stdout_bytes': len(stdout), 'stderr_bytes': len(stderr)})
        if run.returncode:
            raise RuntimeError(name + ' failed with ' + str(run.returncode))
        return run

    try:
        engine = CANDIDATE / 'engine'
        common = [str(COMPILER), '-std=gnu++20', '-O1', '-g', '-DNDEBUG', '-UDEBUG',
                  '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-fno-rtti',
                  '-ffunction-sections', '-fdata-sections', '-fno-omit-frame-pointer',
                  '-I', str(engine / 'kernel_api/include'), '-I', str(engine / 'kernel_api')]
        client_flags = [*common, '-DANDROID', '-DNATIVE_BRIDGE_GUEST_ARCH_ARM64',
                        '-DBERBERIS_GUEST_LP64=1', '-DBERBERIS_PROCMAPS_RAW_METADATA_OWNER=1', '-pthread']
        for component in ('base', 'guest_state', 'guest_state/arm64', 'guest_os_primitives',
                          'guest_os_primitives/arm64', 'runtime_primitives', 'runtime_primitives/arm64',
                          'runtime_primitives/host_x86_64', 'instrument', 'assembler', 'runtime',
                          'guest_abi', 'guest_abi/arm64', 'intrinsics', 'intrinsics/x86_64',
                          'guest_loader', 'code_gen_lib', 'native_bridge_support'):
            client_flags += ['-I', str(engine / component / 'include')]
        aosp = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
        for component in ('system/libbase/include', 'system/logging/liblog/include', 'system/core/libcutils/include'):
            client_flags += ['-I', str(aosp / component)]
        wire = engine / 'kernel_api/proc_maps_factory_wire.cc'
        units = [
            ('factory-main', CANDIDATE / 'host-factory-v2/source/factory_main.cc', common),
            ('factory-context', CANDIDATE / 'host-factory-v2/source/factory_context.cc', common),
            ('factory-wire', wire, common),
            ('client', source / 'client_control.cc', client_flags),
            ('bionic-branch', source / 'bionic_branch_view.cc', common),
        ]
        for name in ('proc_maps_raw_metadata_owner', 'proc_maps_fd_owner', 'proc_maps_path', 'proc_maps_provenance'):
            units.append((name, engine / ('kernel_api/' + name + '.cc'), client_flags))
        dependencies_by_unit = {}
        for name, path, flags in units:
            dependency = out / (name + '.preflight.d')
            command(name + '-dependencies', [*flags, '-M', '-MF', str(dependency), '-MT', name + '.o', str(path)])
            dependencies_by_unit[name] = dependencies(dependency)
        input_paths = sorted({path for paths in dependencies_by_unit.values() for path in paths}, key=str)
        if len(input_paths) != 291:
            raise RuntimeError('host fixture dependency cardinality changed')
        inputs_before = {str(path): pin(path) for path in input_paths}
        save(out / 'input-closure-before.json', {'inputs': inputs_before, 'units': {k: [str(p) for p in v] for k, v in dependencies_by_unit.items()}})
        for name, path, flags in units:
            dependency = out / (name + '.actual.d')
            command(name + '-compile', [*flags, '-MD', '-MF', str(dependency), '-c', str(path), '-o', str(out / (name + '.o'))])
            if dependencies(dependency) != dependencies_by_unit[name]:
                raise RuntimeError('actual dependency closure changed: ' + name)
        factory = out / 'factory-v2-host'
        client = out / 'factory-client-host'
        linker = [str(COMPILER), '-Wl,--gc-sections', '-Wl,-z,relro', '-Wl,-z,now', '-Wl,-z,noexecstack', '-pthread']
        command('factory-link', [*linker, *[str(out / (name + '.o')) for name in ('factory-main', 'factory-context', 'factory-wire')], '-o', str(factory)])
        client_objects = ['client', 'bionic-branch', 'factory-wire', 'proc_maps_raw_metadata_owner', 'proc_maps_fd_owner', 'proc_maps_path', 'proc_maps_provenance']
        command('client-link', [*linker, *[str(out / (name + '.o')) for name in client_objects], '-o', str(client)])
        command('fixed-worker-closure', [sys.executable, '-I', str(source / 'audit_worker_binary.py'), str(client), '--objdump', '/usr/bin/objdump', '--output', str(out / 'worker-audit.json')])
        audit = json.loads((out / 'worker-audit.json').read_text())
        if not audit.get('qualified_worker_closure'):
            raise RuntimeError('actual host worker closure failed')
        inputs_after = {str(path): pin(path) for path in input_paths}
        report['input_count'] = len(inputs_before)
        report['actual_MD_equals_preflight'] = True
        report['inputs_unchanged'] = inputs_before == inputs_after
        report['candidate_source_unchanged'] = source_before == inventory()
        report['fixture_sources_unchanged'] = own_before == {str(path): pin(path) for path in own_sources}
        save(out / 'input-closure-after.json', {'inputs': inputs_after})
        if not all(report[key] for key in ('inputs_unchanged', 'candidate_source_unchanged', 'fixture_sources_unchanged')):
            raise RuntimeError('build input changed')
        report['artifacts'] = {'factory': pin(factory), 'client': pin(client)}
        report['worker_audit_sha256'] = digest((out / 'worker-audit.json').read_bytes())
        report['worker_audit_pass'] = True
        report['success'] = True
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        report['seconds'] = time.monotonic() - report['started_monotonic']
        save(out / 'build-result.json', report)
        print(json.dumps({'success': report['success'], 'report': str(out / 'build-result.json'),
                          'sha256': digest((out / 'build-result.json').read_bytes()),
                          'error': report.get('error'), 'service_started': False, 'Android_execution': False}))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
