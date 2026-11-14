"""Portable policy controls with entirely synthetic metadata and artifacts.

The actual composition function bodies are extracted verbatim from the reviewed
stage source. Fixed pins below model its reader interface; no fixture proves
real filesystem bytes, build qualification, deployment or runtime acceptance.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / 'source' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


model = load('stage_sensor')
audio = load('stage_audio_composition')
entry = load('initial_inputs')
model.audio = audio
model.EXTENSION_CONTENTS = {'transaction-runner.py': b'# synthetic reviewed runner\n',
                            'qualify_final.py': b'# synthetic reviewed qualifier\n'}


def pin(path, *, size=10, sha=None):
    return {'path': str(path), 'bytes': size,
            'sha256': sha or hashlib.sha256(str(path).encode()).hexdigest(),
            'identity': [1, 2, 0o100600, 0, 0, 1, size, 100, 100], 'xattrs': {}}


class FixtureIO:
    class Refusal(RuntimeError):
        pass

    def __init__(self):
        self.files = {}

    @classmethod
    def need(cls, condition, message):
        if not condition:
            raise cls.Refusal(message)

    @staticmethod
    def encode(value):
        return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()

    parse = staticmethod(json.loads)

    @staticmethod
    def short(row):
        return {key: row[key] for key in ('path', 'bytes', 'sha256')}

    @staticmethod
    def matches(actual, expected, *, full=False):
        keys = ('path', 'bytes', 'sha256', 'identity', 'xattrs') if full else ('path', 'bytes', 'sha256')
        return all(key not in expected or actual.get(key) == expected[key] for key in keys)

    def add(self, path, value, *, sha=None, size=None):
        raw = value if type(value) is bytes else self.encode(value)
        record = pin(path, size=len(raw) if size is None else size,
                     sha=sha or hashlib.sha256(raw).hexdigest())
        self.files[str(path)] = (record, raw)
        return copy.deepcopy(record)

    def pinned(self, expected, *, contents=False, single=False):
        row, raw = self.files[expected['path']]
        self.need(self.matches(row, expected, full='identity' in expected), 'CHANGED_SYNTHETIC_PIN')
        return copy.deepcopy(row), raw if contents else None

    def held_read(self, path, *, absent=False, single=False):
        if str(path) in self.files:
            return copy.deepcopy(self.files[str(path)][0]), None
        self.need(absent, 'SYNTHETIC_FILE_MISSING')
        return {'path': str(path), 'absent': True}, None


def fixture():
    io = FixtureIO()
    payloads = []
    operations = []
    overrides = []
    integration = pin(model.DEPLOY / 'framework-integration.json',
        sha='0832861edd6611ae42d5add4367cdc210ce03f0ccd149264151e66a0d3b19385')
    guests = [model.GUEST[role] for role in ('engine', 'bridge_profile', 'sensor')]
    guests += ['/system/framework/services.jar']
    guests += ['/system/etc/synthetic-file-%d' % i for i in range(20)]
    for guest in guests:
        target = str(model.PREFIX / guest.lstrip('/'))
        relative = 'payload/' + target.lstrip('/')
        digest = hashlib.sha256(guest.encode()).hexdigest()
        size = 10
        if guest == model.GUEST['sensor']:
            digest = '8db6580b97dea3e1e8e1109e29953bd46e4300f113d1a1d738b1dbc7a8057b20'
            size = 482440
        if guest == '/system/framework/services.jar':
            digest = model.SERVICES_SHA
        row = {'install_target': target, 'bytes': size, 'sha256': digest,
            'relative_path': relative, 'path': str(model.DEPLOY / relative),
            'role': 'android_file_override', 'source': {'fixture_source': guest},
            'mode': 0o444, 'install_mode': 0o644, 'install_owner': {'uid': 0, 'gid': 0}}
        operation = {'target': target, 'sha256': digest, 'expected_current': {'absent': True},
            'staged_relative_path': relative, 'uid': 0, 'gid': 0, 'mode': 0o644}
        override = {'guest_target': guest, 'candidate_source': target, 'operation': 'install_staged',
            'staged_relative_path': relative}
        if guest in (model.GUEST['engine'], model.GUEST['bridge_profile']):
            row['must_replace_and_reseal_before_apply'] = True
            row['placeholder_for'] = 'synthetic future native artifact'
        if guest == model.GUEST['sensor']:
            row['framework_integration'] = copy.deepcopy(integration)
            override['framework_integration'] = copy.deepcopy(integration)
            row['acceptance_context'] = 'Synthetic staged sensor; runtime pending.'
        payloads.append(row)
        operations.append(operation)
        overrides.append(override)
        io.add(model.DEPLOY / relative, b'synthetic payload', sha=digest, size=size)
    for target in audio.COHORT_TARGETS:
        relative = 'payload/' + target.lstrip('/')
        record = io.add(model.DEPLOY / relative, b'synthetic original host executable')
        payloads.append({'install_target': target, 'bytes': record['bytes'], 'sha256': record['sha256'],
            'relative_path': relative, 'path': str(model.DEPLOY / relative),
            'role': 'matched_host_runtime', 'source': {'fixture_source': target}})
        operations.append({'target': target, 'sha256': record['sha256'],
            'expected_current': {'synthetic_current_host': target}, 'staged_relative_path': relative})
    for i in range(23):
        overrides.append({'guest_target': '/system/etc/synthetic-base-%d' % i,
            'candidate_source': '/synthetic/base-%d' % i, 'current_source': '/synthetic/base-%d' % i})
    directories = [{'source': '/synthetic/dir-%d' % i, 'target': '/system/synthetic-dir-%d' % i} for i in range(4)]
    tooling = {'candidate_sources': [pin(model.DEPLOY / 'transaction-runner.py', sha=model.RUNNER_SHA),
        pin(model.FINAL / 'qualification/qualify_final.py', sha=model.QUALIFIER_SHA)]
        + [pin('/synthetic/unchanged-tool-%d' % i) for i in range(4)]}
    manifest = {'payload': payloads, 'android_file_overrides': overrides,
        'android_runtime_directories': directories, 'ready_for_apply': False, 'stage_only': True,
        'transaction_runner': pin(model.DEPLOY / 'transaction-runner.py', sha=model.RUNNER_SHA),
        'framework_integration': copy.deepcopy(integration), 'qualification_tooling': tooling,
        'cell_source': pin('/synthetic/current-cell'), 'lifecycle_contract': {'synthetic': True},
        'host_build_input': pin(model.DEPLOY / 'host-build-input.json'),
        'candidate_cell': pin(model.DEPLOY / 'cell.candidate.json'),
        'qualification_config': pin(model.DEPLOY / 'qualification-config.json'),
        'transaction_plan': pin(model.DEPLOY / 'transaction-plan.json')}
    transaction = {'install_operations': operations, 'framework_integration': copy.deepcopy(integration),
        'apply_authorized_by_this_artifact': False, 'cell_operation': {'sha256': 'a' * 64}}
    camera_inputs = {key: pin('/synthetic/camera/' + key)
                     for key in ('probe', 'consumer_manifest', 'service_manifest', 'service_unit')}
    camera_inputs['host_cli'] = pin('/usr/bin/droidloomctl')
    qplan = {'ready': False, 'maintenance': {}, 'references': {}, 'remaining_inputs': ['synthetic pending'],
        'component_inputs': {'framework': {}, 'native': {}, 'camera': camera_inputs},
        'component_runners': {'camera': {'program': pin('/synthetic/original-camera'),
            'required': [{'path': ['synthetic-%d' % i], 'equals': True} for i in range(19)]}}}
    config = {name: {'program': str(model.FINAL / 'qualification/qualify_final.py'),
                    'sha256': model.QUALIFIER_SHA} for name in ('maintenance_gate', 'post_start_qualification')}
    cell = {'android_file_overrides': [{'source': row['candidate_source'], 'target': row['guest_target']}
                                     for row in overrides], 'android_runtime_directories': directories,
            'unrelated_synthetic_setting': 'must remain unchanged'}
    values = {'deployment/manifest.json': manifest, 'deployment/transaction-plan.json': transaction,
        'deployment/cell.candidate.json': cell, 'deployment/qualification-config.json': config,
        'qualification/plan.json': qplan, 'deployment/verification.json': {'synthetic': True},
        'camera/runtime-entry.json': {'argv': ['/usr/bin/python3', '/synthetic/original-camera']},
        'deployment/host-build-input.json': {'synthetic': True},
        'deployment/transaction-runner.py': b'# synthetic original runner\n',
        'qualification/qualify_final.py': b'# synthetic original qualifier\n'}
    pins = dict(model.BASE_PINS, **audio.BASE_PINS)
    for relative, value in values.items():
        io.add(model.FINAL / relative, value, sha=pins[relative])
    metadata = ['TRANSACTION.txt', 'cell.candidate.json', 'framework-integration-verification.json',
        'framework-integration.json', 'host-build-input.json', 'host-current-targets.json',
        'legacy-config-retirement-candidates.json', 'manifest.json', 'native-init-integration.json',
        'qualification-config.json', 'qualification-config.template.json', 'reference-inventory.json',
        'transaction-plan.json', 'transaction-runner.py', 'verification.json']
    for name in metadata:
        if str(model.DEPLOY / name) not in io.files:
            io.add(model.DEPLOY / name, {'synthetic_metadata': name},
                   sha=integration['sha256'] if name == 'framework-integration.json' else None)
    relative_rows = metadata + [row['relative_path'] for row in payloads]
    sums = ''.join(io.files[str(model.DEPLOY / name)][0]['sha256'] + '  ' + name + '\n' for name in relative_rows)
    io.add(model.DEPLOY / 'SHA256SUMS', sums.encode(), sha=model.BASE_PINS['deployment/SHA256SUMS'])
    base = model.baseline(io, SimpleNamespace(observed={}))
    for relative in audio.BASE_PINS:
        row, raw = io.pinned({'path': str(model.FINAL / relative)}, contents=True)
        base['records'][relative] = row
        base['raw'][relative] = raw
        base['values'][relative] = io.parse(raw) if relative.endswith('.json') else None
    framework = {'candidate': pin('/synthetic/new-sensor', size=482440,
        sha='8db6580b97dea3e1e8e1109e29953bd46e4300f113d1a1d738b1dbc7a8057b20'), 'gate': {},
        **{name: pin('/synthetic/framework/' + name) for name in ('outer', 'comparison', 'reconciliation', 'original_failed_terminal')}}
    camera = {name: pin('/synthetic/camera/' + name) for name in ('program', 'manifest', 'host_controls')}
    camera['sources'] = []
    native = {name: pin('/synthetic/native/' + name) for name in ('contract', 'assembly', 'offline', 'profile_generation')}
    native['sources'] = {role: pin('/synthetic/native/' + role) for role in model.GUEST if role != 'sensor'}
    native['contract_value'] = {'files': {role: {'qualified_source': ref} for role, ref in native['sources'].items()}}
    sources = {target: pin('/synthetic/audio' + target) for target in audio.ALL_TARGETS}
    evidence = {name: pin('/synthetic/audio/' + name) for name in ('host_build', 'host_mount', 'deployment_extension_controls')}
    audio_info = {'sources': sources, 'packet_ref': pin('/synthetic/audio/packet'), 'gate': {},
        'evidence': evidence, 'evidence_pins': evidence,
        'packet': {'files': sources, 'host_source_base_commit': '5957addac279b11110c6cdd406e32ef871a7c511',
            'host_source_tree': 'a' * 40, 'host_source_manifest': pin('/synthetic/audio/source'), 'observed_unix': 0}}
    return io, base, framework, camera, native, audio_info


class ExistingSensor(unittest.TestCase):
    def test_baseline_accepts_existing_sensor_without_requiring_absence(self):
        io, base, *_ = fixture()
        self.assertEqual(len(base['sums']), 43)
        self.assertEqual(len(base['values']['deployment/manifest.json']['payload']), 28)
        self.assertNotIn(model.payload_relative('sensor'), model.stage_allowlist())
        self.assertEqual(len(model.stage_allowlist()), 27)

    def test_sensor_payload_digest_drift_rejected(self):
        io, *_ = fixture()
        io.files[str(model.FINAL / model.payload_relative('sensor'))][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(io.Refusal, 'CHANGED_SYNTHETIC_PIN'):
            model.baseline(io, SimpleNamespace(observed={}))

    def test_sensor_override_or_integration_drift_rejected(self):
        for change in ('override', 'integration'):
            with self.subTest(change=change):
                io, *_ = fixture()
                path = str(model.DEPLOY / 'manifest.json')
                row, raw = io.files[path]
                value = io.parse(raw)
                if change == 'override':
                    next(r for r in value['android_file_overrides'] if r['guest_target'] == model.GUEST['sensor'])['candidate_source'] = '/synthetic/wrong'
                else:
                    value['framework_integration']['sha256'] = '0' * 64
                io.files[path] = (row, io.encode(value))
                with self.assertRaises(io.Refusal):
                    model.baseline(io, SimpleNamespace(observed={}))

    def test_native_audio_composition_preserves_sensor_and_its_two_metadata_rows(self):
        io, base, framework, camera, native, audio_info = fixture()
        before = copy.deepcopy(base['values']['deployment/manifest.json'])
        built = model.build(io, base, {}, framework, camera, native, {}, model.FINAL / 'qualification/synthetic')
        self.assertEqual(len(built['final_sums']), 45)
        built = audio.compose(io, model, base, built, audio_info)
        final = built['manifest']
        target = str(model.PREFIX / model.GUEST['sensor'].lstrip('/'))
        self.assertEqual(next(r for r in final['payload'] if r['install_target'] == target),
                         next(r for r in before['payload'] if r['install_target'] == target))
        self.assertEqual(next(r for r in final['android_file_overrides'] if r['guest_target'] == model.GUEST['sensor']),
                         next(r for r in before['android_file_overrides'] if r['guest_target'] == model.GUEST['sensor']))
        sums = dict((name, digest) for digest, name in built['final_sums'])
        old_sums = dict((name, digest) for digest, name in base['sums'])
        for name in ('framework-integration.json', 'framework-integration-verification.json'):
            self.assertEqual(sums[name], old_sums[name])
        self.assertEqual((len(final['payload']), len(final['android_file_overrides']), len(sums)), (38, 50, 53))
        self.assertEqual(set(built['metadata']) | set(built['payload_sources']), model.stage_allowlist())
        self.assertFalse(built['source_qualification']['runtime_qualified'])
        self.assertFalse(built['transaction']['apply_authorized_by_this_artifact'])

    def test_initial_inputs_rejects_the_old_27_46_40_runner_shape(self):
        checks = {'checksums_verified': 43, 'install_count': 28, 'file_overrides': 47, 'runtime_directories': 4}
        witness = SimpleNamespace(read=lambda *a, **k: ({}, {}))
        entry.source_witness = lambda *a: witness
        entry.runner = lambda *a: SimpleNamespace(validate=lambda *a: dict(checks))
        fake_model = SimpleNamespace(KNOWN_SHA='a' * 64,
            baseline=lambda *a: {'values': {'deployment/manifest.json': {}, 'deployment/transaction-plan.json': {}}},
            audio=SimpleNamespace(baseline=lambda *a: None), framework=lambda *a: {}, camera=lambda *a: {})
        entry.initial_inputs(FixtureIO(), fake_model, {}, {})
        checks.update(checksums_verified=40, install_count=27, file_overrides=46)
        with self.assertRaisesRegex(FixtureIO.Refusal, 'ACTUAL_OLD_RUNNER_VALIDATION'):
            entry.initial_inputs(FixtureIO(), fake_model, {}, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
