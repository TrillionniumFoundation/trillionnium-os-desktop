"""Closed source contract and real private-filesystem source assembly negatives.
These fixtures never compile/run Servo or provision a production principal.
"""
from __future__ import annotations
import copy
import json
import os
import re
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
        self.assertIn('decode_response(&bytes).unwrap(); println!("RESPONSE {}", std::str::from_utf8(&bytes).unwrap());', ' '.join(agent.split()))
        self.assertEqual(agent.count('client.receive_response('), 1)
        self.assertEqual(agent.count('RESPONSE_REFUSED'), 1)
        refusal = agent.split('        Err(error) => {', 1)[1].split('\n        },', 1)[0]
        self.assertEqual(refusal.count('println!('), 1)
        self.assertIn('let token = agent_receive_error_token(&error);', refusal)
        self.assertLess(refusal.index('agent_receive_error_token(&error)'), refusal.index('drop(error);'))
        self.assertLess(refusal.index('drop(error);'), refusal.index('println!("RESPONSE_REFUSED {token}");'))
        classifier = support.split('const AGENT_RECEIVE_ERRORS:', 1)[1].split('fn agent(op: &Path)', 1)[0]
        # There is no formatting or probing escape hatch for an error's text,
        # raw number, nested source, protocol fields, or payload.
        for forbidden in ['format!', 'write!', 'println!', 'eprintln!', 'dbg!',
                          '.to_string(', '.raw_os_error(', '.get_ref(', '.get_mut(',
                          '.source(', '.read(', '.poll(', '.sleep(', '.receive_response(']:
            self.assertNotIn(forbidden, classifier)
        self.assertEqual(classifier.count('error.kind()'), 1)
        self.assertEqual(classifier.count('_ =>'), 1, 'only non-exhaustive ErrorKind has a fallback')
        self.assertNotIn('pub const AGENT_RECEIVE_ERRORS', support)
        self.assertNotIn('pub fn agent_receive_error_token', support)
        self.assertIn('pub fn agent_receive_error_label(token: &[u8]) -> Option<&\'static str>', support)
        kernel = (assembly.ROOT / 'apps/hepta-browserd/tests/approved_native_startup_kernel.rs').read_text()
        cancel = kernel.split('    trio.agent.expect("REQUEST");', 1)[1].split('    assert!(trio.custodian.line()', 1)[0]
        self.assertEqual(cancel.count('trio.agent.line()'), 1)
        self.assertIn('trio.agent.line().starts_with(if cancel {', cancel)
        self.assertIn('"RESPONSE_REFUSED"', cancel)
        self.assertIn('"RESPONSE "', cancel)
        self.assertNotIn('agent_receive_error_label', cancel)
        self.assertIn('let mut bytes = [0; 34];', source)
        self.assertIn('assert_eq!(observation.service().is_ok(), !cancel);', kernel)
        self.assertIn('Ok(ProductControlMonitorOutcome::ReportEnqueued)', kernel)
        self.assertIn('"REPORT Indeterminate "', kernel)
        self.assertIn('"REPORT Completed "', kernel)
        self.assertLess(agent.index('client.receive_response('), agent.index('decode_response(&bytes)'))
        self.assertNotIn('Command::', agent)
        self.assertNotIn('.spawn(', agent)
        self.assertNotIn('thread::', agent)

    def test_failure_request_marker_extracted_rust_with_pure_poll_and_reader_substitutes(self):
        # Only the original CI supplies rustc. This program substitutes poll,
        # reads, receive, decoding and println; it opens no pipe, socket or peer.
        source = (assembly.ROOT / 'experiments/servo-product-owner/src/approved_connected_tests.rs').read_text()
        support = (assembly.ROOT / 'experiments/servo-product-owner/src/approved_test_support.rs').read_text()
        kernel = (assembly.ROOT / 'apps/hepta-browserd/tests/approved_native_startup_kernel.rs').read_text()
        facade = (assembly.ROOT / 'crates/hepta-agent-transport/src/facade.rs').read_text()
        start = source.index('fn request_marker_at_failure(')
        fragment = source[start:source.index('fn run(', start)]
        self.assertEqual(fragment.count('std::process::ChildStdout'), 1)
        fragment = fragment.replace('std::process::ChildStdout', 'SyntheticStdout', 1)
        start = support.index('const AGENT_RECEIVE_ERRORS:')
        helpers = support[start:support.index('fn agent(op: &Path)', start)]
        start = facade.index('pub enum TransportError {')
        enum = facade[start:facade.index('\n}\n', start) + 3]
        start = support.index('    match client.receive_response(sequence, WAIT) {')
        handling = support[start:support.index("    assert_eq!(input(), b'x');", start)]
        cancel = kernel.split('    trio.agent.expect("REQUEST");', 1)[1].split('    assert!(trio.custodian.line()', 1)[0]
        consumer = re.search(r'assert!\((trio\.agent\.line\(\)\.starts_with\(if cancel \{.*?\n    \}\))\);', cancel, re.S)
        self.assertIsNotNone(consumer)
        # Independent requirements, deliberately not populated from the table
        # or match under test. The real public enum supplies the Rust ABI shape.
        outer = [
            ('UnsupportedPlatform', 'UnsupportedPlatform', 'RXPLAT___', 'unsupported-platform'),
            ('InvalidPeerCredentials', 'InvalidPeerCredentials', 'RXCRED___', 'invalid-peer-credentials'),
            ('UnauthorizedPeer', 'UnauthorizedPeer', 'RXUNAUTH_', 'unauthorized-peer'),
            ('InvalidMagic', 'InvalidMagic', 'RXMAGIC__', 'invalid-magic'),
            ('UnsupportedVersion', 'UnsupportedVersion(31337)', 'RXVERS___', 'unsupported-version'),
            ('UnknownFrameKind', 'UnknownFrameKind(213)', 'RXKIND___', 'unknown-frame-kind'),
            ('ReservedFlags', 'ReservedFlags(197)', 'RXFLAGS__', 'reserved-flags'),
            ('InvalidSessionNonce', 'InvalidSessionNonce', 'RXNINVAL_', 'invalid-session-nonce'),
            ('FrameTooLarge', 'FrameTooLarge { length: 31337, maximum: 127 }', 'RXSIZE___', 'frame-too-large'),
            ('PayloadDigestMismatch', 'PayloadDigestMismatch', 'RXDIGEST_', 'payload-digest-mismatch'),
            ('DeadlineExceeded', 'DeadlineExceeded', 'RXDEADLN_', 'deadline-or-timeout'),
            ('UnexpectedEof', 'UnexpectedEof', 'RXEOF____', 'unexpected-eof'),
            ('InvalidChallenge', 'InvalidChallenge', 'RXCHALL__', 'invalid-challenge'),
            ('UnexpectedFrameKind', 'UnexpectedFrameKind', 'RXEXPECT_', 'unexpected-frame-kind'),
            ('SessionNonceMismatch', 'SessionNonceMismatch', 'RXNONCE__', 'session-nonce-mismatch'),
            ('SequenceMismatch', 'SequenceMismatch { expected: 31337, actual: 127 }', 'RXSEQ____', 'sequence-mismatch'),
            ('SequenceExhausted', 'SequenceExhausted', 'RXSEQEND_', 'sequence-exhausted'),
            ('SelfCheckThreadPanicked', 'SelfCheckThreadPanicked', 'RXPANIC__', 'self-check-thread-panicked'),
        ]
        io_classes = [
            ('ConnectionReset', 'RXRESET__', 'io-connection-reset'),
            ('ConnectionAborted', 'RXABORT__', 'io-connection-aborted'),
            ('BrokenPipe', 'RXBROKEN_', 'io-broken-pipe'),
            ('NotConnected', 'RXNOTCON_', 'io-not-connected'),
            ('UnexpectedEof', 'RXIOEOF__', 'io-unexpected-eof'),
            ('TimedOut', 'RXIOTIME_', 'io-timed-out'),
            ('WouldBlock', 'RXIOBLCK_', 'io-would-block'),
            ('Interrupted', 'RXINTR___', 'io-interrupted'),
            ('InvalidInput', 'RXINVAL__', 'io-invalid-input'),
            ('PermissionDenied', 'RXDENIED_', 'io-permission-denied'),
            ('Other', 'RXIOOTHR_', 'io-other'),
        ]
        actual_variants = re.findall(r'^    (\w+)(?:\(|,| \{)', enum, re.M)
        self.assertCountEqual(actual_variants, ['Io'] + [row[0] for row in outer])
        self.assertCountEqual(re.findall(r'^        TransportError::(\w+)', helpers, re.M), actual_variants)
        expected = outer + [
            ('Io', f'Io(io::Error::from(io::ErrorKind::{kind}))', token, label)
            for kind, token, label in io_classes
        ]
        # Different field values must not change or leak through a fixed class.
        boundaries = [
            ('UnsupportedVersion(0)', 'RXVERS___'), ('UnsupportedVersion(u16::MAX)', 'RXVERS___'),
            ('UnknownFrameKind(0)', 'RXKIND___'), ('UnknownFrameKind(u8::MAX)', 'RXKIND___'),
            ('ReservedFlags(0)', 'RXFLAGS__'), ('ReservedFlags(u8::MAX)', 'RXFLAGS__'),
            ('FrameTooLarge { length: 0, maximum: usize::MAX }', 'RXSIZE___'),
            ('FrameTooLarge { length: usize::MAX, maximum: 0 }', 'RXSIZE___'),
            ('SequenceMismatch { expected: 0, actual: u64::MAX }', 'RXSEQ____'),
            ('SequenceMismatch { expected: u64::MAX, actual: 0 }', 'RXSEQ____'),
        ]
        other_io = ['NotFound', 'AlreadyExists', 'ConnectionRefused', 'AddrInUse',
                    'AddrNotAvailable', 'InvalidData', 'WriteZero', 'Unsupported', 'OutOfMemory']
        boundaries += [(f'Io(io::Error::from(io::ErrorKind::{kind}))', 'RXIOOTHR_') for kind in other_io]
        compatible_suffixes = ['', ' ', ' RXUNKNOWN', ' arbitrary text', ' RXPLAT___suffix', '_suffix']
        cancel_invalid = ['', 'REQUEST', 'REQUEST\n', 'unknown', 'arbitrary text', 'RESPONSE ',
                          'RESPONSE {}', 'RESPONSE_', 'RXPLAT___', 'response_refused', 'XRESPONSE_REFUSED']
        original_handling = '''    if let Ok(bytes) = client.receive_response(sequence, WAIT) {
        decode_response(&bytes).unwrap();
        println!("RESPONSE {}", std::str::from_utf8(&bytes).unwrap());
    } else {
        println!("RESPONSE_REFUSED");
    }
'''
        skeleton = r"""use std::cell::RefCell;
use std::collections::HashSet;
use std::io::{self, Read};
use std::os::fd::{AsRawFd, RawFd};
mod hepta_agent_transport {
    use std::io;
    // Actual facade declaration, without its Debug/Display implementations.
    // An accidental attempt to format TransportError must fail compilation.
ACTUAL_ENUM
}
mod support {
    use crate::hepta_agent_transport;
ACTUAL_HELPERS
    pub fn classify(error: &hepta_agent_transport::TransportError) -> &'static str {
        agent_receive_error_token(error)
    }
    pub fn table() -> &'static [(&'static str, &'static str)] { &AGENT_RECEIVE_ERRORS }
}
fn consumer_accepts(response: &str, cancel: bool) -> bool {
ACTUAL_CONSUMER
}
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
    payload: [u8; 34],
    reads: usize,
}
impl AsRawFd for SyntheticStdout {
    fn as_raw_fd(&self) -> RawFd { 24 }
}
impl Read for SyntheticStdout {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        assert_eq!(bytes.len(), 34, "one fixed read consumes at most 17 response-body bytes");
        self.reads += 1;
        assert_eq!(self.reads, 1, "partial/error reads are never retried");
        match self.result {
            Ok(n) => { bytes[..n].copy_from_slice(&self.payload[..n]); Ok(n) },
            Err(kind) => Err(io::Error::from(kind)),
        }
    }
}
ACTUAL_READER
fn case(poll_result: i32, events: i16, read_result: Result<usize, io::ErrorKind>,
        payload: [u8; 34], expected: &str, reads: usize) -> usize {
    POLL.with(|cell| *cell.borrow_mut() = PollState { result: poll_result, events, calls: 0 });
    let mut reader = SyntheticStdout { result: read_result, payload, reads: 0 };
    assert_eq!(request_marker_at_failure(Some(&mut reader)), expected);
    assert_eq!(reader.reads, reads);
    POLL.with(|cell| assert_eq!(cell.borrow().calls, 1));
    1
}
fn padded(prefix: &[u8]) -> [u8; 34] {
    let mut payload = [0; 34];
    payload[..prefix.len()].copy_from_slice(prefix);
    payload
}
fn request_token(token: &[u8]) -> [u8; 34] {
    assert_eq!(token.len(), 9);
    let mut payload = padded(b"REQUEST\nRESPONSE_REFUSED ");
    payload[25..].copy_from_slice(token);
    payload
}
fn reject_token(token: &[u8]) -> usize {
    assert_eq!(support::agent_receive_error_label(token), None);
    1
}
mod lifecycle {
    use super::{hepta_agent_transport::TransportError, support};
    use std::cell::RefCell;
    use std::io;
    #[derive(Default)]
    struct Trace { events: Vec<&'static str>, prints: Vec<String>, refuse_decode: bool }
    thread_local! { static TRACE: RefCell<Trace> = RefCell::new(Trace::default()); }
    fn event(value: &'static str) { TRACE.with(|t| t.borrow_mut().events.push(value)); }
    fn emit(args: std::fmt::Arguments<'_>) {
        let line = format!("{args}\n");
        TRACE.with(|t| { let mut t = t.borrow_mut(); t.events.push("print"); t.prints.push(line); });
    }
    // The actual receive branch still calls println exactly once. This local
    // macro records that operation, without changing its formatting contract.
    macro_rules! println { ($($arg:tt)*) => { emit(format_args!($($arg)*)) }; }
    pub struct SecretIo;
    impl std::fmt::Debug for SecretIo {
        fn fmt(&self, _: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            panic!("an I/O error's raw debug data was inspected")
        }
    }
    impl std::fmt::Display for SecretIo {
        fn fmt(&self, _: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            panic!("an I/O error's raw message was inspected")
        }
    }
    impl std::error::Error for SecretIo {}
    impl Drop for SecretIo { fn drop(&mut self) { event("drop-error"); } }
    struct Bytes(Vec<u8>);
    impl std::ops::Deref for Bytes {
        type Target = [u8];
        fn deref(&self) -> &[u8] { &self.0 }
    }
    impl Drop for Bytes { fn drop(&mut self) { event("drop-bytes"); } }
    struct Client { result: Option<Result<Bytes, TransportError>> }
    const WAIT: u8 = 7;
    impl Client {
        fn receive_response(&mut self, sequence: u64, wait: u8) -> Result<Bytes, TransportError> {
            assert_eq!((sequence, wait), (41, WAIT));
            event("receive");
            self.result.take().expect("receive must run exactly once")
        }
    }
    fn decode_response(bytes: &[u8]) -> Result<(), ()> {
        assert_eq!(bytes, b"{}");
        event("decode");
        if TRACE.with(|t| t.borrow().refuse_decode) { Err(()) } else { Ok(()) }
    }
    fn agent_receive_error_token(error: &TransportError) -> &'static str { support::classify(error) }
    fn original(client: &mut Client) {
        let sequence = 41;
ORIGINAL_HANDLING
    }
    fn candidate(client: &mut Client) {
        let sequence = 41;
ACTUAL_HANDLING
    }
    fn run(new: bool, success: bool, refuse_decode: bool) -> (Vec<&'static str>, Vec<String>) {
        TRACE.with(|t| *t.borrow_mut() = Trace { refuse_decode, ..Trace::default() });
        let result = if success { Ok(Bytes(b"{}".to_vec())) }
            else { Err(TransportError::Io(io::Error::new(io::ErrorKind::Other, SecretIo))) };
        let mut client = Client { result: Some(result) };
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            if new { candidate(&mut client); } else { original(&mut client); }
            event("after");
        }));
        assert_eq!(result.is_err(), refuse_decode);
        assert!(client.result.is_none());
        TRACE.with(|t| { let t = t.borrow(); (t.events.clone(), t.prints.clone()) })
    }
    pub fn refusal_line(error: TransportError) -> String {
        TRACE.with(|t| *t.borrow_mut() = Trace::default());
        let mut client = Client { result: Some(Err(error)) };
        candidate(&mut client);
        event("after");
        assert!(client.result.is_none());
        TRACE.with(|t| {
            let mut t = t.borrow_mut();
            assert_eq!(t.events, vec!["receive", "print", "after"]);
            assert_eq!(t.prints.len(), 1);
            t.prints.pop().unwrap()
        })
    }
    pub fn check() -> usize {
        let mut cases = 0;
        for (success, refuse_decode, expected_events) in [
            (false, false, vec!["receive", "drop-error", "print", "after"]),
            (true, false, vec!["receive", "decode", "print", "drop-bytes", "after"]),
            (true, true, vec!["receive", "decode", "drop-bytes"]),
        ] {
            let (old_events, old_prints) = run(false, success, refuse_decode);
            let (new_events, new_prints) = run(true, success, refuse_decode);
            assert_eq!(old_events, expected_events, "original Rust 2024 baseline");
            assert_eq!(new_events, old_events, "result handling and destructor order");
            assert_eq!(new_events.iter().filter(|e| **e == "receive").count(), 1);
            assert_eq!(new_events.iter().filter(|e| **e == "print").count(), usize::from(!refuse_decode));
            if success {
                assert_eq!(new_prints, old_prints);
                assert_eq!(new_prints, if refuse_decode { vec![] } else { vec!["RESPONSE {}\n".to_owned()] });
            } else {
                assert_eq!(old_prints, vec!["RESPONSE_REFUSED\n"]);
                assert_eq!(new_prints, vec!["RESPONSE_REFUSED RXIOOTHR_\n"]);
            }
            cases += 1;
        }
        cases
    }
}
fn main() {
    // These are all original 54 controls, counted only after execution.
    let mut legacy = 0;
    assert_eq!(request_marker_at_failure(None), "unknown");
    POLL.with(|cell| assert_eq!(cell.borrow().calls, 0));
    legacy += 1;
    let mut marker = [0_u8; 34];
    marker[..8].copy_from_slice(b"REQUEST\n");
    let response = padded(b"REQUEST\nRESPONSE ");
    let receive_error = padded(b"REQUEST\nRESPONSE_");
    for (result, events) in [(-1, 0), (0, 0), (2, libc::POLLIN), (1, 0), (1, libc::POLLHUP), (1, 32)] {
        legacy += case(result, events, Ok(17), marker, "unknown", 0);
    }
    for payload in [response, receive_error] {
        for bytes in 0..17 {
            let expected = if bytes == 8 { "request-observed" } else { "unknown" };
            legacy += case(1, libc::POLLIN, Ok(bytes), payload, expected, 1);
        }
    }
    for kind in [io::ErrorKind::WouldBlock, io::ErrorKind::Interrupted, io::ErrorKind::Other] {
        legacy += case(1, libc::POLLIN, Err(kind), marker, "unknown", 1);
    }
    legacy += case(1, libc::POLLIN, Ok(8), [b'X'; 34], "unknown", 1);
    legacy += case(1, libc::POLLIN, Ok(17), marker, "unknown", 1);
    legacy += case(1, libc::POLLIN, Ok(8), marker, "request-observed", 1);
    legacy += case(1, libc::POLLIN, Ok(17), response, "response-envelope-observed", 1);
    legacy += case(1, libc::POLLIN, Ok(17), receive_error, "agent-receive-error", 1);
    legacy += case(1, libc::POLLIN | libc::POLLHUP, Ok(8), marker, "request-observed", 1);
    legacy += case(1, libc::POLLIN | libc::POLLHUP, Ok(17), response, "response-envelope-observed", 1);
    legacy += case(1, libc::POLLIN | libc::POLLHUP, Ok(17), receive_error, "agent-receive-error", 1);
    // Assertion formatting remains lazy on the original successful branch.
    POLL.with(|cell| *cell.borrow_mut() = PollState { result: 1, events: libc::POLLIN, calls: 0 });
    let mut reader = SyntheticStdout { result: Ok(8), payload: marker, reads: 0 };
    assert!(true, "original deadline failure: {}", request_marker_at_failure(Some(&mut reader)));
    assert_eq!(reader.reads, 0);
    POLL.with(|cell| assert_eq!(cell.borrow().calls, 0));
    legacy += 1;
    // Diagnostics cannot replace the original failed assertion.
    let failure = std::panic::catch_unwind(|| {
        assert!(false, "original deadline failure: {}", request_marker_at_failure(None));
    }).expect_err("the original assertion must still fail");
    assert_eq!(failure.downcast_ref::<String>().unwrap(), "original deadline failure: unknown");
    legacy += 1;
    use hepta_agent_transport::TransportError;
    let expected = vec![
EXPECTED_VECTORS
    ];
    let mut variants = HashSet::new();
    let mut tokens = HashSet::new();
    let mut labels = HashSet::new();
    let expected_count = expected.len();
    let pairs: HashSet<_> = expected.iter().map(|(_, _, token, label)| (*token, *label)).collect();
    let mut producer = 0;
    let mut reader_cases = 0;
    let mut cancel_positive = 0;
    let mut decoder_negative = 0;
    for (error, variant, token, label) in expected {
        variants.insert(variant);
        assert_eq!(token.len(), 9);
        assert!(token.is_ascii());
        assert!(tokens.insert(token), "independent expected tokens are unique");
        assert!(labels.insert(label), "classes remain distinct");
        assert_eq!(support::classify(&error), token);
        assert_eq!(support::agent_receive_error_label(token.as_bytes()), Some(label));
        // Execute the actual Agent receive branch for every constructor, then
        // feed that exact emitted line into the two real consumer expressions.
        let line = lifecycle::refusal_line(error);
        assert_eq!(line, format!("RESPONSE_REFUSED {token}\n"));
        let complete_line = line.strip_suffix('\n').unwrap();
        producer += 1;
        assert!(consumer_accepts(complete_line, true));
        assert!(!consumer_accepts(complete_line, false));
        cancel_positive += 1;
        let mut payload = padded(b"REQUEST\n");
        payload[8..].copy_from_slice(complete_line.as_bytes());
        assert_eq!(payload, request_token(token.as_bytes()));
        for events in [libc::POLLIN, libc::POLLIN | libc::POLLHUP] {
            reader_cases += case(1, events, Ok(34), payload, label, 1);
            // Exactly 8 keeps REQUEST; exactly 17 keeps legacy RESPONSE_.
            // Every incomplete category length, including 18..33, is unknown.
            for bytes in 0..34 {
                let expected = match bytes {
                    8 => "request-observed",
                    17 => "agent-receive-error",
                    _ => "unknown",
                };
                reader_cases += case(1, events, Ok(bytes), payload, expected, 1);
            }
        }
        // The finite diagnostic decoder is strict. The unchanged cancellation
        // consumer deliberately retains its older starts_with contract below.
        for length in 0..token.len() {
            decoder_negative += reject_token(&token.as_bytes()[..length]);
        }
        for suffix in [b' ', b'\n', 0, b'X'] {
            let mut extended = token.as_bytes().to_vec();
            extended.push(suffix);
            decoder_negative += reject_token(&extended);
        }
        for prefix in [b'X', b' '] {
            let mut extended = vec![prefix];
            extended.extend_from_slice(token.as_bytes());
            decoder_negative += reject_token(&extended);
        }
        for position in 0..token.len() {
            let mut malformed = token.as_bytes().to_vec();
            malformed[position] = b'?';
            decoder_negative += reject_token(&malformed);
            reader_cases += case(1, libc::POLLIN, Ok(34), request_token(&malformed), "unknown", 1);
        }
        for position in [0, 24] {
            let mut wrong_prefix = payload;
            wrong_prefix[position] = b'X';
            reader_cases += case(1, libc::POLLIN, Ok(34), wrong_prefix, "unknown", 1);
        }
    }
    assert_eq!(support::table().len(), expected_count);
    let table: HashSet<_> = support::table().iter().copied().collect();
    assert_eq!(table, pairs, "table agrees with independent requirements");
    for invalid in ["", "REQUEST", "REQUEST\n", "unknown", "arbitrary text", "RESPONSE ",
        "RESPONSE {}", "RESPONSE_", "RESPONSE_REFUSED", "rxplat___", "RXUNKNOWN", " RXPLAT___"] {
        decoder_negative += reject_token(invalid.as_bytes());
    }
    // Successful response bodies are never decoded or returned by the marker.
    // Exercise every read length with arbitrary, even non-UTF-8, fixed tails.
    for tail in [[0; 17], [0xff; 17], *b"private-value-123"] {
        let mut payload = padded(b"REQUEST\nRESPONSE ");
        payload[17..].copy_from_slice(&tail);
        for events in [libc::POLLIN, libc::POLLIN | libc::POLLHUP] {
            for bytes in 0..=34 {
                reader_cases += case(1, events, Ok(bytes), payload,
                    if bytes == 8 { "request-observed" }
                    else if bytes >= 17 { "response-envelope-observed" }
                    else { "unknown" }, 1);
            }
        }
    }
    let mut consumer_controls = 0;
    for suffix in [COMPATIBLE_SUFFIXES] {
        assert!(consumer_accepts(&format!("RESPONSE_REFUSED{suffix}"), true));
        consumer_controls += 1;
    }
    for invalid in [CANCEL_INVALID] {
        assert!(!consumer_accepts(invalid, true));
        consumer_controls += 1;
    }
    assert!(consumer_accepts("RESPONSE {}", false));
    consumer_controls += 1;
    let mut privacy = 0;
    for (error, token) in [
BOUNDARY_VECTORS
    ] {
        assert_eq!(support::classify(&error), token);
        privacy += 1;
    }
    let io_secrets = [
IO_SECRET_VECTORS
    ];
    for (kind, token) in io_secrets {
        let error = TransportError::Io(io::Error::new(kind, lifecycle::SecretIo));
        assert_eq!(support::classify(&error), token);
        drop(error); // Debug and Display would panic before reaching this drop.
        privacy += 1;
    }
    assert_eq!(support::agent_receive_error_label(&[0xff; 9]), None);
    privacy += 1;
    let lifecycle = lifecycle::check();
    println!("PURE_REQUEST_MARKER_CONTROLS legacy={} producer={} reader={} cancel_positive={} decoder_negative={} consumer_controls={} lifecycle={} privacy={} outer={} io_classes={}; no kernel/peer/native claim",
        legacy, producer, reader_cases, cancel_positive, decoder_negative, consumer_controls, lifecycle, privacy, variants.len(), io_secrets.len());
}
"""
        replacements = {
            'ACTUAL_ENUM': enum, 'ACTUAL_HELPERS': helpers, 'ACTUAL_READER': fragment,
            'ACTUAL_CONSUMER': consumer.group(1).replace('trio.agent.line()', 'response', 1), 'ACTUAL_HANDLING': handling,
            'COMPATIBLE_SUFFIXES': ', '.join(json.dumps(value) for value in compatible_suffixes),
            'CANCEL_INVALID': ', '.join(json.dumps(value) for value in cancel_invalid),
            'ORIGINAL_HANDLING': original_handling,
            'EXPECTED_VECTORS': '\n'.join(
                f'        (TransportError::{constructor}, "{variant}", "{token}", "{label}"),'
                for variant, constructor, token, label in expected),
            'BOUNDARY_VECTORS': '\n'.join(
                f'        (TransportError::{constructor}, "{token}"),' for constructor, token in boundaries),
            'IO_SECRET_VECTORS': '\n'.join(
                f'        (io::ErrorKind::{kind}, "{token}"),' for kind, token, _ in io_classes),
        }
        for marker, value in replacements.items():
            self.assertEqual(skeleton.count(marker), 1, marker)
            skeleton = skeleton.replace(marker, value, 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            rust_source = path / 'request_marker.rs'
            binary = path / 'request_marker'
            rust_source.write_text(skeleton)
            compiled = subprocess.run(['rustc', '--edition=2024', str(rust_source), '-o', str(binary)],
                cwd=assembly.ROOT, env=dict(os.environ, RUSTUP_TOOLCHAIN='1.93.0'),
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            summary = re.search(r'^PURE_REQUEST_MARKER_CONTROLS (.*); no kernel/peer/native claim$', executed.stdout, re.M)
            self.assertIsNotNone(summary, executed.stdout)
            counts = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', summary.group(1))}
            self.assertEqual(counts, {
                'legacy': 54,
                'producer': len(expected),
                'reader': len(expected) * (2 * (1 + 34) + 9 + 2) + 3 * 2 * 35,
                'cancel_positive': len(expected),
                'decoder_negative': len(expected) * (9 + 4 + 2 + 9) + 12,
                'consumer_controls': len(compatible_suffixes) + len(cancel_invalid) + 1,
                'lifecycle': 3,
                'privacy': len(boundaries) + len(io_classes) + 1,
                'outer': len(actual_variants),
                'io_classes': len(io_classes),
            })

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
