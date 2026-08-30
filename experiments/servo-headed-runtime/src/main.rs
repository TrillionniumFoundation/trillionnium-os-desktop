// D0A-02 headed runtime proof for the exact pinned Servo checkout.
//
// This source is copied into Servo's examples directory by the permanent
// qualification workflow. It creates one native window, draws trusted chrome
// in the embedder-owned parent framebuffer, and composites exactly one Servo
// WebView from an offscreen rendering context below that chrome. The proof
// binds recovery to an exact externally injected SIGKILL of one PID/start-time
// identity, isolates every callback by generation and WebView identity, and
// records measured WebView/process topology. It never starts WebDriver and its
// HTTP fixture listens only on 127.0.0.1.

use std::cell::{Cell, RefCell};
use std::env;
use std::error::Error;
use std::fs;
use std::io::{ErrorKind, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::rc::{Rc, Weak};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
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
    WebView, WebViewBuilder, WebViewDelegate, WheelDelta, WheelEvent, WheelMode,
    WindowRenderingContext, run_content_process,
};
use url::Url;
use winit::application::ApplicationHandler;
use winit::dpi::{PhysicalPosition, PhysicalSize};
use winit::event::{ElementState, Ime, MouseButton, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop, EventLoopProxy};
use winit::keyboard::{Key as WinitKey, NamedKey as WinitNamedKey};
use winit::raw_window_handle::{HasDisplayHandle, HasWindowHandle};
use winit::window::Window;

const WINDOW_WIDTH: u32 = 1024;
const WINDOW_HEIGHT: u32 = 768;
const CHROME_HEIGHT: u32 = 64;
const CONTENT_HEIGHT: u32 = WINDOW_HEIGHT - CHROME_HEIGHT;
const WINDOW_TITLE: &str = "TrillionniumOS Desktop — trusted chrome — D0A-02";
const FIXTURE_HTML: &str = include_str!("trillionnium_headed_fixture.html");
const NATIVE_INPUT_TIMEOUT_SECONDS: u64 = 150;
const PROCESS_OBSERVATION_TIMEOUT_SECONDS: u64 = 10;
const EXTERNAL_FAULT_POLL_MILLISECONDS: u64 = 50;

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
    // The integrated D2I image keeps the embedder alive after it has emitted
    // its evidence.  This gives the external systemd injector and the guest
    // acceptance unit a stable supervision boundary until QEMU powers off.
    // The host-only D0A-02 gate leaves this unset and exits normally.
    if exit_code == 0 && env::var_os("HEPTA_D2I_HOLD_AFTER_RESULT").is_some() {
        eprintln!("D2I runtime evidence complete; holding for supervised shutdown");
        loop {
            thread::sleep(Duration::from_secs(60));
        }
    }
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
    // Clean Servo teardown is deliberately outside this gate's claim ceiling.
    // The result records that non-claim explicitly; successful evidence must
    // not be converted into an unbounded synchronous Drop wait after the event
    // loop has stopped.
    std::mem::forget(app);
    Ok(exit_code)
}

struct FixtureServer {
    address: SocketAddr,
    shutdown: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}

impl FixtureServer {
    fn start() -> Result<Self, Box<dyn Error>> {
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        listener.set_nonblocking(true)?;
        let address = listener.local_addr()?;
        let shutdown = Arc::new(AtomicBool::new(false));
        let thread_shutdown = shutdown.clone();
        let handle = thread::spawn(move || {
            while !thread_shutdown.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut stream, _peer)) => serve_fixture(&mut stream),
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
    let mut request = [0_u8; 4096];
    let _ = stream.read(&mut request);
    let body = FIXTURE_HTML.as_bytes();
    let header = format!(
        "HTTP/1.1 200 OK\r\n\
         Content-Type: text/html; charset=utf-8\r\n\
         Content-Length: {}\r\n\
         Cache-Control: no-store\r\n\
         Content-Security-Policy: default-src 'self' 'unsafe-inline'; connect-src 'none'; img-src 'none'; media-src 'none'; frame-src 'none'\r\n\
         X-Content-Type-Options: nosniff\r\n\
         Connection: close\r\n\r\n",
        body.len()
    );
    let _ = stream.write_all(header.as_bytes());
    let _ = stream.write_all(body);
    let _ = stream.flush();
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct ProcessIdentity {
    pid: u32,
    start_time: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct ObservedProcess {
    identity: ProcessIdentity,
    parent_pid: u32,
    state: char,
}

#[derive(Debug)]
enum AppEvent {
    Wake,
    Drive,
    Settled {
        generation: u32,
    },
    Timeout,
    ContentProcessTerminated {
        generation: u32,
        identity: ProcessIdentity,
    },
    ContentProcessTerminationFailed {
        generation: u32,
        message: String,
    },
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
            AppEvent::ContentProcessTerminated {
                generation,
                identity,
            } => {
                if let Some(state) = &self.state {
                    state.observe_exact_termination(generation, identity);
                }
            }
            AppEvent::ContentProcessTerminationFailed {
                generation,
                message,
            } => {
                if let Some(state) = &self.state {
                    if generation == state.generation.get() && !state.recovery_started.get() {
                        state.fail(&message);
                    } else {
                        state.note_stale_callback("termination-observer");
                    }
                }
            }
            AppEvent::Settled { generation } => {
                if let Some(state) = &self.state {
                    if generation == state.generation.get() {
                        state.settled.set(true);
                        state.servo.spin_event_loop();
                        state.drive();
                    } else {
                        state.note_stale_callback("settled-timer");
                    }
                }
            }
            AppEvent::Wake | AppEvent::Drive => {
                if let Some(state) = &self.state {
                    state.replacement_probe_scheduled.set(false);
                    state.servo.spin_event_loop();
                    state.drive();
                }
            }
        }
    }

    fn window_event(
        &mut self,
        _event_loop: &ActiveEventLoop,
        _window_id: winit::window::WindowId,
        event: WindowEvent,
    ) {
        let Some(state) = &self.state else {
            return;
        };
        state.servo.spin_event_loop();
        match event {
            WindowEvent::CloseRequested => {
                state.fail("window closed before qualification completed");
            }
            WindowEvent::RedrawRequested => state.compose(),
            WindowEvent::CursorMoved { position, .. } => state.forward_pointer_move(position),
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
                    state.fail("runtime window size changed from the fixed qualification surface");
                }
            }
            _ => {}
        }
        let _ = state.proxy.send_event(AppEvent::Drive);
    }

    fn about_to_wait(&mut self, _event_loop: &ActiveEventLoop) {
        if let Some(state) = &self.state {
            state.servo.spin_event_loop();
            state.drive();
        }
    }
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
    output_dir: PathBuf,

    generation: Cell<u32>,
    logical_webviews_created: Cell<u32>,
    logical_webviews_invalidated: Cell<u32>,
    logical_webviews_live: Cell<u32>,
    logical_webviews_peak: Cell<u32>,
    stale_callbacks_ignored: Cell<u32>,

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

    fault_selected: Cell<Option<ProcessIdentity>>,
    external_fault_armed: Cell<bool>,
    signal_sent: Cell<bool>,
    termination_observer_started: Cell<bool>,
    exact_termination_observed: Cell<bool>,
    old_process_absent: Cell<bool>,
    servo_crash_callback_observed: Cell<bool>,
    servo_crash_callback_reason: RefCell<Option<String>>,
    crash_workspace_saved: Cell<bool>,
    recovery_started: Cell<bool>,
    recovery_started_at: RefCell<Option<Instant>>,
    replacement_process: Cell<Option<ProcessIdentity>>,
    replacement_probe_scheduled: Cell<bool>,

    chrome_initial_ok: Cell<bool>,
    chrome_crash_ok: Cell<bool>,
    chrome_recovery_ok: Cell<bool>,
    window_resize_events: Cell<u32>,
    failure: RefCell<Option<String>>,
    completed: Cell<bool>,
    last_content_point: Cell<DevicePoint>,
}

