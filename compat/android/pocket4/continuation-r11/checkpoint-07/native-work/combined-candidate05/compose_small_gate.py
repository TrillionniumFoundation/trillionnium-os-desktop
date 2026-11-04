#!/usr/bin/env python3
"""Create candidate05 and bounded actual source controls. No full build/service."""
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import resource
import stat
import subprocess
import sys

OWNER = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01')
ROOT = OWNER / 'overlay-reconstruction-09'
BASE = ROOT / 'candidate-04'
BASE_MANIFEST = ROOT / 'candidate-04-source-manifest.json'
BASE_SHA = '00a19fef1ca8e86a3da18eecfb16eedb41e9de55e2934b96987845fa8b749fbd'
BASE_GATE = ROOT / 'combined-adapter-controls-06/report.json'
BASE_GATE_SHA = '5309622bd9ab29908f820e28eaaa7266d9a2beac8dbf4af9e1b23234720761df'
COMPONENT = OWNER / 'factory-v2-review-03'
COMPONENT_SHA = 'd087c114ecbeb76086abc2d91736d5f9fcbfa9e093cdff32bb63771f434cc202'
BUNDLE_SHA = 'fed272af40ecb286ec152254de55c7c6a6d1e722fd90028bd696037ca5c4e174'
CANDIDATE = ROOT / 'candidate-05'
MANIFEST = ROOT / 'candidate-05-source-manifest.json'
OUT = ROOT / 'combined-ancillary-controls-07'
AOSP = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
GXX = Path('/usr/bin/x86_64-linux-gnu-g++-15')
GXX_SHA = 'e6718f7e0c7d057c3ff77b550c603da9bc4030e3ede3c053705acce1293dbe4d'
REFERENCE = Path('/home/alex/work/pocket4-owned-fd-capability-r20-apk-01/fd-owner-probe-r20-source/build-attempt-1/build-result.json')
REFERENCE_SHA = '09a8a5ab25c897405b70bebdeb6c75c98d94ec9124365fdb51956b35df96db43'
ADAPTER_SHA = '4bd5a423b03960aa99aac52da8a0e802381dcb777c7f11e7645bd882ad72649a'
REPLACEMENTS = {
    'host-factory-v2/source/factory_main.cc': ('source/factory_main.cc',
        '19abcf92feca3bd1ef46306e15fd8110c8e238c443a536625ba308f52fda45fb',
        '18d8134ed6c2077088104d9b5dc22ccfe1c93f73a87ee880595a9eb89821e2b9'),
    'engine/kernel_api/proc_maps_provenance.cc': ('engine-delta/proc_maps_provenance.cc',
        'bc68ad924a1c3a31d2a8b97099130ad796f52c6d7c9bca5b68267de995e0d62f',
        'f4e6685f5b689d3b408dc6aa7723e36b2174e6e2545e743fbb5c5896f6142137'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(value, why):
    if not value:
        raise RuntimeError(why)


def relative(name):
    path = PurePosixPath(name)
    require(path.parts and str(path) == name and not path.is_absolute() and
            all(piece not in ('.', '..', '.git') for piece in path.parts), 'unsafe relative path')
    return path


def no_alias(path):
    for item in [path, *path.parents]:
        if item.exists() or item.is_symlink():
            require(stat.S_ISDIR(item.lstat().st_mode), 'aliased directory: ' + str(item))


def inventory(base):
    files = {}
    for directory, dirs, names in os.walk(base, followlinks=False):
        for name in dirs:
            require(stat.S_ISDIR((Path(directory) / name).lstat().st_mode), 'source directory alias')
        for name in names:
            path = Path(directory) / name
            require(stat.S_ISREG(path.lstat().st_mode), 'nonregular source')
            files[path.relative_to(base).as_posix()] = file_sha(path)
    return dict(sorted(files.items()))


def put(path, raw, mode=0o444):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def run_gate(report, name, argv, timeout=90):
    args = list(map(str, argv))
    result = subprocess.run(args, capture_output=True, timeout=timeout,
                            env={**os.environ, 'LANG': 'C', 'LC_ALL': 'C'})
    put(OUT / (name + '.stdout'), result.stdout)
    put(OUT / (name + '.stderr'), result.stderr)
    row = {'name': name, 'argv': args, 'returncode': result.returncode,
           'stdout_sha256': sha(result.stdout), 'stderr_sha256': sha(result.stderr),
           'stderr_excerpt': result.stderr.decode(errors='replace')[-2500:]}
    report['commands'].append(row)
    require(result.returncode == 0, 'command failed: ' + name)
    return result


def main():
    if sys.argv[1:] != ['--compose-and-check']:
        print(json.dumps({'state': 'PLAN_ONLY', 'candidate': str(CANDIDATE),
                          'out': str(OUT), 'component': str(COMPONENT),
                          'factory_service_started': False, 'fullbuild_started': False,
                          'Android_actions': 0, 'production_ready': False}))
        return 0
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'owned nonroot operator required')
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    bundle_raw = sys.stdin.buffer.read()
    require(sha(bundle_raw) == BUNDLE_SHA, 'bundle changed')
    packet = json.loads(bundle_raw)
    component_raw = packet['component_pins_text'].encode()
    require(sha(component_raw) == COMPONENT_SHA, 'component pins changed')
    pins = json.loads(component_raw)
    rows = packet['component_files']
    require(len(rows) == 30 and set(rows) == set(pins['files']), 'component inventory changed')
    for name, row in rows.items():
        relative(name)
        raw = row['text'].encode()
        require(len(raw) == row['bytes'] and sha(raw) == row['sha256'] and
                pins['files'][name] == {'bytes': len(raw), 'sha256': sha(raw)}, 'component source changed')
    base_raw = BASE_MANIFEST.read_bytes()
    require(sha(base_raw) == BASE_SHA and file_sha(BASE_GATE) == BASE_GATE_SHA, 'candidate04 proof changed')
    prior_gate = json.loads(BASE_GATE.read_bytes())
    require(prior_gate['all_compiles_pass'] is True and prior_gate['source_unchanged'] is True and
            prior_gate['actual_host_adapter_checks'] == 8, 'candidate04 gate was not successful')
    before = json.loads(base_raw)
    require(len(before['files']) == 948 and sum(name.startswith('engine/') for name in before['files']) == 925,
            'base counts differ')
    no_alias(BASE)
    require(inventory(BASE) == before['files'], 'base missing, extra or changed file')
    for name, (_, old, new) in REPLACEMENTS.items():
        require(before['files'][name] == old, 'unexpected replacement preimage')
    require(file_sha(GXX) == GXX_SHA and file_sha(REFERENCE) == REFERENCE_SHA, 'compiler reference changed')
    reference = json.loads(REFERENCE.read_bytes())
    original_command = next(row['argv'] for row in reference['commands'] if row['name'] == 'compile-native')
    clang = Path(original_command[0])
    sysroot = Path(next(value.split('=', 1)[1] for value in original_command if value.startswith('--sysroot=')))
    clang_pin = reference['tools_sha256'][str(clang).replace('clang++', 'clang')]
    require(file_sha(clang) == clang_pin, 'actual Android compiler changed')
    for path in (COMPONENT, CANDIDATE, OUT):
        no_alias(path)
        require(not path.exists(), 'new output already exists; reconcile exact request')
    for path in (MANIFEST, ROOT / 'candidate04-to-candidate05.patch', ROOT / 'candidate-05-report.json'):
        require(not path.exists() and not path.is_symlink(), 'new receipt already exists')
    COMPONENT.mkdir(mode=0o700)
    for name, row in rows.items():
        put(COMPONENT / name, row['text'].encode())
    put(COMPONENT / 'SOURCE_PINS.json', component_raw)
    CANDIDATE.mkdir(mode=0o700)
    replacements = {name: rows[part]['text'].encode() for name, (part, _, _) in REPLACEMENTS.items()}
    replacements['references/v2-component-SOURCE_PINS.json'] = component_raw
    ancestry = dict(before.get('ancestry', {}))
    for name, old in before['files'].items():
        relative(name)
        raw = replacements.get(name)
        if raw is None:
            raw = (BASE / name).read_bytes()
            require(sha(raw) == old, 'base changed while copying')
        else:
            ancestry.setdefault(name, []).append({'source': 'SCM_PIDFD ownership revision2 ' + COMPONENT_SHA,
                                                  'prior_sha256': old, 'sha256': sha(raw)})
        put(CANDIDATE / name, raw)
    current = inventory(CANDIDATE)
    require(set(current) == set(before['files']) and len(current) == 948, 'candidate path set changed')
    changed = {name for name in current if current[name] != before['files'][name]}
    require(changed == set(replacements), 'undeclared candidate change')
    for name, (_, _, expected) in REPLACEMENTS.items():
        require(current[name] == expected, 'replacement digest mismatch')
    signal_pins = json.loads((CANDIDATE / 'references/signal-mask-r1-pins.json').read_bytes())
    require(file_sha(CANDIDATE / 'references/signal-mask-r1-pins.json') ==
            '6a24ef53595e9d8da458a626effbfca4280a5de18c90ad1d5dd036ad3e936bf2', 'signal pins changed')
    for row in signal_pins['changes']:
        require(current['engine/' + row['path']] == row['sha256'], 'signal fix was not preserved')
    manifest_raw = encoded({'schema': 1, 'files': current, 'ancestry': ancestry})
    put(MANIFEST, manifest_raw)
    patch = ''
    for name in sorted(changed):
        old = (BASE / name).read_bytes()
        new = (CANDIDATE / name).read_bytes()
        patch += ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                            fromfile='a/' + name, tofile='b/' + name))
    put(ROOT / 'candidate04-to-candidate05.patch', patch.encode())
    OUT.mkdir(mode=0o700)
    adapter = packet['actual_adapter']['text'].encode()
    require(sha(adapter) == ADAPTER_SHA, 'actual adapter control changed')
    put(OUT / 'actual_adapter.cc', adapter)
    summary = {'schema': 1, 'state': 'CANDIDATE05_FROZEN_GATES_PENDING', 'source_manifest_sha256': sha(manifest_raw),
               'base_manifest_sha256': BASE_SHA, 'component_pins_sha256': COMPONENT_SHA,
               'source_files': 948, 'engine_files': 925, 'production_changed_files': sorted(REPLACEMENTS),
               'reference_changed_files': ['references/v2-component-SOURCE_PINS.json'],
               'six_signal_outputs_unchanged': True, 'binary_inputs_never_text_decoded': True,
               'patch_sha256': sha(patch.encode()), 'full_engine_built': False, 'full_ART_built': False,
               'factory_service_started': False, 'Android_executed': False, 'default_feature_enabled': False,
               'production_ready': False}
    put(ROOT / 'candidate-05-report.json', encoded(summary))
    print(json.dumps({'stage': 'CANDIDATE05_FROZEN', 'source_manifest_sha256': sha(manifest_raw),
                      'report_sha256': file_sha(ROOT / 'candidate-05-report.json')}), flush=True)
    report = {**summary, 'state': 'RUNNING', 'commands': [], 'compiler_sha256': clang_pin,
              'host_compiler_sha256': GXX_SHA, 'inherited_candidate04_gate_sha256': BASE_GATE_SHA,
              'inherited_controls_scope': 'Unchanged source proof only; changed provenance recompiled in both modes; actual adapter rerun.',
              'source_unchanged': False, 'actual_listener_inheritance_fixed': False,
              'actual_ancillary_cases': 0, 'actual_host_adapter_checks': 0}
    source = CANDIDATE / 'engine'
    includes = ['kernel_api/include', 'kernel_api', 'base/include', 'guest_state/include',
                'guest_state/arm64/include', 'guest_os_primitives/include', 'guest_os_primitives/arm64/include',
                'runtime_primitives/include', 'runtime_primitives/arm64/include', 'runtime_primitives/host_x86_64/include',
                'instrument/include', 'assembler/include', 'runtime/include', 'guest_abi/include',
                'guest_abi/arm64/include', 'intrinsics/include', 'intrinsics/x86_64/include',
                'guest_loader/include', 'code_gen_lib/include', 'native_bridge_support/include']
    try:
        for feature in (0, 1):
            command = [clang, '-target', 'x86_64-linux-android37', '--sysroot=' + str(sysroot),
                       '-std=gnu++20', '-nostdinc++', '-isystem', sysroot / 'usr/include/c++/v1',
                       '-I', sysroot / 'usr/include/x86_64-linux-android', '-DANDROID', '-DNDEBUG', '-UDEBUG',
                       '-DNATIVE_BRIDGE_GUEST_ARCH_ARM64', '-DBERBERIS_GUEST_LP64=1',
                       '-DBERBERIS_PROCMAPS_RAW_METADATA_OWNER=' + str(feature),
                       '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror']
            for directory in includes:
                command += ['-I', source / directory]
            for directory in ('system/libbase/include', 'system/logging/liblog/include', 'system/core/libcutils/include'):
                command += ['-I', AOSP / directory]
            run_gate(report, 'android-provenance-feature-' + str(feature), command +
                     ['-c', source / 'kernel_api/proc_maps_provenance.cc', '-o', OUT / ('provenance-' + str(feature) + '.o')])
        host = [GXX, '-DANDROID', '-DNDEBUG', '-UDEBUG', '-std=gnu++20', '-O1', '-Wall', '-Wextra', '-Werror',
                '-fno-exceptions', '-fno-rtti', '-DNATIVE_BRIDGE_GUEST_ARCH_ARM64', '-DBERBERIS_GUEST_LP64=1',
                '-DBERBERIS_PROCMAPS_RAW_METADATA_OWNER=1', '-ffunction-sections', '-fdata-sections',
                '-Wl,--gc-sections', '-pthread']
        for directory in includes:
            host += ['-I', source / directory]
        for directory in ('system/libbase/include', 'system/logging/liblog/include', 'system/core/libcutils/include'):
            host += ['-I', AOSP / directory]
        core = [source / 'kernel_api' / (name + '.cc') for name in
                ('proc_maps_raw_metadata_owner', 'proc_maps_fd_owner', 'proc_maps_path', 'proc_maps_provenance',
                 'proc_maps_factory_wire')]
        run_gate(report, 'compile-actual-adapter', host + [OUT / 'actual_adapter.cc',
                 source / 'kernel_api/arm64/syscall_emulation_arch.cc'] + core + ['-o', OUT / 'actual-adapter'])
        actual = run_gate(report, 'run-actual-adapter', [OUT / 'actual-adapter'], 30)
        parsed = [json.loads(line) for line in actual.stdout.splitlines()]
        require(parsed[-1]['checks'] == 8 and parsed[-1]['failed'] == 0, 'actual adapter gate failed')
        report['actual_host_adapter_checks'] = 8
        factory = CANDIDATE / 'host-factory-v2/source'
        basic = [GXX, '-std=gnu++20', '-O1', '-Wall', '-Wextra', '-Werror',
                 '-I', source / 'kernel_api/include', '-I', factory]
        context_and_wire = [factory / 'factory_context.cc', source / 'kernel_api/proc_maps_factory_wire.cc']
        run_gate(report, 'compile-ancillary-stages', basic + ['-ffunction-sections', '-fdata-sections',
                 '-DFACTORY_SOURCE="' + str(factory / 'factory_main.cc') + '"',
                 '-DPROVENANCE_SOURCE="' + str(source / 'kernel_api/proc_maps_provenance.cc') + '"',
                 COMPONENT / 'tests/ancillary_controls.cc'] + context_and_wire +
                 ['-Wl,--gc-sections', '-o', OUT / 'ancillary-stages'])
        actual = run_gate(report, 'run-ancillary-stages', [OUT / 'ancillary-stages'], 15)
        parsed = [json.loads(line) for line in actual.stdout.splitlines()]
        require(parsed[-1] == {'cases': 34, 'all_owned_descriptors_closed': True, 'all_pass': True},
                'actual ancillary ownership gate failed')
        report['actual_ancillary_cases'] = 34
        run_gate(report, 'compile-listener-inheritance', basic +
                 ['-DFACTORY_SOURCE="' + str(factory / 'factory_main.cc') + '"',
                  COMPONENT / 'tests/listener_inheritance_control.cc'] + context_and_wire +
                 ['-o', OUT / 'listener-inheritance'])
        actual = run_gate(report, 'run-listener-inheritance', [OUT / 'listener-inheritance'], 15)
        parsed = [json.loads(line) for line in actual.stdout.splitlines()]
        require(len(parsed) == 4 and parsed[-1]['all_control_descriptors_closed'] is True,
                'listener control incomplete')
        ordinary, added = parsed[1:3]
        require(ordinary['case'] == 'ordinary' and ordinary['receive_rc'] == 0 and
                ordinary['accepted_passpidfd'] == 0 and ordinary['fds_after_rights_destructor_delta'] == 0 and
                ordinary['expected_result_observed'] is True, 'ordinary listener control failed')
        require(added['case'] == 'passpidfd' and added['accepted_passpidfd'] == 1 and
                added['receive_rc'] == -1 and added['receive_errno'] == 71 and added['unowned_pidfds'] == 0 and
                added['fds_after_rights_destructor_delta'] == 0 and added['fd_table_restored'] is True and
                added['expected_result_observed'] is True, 'inherited pidfd was not closed/rejected')
        report['actual_listener_inheritance_fixed'] = True
        require(inventory(BASE) == before['files'] and inventory(CANDIDATE) == current, 'source changed during gate')
        require(file_sha(clang) == clang_pin and file_sha(GXX) == GXX_SHA, 'compiler changed during gate')
        for name, row in pins['files'].items():
            require(file_sha(COMPONENT / name) == row['sha256'], 'component changed during gate')
        report.update(state='MATCHED_SMALL_GATES_PASSED', source_unchanged=True, all_commands_pass=True)
    except BaseException as error:
        report.update(state='FAILED', error=repr(error), all_commands_pass=False)
    put(OUT / 'report.json', encoded(report))
    print(json.dumps({'state': report['state'], 'report': str(OUT / 'report.json'),
                      'report_sha256': file_sha(OUT / 'report.json'), 'source_manifest_sha256': sha(manifest_raw),
                      'actual_listener_inheritance_fixed': report['actual_listener_inheritance_fixed'],
                      'actual_ancillary_cases': report['actual_ancillary_cases'],
                      'actual_host_adapter_checks': report['actual_host_adapter_checks'],
                      'error': report.get('error')}), flush=True)
    return 0 if report['state'] == 'MATCHED_SMALL_GATES_PASSED' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'state': 'COMPOSITION_OR_ADMISSION_FAILED', 'error': repr(error),
                          'Main_actions': 0, 'factory_service_started': False, 'fullbuild_started': False}), flush=True)
        raise SystemExit(1)
