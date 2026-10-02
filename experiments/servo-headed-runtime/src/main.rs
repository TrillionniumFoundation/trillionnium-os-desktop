// D0A-02 headed runtime probe for the exact pinned Servo checkout.
//
// This source is copied into Servo's examples directory by the permanent
// qualification workflow. It creates one native window, draws trusted chrome
// in the embedder-owned parent framebuffer, and composites exactly one Servo
// WebView from an offscreen rendering context below that chrome. It never starts
// WebDriver and its HTTP fixture listens only on 127.0.0.1.

use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::env;
use std::error::Error;
use std::fs;
use std::io::{ErrorKind, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::rc::{Rc, Weak};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use euclid::default::{Point2D, Rect, Size2D};
use glow::HasContext as _;
use servo::{
    CompositionEvent, CompositionState, CreateNewWebViewRequest, DeviceIntPoint, DeviceIntRect,
    DevicePoint, EmbedderControl, EventLoopWaker, ImeEvent, InputEvent, InputEventId,
    InputEventResult, JSValue, Key, KeyState, KeyboardEvent, LoadStatus,
    MouseButton as ServoMouseButton, MouseButtonAction, MouseButtonEvent, MouseMoveEvent, NamedKey,
    NavigationRequest, OffscreenRenderingContext, Opts, RenderingContext, Servo, ServoBuilder,
    ServoDelegate, WebResourceLoad, WebResourceResponse, WebView, WebViewBuilder, WebViewDelegate,
    WheelDelta, WheelEvent, WheelMode, WindowRenderingContext, run_content_process,
};
use url::Url;
use winit::application::ApplicationHandler;
use winit::dpi::{PhysicalPosition, PhysicalSize};
use winit::event::{ElementState, Ime, MouseButton, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop, EventLoopProxy};
use winit::keyboard::{Key as WinitKey, NamedKey as WinitNamedKey};
use winit::raw_window_handle::{HasDisplayHandle, HasWindowHandle};
use winit::window::Window;

mod input_ownership;
use input_ownership::{
    AuxiliaryOwnership, Button, ButtonAction, CheckpointPhase, InputCheckpoint, InputOwnership,
    LaneError, NativeAck, NativeKind, NativeOwner, NativeTicket, OrderedNativeInput,
    PhysicalIngress, QualificationInput, ReleaseOutcome,
};
mod resource_gate;
use resource_gate::{
    Context as ResourceContext, Decision as ResourceDecision, Denial, Observations,
    QUALIFICATION_CSP, Request as ResourceRequest, ResourceGate,
};

const WINDOW_WIDTH: u32 = 1024;
const WINDOW_HEIGHT: u32 = 768;
const CHROME_HEIGHT: u32 = 64;
const CONTENT_HEIGHT: u32 = WINDOW_HEIGHT - CHROME_HEIGHT;
const WINDOW_TITLE: &str = "TrillionniumOS Desktop — trusted chrome — D0A-02";
const FIXTURE_HTML: &str = include_str!("trillionnium_headed_fixture.html");
const NATIVE_INPUT_TIMEOUT_SECONDS: u64 = 150;

fn main() {
    if let Some(token) = content_process_token() {
        run_content_process(token);
        return;
    }

    let exit_code = match run_embedder() {
        Ok(code) => code,
        Err(error) => {
            eprintln!("D0A-02 runtime initialization failed: {error}");
            1
        }
    };
    std::process::exit(exit_code);
}

fn content_process_token() -> Option<String> {
    let mut args = env::args();
    while let Some(arg) = args.next() {
        if arg == "--content-process" {
            return args.next();
        }
    }
    None
}

fn run_embedder() -> Result<i32, Box<dyn Error>> {
    let _ = rustls::crypto::aws_lc_rs::default_provider().install_default();

    let output_dir = env::var_os("HEPTA_D0A02_OUTPUT")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("artifacts/servo-headed-runtime"));
    fs::create_dir_all(&output_dir)?;

    let fixture = FixtureServer::start()?;
    fs::write(output_dir.join("fixture-origin.txt"), fixture.origin())?;

    let event_loop = EventLoop::with_user_event().build()?;
    let mut app = App::new(&event_loop, fixture.url(), output_dir, fixture);
    event_loop.run_app(&mut app)?;
    let exit_code = app.exit_code;
    // The proof has already emitted its bounded result. Servo's synchronous Drop
    // path can wait on an event loop that has stopped, so do not turn successful
    // evidence into a teardown timeout.
    std::mem::forget(app);
    std::process::exit(exit_code)
}

struct FixtureServer {
    address: SocketAddr,
    shutdown: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
    resource_gate: Rc<ResourceGate>,
    network_requests: Arc<AtomicU32>,
}

impl FixtureServer {
    fn start() -> Result<Self, Box<dyn Error>> {
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        listener.set_nonblocking(true)?;
        let address = listener.local_addr()?;
        let resource_gate = Rc::new(ResourceGate::for_owned_fixture(
            &listener,
            FIXTURE_HTML.as_bytes(),
        )?);
        let network_requests = Arc::new(AtomicU32::new(0));
        let observed_requests = network_requests.clone();
        let shutdown = Arc::new(AtomicBool::new(false));
        let thread_shutdown = shutdown.clone();
        let handle = thread::spawn(move || {
            while !thread_shutdown.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut stream, _peer)) => {
                        let _ = observed_requests.fetch_update(
                            Ordering::Relaxed,
                            Ordering::Relaxed,
                            |count| Some(count.saturating_add(1)),
                        );
                        serve_fixture(&mut stream);
                    }
                    Err(error) if error.kind() == ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(10));
                    }
                    Err(error) => {
                        eprintln!("fixture accept failed: {error}");
                        break;
                    }
                }
            }
        });
        Ok(Self {
            address,
            shutdown,
            thread: Some(handle),
            resource_gate,
            network_requests,
        })
    }

    fn origin(&self) -> String {
        format!("http://127.0.0.1:{}", self.address.port())
    }

    fn url(&self) -> Url {
        Url::parse(&format!("{}/", self.origin())).expect("fixed loopback URL is valid")
    }
}

impl Drop for FixtureServer {
    fn drop(&mut self) {
        self.shutdown.store(true, Ordering::Relaxed);
        let _ = TcpStream::connect(self.address);
        if let Some(handle) = self.thread.take() {
            let _ = handle.join();
        }
    }
}

fn serve_fixture(stream: &mut TcpStream) {
    // The listener reserves this real fixture origin. Renderer resources must
    // use the interception path; a network continuation cannot fetch the page.
    let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));
    let _ = stream
        .write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
    let _ = stream.flush();
}

#[derive(Debug)]
enum AppEvent {
    Wake,
    Drive,
    Settled,
    Timeout,
    ContentProcessTerminated { pid: u32, start_time: u64 },
    ContentProcessTerminationFailed(String),
    Exit(i32),
}

#[derive(Clone)]
struct Waker(EventLoopProxy<AppEvent>);

impl Waker {
    fn new(event_loop: &EventLoop<AppEvent>) -> Self {
        Self(event_loop.create_proxy())
    }
}

impl EventLoopWaker for Waker {
    fn clone_box(&self) -> Box<dyn EventLoopWaker> {
        Box::new(self.clone())
    }

    fn wake(&self) {
        if let Err(error) = self.0.send_event(AppEvent::Wake) {
            eprintln!("failed to wake D0A-02 event loop: {error}");
        }
    }
}

struct App {
    waker: Waker,
    proxy: EventLoopProxy<AppEvent>,
    fixture_url: Url,
    output_dir: PathBuf,
    _fixture: FixtureServer,
    state: Option<Rc<RuntimeState>>,
    exit_code: i32,
}

impl App {
    fn new(
        event_loop: &EventLoop<AppEvent>,
        fixture_url: Url,
        output_dir: PathBuf,
        fixture: FixtureServer,
    ) -> Self {
        let proxy = event_loop.create_proxy();
        Self {
            waker: Waker::new(event_loop),
            proxy,
            fixture_url,
            output_dir,
            _fixture: fixture,
            state: None,
            exit_code: 1,
        }
    }
}

impl ApplicationHandler<AppEvent> for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        if self.state.is_some() {
            return;
        }

        let result = RuntimeState::create(
            event_loop,
            self.waker.clone(),
            self.proxy.clone(),
            self.fixture_url.clone(),
            self.output_dir.clone(),
            self._fixture.resource_gate.clone(),
            self._fixture.network_requests.clone(),
        );
        match result {
            Ok(state) => {
                let timeout_proxy = self.proxy.clone();
                thread::spawn(move || {
                    thread::sleep(Duration::from_secs(NATIVE_INPUT_TIMEOUT_SECONDS));
                    let _ = timeout_proxy.send_event(AppEvent::Timeout);
                });
                self.state = Some(state);
            }
            Err(error) => {
                eprintln!("failed to create headed runtime: {error}");
                self.exit_code = 1;
                event_loop.exit();
            }
        }
    }

    fn user_event(&mut self, event_loop: &ActiveEventLoop, event: AppEvent) {
        match event {
            AppEvent::Exit(code) => {
                self.exit_code = code;
                event_loop.exit();
            }
            AppEvent::Timeout => {
                if let Some(state) = &self.state {
                    if !state.completed.get() {
                        state.fail("runtime watchdog expired");
                    }
                }
            }
            AppEvent::ContentProcessTerminated { pid, start_time } => {
                if let Some(state) = &self.state {
                    if state.generation.get() != 1 {
                        return;
                    }
                    if state.fault_process.get() != Some((pid, start_time)) {
                        state.fail("content termination event does not match selected incarnation");
                        return;
                    }
                    state.crash_observed.set(true);
                    state.exact_termination_observed.set(true);
                    state.ingress.borrow_mut().barrier();
                    state.input.borrow_mut().crashed();
                    state.withdraw_native_input();
                    state.retire_withdrawn_gesture();
                    *state.crash_reason.borrow_mut() = Some(format!(
                        "exact content process terminated after SIGKILL: pid={pid}, start_time={start_time}"
                    ));
                    state.window.request_redraw();
                    state.drive();
                }
            }
            AppEvent::ContentProcessTerminationFailed(message) => {
                if let Some(state) = &self.state {
                    state.fail(&message);
                }
            }
            AppEvent::Settled => {
                if let Some(state) = &self.state {
                    state.settled.set(true);
                    state.servo.spin_event_loop();
                    state.drive();
                }
            }
            AppEvent::Wake | AppEvent::Drive => {
                if let Some(state) = &self.state {
                    state.servo.spin_event_loop();
                    state.drive();
                }
            }
        }
    }

    fn window_event(
        &mut self,
        _event_loop: &ActiveEventLoop,
        window_id: winit::window::WindowId,
        event: WindowEvent,
    ) {
        let Some(state) = &self.state else {
            return;
        };
        if window_id != state.window.id() {
            return;
        }
        // OS ingress/withdrawal must precede any old Servo ACK or queue drain.
        match event {
            WindowEvent::CloseRequested => {
                state.ingress.borrow_mut().barrier();
                state.input.borrow_mut().pointer_left();
                state.withdraw_native_input();
                state.fail("window closed before qualification completed");
            }
            WindowEvent::RedrawRequested => state.compose(),
            WindowEvent::CursorMoved { position, .. } => state.forward_pointer_move(position),
            WindowEvent::CursorLeft { .. } => state.pointer_left(),
            WindowEvent::Focused(focused) => {
                let changed = state.ingress.borrow().focused_now() != focused;
                state.ingress.borrow_mut().focused(focused);
                state.input.borrow_mut().focused(focused);
                if changed {
                    state.withdraw_native_input();
                }
                if state.retire_withdrawn_gesture() {
                    return;
                }
                if !focused {
                    let webview = state.webview.borrow().as_ref().cloned();
                    if let Some(webview) = webview {
                        webview.blur();
                    }
                }
            }
            WindowEvent::MouseInput {
                state: button_state,
                button,
                ..
            } => state.forward_mouse_button(button_state, button),
            WindowEvent::MouseWheel { delta, .. } => state.forward_wheel(delta),
            WindowEvent::KeyboardInput { event, .. } => state.forward_keyboard(event),
            WindowEvent::Ime(event) => state.forward_native_ime(event),
            WindowEvent::Resized(new_size) => {
                if new_size.width == WINDOW_WIDTH && new_size.height == WINDOW_HEIGHT {
                    state
                        .window_resize_events
                        .set(state.window_resize_events.get() + 1);
                } else {
                    state.ingress.borrow_mut().barrier();
                    state.input.borrow_mut().pointer_left();
                    state.withdraw_native_input();
                    state.fail("runtime window size changed from the fixed qualification surface");
                }
            }
            _ => {}
        }
        if state.failure.borrow().is_none() {
            state.servo.spin_event_loop();
        }
        let _ = state.proxy.send_event(AppEvent::Drive);
    }

    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        if let Some(state) = &self.state {
            state.servo.spin_event_loop();
            state.drive();
            let deadline = state.native_lane.borrow().deadline();
            event_loop.set_control_flow(deadline.map_or(ControlFlow::Wait, ControlFlow::WaitUntil));
        }
    }
}