impl RuntimeState {
    fn create(
        event_loop: &ActiveEventLoop,
        waker: Waker,
        proxy: EventLoopProxy<AppEvent>,
        fixture_url: Url,
        output_dir: PathBuf,
    ) -> Result<Rc<Self>, Box<dyn Error>> {
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
        servo.setup_logging();

        let state = Rc::new(Self {
            window,
            servo,
            parent_context,
            content_context,
            webview: RefCell::new(None),
            proxy,
            fixture_url,
            output_dir,
            generation: Cell::new(1),
            logical_webviews_created: Cell::new(0),
            logical_webviews_invalidated: Cell::new(0),
            logical_webviews_live: Cell::new(0),
            logical_webviews_peak: Cell::new(0),
            stale_callbacks_ignored: Cell::new(0),
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
            fault_selected: Cell::new(None),
            external_fault_armed: Cell::new(false),
            signal_sent: Cell::new(false),
            termination_observer_started: Cell::new(false),
            exact_termination_observed: Cell::new(false),
            old_process_absent: Cell::new(false),
            servo_crash_callback_observed: Cell::new(false),
            servo_crash_callback_reason: RefCell::new(None),
            crash_workspace_saved: Cell::new(false),
            recovery_started: Cell::new(false),
            recovery_started_at: RefCell::new(None),
            replacement_process: Cell::new(None),
            replacement_probe_scheduled: Cell::new(false),
            chrome_initial_ok: Cell::new(false),
            chrome_crash_ok: Cell::new(false),
            chrome_recovery_ok: Cell::new(false),
            window_resize_events: Cell::new(0),
            failure: RefCell::new(None),
            completed: Cell::new(false),
            last_content_point: Cell::new(DevicePoint::new(0.0, 0.0)),
        });
        state.create_webview();
        fs::write(state.output_dir.join("window-created"), WINDOW_TITLE)?;
        state.window.request_redraw();
        Ok(state)
    }

    fn create_webview(self: &Rc<Self>) {
        if self.webview.borrow().is_some() || self.logical_webviews_live.get() != 0 {
            self.fail("attempted to create a second authoritative logical WebView");
            return;
        }
        let generation = self.generation.get();
        let mut url = self.fixture_url.clone();
        url.set_query(Some(&format!("generation={generation}")));
        let delegate = Rc::new(RuntimeDelegate {
            state: Rc::downgrade(self),
            generation,
        });
        let webview = WebViewBuilder::new(&self.servo, self.content_context.clone())
            .url(url)
            .delegate(delegate)
            .build();
        webview.focus();
        *self.webview.borrow_mut() = Some(webview);
        self.logical_webviews_created
            .set(self.logical_webviews_created.get() + 1);
        self.logical_webviews_live.set(1);
        self.logical_webviews_peak
            .set(self.logical_webviews_peak.get().max(1));
    }

    fn invalidate_current_webview(&self) -> Result<(), String> {
        if self.logical_webviews_live.get() != 1 {
            return Err(format!(
                "logical WebView live count was {} before invalidation",
                self.logical_webviews_live.get()
            ));
        }
        let webview =
            self.webview.borrow_mut().take().ok_or_else(|| {
                "authoritative WebView was missing during invalidation".to_owned()
            })?;
        drop(webview);
        self.logical_webviews_live.set(0);
        self.logical_webviews_invalidated
            .set(self.logical_webviews_invalidated.get() + 1);
        Ok(())
    }

