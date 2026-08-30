#!/usr/bin/env python3
"""Materialize the generation-bound Servo clipboard round-trip proof once."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments/servo-headed-runtime/src/main.rs"
WORKFLOW = ROOT / ".github/workflows/servo-headed-runtime.yml"
VALIDATOR = ROOT / "tools/validate_d0a02_clipboard_roundtrip.py"
DOCUMENT = ROOT / "docs/architecture/D0A02_CLIPBOARD_ROUNDTRIP.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def materialize_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if "PASS_SERVO_EDITING_ACTION_TO_GENERATION_BOUND_DELEGATE_AND_BACK_TO_DOCUMENT" in text:
        return

    text = replace_once(
        text,
        "use servo::{\n    CompositionEvent,",
        "use servo::{\n    ClipboardDelegate, CompositionEvent,",
        "ClipboardDelegate import",
    )
    text = replace_once(
        text,
        "DevicePoint, EmbedderControl, EventLoopWaker, ImeEvent, InputEvent, InputEventId,",
        "DevicePoint, EditingAction, EditingActionEvent, EmbedderControl, EventLoopWaker, ImeEvent, InputEvent, InputEventId,",
        "editing action imports",
    )
    text = replace_once(
        text,
        "NavigationRequest, OffscreenRenderingContext, Opts, RenderingContext, Servo, ServoBuilder,\n    ViewId, WebView,",
        "NavigationRequest, OffscreenRenderingContext, Opts, RenderingContext, Servo, ServoBuilder,\n    StringRequest, ViewId, WebView,",
        "StringRequest import",
    )
    text = replace_once(
        text,
        "const NATIVE_INPUT_TIMEOUT_SECONDS: u64 = 150;\n",
        "const NATIVE_INPUT_TIMEOUT_SECONDS: u64 = 150;\nconst CLIPBOARD_SENTINEL: &str = \"hepta-servo-clipboard-roundtrip-v1\";\n",
        "clipboard sentinel",
    )

    clipboard_types = r'''
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ClipboardPhase {
    Idle,
    PreparingCopy,
    CopyRequested,
    CopyObserved,
    PreparingPaste,
    PasteRequested,
    PasteServed,
    Verifying,
    Verified,
}

#[derive(Debug, Clone, Copy)]
enum ClipboardScriptAction {
    PrepareCopy,
    PreparePaste,
    VerifyPaste,
}

struct ClipboardState {
    binding_generation: Cell<u32>,
    binding_webview_id: Cell<Option<u64>>,
    phase: Cell<ClipboardPhase>,
    text: RefCell<Option<String>>,
    set_text_calls: Cell<u32>,
    get_text_calls: Cell<u32>,
    clear_calls: Cell<u32>,
    stale_callbacks: Cell<u32>,
    document_verified: Cell<bool>,
    failure: RefCell<Option<String>>,
    proxy: EventLoopProxy<AppEvent>,
}

impl ClipboardState {
    fn new(proxy: EventLoopProxy<AppEvent>) -> Rc<Self> {
        Rc::new(Self {
            binding_generation: Cell::new(0),
            binding_webview_id: Cell::new(None),
            phase: Cell::new(ClipboardPhase::Idle),
            text: RefCell::new(None),
            set_text_calls: Cell::new(0),
            get_text_calls: Cell::new(0),
            clear_calls: Cell::new(0),
            stale_callbacks: Cell::new(0),
            document_verified: Cell::new(false),
            failure: RefCell::new(None),
            proxy,
        })
    }

    fn begin_generation(&self, generation: u32) {
        self.binding_generation.set(generation);
        self.binding_webview_id.set(None);
    }

    fn bind_webview(&self, generation: u32, webview_id: u64) {
        if self.binding_generation.get() != generation {
            self.fail(format!(
                "clipboard binding generation mismatch: expected {}, got {generation}",
                self.binding_generation.get()
            ));
            return;
        }
        self.binding_webview_id.set(Some(webview_id));
    }

    fn accepts(&self, generation: u32, webview_id: u64) -> bool {
        let accepted = self.binding_generation.get() == generation
            && self.binding_webview_id.get() == Some(webview_id);
        if !accepted {
            self.stale_callbacks
                .set(self.stale_callbacks.get().saturating_add(1));
        }
        accepted
    }

    fn fail(&self, reason: String) {
        let mut failure = self.failure.borrow_mut();
        if failure.is_none() {
            *failure = Some(reason);
        }
        let _ = self.proxy.send_event(AppEvent::Drive);
    }

    fn failure(&self) -> Option<String> {
        self.failure.borrow().clone()
    }

    fn ready_for_page_evidence(&self) -> bool {
        self.phase.get() == ClipboardPhase::Verified && self.document_verified.get()
    }

    fn phase_name(&self) -> &'static str {
        match self.phase.get() {
            ClipboardPhase::Idle => "Idle",
            ClipboardPhase::PreparingCopy => "PreparingCopy",
            ClipboardPhase::CopyRequested => "CopyRequested",
            ClipboardPhase::CopyObserved => "CopyObserved",
            ClipboardPhase::PreparingPaste => "PreparingPaste",
            ClipboardPhase::PasteRequested => "PasteRequested",
            ClipboardPhase::PasteServed => "PasteServed",
            ClipboardPhase::Verifying => "Verifying",
            ClipboardPhase::Verified => "Verified",
        }
    }
}

struct RuntimeClipboard {
    state: Rc<ClipboardState>,
    generation: u32,
}

impl RuntimeClipboard {
    fn new(state: Rc<ClipboardState>, generation: u32) -> Self {
        Self { state, generation }
    }

    fn accepts(&self, webview: &WebView) -> bool {
        self.state.accepts(self.generation, webview.id().get())
    }
}

impl ClipboardDelegate for RuntimeClipboard {
    fn clear(&self, webview: WebView) {
        if !self.accepts(&webview) {
            return;
        }
        self.state
            .clear_calls
            .set(self.state.clear_calls.get().saturating_add(1));
        self.state
            .fail("unexpected clipboard clear during bounded text round-trip".to_owned());
    }

    fn get_text(&self, webview: WebView, request: StringRequest) {
        if !self.accepts(&webview) {
            request.failure("stale clipboard delegate callback");
            let _ = self.state.proxy.send_event(AppEvent::Drive);
            return;
        }
        self.state
            .get_text_calls
            .set(self.state.get_text_calls.get().saturating_add(1));
        if self.state.phase.get() != ClipboardPhase::PasteRequested {
            request.failure("clipboard paste arrived in an invalid phase");
            self.state.fail(format!(
                "clipboard get_text arrived in phase {}",
                self.state.phase_name()
            ));
            return;
        }
        let Some(text) = self.state.text.borrow().clone() else {
            request.failure("clipboard text was not populated by Servo copy");
            self.state
                .fail("clipboard paste requested before copied text existed".to_owned());
            return;
        };
        if text != CLIPBOARD_SENTINEL {
            request.failure("clipboard text did not match the bounded sentinel");
            self.state
                .fail("clipboard stored text did not equal the sentinel".to_owned());
            return;
        }
        self.state.phase.set(ClipboardPhase::PasteServed);
        request.success(text);
        let _ = self.state.proxy.send_event(AppEvent::Drive);
    }

    fn set_text(&self, webview: WebView, text: String) {
        if !self.accepts(&webview) {
            let _ = self.state.proxy.send_event(AppEvent::Drive);
            return;
        }
        self.state
            .set_text_calls
            .set(self.state.set_text_calls.get().saturating_add(1));
        if self.state.phase.get() != ClipboardPhase::CopyRequested {
            self.state.fail(format!(
                "clipboard set_text arrived in phase {}",
                self.state.phase_name()
            ));
            return;
        }
        if text != CLIPBOARD_SENTINEL {
            self.state.fail(format!(
                "Servo copied unexpected clipboard text: {text:?}"
            ));
            return;
        }
        *self.state.text.borrow_mut() = Some(text);
        self.state.phase.set(ClipboardPhase::CopyObserved);
        let _ = self.state.proxy.send_event(AppEvent::Drive);
    }
}

struct ClipboardJavaScript {
    state: Weak<RuntimeState>,
    generation: u32,
    webview_id: u64,
    action: ClipboardScriptAction,
}

impl JSValue for ClipboardJavaScript {
    fn notify_complete(self: Box<Self>, result: Result<String, String>) {
        let Some(state) = self.state.upgrade() else {
            return;
        };
        if !state
            .clipboard
            .accepts(self.generation, self.webview_id)
        {
            let _ = state.proxy.send_event(AppEvent::Drive);
            return;
        }
        let encoded = match result {
            Ok(value) => value,
            Err(error) => {
                state
                    .clipboard
                    .fail(format!("clipboard JavaScript failed: {error}"));
                return;
            }
        };
        state.handle_clipboard_javascript(self.action, encoded);
    }
}

'''
    text = replace_once(
        text,
        "struct RuntimeState {\n",
        clipboard_types + "struct RuntimeState {\n",
        "clipboard implementation",
    )
    text = replace_once(
        text,
        "    selected_replacement_content_process: RefCell<Option<ProcessIdentity>>,\n    failure:",
        "    selected_replacement_content_process: RefCell<Option<ProcessIdentity>>,\n    clipboard: Rc<ClipboardState>,\n    failure:",
        "clipboard state field",
    )
    text = replace_once(
        text,
        "            .build();\n\n        let state = Rc::new(Self {",
        "            .build();\n\n        let clipboard = ClipboardState::new(proxy.clone());\n        let state = Rc::new(Self {",
        "clipboard state construction",
    )
    text = replace_once(
        text,
        "            selected_replacement_content_process: RefCell::new(None),\n            failure:",
        "            selected_replacement_content_process: RefCell::new(None),\n            clipboard,\n            failure:",
        "clipboard state initialization",
    )
    text = replace_once(
        text,
        "        let delegate = RuntimeDelegate::new(Rc::downgrade(self), generation);\n        let webview = WebViewBuilder::new(&self.servo, self.content_context.clone())",
        "        self.clipboard.begin_generation(generation);\n        let delegate = RuntimeDelegate::new(Rc::downgrade(self), generation);\n        let clipboard_delegate = RuntimeClipboard::new(self.clipboard.clone(), generation);\n        let webview = WebViewBuilder::new(&self.servo, self.content_context.clone())",
        "generation-bound clipboard delegate construction",
    )
    text = replace_once(
        text,
        "            .delegate(Box::new(delegate))\n            .build();",
        "            .delegate(Box::new(delegate))\n            .clipboard_delegate(Box::new(clipboard_delegate))\n            .build();",
        "clipboard delegate installation",
    )
    text = replace_once(
        text,
        "        let webview_id = webview.id().get();\n        let creation =",
        "        let webview_id = webview.id().get();\n        self.clipboard.bind_webview(generation, webview_id);\n        let creation =",
        "clipboard WebView identity binding",
    )
    text = replace_once(
        text,
        "        if self.completed.get() {\n            return;\n        }\n        if let Some(error) = self.failure.borrow().clone() {",
        "        if self.completed.get() {\n            return;\n        }\n        if let Some(error) = self.clipboard.failure() {\n            self.fail(&error);\n            return;\n        }\n        if let Some(error) = self.failure.borrow().clone() {",
        "clipboard failure propagation",
    )
    text = replace_once(
        text,
        "        if self.initial_page_evidence.borrow().is_none() {\n            if !self.page_evidence_requested.get() {",
        "        if self.generation.get() == 1 && !self.clipboard.ready_for_page_evidence() {\n            self.drive_clipboard_roundtrip();\n            return;\n        }\n\n        if self.initial_page_evidence.borrow().is_none() {\n            if !self.page_evidence_requested.get() {",
        "clipboard round-trip gate before page evidence",
    )

    clipboard_methods = r'''
    fn drive_clipboard_roundtrip(self: &Rc<Self>) {
        if let Some(reason) = self.clipboard.failure() {
            self.fail(&reason);
            return;
        }
        let generation = self.generation.get();
        if generation != 1 {
            self.fail("clipboard qualification ran outside generation 1");
            return;
        }
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.fail("clipboard qualification has no active WebView");
            return;
        };
        let webview_id = webview.id().get();
        match self.clipboard.phase.get() {
            ClipboardPhase::Idle => {
                self.clipboard.phase.set(ClipboardPhase::PreparingCopy);
                webview.evaluate_javascript(
                    format!(
                        "(() => {{ const target = document.getElementById('text'); target.value = {sentinel:?}; target.focus(); target.setSelectionRange(0, target.value.length); return JSON.stringify({{ready: true, value: target.value, selection_start: target.selectionStart, selection_end: target.selectionEnd}}); }})()",
                        sentinel = CLIPBOARD_SENTINEL,
                    ),
                    Box::new(ClipboardJavaScript {
                        state: Rc::downgrade(self),
                        generation,
                        webview_id,
                        action: ClipboardScriptAction::PrepareCopy,
                    }),
                );
            }
            ClipboardPhase::CopyObserved => {
                self.clipboard.phase.set(ClipboardPhase::PreparingPaste);
                webview.evaluate_javascript(
                    "(() => { const target = document.getElementById('text'); target.value = ''; target.focus(); target.setSelectionRange(0, 0); return JSON.stringify({ready: true, value: target.value}); })()"
                        .to_owned(),
                    Box::new(ClipboardJavaScript {
                        state: Rc::downgrade(self),
                        generation,
                        webview_id,
                        action: ClipboardScriptAction::PreparePaste,
                    }),
                );
            }
            ClipboardPhase::PasteServed => {
                self.clipboard.phase.set(ClipboardPhase::Verifying);
                webview.evaluate_javascript(
                    "JSON.stringify(document.getElementById('text').value)".to_owned(),
                    Box::new(ClipboardJavaScript {
                        state: Rc::downgrade(self),
                        generation,
                        webview_id,
                        action: ClipboardScriptAction::VerifyPaste,
                    }),
                );
            }
            ClipboardPhase::PreparingCopy
            | ClipboardPhase::CopyRequested
            | ClipboardPhase::PreparingPaste
            | ClipboardPhase::PasteRequested
            | ClipboardPhase::Verifying => {}
            ClipboardPhase::Verified => {}
        }
    }

    fn handle_clipboard_javascript(
        self: &Rc<Self>,
        action: ClipboardScriptAction,
        encoded: String,
    ) {
        match action {
            ClipboardScriptAction::PrepareCopy => {
                let parsed = serde_json::from_str::<serde_json::Value>(&encoded);
                let Ok(value) = parsed else {
                    self.clipboard
                        .fail("clipboard copy preparation returned invalid JSON".to_owned());
                    return;
                };
                let selection_start = value.get("selection_start").and_then(|v| v.as_u64());
                let selection_end = value.get("selection_end").and_then(|v| v.as_u64());
                if value.get("ready").and_then(|v| v.as_bool()) != Some(true)
                    || value.get("value").and_then(|v| v.as_str())
                        != Some(CLIPBOARD_SENTINEL)
                    || selection_start != Some(0)
                    || selection_end != Some(CLIPBOARD_SENTINEL.len() as u64)
                {
                    self.clipboard.fail(format!(
                        "clipboard copy preparation did not select the sentinel: {encoded}"
                    ));
                    return;
                }
                self.clipboard.phase.set(ClipboardPhase::CopyRequested);
                self.send_editing_action(EditingAction::Copy);
            }
            ClipboardScriptAction::PreparePaste => {
                let parsed = serde_json::from_str::<serde_json::Value>(&encoded);
                let Ok(value) = parsed else {
                    self.clipboard
                        .fail("clipboard paste preparation returned invalid JSON".to_owned());
                    return;
                };
                if value.get("ready").and_then(|v| v.as_bool()) != Some(true)
                    || value.get("value").and_then(|v| v.as_str()) != Some("")
                {
                    self.clipboard.fail(format!(
                        "clipboard paste preparation did not clear the document field: {encoded}"
                    ));
                    return;
                }
                self.clipboard.phase.set(ClipboardPhase::PasteRequested);
                self.send_editing_action(EditingAction::Paste);
            }
            ClipboardScriptAction::VerifyPaste => {
                let parsed = serde_json::from_str::<String>(&encoded);
                let Ok(value) = parsed else {
                    self.clipboard
                        .fail("clipboard document verification returned invalid JSON".to_owned());
                    return;
                };
                if value != CLIPBOARD_SENTINEL {
                    self.clipboard.fail(format!(
                        "Servo paste did not restore the sentinel into the document: {value:?}"
                    ));
                    return;
                }
                self.clipboard.document_verified.set(true);
                self.clipboard.phase.set(ClipboardPhase::Verified);
                let _ = self.proxy.send_event(AppEvent::Drive);
            }
        }
    }

    fn send_editing_action(&self, action: EditingAction) {
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            self.clipboard
                .fail("cannot send clipboard EditingAction without a WebView".to_owned());
            return;
        };
        webview.notify_input_event(InputEvent::EditingAction(EditingActionEvent::from(action)));
    }

'''
    text = replace_once(
        text,
        "    fn request_page_evidence(self: &Rc<Self>) {\n",
        clipboard_methods + "    fn request_page_evidence(self: &Rc<Self>) {\n",
        "clipboard runtime methods",
    )
    text = replace_once(
        text,
        "content_process_crash: Boolean(window.__contentProcessCrash),\n  generation: Number(document.body.dataset.generation)",
        "content_process_crash: Boolean(window.__contentProcessCrash),\n  clipboard_value: document.getElementById('text').value,\n  generation: Number(document.body.dataset.generation)",
        "clipboard document evidence",
    )
    text = replace_once(
        text,
        "            (\"ime_state\", \"string\"),\n            (\"rect\", \"object\"),",
        "            (\"ime_state\", \"string\"),\n            (\"clipboard_value\", \"string\"),\n            (\"rect\", \"object\"),",
        "clipboard evidence type validation",
    )
    text = replace_once(
        text,
        "        if initial.get(\"generation\").and_then(|value| value.as_u64()) != Some(1)\n            || initial\n                .get(\"content_process_crash\")",
        "        if initial.get(\"generation\").and_then(|value| value.as_u64()) != Some(1)\n            || initial.get(\"clipboard_value\").and_then(|value| value.as_str())\n                != Some(CLIPBOARD_SENTINEL)\n            || initial\n                .get(\"content_process_crash\")",
        "initial clipboard artifact validation",
    )
    text = replace_once(
        text,
        "        let fault = self.fault.borrow();\n        let fault = fault.as_ref().expect(\"validated fault receipt\");",
        "        if !self.clipboard.ready_for_page_evidence()\n            || self.clipboard.set_text_calls.get() != 1\n            || self.clipboard.get_text_calls.get() != 1\n            || self.clipboard.clear_calls.get() != 0\n            || self.clipboard.stale_callbacks.get() != 0\n            || self.clipboard.text.borrow().as_deref() != Some(CLIPBOARD_SENTINEL)\n        {\n            self.fail(\"Servo clipboard round-trip evidence is incomplete\");\n            return;\n        }\n\n        let fault = self.fault.borrow();\n        let fault = fault.as_ref().expect(\"validated fault receipt\");",
        "clipboard finish invariants",
    )
    text = replace_once(
        text,
        "            \"native_input\": {\n                \"pointer_events\": self.native_pointer_events.get(),",
        "            \"clipboard\": {\n                \"status\": \"PASS_SERVO_EDITING_ACTION_TO_GENERATION_BOUND_DELEGATE_AND_BACK_TO_DOCUMENT\",\n                \"phase\": self.clipboard.phase_name(),\n                \"sentinel\": CLIPBOARD_SENTINEL,\n                \"set_text_calls\": self.clipboard.set_text_calls.get(),\n                \"get_text_calls\": self.clipboard.get_text_calls.get(),\n                \"clear_calls\": self.clipboard.clear_calls.get(),\n                \"stale_callbacks\": self.clipboard.stale_callbacks.get(),\n                \"document_verified\": self.clipboard.document_verified.get(),\n                \"generation_bound\": true,\n                \"host_clipboard_authority_claimed\": false,\n                \"image_clipboard_authority_claimed\": false\n            },\n            \"native_input\": {\n                \"pointer_events\": self.native_pointer_events.get(),",
        "clipboard machine evidence",
    )
    SOURCE.write_text(text, encoding="utf-8")


def materialize_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    if "PASS_SERVO_EDITING_ACTION_TO_GENERATION_BOUND_DELEGATE_AND_BACK_TO_DOCUMENT" in text:
        return
    text = text.replace("      - \"tools/validate_d0a02_proof_soundness.py\"\n", "      - \"tools/validate_d0a02_proof_soundness.py\"\n      - \"tools/validate_d0a02_clipboard_roundtrip.py\"\n      - \"docs/architecture/D0A02_CLIPBOARD_ROUNDTRIP.md\"\n")
    text = text.replace("            xclip \\\n", "")
    text = replace_once(
        text,
        "          python3 tools/validate_d0a02_proof_soundness.py\n          cargo metadata",
        "          python3 tools/validate_d0a02_proof_soundness.py\n          python3 tools/validate_d0a02_clipboard_roundtrip.py\n          cargo metadata",
        "clipboard validator execution",
    )
    old_host_roundtrip = '''          clipboard_sentinel='hepta-native-clipboard-roundtrip-v1'\n          printf '%s' "$clipboard_sentinel" | DISPLAY=:99 xclip -selection clipboard -in\n          clipboard_roundtrip=$(DISPLAY=:99 xclip -selection clipboard -out)\n          [[ "$clipboard_roundtrip" == "$clipboard_sentinel" ]]\n          printf '%s\\n' "$clipboard_roundtrip" \\\n            > artifacts/servo-headed-runtime/native-clipboard-roundtrip.txt\n'''
    text = replace_once(text, old_host_roundtrip, "", "remove host clipboard substitute")
    old_assert = '''          assert result['native_input']['clipboard_roundtrip'] == \\\n              'PASS_NATIVE_X11_SELECTION_ROUNDTRIP'\n          assert result['native_input']['clipboard_sentinel'] == \\\n              'hepta-native-clipboard-roundtrip-v1'\n'''
    new_assert = '''          clipboard = result['clipboard']\n          assert clipboard['status'] == \\\n              'PASS_SERVO_EDITING_ACTION_TO_GENERATION_BOUND_DELEGATE_AND_BACK_TO_DOCUMENT'\n          assert clipboard['phase'] == 'Verified'\n          assert clipboard['sentinel'] == 'hepta-servo-clipboard-roundtrip-v1'\n          assert clipboard['set_text_calls'] == 1\n          assert clipboard['get_text_calls'] == 1\n          assert clipboard['clear_calls'] == 0\n          assert clipboard['stale_callbacks'] == 0\n          assert clipboard['document_verified'] is True\n          assert clipboard['generation_bound'] is True\n          assert clipboard['host_clipboard_authority_claimed'] is False\n          assert clipboard['image_clipboard_authority_claimed'] is False\n'''
    text = replace_once(text, old_assert, new_assert, "clipboard evidence assertions")
    text = text.replace("              'native-clipboard-roundtrip.txt',\n", "")
    text = replace_once(
        text,
        "              'RuntimeDelegate::new',\n              'ClipboardDelegate',",
        "              'RuntimeDelegate::new',\n              'ClipboardDelegate',\n              'StringRequest',\n              'EditingAction::Copy',\n              'EditingAction::Paste',\n              '.clipboard_delegate(Box::new(clipboard_delegate))',\n              'PASS_SERVO_EDITING_ACTION_TO_GENERATION_BOUND_DELEGATE_AND_BACK_TO_DOCUMENT',",
        "clipboard source markers",
    )
    text = replace_once(
        text,
        "              Path('tools/validate_d0a02_proof_soundness.py'),\n              Path('manifests/servo.lock.json'),",
        "              Path('tools/validate_d0a02_proof_soundness.py'),\n              Path('tools/validate_d0a02_clipboard_roundtrip.py'),\n              Path('docs/architecture/D0A02_CLIPBOARD_ROUNDTRIP.md'),\n              Path('manifests/servo.lock.json'),",
        "clipboard evidence inputs",
    )
    WORKFLOW.write_text(text, encoding="utf-8")


def write_validator() -> None:
    VALIDATOR.write_text(
        '''#!/usr/bin/env python3\nfrom __future__ import annotations\n\nfrom pathlib import Path\nimport sys\n\nROOT = Path(__file__).resolve().parents[1]\nsource = (ROOT / "experiments/servo-headed-runtime/src/main.rs").read_text(encoding="utf-8")\nworkflow = (ROOT / ".github/workflows/servo-headed-runtime.yml").read_text(encoding="utf-8")\ndoc = ROOT / "docs/architecture/D0A02_CLIPBOARD_ROUNDTRIP.md"\nrequired_source = [\n    "ClipboardDelegate",\n    "StringRequest",\n    "EditingAction::Copy",\n    "EditingAction::Paste",\n    ".clipboard_delegate(Box::new(clipboard_delegate))",\n    "hepta-servo-clipboard-roundtrip-v1",\n    "PASS_SERVO_EDITING_ACTION_TO_GENERATION_BOUND_DELEGATE_AND_BACK_TO_DOCUMENT",\n    "host_clipboard_authority_claimed",\n    "image_clipboard_authority_claimed",\n]\nrequired_workflow = [\n    "tools/validate_d0a02_clipboard_roundtrip.py",\n    "D0A02_CLIPBOARD_ROUNDTRIP.md",\n    "PASS_SERVO_EDITING_ACTION_TO_GENERATION_BOUND_DELEGATE_AND_BACK_TO_DOCUMENT",\n    "clipboard['set_text_calls'] == 1",\n    "clipboard['get_text_calls'] == 1",\n    "clipboard['stale_callbacks'] == 0",\n]\nerrors = []\nfor marker in required_source:\n    if marker not in source:\n        errors.append(f"source missing {marker!r}")\nfor marker in required_workflow:\n    if marker not in workflow:\n        errors.append(f"workflow missing {marker!r}")\nfor forbidden in ["xclip", "native-clipboard-roundtrip.txt", "PASS_NATIVE_X11_SELECTION_ROUNDTRIP"]:\n    if forbidden in source or forbidden in workflow:\n        errors.append(f"host clipboard substitute remains: {forbidden!r}")\nif not doc.is_file():\n    errors.append("clipboard architecture note is missing")\nif errors:\n    for error in errors:\n        print(f"ERROR: {error}", file=sys.stderr)\n    raise SystemExit(1)\nprint("D0A-02 Servo clipboard round-trip validation passed")\n''',
        encoding="utf-8",
    )


def write_document() -> None:
    DOCUMENT.write_text(
        '''# D0A-02 Servo clipboard round-trip\n\nThe headed-host qualification binds text clipboard callbacks to the exact active\ncontent generation and Servo `WebView` identity. Generation 1 selects a fixed\nlocal-fixture sentinel, sends Servo `EditingAction::Copy`, requires the bound\n`ClipboardDelegate::set_text` callback, clears the fixture field, sends Servo\n`EditingAction::Paste`, serves the stored sentinel through\n`ClipboardDelegate::get_text`, and finally reads the Servo document value back.\n\nThe gate fails on stale generation/WebView callbacks, unexpected clear calls,\nwrong text, duplicate callbacks, or a document value that does not equal the\nbounded sentinel. The receipt records callback counts, stale-callback count,\ngeneration binding, the final phase, and the document verification fact.\n\nThis is deterministic local-fixture text clipboard evidence only. It does not\nclaim host desktop clipboard integration, image clipboard formats, persistent\nclipboard storage, external navigation, credentials, AgentPort activation, or\nrelease authority. Host `xclip` round-tripping is explicitly forbidden as a\nsubstitute for Servo/embedder clipboard evidence.\n''',
        encoding="utf-8",
    )


def main() -> int:
    materialize_source()
    materialize_workflow()
    write_validator()
    write_document()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
