//! Read-only explicitly authorized collaboration observations from the actual owned session.
//! The selected original APK, native replies, decoded window pixels and finished
//! histories remain bound together. Static resource names and an observed login never mint a gate.
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeUiReply, NativeUiSelector, NativeUiSession,
    NativeUiTranscript, RetainedScopedWindowPixels,
};
use droidloom_supervisor::working_qualification::FeishuReadonlyFixture;
use serde::Serialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::time::Instant;
#[path = "family_collaboration_document.rs"]
mod document;

const PACKAGE: &str = "com.ss.android.lark";
const ORIGINAL_APK_SHA256: &str =
    "00f307f3f09df4b29fdaa90e8a1048df7c9cd64e16126f72cd784254bc75af50";
const ORIGINAL_APK_BYTES: u64 = 397_857_672;
// The maximal normal route includes four navigation clicks and a declared
// readonly document: seven more image frames, nine actions (four double-request
// text/scroll operations), plus two explicit post-text dumps. No retries.
const FIRST_REQUESTS: usize = 2 * 12 + 13 + 4 + 2;
const SECOND_REQUESTS: usize = 2;
const FIRST_CAPTURES: usize = 12;
const SECOND_CAPTURES: usize = 1;
const RETAINED_REPLY_BYTES: usize = 64 * 1024 * 1024;
pub(super) fn supports(package: &str) -> bool {
    package == PACKAGE
}
pub(super) fn additional_window_seconds() -> u64 {
    (FIRST_REQUESTS + SECOND_REQUESTS) as u64 * (15 + 70 + 15)
        + (FIRST_CAPTURES + SECOND_CAPTURES) as u64 * (2 * 15 + 2 * 15 + 2 * 15 + 20 + 60)
}
pub(super) fn second_business_seconds() -> u64 {
    SECOND_REQUESTS as u64 * (15 + 70 + 15)
        + SECOND_CAPTURES as u64 * (2 * 15 + 2 * 15 + 2 * 15 + 20 + 60)
}
pub(super) fn first_max_extra_ui_commands() -> u32 {
    FIRST_REQUESTS as u32 * 3 + FIRST_CAPTURES as u32 * 7
}
pub(super) fn first_max_extra_actions() -> u32 {
    13
}
pub(super) fn reopen_max_ui_commands() -> u32 {
    SECOND_REQUESTS as u32 * 3 + SECOND_CAPTURES as u32 * 7
}
pub(super) fn reopen_max_actions() -> u32 {
    0
}
fn need(ok: bool, why: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn before(end: Instant) -> Result<(), String> {
    need(
        Instant::now() < end,
        "collaboration original window expired",
    )
}
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn text<'a>(n: &'a Value, key: &str) -> &'a str {
    n.get(key).and_then(Value::as_str).unwrap_or("")
}
fn norm(s: &str) -> String {
    s.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}