    fn callback_is_current(&self, generation: u32, webview: &WebView, kind: &str) -> bool {
        let current = generation == self.generation.get()
            && self
                .webview
                .borrow()
                .as_ref()
                .is_some_and(|active| active == webview);
        if !current {
            self.note_stale_callback(kind);
        }
        current
    }

    fn note_stale_callback(&self, kind: &str) {
        self.stale_callbacks_ignored
            .set(self.stale_callbacks_ignored.get().saturating_add(1));
        eprintln!(
            "ignored stale D0A-02 callback: kind={kind}, active_generation={}",
            self.generation.get()
        );
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
        if self.failure.borrow().is_some() {
            self.finish_failure();
            return;
        }

        // D2I owns exactly one fault injector: the privileged, qualification
        // only systemd helper.  The runtime publishes an identity-bound arm
        // request and then waits for the helper's signed-by-convention
        // SIGKILL receipt before observing termination.  Keeping the dispatch
        // outside this process avoids racing two independent injectors.
        if self.fault_selected.get().is_some() && !self.signal_sent.get() {
            self.observe_external_crash_dispatch();
            return;
        }

        if self.exact_termination_observed.get()
            && self.old_process_absent.get()
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

        if self.generation.get() == 2
            && self.load_complete.get()
            && self.frame_ready.get() > 0
            && self.replacement_process.get().is_none()
        {
            if !self.observe_replacement_process() {
                return;
            }
        }

        if self.load_complete.get()
            && self.frame_ready.get() > 0
            && (self.generation.get() == 1 || self.replacement_process.get().is_some())
        {
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
            && self.native_pointer_events.get() > 0
            && self.native_button_events.get() >= 2
            && self.native_wheel_events.get() > 0
            && self.native_keyboard_events.get() >= 2
            && !self.synthetic_ime_sent.get()
        {
            self.send_synthetic_ime();
            return;
        }

        if self.generation.get() == 1
            && self.synthetic_ime_sent.get()
            && self.settled.get()
            && !self.page_evidence_requested.get()
        {
            self.request_page_evidence();
            return;
        }

        if self.generation.get() == 1
            && self.initial_page_evidence.borrow().is_some()
            && self.popup_denied.get() > 0
            && self.navigation_denied.get() > 0
            && self.input_method_controls.get() > 0
            && self.fault_selected.get().is_none()
        {
            self.arm_external_content_crash();
            return;
        }

        if self.generation.get() == 2
            && self.workspace_screenshot_saved.get()
            && !self.page_evidence_requested.get()
        {
            self.request_page_evidence();
            return;
        }
        if self.generation.get() == 2 && self.recovery_page_evidence.borrow().is_some() {
            self.finish_success();
        }
    }

    fn request_content_screenshot(self: &Rc<Self>) {
        self.content_screenshot_requested.set(true);
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("missing WebView while requesting screenshot");
            return;
        };
        let expected_webview = webview.clone();
        let generation = self.generation.get();
        let state = self.clone();
        webview.take_screenshot(None, move |result| {
            if !state.callback_is_current(generation, &expected_webview, "screenshot") {
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
        let expected_webview = webview.clone();
        let generation = self.generation.get();
        let state = self.clone();
        webview.evaluate_javascript(
            "document.getElementById('field').focus(); document.activeElement.id === 'field'",
            move |result| {
                if !state.callback_is_current(generation, &expected_webview, "focus-evaluation") {
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
        for event in events {
            webview.notify_input_event(InputEvent::Ime(ImeEvent::Composition(event)));
        }
        self.synthetic_ime_sent.set(true);
        self.settled.set(false);
        let proxy = self.proxy.clone();
        let generation = self.generation.get();
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(800));
            let _ = proxy.send_event(AppEvent::Settled { generation });
        });
    }

    fn request_page_evidence(self: &Rc<Self>) {
        self.page_evidence_requested.set(true);
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("missing WebView while reading fixture evidence");
            return;
        };
        let expected_webview = webview.clone();
        let state = self.clone();
        let generation = self.generation.get();
        webview.evaluate_javascript("JSON.stringify(window.__heptaEvidence)", move |result| {
            if !state.callback_is_current(generation, &expected_webview, "page-evidence") {
                return;
            }
            match result {
                Ok(JSValue::String(value)) => {
                    if generation == 1 {
                        *state.initial_page_evidence.borrow_mut() = Some(value);
                    } else if generation == 2 {
                        *state.recovery_page_evidence.borrow_mut() = Some(value);
                    } else {
                        state.fail("page evidence arrived for an unsupported generation");
                        return;
                    }
                    let _ = state.proxy.send_event(AppEvent::Drive);
                }
                other => state.fail(&format!("fixture evidence evaluation failed: {other:?}")),
            }
        });
    }

    fn arm_external_content_crash(&self) {
        if self.external_fault_armed.get() {
            return;
        }
        let processes = match exact_active_content_processes() {
            Ok(processes) => processes,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        let selected = match processes.as_slice() {
            [process] => process.identity,
            [] => {
                self.fail("no exact active direct --content-process child was found");
                return;
            }
            _ => {
                self.fail(&format!(
                    "multiple exact active direct --content-process children were found: {processes:?}"
                ));
                return;
            }
        };
        if let Err(error) =
            self.write_process_topology("process-topology-pre-fault.json", &processes)
        {
            self.fail(&error);
            return;
        }
        self.fault_selected.set(Some(selected));

        let current_identity = match exact_content_process_identity(selected.pid) {
            Ok(identity) => identity,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        if current_identity != selected {
            self.fail("selected content-process identity changed before SIGKILL dispatch");
            return;
        }
        if let Err(error) = write_atomic(
            &self.output_dir.join("content-process-identity.json"),
            &process_identity_json(selected, 1),
        ) {
            self.fail(&format!(
                "could not record selected content-process identity: {error}"
            ));
            return;
        }
        if let Err(error) = write_atomic(&self.output_dir.join("content-crash-ready"), "ready\n") {
            self.fail(&format!(
                "could not publish exact content-process crash marker: {error}"
            ));
            return;
        }
        self.external_fault_armed.set(true);
        eprintln!(
            "D2I external content-process crash armed: pid={}, start_time={}",
            selected.pid, selected.start_time
        );
    }

    fn observe_external_crash_dispatch(self: &Rc<Self>) {
        let Some(selected) = self.fault_selected.get() else {
            self.fail("external crash dispatch was observed without a selected identity");
            return;
        };
        let receipt_path = self.output_dir.join("content-sigkill-sent.json");
        let receipt = match fs::read_to_string(&receipt_path) {
            Ok(receipt) => receipt,
            Err(error) if error.kind() == ErrorKind::NotFound => {
                self.schedule_drive_probe();
                return;
            }
            Err(error) => {
                self.fail(&format!("could not read external SIGKILL receipt: {error}"));
                return;
            }
        };
        if !receipt_matches_identity(&receipt, selected) {
            self.fail("external SIGKILL receipt did not match the armed process identity");
            return;
        }
        self.signal_sent.set(true);
        self.start_termination_observer(selected);
        let _ = self.proxy.send_event(AppEvent::Drive);
    }

    fn start_termination_observer(&self, selected: ProcessIdentity) {
        if self.termination_observer_started.replace(true) {
            return;
        }
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let stat_path = format!("/proc/{}/stat", selected.pid);
            let deadline =
                Instant::now() + Duration::from_secs(PROCESS_OBSERVATION_TIMEOUT_SECONDS);
            loop {
                match fs::read_to_string(&stat_path) {
                    Err(error) if error.kind() == ErrorKind::NotFound => {
                        let _ = proxy.send_event(AppEvent::ContentProcessTerminated {
                            generation: 1,
                            identity: selected,
                        });
                        break;
                    }
                    Err(error) => {
                        let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed {
                            generation: 1,
                            message: format!(
                                "could not observe exact content-process termination: {error}"
                            ),
                        });
                        break;
                    }
                    Ok(stat) => {
                        let observed_start_time = match proc_start_time(&stat) {
                            Some(start_time) => start_time,
                            None => {
                                let _ = proxy.send_event(
                                    AppEvent::ContentProcessTerminationFailed {
                                        generation: 1,
                                        message: "could not parse exact content-process start time while observing termination".to_owned(),
                                    },
                                );
                                break;
                            }
                        };
                        if observed_start_time != selected.start_time {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed {
                                generation: 1,
                                message: format!(
                                    "content-process PID identity changed before absence was observed: pid={}, expected_start_time={}, observed_start_time={observed_start_time}",
                                    selected.pid, selected.start_time
                                ),
                            });
                            break;
                        }
                        if Instant::now() >= deadline {
                            let state = proc_state(&stat).unwrap_or('?');
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed {
                                generation: 1,
                                message: format!(
                                    "exact content-process /proc identity remained after SIGKILL timeout: pid={}, start_time={}, state={state}",
                                    selected.pid, selected.start_time
                                ),
                            });
                            break;
                        }
                        thread::sleep(Duration::from_millis(10));
                    }
                }
            }
        });
    }

    fn observe_exact_termination(&self, generation: u32, identity: ProcessIdentity) {
        if generation != 1 || self.generation.get() != 1 || self.recovery_started.get() {
            self.note_stale_callback("exact-termination");
            return;
        }
        if !self.signal_sent.get() {
            self.fail("content-process termination arrived before successful SIGKILL dispatch");
            return;
        }
        if self.fault_selected.get() != Some(identity) {
            self.fail(
                "content-process termination identity did not match the selected fault target",
            );
            return;
        }
        if self.exact_termination_observed.replace(true) {
            self.fail("duplicate exact content-process termination observation");
            return;
        }
        let processes = match exact_active_content_processes() {
            Ok(processes) => processes,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        if !processes.is_empty() {
            self.fail(&format!(
                "an active content process existed before explicit recovery: {processes:?}"
            ));
            return;
        }
        if let Err(error) =
            self.write_process_topology("process-topology-post-termination.json", &processes)
        {
            self.fail(&error);
            return;
        }
        self.old_process_absent.set(true);
        self.window.request_redraw();
        let _ = self.proxy.send_event(AppEvent::Drive);
    }

    fn start_recovery(self: &Rc<Self>) {
        if !self.signal_sent.get()
            || !self.exact_termination_observed.get()
            || !self.old_process_absent.get()
        {
            self.fail("recovery attempted before all fault-causality evidence was present");
            return;
        }
        if let Err(error) = self.invalidate_current_webview() {
            self.fail(&error);
            return;
        }
        self.recovery_started.set(true);
        *self.recovery_started_at.borrow_mut() = Some(Instant::now());
        self.generation.set(2);
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

    fn observe_replacement_process(&self) -> bool {
        let processes = match exact_active_content_processes() {
            Ok(processes) => processes,
            Err(error) => {
                self.fail(&error);
                return false;
            }
        };
        match processes.as_slice() {
            [process] => {
                let Some(old) = self.fault_selected.get() else {
                    self.fail("replacement process appeared without a selected old identity");
                    return false;
                };
                let replacement = process.identity;
                if replacement == old || replacement.pid == old.pid {
                    self.fail("replacement content process reused the old PID identity");
                    return false;
                }
                if let Err(error) =
                    self.write_process_topology("process-topology-post-recovery.json", &processes)
                {
                    self.fail(&error);
                    return false;
                }
                self.replacement_process.set(Some(replacement));
                true
            }
            [] => {
                let timed_out = self
                    .recovery_started_at
                    .borrow()
                    .as_ref()
                    .is_some_and(|started| {
                        started.elapsed()
                            >= Duration::from_secs(PROCESS_OBSERVATION_TIMEOUT_SECONDS)
                    });
                if timed_out {
                    self.fail("no replacement content process appeared after recovery");
                } else {
                    self.schedule_drive_probe();
                }
                false
            }
            _ => {
                self.fail(&format!(
                    "multiple active content processes existed after recovery: {processes:?}"
                ));
                false
            }
        }
    }

    fn schedule_drive_probe(&self) {
        if self.replacement_probe_scheduled.replace(true) {
            return;
        }
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(EXTERNAL_FAULT_POLL_MILLISECONDS));
            let _ = proxy.send_event(AppEvent::Drive);
        });
    }

    fn write_process_topology(
        &self,
        name: &str,
        processes: &[ObservedProcess],
    ) -> Result<(), String> {
        let mut rows = String::new();
        for (index, process) in processes.iter().enumerate() {
            if index > 0 {
                rows.push_str(",\n");
            }
            rows.push_str(&format!(
                "    {{\"parent_pid\":{},\"pid\":{},\"start_time\":{},\"state\":{}}}",
                process.parent_pid,
                process.identity.pid,
                process.identity.start_time,
                json_string(&process.state.to_string())
            ));
        }
        let report = format!(
            "{{\n  \"active_process_count\": {},\n  \"embedder_pid\": {},\n  \"processes\": [\n{}\n  ]\n}}\n",
            processes.len(),
            std::process::id(),
            rows
        );
        fs::write(self.output_dir.join(name), report)
            .map_err(|error| format!("could not write {name}: {error}"))
    }

    fn compose(self: &Rc<Self>) {
        if self.completed.get() {
            return;
        }
        if let Err(error) = self.parent_context.make_current() {
            self.fail(&format!("could not make parent context current: {error:?}"));
            return;
        }

        if !self.exact_termination_observed.get() || self.recovery_started.get() {
            if let Some(webview) = self.webview.borrow().as_ref() {
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

        if self.exact_termination_observed.get() && !self.recovery_started.get() {
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
            if self.exact_termination_observed.get() && !self.recovery_started.get() {
                [0.95, 0.36, 0.16, 1.0]
            } else {
                [0.10, 0.72, 0.36, 1.0]
            },
        );

        if self.exact_termination_observed.get()
            && self.old_process_absent.get()
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
        if position.y < CHROME_HEIGHT as f64 {
            return;
        }
        let point = DevicePoint::new(
            position.x as f32,
            (position.y - CHROME_HEIGHT as f64) as f32,
        );
        self.last_content_point.set(point);
        self.native_pointer_events
            .set(self.native_pointer_events.get() + 1);
        if let Some(webview) = self.webview.borrow().as_ref() {
            webview.notify_input_event(InputEvent::MouseMove(MouseMoveEvent::new(point.into())));
        }
    }

    fn forward_mouse_button(&self, state: ElementState, button: MouseButton) {
        let button = match button {
            MouseButton::Left => ServoMouseButton::Primary,
            MouseButton::Right => ServoMouseButton::Secondary,
            MouseButton::Middle => ServoMouseButton::Auxiliary,
            MouseButton::Back => ServoMouseButton::Back,
            MouseButton::Forward => ServoMouseButton::Forward,
            MouseButton::Other(value) => ServoMouseButton::Other(value),
        };
        let action = match state {
            ElementState::Pressed => MouseButtonAction::Down,
            ElementState::Released => MouseButtonAction::Up,
        };
        self.native_button_events
            .set(self.native_button_events.get() + 1);
        if let Some(webview) = self.webview.borrow().as_ref() {
            webview.notify_input_event(InputEvent::MouseButton(MouseButtonEvent::new(
                action,
                button,
                self.last_content_point.get().into(),
            )));
        }
    }

    fn forward_wheel(&self, delta: MouseScrollDelta) {
        let (x, y, mode) = match delta {
            MouseScrollDelta::LineDelta(x, y) => {
                (x as f64 * 40.0, y as f64 * 40.0, WheelMode::DeltaLine)
            }
            MouseScrollDelta::PixelDelta(position) => {
                (position.x, position.y, WheelMode::DeltaPixel)
            }
        };
        self.native_wheel_events
            .set(self.native_wheel_events.get() + 1);
        if let Some(webview) = self.webview.borrow().as_ref() {
            webview.notify_input_event(InputEvent::Wheel(WheelEvent::new(
                WheelDelta { x, y, z: 0.0, mode },
                self.last_content_point.get().into(),
            )));
        }
    }

    fn forward_keyboard(&self, event: winit::event::KeyEvent) {
        let key = match event.logical_key {
            WinitKey::Character(value) => Key::Character(value.to_string()),
            WinitKey::Named(WinitNamedKey::Enter) => Key::Named(NamedKey::Enter),
            WinitKey::Named(WinitNamedKey::Tab) => Key::Named(NamedKey::Tab),
            WinitKey::Named(WinitNamedKey::Backspace) => Key::Named(NamedKey::Backspace),
            _ => Key::Named(NamedKey::Unidentified),
        };
        let key_state = match event.state {
            ElementState::Pressed => KeyState::Down,
            ElementState::Released => KeyState::Up,
        };
        self.native_keyboard_events
            .set(self.native_keyboard_events.get() + 1);
        if let Some(webview) = self.webview.borrow().as_ref() {
            webview.notify_input_event(InputEvent::Keyboard(KeyboardEvent::from_state_and_key(
                key_state, key,
            )));
        }
    }

    fn forward_native_ime(&self, event: Ime) {
        self.native_ime_events.set(self.native_ime_events.get() + 1);
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            return;
        };
        let input = match event {
            Ime::Enabled => Some(ImeEvent::Composition(CompositionEvent {
                state: CompositionState::Start,
                data: String::new(),
            })),
            Ime::Preedit(data, _) => Some(ImeEvent::Composition(CompositionEvent {
                state: CompositionState::Update,
                data,
            })),
            Ime::Commit(data) => Some(ImeEvent::Composition(CompositionEvent {
                state: CompositionState::End,
                data,
            })),
            Ime::Disabled => Some(ImeEvent::Dismissed),
        };
        if let Some(input) = input {
            webview.notify_input_event(InputEvent::Ime(input));
        }
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
                "  \"schema\": \"trillionnium.desktop.d0a02-runtime-state.v2\",\n",
                "  \"generation\": {},\n",
                "  \"logical_webviews_created\": {},\n",
                "  \"logical_webviews_invalidated\": {},\n",
                "  \"logical_webviews_live\": {},\n",
                "  \"logical_webviews_peak\": {},\n",
                "  \"stale_callbacks_ignored\": {},\n",
                "  \"load_complete\": {},\n",
                "  \"frame_ready\": {},\n",
                "  \"fault_selected\": {},\n",
                "  \"signal_sent\": {},\n",
                "  \"exact_termination_observed\": {},\n",
                "  \"old_process_absent\": {},\n",
                "  \"servo_crash_callback_observed\": {},\n",
                "  \"replacement_process\": {},\n",
                "  \"failure\": {}\n",
                "}}\n"
            ),
            self.generation.get(),
            self.logical_webviews_created.get(),
            self.logical_webviews_invalidated.get(),
            self.logical_webviews_live.get(),
            self.logical_webviews_peak.get(),
            self.stale_callbacks_ignored.get(),
            self.load_complete.get(),
            self.frame_ready.get(),
            optional_process_identity_json(self.fault_selected.get(), 1),
            self.signal_sent.get(),
            self.exact_termination_observed.get(),
            self.old_process_absent.get(),
            self.servo_crash_callback_observed.get(),
            optional_process_identity_json(self.replacement_process.get(), 2),
            json_string(&failure),
        );
        let _ = fs::write(self.output_dir.join("runtime-state.json"), state_report);
        let report = format!(
            "{{\n  \"schema\": \"trillionnium.desktop.d0a02-headed-runtime.v2\",\n  \"status\": \"FAIL\",\n  \"failure\": {},\n  \"servo_started\": true,\n  \"product_ready\": false\n}}\n",
            json_string(&failure)
        );
        if let Err(error) = self.write_runtime_reports(&report) {
            eprintln!("could not write D2I runtime failure evidence: {error}");
        }
        let _ = self.proxy.send_event(AppEvent::Exit(1));
    }

    fn write_runtime_reports(&self, report: &str) -> Result<(), String> {
        fs::write(self.output_dir.join("runtime-result.json"), report)
            .map_err(|error| format!("could not write runtime-result.json: {error}"))?;
        // D2I's guest acceptance consumes the stable runtime-ready name while
        // the host-only D0A-02 gate retains runtime-result.json.  Both files
        // carry identical bytes so neither path can silently diverge.
        fs::write(self.output_dir.join("runtime-ready.json"), report)
            .map_err(|error| format!("could not write runtime-ready.json: {error}"))?;
        Ok(())
    }

    fn success_invariant_error(&self) -> Option<String> {
        let Some(old) = self.fault_selected.get() else {
            return Some("fault target identity is missing".to_owned());
        };
        let Some(replacement) = self.replacement_process.get() else {
            return Some("replacement process identity is missing".to_owned());
        };
        let checks = [
            (self.generation.get() == 2, "active generation is not 2"),
            (
                self.logical_webviews_created.get() == 2,
                "logical WebView create count is not 2",
            ),
            (
                self.logical_webviews_invalidated.get() == 1,
                "logical WebView invalidation count is not 1",
            ),
            (
                self.logical_webviews_live.get() == 1,
                "logical WebView live count is not 1",
            ),
            (
                self.logical_webviews_peak.get() == 1,
                "logical WebView peak is not 1",
            ),
            (self.signal_sent.get(), "SIGKILL was not recorded as sent"),
            (
                self.exact_termination_observed.get(),
                "exact process termination was not observed",
            ),
            (
                self.old_process_absent.get(),
                "old process absence was not observed",
            ),
            (
                old.pid != replacement.pid && old != replacement,
                "replacement process identity is not distinct",
            ),
            (
                self.recovery_page_evidence.borrow().is_some(),
                "generation-2 page evidence is missing",
            ),
            (
                self.chrome_initial_ok.get()
                    && self.chrome_crash_ok.get()
                    && self.chrome_recovery_ok.get(),
                "trusted chrome pixel evidence is incomplete",
            ),
        ];
        checks
            .into_iter()
            .find_map(|(ok, message)| (!ok).then(|| message.to_owned()))
    }

    fn finish_success(&self) {
        if let Some(error) = self.success_invariant_error() {
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
        let crash_callback_reason = self
            .servo_crash_callback_reason
            .borrow()
            .clone()
            .unwrap_or_default();
        let selected = self
            .fault_selected
            .get()
            .expect("validated selected identity");
        let replacement = self
            .replacement_process
            .get()
            .expect("validated replacement identity");
        let report = format!(
            concat!(
                "{{\n",
                "  \"schema\": \"trillionnium.desktop.d0a02-headed-runtime.v2\",\n",
                "  \"status\": \"PASS_HEADED_LOCAL_FIXTURE_ONLY\",\n",
                "  \"servo_commit\": \"670ae8a70801b162e186f81cbb5bdd2d59c39108\",\n",
                "  \"window_created\": true,\n",
                "  \"trusted_chrome_separate_from_content\": true,\n",
                "  \"callback_identity_enforced\": true,\n",
                "  \"stale_callbacks_ignored\": {},\n",
                "  \"logical_content_webview_peak\": {},\n",
                "  \"logical_webviews_created\": {},\n",
                "  \"logical_webviews_invalidated\": {},\n",
                "  \"logical_webviews_live_at_result\": {},\n",
                "  \"initial_generation\": 1,\n",
                "  \"recovery_generation\": 2,\n",
                "  \"content_surface_limit\": 1,\n",
                "  \"content_generation\": 2,\n",
                "  \"page_input_verified\": true,\n",
                "  \"ime_path_exercised\": true,\n",
                "  \"ime_composition_events_sent\": 3,\n",
                "  \"external_network_used\": false,\n",
                "  \"chrome_initial_pixels_verified\": {},\n",
                "  \"chrome_crash_pixels_verified\": {},\n",
                "  \"chrome_recovery_pixels_verified\": {},\n",
                "  \"native_pointer_events\": {},\n",
                "  \"native_button_events\": {},\n",
                "  \"native_wheel_events\": {},\n",
                "  \"native_keyboard_events\": {},\n",
                "  \"native_ime_events\": {},\n",
                "  \"window_resize_events\": {},\n",
                "  \"synthetic_ime_composition_events\": 3,\n",
                "  \"input_handled_callbacks\": {},\n",
                "  \"input_method_controls\": {},\n",
                "  \"popup_requests_denied\": {},\n",
                "  \"external_navigation_requests_denied\": {},\n",
                "  \"fault_injection\": {{\n",
                "    \"generation\": 1,\n",
                "    \"mechanism\": \"external_SIGKILL\",\n",
                "    \"selected_pid\": {},\n",
                "    \"selected_start_time\": {},\n",
                "    \"signal_sent\": true,\n",
                "    \"exact_termination_observed\": true,\n",
                "    \"old_process_absent\": true,\n",
                "    \"servo_pipeline_panic_callback_required\": false,\n",
                "    \"servo_pipeline_panic_callback_observed\": {},\n",
                "    \"servo_pipeline_panic_callback_reason\": {}\n",
                "  }},\n",
                "  \"replacement_process\": {{\n",
                "    \"generation\": 2,\n",
                "    \"pid\": {},\n",
                "    \"start_time\": {},\n",
                "    \"distinct_from_fault_target\": true\n",
                "  }},\n",
                "  \"process_topology\": {{\n",
                "    \"pre_fault\": \"process-topology-pre-fault.json\",\n",
                "    \"post_termination\": \"process-topology-post-termination.json\",\n",
                "    \"post_recovery\": \"process-topology-post-recovery.json\"\n",
                "  }},\n",
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
                "    \"clipboard_path_claimed\": false,\n",
                "    \"clean_runtime_teardown_claimed\": false,\n",
                "    \"product_ready\": false\n",
                "  }}\n",
                "}}\n"
            ),
            self.stale_callbacks_ignored.get(),
            self.logical_webviews_peak.get(),
            self.logical_webviews_created.get(),
            self.logical_webviews_invalidated.get(),
            self.logical_webviews_live.get(),
            self.chrome_initial_ok.get(),
            self.chrome_crash_ok.get(),
            self.chrome_recovery_ok.get(),
            self.native_pointer_events.get(),
            self.native_button_events.get(),
            self.native_wheel_events.get(),
            self.native_keyboard_events.get(),
            self.native_ime_events.get(),
            self.window_resize_events.get(),
            self.input_handled_callbacks.get(),
            self.input_method_controls.get(),
            self.popup_denied.get(),
            self.navigation_denied.get(),
            selected.pid,
            selected.start_time,
            self.servo_crash_callback_observed.get(),
            json_string(&crash_callback_reason),
            replacement.pid,
            replacement.start_time,
            initial,
            recovery,
        );
        if let Err(error) = self.write_runtime_reports(&report) {
            eprintln!("could not write D0A-02 runtime result: {error}");
            let _ = self.proxy.send_event(AppEvent::Exit(1));
            return;
        }
        let _ = self.proxy.send_event(AppEvent::Exit(0));
    }
}

