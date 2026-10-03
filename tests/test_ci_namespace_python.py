"""CI source/ordinary-FS regressions; never load a profile, sudo or probe userns.

The setup/cleanup model deliberately substitutes root ownership, kernel profile
inventory and parser execution. It tests refusal/order/owned-state behavior,
not AppArmor activation or hosted namespace permission. The original real G1
readonly snapshot and five-capabilities/NNP case remains a separate unchanged
test in the full discovery corpus.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import ci_namespace_python as helper
from tools import verify_ci_namespace_python as gate
try:
    from . import test_ci_source_dependency_filters as dependencies
except ImportError:
    import test_ci_source_dependency_filters as dependencies

ROOT = Path(__file__).resolve().parents[1]


class NamespaceConfigurationSourceTests(unittest.TestCase):
    def test_actual_contract_checker_cli_is_source_only(self):
        gate.validate(ROOT)
        result = subprocess.run([sys.executable, str(ROOT / 'tools/verify_ci_namespace_python.py')],
                                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            'scope': 'CI_CONFIGURATION_SOURCE_ONLY', 'hosted_qualified': False,
            'global_security_changed': False, 'production_ready': False})

    def test_closed_claims_types_bounds_and_input_inventory_refuse(self):
        texts = gate.inputs(ROOT)
        for key in ('corpus_as_host_root', 'global_AppArmor_or_sysctl_changes',
                    'namespace_or_security_fallback', 'hosted_qualified', 'G1_closed', 'production_ready'):
            for wrong in (True, 0):
                value = copy.deepcopy(gate.EXPECTED); value[key] = wrong
                with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError): gate.check(value, texts)
        value = copy.deepcopy(gate.EXPECTED); value['bounds']['old_job_timeout_minutes'] = 21
        with self.assertRaises(ValueError): gate.check(value, texts)
        value = copy.deepcopy(gate.EXPECTED); value['caller_profile_verified'] = True
        with self.assertRaises(ValueError): gate.check(value, texts)
        for key in texts:
            missing = dict(texts); del missing[key]
            with self.subTest(missing=key), self.assertRaises(ValueError): gate.check(gate.EXPECTED, missing)

    def test_profile_attachment_and_global_change_source_cannot_be_rebound(self):
        for path in gate.EXPECTED['source_sha256']:
            texts = gate.inputs(ROOT); texts[path] += '\n# additional unreviewed behavior\n'
            with self.subTest(path=path), self.assertRaises(ValueError): gate.check(gate.EXPECTED, texts)
        value = copy.deepcopy(gate.EXPECTED)
        value['source_sha256'][helper.TEMPLATE] = '0' * 64
        with self.assertRaises(ValueError): gate.check(value, gate.inputs(ROOT))

    def test_setup_checker_always_cleanup_and_original_commands_cannot_be_detached(self):
        path = '.github/workflows/ci.yml'
        variants = [('python3 tools/verify_ci_namespace_python.py', 'true'),
                    ('        if: always()', '        if: success()'),
                    ('python3 -m unittest discover -s tests -v', 'true'),
                    ('timeout-minutes: 20', 'timeout-minutes: 21'),
                    ('/usr/bin/python3.12 tools/ci_namespace_python.py cleanup', 'true')]
        for before, after in variants:
            texts = gate.inputs(ROOT); self.assertIn(before, texts[path])
            texts[path] = texts[path].replace(before, after, 1)
            with self.subTest(before=before), self.assertRaises(ValueError): gate.check(gate.EXPECTED, texts)

    def test_actual_catalog_digest_and_duplicate_fields_refuse(self):
        path = 'contracts/ci-required-contexts.v1.json'
        texts = gate.inputs(ROOT); value = json.loads(texts[path])
        value['workflows']['.github/workflows/ci.yml']['body_without_job_display_names_sha256'] = '0' * 64
        texts[path] = json.dumps(value)
        with self.assertRaises(ValueError): gate.check(gate.EXPECTED, texts)
        texts = gate.inputs(ROOT)
        texts[path] = texts[path].replace('"schema":', '"schema":"duplicate", "schema":', 1)
        with self.assertRaises(ValueError): gate.check(gate.EXPECTED, texts)

    def test_default_make_discovery_collects_this_gate_without_running_root_setup(self):
        make = (ROOT / 'Makefile').read_text()
        self.assertIn('check: validate truth test-python ', make)
        self.assertIn('test-python:\n\tpython3 -m unittest discover -s tests -v\n', make)
        script = ("import unittest\n"
                  "def leaves(s):\n"
                  " for x in s:\n"
                  "  if isinstance(x,unittest.TestSuite): yield from leaves(x)\n"
                  "  else: yield x.id()\n"
                  "print('\\n'.join(x for x in leaves(unittest.TestLoader().discover('tests')) "
                  "if x.startswith('test_ci_namespace_python.')))\n")
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        collected = set(result.stdout.splitlines())
        self.assertIn('test_ci_namespace_python.NamespaceConfigurationSourceTests.test_actual_contract_checker_cli_is_source_only', collected)
        self.assertIn('test_ci_namespace_python.OwnedCleanupModelTests.test_running_owned_interpreter_refuses_before_profile_removal', collected)
        self.assertGreaterEqual(len(collected), 20)

    def test_new_module_references_trigger_every_actual_module_reader(self):
        new = [helper.TEMPLATE, 'tools/ci_namespace_python.py', gate.CONTRACT,
               'tools/verify_ci_namespace_python.py', 'tests/test_ci_namespace_python.py']
        registry = json.loads((ROOT / 'manifests/modules.v1.json').read_text())
        module = next(item for item in registry['modules'] if item['id'] == 'hepta-browser-codec')
        for path in new:
            self.assertIn(path, module['contracts'] + module['tests'])
        readers = []
        for path in sorted((ROOT / '.github/workflows').glob('*.yml')):
            document = dependencies.workflow(path)
            closure, unused = dependencies.dependencies(ROOT, document)
            if 'tools/validate_module_documentation.py' not in closure: continue
            readers.append(path.name)
            for event in ('push', 'pull_request'):
                if event not in document['on']: continue
                for value in new:
                    with self.subTest(workflow=path.name, event=event, value=value):
                        self.assertTrue(dependencies.matches(document, event, value))
        self.assertEqual(len(readers), 9)


class FixedContextAndOrdinaryFileTests(unittest.TestCase):
    def context(self):
        return helper._context('123', '2', helper.JOBS[0], 1001, 1001, 'a' * 40, 'b' * 40)

    def test_context_refuses_path_job_numeric_bool_and_source_tuple_injection(self):
        good = ['123', '2', helper.JOBS[0], 1001, 1001, 'a' * 40, 'b' * 40]
        for index, values in [(0, ['0', '01', '../123', '1\n', str(1 << 64), True]),
                              (1, ['0', '10000', '2/../3']),
                              (2, ['rust', 'repository-contracts\n', '*', '../job']),
                              (3, [0, True, -1]), (4, [True, -1]),
                              (5, ['A' * 40, 'a' * 39]), (6, ['b' * 40 + '\n'])]:
            for value in values:
                args = list(good); args[index] = value
                with self.subTest(index=index, value=value), self.assertRaises(ValueError): helper._context(*args)
        context = self.context()
        self.assertEqual(context['directory'], '/var/lib/hepta-ci-g1-123-2-repository-contracts')

    def test_template_only_attaches_exact_named_real_copy(self):
        template = (ROOT / helper.TEMPLATE).read_bytes(); context = self.context()
        rendered = helper._render(context, template).decode()
        self.assertIn('profile ' + context['profile'] + ' "' + context['directory'] + '/bin/python3"', rendered)
        self.assertIn('flags=(unconfined)', rendered); self.assertIn('  userns,', rendered)
        self.assertNotIn('"/usr/bin/python', rendered)
        for key, wrong in [('profile', 'unconfined'), ('directory', '/usr/bin'), ('uid', True)]:
            changed = dict(context); changed[key] = wrong
            with self.subTest(key=key), self.assertRaises(ValueError): helper._render(changed, template)
        for wrong in (template.replace(b'userns,', b'capability,'), template + b'\nprofile wildcard /** {}\n'):
            with self.assertRaises(ValueError): helper._render(context, wrong)

    def test_duplicate_and_nonfinite_state_json_refuse(self):
        for raw in (b'{"uid":1,"uid":2}', b'{"value":NaN}', b'{"value":Infinity}',
                    b'{"uid":1001.0}', b'{"value":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): helper._strict_json(raw)
        for raw in ('{}', b' ' * (helper.LIMIT + 1)):
            with self.assertRaises(ValueError): helper._strict_json(raw)

    def test_actual_regular_read_bounds_symlink_hardlink_and_fd_lifetime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; source.write_bytes(b'abcdefgh')
            before = set(os.listdir('/proc/self/fd'))
            self.assertEqual(helper._read(source, 8)[0], b'abcdefgh')
            with self.assertRaises(ValueError): helper._read(source, 7)
            (root / 'alias').symlink_to(source)
            with self.assertRaises(OSError): helper._read(root / 'alias')
            os.link(source, root / 'hardlink')
            with self.assertRaises(ValueError): helper._read(source)
            self.assertEqual(set(os.listdir('/proc/self/fd')), before)

    def test_actual_read_mutation_and_interrupted_read_close_owned_fd(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'; source.write_bytes(b'abcdefgh')
            before = set(os.listdir('/proc/self/fd')); original = os.read; changed = False
            def mutate(fd, size):
                nonlocal changed
                data = original(fd, size)
                if not changed:
                    changed = True; source.write_bytes(b'changed-length')
                return data
            with patch.object(helper.os, 'read', side_effect=mutate), self.assertRaises(ValueError): helper._read(source)
            with patch.object(helper.os, 'read', side_effect=InterruptedError('ordinary host interruption')), self.assertRaises(InterruptedError): helper._read(source)
            self.assertEqual(set(os.listdir('/proc/self/fd')), before)

    def test_actual_kernel_style_bound_and_create_new_never_follow_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'file'
            helper._write_new(path, b'abcdefgh', 0o600)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(helper._kernel_read(path, 8), b'abcdefgh')
            with self.assertRaises(ValueError): helper._kernel_read(path, 7)
            with self.assertRaises(FileExistsError): helper._write_new(path, b'replace', 0o600)
            alias = root / 'alias'; alias.symlink_to(path)
            with self.assertRaises(FileExistsError): helper._write_new(alias, b'replace', 0o600)
            self.assertEqual(path.read_bytes(), b'abcdefgh')

    def test_actual_proc_shaped_inventory_catches_copy_inode_and_inherited_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); binary = root / 'binary'; binary.write_bytes(b'ordinary fixture')
            identity = helper._identity(binary.stat()); profile = self.context()['profile']
            for pid, label in [(101, 'unconfined'), (102, profile + ' (unconfined)'), (103, 'unconfined')]:
                item = root / str(pid); (item / 'attr').mkdir(parents=True)
                (item / 'attr/current').write_text(label + '\n')
            (root / '101/exe').symlink_to(binary)
            # A profile-labelled descendant is caught even after exec changed or
            # after the exe link became unavailable; no real /proc is probed.
            self.assertEqual(sorted(helper._live_private(identity, profile, root)), [101, 102])

    def test_proc_label_read_error_is_refusal_not_evidence_of_no_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / '101').mkdir()
            with patch.object(helper, '_kernel_read', side_effect=PermissionError('fixture unreadable')), self.assertRaises(PermissionError):
                helper._live_private([1, 2], self.context()['profile'], root)

    def test_normal_cli_rejects_context_without_sudo_and_never_prints_payload(self):
        environment = dict(os.environ, GITHUB_ACTIONS='false', GITHUB_JOB='private-sentinel-路径\n1001')
        for argv in (['setup'], ['cleanup'], ['custom-sentinel-路径']):
            result = subprocess.run([sys.executable, str(ROOT / 'tools/ci_namespace_python.py'), *argv],
                                    cwd=ROOT, env=environment, capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (1, '', 'CI_NAMESPACE_PYTHON_REFUSED\n'))

    def test_private_preflight_requires_same_uid_label_and_no_host_caps(self):
        context = self.context()
        def status(cap='0000000000000000'):
            return ('CapEff:' + cap + '\nCapPrm:0\nCapInh:0\nCapAmb:0\nCapBnd:00000000ffffffff\nNoNewPrivs:0\n').encode()
        def read_for(raw, label):
            return lambda path, maximum: raw if str(path).endswith('/status') else label.encode()
        label = context['profile'] + ' (unconfined)\n'
        with patch.object(helper.os, 'getuid', return_value=1001), patch.object(helper.os, 'getgid', return_value=1001):
            with patch.object(helper, '_kernel_read', side_effect=read_for(status(), label)), patch.object(helper, '_global', return_value={'synthetic': 'unchanged'}):
                actual = helper._runner_preflight(context)
                self.assertEqual(actual['uid'], 1001); self.assertEqual(actual['caps']['CapEff'], 0)
            for raw, wrong in [(status('1'), label), (status(), 'unconfined\n')]:
                with patch.object(helper, '_kernel_read', side_effect=read_for(raw, wrong)), self.assertRaises(ValueError): helper._runner_preflight(context)
            with patch.object(helper.os, 'getgid', return_value=1002), patch.object(helper, '_kernel_read', side_effect=read_for(status(), label)), self.assertRaises(ValueError): helper._runner_preflight(context)


class OwnedCleanupModelTests(unittest.TestCase):
    @contextmanager
    def model(self, *, parser_failure=False):
        # Real ordinary files; root ownership, kernel inventory and parser are
        # explicitly synthetic. No sudo, AppArmor or namespace call occurs.
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            base = Path(directory); system = base / 'system-python'; system.write_bytes(b'real ordinary interpreter fixture')
            stack.enter_context(patch.object(helper, 'BASE', base))
            stack.enter_context(patch.object(helper, 'PYTHON', system))
            context = helper._context('123', '2', helper.JOBS[0], 1001, 1001, 'a' * 40, 'b' * 40)
            profiles = ['unrelated-original (enforce)']; settings = {'synthetic-global': 'unchanged'}; commands = []
            def executable(path):
                raw, observed = helper._read(path, 64 * 1024 * 1024)
                if observed.st_mode & 0o6000: raise ValueError('model setid refused')
                return {'identity': helper._identity(observed), 'bytes': len(raw), 'sha256': helper._sha(raw)}
            def parser(argv):
                commands.append(list(argv))
                self.assertEqual(argv[0], '/sbin/apparmor_parser')
                self.assertEqual(argv[2], context['directory'] + '/profile')
                if argv[1] == '-a':
                    profiles.append(context['profile'] + ' (unconfined)')
                    if parser_failure: raise ValueError('model failure after load')
                elif argv[1] == '-R': profiles.remove(context['profile'] + ' (unconfined)')
                else: self.fail('unexpected parser operation')
                return b''
            stack.enter_context(patch.object(helper, '_root_owned', side_effect=lambda path, mode=None: path.lstat()))
            stack.enter_context(patch.object(helper, '_executable', side_effect=executable))
            stack.enter_context(patch.object(helper, '_profiles', side_effect=lambda: sorted(profiles)))
            stack.enter_context(patch.object(helper, '_global', side_effect=lambda: dict(settings)))
            stack.enter_context(patch.object(helper, '_command', side_effect=parser))
            stack.enter_context(patch.object(helper, '_live_private', return_value=[]))
            yield context, profiles, settings, commands, system

    def test_full_modeled_setup_cleanup_removes_only_known_own_state(self):
        with self.model() as (context, profiles, settings, commands, system):
            result = helper._root_setup(context)
            self.assertFalse(result['corpus_root']); self.assertTrue(result['global_unchanged'])
            self.assertEqual(helper._read(Path(context['directory']) / 'bin/python3')[0], system.read_bytes())
            self.assertEqual(helper._root_cleanup(context), {'cleanup': 'PASS', 'global_unchanged': True, 'no_owned_python_processes': True})
            self.assertEqual(profiles, ['unrelated-original (enforce)'])
            self.assertFalse(Path(context['directory']).exists()); self.assertTrue(system.exists())
            self.assertEqual([argv[1] for argv in commands], ['-a', '-R'])

    def test_running_owned_interpreter_refuses_before_profile_removal(self):
        with self.model() as (context, profiles, settings, commands, system):
            helper._root_setup(context)
            with patch.object(helper, '_live_private', return_value=[101]), self.assertRaises(ValueError): helper._root_cleanup(context)
            self.assertEqual([argv[1] for argv in commands], ['-a'])
            self.assertTrue(Path(context['directory']).exists())

    def test_changed_global_system_copy_or_profile_refuses_cleanup(self):
        for variant in ('global', 'system', 'private', 'profile', 'state-context', 'loaded'):
            with self.subTest(variant=variant), self.model() as (context, profiles, settings, commands, system):
                helper._root_setup(context); directory = Path(context['directory'])
                if variant == 'global': settings['synthetic-global'] = 'changed'
                elif variant == 'system': system.write_bytes(b'changed-system')
                elif variant == 'private': (directory / 'bin/python3').write_bytes(b'changed-copy')
                elif variant == 'profile': (directory / 'profile').write_bytes(b'profile different {}')
                elif variant == 'loaded': (directory / 'loaded').write_bytes(b'not-verified\n')
                else:
                    state = json.loads((directory / 'state.json').read_text()); state['context']['uid'] = 1002
                    (directory / 'state.json').write_text(json.dumps(state))
                with self.assertRaises(ValueError): helper._root_cleanup(context)
                self.assertEqual([argv[1] for argv in commands], ['-a'])
                self.assertTrue(system.exists()); self.assertTrue(directory.exists())

    def test_orphan_profile_unrelated_profile_extra_inventory_and_preexisting_allocation_refuse(self):
        with self.model() as (context, profiles, settings, commands, system):
            profiles.append(context['profile'] + ' (unconfined)')
            with self.assertRaises(ValueError): helper._root_cleanup(context)
            self.assertEqual(commands, [])
        with self.model() as (context, profiles, settings, commands, system):
            Path(context['directory']).mkdir()
            with self.assertRaises(FileExistsError): helper._root_setup(context)
            self.assertEqual(commands, [])
        for variant in ('unrelated-profile', 'extra-file'):
            with self.subTest(variant=variant), self.model() as (context, profiles, settings, commands, system):
                helper._root_setup(context)
                if variant == 'unrelated-profile': profiles.append('new-unrelated (enforce)')
                else: (Path(context['directory']) / 'unexpected').write_bytes(b'do not delete')
                with self.assertRaises(ValueError): helper._root_cleanup(context)
                self.assertTrue(system.exists()); self.assertTrue(Path(context['directory']).exists())
                if variant == 'extra-file': self.assertTrue((Path(context['directory']) / 'unexpected').exists())

    def test_partial_parser_failure_is_not_success_but_known_state_can_be_cleaned(self):
        with self.model(parser_failure=True) as (context, profiles, settings, commands, system):
            with self.assertRaises(ValueError): helper._root_setup(context)
            self.assertFalse((Path(context['directory']) / 'loaded').exists())
            result = helper._root_cleanup(context)
            self.assertEqual(result['cleanup'], 'PASS')
            self.assertEqual([argv[1] for argv in commands], ['-a', '-R'])
            self.assertTrue(system.exists())


if __name__ == '__main__':
    unittest.main()
