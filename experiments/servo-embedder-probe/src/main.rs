// Compile-only external-style API sentinel for Servo
// 670ae8a70801b162e186f81cbb5bdd2d59c39108.
//
// The qualification script copies this file into Servo's examples directory,
// where Cargo builds it as a separate crate under Servo's exact Cargo.lock.
// Nothing in this program is executed by D0A-01.

#![allow(dead_code, unused_imports)]

use std::rc::Rc;

use accesskit::TreeUpdate;
use dpi::PhysicalSize;
use servo::{
    ClipboardDelegate, CompositionEvent, CreateNewWebViewRequest, EmbedderControl, EventLoopWaker,
    InputEvent, InputMethodControl, LoadStatus, NavigationRequest, RenderingContext, Servo,
    ServoBuilder, ServoDelegate, WebResourceLoad, WebView, WebViewBuilder, WebViewDelegate,
    WebViewRect, WindowRenderingContext,
};
use url::Url;

#[derive(Clone)]
struct ProbeWaker;

impl EventLoopWaker for ProbeWaker {
    fn clone_box(&self) -> Box<dyn EventLoopWaker> {
        Box::new(self.clone())
    }

    fn wake(&self) {}
}

struct ProbeServoDelegate;
impl ServoDelegate for ProbeServoDelegate {}

struct ProbeWebViewDelegate;

impl WebViewDelegate for ProbeWebViewDelegate {
    fn notify_url_changed(&self, _webview: WebView, _url: Url) {}

    fn notify_load_status_changed(&self, _webview: WebView, _status: LoadStatus) {}

    fn notify_new_frame_ready(&self, _webview: WebView) {}

    fn notify_crashed(&self, _webview: WebView, _reason: String, _backtrace: Option<String>) {}

    fn request_navigation(&self, _webview: WebView, request: NavigationRequest) {
        request.deny();
    }

    fn request_create_new(&self, _webview: WebView, _request: CreateNewWebViewRequest) {
        // Dropping the request returns no auxiliary WebView. This is the v1
        // popup/new-window fail-closed policy.
    }

    fn notify_accessibility_tree_update(&self, _webview: WebView, _update: TreeUpdate) {}
}

fn construct_servo() -> Servo {
    let servo = ServoBuilder::default()
        .event_loop_waker(Box::new(ProbeWaker))
        .build();
    servo.set_delegate(Rc::new(ProbeServoDelegate));
    servo
}

fn construct_webview(
    servo: &Servo,
    rendering_context: Rc<dyn RenderingContext>,
    url: Url,
) -> WebView {
    WebViewBuilder::new(servo, rendering_context)
        .delegate(Rc::new(ProbeWebViewDelegate))
        .url(url)
        .build()
}

fn assert_webview_surface(
    servo: &Servo,
    webview: &WebView,
    url: Url,
    event: InputEvent,
    size: PhysicalSize<u32>,
    rect: Option<WebViewRect>,
) {
    servo.spin_event_loop();
    webview.focus();
    webview.blur();
    webview.resize(size);
    webview.load(url);
    let _event_id = webview.notify_input_event(event);
    webview.paint();
    webview.take_screenshot(rect, |_result| {});
    let _context = webview.rendering_context();
}

fn assert_auxiliary_type_exports(
    _composition: CompositionEvent,
    _control: EmbedderControl,
    _input_method: InputMethodControl,
    _resource: WebResourceLoad,
    _clipboard: &dyn ClipboardDelegate,
    _window_context: &WindowRenderingContext,
) {
}

fn main() {}