struct RuntimeDelegate {
    state: Weak<RuntimeState>,
    generation: u32,
}

impl RuntimeDelegate {
    fn with_current<F>(&self, webview: &WebView, kind: &str, callback: F)
    where
        F: FnOnce(&RuntimeState),
    {
        if let Some(state) = self.state.upgrade()
            && state.callback_is_current(self.generation, webview, kind)
        {
            callback(&state);
        }
    }
}

impl WebViewDelegate for RuntimeDelegate {
    fn notify_load_status_changed(&self, webview: WebView, status: LoadStatus) {
        self.with_current(&webview, "load-status", |state| {
            state.load_complete.set(status == LoadStatus::Complete);
            let _ = state.proxy.send_event(AppEvent::Drive);
        });
    }

    fn notify_new_frame_ready(&self, webview: WebView) {
        self.with_current(&webview, "new-frame", |state| {
            state.frame_ready.set(state.frame_ready.get() + 1);
            state.window.request_redraw();
        });
    }

    fn notify_input_event_handled(
        &self,
        webview: WebView,
        _event_id: InputEventId,
        _result: InputEventResult,
    ) {
        self.with_current(&webview, "input-handled", |state| {
            state
                .input_handled_callbacks
                .set(state.input_handled_callbacks.get() + 1);
            let _ = state.proxy.send_event(AppEvent::Drive);
        });
    }

