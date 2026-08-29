from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"expected exactly one replacement in {path}, found {count}: {old[:96]!r}"
        )
    target.write_text(text.replace(old, new, 1))


headed = "experiments/servo-headed-runtime/src/main.rs"
replace_once(
    headed,
    """            AppEvent::Exit(code) => {
                self.exit_code = code;
                event_loop.exit();
            }
""",
    """            AppEvent::Exit(code) => {
                self.exit_code = code;
                if let Some(state) = self.state.take() {
                    state.webview.borrow_mut().take();
                    drop(state);
                }
                event_loop.exit();
            }
""",
)
replace_once(
    headed,
    """struct RuntimeState {
    window: Window,
    servo: Servo,
    parent_context: Rc<WindowRenderingContext>,
    content_context: Rc<OffscreenRenderingContext>,
    webview: RefCell<Option<WebView>>,
""",
    """struct RuntimeState {
    webview: RefCell<Option<WebView>>,
    servo: Servo,
    content_context: Rc<OffscreenRenderingContext>,
    parent_context: Rc<WindowRenderingContext>,
    // The native window must outlive both rendering contexts.
    window: Window,
""",
)
replace_once(
    headed,
    """            WindowEvent::CloseRequested => {
                state.fail("window closed before qualification completed");
                event_loop.exit();
            }
""",
    """            WindowEvent::CloseRequested => {
                state.fail("window closed before qualification completed");
            }
""",
)
replace_once(
    headed,
    """        event_loop: &ActiveEventLoop,
        _window_id: winit::window::WindowId,
        event: WindowEvent,
""",
    """        _event_loop: &ActiveEventLoop,
        _window_id: winit::window::WindowId,
        event: WindowEvent,
""",
)

product = "runtime/servo/hepta_workspace_runtime.rs"
replace_once(
    product,
    """struct RuntimeState {
    window: Window,
    servo: Servo,
    rendering_context: Rc<WindowRenderingContext>,
    webview: RefCell<Option<WebView>>,
""",
    """struct RuntimeState {
    webview: RefCell<Option<WebView>>,
    servo: Servo,
    rendering_context: Rc<WindowRenderingContext>,
    // Keep the native window alive until after Servo and its rendering context.
    window: Window,
""",
)
replace_once(
    product,
    """enum App {
    Initial { waker: Waker, output: PathBuf },
    Running(Rc<RuntimeState>),
}
""",
    """enum App {
    Initial { waker: Waker, output: PathBuf },
    Running(Rc<RuntimeState>),
    Finished,
}
""",
)
replace_once(
    product,
    """    fn new(event_loop: &EventLoop<AppEvent>, output: PathBuf) -> Self {
        Self::Initial {
            waker: Waker::new(event_loop),
            output,
        }
    }
}
""",
    """    fn new(event_loop: &EventLoop<AppEvent>, output: PathBuf) -> Self {
        Self::Initial {
            waker: Waker::new(event_loop),
            output,
        }
    }

    fn shutdown(&mut self, event_loop: &ActiveEventLoop) {
        let previous = std::mem::replace(self, Self::Finished);
        if let Self::Running(state) = previous {
            state.webview.borrow_mut().take();
            drop(state);
        }
        event_loop.exit();
    }
}
""",
)
replace_once(
    product,
    """    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        let Self::Running(state) = self else {
            return;
        };
        state.drive();
        state.window.request_redraw();
        if state.evidence_written.get()
            && (state.output.join("capture.done").is_file()
                || state.started_at.elapsed() > Duration::from_secs(100))
        {
            event_loop.exit();
        }
    }
""",
    """    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        let should_shutdown = {
            let Self::Running(state) = self else {
                return;
            };
            state.drive();
            state.window.request_redraw();
            state.evidence_written.get()
                && (state.output.join("capture.done").is_file()
                    || state.started_at.elapsed() > Duration::from_secs(100))
        };
        if should_shutdown {
            self.shutdown(event_loop);
        }
    }
""",
)

replace_once(
    ".github/workflows/servo-headed-runtime.yml",
    'xdotool mousemove --sync --window "$window_id" 400 132',
    'xdotool mousemove --sync --window "$window_id" 400 164',
)