struct NativePayload {
    event: Option<InputEvent>,
    local_ime: Option<bool>,
    key_transition: Option<(String, bool)>,
}

struct RuntimeState {
    webview: RefCell<Option<WebView>>,
    servo: Servo,
    content_context: Rc<OffscreenRenderingContext>,
    parent_context: Rc<WindowRenderingContext>,
    // The native window must outlive both rendering contexts.
    window: Window,
    proxy: EventLoopProxy<AppEvent>,
    fixture_url: Url,
    resource_gate: Rc<ResourceGate>,
    resource_observations: Rc<RefCell<Observations>>,
    fixture_network_requests: Arc<AtomicU32>,
    output_dir: PathBuf,

    generation: Cell<u32>,
    load_complete: Cell<bool>,
    frame_ready: Cell<u32>,
    content_screenshot_requested: Cell<bool>,
    content_screenshot_saved: Cell<bool>,
    workspace_screenshot_saved: Cell<bool>,
    focus_requested: Cell<bool>,
    focus_ready: Cell<bool>,
    input_marker_written: Cell<bool>,
    native_pointer_events: Cell<u32>,
    native_button_events: Cell<u32>,
    native_wheel_events: Cell<u32>,
    native_keyboard_events: Cell<u32>,
    native_ime_events: Cell<u32>,
    input_handled_callbacks: Cell<u32>,
    synthetic_ime_sent: Cell<bool>,
    settled: Cell<bool>,
    page_evidence_requested: Cell<bool>,
    initial_page_evidence: RefCell<Option<String>>,
    recovery_page_evidence: RefCell<Option<String>>,
    popup_denied: Cell<u32>,
    navigation_denied: Cell<u32>,
    input_method_controls: Cell<u32>,
    crash_triggered: Cell<bool>,
    crash_observed: Cell<bool>,
    crash_reason: RefCell<Option<String>>,
    crash_workspace_saved: Cell<bool>,
    recovery_started: Cell<bool>,
    chrome_initial_ok: Cell<bool>,
    chrome_crash_ok: Cell<bool>,
    chrome_recovery_ok: Cell<bool>,
    window_resize_events: Cell<u32>,
    failure: RefCell<Option<String>>,
    completed: Cell<bool>,
    input: RefCell<InputOwnership>,
    ingress: RefCell<PhysicalIngress>,
    native_lane: RefCell<OrderedNativeInput<InputEventId, NativePayload>>,
    native_trace: RefCell<Vec<serde_json::Value>>,
    auxiliary: RefCell<AuxiliaryOwnership<InputEventId>>,
    pending_mouse_releases: RefCell<HashMap<InputEventId, Button>>,
    fault_process: Cell<Option<(u32, u64)>>,
    exact_termination_observed: Cell<bool>,
    qualification_nonce: Option<String>,
    qualification_owner_start: u64,
    qualification_input: RefCell<Option<QualificationInput<InputEventId>>>,
}

impl RuntimeState {
    fn create(
        event_loop: &ActiveEventLoop,
        waker: Waker,
        proxy: EventLoopProxy<AppEvent>,
        fixture_url: Url,
        output_dir: PathBuf,
        resource_gate: Rc<ResourceGate>,
        fixture_network_requests: Arc<AtomicU32>,
    ) -> Result<Rc<Self>, Box<dyn Error>> {
        // Only explicit host qualification enables these checkpoints.
        let qualification_nonce = match env::var("HEPTA_D0A02_INPUT_NONCE") {
            Ok(nonce)
                if nonce.len() == 32
                    && nonce
                        .bytes()
                        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) =>
            {
                if fs::metadata(&output_dir)?.permissions().mode() & 0o777 != 0o700 {
                    return Err("qualification output directory must be private (0700)".into());
                }
                Some(nonce)
            }
            Ok(_) => return Err("qualification input nonce must be 32 lowercase hex digits".into()),
            Err(env::VarError::NotPresent) => None,
            Err(error) => return Err(error.into()),
        };
        let qualification_input = qualification_nonce
            .as_ref()
            .map(|_| QualificationInput::new());
        let qualification_owner_start = exact_content_process_start_time(std::process::id())?;
        let display_handle = event_loop.display_handle()?;
        let attributes = Window::default_attributes()
            .with_title(WINDOW_TITLE)
            .with_inner_size(PhysicalSize::new(WINDOW_WIDTH, WINDOW_HEIGHT))
            .with_resizable(false)
            .with_visible(true);
        let window = event_loop.create_window(attributes)?;
        let window_handle = window.window_handle()?;
        let parent_context = Rc::new(
            WindowRenderingContext::new(
                display_handle,
                window_handle,
                PhysicalSize::new(WINDOW_WIDTH, WINDOW_HEIGHT),
            )
            .map_err(|error| {
                std::io::Error::other(format!("WindowRenderingContext::new failed: {error:?}"))
            })?,
        );
        parent_context.make_current().map_err(|error| {
            std::io::Error::other(format!(
                "WindowRenderingContext::make_current failed: {error:?}"
            ))
        })?;
        let content_context = Rc::new(
            parent_context.offscreen_context(PhysicalSize::new(WINDOW_WIDTH, CONTENT_HEIGHT)),
        );

        let profile = output_dir.join("servo-profile");
        fs::create_dir_all(&profile)?;
        let mut opts = Opts::default();
        opts.multiprocess = true;
        opts.hard_fail = false;
        opts.sandbox = false;
        opts.temporary_storage = true;
        opts.config_dir = Some(profile);
        let servo = ServoBuilder::default()
            .opts(opts)
            .event_loop_waker(Box::new(waker))
            .build();
        let resource_observations = Rc::new(RefCell::new(Observations::default()));
        // The exact pin installs its default delegate during build. Replace it
        // before any WebView or event-loop spin can publish an HTTP request.
        servo.set_delegate(Rc::new(GlobalResourceDelegate {
            observations: resource_observations.clone(),
        }));
        servo.setup_logging();