    // Servo defines this callback for a pipeline panic. External SIGKILL of the
    // multiprocess content child is proved independently by exact PID/start-time
    // selection, successful signal dispatch, /proc disappearance, zero-child
    // topology, trusted-chrome survival, and a distinct replacement identity.
    fn notify_crashed(&self, webview: WebView, reason: String, _backtrace: Option<String>) {
        let Some(state) = self.state.upgrade() else {
            return;
        };
        if !state.callback_is_current(self.generation, &webview, "crash") {
            return;
        }
        if self.generation != 1 {
            state.fail("current generation 2 emitted an unexpected crash callback");
            return;
        }
        if state.fault_selected.get().is_none() {
            state.fail("Servo crash callback arrived before external fault was armed");
            return;
        }
        // The helper writes the SIGKILL receipt immediately after dispatch.
        // Servo may deliver notify_crashed on the event loop before that
        // receipt is observed, so retain the callback and let the causal
        // receipt gate establish ordering without treating this harmless
        // scheduling race as a second injector.
        if !state.signal_sent.get() {
            eprintln!("Servo crash callback observed while awaiting external SIGKILL receipt");
        }
        if state.servo_crash_callback_observed.replace(true) {
            state.fail("duplicate current-generation Servo crash callback");
            return;
        }
        *state.servo_crash_callback_reason.borrow_mut() = Some(reason);
        state.window.request_redraw();
        let _ = state.proxy.send_event(AppEvent::Drive);
    }