fn same_title(a: &str, b: &str) -> bool {
    norm(a) == norm(b)
}
pub(super) fn require_application(a: &ApplicationInspection) -> Result<(), String> {
    need(
        a.package == PACKAGE
            && a.user == 0
            && (10_000..20_000).contains(&a.uid)
            && a.version_code == 8_080_550
            && a.apks.len() == 1
            && a.apks[0].name == "base.apk"
            && a.apks[0].bytes == ORIGINAL_APK_BYTES
            && a.apks[0].sha256 == ORIGINAL_APK_SHA256,
        "collaboration source facts require the actual complete selected original PM APK",
    )
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct Rect([i64; 4]);
impl Rect {
    fn parse(v: &Value) -> Result<Self, String> {
        let a = v
            .as_array()
            .filter(|v| v.len() == 4)
            .ok_or("collaboration rectangle absent")?;
        let v = a
            .iter()
            .map(Value::as_i64)
            .collect::<Option<Vec<_>>>()
            .ok_or("collaboration rectangle noninteger")?;
        need(
            v.iter().all(|v| (0..=8192).contains(v)) && v[2] > v[0] && v[3] > v[1],
            "collaboration rectangle bound",
        )?;
        Ok(Self([v[0], v[1], v[2], v[3]]))
    }
    fn contains(self, b: Self) -> bool {
        self.0[0] <= b.0[0] && self.0[1] <= b.0[1] && self.0[2] >= b.0[2] && self.0[3] >= b.0[3]
    }
    fn area(self) -> i64 {
        (self.0[2] - self.0[0]) * (self.0[3] - self.0[1])
    }
    fn height(self) -> i64 {
        self.0[3] - self.0[1]
    }
    fn disjoint(self, b: Self) -> bool {
        self.0[2] <= b.0[0] || b.0[2] <= self.0[0] || self.0[3] <= b.0[1] || b.0[3] <= self.0[1]
    }
}
fn nodes(body: &Value) -> Result<&[Value], String> {
    let c = &body["window_context"];
    need(
        body["ok"] == true
            && c["root"]["package"] == PACKAGE
            && c["selected_window"]["root"]["package"] == PACKAGE
            && c["selected_window"]["focused"] == true
            && c["selected_window"]["display_id"] == 0
            && c["snapshot_complete"] == true
            && c["truncated"] == false,
        "collaboration needs the actual complete same-package focused tree",
    )?;
    body["nodes"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 2000)
        .map(Vec::as_slice)
        .ok_or_else(|| "collaboration actual nodes absent".into())
}
fn usable(n: &Value) -> bool {
    n["package"] == PACKAGE
        && n["visible"] == true
        && n["enabled"] == true
        && n["password"] == false
        && n["source"] == "native_accessibility"
        && Rect::parse(&n["bounds_array"]).is_ok()
}
fn same_node(a: &Value, b: &Value) -> bool {
    [
        "resource-id",
        "text",
        "content-desc",
        "class",
        "package",
        "window_id",
        "bounds_array",
        "visible",
        "enabled",
        "password",
        "clickable",
        "scrollable",
        "editable",
    ]
    .iter()
    .all(|k| a[*k] == b[*k])
}
fn image(n: &Value) -> bool {
    usable(n)
        && text(n, "text").is_empty()
        && text(n, "class").contains("Image")
        && Rect::parse(&n["bounds_array"]).is_ok_and(|r| r.0[2] - r.0[0] >= 64 && r.height() >= 48)
}
#[derive(Clone, Debug)]
struct Patch {
    rgb: Vec<u8>,
    sha256: String,
}
fn patch(
    rgb: &[u8],
    width: usize,
    height: usize,
    window: Rect,
    area: Rect,
) -> Result<Patch, String> {
    need(
        window.contains(area)
            && width == (window.0[2] - window.0[0]) as usize
            && height == window.height() as usize
            && width.checked_mul(height).and_then(|n| n.checked_mul(3)) == Some(rgb.len())
            && area.0[2] - area.0[0] >= 12
            && area.height() >= 10,
        "collaboration pixel crop does not match actual window",
    )?;
    let mut out = Vec::with_capacity(768);
    for y in 0..16 {
        for x in 0..16 {
            let sx = (area.0[0] - window.0[0]) as usize
                + (2 * x + 1) * (area.0[2] - area.0[0]) as usize / 32;
            let sy = (area.0[1] - window.0[1]) as usize + (2 * y + 1) * area.height() as usize / 32;
            out.extend_from_slice(&rgb[3 * (sy * width + sx)..3 * (sy * width + sx) + 3]);
        }
    }
    let lo = *out.iter().min().ok_or("collaboration pixel patch empty")?;
    let hi = *out.iter().max().unwrap();
    need(
        hi - lo >= 48
            && out
                .chunks_exact(3)
                .filter(|p| p.iter().any(|v| *v < 220))
                .count()
                >= 8
            && out.chunks_exact(3).any(|p| p.iter().any(|v| *v < 160)),
        "collaboration crop is blank, pale, or lacks contrast",
    )?;
    Ok(Patch {
        sha256: digest(&out),
        rgb: out,
    })
}
fn materially_changed(a: &Patch, b: &Patch) -> bool {
    a.rgb.len() == 768
        && b.rgb.len() == 768
        && a.sha256 != b.sha256
        && a.rgb
            .iter()
            .zip(&b.rgb)
            .filter(|(a, b)| a.abs_diff(**b) >= 24)
            .count()
            >= 48
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
enum Role {
    Page,
    SearchEntry,
    Input,
    Submit,
    Document,
    Back,
    Scroll,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
enum Operation {
    Dump,
    Click,
    SetText,
    Forward,
    Backward,
}
impl Operation {
    fn requests(self) -> u32 {
        if matches!(self, Self::SetText | Self::Forward | Self::Backward) {
            2
        } else {
            1
        }
    }
    fn name(self) -> &'static str {
        match self {
            Self::Dump => "dump",
            Self::Click => "click",
            Self::SetText => "set-text",
            Self::Forward => "scroll-forward",
            Self::Backward => "scroll-backward",
        }
    }
}
fn allowed_operation(role: Role, op: Operation, written: Option<&str>) -> bool {
    match (role, op, written) {
        (Role::Input, Operation::SetText, Some(value)) => {
            value.len() <= 256 && !value.chars().any(char::is_control)
        }
        (Role::Scroll, Operation::Forward | Operation::Backward, None) => true,
        (
            Role::Page | Role::SearchEntry | Role::Submit | Role::Document | Role::Back,
            Operation::Click,
            None,
        ) => true,
        _ => false,
    }
}
struct Target {
    selector: NativeUiSelector,
    node: Value,
    origin: usize,
    role: Role,
    container: Option<Rect>,
}
struct Step {
    op: Operation,
    reply: NativeUiReply,
    target: Option<(usize, Role, Value, Option<Rect>)>,
    written: Option<String>,
}
struct Frame {
    before: usize,
    after: usize,
    pixels: RetainedScopedWindowPixels,
    patches: BTreeMap<Rect, Patch>,
    window: Rect,
}
struct Trace {
    steps: Vec<Step>,
    frames: Vec<Frame>,
    second: bool,
    retained_bytes: usize,
}
impl Trace {
    fn new(second: bool) -> Self {
        Self {
            steps: vec![],
            frames: vec![],
            second,
            retained_bytes: 0,
        }
    }
    fn requests(&self) -> u32 {
        self.steps.iter().map(|s| s.op.requests()).sum()
    }
    fn actions(&self) -> u32 {
        self.steps
            .iter()
            .filter(|s| s.op != Operation::Dump)
            .count() as u32
    }
    fn counts(&self) -> (u32, u32) {
        (
            self.requests() * 3 + self.frames.len() as u32 * 7,
            self.actions(),
        )
    }
    fn reserve(&self, requests: u32, action: bool, end: Instant) -> Result<(), String> {
        before(end)?;
        need(
            self.requests() + requests
                <= if self.second {
                    SECOND_REQUESTS
                } else {
                    FIRST_REQUESTS
                } as u32
                && self.actions() + u32::from(action)
                    <= if self.second {
                        reopen_max_actions()
                    } else {
                        first_max_extra_actions()
                    },
            "collaboration fixed request/action budget exhausted",
        )
    }
    fn add(&mut self, step: Step) -> Result<usize, String> {
        self.retained_bytes = self
            .retained_bytes
            .checked_add(
                serde_json::to_vec(step.reply.body())
                    .map_err(|e| e.to_string())?
                    .len(),
            )
            .ok_or("collaboration retained reply byte overflow")?;
        need(
            self.retained_bytes <= RETAINED_REPLY_BYTES,
            "collaboration retained reply memory bound exceeded",
        )?;
        let idx = self.steps.len();
        self.steps.push(step);
        Ok(idx)
    }
    fn body(&self, n: usize) -> Result<&Value, String> {
        self.steps
            .get(n)
            .map(|s| s.reply.body())
            .ok_or_else(|| "collaboration reply index differs".into())
    }
    fn dump(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &NativeApplicationInspector,
        end: Instant,
    ) -> Result<usize, String> {
        self.reserve(1, false, end)?;
        let reply = s.dump(i)?;
        nodes(reply.body())?;
        self.add(Step {
            op: Operation::Dump,
            reply,
            target: None,
            written: None,
        })
    }
    fn perform(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &NativeApplicationInspector,
        target: Target,
        op: Operation,
        written: Option<&str>,
        end: Instant,
    ) -> Result<usize, String> {
        need(
            allowed_operation(target.role, op, written),
            "collaboration operation is outside fixed readonly search/document controls",
        )?;
        self.reserve(op.requests(), true, end)?;
        let reply = match op {
            Operation::Click => s.click(i, target.selector)?,
            Operation::SetText => s.set_text(
                i,
                target.selector,
                written.ok_or("collaboration typed text absent")?,
            )?,
            Operation::Forward => s.scroll_forward(i, target.selector)?,
            Operation::Backward => s.scroll_backward(i, target.selector)?,
            Operation::Dump => return Err("collaboration mutation cannot select Dump".into()),
        };
        if op != Operation::SetText {
            need(
                same_node(&reply.body()["target"], &target.node),
                "collaboration acknowledged target differs from its actual observed node",
            )?;
            if op == Operation::Click {
                let actual = &reply.body()["actual_target"];
                let a = Rect::parse(&actual["bounds_array"])?;
                let n = Rect::parse(&target.node["bounds_array"])?;
                need(
                    nodes(self.body(target.origin)?)?
                        .iter()
                        .any(|v| same_node(v, actual))
                        && a.contains(n)
                        && target.container.map_or(a == n, |c| c.contains(a)),
                    "collaboration click climbed outside the actual source-chosen control/card",
                )?;
            }
        }
        self.add(Step {
            op,
            reply,
            target: Some((target.origin, target.role, target.node, target.container)),
            written: written.map(str::to_owned),
        })
    }
    fn frame(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &NativeApplicationInspector,
        end: Instant,
    ) -> Result<usize, String> {
        need(
            self.frames.len()
                < if self.second {
                    SECOND_CAPTURES
                } else {
                    FIRST_CAPTURES
                },
            "collaboration fixed scoped image budget exhausted",
        )?;
        self.reserve(2, false, end)?;
        let a = self.dump(s, i, end)?;
        let pixels = s.scoped_window_pixels(i)?;
        let z = self.dump(s, i, end)?;
        let before = self.body(a)?;
        let after = self.body(z)?;
        let window = Rect::parse(&before["window_context"]["selected_window"]["bounds"])?;
        need(
            before["window_context"]["selected_window"]["window_id"]
                == after["window_context"]["selected_window"]["window_id"]
                && before["window_context"]["selected_window"]["bounds"]
                    == after["window_context"]["selected_window"]["bounds"],
            "collaboration window changed across the real pixel observation",
        )?;
        let cmp = pixels.comparison()?;
        let p = &cmp["window"]["bounds"];
        need(
            window
                == Rect([
                    p["left"].as_i64().ok_or("collaboration pixel left")?,
                    p["top"].as_i64().ok_or("collaboration pixel top")?,
                    p["right"].as_i64().ok_or("collaboration pixel right")?,
                    p["bottom"].as_i64().ok_or("collaboration pixel bottom")?,
                ]),
            "collaboration scoped pixel window differs from actual semantic tree",
        )?;
        let mut patches = BTreeMap::new();
        patches.insert(
            window,
            patch(
                pixels.rgb(),
                pixels.width() as usize,
                pixels.height() as usize,
                window,
                window,
            )?,
        );
        for n in nodes(before)?.iter().filter(|n| usable(n)) {
            let rect = Rect::parse(&n["bounds_array"])?;
            if window.contains(rect)
                && nodes(after)?.iter().any(|v| same_node(n, v))
                && (image(n)
                    || !text(n, "text").is_empty()
                    || n["scrollable"] == true
                    || structural_region(n))
            {
                if let Ok(p) = patch(
                    pixels.rgb(),
                    pixels.width() as usize,
                    pixels.height() as usize,
                    window,
                    rect,
                ) {
                    patches.insert(rect, p);
                }
            }
        }
        need(
            patches.len() <= 256,
            "collaboration actual rendered patch count exceeds source bound",
        )?;
        let idx = self.frames.len();
        self.frames.push(Frame {
            before: a,
            after: z,
            pixels: pixels.into_retained()?,
            patches,
            window,
        });
        Ok(idx)
    }
    fn rendered(&self, frame: usize, n: &Value) -> bool {
        self.frames.get(frame).is_some_and(|f| {
            Rect::parse(&n["bounds_array"]).is_ok_and(|r| f.patches.contains_key(&r))
                && self
                    .body(f.before)
                    .and_then(nodes)
                    .is_ok_and(|ns| ns.iter().any(|v| same_node(v, n)))
                && self
                    .body(f.after)
                    .and_then(nodes)
                    .is_ok_and(|ns| ns.iter().any(|v| same_node(v, n)))
        })
    }
    fn guard(&self, transcript: &NativeUiTranscript) -> Result<(), String> {
        require_application(transcript.engine().application())?;
        need(
            self.requests()
                <= if self.second {
                    SECOND_REQUESTS
                } else {
                    FIRST_REQUESTS
                } as u32
                && self.actions()
                    <= if self.second {
                        reopen_max_actions()
                    } else {
                        first_max_extra_actions()
                    }
                && self.frames.len()
                    <= if self.second {
                        SECOND_CAPTURES
                    } else {
                        FIRST_CAPTURES
                    }
                && self.retained_bytes <= RETAINED_REPLY_BYTES,
            "collaboration retained trace limits differ",
        )?;
        for (idx, step) in self.steps.iter().enumerate() {
            need(
                step.reply.body()["ok"] == true,
                "collaboration retained reply failed",
            )?;
            if let Some((origin, _, node, _)) = &step.target {
                need(
                    *origin < idx
                        && self.steps[*origin].op == Operation::Dump
                        && nodes(self.body(*origin)?)?.iter().any(|v| v == node)
                        && usable(node)
                        && step.reply.body()["performed"] == step.op.name(),
                    "collaboration retained action lost its actual source choice",
                )?;
                let role = step.target.as_ref().unwrap().1;
                need(
                    allowed_operation(role, step.op, step.written.as_deref()),
                    "collaboration retained operation escaped readonly role",
                )?;
                if step.op != Operation::SetText {
                    need(
                        same_node(node, &step.reply.body()["target"]),
                        "collaboration retained target changed",
                    )?;
                } else {
                    need(
                        step.written.as_ref().is_some_and(|value| {
                            step.reply.body()["characters"].as_u64()
                                == Some(value.chars().count() as u64)
                                && step.reply.body()["readback_verified"] == true
                        }),
                        "collaboration typed Unicode lacks its exact actual readback",
                    )?;
                }
            } else {
                need(
                    step.op == Operation::Dump,
                    "collaboration action lacks observed target",
                )?;
            }
        }
        for f in &self.frames {
            f.pixels.require_transcript(transcript)?;
            nodes(self.body(f.before)?)?;
            nodes(self.body(f.after)?)?;
            need(
                f.patches.contains_key(&f.window)
                    && f.patches
                        .values()
                        .all(|p| p.rgb.len() == 768 && digest(&p.rgb) == p.sha256),
                "collaboration actual decoded patch history changed",
            )?;
        }
        Ok(())
    }
}

fn choose(
    trace: &Trace,
    origin: usize,
    role: Role,
    selected: &Value,
    container: Option<Rect>,
) -> Result<Option<Target>, String> {
    let ns = nodes(trace.body(origin)?)?;
    need(
        usable(selected) && ns.iter().any(|n| n == selected),
        "collaboration choice is not an actual usable node",
    )?;
    for (field, make) in [
        (
            "resource-id",
            NativeUiSelector::resource_id as fn(&str) -> Result<NativeUiSelector, _>,
        ),
        ("text", NativeUiSelector::exact_text),
        ("content-desc", NativeUiSelector::description),
    ] {
        let v = text(selected, field);
        if !v.is_empty() && ns.iter().filter(|n| text(n, field) == v).count() == 1 {
            let selector = make(v).map_err(|e| e.to_string())?.enabled();
            return Ok(Some(Target {
                selector,
                node: selected.clone(),
                origin,
                role,
                container,
            }));
        }
    }
    Ok(None)
}

const NAV_BAR: &str = "main_tab_bottom_bar";
const TENANT_IDS: &[&str] = &[
    "contacts_tenant_name_tv",
    "tenant_name",
    "tv_tenant_name",
    "tv_user_tenant_name",
];
const ACCOUNT_IDS: &[&str] = &[
    "account_name_tv",
    "setting_account_name_tv",
    "tv_account_name",
    "user_name",
];
const PAGE_ROOTS: &[&str] = &[
    "main_tab_chat_container",
    "conversation_list",
    "chat_list",
    "message_list_container",
    "calendar_view_shell_calendar_container",
    "calendar_view",
    "calendar_month_day_view_pager",
    "calendar_rv",
    "list_calendar_view_content",
    "workplace_fragment_container",
    "workplace_view",
];
fn resource(n: &Value, suffix: &str) -> bool {
    text(n, "resource-id") == format!("{PACKAGE}:id/{suffix}")
}
fn structural_region(n: &Value) -> bool {
    resource(n, NAV_BAR) || PAGE_ROOTS.iter().any(|name| resource(n, name))
}
fn bounded_identity(value: &str) -> bool {
    let count = value.chars().count();
    (1..=160).contains(&count)
        && value.trim() == value
        && !value.chars().any(char::is_control)
        && ![
            "登录",
            "登錄",
            "login",
            "sign in",
            "用户名",
            "user name",
            "企业名称",
            "tenant name",
        ]
        .contains(&norm(value).as_str())
}
fn authentication_surface(body: &Value) -> Result<bool, String> {
    Ok(nodes(body)?.iter().any(|n| {
        usable(n)
            && (resource(n, "login_button")
                || [
                    "登录",
                    "登陆",
                    "登錄",
                    "注册",
                    "sign in",
                    "log in",
                    "login",
                    "sign up",
                    "get started",
                    "验证码",
                ]
                .contains(&norm(text(n, "text")).as_str())
                || ["password", "密码", "验证码", "verification code"]
                    .iter()
                    .any(|v| norm(text(n, "hint")).contains(v)))
    }))
}
fn rendered_identity(trace: &Trace, frame: usize, ids: &[&str]) -> Result<Option<String>, String> {
    let f = trace
        .frames
        .get(frame)
        .ok_or("collaboration identity frame absent")?;
    let mut values = nodes(trace.body(f.after)?)?
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == false
                && ids.iter().any(|id| resource(n, id))
                && bounded_identity(text(n, "text"))
                && trace.rendered(frame, n)
        })
        .map(|n| text(n, "text").to_owned())
        .collect::<Vec<_>>();
    values.sort();
    values.dedup();
    Ok(if values.len() == 1 {
        values.pop()
    } else {
        None
    })
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct WorkspaceIdentity {
    tenant: String,
    account: String,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum Page {
    Messages,
    Calendar,
    Workplace,
}
const ROUTE: [Page; 4] = [
    Page::Messages,
    Page::Calendar,
    Page::Workplace,
    Page::Messages,
];
impl Page {
    fn labels(self) -> &'static [&'static str] {
        match self {
            Self::Messages => &["消息", "messages", "messenger"],
            Self::Calendar => &["日历", "日曆", "calendar"],
            Self::Workplace => &["工作台", "workplace"],
        }
    }
    fn roots(self) -> &'static [&'static str] {
        match self {
            Self::Messages => &[
                "main_tab_chat_container",
                "conversation_list",
                "chat_list",
                "message_list_container",
            ],
            Self::Calendar => &[
                "calendar_view_shell_calendar_container",
                "calendar_view",
                "calendar_month_day_view_pager",
                "calendar_rv",
                "list_calendar_view_content",
            ],
            Self::Workplace => &["workplace_fragment_container", "workplace_view"],
        }
    }
}
fn navigation_control(trace: &Trace, frame: usize, page: Page) -> Result<Option<Target>, String> {
    let f = trace
        .frames
        .get(frame)
        .ok_or("collaboration navigation frame absent")?;
    let ns = nodes(trace.body(f.after)?)?;
    let bars = ns
        .iter()
        .filter(|n| {
            usable(n)
                && resource(n, NAV_BAR)
                && Rect::parse(&n["bounds_array"]).is_ok_and(|r| f.window.contains(r))
        })
        .collect::<Vec<_>>();
    if bars.len() != 1 {
        return Ok(None);
    }
    let bar = Rect::parse(&bars[0]["bounds_array"])?;
    let labels = ns
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == false
                && (page.labels().contains(&norm(text(n, "text")).as_str())
                    || page
                        .labels()
                        .contains(&norm(text(n, "content-desc")).as_str()))
                && Rect::parse(&n["bounds_array"]).is_ok_and(|r| bar.contains(r))
                && trace.rendered(frame, n)
        })
        .collect::<Vec<_>>();
    if labels.len() != 1 {
        return Ok(None);
    }
    let node = labels[0];
    let r = Rect::parse(&node["bounds_array"])?;
    let mut buttons = ns
        .iter()
        .filter(|n| usable(n) && n["clickable"] == true && n["editable"] == false)
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .filter(|b| b.contains(r) && bar.contains(*b) && b.area() < bar.area() / 2)
        .collect::<Vec<_>>();
    buttons.sort_by_key(|r| r.area());
    buttons.dedup();
    let Some(button) = buttons.first().copied() else {
        return Ok(None);
    };
    choose(trace, f.after, Role::Page, node, Some(button))
}
fn workspace(trace: &Trace, frame: usize) -> Result<Option<WorkspaceIdentity>, String> {
    let f = trace
        .frames
        .get(frame)
        .ok_or("collaboration workspace frame absent")?;
    if authentication_surface(trace.body(f.after)?)? {
        return Ok(None);
    }
    let Some(tenant) = rendered_identity(trace, frame, TENANT_IDS)? else {
        return Ok(None);
    };
    let Some(account) = rendered_identity(trace, frame, ACCOUNT_IDS)? else {
        return Ok(None);
    };
    for page in [Page::Messages, Page::Calendar, Page::Workplace] {
        if navigation_control(trace, frame, page)?.is_none() {
            return Ok(None);
        }
    }
    Ok(Some(WorkspaceIdentity { tenant, account }))
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct PageContent {
    region: Rect,
    pixels_sha256: String,
    body_sha256: String,
}
fn page_content(trace: &Trace, frame: usize, page: Page) -> Result<Option<PageContent>, String> {
    let f = trace
        .frames
        .get(frame)
        .ok_or("collaboration page frame absent")?;
    let body = trace.body(f.after)?;
    let ns = nodes(body)?;
    if authentication_surface(body)? {
        return Ok(None);
    }
    let regions = ns
        .iter()
        .filter(|n| usable(n) && page.roots().iter().any(|r| resource(n, r)))
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .filter(|r| {
            f.window.contains(*r)
                && r.height() >= f.window.height() / 3
                && f.patches.contains_key(r)
        })
        .collect::<std::collections::BTreeSet<_>>();
    // Nested UI containers may refer to one body; use the largest observed
    // source-fixed region, never a caller coordinate or arbitrary screen.
    let Some(region) = regions.iter().max_by_key(|r| r.area()).copied() else {
        return Ok(None);
    };
    let texts = ns
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == false
                && trace.rendered(frame, n)
                && Rect::parse(&n["bounds_array"]).is_ok_and(|r| region.contains(r))
                && !text(n, "text").trim().is_empty()
                && ![Page::Messages, Page::Calendar, Page::Workplace]
                    .iter()
                    .any(|p| p.labels().contains(&norm(text(n, "text")).as_str()))
        })
        .map(|n| norm(text(n, "text")))
        .collect::<std::collections::BTreeSet<_>>();
    let substantive = match page {
        Page::Messages => {
            texts.len() >= 2
                || texts.iter().any(|s| {
                    ["暂无消息", "暫無消息", "no messages", "no chats yet"].contains(&s.as_str())
                })
        }
        Page::Calendar => {
            texts
                .iter()
                .filter(|s| s.parse::<u8>().is_ok_and(|d| (1..=31).contains(&d)))
                .count()
                >= 3
        }
        Page::Workplace => {
            texts.len() >= 2
                && ns
                    .iter()
                    .filter(|n| {
                        image(n)
                            && trace.rendered(frame, n)
                            && Rect::parse(&n["bounds_array"]).is_ok_and(|r| region.contains(r))
                    })
                    .count()
                    >= 2
        }
    };
    if !substantive {
        return Ok(None);
    }
    Ok(Some(PageContent {
        region,
        pixels_sha256: f.patches[&region].sha256.clone(),
        body_sha256: digest(
            serde_json::to_vec(&texts)
                .map_err(|e| e.to_string())?
                .as_slice(),
        ),
    }))
}
struct Navigation {
    page: Page,
    origin: usize,
    action: usize,
    frame: usize,
    content: PageContent,
}
struct Reopen {
    trace: Trace,
    frame: usize,
    workspace: Option<WorkspaceIdentity>,
    login: bool,
}
pub(super) struct CollaborationExecution {
    first: Trace,
    initial: usize,
    workspace: Option<WorkspaceIdentity>,
    login: bool,
    target_owned_accounts: usize,
    navigation: Vec<Navigation>,
    document: Option<document::DocumentExecution>,
    stop: &'static str,
    reopened: Option<Reopen>,
    original_end: Instant,
}
impl CollaborationExecution {
    pub(super) fn first_counts(&self) -> (u32, u32) {
        self.first.counts()
    }
    pub(super) fn reopened_counts(&self) -> Option<(u32, u32)> {
        self.reopened.as_ref().map(|x| x.trace.counts())
    }
    pub(super) fn target_owned_accounts(&self) -> usize {
        self.target_owned_accounts
    }
    pub(super) fn should_reopen(&self) -> bool {
        self.reopened.is_none() && (self.login || self.workspace.is_some())
    }
    pub(super) fn observe_reopen(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &mut NativeApplicationInspector,
        first: &NativeUiTranscript,
        end: Instant,
    ) -> Result<(), String> {
        need(
            end == self.original_end && self.should_reopen(),
            "collaboration reopen lost its original scope",
        )?;
        self.guard_immutable(first, None)?;
        let mut trace = Trace::new(true);
        let frame = trace.frame(s, i, end)?;
        let identity = workspace(&trace, frame)?;
        let login = authentication_surface(trace.body(trace.frames[frame].after)?)?;
        self.reopened = Some(Reopen {
            trace,
            frame,
            workspace: identity,
            login,
        });
        before(end)
    }
    fn guard_first(&self, t: &NativeUiTranscript) -> Result<(), String> {
        self.first.guard(t)?;
        need(
            self.initial == 0
                && self.workspace == workspace(&self.first, self.initial)?
                && self.login
                    == authentication_surface(
                        self.first.body(self.first.frames[self.initial].after)?,
                    )?,
            "collaboration initial actual workspace/login evidence changed",
        )?;
        need(
            self.navigation.len() <= ROUTE.len(),
            "collaboration navigation route length differs",
        )?;
        let mut prior = self.initial;
        for (n, page) in self.navigation.iter().enumerate() {
            let chosen = navigation_control(&self.first, page.origin, ROUTE[n])?
                .ok_or("collaboration retained route has no original unique navigation control")?;
            let step = &self.first.steps[page.action];
            need(
                page.page == ROUTE[n]
                    && page.origin == prior
                    && self.workspace.is_some()
                    && self.target_owned_accounts > 0
                    && step.op == Operation::Click
                    && step
                        .target
                        .as_ref()
                        .is_some_and(|(origin, role, node, area)| {
                            *origin == chosen.origin
                                && *role == Role::Page
                                && node == &chosen.node
                                && *area == chosen.container
                        })
                    && self.first.frames[page.origin].after < page.action
                    && page.action < self.first.frames[page.frame].before
                    && page_content(&self.first, page.frame, page.page)?.as_ref()
                        == Some(&page.content),
                "collaboration page result is detached from its actual scoped navigation",
            )?;
            prior = page.frame;
        }
        if let Some(document) = &self.document {
            need(
                self.navigation.len() == ROUTE.len() && document.origin() == prior,
                "declared document is not after the complete original readonly navigation",
            )?;
            document.guard(
                &self.first,
                self.workspace
                    .as_ref()
                    .ok_or("document has no actual workspace")?,
            )?;
        }
        need(
            self.first.actions()
                == self.navigation.len() as u32 + self.document.as_ref().map_or(0, |v| v.actions()),
            "collaboration readonly route contains an extra mutation",
        )?;
        Ok(())
    }
    pub(super) fn guard_immutable(
        &self,
        first: &NativeUiTranscript,
        reopened: Option<&NativeUiTranscript>,
    ) -> Result<(), String> {
        self.guard_first(first)?;
        match (&self.reopened, reopened) {
            (None, None) => {}
            (Some(r), Some(next)) => {
                r.trace.guard(next)?;
                need(
                    first.task() != next.task()
                        && first.journal() != next.journal()
                        && first.engine().application() == next.engine().application()
                        && first.engine().facts().main == next.engine().facts().main
                        && r.workspace == workspace(&r.trace, r.frame)?
                        && r.login
                            == authentication_surface(
                                r.trace.body(r.trace.frames[r.frame].after)?,
                            )?
                        && r.trace.actions() == 0,
                    "collaboration actual distinct reopen or readonly identity differs",
                )?;
            }
            _ => return Err(
                "collaboration saved comparisons cannot replace its retained actual second history"
                    .into(),
            ),
        }
        Ok(())
    }
    fn same_reopened_workspace(&self) -> bool {
        !self.login
            && self.target_owned_accounts > 0
            && self.workspace.is_some()
            && self
                .reopened
                .as_ref()
                .is_some_and(|r| !r.login && r.workspace == self.workspace)
    }
    fn navigation_complete(&self) -> bool {
        self.same_reopened_workspace()
            && self.navigation.len() == 4
            && self.navigation[0].content.body_sha256 == self.navigation[3].content.body_sha256
            && self.navigation[0].content.pixels_sha256 != self.navigation[1].content.pixels_sha256
            && self.navigation[1].content.pixels_sha256 != self.navigation[2].content.pixels_sha256
            && workspace(&self.first, self.navigation[3].frame)
                .ok()
                .flatten()
                == self.workspace
    }
    pub(super) fn completed_gates(&self) -> Vec<&'static str> {
        let mut out = vec![];
        if self.same_reopened_workspace() {
            out.push("collaboration.account")
        }
        if self.navigation_complete() {
            out.push("collaboration.navigation");
            if self.document.is_some() {
                out.push("collaboration.search");
                out.push("collaboration.documents");
            }
        }
        out
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        let phase = |trace: &Trace| -> Result<Value, String> {
            Ok(json!({
            "actual_ui_requests":trace.requests(),"actual_input_actions":trace.actions(),
            "actual_commands":trace.counts().0,"retained_reply_bytes":trace.retained_bytes,
            "actual_scoped_pixels":trace.frames.iter().map(|f|f.pixels.comparison()).collect::<Result<Vec<_>,_>>()?,
            "decoded_rgb_retained":false}))
        };
        Ok(
            json!({"schema":"droidloom.collaboration-actual-guest-execution.v1","package":PACKAGE,
            "original_apk_sha256":ORIGINAL_APK_SHA256,
            "static_resources_sha256":"dfac362be48d62aeff82ed991074b5fbc5df9a6a285256e5a65fd6f7b896eb73",
            "first":phase(&self.first)?,"reopened":self.reopened.as_ref().map(|r|phase(&r.trace)).transpose()?,
            "target_owned_registered_accounts":self.target_owned_accounts,
            "account_registration_is_authentication":false,"login_entry_scoped_progress":self.login,
            "workspace_identity":self.workspace.as_ref().map(|w|json!({"tenant_sha256":digest(w.tenant.as_bytes()),"account_sha256":digest(w.account.as_bytes())})),
            "observed_readonly_pages":self.navigation.iter().map(|n|n.page).collect::<Vec<_>>(),
            "stop":self.stop,"completed_business_gates":self.completed_gates(),
            "declared_readonly_document":self.document.as_ref().map(|v|v.comparison()),
            "search_document_pending":self.document.is_none(),
            "missing_document_condition":"normally_declared_document_fixture_and_matching_actual_authorized_workspace_body_image_scroll_return",
            "compose_pending":"uniquely_owned_unsent_local_draft_with_actual_reversible_restore",
            "recovery_pending":"declared_owned_denial_or_unavailable_resource_and_normal_prerequisite_restore",
            "message_invite_post_upload_order_payment_otp_login_or_account_change_attempted":false,
            "host_network_or_permission_state_changed":false,"runtime_qualified":false,"production_ready":false,"comparison_only":true}),
        )
    }
}
pub(super) fn run(
    s: &mut NativeUiSession<'_, '_>,
    i: &mut NativeApplicationInspector,
    scope: &droidloom_supervisor::control::NativeUiPermissionWindow,
    main: &droidloom_supervisor::main_custody::RuntimeMainCustody,
    application: &ApplicationInspection,
    fixture: Option<&droidloom_supervisor::working_qualification::FeishuReadonlyFixture>,
    end: Instant,
) -> Result<CollaborationExecution, String> {
    require_application(application)?;
    if let Some(fixture) = fixture {
        fixture.validate().map_err(|e| e.to_string())?;
    }
    let count = scope.require_readonly_subject(main, application, end)?;
    let mut first = Trace::new(false);
    let initial = first.frame(s, i, end)?;
    let identity = workspace(&first, initial)?;
    let login = authentication_surface(first.body(first.frames[initial].after)?)?;
    let mut out = CollaborationExecution {
        first,
        initial,
        workspace: identity,
        login,
        target_owned_accounts: count,
        navigation: vec![],
        document: None,
        stop: "workspace_surface_or_account_source_not_observed",
        reopened: None,
        original_end: end,
    };
    if out.login {
        out.stop = "login_entry_only_no_authenticated_business";
        return Ok(out);
    }
    if out.workspace.is_none() {
        return Ok(out);
    }
    if count == 0 {
        out.stop = "no_target_owned_registered_account_source_authentication_not_inferred";
        return Ok(out);
    }
    let mut previous = initial;
    for page in ROUTE {
        scope.require_readonly_subject(main, application, end)?;
        let Some(target) = navigation_control(&out.first, previous, page)? else {
            out.stop = "unique_supported_readonly_navigation_control_not_observed";
            return Ok(out);
        };
        let action = out
            .first
            .perform(s, i, target, Operation::Click, None, end)?;
        let frame = out.first.frame(s, i, end)?;
        let Some(content) = page_content(&out.first, frame, page)? else {
            // A real acknowledged page change with insufficient body evidence
            // is retained as failure, not retried or erased as an absent action.
            return Err("collaboration navigation acknowledged but expected actual rendered page content is incomplete".into());
        };
        out.navigation.push(Navigation {
            page,
            origin: previous,
            action,
            frame,
            content,
        });
        previous = frame;
    }
    need(
        workspace(&out.first, previous)? == out.workspace,
        "collaboration readonly route returned to a different actual workspace/account",
    )?;
    if let Some(fixture) = fixture {
        scope.require_readonly_subject(main, application, end)?;
        out.document = document::run(
            &mut out.first,
            s,
            i,
            fixture,
            out.workspace
                .as_ref()
                .ok_or("document missing actual workspace")?,
            previous,
            end,
        )?;
    }
    out.stop = if out.document.is_some() {
        "readonly_navigation_search_document_observed_owned_draft_and_recovery_prerequisites_pending"
    } else {
        "readonly_navigation_observed_declared_document_or_matching_actual_workspace_pending"
    };
    before(end)?;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_supervisor::control::application_probe::{InstalledApk, RuntimeEpoch};
    #[test]
    fn collaboration_source_contract_rejects_name_only_version_only_and_changed_split_sets() {
        let original = ApplicationInspection {
            package: PACKAGE.into(),
            user: 0,
            uid: 10213,
            version_code: 8_080_550,
            epoch: RuntimeEpoch {
                boot_id: "comparison".into(),
                cell_host_pid: 1,
                framework_host_pid: 2,
                framework_start_ticks: 3,
            },
            apks: vec![InstalledApk {
                name: "base.apk".into(),
                path: "/data/app/observed/base.apk".into(),
                bytes: ORIGINAL_APK_BYTES,
                sha256: ORIGINAL_APK_SHA256.into(),
            }],
        };
        require_application(&original).unwrap();
        for case in 0..7 {
            let mut altered = original.clone();
            match case {
                0 => altered.apks[0].sha256 = "0".repeat(64),
                1 => altered.apks[0].bytes += 1,
                2 => altered.apks.push(altered.apks[0].clone()),
                3 => altered.version_code += 1,
                4 => altered.package = "com.ss.android.article.lite".into(),
                5 => altered.user = 10,
                _ => altered.uid = 2000,
            }
            assert!(require_application(&altered).is_err());
        }
        // Comparison validation alone produces no CollaborationExecution, UI session,
        // retained transcript, application signature or accepted gate.
    }
    #[test]
    fn collaboration_real_crop_rejects_blank_pale_wrong_dimensions_and_outside_window() {
        let window = Rect([20, 30, 84, 94]);
        let area = Rect([24, 34, 80, 90]);
        for color in [0u8, 240, 255] {
            assert!(patch(&vec![color; 64 * 64 * 3], 64, 64, window, area).is_err());
        }
        let mut pixels = vec![255; 64 * 64 * 3];
        for y in 0..64 {
            for x in 0..64 {
                let p = 3 * (y * 64 + x);
                pixels[p] = (x * 4) as u8;
                pixels[p + 1] = (y * 4) as u8;
                pixels[p + 2] = 40;
            }
        }
        let real = patch(&pixels, 64, 64, window, area).unwrap();
        assert!(!materially_changed(&real, &real));
        assert!(patch(&pixels, 63, 64, window, area).is_err());
        assert!(patch(&pixels, 64, 64, window, Rect([0, 0, 60, 60])).is_err());
        assert!(patch(&pixels[..pixels.len() - 1], 64, 64, window, area).is_err());
        let inverted: Vec<_> = pixels.iter().map(|v| 255 - v).collect();
        assert!(materially_changed(
            &real,
            &patch(&inverted, 64, 64, window, area).unwrap()
        ));
        let mut single = real.clone();
        single.rgb[0] ^= 255;
        single.sha256 = digest(&single.rgb);
        assert!(!materially_changed(&real, &single));
    }

    #[test]
    fn collaboration_login_or_registered_account_or_ui_identity_alone_cannot_complete_business() {
        let end = Instant::now() + std::time::Duration::from_secs(60);
        for count in [0, 1, 128] {
            for login in [false, true] {
                let mut e = CollaborationExecution {
                    first: Trace::new(false),
                    initial: 0,
                    workspace: None,
                    login,
                    target_owned_accounts: count,
                    navigation: vec![],
                    document: None,
                    stop: "test",
                    reopened: None,
                    original_end: end,
                };
                assert!(e.completed_gates().is_empty());
                e.workspace = Some(WorkspaceIdentity {
                    tenant: "owned-test".into(),
                    account: "owned-account".into(),
                });
                assert!(e.completed_gates().is_empty());
                e.reopened = Some(Reopen {
                    trace: Trace::new(true),
                    frame: 0,
                    workspace: None,
                    login: true,
                });
                assert!(e.completed_gates().is_empty());
            }
        }
    }
    #[test]
    fn collaboration_source_names_never_accept_foreign_package_or_login_placeholder() {
        assert!(bounded_identity("实验工作区"));
        for name in ["", " 登录", "登录", "sign in", "tenant name", "name\nvalue"] {
            assert!(!bounded_identity(name), "{name:?}");
        }
        let node = json!({"resource-id":"com.ss.android.lark:id/tenant_name"});
        assert!(resource(&node, "tenant_name"));
        assert!(!resource(
            &json!({"resource-id":"com.example.helper:id/tenant_name"}),
            "tenant_name"
        ));
        assert!(!resource(
            &json!({"resource-id":"tenant_name"}),
            "tenant_name"
        ));
        for page in ROUTE {
            for forbidden in [
                "发送",
                "邀请",
                "send",
                "invite",
                "publish",
                "upload",
                "新建会议",
                "buy",
            ] {
                assert!(!page.labels().contains(&forbidden));
            }
        }
    }
    #[test]
    fn collaboration_maximal_readonly_document_route_preserves_exact_navigation_and_reopen() {
        assert_eq!(FIRST_REQUESTS, 43);
        assert_eq!(SECOND_REQUESTS, 2);
        assert_eq!(FIRST_CAPTURES, 12);
        assert_eq!(SECOND_CAPTURES, 1);
        assert_eq!(first_max_extra_actions(), 13);
        assert_eq!(reopen_max_actions(), 0);
        assert_eq!(first_max_extra_ui_commands(), 213);
        assert_eq!(reopen_max_ui_commands(), 13);
        assert_eq!(additional_window_seconds(), 6710);
        assert_eq!(second_business_seconds(), 370);
        assert!(!supports("com.larksuite.suite"));
        assert!(!supports("com.ss.android.article.news"));
        assert_eq!(
            ROUTE,
            [
                Page::Messages,
                Page::Calendar,
                Page::Workplace,
                Page::Messages
            ]
        );
    }
}