        let state = Rc::new(Self {
            window,
            servo,
            parent_context,
            content_context,
            webview: RefCell::new(None),
            proxy,
            fixture_url,
            resource_gate,
            resource_observations,
            fixture_network_requests,
            output_dir,
            generation: Cell::new(1),
            load_complete: Cell::new(false),
            frame_ready: Cell::new(0),
            content_screenshot_requested: Cell::new(false),
            content_screenshot_saved: Cell::new(false),
            workspace_screenshot_saved: Cell::new(false),
            focus_requested: Cell::new(false),
            focus_ready: Cell::new(false),
            input_marker_written: Cell::new(false),
            native_pointer_events: Cell::new(0),
            native_button_events: Cell::new(0),
            native_wheel_events: Cell::new(0),
            native_keyboard_events: Cell::new(0),
            native_ime_events: Cell::new(0),
            input_handled_callbacks: Cell::new(0),
            synthetic_ime_sent: Cell::new(false),
            settled: Cell::new(false),
            page_evidence_requested: Cell::new(false),
            initial_page_evidence: RefCell::new(None),
            recovery_page_evidence: RefCell::new(None),
            popup_denied: Cell::new(0),
            navigation_denied: Cell::new(0),
            input_method_controls: Cell::new(0),
            crash_triggered: Cell::new(false),
            crash_observed: Cell::new(false),
            crash_reason: RefCell::new(None),
            crash_workspace_saved: Cell::new(false),
            recovery_started: Cell::new(false),
            chrome_initial_ok: Cell::new(false),
            chrome_crash_ok: Cell::new(false),
            chrome_recovery_ok: Cell::new(false),
            window_resize_events: Cell::new(0),
            failure: RefCell::new(None),
            completed: Cell::new(false),
            input: RefCell::new(InputOwnership::new(
                WINDOW_WIDTH,
                WINDOW_HEIGHT,
                CHROME_HEIGHT,
            )),
            ingress: RefCell::new(PhysicalIngress::new(
                WINDOW_WIDTH,
                WINDOW_HEIGHT,
                CHROME_HEIGHT,
            )),
            native_lane: RefCell::new(OrderedNativeInput::new()),
            native_trace: RefCell::new(Vec::new()),
            auxiliary: RefCell::new(AuxiliaryOwnership::new()),
            pending_mouse_releases: RefCell::new(HashMap::new()),
            fault_process: Cell::new(None),
            exact_termination_observed: Cell::new(false),
            qualification_nonce,
            qualification_owner_start,
            qualification_input: RefCell::new(qualification_input),
        });
        state.create_webview();
        fs::write(state.output_dir.join("window-created"), WINDOW_TITLE)?;
        state.window.request_redraw();
        Ok(state)
    }

    fn create_webview(self: &Rc<Self>) {
        let generation = self.generation.get();
        let mut url = self.fixture_url.clone();
        url.set_query(Some(&format!("generation={generation}")));
        let delegate = Rc::new(RuntimeDelegate {
            state: Rc::downgrade(self),
            generation,
            resource_gate: self.resource_gate.clone(),
            observations: self.resource_observations.clone(),
        });
        let webview = WebViewBuilder::new(&self.servo, self.content_context.clone())
            .url(url)
            .delegate(delegate)
            .build();
        webview.focus();
        *self.webview.borrow_mut() = Some(webview);
    }

    fn fixture_origin_matches(&self, url: &Url) -> bool {
        url.scheme() == self.fixture_url.scheme()
            && url.host_str() == self.fixture_url.host_str()
            && url.port_or_known_default() == self.fixture_url.port_or_known_default()
    }

    fn drive(self: &Rc<Self>) {
        if self.completed.get() {
            return;
        }
        let time_check = self.native_lane.borrow_mut().check(Instant::now());
        if let Err(error) = time_check {
            self.refuse_native_input(error);
        }
        if self.resource_observations.borrow().exceeded_bound
            || self.fixture_network_requests.load(Ordering::Relaxed) != 0
        {
            self.fail("resource callback bound or fixture network continuation violated");
        }
        if self.failure.borrow().is_some() {
            self.finish_failure();
            return;
        }
        self.drain_native_input();
        if self.failure.borrow().is_some() {
            self.finish_failure();
            return;
        }
        if self.crash_observed.get() && !self.exact_termination_observed.get() {
            return;
        }

        if self.crash_observed.get()
            && !self.crash_workspace_saved.get()
            && !self.recovery_started.get()
        {
            self.window.request_redraw();
            return;
        }
        if self.crash_workspace_saved.get() && !self.recovery_started.get() {
            self.start_recovery();
            return;
        }

        if self.load_complete.get() && self.frame_ready.get() > 0 {
            if !self.content_screenshot_requested.get() {
                self.request_content_screenshot();
                return;
            }
            if self.content_screenshot_saved.get() && !self.workspace_screenshot_saved.get() {
                self.window.request_redraw();
                return;
            }
        }

        if self.generation.get() == 1
            && self.workspace_screenshot_saved.get()
            && !self.focus_requested.get()
        {
            self.request_focus();
            return;
        }
        if self.generation.get() == 1 && self.focus_ready.get() && !self.input_marker_written.get()
        {
            if let Err(error) = fs::write(self.output_dir.join("input-ready"), "ready\n") {
                self.fail(&format!("could not write input-ready marker: {error}"));
                return;
            }
            self.input_marker_written.set(true);
        }

        if self.generation.get() == 1
            && self.qualification_input_complete()
            && self.native_lane.borrow().idle()
            && self.native_pointer_events.get() > 0
            && self.native_button_events.get() >= 2
            && self.native_wheel_events.get() > 0
            && self.native_keyboard_events.get() >= 2
            && !self.auxiliary.borrow().unsettled()
            && !self.synthetic_ime_sent.get()
        {
            self.send_synthetic_ime();
            return;
        }

        if self.generation.get() == 1
            && self.qualification_input_complete()
            && self.native_lane.borrow().idle()
            && self.synthetic_ime_sent.get()
            && self.settled.get()
            && !self.page_evidence_requested.get()
        {
            self.request_page_evidence();
            return;
        }

        if self.generation.get() == 1
            && self.initial_page_evidence.borrow().is_some()
            && self.native_lane.borrow().idle()
            && !self.auxiliary.borrow().unsettled()
            && self.popup_denied.get() > 0
            && self.navigation_denied.get() > 0
            && self.input_method_controls.get() > 0
            && !self.crash_triggered.get()
        {
            self.trigger_content_crash();
            return;
        }

        if self.generation.get() == 2
            && self.workspace_screenshot_saved.get()
            && self.native_lane.borrow().idle()
            && !self.page_evidence_requested.get()
        {
            self.request_page_evidence();
            return;
        }
        if self.generation.get() == 2
            && self.native_lane.borrow().idle()
            && self.recovery_page_evidence.borrow().is_some()
        {
            self.finish_success();
        }
    }

    fn request_content_screenshot(self: &Rc<Self>) {
        self.content_screenshot_requested.set(true);
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("missing WebView while requesting screenshot");
            return;
        };
        let generation = self.generation.get();
        let state = self.clone();
        webview.take_screenshot(None, move |result| {
            if !state.input.borrow().current_callback(generation) {
                return;
            }
            match result {
                Ok(image) => {
                    let path = state
                        .output_dir
                        .join(format!("content-generation-{generation}.png"));
                    if let Err(error) = image.save(&path) {
                        state.fail(&format!("could not save Servo screenshot: {error}"));
                        return;
                    }
                    state.content_screenshot_saved.set(true);
                    let _ = state.proxy.send_event(AppEvent::Drive);
                }
                Err(error) => state.fail(&format!("Servo screenshot failed: {error:?}")),
            }
        });
    }

    fn request_focus(self: &Rc<Self>) {
        self.focus_requested.set(true);
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("missing WebView while focusing fixture input");
            return;
        };
        let state = self.clone();
        let generation = self.generation.get();
        webview.evaluate_javascript(
            "document.getElementById('field').focus(); document.activeElement.id === 'field'",
            move |result| {
                if !state.input.borrow().current_callback(generation) {
                    return;
                }
                match result {
                    Ok(JSValue::Boolean(true)) => {
                        state.focus_ready.set(true);
                        let _ = state.proxy.send_event(AppEvent::Drive);
                    }
                    other => state.fail(&format!("fixture input focus failed: {other:?}")),
                }
            },
        );
    }

    fn send_synthetic_ime(self: &Rc<Self>) {
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("missing WebView while delivering IME composition");
            return;
        };
        let events = [
            CompositionEvent {
                state: CompositionState::Start,
                data: String::new(),
            },
            CompositionEvent {
                state: CompositionState::Update,
                data: "hepta".to_owned(),
            },
            CompositionEvent {
                state: CompositionState::End,
                data: "hepta".to_owned(),
            },
        ];
        drop(webview);
        let events = events
            .into_iter()
            .map(|event| {
                let bytes = event.data.len() + 32;
                (
                    NativeKind::SyntheticIme,
                    None,
                    bytes,
                    NativePayload {
                        event: Some(InputEvent::Ime(ImeEvent::Composition(event))),
                        local_ime: None,
                        key_transition: None,
                    },
                )
            })
            .collect();
        self.enqueue_native(events);
        self.synthetic_ime_sent.set(true);
        self.settled.set(false);
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(800));
            let _ = proxy.send_event(AppEvent::Settled);
        });
    }

    fn request_page_evidence(self: &Rc<Self>) {
        self.page_evidence_requested.set(true);
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("missing WebView while reading fixture evidence");
            return;
        };
        let state = self.clone();
        let generation = self.generation.get();
        webview.evaluate_javascript("JSON.stringify(window.__heptaEvidence)", move |result| {
            if !state.input.borrow().current_callback(generation) {
                return;
            }
            match result {
                Ok(JSValue::String(value)) => {
                    let probes_settled = serde_json::from_str::<serde_json::Value>(&value)
                        .ok()
                        .and_then(|value| value.get("resourceProbesSettled").cloned())
                        == Some(serde_json::Value::Bool(true));
                    if !probes_settled {
                        state.page_evidence_requested.set(false);
                        let proxy = state.proxy.clone();
                        thread::spawn(move || {
                            thread::sleep(Duration::from_millis(100));
                            let _ = proxy.send_event(AppEvent::Drive);
                        });
                        return;
                    }
                    if generation == 1 {
                        *state.initial_page_evidence.borrow_mut() = Some(value);
                    } else {
                        *state.recovery_page_evidence.borrow_mut() = Some(value);
                    }
                    let _ = state.proxy.send_event(AppEvent::Drive);
                }
                other => state.fail(&format!("fixture evidence evaluation failed: {other:?}")),
            }
        });
    }

    fn trigger_content_crash(self: &Rc<Self>) {
        self.crash_triggered.set(true);
        let content_pid = match exact_content_process_pid() {
            Ok(pid) => pid,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        let content_start_time = match exact_content_process_start_time(content_pid) {
            Ok(start_time) => start_time,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        self.fault_process
            .set(Some((content_pid, content_start_time)));
        if let Err(error) = fs::write(
            self.output_dir.join("content-process-identity.json"),
            format!(
                "{{\"generation\":1,\"pid\":{content_pid},\"start_time\":{content_start_time}}}\n"
            ),
        ) {
            self.fail(&format!("could not bind fault incarnation: {error}"));
            return;
        }
        if let Err(error) = fs::write(
            self.output_dir.join("content-process-pid.txt"),
            format!("{content_pid}\n"),
        ) {
            self.fail(&format!(
                "could not record exact content-process pid: {error}"
            ));
            return;
        }
        if let Err(error) = fs::write(self.output_dir.join("content-crash-ready"), "ready\n") {
            self.fail(&format!(
                "could not publish exact content-process crash marker: {error}"
            ));
            return;
        }
        let status = match Command::new("/bin/kill")
            .args(["-KILL", &content_pid.to_string()])
            .status()
        {
            Ok(status) => status,
            Err(error) => {
                self.fail(&format!(
                    "could not execute exact content-process kill: {error}"
                ));
                return;
            }
        };
        if !status.success() {
            self.fail(&format!(
                "exact content-process kill exited with status {status}"
            ));
            return;
        }
        if let Err(error) = fs::write(
            self.output_dir.join("content-sigkill-sent.json"),
            format!(
                "{{\"generation\":1,\"pid\":{content_pid},\"start_time\":{content_start_time},\"signal\":\"SIGKILL\"}}\n"
            ),
        ) {
            self.fail(&format!("could not record requested fault signal: {error}"));
            return;
        }

        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let stat_path = format!("/proc/{content_pid}/stat");
            let deadline = Instant::now() + Duration::from_secs(5);
            loop {
                match fs::read_to_string(&stat_path) {
                    Err(error) if error.kind() == ErrorKind::NotFound => {
                        let _ = proxy.send_event(AppEvent::ContentProcessTerminated {
                            pid: content_pid,
                            start_time: content_start_time,
                        });
                        break;
                    }
                    Err(error) => {
                        let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                            format!("could not observe exact content-process termination: {error}"),
                        ));
                        break;
                    }
                    Ok(stat) => {
                        let observed_start_time = match proc_start_time(&stat) {
                            Some(start_time) => start_time,
                            None => {
                                let _ = proxy.send_event(
                                    AppEvent::ContentProcessTerminationFailed(
                                        "could not parse exact content-process start time while observing termination"
                                            .to_owned(),
                                    ),
                                );
                                break;
                            }
                        };
                        if observed_start_time != content_start_time {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                                format!(
                                    "content-process pid identity changed before an unambiguous exit observation: pid={content_pid}, expected_start_time={content_start_time}, observed_start_time={observed_start_time}"
                                ),
                            ));
                            break;
                        }
                        if proc_state(&stat) == Some('Z') {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminated {
                                pid: content_pid,
                                start_time: content_start_time,
                            });
                            break;
                        }
                        if Instant::now() >= deadline {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                                format!(
                                    "exact content process remained executable after SIGKILL timeout: pid={content_pid}, start_time={content_start_time}"
                                ),
                            ));
                            break;
                        }
                        thread::sleep(Duration::from_millis(10));
                    }
                }
            }
        });
    }

    fn start_recovery(self: &Rc<Self>) {
        self.recovery_started.set(true);
        *self.webview.borrow_mut() = None;
        self.ingress.borrow_mut().barrier();
        self.generation.set(2);
        if !self.input.borrow_mut().reconstruct(2) {
            self.fail("replacement input ownership did not follow a crash");
            return;
        }
        self.load_complete.set(false);
        self.frame_ready.set(0);
        self.content_screenshot_requested.set(false);
        self.content_screenshot_saved.set(false);
        self.workspace_screenshot_saved.set(false);
        self.page_evidence_requested.set(false);
        self.settled.set(false);
        self.create_webview();
        self.window.request_redraw();
    }

    fn compose(self: &Rc<Self>) {
        if self.completed.get() {
            return;
        }
        if let Err(error) = self.parent_context.make_current() {
            self.fail(&format!("could not make parent context current: {error:?}"));
            return;
        }

        if !self.crash_observed.get() || self.recovery_started.get() {
            let webview = self.webview.borrow().as_ref().cloned();
            if let Some(webview) = webview {
                webview.paint();
            }
        }

        self.parent_context.prepare_for_rendering();
        let gl = self.parent_context.glow_gl_api();
        unsafe {
            gl.disable(glow::SCISSOR_TEST);
            gl.clear_color(0.055, 0.063, 0.082, 1.0);
            gl.clear(glow::COLOR_BUFFER_BIT);
        }

        if self.crash_observed.get() && !self.recovery_started.get() {
            clear_rect(
                &gl,
                0,
                0,
                WINDOW_WIDTH as i32,
                CONTENT_HEIGHT as i32,
                [0.24, 0.06, 0.08, 1.0],
            );
        } else if let Some(blit) = self.content_context.render_to_parent_callback() {
            blit(
                &gl,
                Rect::new(
                    Point2D::new(0, 0),
                    Size2D::new(WINDOW_WIDTH as i32, CONTENT_HEIGHT as i32),
                ),
            );
        } else {
            self.fail("offscreen Servo context did not expose a blit callback");
            return;
        }

        clear_rect(
            &gl,
            0,
            CONTENT_HEIGHT as i32,
            WINDOW_WIDTH as i32,
            CHROME_HEIGHT as i32,
            [0.08, 0.18, 0.42, 1.0],
        );
        clear_rect(
            &gl,
            16,
            CONTENT_HEIGHT as i32 + 16,
            28,
            32,
            if self.crash_observed.get() && !self.recovery_started.get() {
                [0.95, 0.36, 0.16, 1.0]
            } else {
                [0.10, 0.72, 0.36, 1.0]
            },
        );

        if self.crash_observed.get()
            && !self.recovery_started.get()
            && !self.crash_workspace_saved.get()
        {
            match self.save_workspace_image("workspace-crash-placeholder.png") {
                Ok(chrome_ok) => {
                    self.chrome_crash_ok.set(chrome_ok);
                    self.crash_workspace_saved.set(true);
                }
                Err(error) => self.fail(&error),
            }
        } else if self.content_screenshot_saved.get() && !self.workspace_screenshot_saved.get() {
            let generation = self.generation.get();
            match self.save_workspace_image(&format!("workspace-generation-{generation}.png")) {
                Ok(chrome_ok) => {
                    if generation == 1 {
                        self.chrome_initial_ok.set(chrome_ok);
                    } else {
                        self.chrome_recovery_ok.set(chrome_ok);
                    }
                    self.workspace_screenshot_saved.set(true);
                }
                Err(error) => self.fail(&error),
            }
        }

        self.parent_context.present();
        let _ = self.proxy.send_event(AppEvent::Drive);
    }

    fn save_workspace_image(&self, name: &str) -> Result<bool, String> {
        let rect = DeviceIntRect::new(
            DeviceIntPoint::new(0, 0),
            DeviceIntPoint::new(WINDOW_WIDTH as i32, WINDOW_HEIGHT as i32),
        );
        let image = self
            .parent_context
            .read_to_image(rect)
            .ok_or_else(|| "could not read composed parent framebuffer".to_owned())?;
        let chrome = image.get_pixel(8, 8).0;
        let content = image.get_pixel(8, CHROME_HEIGHT + 24).0;
        let chrome_ok =
            chrome[2] > 70 && chrome[2] > chrome[0] && chrome[2] > chrome[1] && chrome != content;
        image
            .save(self.output_dir.join(name))
            .map_err(|error| format!("could not save composed workspace image: {error}"))?;
        Ok(chrome_ok)
    }

    fn forward_pointer_move(&self, position: PhysicalPosition<f64>) {
        let point = self.ingress.borrow_mut().pointer(position.x, position.y);
        let Some((x, y)) = point else {
            self.input.borrow_mut().pointer(position.x, position.y);
            self.input.borrow_mut().pressed();
            self.withdraw_native_input();
            self.pointer_left();
            if position.x == 10.0 && position.y == 10.0 {
                let checkpoint = self
                    .qualification_input
                    .borrow_mut()
                    .as_mut()
                    .and_then(|input| {
                        input.observe_chrome(
                            self.generation.get(),
                            self.input.borrow().window_focused(),
                        )
                    });
                if let Some(checkpoint) = checkpoint {
                    self.publish_input_checkpoint(checkpoint);
                }
            }
            return;
        };
        self.enqueue_native(vec![(
            NativeKind::Move,
            Some((x, y)),
            32,
            NativePayload {
                event: Some(InputEvent::MouseMove(MouseMoveEvent::new(
                    DevicePoint::new(x, y).into(),
                ))),
                local_ime: None,
                key_transition: None,
            },
        )]);
    }

    fn pointer_left(&self) {
        self.ingress.borrow_mut().barrier();
        self.input.borrow_mut().pointer_left();
        self.withdraw_native_input();
        self.retire_withdrawn_gesture();
    }

    fn forward_mouse_button(&self, state: ElementState, button: MouseButton) {
        let (owned_button, button) = match button {
            MouseButton::Left => (Button::Primary, ServoMouseButton::Primary),
            MouseButton::Right => (Button::Secondary, ServoMouseButton::Secondary),
            MouseButton::Middle => (Button::Auxiliary, ServoMouseButton::Auxiliary),
            MouseButton::Back => (Button::Back, ServoMouseButton::Back),
            MouseButton::Forward => (Button::Forward, ServoMouseButton::Forward),
            MouseButton::Other(value) => (Button::Other(value), ServoMouseButton::Other(value)),
        };
        let (owned_action, action) = match state {
            ElementState::Pressed => (ButtonAction::Down, MouseButtonAction::Down),
            ElementState::Released => (ButtonAction::Up, MouseButtonAction::Up),
        };
        let projected = self.ingress.borrow_mut().button(owned_button, owned_action);
        let point = match projected {
            Ok(Some(point)) => point,
            Ok(None) => {
                self.trace_native_refusal("outside_content");
                let webview = self.webview.borrow().as_ref().cloned();
                if let Some(webview) = webview {
                    webview.blur();
                }
                self.input.borrow_mut().pressed();
                return;
            }
            Err(error) => {
                self.refuse_native_input(error);
                return;
            }
        };
        if let Some(input) = self.qualification_input.borrow().as_ref() {
            let ready = owned_button == Button::Primary
                && match owned_action {
                    ButtonAction::Down => input.allows_down(self.generation.get(), Some(point)),
                    ButtonAction::Up => input.allows_up(self.generation.get(), Some(point)),
                };
            if !ready {
                self.fail("native qualification button arrived before its exact checkpoint");
                return;
            }
        }
        let kind = match owned_action {
            ButtonAction::Down => NativeKind::Down(owned_button),
            ButtonAction::Up => NativeKind::Up(owned_button),
        };
        self.enqueue_native(vec![(
            kind,
            Some(point),
            32,
            NativePayload {
                event: Some(InputEvent::MouseButton(MouseButtonEvent::new(
                    action,
                    button,
                    DevicePoint::new(point.0, point.1).into(),
                ))),
                local_ime: None,
                key_transition: None,
            },
        )]);
    }

    fn qualification_input_complete(&self) -> bool {
        self.qualification_input
            .borrow()
            .as_ref()
            .is_none_or(QualificationInput::complete)
    }

    fn publish_input_checkpoint(&self, checkpoint: InputCheckpoint<InputEventId>) {
        let Some(nonce) = &self.qualification_nonce else {
            self.fail("input checkpoint has no qualification session");
            return;
        };
        let phase = checkpoint.phase.as_str();
        let point = checkpoint
            .point
            .map_or_else(|| "null".to_owned(), |(x, y)| format!("[{x},{y}]"));
        let identifier = |event: Option<InputEventId>| {
            event.map_or_else(|| "null".to_owned(), |id| json_string(&format!("{id:?}")))
        };
        let report = format!(
            concat!(
                "{{\"schema\":\"trillionnium.desktop.native-input-checkpoint.v1\",",
                "\"nonce\":{},\"owner_pid\":{},\"owner_start_time\":{},",
                "\"generation\":1,\"sequence\":{},\"phase\":{},\"content_point\":{},",
                "\"pointer_event_id\":{},\"down_event_id\":{},\"up_event_id\":{},",
                "\"pointer_dispatch_accepted\":{},\"down_dispatch_accepted\":{},",
                "\"up_dispatch_accepted\":{},\"completed_pairs\":{},\"product_ready\":false}}\n"
            ),
            json_string(nonce),
            std::process::id(),
            self.qualification_owner_start,
            checkpoint.sequence,
            json_string(phase),
            point,
            identifier(checkpoint.pointer_event),
            identifier(checkpoint.down_event),
            identifier(checkpoint.up_event),
            checkpoint.phase != CheckpointPhase::ChromeReady,
            matches!(
                checkpoint.phase,
                CheckpointPhase::DownAccepted | CheckpointPhase::UpAccepted
            ),
            checkpoint.phase == CheckpointPhase::UpAccepted,
            checkpoint.completed_pairs,
        );
        let name = format!("input-pair-{}-{phase}.json", checkpoint.sequence);
        let temporary = self.output_dir.join(format!(".{name}.{nonce}.tmp"));
        let published = self.output_dir.join(&name);
        let write = || -> std::io::Result<()> {
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(&temporary)?;
            file.write_all(report.as_bytes())?;
            file.sync_all()?;
            if published.symlink_metadata().is_ok() {
                return Err(std::io::Error::other("input checkpoint already exists"));
            }
            fs::rename(&temporary, &published)
        };
        if let Err(error) = write() {
            self.fail(&format!(
                "could not publish exact input checkpoint: {error}"
            ));
        }
    }

    fn retire_withdrawn_gesture(&self) -> bool {
        let Some(outcome) = self.input.borrow_mut().take_withdrawal() else {
            return false;
        };
        if outcome.generation != self.generation.get() {
            self.fail("withdrawn gesture does not match the active native generation");
            return true;
        }
        self.input.borrow_mut().end_ime();
        let _ = self.native_lane.borrow_mut().withdraw();
        self.ingress.borrow_mut().barrier();
        let retired = self.webview.borrow_mut().take();
        self.pending_mouse_releases.borrow_mut().clear();
        let owned_handle_removed = retired.is_some();
        if let Some(webview) = retired {
            webview.blur();
            webview.hide();
            // The pin closes a WebView when its last handle drops. Temporary
            // callback handles can defer that; input and delegates are already
            // latched closed. Servo's global mouse mask has no cancellation API.
            drop(webview);
        }
        self.window
            .set_title("TrillionniumOS Desktop — input recovery required — D0A-02");
        self.window.request_redraw();
        let report = format!(
            concat!(
                "{{\n",
                "  \"schema\": \"trillionnium.desktop.native-gesture-withdrawal.v1\",\n",
                "  \"generation\": {},\n",
                "  \"reason\": {},\n",
                "  \"held_button_count\": {},\n",
                "  \"recovery_required\": true,\n",
                "  \"owned_webview_handle_removed\": {},\n",
                "  \"synthetic_mouse_release_sent\": false,\n",
                "  \"servo_mouse_state_reset_proven\": false,\n",
                "  \"automatic_reconstruction_allowed\": false,\n",
                "  \"product_ready\": false\n",
                "}}\n"
            ),
            outcome.generation,
            json_string(outcome.reason.as_str()),
            outcome.held_buttons,
            owned_handle_removed,
        );
        if fs::write(
            self.output_dir.join("gesture-recovery-required.json"),
            report,
        )
        .is_err()
        {
            self.fail("could not record native held-gesture recovery requirement");
        } else {
            self.fail("native held gesture withdrawn; fresh Servo owner recovery is required");
        }
        true
    }

    fn forward_wheel(&self, delta: MouseScrollDelta) {
        let Some((px, py)) = self.ingress.borrow().point() else {
            self.trace_native_refusal("wheel_outside_content");
            return;
        };
        let (x, y, mode) = match delta {
            MouseScrollDelta::LineDelta(x, y) => (x as f64, y as f64, WheelMode::DeltaLine),
            MouseScrollDelta::PixelDelta(position) => {
                (position.x, position.y, WheelMode::DeltaPixel)
            }
        };
        if !x.is_finite() || !y.is_finite() {
            self.refuse_native_input(LaneError::Payload);
            return;
        }
        self.enqueue_native(vec![(
            NativeKind::Wheel,
            Some((px, py)),
            48,
            NativePayload {
                event: Some(InputEvent::Wheel(WheelEvent::new(
                    WheelDelta { x, y, z: 0.0, mode },
                    DevicePoint::new(px, py).into(),
                ))),
                local_ime: None,
                key_transition: None,
            },
        )]);
    }

    fn forward_keyboard(&self, event: winit::event::KeyEvent) {
        if !self.ingress.borrow().keyboard_allowed() {
            self.trace_native_refusal("keyboard_not_owned");
            return;
        }
        let physical_key = format!("{:?}", event.physical_key);
        let down = event.state == ElementState::Pressed;
        let (key, bytes) = match event.logical_key {
            WinitKey::Character(value) => (Key::Character(value.to_string()), value.len() + 32),
            WinitKey::Named(WinitNamedKey::Enter) => (Key::Named(NamedKey::Enter), 32),
            WinitKey::Named(WinitNamedKey::Tab) => (Key::Named(NamedKey::Tab), 32),
            WinitKey::Named(WinitNamedKey::Backspace) => (Key::Named(NamedKey::Backspace), 32),
            _ => (Key::Named(NamedKey::Unidentified), 32),
        };
        let state = match event.state {
            ElementState::Pressed => KeyState::Down,
            ElementState::Released => KeyState::Up,
        };
        let point = self.ingress.borrow().point();
        self.enqueue_native(vec![(
            NativeKind::Key,
            point,
            bytes + physical_key.len(),
            NativePayload {
                event: Some(InputEvent::Keyboard(KeyboardEvent::from_state_and_key(
                    state, key,
                ))),
                local_ime: None,
                key_transition: Some((physical_key, down)),
            },
        )]);
    }

    fn forward_native_ime(&self, event: Ime) {
        self.native_ime_events.set(self.native_ime_events.get() + 1);
        let mut events = Vec::new();
        let committing = matches!(&event, Ime::Commit(_));
        match event {
            Ime::Enabled => {
                self.ingress.borrow_mut().ime_enabled(true);
                events.push((
                    NativeKind::LocalIme,
                    None,
                    8,
                    NativePayload {
                        event: None,
                        local_ime: Some(true),
                        key_transition: None,
                    },
                ));
            }
            Ime::Disabled => {
                let dismiss = self.ingress.borrow_mut().ime_enabled(false);
                events.push((
                    NativeKind::LocalIme,
                    None,
                    8,
                    NativePayload {
                        event: None,
                        local_ime: Some(false),
                        key_transition: None,
                    },
                ));
                if dismiss {
                    events.push((
                        NativeKind::Ime,
                        None,
                        8,
                        NativePayload {
                            event: Some(InputEvent::Ime(ImeEvent::Dismissed)),
                            local_ime: None,
                            key_transition: None,
                        },
                    ));
                }
            }
            Ime::Preedit(data, _) | Ime::Commit(data) => {
                let start = self.ingress.borrow_mut().composition(committing);
                let Some(start) = start else {
                    self.trace_native_refusal("ime_not_owned");
                    return;
                };
                if start {
                    events.push((
                        NativeKind::Ime,
                        None,
                        32,
                        NativePayload {
                            event: Some(InputEvent::Ime(ImeEvent::Composition(CompositionEvent {
                                state: CompositionState::Start,
                                data: String::new(),
                            }))),
                            local_ime: None,
                            key_transition: None,
                        },
                    ));
                }
                let bytes = data.len() + 32;
                events.push((
                    NativeKind::Ime,
                    None,
                    bytes,
                    NativePayload {
                        event: Some(InputEvent::Ime(ImeEvent::Composition(CompositionEvent {
                            state: if committing {
                                CompositionState::End
                            } else {
                                CompositionState::Update
                            },
                            data,
                        }))),
                        local_ime: None,
                        key_transition: None,
                    },
                ));
            }
        }
        self.enqueue_native(events);
    }

    fn native_owner(&self) -> Option<NativeOwner> {
        if !self.input.borrow().current_callback(self.generation.get()) {
            return None;
        }
        let view = self
            .webview
            .borrow()
            .as_ref()
            .map(|webview| format!("{:?}", webview.id()))?;
        Some(NativeOwner {
            generation: self.generation.get(),
            view,
            epoch: self.ingress.borrow().epoch,
        })
    }

    fn record_native(&self, phase: &str, ticket: &NativeTicket, id: Option<InputEventId>) {
        let mut records = self.native_trace.borrow_mut();
        if records.len() == 256 {
            drop(records);
            self.fail("bounded native input facts exceeded");
            return;
        }
        records.push(serde_json::json!({"phase":phase,"sequence":ticket.sequence,
            "generation":ticket.owner.generation,"view":ticket.owner.view,"epoch":ticket.owner.epoch,
            "kind":ticket.kind.as_str(),"point":ticket.point,"event_id":id.map(|value|format!("{value:?}")),
            "source":if ticket.kind == NativeKind::SyntheticIme {"qualification_synthetic"} else {"native_winit"}}));
    }

    fn trace_native_refusal(&self, reason: &str) {
        let mut records = self.native_trace.borrow_mut();
        if records.len() == 256 {
            drop(records);
            self.fail("bounded native input facts exceeded");
            return;
        }
        records.push(serde_json::json!({"phase":"not_admitted","reason":reason,
            "generation":self.generation.get(),"epoch":self.ingress.borrow().epoch}));
    }

    fn enqueue_native(&self, events: Vec<(NativeKind, Option<(f32, f32)>, usize, NativePayload)>) {
        let Some(owner) = self.native_owner() else {
            self.trace_native_refusal("stale_owner");
            return;
        };
        let result = self
            .native_lane
            .borrow_mut()
            .enqueue(Instant::now(), owner, events);
        match result {
            Ok(tickets) => {
                for ticket in tickets {
                    self.record_native("admitted", &ticket, None);
                }
                let _ = self.proxy.send_event(AppEvent::Drive);
            }
            Err(error) => self.refuse_native_input(error),
        }
    }

    fn withdraw_native_input(&self) {
        let discarded = self.native_lane.borrow().unsent_tickets();
        let result = self.native_lane.borrow_mut().withdraw();
        for ticket in discarded {
            self.record_native("withdrawn_unsent", &ticket, None);
        }
        let result = if self.auxiliary.borrow().unsettled() {
            self.native_lane
                .borrow_mut()
                .close(LaneError::OwnershipWithdrawn)
        } else {
            result
        };
        // Preserve the actual held gesture's original withdrawal reason.
        if self.retire_withdrawn_gesture() {
            return;
        }
        if let Err(error) = result {
            self.refuse_native_input(error);
        }
    }

    fn refuse_native_input(&self, error: LaneError) {
        if self.failure.borrow().is_some() {
            return;
        }
        let _: Result<(), LaneError> = self.native_lane.borrow_mut().close(error);
        self.input.borrow_mut().refuse_ordered_input();
        if self.retire_withdrawn_gesture() {
            return;
        }
        self.input.borrow_mut().crashed();
        self.ingress.borrow_mut().barrier();
        let retired = self.webview.borrow_mut().take();
        if let Some(webview) = retired {
            webview.blur();
            webview.hide();
            drop(webview);
        }
        self.trace_native_refusal(error.as_str());
        let report = serde_json::json!({"schema":"trillionnium.desktop.native-input-refusal.v1",
            "reason":error.as_str(),"generation":self.generation.get(),"fresh_servo_owner_required":true,
            "synthetic_mouse_release_sent":false,"same_servo_reconstruction_allowed":false,"product_ready":false});
        let _ = fs::write(
            self.output_dir.join("native-input-refusal.json"),
            serde_json::to_string_pretty(&report).unwrap() + "\n",
        );
        self.fail(&format!("ordered native input refused: {}", error.as_str()));
    }

    fn drain_native_input(&self) {
        let Some(owner) = self.native_owner() else {
            return;
        };
        let reservation = self.native_lane.borrow_mut().begin(Instant::now(), &owner);
        let event = match reservation {
            Ok(Some(event)) => event,
            Ok(None) => return,
            Err(error) => {
                self.refuse_native_input(error);
                return;
            }
        };
        let ticket = event.ticket;
        let webview = self.webview.borrow().as_ref().cloned();
        let Some(webview) = webview else {
            self.refuse_native_input(LaneError::UnknownSubmission);
            return;
        };
        // Submitting is reserved and all RefCell borrows are released here.
        if let Some(enabled) = event.payload.local_ime {
            if enabled {
                self.input.borrow_mut().enable_ime();
            } else {
                self.input.borrow_mut().disable_ime();
            }
            let result = self
                .native_lane
                .borrow_mut()
                .local(Instant::now(), &owner, &ticket);
            match result {
                Ok(()) => {
                    self.record_native("local_applied", &ticket, None);
                    let _ = self.proxy.send_event(AppEvent::Drive);
                }
                Err(error) => self.refuse_native_input(error),
            }
            return;
        }
        if matches!(ticket.kind, NativeKind::Down(_)) {
            webview.focus();
        }
        if self.native_owner().as_ref() != Some(&ticket.owner) {
            self.refuse_native_input(LaneError::StaleOwner);
            return;
        }
        let check = self.native_lane.borrow_mut().check(Instant::now());
        if let Err(error) = check {
            self.refuse_native_input(error);
            return;
        }
        if let Some((x, y)) = ticket.point {
            self.input
                .borrow_mut()
                .pointer(x as f64, y as f64 + CHROME_HEIGHT as f64);
        }
        match ticket.kind {
            NativeKind::Down(button) | NativeKind::Up(button) => {
                let owned_action = if matches!(ticket.kind, NativeKind::Down(_)) {
                    ButtonAction::Down
                } else {
                    ButtonAction::Up
                };
                let point = ticket.point.unwrap();
                if owned_action == ButtonAction::Down {
                    self.input.borrow_mut().pressed();
                }
                let route = self.input.borrow_mut().route_button_at(
                    self.generation.get(),
                    button,
                    owned_action,
                    point,
                );
                if route != Some(point) {
                    self.refuse_native_input(LaneError::PhysicalSequence);
                    return;
                }
                self.native_button_events
                    .set(self.native_button_events.get() + 1);
            }
            NativeKind::Move => self
                .native_pointer_events
                .set(self.native_pointer_events.get() + 1),
            NativeKind::Wheel => self
                .native_wheel_events
                .set(self.native_wheel_events.get() + 1),
            NativeKind::Key => self
                .native_keyboard_events
                .set(self.native_keyboard_events.get() + 1),
            _ => {}
        }
        let Some(payload) = event.payload.event else {
            self.refuse_native_input(LaneError::UnknownSubmission);
            return;
        };
        let key_release = if let Some((physical_key, down)) = event.payload.key_transition {
            let result = self.auxiliary.borrow_mut().reserve_key(&physical_key, down);
            match result {
                Ok(release) => release,
                Err(error) => {
                    self.refuse_native_input(error);
                    return;
                }
            }
        } else {
            None
        };
        let composition_end = matches!(
            &payload,
            InputEvent::Ime(ImeEvent::Composition(CompositionEvent {
                state: CompositionState::End,
                ..
            })) | InputEvent::Ime(ImeEvent::Dismissed)
        );
        if let InputEvent::Ime(ImeEvent::Composition(composition)) = &payload {
            let start = matches!(&composition.state, CompositionState::Start);
            let result = self
                .auxiliary
                .borrow_mut()
                .reserve_composition(start, composition_end);
            if let Err(error) = result {
                self.refuse_native_input(error);
                return;
            }
            if ticket.kind == NativeKind::Ime {
                let allowed = if start {
                    self.input.borrow_mut().begin_ime()
                } else {
                    self.input.borrow().ime_allowed()
                };
                if !allowed {
                    self.refuse_native_input(LaneError::PhysicalSequence);
                    return;
                }
            }
        }
        // At most one actual Servo input call per Drive, never from the ACK.
        let event_id = webview.notify_input_event(payload);
        let Some(current) = self.native_owner() else {
            self.refuse_native_input(LaneError::UnknownSubmission);
            return;
        };
        let result =
            self.native_lane
                .borrow_mut()
                .bind(Instant::now(), &current, &ticket, event_id);
        if let Err(error) = result {
            self.refuse_native_input(error);
            return;
        }
        let completion =
            self.auxiliary
                .borrow_mut()
                .bind_completion(event_id, key_release, composition_end);
        if let Err(error) = completion {
            self.refuse_native_input(error);
            return;
        }
        if let NativeKind::Up(owned_button) = ticket.kind {
            self.pending_mouse_releases
                .borrow_mut()
                .insert(event_id, owned_button);
        }
        let qualified = {
            let mut qualified = self.qualification_input.borrow_mut();
            if let Some(input) = qualified.as_mut() {
                match ticket.kind {
                    NativeKind::Move => {
                        input.observe_pointer(
                            self.generation.get(),
                            ticket.point.unwrap(),
                            event_id,
                        );
                        Ok(())
                    }
                    NativeKind::Down(_) => input.submit_down(event_id),
                    NativeKind::Up(_) => input.submit_up(event_id),
                    _ => Ok(()),
                }
            } else {
                Ok(())
            }
        };
        if let Err(error) = qualified {
            self.fail(error);
        }
        self.record_native("submitted", &ticket, Some(event_id));
    }

    fn write_native_evidence(&self) -> Result<(), String> {
        let report = serde_json::json!({"schema":"trillionnium.desktop.native-input-queue.v1",
            "source_only":true,"owner_pid":std::process::id(),"owner_start_time":self.qualification_owner_start,
            "qualification_ack_profile":self.qualification_nonce.is_some(),
            "records":&*self.native_trace.borrow(),"queue_idle":self.native_lane.borrow().idle(),
            "maximum_pending_events":input_ownership::MAX_NATIVE_EVENTS,
            "maximum_payload_bytes":input_ownership::MAX_NATIVE_PAYLOAD_BYTES,
            "busy_episode_budget_seconds":input_ownership::NATIVE_EPISODE_BUDGET.as_secs(),
            "ack_is_dom_execution_proof":false,"product_ready":false});
        fs::write(
            self.output_dir.join("native-input-queue.json"),
            serde_json::to_string_pretty(&report).map_err(|_| "input facts encoding failed")?
                + "\n",
        )
        .map_err(|_| "input facts publication failed".into())
    }

    fn fail(&self, message: &str) {
        if self.failure.borrow().is_none() {
            *self.failure.borrow_mut() = Some(message.to_owned());
            eprintln!("D0A-02 failure: {message}");
            let _ = self.proxy.send_event(AppEvent::Drive);
        }
    }

    fn finish_failure(&self) {
        if self.completed.replace(true) {
            return;
        }
        let failure = self
            .failure
            .borrow()
            .clone()
            .unwrap_or_else(|| "unknown failure".to_owned());
        let state_report = format!(
            concat!(
                "{{\n",
                "  \"schema\": \"trillionnium.desktop.d0a02-runtime-state.v1\",\n",
                "  \"generation\": {},\n",
                "  \"load_complete\": {},\n",
                "  \"frame_ready\": {},\n",
                "  \"content_screenshot_requested\": {},\n",
                "  \"content_screenshot_saved\": {},\n",
                "  \"workspace_screenshot_saved\": {},\n",
                "  \"focus_requested\": {},\n",
                "  \"focus_ready\": {},\n",
                "  \"input_marker_written\": {},\n",
                "  \"native_pointer_events\": {},\n",
                "  \"native_button_events\": {},\n",
                "  \"native_wheel_events\": {},\n",
                "  \"native_keyboard_events\": {},\n",
                "  \"native_ime_events\": {},\n",
                "  \"input_handled_callbacks\": {},\n",
                "  \"synthetic_ime_sent\": {},\n",
                "  \"settled\": {},\n",
                "  \"page_evidence_requested\": {},\n",
                "  \"initial_page_evidence_present\": {},\n",
                "  \"recovery_page_evidence_present\": {},\n",
                "  \"popup_denied\": {},\n",
                "  \"navigation_denied\": {},\n",
                "  \"input_method_controls\": {},\n",
                "  \"crash_triggered\": {},\n",
                "  \"crash_observed\": {},\n",
                "  \"crash_workspace_saved\": {},\n",
                "  \"recovery_started\": {},\n",
                "  \"chrome_initial_ok\": {},\n",
                "  \"chrome_crash_ok\": {},\n",
                "  \"chrome_recovery_ok\": {},\n",
                "  \"window_resize_events\": {},\n",
                "  \"failure\": {}\n",
                "}}\n"
            ),
            self.generation.get(),
            self.load_complete.get(),
            self.frame_ready.get(),
            self.content_screenshot_requested.get(),
            self.content_screenshot_saved.get(),
            self.workspace_screenshot_saved.get(),
            self.focus_requested.get(),
            self.focus_ready.get(),
            self.input_marker_written.get(),
            self.native_pointer_events.get(),
            self.native_button_events.get(),
            self.native_wheel_events.get(),
            self.native_keyboard_events.get(),
            self.native_ime_events.get(),
            self.input_handled_callbacks.get(),
            self.synthetic_ime_sent.get(),
            self.settled.get(),
            self.page_evidence_requested.get(),
            self.initial_page_evidence.borrow().is_some(),
            self.recovery_page_evidence.borrow().is_some(),
            self.popup_denied.get(),
            self.navigation_denied.get(),
            self.input_method_controls.get(),
            self.crash_triggered.get(),
            self.crash_observed.get(),
            self.crash_workspace_saved.get(),
            self.recovery_started.get(),
            self.chrome_initial_ok.get(),
            self.chrome_crash_ok.get(),
            self.chrome_recovery_ok.get(),
            self.window_resize_events.get(),
            json_string(&failure),
        );
        let _ = self.write_native_evidence();
        let _ = fs::write(self.output_dir.join("runtime-state.json"), state_report);
        let report = format!(
            "{{\n  \"schema\": \"trillionnium.desktop.d0a02-headed-runtime.v1\",\n  \"status\": \"FAIL\",\n  \"failure\": {},\n  \"servo_started\": true,\n  \"product_ready\": false\n}}\n",
            json_string(&failure)
        );
        let _ = fs::write(self.output_dir.join("runtime-result.json"), report);
        let _ = self.proxy.send_event(AppEvent::Exit(1));
    }

    fn finish_success(&self) {
        if !self.crash_triggered.get()
            || !self.exact_termination_observed.get()
            || self.fault_process.get().is_none()
        {
            self.fail("requested process fault and exact termination evidence are required");
            self.finish_failure();
            return;
        }
        if let Err(error) = self.write_resource_evidence() {
            self.fail(&format!(
                "resource confinement evidence incomplete: {error}"
            ));
            self.finish_failure();
            return;
        }
        if let Err(error) = self.write_native_evidence() {
            self.fail(&error);
            self.finish_failure();
            return;
        }
        if self.completed.replace(true) {
            return;
        }
        let initial = self
            .initial_page_evidence
            .borrow()
            .clone()
            .unwrap_or_else(|| "null".to_owned());
        let recovery = self
            .recovery_page_evidence
            .borrow()
            .clone()
            .unwrap_or_else(|| "null".to_owned());
        let crash_reason = self.crash_reason.borrow().clone().unwrap_or_default();
        let (fault_pid, fault_start) = self
            .fault_process
            .get()
            .expect("fault identity checked above");
        let report = format!(
            concat!(
                "{{\n",
                "  \"schema\": \"trillionnium.desktop.d0a02-headed-runtime.v1\",\n",
                "  \"status\": \"PASS_HEADED_LOCAL_FIXTURE_ONLY\",\n",
                "  \"servo_commit\": \"670ae8a70801b162e186f81cbb5bdd2d59c39108\",\n",
                "  \"window_created\": true,\n",
                "  \"trusted_chrome_separate_from_content\": true,\n",
                "  \"logical_content_webview_peak\": 1,\n",
                "  \"initial_generation\": 1,\n",
                "  \"recovery_generation\": 2,\n",
                "  \"chrome_initial_pixels_verified\": {},\n",
                "  \"chrome_crash_pixels_verified\": {},\n",
                "  \"chrome_recovery_pixels_verified\": {},\n",
                "  \"native_pointer_events\": {},\n",
                "  \"native_button_events\": {},\n",
                "  \"native_wheel_events\": {},\n",
                "  \"native_keyboard_events\": {},\n",
                "  \"native_ime_events\": {},\n",
                "  \"synthetic_ime_composition_events\": 3,\n",
                "  \"input_handled_callbacks\": {},\n",
                "  \"input_method_controls\": {},\n",
                "  \"popup_requests_denied\": {},\n",
                "  \"external_navigation_requests_denied\": {},\n",
                "  \"content_crash_observed\": true,\n",
                "  \"content_crash_reason\": {},\n",
                "  \"fault_injection\": {{\"mechanism\":\"requested_SIGKILL\",\"generation\":1,\"pid\":{},\"start_time\":{},\"exact_termination_observed\":{}}},\n",
                "  \"trusted_window_survived_content_crash\": true,\n",
                "  \"initial_page_evidence\": {},\n",
                "  \"recovery_page_evidence\": {},\n",
                "  \"authority\": {{\n",
                "    \"fixture_listener_loopback_only\": true,\n",
                "    \"external_navigation_performed\": false,\n",
                "    \"webdriver_listener_started\": false,\n",
                "    \"browser_actor_started\": false,\n",
                "    \"agent_port_enabled\": false,\n",
                "    \"persistent_credentials_used\": false,\n",
                "    \"product_ready\": false\n",
                "  }}\n",
                "}}\n"
            ),
            self.chrome_initial_ok.get(),
            self.chrome_crash_ok.get(),
            self.chrome_recovery_ok.get(),
            self.native_pointer_events.get(),
            self.native_button_events.get(),
            self.native_wheel_events.get(),
            self.native_keyboard_events.get(),
            self.native_ime_events.get(),
            self.input_handled_callbacks.get(),
            self.input_method_controls.get(),
            self.popup_denied.get(),
            self.navigation_denied.get(),
            json_string(&crash_reason),
            fault_pid,
            fault_start,
            self.exact_termination_observed.get(),
            initial,
            recovery,
        );
        if let Err(error) = fs::write(self.output_dir.join("runtime-result.json"), report) {
            eprintln!("could not write D0A-02 runtime result: {error}");
            let _ = self.proxy.send_event(AppEvent::Exit(1));
            return;
        }
        let _ = self.proxy.send_event(AppEvent::Exit(0));
    }

    fn write_resource_evidence(&self) -> Result<(), String> {
        let observations = self.resource_observations.borrow();
        if observations.exceeded_bound || self.fixture_network_requests.load(Ordering::Relaxed) != 0
        {
            return Err("bounded callback or no-network requirement failed".into());
        }
        let mut generations = Vec::with_capacity(2);
        for (index, evidence) in [
            self.initial_page_evidence.borrow().clone(),
            self.recovery_page_evidence.borrow().clone(),
        ]
        .into_iter()
        .enumerate()
        {
            let generation = index + 1;
            let facts = observations.generations[index];
            let page: serde_json::Value =
                serde_json::from_str(&evidence.ok_or("missing actual DOM evidence")?)
                    .map_err(|_| "invalid actual DOM evidence")?;
            let mut dom = serde_json::Map::new();
            for key in [
                "resourceProbesSettled",
                "sameOriginScriptRejected",
                "wrongMethodFetchRejected",
                "externalScriptRejected",
            ] {
                if page.get(key) != Some(&serde_json::Value::Bool(true)) {
                    return Err(format!(
                        "generation {generation} DOM refusal missing: {key}"
                    ));
                }
                dom.insert(key.into(), serde_json::Value::Bool(true));
            }
            if page.get("forbiddenResourceExecuted") != Some(&serde_json::Value::Bool(false))
                || page.get("generation").and_then(serde_json::Value::as_u64)
                    != Some(generation as u64)
                || !facts.probes_observed()
            {
                return Err(format!(
                    "generation {generation} actual callback/DOM binding failed"
                ));
            }
            dom.insert(
                "forbiddenResourceExecuted".into(),
                serde_json::Value::Bool(false),
            );
            let worker = page
                .get("serviceWorkerProbe")
                .and_then(serde_json::Value::as_str)
                .ok_or("missing worker probe availability")?;
            if !matches!(worker, "unavailable" | "rejected") {
                return Err("worker probe did not reach a refused or unavailable outcome".into());
            }
            dom.insert(
                "serviceWorkerProbe".into(),
                serde_json::Value::String(worker.into()),
            );
            generations.push(serde_json::json!({
                "generation": generation,
                "callbacks": facts.callbacks,
                "local_response_finishes": facts.local_response_finishes,
                "cancel_submissions": facts.cancel_submissions,
                "same_origin_script_cancels": facts.same_origin_script_cancels,
                "wrong_method_fetch_cancels": facts.wrong_method_fetch_cancels,
                "external_script_cancels": facts.external_script_cancels,
                "dom": dom,
            }));
        }
        let report = serde_json::json!({
            "schema": "trillionnium.desktop.servo-http-resource-gate.v1",
            "servo_commit": "670ae8a70801b162e186f81cbb5bdd2d59c39108",
            "status": "OBSERVED_HTTP_CALLBACK_REFUSALS",
            "fixture_origin": self.resource_gate.origin().ok_or("missing fixture custody")?,
            "fixture_network_requests": self.fixture_network_requests.load(Ordering::Relaxed),
            "generations": generations,
            "global_cancel_submissions": observations.global_cancel_submissions,
            "global_callback_observed": observations.global_cancel_submissions > 0,
            "stale_cancel_submissions": observations.stale_cancel_submissions,
            "default_resources_admitted": 0,
            "network_continuations_submitted": 0,
            "callback_bound_exceeded": observations.exceeded_bound,
            "claim_ceiling": {
                "signed_app_admission_connected": false,
                "installed_csp_qualified": false,
                "websocket_confinement": false,
                "all_protocol_confinement": false,
                "network_namespace_confinement": false,
                "product_ready": false,
            },
        });
        fs::write(
            self.output_dir.join("resource-gate-result.json"),
            serde_json::to_string_pretty(&report)
                .map_err(|_| "resource result serialization failed")?
                + "\n",
        )
        .map_err(|_| "resource result publication failed".into())
    }
}