    fn request_navigation(&self, webview: WebView, request: NavigationRequest) {
        let Some(state) = self.state.upgrade() else {
            request.deny();
            return;
        };
        if !state.callback_is_current(self.generation, &webview, "navigation") {
            request.deny();
            return;
        }
        if state.fixture_origin_matches(&request.url) {
            request.allow();
        } else {
            state
                .navigation_denied
                .set(state.navigation_denied.get() + 1);
            request.deny();
        }
        let _ = state.proxy.send_event(AppEvent::Drive);
    }

    fn request_create_new(&self, parent: WebView, _request: CreateNewWebViewRequest) {
        self.with_current(&parent, "create-new", |state| {
            state.popup_denied.set(state.popup_denied.get() + 1);
            let _ = state.proxy.send_event(AppEvent::Drive);
        });
        // Dropping the request returns no auxiliary WebView.
    }

    fn show_embedder_control(&self, webview: WebView, control: EmbedderControl) {
        self.with_current(&webview, "embedder-control", |state| {
            if matches!(control, EmbedderControl::InputMethod(_)) {
                state
                    .input_method_controls
                    .set(state.input_method_controls.get() + 1);
            }
            let _ = state.proxy.send_event(AppEvent::Drive);
        });
    }
}

fn exact_active_content_processes() -> Result<Vec<ObservedProcess>, String> {
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
        let state = match proc_state(&stat) {
            Some(state) if state != 'Z' => state,
            _ => continue,
        };
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
        if !has_content_process_flag {
            continue;
        }
        let Some(start_time) = proc_start_time(&stat) else {
            return Err(format!(
                "could not parse exact content-process start time for pid {pid}"
            ));
        };
        candidates.push(ObservedProcess {
            identity: ProcessIdentity { pid, start_time },
            parent_pid,
            state,
        });
    }
    candidates.sort_by_key(|process| (process.identity.pid, process.identity.start_time));
    Ok(candidates)
}

