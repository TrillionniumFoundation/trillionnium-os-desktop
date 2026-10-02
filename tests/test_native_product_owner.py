"""Closed source contract and real private-filesystem source assembly negatives.
These fixtures never compile/run Servo or provision a production principal.
"""
from __future__ import annotations
import copy
import json
import os
import stat
import gc
import inspect
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import prepare_native_product_owner as assembly
from tools import validate_native_product_owner as scope

class NativeProductOwnerContractTests(unittest.TestCase):
    def test_current_closed_source_contract_and_consumer_wiring(self):
        scope.validate()

    def test_nested_activation_claim_is_refused(self):
        item = copy.deepcopy(scope.EXPECTED)
        item['non_claims']['retained_terminal_handoff_integrated'] = True
        with self.assertRaises(ValueError): scope.typed_equal(item, scope.EXPECTED)

    def test_unknown_nested_capability_is_refused(self):
        item = copy.deepcopy(scope.EXPECTED)
        item['profile']['allow_actions'] = False
        with self.assertRaises(ValueError): scope.typed_equal(item, scope.EXPECTED)

    def test_boolean_and_float_budget_aliases_are_refused(self):
        for value in [True, 5.0]:
            item = copy.deepcopy(scope.EXPECTED); item['bounds']['native_command_seconds'] = value
            with self.assertRaises(ValueError): scope.typed_equal(item, scope.EXPECTED)

    def test_deadline_renewal_and_successful_close_promotion_are_refused(self):
        for path in [('bounds', 'deadline_renewal'), ('close', 'successful_closed_response'), ('close', 'pipeline_retirement_confirmed')]:
            item = copy.deepcopy(scope.EXPECTED); item[path[0]][path[1]] = True
            with self.assertRaises(ValueError): scope.typed_equal(item, scope.EXPECTED)

    def test_status_promotion_and_changed_pin_are_refused(self):
        for key, value in [('status', 'PRODUCTION_READY'), ('servo_commit', 'f' * 40), ('default_activation', True)]:
            item = copy.deepcopy(scope.EXPECTED); item[key] = value
            with self.assertRaises(ValueError): scope.typed_equal(item, scope.EXPECTED)

class NativeOwnerSourceAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def file(self, name, data=b'fixed source'):
        path = self.root / name; path.write_bytes(data); return path

    def test_read_refuses_actual_ancestor_symlink(self):
        directory = self.root / 'actual'; directory.mkdir()
        (directory/'source').write_bytes(b'source')
        (self.root/'alias').symlink_to(directory, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)): assembly.read(self.root/'alias'/'source')

    def test_read_refuses_hardlink_and_oversize_source(self):
        original = self.file('original'); os.link(original, self.root/'alias')
        with self.assertRaises((ValueError, OSError)): assembly.read(original)
        large = self.file('large', b'x' * (assembly.MAX_SOURCE + 1))
        with self.assertRaises(ValueError): assembly.read(large)

    def test_write_preserves_existing_alias_and_does_not_truncate(self):
        target = self.file('manifest', b'old'); alias = self.root/'alias'; os.link(target, alias)
        with self.assertRaises(ValueError): assembly.write_source(target, b'new', b'old')
        self.assertEqual(alias.read_bytes(), b'old'); self.assertEqual(target.read_bytes(), b'old')

    def test_write_refuses_appeared_target_and_ancestor_symlink(self):
        target = self.file('exists')
        with self.assertRaises(ValueError): assembly.write_source(target, b'replace')
        directory = self.root/'actual'; directory.mkdir(); alias = self.root/'alias'; alias.symlink_to(directory, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)): assembly.write_source(alias/'new', b'new')
        self.assertFalse((directory/'new').exists())

    def test_atomic_source_readback_and_failed_staged_substitution(self):
        target = self.root/'new'
        assembly.write_source(target, b'actual source')
        self.assertEqual(assembly.read(target), b'actual source')
        assembly.write_source(target, b'successor', b'actual source')
        self.assertEqual(assembly.read(target), b'successor')
        outside = self.file('outside', b'foreign')
        real_fsync = os.fsync
        def substitute(fd):
            real_fsync(fd)
            for entry in self.root.iterdir():
                if entry.name.startswith('.native-owner-'):
                    entry.unlink(); entry.symlink_to(outside); break
        with patch.object(assembly.os, 'fsync', substitute):
            with self.assertRaises(ValueError): assembly.write_source(self.root/'negative', b'candidate')
        self.assertFalse((self.root/'negative').exists()); self.assertEqual(outside.read_bytes(), b'foreign')
        self.assertTrue(any(p.is_symlink() for p in self.root.glob('.native-owner-*')))

    def test_after_read_real_file_mutation_is_refused(self):
        path = self.file('mutating'); real = os.fstat; count = 0
        def mutate(fd):
            nonlocal count
            result = real(fd)
            if stat.S_ISREG(result.st_mode): count += 1
            if count == 4: path.write_bytes(b'changed')
            return real(fd)
        with patch.object(assembly.os, 'fstat', mutate):
            with self.assertRaises(ValueError): assembly.read(path)

    def test_non_pin_checkout_refuses_before_any_source_assembly(self):
        with patch.object(assembly, 'git', return_value='0'*40):
            with self.assertRaises(ValueError): assembly.prepare(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_after_read_actual_hardlink_creation_is_refused(self):
        path = self.file('link-race'); real = os.fstat; count = 0
        def add_alias(fd):
            nonlocal count
            result = real(fd)
            if stat.S_ISREG(result.st_mode): count += 1
            if count == 4: os.link(path, self.root/'added-alias')
            return real(fd)
        with patch.object(assembly.os, 'fstat', add_alias):
            with self.assertRaises(ValueError): assembly.read(path)
        self.assertEqual((self.root/'added-alias').read_bytes(), b'fixed source')

    def test_dependency_edge_drift_and_unknown_local_package_are_refused(self):
        before = self.file('before.lock', b'version=4\n[[package]]\nname="servo"\nversion="0.1.0"\ndependencies=["original"]\n')
        after = self.file('after.lock', before.read_bytes())
        with patch.dict(assembly.PIN_FILES, {'Cargo.lock': assembly.digest(before.read_bytes())}):
            self.assertEqual(assembly.verify_lock(before, after)['actual_servo_execution'], False)
            after.write_bytes(before.read_bytes().replace(b'"original"', b'"different"'))
            with self.assertRaises(ValueError): assembly.verify_lock(before, after)
            after.write_bytes(before.read_bytes()+b'[[package]]\nname="unreviewed-local"\nversion="0.1.0"\n')
            with self.assertRaises(ValueError): assembly.verify_lock(before, after)

    def test_unbound_baseline_lock_and_registry_checksum_change_are_refused(self):
        baseline = b'version=4\n[[package]]\nname="dependency"\nversion="1.0.0"\nsource="registry+https://example.invalid"\nchecksum="fixed"\n'
        before = self.file('before.lock', baseline); after = self.file('after.lock', baseline)
        with self.assertRaises(ValueError): assembly.verify_lock(before, after)
        with patch.dict(assembly.PIN_FILES, {'Cargo.lock': assembly.digest(baseline)}):
            after.write_bytes(baseline.replace(b'checksum="fixed"', b'checksum="changed"'))
            with self.assertRaises(ValueError): assembly.verify_lock(before, after)

    def test_approved_libc_identity_cannot_smuggle_dependency_edges(self):
        baseline = b'version=4\n[[package]]\nname="libc"\nversion="0.2.189"\nsource="registry+https://github.com/rust-lang/crates.io-index"\nchecksum="3eaf3ede3fee6db1a4c2ee091bf8a8b4dccdc6d17f656fb07896ee72867612f2"\n'
        before = self.file('before.lock', baseline); after = self.file('after.lock', baseline)
        with patch.dict(assembly.PIN_FILES, {'Cargo.lock': assembly.digest(baseline)}):
            self.assertFalse(assembly.verify_lock(before, after)['actual_servo_execution'])
            after.write_bytes(baseline + b'dependencies=["unreviewed-local"]\n')
            with self.assertRaises(ValueError): assembly.verify_lock(before, after)

    def test_real_walk_close_line_interrupt_never_loses_the_old_descriptor(self):
        lines, first = inspect.getsourcelines(assembly._SourceDescriptor.close)
        for marker in ['descriptor, self.fd =', 'close_attempted = True; os.close']:
            with self.subTest(marker=marker):
                target_line = next(first+i for i, line in enumerate(lines) if marker in line)
                captured = []
                before = {name: os.readlink('/proc/self/fd/'+name) for name in os.listdir('/proc/self/fd') if os.path.exists('/proc/self/fd/'+name)}
                def trace(frame, event, arg):
                    if frame.f_code is assembly._SourceDescriptor.close.__code__ and event == 'line' and frame.f_lineno == target_line and not captured:
                        descriptor = frame.f_locals.get('descriptor')
                        if descriptor is None: descriptor = frame.f_locals['self'].fd
                        if descriptor is not None:
                            captured.append(descriptor)
                            raise KeyboardInterrupt('actual ordinary line before native walk close')
                    return trace
                prior = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(KeyboardInterrupt): assembly.write_source(self.root/'trace-target', b'source')
                finally: sys.settrace(prior)
                gc.collect()
                self.assertEqual(len(captured), 1)
                with self.assertRaises(OSError): os.fstat(captured[0])
                after = {name: os.readlink('/proc/self/fd/'+name) for name in os.listdir('/proc/self/fd') if os.path.exists('/proc/self/fd/'+name)}
                self.assertEqual(after, before)
                self.assertFalse((self.root/'trace-target').exists())

    def test_real_close_then_interrupt_and_fd_reuse_never_closes_foreign_descriptor(self):
        real_close = os.close
        for target in ['/', '.native-owner-']:
            with self.subTest(target=target):
                foreign = []; captured = []; attempts = []; capture_index = []
                destination = self.root/('walk-target' if target == '/' else 'staged-target')
                def close_then_reuse(fd):
                    attempts.append(fd)
                    link = os.readlink('/proc/self/fd/'+str(fd))
                    real_close(fd)
                    if not captured and (link == '/' if target == '/' else '.native-owner-' in link):
                        captured.append(fd)
                        capture_index.append(len(attempts)-1)
                        opened = os.open('/dev/null', os.O_RDONLY | os.O_CLOEXEC)
                        if opened != fd:
                            os.dup2(opened, fd); real_close(opened)
                        foreign.append(fd)
                        raise KeyboardInterrupt('actual native close completed before interruption')
                try:
                    with patch.object(assembly.os, 'close', close_then_reuse):
                        with self.assertRaises(KeyboardInterrupt): assembly.write_source(destination, b'actual source')
                    gc.collect()
                    self.assertEqual(len(foreign), 1)
                    self.assertEqual(attempts[capture_index[0]:].count(foreign[0]), 1)
                    self.assertTrue(stat.S_ISCHR(os.fstat(foreign[0]).st_mode))
                    self.assertEqual(destination.exists(), target != '/')
                finally:
                    for descriptor in foreign: real_close(descriptor)

    def test_parent_close_call_and_final_cleanup_interrupt_gc_close_only_owned_descriptors(self):
        lines, first = inspect.getsourcelines(assembly.write_source)
        for marker in ['parent.close()', 'for descriptor in reversed(descriptors):']:
            with self.subTest(marker=marker):
                target_line = next(first+i for i, line in enumerate(lines) if line.strip() == marker)
                fired = []
                destination = self.root/('parent-cut' if marker == 'parent.close()' else 'finally-cut')
                before = {name: os.readlink('/proc/self/fd/'+name) for name in os.listdir('/proc/self/fd') if os.path.exists('/proc/self/fd/'+name)}
                def trace(frame, event, arg):
                    if frame.f_code is assembly.write_source.__code__ and event == 'line' and frame.f_lineno == target_line and not fired:
                        fired.append(True)
                        raise KeyboardInterrupt('actual caller line before descriptor cleanup')
                    return trace
                prior = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(KeyboardInterrupt): assembly.write_source(destination, b'actual source')
                finally: sys.settrace(prior)
                gc.collect()
                self.assertEqual(fired, [True])
                after = {name: os.readlink('/proc/self/fd/'+name) for name in os.listdir('/proc/self/fd') if os.path.exists('/proc/self/fd/'+name)}
                self.assertEqual(after, before)
                self.assertEqual(destination.exists(), marker != 'parent.close()')

if __name__ == '__main__': unittest.main()