struct RuntimeDelegate {
    state: Weak<RuntimeState>,
    generation: u32,
    resource_gate: Rc<ResourceGate>,
    observations: Rc<RefCell<Observations>>,
}

impl RuntimeDelegate {
    fn current(&self) -> Option<Rc<RuntimeState>> {
        self.state
            .upgrade()
            .filter(|state| state.input.borrow().current_callback(self.generation))
    }
}

impl WebViewDelegate for RuntimeDelegate {
    fn load_web_resource(&self, webview: WebView, load: WebResourceLoad) {
        let state = self.current();
        let current_generation = state.as_ref().map_or(0, |state| state.generation.get());
        let active_owned_webview = state.as_ref().is_some_and(|state| {
            !state.completed.get()
                && state.failure.borrow().is_none()
                && state
                    .webview
                    .borrow()
                    .as_ref()
                    .is_some_and(|owned| owned.id() == webview.id())
        });
        respond_to_resource(
            load,
            &self.resource_gate,
            &self.observations,
            ResourceContext {
                callback_generation: Some(self.generation),
                current_generation,
                active_owned_webview,
            },
        );
        if let Some(state) = state {
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
    }

    fn notify_load_status_changed(&self, _webview: WebView, status: LoadStatus) {
        if let Some(state) = self.current() {
            state.load_complete.set(status == LoadStatus::Complete);
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
    }

    fn notify_new_frame_ready(&self, _webview: WebView) {
        if let Some(state) = self.current() {
            state.frame_ready.set(state.frame_ready.get() + 1);
            state.window.request_redraw();
        }
    }

    fn notify_input_event_handled(
        &self,
        webview: WebView,
        event_id: InputEventId,
        result: InputEventResult,
    ) {
        if let Some(state) = self.current() {
            let Some(mut owner) = state.native_owner() else {
                return;
            };
            owner.view = format!("{:?}", webview.id());
            let result_lane = state.native_lane.borrow_mut().acknowledge(
                Instant::now(),
                &owner,
                event_id,
                !result.contains(InputEventResult::DispatchFailed),
            );
            let ticket = match result_lane {
                Ok(NativeAck::Accepted(ticket)) => ticket,
                Ok(NativeAck::Ignored) => {
                    state.trace_native_refusal("stale_callback");
                    return;
                }
                Err(error) => {
                    if error == LaneError::DispatchFailed {
                        let release = state.pending_mouse_releases.borrow_mut().remove(&event_id);
                        if let Some(button) = release {
                            state.input.borrow_mut().acknowledge_release(
                                self.generation,
                                button,
                                ReleaseOutcome::DispatchFailed,
                            );
                            if state.retire_withdrawn_gesture() {
                                return;
                            }
                        }
                    }
                    state.refuse_native_input(error);
                    return;
                }
            };
            state.record_native("accepted", &ticket, Some(event_id));
            let auxiliary = state.auxiliary.borrow_mut().accepted(event_id);
            match auxiliary {
                Ok(true) => {
                    state.input.borrow_mut().end_ime();
                }
                Ok(false) => {}
                Err(error) => {
                    state.refuse_native_input(error);
                    return;
                }
            }
            let button = state.pending_mouse_releases.borrow_mut().remove(&event_id);
            if let Some(button) = button {
                let outcome = if result.contains(InputEventResult::DispatchFailed) {
                    ReleaseOutcome::DispatchFailed
                } else {
                    ReleaseOutcome::Accepted
                };
                let acknowledged =
                    state
                        .input
                        .borrow_mut()
                        .acknowledge_release(self.generation, button, outcome);
                if state.retire_withdrawn_gesture() {
                    return;
                }
                if !acknowledged {
                    state.fail("actual mouse release callback did not settle its owned binding");
                    return;
                }
            }
            let (point, focused, ready) = {
                let input = state.input.borrow();
                (
                    if state.qualification_nonce.is_some() {
                        input.point()
                    } else {
                        state.ingress.borrow().point()
                    },
                    input.window_focused(),
                    input.button_ready(self.generation, Button::Primary),
                )
            };
            let checkpoint = state
                .qualification_input
                .borrow_mut()
                .as_mut()
                .map(|input| {
                    input.acknowledge(
                        self.generation,
                        point,
                        focused,
                        event_id,
                        !result.contains(InputEventResult::DispatchFailed),
                    )
                });
            match checkpoint {
                Some(Ok(Some(checkpoint))) => {
                    if checkpoint.phase == CheckpointPhase::UpAccepted
                        && button != Some(Button::Primary)
                    {
                        state.fail("qualification Up callback did not match the actual owned primary release");
                        return;
                    }
                    if matches!(
                        checkpoint.phase,
                        CheckpointPhase::Ready | CheckpointPhase::PreludeReady
                    ) && !ready
                    {
                        state.fail("native pointer checkpoint still has an unsettled owned button");
                        return;
                    }
                    state.publish_input_checkpoint(checkpoint);
                }
                Some(Err(error)) => {
                    state.fail(error);
                    return;
                }
                _ => {}
            }
            state
                .input_handled_callbacks
                .set(state.input_handled_callbacks.get() + 1);
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
    }

    fn notify_crashed(&self, _webview: WebView, reason: String, _backtrace: Option<String>) {
        if let Some(state) = self.current() {
            if !state.crash_triggered.get() || state.fault_process.get().is_none() {
                state.ingress.borrow_mut().barrier();
                state.input.borrow_mut().crashed();
                state.withdraw_native_input();
                state.retire_withdrawn_gesture();
                state.fail("spontaneous content crash cannot satisfy requested process-fault qualification");
                return;
            }
            state.crash_observed.set(true);
            state.ingress.borrow_mut().barrier();
            state.input.borrow_mut().crashed();
            state.withdraw_native_input();
            state.retire_withdrawn_gesture();
            *state.crash_reason.borrow_mut() = Some(reason);
            state.window.request_redraw();
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
    }

    fn request_navigation(&self, _webview: WebView, request: NavigationRequest) {
        if let Some(state) = self.current() {
            if state.fixture_origin_matches(&request.url) {
                request.allow();
            } else {
                state
                    .navigation_denied
                    .set(state.navigation_denied.get() + 1);
                request.deny();
            }
            let _ = state.proxy.send_event(AppEvent::Drive);
        } else {
            request.deny();
        }
    }

    fn request_create_new(&self, _parent: WebView, _request: CreateNewWebViewRequest) {
        if let Some(state) = self.current() {
            state.popup_denied.set(state.popup_denied.get() + 1);
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
        // Dropping the request returns no auxiliary WebView.
    }

    fn show_embedder_control(&self, _webview: WebView, control: EmbedderControl) {
        if let Some(state) = self.current() {
            if matches!(control, EmbedderControl::InputMethod(_)) {
                state.window.set_ime_allowed(true);
                state
                    .input_method_controls
                    .set(state.input_method_controls.get() + 1);
            }
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
    }
}

struct GlobalResourceDelegate {
    observations: Rc<RefCell<Observations>>,
}

impl ServoDelegate for GlobalResourceDelegate {
    fn load_web_resource(&self, load: WebResourceLoad) {
        // No WebView principal exists here. No fixture or future app authority
        // is granted to global/worker/background requests.
        cancel_resource(load);
        self.observations
            .borrow_mut()
            .cancel(None, Denial::NoWebView, None);
    }
}

fn cancel_resource(load: WebResourceLoad) {
    // Cancellation is bound to the load's responder, not the response URL. A
    // fixed URL avoids copying an unbounded, content-controlled denied URL.
    let response =
        WebResourceResponse::new(Url::parse("about:blank").expect("fixed cancellation URL"));
    load.intercept(response).cancel();
}

fn respond_to_resource(
    load: WebResourceLoad,
    gate: &ResourceGate,
    observations: &RefCell<Observations>,
    context: ResourceContext,
) {
    let request = load.request();
    let probe = context.callback_generation.and_then(|generation| {
        gate.probe(generation, request.url.as_str(), request.method.as_str())
    });
    let decision = if observations.borrow().exceeded_bound {
        ResourceDecision::Cancel(Denial::StaleOrWithdrawn)
    } else {
        gate.decide(
            context,
            ResourceRequest {
                canonical_url: request.url.as_str(),
                method: request.method.as_str(),
                is_for_main_frame: request.is_for_main_frame,
                is_redirect: request.is_redirect,
            },
        )
    };
    match decision {
        ResourceDecision::LocalFixture(bytes) => {
            let mut response = WebResourceResponse::new(request.url.clone());
            for (name, value) in [
                ("content-type", "text/html; charset=utf-8"),
                ("cache-control", "no-store"),
                ("x-content-type-options", "nosniff"),
                ("content-security-policy", QUALIFICATION_CSP),
            ] {
                response
                    .headers
                    .insert(name, value.parse().expect("fixed response header"));
            }
            let mut interception = load.intercept(response);
            interception.send_body_data(bytes.to_vec());
            interception.finish();
            observations.borrow_mut().finish_local(
                context
                    .callback_generation
                    .expect("admitted WebView generation"),
            );
        }
        ResourceDecision::Cancel(denial) => {
            cancel_resource(load);
            observations
                .borrow_mut()
                .cancel(context.callback_generation, denial, probe);
        }
    }
}

fn exact_content_process_pid() -> Result<u32, String> {
    let parent_pid = std::process::id();
    let current_exe = fs::canonicalize(
        env::current_exe()
            .map_err(|error| format!("could not resolve parent executable: {error}"))?,
    )
    .map_err(|error| format!("could not canonicalize parent executable: {error}"))?;
    let mut candidates = Vec::new();
    let entries = fs::read_dir("/proc")
        .map_err(|error| format!("could not enumerate /proc for content process: {error}"))?;
    for entry in entries {
        let entry = match entry {
            Ok(entry) => entry,
            Err(_) => continue,
        };
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        let Ok(pid) = name.parse::<u32>() else {
            continue;
        };
        if pid == parent_pid {
            continue;
        }
        let stat = match fs::read_to_string(format!("/proc/{pid}/stat")) {
            Ok(stat) => stat,
            Err(_) => continue,
        };
        if proc_parent_pid(&stat) != Some(parent_pid) {
            continue;
        }
        let executable = match fs::canonicalize(format!("/proc/{pid}/exe")) {
            Ok(executable) => executable,
            Err(_) => continue,
        };
        if executable != current_exe {
            continue;
        }
        let cmdline = match fs::read(format!("/proc/{pid}/cmdline")) {
            Ok(cmdline) => cmdline,
            Err(_) => continue,
        };
        let has_content_process_flag = cmdline
            .split(|byte| *byte == 0)
            .any(|argument| argument == b"--content-process");
        if has_content_process_flag {
            candidates.push(pid);
        }
    }
    match candidates.as_slice() {
        [pid] => Ok(*pid),
        [] => Err("no exact direct --content-process child was found".to_owned()),
        _ => Err(format!(
            "multiple exact direct --content-process children were found: {candidates:?}"
        )),
    }
}

fn exact_content_process_start_time(pid: u32) -> Result<u64, String> {
    let stat = fs::read_to_string(format!("/proc/{pid}/stat"))
        .map_err(|error| format!("could not read exact content-process identity: {error}"))?;
    proc_start_time(&stat)
        .ok_or_else(|| "could not parse exact content-process start time".to_owned())
}

fn proc_state(stat: &str) -> Option<char> {
    let command_end = stat.rfind(')')?;
    stat.get(command_end + 2..)?
        .split_whitespace()
        .next()?
        .chars()
        .next()
}

fn proc_start_time(stat: &str) -> Option<u64> {
    let command_end = stat.rfind(')')?;
    stat.get(command_end + 2..)?
        .split_whitespace()
        .nth(19)?
        .parse()
        .ok()
}

fn proc_parent_pid(stat: &str) -> Option<u32> {
    let command_end = stat.rfind(')')?;
    stat.get(command_end + 2..)?
        .split_whitespace()
        .nth(1)?
        .parse()
        .ok()
}

fn clear_rect(gl: &glow::Context, x: i32, y: i32, width: i32, height: i32, color: [f32; 4]) {
    unsafe {
        gl.enable(glow::SCISSOR_TEST);
        gl.scissor(x, y, width, height);
        gl.clear_color(color[0], color[1], color[2], color[3]);
        gl.clear(glow::COLOR_BUFFER_BIT);
        gl.disable(glow::SCISSOR_TEST);
    }
}

fn json_string(value: &str) -> String {
    let mut output = String::with_capacity(value.len() + 2);
    output.push('"');
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character.is_control() => {
                use std::fmt::Write as _;
                let _ = write!(output, "\\u{:04x}", character as u32);
            }
            character => output.push(character),
        }
    }
    output.push('"');
    output
}

#[allow(dead_code)]
fn _assert_output_is_under(path: &Path, root: &Path) -> bool {
    path.starts_with(root)
}