fn exact_content_process_identity(pid: u32) -> Result<ProcessIdentity, String> {
    let stat = fs::read_to_string(format!("/proc/{pid}/stat"))
        .map_err(|error| format!("could not read exact content-process identity: {error}"))?;
    let start_time = proc_start_time(&stat)
        .ok_or_else(|| "could not parse exact content-process start time".to_owned())?;
    Ok(ProcessIdentity { pid, start_time })
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

fn process_identity_json(identity: ProcessIdentity, generation: u32) -> String {
    format!(
        "{{\"generation\":{generation},\"pid\":{},\"start_time\":{}}}\n",
        identity.pid, identity.start_time
    )
}

fn write_atomic(path: &Path, contents: &str) -> Result<(), String> {
    let temporary = path.with_extension(format!(
        "{}tmp-{}",
        path.extension()
            .and_then(|extension| extension.to_str())
            .map(|extension| format!("{extension}."))
            .unwrap_or_default(),
        std::process::id()
    ));
    fs::write(&temporary, contents)
        .map_err(|error| format!("could not write {}: {error}", temporary.display()))?;
    fs::rename(&temporary, path).map_err(|error| {
        let _ = fs::remove_file(&temporary);
        format!("could not publish {}: {error}", path.display())
    })
}

fn receipt_matches_identity(receipt: &str, identity: ProcessIdentity) -> bool {
    let expected = format!(
        "{{\"generation\":1,\"pid\":{},\"signal\":\"SIGKILL\",\"start_time\":{}}}",
        identity.pid, identity.start_time
    );
    receipt.lines().any(|line| line.trim() == expected)
}

fn optional_process_identity_json(identity: Option<ProcessIdentity>, generation: u32) -> String {
    identity
        .map(|identity| {
            process_identity_json(identity, generation)
                .trim()
                .to_owned()
        })
        .unwrap_or_else(|| "null".to_owned())
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
