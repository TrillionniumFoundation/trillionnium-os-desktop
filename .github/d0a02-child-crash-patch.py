from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one replacement target, found {count}: {old!r}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


source = Path("experiments/servo-headed-runtime/src/main.rs")
replace_once(
    source,
    "    ServoBuilder, WebView, WebViewBuilder, WebViewDelegate, WheelDelta, WheelEvent, WheelMode,\n"
    "    WindowRenderingContext, run_content_process,\n",
    "    ServoBuilder, WebView, WebViewBuilder, WebViewDelegate, WheelDelta, WheelEvent, WheelMode,\n"
    "    WindowRenderingContext, run_content_process,\n",
)
replace_once(
    source,
    "    NavigationRequest, OffscreenRenderingContext, Opts, Preferences, RenderingContext, Servo,\n",
    "    NavigationRequest, OffscreenRenderingContext, Opts, RenderingContext, Servo,\n",
)
replace_once(
    source,
    """        let mut preferences = Preferences::default();
        preferences.dom_servo_helpers_enabled = true;

        let servo = ServoBuilder::default()
            .opts(opts)
            .preferences(preferences)
            .event_loop_waker(Box::new(waker))
            .build();
""",
    """        let servo = ServoBuilder::default()
            .opts(opts)
            .event_loop_waker(Box::new(waker))
            .build();
""",
)
replace_once(
    source,
    """    fn trigger_content_crash(self: &Rc<Self>) {
        self.crash_triggered.set(true);
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("missing WebView while triggering test-only content panic");
            return;
        };
        webview.evaluate_javascript("ServoTestUtils.panic()", |_result| {});
    }
""",
    """    fn trigger_content_crash(self: &Rc<Self>) {
        self.crash_triggered.set(true);
        if let Err(error) = fs::write(self.output_dir.join("content-crash-ready"), "ready\\n") {
            self.fail(&format!(
                "could not publish exact content-process crash marker: {error}"
            ));
        }
    }
""",
)
