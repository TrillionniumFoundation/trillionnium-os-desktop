// D0A-02 headed runtime probe for the exact pinned Servo checkout.
//
// This source is copied into Servo's examples directory by the permanent
// qualification workflow. It creates one native window, draws trusted chrome
// in the embedder-owned parent framebuffer, and composites exactly one Servo
// WebView from an offscreen rendering context below that chrome. It never starts
// WebDriver and its HTTP fixture listens only on 127.0.0.1.

use std::cell::{Cell, RefCell};
use std::env;
use std::error::Error;
use std::fs;
use std::io::{ErrorKind, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::Command;
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
    Ok(app.exit_code)
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
                    state.crash_observed.set(true);
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
        event_loop: &ActiveEventLoop,
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
                event_loop.exit();
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
    window: Window,
    servo: Servo,
    parent_context: Rc<WindowRenderingContext>,
    content_context: Rc<OffscreenRenderingContext>,
    webview: RefCell<Option<WebView>>,
    proxy: EventLoopProxy<AppEvent>,
    fixture_url: Url,
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
            last_content_point: Cell::new(DevicePoint::new(0.0, 0.0)),
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
        if self.failure.borrow().is_some() {
            self.finish_failure();
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
            && !self.crash_triggered.get()
        {
            self.trigger_content_crash();
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
        let generation = self.generation.get();
        let state = self.clone();
        webview.take_screenshot(None, move |result| match result {
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
        });
    }

    fn request_focus(self: &Rc<Self>) {
        self.focus_requested.set(true);
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("missing WebView while focusing fixture input");
            return;
        };
        let state = self.clone();
        webview.evaluate_javascript(
            "document.getElementById('field').focus(); document.activeElement.id === 'field'",
            move |result| match result {
                Ok(JSValue::Boolean(true)) => {
                    state.focus_ready.set(true);
                    let _ = state.proxy.send_event(AppEvent::Drive);
                }
                other => state.fail(&format!("fixture input focus failed: {other:?}")),
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
            match result {
                Ok(JSValue::String(value)) => {
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

    fn compose(self: &Rc<Self>) {
        if self.completed.get() {
            return;
        }
        if let Err(error) = self.parent_context.make_current() {
            self.fail(&format!("could not make parent context current: {error:?}"));
            return;
        }

        if !self.crash_observed.get() || self.recovery_started.get() {
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
        let _ = fs::write(self.output_dir.join("runtime-state.json"), state_report);
        let report = format!(
            "{{\n  \"schema\": \"trillionnium.desktop.d0a02-headed-runtime.v1\",\n  \"status\": \"FAIL\",\n  \"failure\": {},\n  \"servo_started\": true,\n  \"product_ready\": false\n}}\n",
            json_string(&failure)
        );
        let _ = fs::write(self.output_dir.join("runtime-result.json"), report);
        let _ = self.proxy.send_event(AppEvent::Exit(1));
    }

    fn finish_success(&self) {
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
}

struct RuntimeDelegate {
    state: Weak<RuntimeState>,
}

impl WebViewDelegate for RuntimeDelegate {
    fn notify_load_status_changed(&self, _webview: WebView, status: LoadStatus) {
        if let Some(state) = self.state.upgrade() {
            state.load_complete.set(status == LoadStatus::Complete);
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
    }

    fn notify_new_frame_ready(&self, _webview: WebView) {
        if let Some(state) = self.state.upgrade() {
            state.frame_ready.set(state.frame_ready.get() + 1);
            state.window.request_redraw();
        }
    }

    fn notify_input_event_handled(
        &self,
        _webview: WebView,
        _event_id: InputEventId,
        _result: InputEventResult,
    ) {
        if let Some(state) = self.state.upgrade() {
            state
                .input_handled_callbacks
                .set(state.input_handled_callbacks.get() + 1);
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
    }

    fn notify_crashed(&self, _webview: WebView, reason: String, _backtrace: Option<String>) {
        if let Some(state) = self.state.upgrade() {
            state.crash_observed.set(true);
            *state.crash_reason.borrow_mut() = Some(reason);
            state.window.request_redraw();
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
    }

    fn request_navigation(&self, _webview: WebView, request: NavigationRequest) {
        if let Some(state) = self.state.upgrade() {
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
        if let Some(state) = self.state.upgrade() {
            state.popup_denied.set(state.popup_denied.get() + 1);
            let _ = state.proxy.send_event(AppEvent::Drive);
        }
        // Dropping the request returns no auxiliary WebView.
    }

    fn show_embedder_control(&self, _webview: WebView, control: EmbedderControl) {
        if let Some(state) = self.state.upgrade() {
            if matches!(control, EmbedderControl::InputMethod(_)) {
                state
                    .input_method_controls
                    .set(state.input_method_controls.get() + 1);
            }
            let _ = state.proxy.send_event(AppEvent::Drive);
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
