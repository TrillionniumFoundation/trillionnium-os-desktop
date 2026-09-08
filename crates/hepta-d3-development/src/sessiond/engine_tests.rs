//! Exercise the exact daemon runner with a !Send test backend, not Servo.
use super::*;
use hepta_agent_port::{BrowserRequestHandler, DispatchContext, HandlerOutcome};
use hepta_agent_transport::PeerIdentity;
use hepta_browser_actor::{BrowserActor, MechanismIdentity, PrincipalBinding, TaskFlowPrincipal};
use hepta_browser_actor::{
    BrowserActorMessage, PageOwnerSnapshot, RequestControl, RuntimeFailure, RuntimeReply,
};
use hepta_browser_codec::{BrowserOperation, BrowserRequest, EffectClass, JsonObject};
use std::cell::RefCell;
use std::fs;
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::mpsc;
use std::time::Instant;

const BUDGET: Duration = Duration::from_secs(5);
#[derive(Default)]
struct Trace {
    calls: Vec<thread::ThreadId>,
    dropped: Option<thread::ThreadId>,
}
struct Backend {
    trace: Rc<RefCell<Trace>>,
    failure: bool,
    panics: bool,
}
impl PageRuntime for Backend {
    fn dispatch(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        control.ensure_active()?;
        self.trace.borrow_mut().calls.push(thread::current().id());
        assert!(!self.panics, "test backend panic");
        if self.failure {
            Err(RuntimeFailure::BrowserCrashed)
        } else {
            Ok(RuntimeReply {
                result: JsonObject::new(),
                current_url: None,
            })
        }
    }
}
impl Drop for Backend {
    fn drop(&mut self) {
        self.trace.borrow_mut().dropped = Some(thread::current().id());
    }
}
fn backend() -> (Rc<RefCell<Trace>>, Backend) {
    let trace = Rc::new(RefCell::new(Trace::default()));
    (
        trace.clone(),
        Backend {
            trace,
            failure: false,
            panics: false,
        },
    )
}
struct Capture(Rc<RefCell<Option<RequestControl>>>);
impl PageRuntime for Capture {
    fn dispatch(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        c: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        *self.0.borrow_mut() = Some(c.clone());
        Ok(RuntimeReply {
            result: JsonObject::new(),
            current_url: None,
        })
    }
}
pub(super) fn control() -> RequestControl {
    let slot = Rc::new(RefCell::new(None));
    let peer = PeerIdentity {
        pid: Some(82),
        uid: 1000,
        gid: 1001,
    };
    let binding = PrincipalBinding::bind(
        TaskFlowPrincipal {
            principal_id: "atomic-fixture-tests".into(),
            expected_uid: 1000,
            expected_gid: 1001,
            expected_systemd_unit: "hepta-agent.service".into(),
            expected_cgroup_v2_path: "/system.slice/hepta-agent.service".into(),
            expected_executable_sha256: "1".repeat(64),
        },
        MechanismIdentity {
            peer,
            systemd_unit: "hepta-agent.service".into(),
            cgroup_v2_path: "/system.slice/hepta-agent.service".into(),
            executable_sha256: "1".repeat(64),
        },
    )
    .unwrap();
    let mut actor = BrowserActor::new(binding, Capture(slot.clone()));
    let now = Instant::now();
    let ctx = DispatchContext {
        peer,
        transport_sequence: 1,
        canonical_request_sha256: "2".repeat(64),
        effect_class: EffectClass::Observation,
        accepted_at: now,
        effective_deadline: now + BUDGET,
    };
    let request = BrowserRequest {
        request_id: "capture-control".into(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    assert!(matches!(
        actor.handle(&ctx, &request).unwrap(),
        HandlerOutcome::Success(_)
    ));
    slot.borrow_mut().take().unwrap()
}

fn invoke(runtime: &mut EngineThreadRuntime) -> Result<RuntimeReply, RuntimeFailure> {
    runtime.dispatch(None, BrowserActorMessage::Health, &control())
}
static UNIQUE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
struct SocketDir(PathBuf);
impl SocketDir {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "d3-engine-service-{}-{}",
            std::process::id(),
            UNIQUE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn listener(&self) -> UnixListener {
        let listener = UnixListener::bind(self.0.join("s")).unwrap();
        listener.set_nonblocking(true).unwrap();
        listener
    }
}
impl Drop for SocketDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn runner_keeps_non_send_backend_and_drop_on_calling_thread() {
    let (trace, runtime) = backend();
    let owner = thread::current().id();
    let worker = run_on_owner(runtime, |mut endpoint, stop| {
        stop.ensure_active()?;
        for _ in 0..4 {
            invoke(&mut endpoint).map_err(|_| invalid("unexpected failure"))?;
        }
        Ok(thread::current().id())
    })
    .unwrap();
    assert_ne!(worker, owner);
    assert_eq!(trace.borrow().calls, vec![owner; 4]);
    assert_eq!(trace.borrow().dropped, Some(owner));
}

#[test]
fn worker_early_error_joins_without_a_backend_call() {
    let (trace, runtime) = backend();
    let answer: Result<(), AnyError> =
        run_on_owner(runtime, |_, _| Err(invalid("setup failed").into()));
    assert_eq!(answer.unwrap_err().to_string(), "setup failed");
    assert!(trace.borrow().calls.is_empty());
    assert_eq!(trace.borrow().dropped, Some(thread::current().id()));
}

#[test]
fn worker_panic_is_joined_and_return_value_is_fixed() {
    let (trace, runtime) = backend();
    let answer: Result<(), AnyError> = run_on_owner(runtime, |_, _| panic!("test worker panic"));
    assert_eq!(
        answer.unwrap_err().to_string(),
        "D3 connection worker panicked; service stopped"
    );
    assert!(trace.borrow().calls.is_empty());
    assert_eq!(trace.borrow().dropped, Some(thread::current().id()));
}

#[test]
fn retired_engine_interrupts_idle_accept_without_a_client() {
    let dir = SocketDir::new();
    let listener = dir.listener();
    let (trace, mut runtime) = backend();
    runtime.failure = true;
    let answer: Result<(), AnyError> = run_on_owner(runtime, move |mut endpoint, stop| {
        assert!(invoke(&mut endpoint).is_err());
        accept_next(&listener, stop)?;
        Err(invalid("must not accept after retirement").into())
    });
    assert_eq!(
        answer.unwrap_err().to_string(),
        "D3 engine retired; service must stop"
    );
    assert_eq!(trace.borrow().calls.len(), 1);
}

#[test]
fn backend_panic_retires_acceptor_and_no_second_dispatch_occurs() {
    let dir = SocketDir::new();
    let listener = dir.listener();
    let (trace, mut runtime) = backend();
    runtime.panics = true;
    let answer: Result<(), AnyError> = run_on_owner(runtime, move |mut endpoint, stop| {
        assert!(invoke(&mut endpoint).is_err());
        assert!(invoke(&mut endpoint).is_err());
        accept_next(&listener, stop)?;
        Ok(())
    });
    assert!(answer.is_err());
    assert_eq!(trace.borrow().calls.len(), 1);
}

#[test]
fn dropped_endpoint_wakes_idle_service_retirement() {
    let dir = SocketDir::new();
    let listener = dir.listener();
    let (trace, runtime) = backend();
    let answer: Result<(), AnyError> = run_on_owner(runtime, move |endpoint, stop| {
        drop(endpoint);
        accept_next(&listener, stop)?;
        Ok(())
    });
    assert!(answer.is_err());
    assert!(trace.borrow().calls.is_empty());
}

#[test]
fn stopped_acceptor_does_not_consume_a_queued_connection() {
    let dir = SocketDir::new();
    let listener = dir.listener();
    let _client = UnixStream::connect(dir.0.join("s")).unwrap();
    let stop = ServiceStop::default();
    stop.retire();
    assert!(accept_next(&listener, &stop).is_err());
    assert!(
        listener.accept().is_ok(),
        "a retired acceptor must not drain clients"
    );
    assert!(stop.ensure_active().is_err(), "retirement is permanent");
}

#[test]
fn accepted_stream_retains_blocking_transport_semantics() {
    use std::io::Read;
    let dir = SocketDir::new();
    let listener = dir.listener();
    let _client = UnixStream::connect(dir.0.join("s")).unwrap();
    let mut server = accept_next(&listener, &ServiceStop::default()).unwrap();
    server
        .set_read_timeout(Some(Duration::from_millis(30)))
        .unwrap();
    let started = Instant::now();
    let error = server.read(&mut [0u8; 1]).unwrap_err();
    assert!(matches!(
        error.kind(),
        io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut
    ));
    assert!(
        started.elapsed() >= Duration::from_millis(15),
        "nonblocking fd returned too early"
    );
}

#[test]
fn retirement_wakes_worker_and_runner_joins_before_return() {
    let (trace, runtime) = backend();
    let (done, observed) = mpsc::sync_channel(1);
    run_on_owner(runtime, move |endpoint, stop| {
        drop(endpoint);
        while stop.ensure_active().is_ok() {
            thread::park_timeout(SERVICE_POLL);
        }
        done.send("worker complete").unwrap();
        Ok(())
    })
    .unwrap();
    assert_eq!(observed.try_recv().unwrap(), "worker complete");
    assert!(trace.borrow().dropped.is_some());
}

#[test]
fn deadline_abandonment_retires_actual_service_accept_loop() {
    struct Slow;
    impl PageRuntime for Slow {
        fn dispatch(
            &mut self,
            _: Option<&PageOwnerSnapshot>,
            _: BrowserActorMessage,
            control: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            // Deliberately ignores cooperative cancellation, bounded in this test.
            while Instant::now() <= control.deadline + Duration::from_millis(15) {
                thread::sleep(Duration::from_millis(1));
            }
            Ok(RuntimeReply {
                result: JsonObject::new(),
                current_url: None,
            })
        }
    }
    let dir = SocketDir::new();
    let listener = dir.listener();
    let result: Result<(), AnyError> = run_on_owner(Slow, move |mut endpoint, stop| {
        let mut c = control();
        c.deadline = Instant::now() + Duration::from_millis(50);
        assert!(
            endpoint
                .dispatch(None, BrowserActorMessage::Health, &c)
                .is_err()
        );
        accept_next(&listener, stop)?;
        Ok(())
    });
    assert_eq!(
        result.unwrap_err().to_string(),
        "D3 engine retired; service must stop"
    );
}
