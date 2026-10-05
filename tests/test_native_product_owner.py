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
import subprocess
from unittest.mock import patch
from tools import prepare_native_product_owner as assembly
from tools import validate_native_product_owner as scope

class NativeProductOwnerContractTests(unittest.TestCase):
    def test_unit_return_event_loop_fragment_compiles_and_preserves_invalidation_refusal(self):
        # A deliberately synthetic unit-return ABI typing check, not Servo or
        # journal qualification. The actual fixed-PIN target still must compile
        # and execute all four unchanged native cases in its workflow.
        source = assembly.read(assembly.ROOT / scope.EXPECTED['qualification']['consumer_module']).decode()
        start = source.index('        self.servo.spin_event_loop();')
        end = source.index('        if self.apply_updates().is_err()', start)
        fragment = source[start:end]
        before = '''        if !self.servo.spin_event_loop() || self.delegate.invalidated.get() {
            return Ok(self.fail_pending(ServoRuntimeError::BrowserCrashed));
        }
'''
        skeleton = '''use std::cell::Cell;
struct SyntheticUnitServo { spins: Cell<usize> }
impl SyntheticUnitServo {
    pub fn spin_event_loop(&self) { self.spins.set(self.spins.get() + 1); }
}
struct Delegate { invalidated: Cell<bool> }
enum ServoRuntimeError { BrowserCrashed }
#[derive(Debug, PartialEq)]
enum NativeDrive { Idle, Retired }
struct State { servo: SyntheticUnitServo, delegate: Delegate }
impl State {
    fn fail_pending(&mut self, _: ServoRuntimeError) -> NativeDrive { NativeDrive::Retired }
    fn drive(&mut self) -> Result<NativeDrive, ServoRuntimeError> {
FRAGMENT
        Ok(NativeDrive::Idle)
    }
}
fn main() {
    let mut state = State { servo: SyntheticUnitServo { spins: Cell::new(0) },
        delegate: Delegate { invalidated: Cell::new(false) } };
    assert_eq!(state.drive().ok(), Some(NativeDrive::Idle));
    assert_eq!(state.servo.spins.get(), 1);
    state.delegate.invalidated.set(true);
    assert_eq!(state.drive().ok(), Some(NativeDrive::Retired));
    assert_eq!(state.servo.spins.get(), 2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            env = dict(os.environ, RUSTUP_TOOLCHAIN='1.93.0')
            for name, selected, expected in [('before', before, 1), ('after', fragment, 0)]:
                file = path / (name + '.rs'); binary = path / name
                file.write_text(skeleton.replace('FRAGMENT', selected))
                compiled = subprocess.run(['rustc', '--edition=2024', str(file), '-o', str(binary)],
                    cwd=assembly.ROOT, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, expected, compiled.stderr)
                if expected:
                    self.assertIn('E0600', compiled.stderr)
                else:
                    executed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
                    self.assertEqual(executed.returncode, 0, executed.stderr)

    def test_failure_request_marker_belongs_to_current_unbuffered_child(self):
        source = (assembly.ROOT / 'experiments/servo-product-owner/src/approved_connected_tests.rs').read_text()
        support = (assembly.ROOT / 'experiments/servo-product-owner/src/approved_test_support.rs').read_text()
        self.assertEqual(source.count('request_marker_at_failure('), 2)
        assertion = source.split('        assert!(\n            Instant::now() < driver.original_deadline().unwrap(),', 1)[1].split('        );', 1)[0]
        self.assertIn('request_marker_at_failure(trio.agent.child.stdout.as_mut())', assertion)
        self.assertIn('let reader = self.child.stdout.as_mut().unwrap();', support)
        self.assertIn('.stdout(Stdio::piped())', support)
        self.assertNotIn('BufReader', source + support)
        self.assertNotIn('stdout.take()', source + support)
        self.assertNotIn('stdout.try_clone()', source + support)
        self.assertIn('let (health, health_fact) = run(\n        &mut driver,\n        &mut first,', source)
        self.assertIn('let mut creating = support::Trio::new_before(original);', source)
        self.assertIn('let (created, created_digest) = run(\n        &mut driver,\n        &mut creating,', source)
        self.assertLess(source.index('trio.agent.expect("REQUEST");'), source.index('trio.finish();'))
        agent = support.split('fn agent(op: &Path) {', 1)[1].split('pub struct Trio {', 1)[0]
        self.assertEqual(agent.count('println!("REQUEST");'), 1)
        self.assertLess(agent.index('ClientConnection::connect('), agent.index('client.send_request('))
        self.assertLess(agent.index('client.send_request('), agent.index('println!("REQUEST");'))
        self.assertIn('agent.expect("CONNECTED");', support)
        self.assertEqual(agent.count('println!('), 5)
        self.assertIn('decode_response(&bytes).unwrap();\n        println!("RESPONSE {}", std::str::from_utf8(&bytes).unwrap());', agent)
        self.assertIn('} else {\n        println!("RESPONSE_REFUSED");', agent)
        self.assertLess(agent.index('client.receive_response('), agent.index('decode_response(&bytes)'))
        self.assertNotIn('Command::', agent)
        self.assertNotIn('.spawn(', agent)
        self.assertNotIn('thread::', agent)

    def test_failure_request_marker_extracted_rust_with_pure_poll_and_reader_substitutes(self):
        # No pipe, subprocess peer, native engine or real poll/read syscall is
        # exercised by the extracted program. The original CI supplies rustc.
        source = (assembly.ROOT / 'experiments/servo-product-owner/src/approved_connected_tests.rs').read_text()
        start = source.index('fn request_marker_at_failure(')
        fragment = source[start:source.index('fn run(', start)]
        self.assertEqual(fragment.count('std::process::ChildStdout'), 1)
        fragment = fragment.replace('std::process::ChildStdout', 'SyntheticStdout', 1)
        skeleton = r"""use std::cell::RefCell;
use std::io::{self, Read};
use std::os::fd::{AsRawFd, RawFd};
struct PollState { result: i32, events: i16, calls: usize }
thread_local! {
    static POLL: RefCell<PollState> = const { RefCell::new(PollState { result: 0, events: 0, calls: 0 }) };
}
mod libc {
    #[allow(non_camel_case_types)]
    pub struct pollfd { pub fd: i32, pub events: i16, pub revents: i16 }
    pub const POLLIN: i16 = 1;
    pub const POLLHUP: i16 = 16;
    pub unsafe fn poll(p: *mut pollfd, count: usize, timeout: i32) -> i32 {
        assert_eq!(count, 1);
        assert_eq!(timeout, 0, "the observation cannot wait");
        let p = unsafe { &mut *p };
        assert_eq!(p.fd, 24);
        assert_eq!(p.events, POLLIN);
        super::POLL.with(|cell| {
            let mut state = cell.borrow_mut();
            state.calls += 1;
            assert_eq!(state.calls, 1, "poll is never retried");
            p.revents = state.events;
            state.result
        })
    }
}
struct SyntheticStdout {
    result: Result<usize, io::ErrorKind>,
    payload: [u8; 17],
    reads: usize,
}
impl AsRawFd for SyntheticStdout {
    fn as_raw_fd(&self) -> RawFd { 24 }
}
impl Read for SyntheticStdout {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        assert_eq!(bytes.len(), 17, "never read arbitrary response data");
        self.reads += 1;
        assert_eq!(self.reads, 1, "partial/error reads are never retried");
        match self.result {
            Ok(n) => { bytes[..n].copy_from_slice(&self.payload[..n]); Ok(n) },
            Err(kind) => Err(io::Error::from(kind)),
        }
    }
}
FRAGMENT
fn case(poll_result: i32, events: i16, read_result: Result<usize, io::ErrorKind>,
        payload: [u8; 17], expected: &str, reads: usize) {
    POLL.with(|cell| *cell.borrow_mut() = PollState { result: poll_result, events, calls: 0 });
    let mut reader = SyntheticStdout { result: read_result, payload, reads: 0 };
    assert_eq!(request_marker_at_failure(Some(&mut reader)), expected);
    assert_eq!(reader.reads, reads);
    POLL.with(|cell| assert_eq!(cell.borrow().calls, 1));
}
fn main() {
    assert_eq!(request_marker_at_failure(None), "unknown");
    POLL.with(|cell| assert_eq!(cell.borrow().calls, 0));
    let mut marker = [0_u8; 17];
    marker[..8].copy_from_slice(b"REQUEST\n");
    let response = *b"REQUEST\nRESPONSE ";
    let receive_error = *b"REQUEST\nRESPONSE_";
    for (result, events) in [(-1, 0), (0, 0), (2, libc::POLLIN), (1, 0), (1, libc::POLLHUP), (1, 32)] {
        case(result, events, Ok(17), marker, "unknown", 0);
    }
    // Every partial length is exercised for both fixed response prefixes.
    // Exactly eight bytes preserves the original complete REQUEST marker;
    // zero through seven and nine through sixteen remain unknown.
    for payload in [response, receive_error] {
        for bytes in 0..17 {
            let expected = if bytes == 8 { "request-observed" } else { "unknown" };
            case(1, libc::POLLIN, Ok(bytes), payload, expected, 1);
        }
    }
    for kind in [io::ErrorKind::WouldBlock, io::ErrorKind::Interrupted, io::ErrorKind::Other] {
        case(1, libc::POLLIN, Err(kind), marker, "unknown", 1);
    }
    case(1, libc::POLLIN, Ok(8), [b'X'; 17], "unknown", 1);
    case(1, libc::POLLIN, Ok(17), marker, "unknown", 1);
    case(1, libc::POLLIN, Ok(8), marker, "request-observed", 1);
    case(1, libc::POLLIN, Ok(17), response, "response-envelope-observed", 1);
    case(1, libc::POLLIN, Ok(17), receive_error, "agent-receive-error", 1);
    case(1, libc::POLLIN | libc::POLLHUP, Ok(8), marker, "request-observed", 1);
    case(1, libc::POLLIN | libc::POLLHUP, Ok(17), response, "response-envelope-observed", 1);
    case(1, libc::POLLIN | libc::POLLHUP, Ok(17), receive_error, "agent-receive-error", 1);
    // Assertion formatting must stay lazy on the successful original branch.
    POLL.with(|cell| *cell.borrow_mut() = PollState { result: 1, events: libc::POLLIN, calls: 0 });
    let mut reader = SyntheticStdout { result: Ok(8), payload: marker, reads: 0 };
    assert!(true, "original deadline failure: {}", request_marker_at_failure(Some(&mut reader)));
    assert_eq!(reader.reads, 0);
    POLL.with(|cell| assert_eq!(cell.borrow().calls, 0));
    // Unavailable diagnostics cannot replace the original failed assertion.
    let failure = std::panic::catch_unwind(|| {
        assert!(false, "original deadline failure: {}", request_marker_at_failure(None));
    }).expect_err("the original assertion must still fail");
    let text = failure.downcast_ref::<String>().unwrap();
    assert_eq!(text, "original deadline failure: unknown");
    println!("PURE_REQUEST_MARKER_CONTROLS cases=54; no kernel/peer/native claim");
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            rust_source = path / 'request_marker.rs'
            binary = path / 'request_marker'
            rust_source.write_text(skeleton.replace('FRAGMENT', fragment))
            compiled = subprocess.run(['rustc', '--edition=2024', str(rust_source), '-o', str(binary)],
                cwd=assembly.ROOT, env=dict(os.environ, RUSTUP_TOOLCHAIN='1.93.0'),
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertIn('PURE_REQUEST_MARKER_CONTROLS cases=54', executed.stdout)

    def test_formatting_scope_cannot_disable_comparison_or_change_approved_config(self):
        for field, value in [('formatter_and_byte_comparison_required', False), ('configuration_sha256', '0'*64), ('upstream_rust', '1.93.0')]:
            item = copy.deepcopy(scope.EXPECTED)
            item['qualification']['formatting'][field] = value
            with self.assertRaises(ValueError): scope.typed_equal(item, scope.EXPECTED)

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
    def test_actual_formatting_files_bind_same_fixed_bytes_and_refuse_drift(self):
        upstream = self.root/'upstream'; upstream.mkdir()
        local = self.root/'local'; (local/assembly.FORMAT_CONFIG).parent.mkdir(parents=True)
        data = (assembly.ROOT/assembly.FORMAT_CONFIG).read_bytes()
        (upstream/'rustfmt.toml').write_bytes(data)
        (local/assembly.FORMAT_CONFIG).write_bytes(data)
        self.assertEqual(assembly.verify_format_config(upstream, local), assembly.PIN_FILES['rustfmt.toml'])
        (local/assembly.FORMAT_CONFIG).write_bytes(data+b'max_width = 80\n')
        with self.assertRaises(ValueError): assembly.verify_format_config(upstream, local)
        (upstream/'rustfmt.toml').write_bytes(data+b'max_width = 80\n')
        with self.assertRaises(ValueError): assembly.verify_format_config(upstream, local)
        (upstream/'rustfmt.toml').write_bytes(data); (local/assembly.FORMAT_CONFIG).write_bytes(data)
        os.link(local/assembly.FORMAT_CONFIG, self.root/'foreign-config-alias')
        with self.assertRaises((ValueError, OSError)): assembly.verify_format_config(upstream, local)

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
