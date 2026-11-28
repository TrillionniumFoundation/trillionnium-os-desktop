//! Read-only public news business observations from the actual owned session.
//! The selected original APK, native replies, decoded window pixels and finished
//! histories remain bound together. Static resource names never mint a gate.
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeUiReply, NativeUiSelector, NativeUiSession,
    NativeUiTranscript, RetainedScopedWindowPixels,
};
use serde::Serialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::time::Instant;

const PACKAGE: &str = "com.ss.android.article.news";
const ORIGINAL_APK_SHA256: &str =
    "43436ccd57fb537a2edc4eaa4a88bed7e681901a42faf1194136d27f56b8387a";
const ORIGINAL_APK_BYTES: u64 = 202_308_082;
const QUERIES: [&str; 2] = ["航天", "中国航天"];
const FIRST_REQUESTS: usize = 48;
const SECOND_REQUESTS: usize = 6;
const FIRST_CAPTURES: usize = 8;
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
    16
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
    need(Instant::now() < end, "news original window expired")
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
            && a.version_code == 19_300
            && a.apks.len() == 1
            && a.apks[0].name == "base.apk"
            && a.apks[0].bytes == ORIGINAL_APK_BYTES
            && a.apks[0].sha256 == ORIGINAL_APK_SHA256,
        "news source facts require the actual complete selected original PM APK",
    )
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct Rect([i64; 4]);
impl Rect {
    fn parse(v: &Value) -> Result<Self, String> {
        let a = v
            .as_array()
            .filter(|v| v.len() == 4)
            .ok_or("news rectangle absent")?;
        let v = a
            .iter()
            .map(Value::as_i64)
            .collect::<Option<Vec<_>>>()
            .ok_or("news rectangle noninteger")?;
        need(
            v.iter().all(|v| (0..=8192).contains(v)) && v[2] > v[0] && v[3] > v[1],
            "news rectangle bound",
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
        "news needs the actual complete same-package focused tree",
    )?;
    body["nodes"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 2000)
        .map(Vec::as_slice)
        .ok_or_else(|| "news actual nodes absent".into())
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
fn unwanted(s: &str) -> bool {
    let s = norm(s);
    [
        "广告",
        "赞助",
        "推广",
        "登录",
        "登陆",
        "注册",
        "支付",
        "购买",
        "开通会员",
        "评论",
        "转发",
        "发帖",
        "私信",
        "下载",
        "加载中",
        "点击重试",
        "网络异常",
        "network error",
        "sign in",
        "sponsored",
    ]
    .iter()
    .any(|v| s.contains(v))
}
fn title(s: &str) -> bool {
    (8..=160).contains(&s.chars().count())
        && !unwanted(s)
        && !s.contains("http")
        && !s.contains('\n')
        && !s.contains('…')
        && !s.ends_with("...")
}
fn publisher(s: &str) -> bool {
    let s = s.trim();
    (2..=32).contains(&s.chars().count())
        && !unwanted(s)
        && s.chars().any(|c| c.is_alphabetic())
        && !s.chars().any(|c| c.is_ascii_digit())
        && ![
            "小时前",
            "分钟前",
            "天前",
            "刚刚",
            "阅读",
            "推荐",
            "关注",
            "收藏",
            "搜索",
            "展开",
            "更多",
            "置顶",
            "热榜",
        ]
        .iter()
        .any(|v| s.contains(v))
}
fn paragraph(s: &str) -> bool {
    let count = s.chars().count();
    (24..=8192).contains(&count)
        && !unwanted(s)
        && s.chars().filter(|c| c.is_alphabetic()).count() >= 16
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
        "news pixel crop does not match actual window",
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
    let lo = *out.iter().min().ok_or("news pixel patch empty")?;
    let hi = *out.iter().max().unwrap();
    need(
        hi - lo >= 48
            && out
                .chunks_exact(3)
                .filter(|p| p.iter().any(|v| *v < 220))
                .count()
                >= 8
            && out.chunks_exact(3).any(|p| p.iter().any(|v| *v < 160)),
        "news crop is blank, pale, or lacks contrast",
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
    Story,
    SearchEntry,
    Input,
    Submit,
    EditQuery,
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
            "news fixed request/action budget exhausted",
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
            .ok_or("news retained reply byte overflow")?;
        need(
            self.retained_bytes <= RETAINED_REPLY_BYTES,
            "news retained reply memory bound exceeded",
        )?;
        let idx = self.steps.len();
        self.steps.push(step);
        Ok(idx)
    }
    fn body(&self, n: usize) -> Result<&Value, String> {
        self.steps
            .get(n)
            .map(|s| s.reply.body())
            .ok_or_else(|| "news reply index differs".into())
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
        self.reserve(op.requests(), true, end)?;
        let reply = match op {
            Operation::Click => s.click(i, target.selector)?,
            Operation::SetText => {
                s.set_text(i, target.selector, written.ok_or("news typed text absent")?)?
            }
            Operation::Forward => s.scroll_forward(i, target.selector)?,
            Operation::Backward => s.scroll_backward(i, target.selector)?,
            Operation::Dump => return Err("news mutation cannot select Dump".into()),
        };
        if op != Operation::SetText {
            need(
                same_node(&reply.body()["target"], &target.node),
                "news acknowledged target differs from its actual observed node",
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
                    "news click climbed outside the actual source-chosen control/card",
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
            "news fixed scoped image budget exhausted",
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
            "news window changed across the real pixel observation",
        )?;
        let cmp = pixels.comparison()?;
        let p = &cmp["window"]["bounds"];
        need(
            window
                == Rect([
                    p["left"].as_i64().ok_or("news pixel left")?,
                    p["top"].as_i64().ok_or("news pixel top")?,
                    p["right"].as_i64().ok_or("news pixel right")?,
                    p["bottom"].as_i64().ok_or("news pixel bottom")?,
                ]),
            "news scoped pixel window differs from actual semantic tree",
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
                && (image(n) || !text(n, "text").is_empty() || n["scrollable"] == true)
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
            "news actual rendered patch count exceeds source bound",
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
            "news retained trace limits differ",
        )?;
        for (idx, step) in self.steps.iter().enumerate() {
            need(
                step.reply.body()["ok"] == true,
                "news retained reply failed",
            )?;
            if let Some((origin, _, node, _)) = &step.target {
                need(
                    *origin < idx
                        && self.steps[*origin].op == Operation::Dump
                        && nodes(self.body(*origin)?)?.iter().any(|v| v == node)
                        && usable(node)
                        && step.reply.body()["performed"] == step.op.name(),
                    "news retained action lost its actual source choice",
                )?;
                if step.op != Operation::SetText {
                    need(
                        same_node(node, &step.reply.body()["target"]),
                        "news retained target changed",
                    )?;
                } else {
                    need(
                        step.written.as_ref().is_some_and(|v| {
                            step.reply.body()["characters"].as_u64()
                                == Some(v.chars().count() as u64)
                        }) && step.reply.body()["readback_verified"] == true,
                        "news text readback changed",
                    )?;
                }
            } else {
                need(
                    step.op == Operation::Dump,
                    "news action lacks observed target",
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
                "news actual decoded patch history changed",
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
        "news choice is not an actual usable node",
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
            let mut selector = make(v).map_err(|e| e.to_string())?.enabled();
            if role == Role::Scroll {
                selector = selector.requiring_scrollable();
            }
            return Ok(Some(Target {
                selector,
                node: selected.clone(),
                origin,
                role,
                container,
            }));
        }
    }
    let selector = if role == Role::Input
        && ns
            .iter()
            .filter(|n| usable(n) && n["editable"] == true)
            .count()
            == 1
    {
        Some(NativeUiSelector::editable().enabled())
    } else if role == Role::Scroll
        && ns
            .iter()
            .filter(|n| usable(n) && n["scrollable"] == true)
            .count()
            == 1
    {
        Some(NativeUiSelector::scrollable().enabled())
    } else {
        None
    };
    Ok(selector.map(|selector| Target {
        selector,
        node: selected.clone(),
        origin,
        role,
        container,
    }))
}
fn one_control(
    trace: &Trace,
    origin: usize,
    role: Role,
    query: Option<&str>,
) -> Result<Option<Target>, String> {
    let body = trace.body(origin)?;
    let ns = nodes(body)?;
    let win = Rect::parse(&body["window_context"]["selected_window"]["bounds"])?;
    let matching: Vec<_> = ns
        .iter()
        .filter(|n| {
            if !usable(n) {
                return false;
            }
            let r = Rect::parse(&n["bounds_array"]).unwrap();
            let t = norm(text(n, "text"));
            let d = norm(text(n, "content-desc"));
            let header = r.0[1] < win.0[1] + win.height() / 4 && r.height() < win.height() / 4;
            match role {
                Role::Input => n["editable"] == true && header && search_editor_context(n, ns),
                Role::SearchEntry => {
                    header
                        && n["editable"] == false
                        && (text(n, "resource-id")
                            == "com.ss.android.article.news:id/search_bar_search_icon"
                            || ["搜索", "search", "搜尋"].contains(&t.as_str())
                            || ["搜索", "search", "搜尋"].contains(&d.as_str()))
                }
                Role::Submit => {
                    header
                        && n["clickable"] == true
                        && n["editable"] == false
                        && (["搜索", "search", "搜尋"].contains(&t.as_str())
                            || ["搜索", "search", "搜尋"].contains(&d.as_str()))
                }
                Role::EditQuery => {
                    header
                        && n["editable"] == false
                        && query.is_some_and(|q| t == norm(q) || d == norm(q))
                }
                Role::Back => {
                    header
                        && r.0[0] < win.0[0] + (win.0[2] - win.0[0]) / 3
                        && n["editable"] == false
                        && (["返回", "back", "navigate up", "上一页"].contains(&t.as_str())
                            || ["返回", "back", "navigate up", "上一页"].contains(&d.as_str()))
                }
                Role::Scroll => n["scrollable"] == true,
                Role::Story => false,
            }
        })
        .collect();
    if matching.len() != 1 {
        return Ok(None);
    }
    choose(trace, origin, role, matching[0], None)
}
fn search_editor_context(n: &Value, ns: &[Value]) -> bool {
    let hint = norm(&format!("{} {}", text(n, "hint"), text(n, "content-desc")));
    let excluded = [
        "password",
        "email",
        "phone",
        "account",
        "comment",
        "密码",
        "邮箱",
        "手机",
        "账号",
        "账户",
        "验证码",
        "评论",
        "回复",
    ]
    .iter()
    .any(|s| hint.contains(s));
    !excluded
        && (["search", "搜索", "搜尋"].iter().any(|s| hint.contains(s))
            || ns.iter().any(|x| {
                usable(x)
                    && x["clickable"] == true
                    && x["editable"] == false
                    && ["search", "搜索", "搜尋"].contains(&norm(text(x, "text")).as_str())
            }))
}
fn actual_input(n: &Value) -> Option<&str> {
    if !usable(n) || n["editable"] != true {
        return None;
    }
    if n["showing-hint"] == true && n["value"].as_str().is_none_or(str::is_empty) {
        Some("")
    } else {
        n["value"].as_str().or_else(|| n["text"].as_str())
    }
}
fn query_visible(body: &Value, q: &str) -> Result<bool, String> {
    Ok(nodes(body)?
        .iter()
        .filter(|n| actual_input(n) == Some(q))
        .count()
        == 1)
}
fn click_back(
    trace: &mut Trace,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    origin: usize,
    end: Instant,
) -> Result<Option<usize>, String> {
    let Some(t) = one_control(trace, origin, Role::Back, None)? else {
        return Ok(None);
    };
    Ok(Some(trace.perform(s, i, t, Operation::Click, None, end)?))
}

#[derive(Clone, Debug, PartialEq)]
struct Story {
    title: String,
    publisher: String,
    title_node: Value,
    publisher_node: Value,
    card: Value,
    image: Rect,
}
fn stories(trace: &Trace, frame: usize, query: Option<&str>) -> Result<Vec<Story>, String> {
    let f = trace.frames.get(frame).ok_or("news feed frame absent")?;
    let ns = nodes(trace.body(f.after)?)?;
    let mut out = Vec::new();
    for heading in ns.iter().filter(|n| {
        usable(n) && title(text(n, "text")) && n["editable"] == false && trace.rendered(frame, n)
    }) {
        let title_text = text(heading, "text");
        // Both declared Unicode queries share this exact topic. Query text in
        // an editor or navigation label cannot satisfy a populated story row.
        if query.is_some() && !title_text.contains(QUERIES[0]) {
            continue;
        }
        let title_bounds = Rect::parse(&heading["bounds_array"])?;
        let mut candidates = Vec::new();
        for card in ns
            .iter()
            .filter(|n| usable(n) && n["clickable"] == true && n["editable"] == false)
        {
            let area = Rect::parse(&card["bounds_array"])?;
            if !area.contains(title_bounds)
                || area.area() > f.window.area() * 2 / 3
                || area.height() < 64
            {
                continue;
            }
            let contents: Vec<_> = ns
                .iter()
                .filter(|n| {
                    usable(n) && Rect::parse(&n["bounds_array"]).is_ok_and(|r| area.contains(r))
                })
                .collect();
            if contents.iter().any(|n| {
                ["广告", "推广", "赞助", "sponsored"].contains(&norm(text(n, "text")).as_str())
                    || text(n, "content-desc").contains("播放")
                    || ["SurfaceView", "TextureView"]
                        .iter()
                        .any(|s| text(n, "class").contains(s))
                    || duration_label(text(n, "text"))
            }) {
                continue;
            }
            let labels: Vec<_> = contents
                .iter()
                .copied()
                .filter(|n| {
                    *n != heading
                        && publisher(text(n, "text"))
                        && trace.rendered(frame, n)
                        && Rect::parse(&n["bounds_array"]).is_ok_and(|r| {
                            r.0[1] >= title_bounds.0[3] - 8 && r.0[0] <= title_bounds.0[2]
                        })
                })
                .collect();
            let pictures: Vec<_> = contents
                .iter()
                .copied()
                .filter(|n| image(n) && trace.rendered(frame, n))
                .collect();
            if labels.len() != 1 || pictures.is_empty() {
                continue;
            }
            let picture = pictures
                .iter()
                .min_by_key(|n| Rect::parse(&n["bounds_array"]).unwrap().0[1])
                .unwrap();
            candidates.push(Story {
                title: title_text.into(),
                publisher: text(labels[0], "text").into(),
                title_node: heading.clone(),
                publisher_node: labels[0].clone(),
                card: card.clone(),
                image: Rect::parse(&picture["bounds_array"])?,
            });
        }
        candidates.sort_by_key(|s| Rect::parse(&s.card["bounds_array"]).unwrap().area());
        if let Some(chosen) = candidates.into_iter().next() {
            out.push(chosen);
        }
    }
    out.sort_by_key(|s| Rect::parse(&s.card["bounds_array"]).unwrap().0[1]);
    out.dedup_by(|a, b| same_title(&a.title, &b.title) && a.publisher == b.publisher);
    need(out.len() <= 32, "news visible story bound exceeded")?;
    // Ambiguous overlapping cards are not treated as separate feed results.
    if out.iter().enumerate().any(|(i, a)| {
        out.iter().skip(i + 1).any(|b| {
            !Rect::parse(&a.card["bounds_array"])
                .unwrap()
                .disjoint(Rect::parse(&b.card["bounds_array"]).unwrap())
        })
    }) {
        return Ok(vec![]);
    }
    Ok(out)
}
fn duration_label(s: &str) -> bool {
    let Some((a, b)) = s.trim().split_once(':') else {
        return false;
    };
    !a.is_empty()
        && a.len() <= 3
        && b.len() == 2
        && a.bytes().chain(b.bytes()).all(|b| b.is_ascii_digit())
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Article {
    title: String,
    publisher: String,
    paragraphs: BTreeMap<String, Rect>,
    images: Vec<Rect>,
}
fn article(trace: &Trace, frame: usize, selected: &Story) -> Result<Option<Article>, String> {
    let f = trace.frames.get(frame).ok_or("news article frame absent")?;
    let ns = nodes(trace.body(f.after)?)?;
    let titles: Vec<_> = ns
        .iter()
        .filter(|n| {
            usable(n) && same_title(text(n, "text"), &selected.title) && trace.rendered(frame, n)
        })
        .collect();
    let publishers: Vec<_> = ns
        .iter()
        .filter(|n| usable(n) && text(n, "text") == selected.publisher && trace.rendered(frame, n))
        .collect();
    if titles.len() != 1 || publishers.len() != 1 {
        return Ok(None);
    }
    let heading = Rect::parse(&titles[0]["bounds_array"])?;
    let source = Rect::parse(&publishers[0]["bounds_array"])?;
    if source.0[1] < heading.0[1] || source.0[1] - heading.0[3] > f.window.height() / 3 {
        return Ok(None);
    }
    let paragraphs = body_paragraphs(trace, frame, Some(heading.0[3]))?;
    let images: Vec<_> = ns
        .iter()
        .filter(|n| image(n) && trace.rendered(frame, n))
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .filter(|r| r.0[1] >= source.0[3] && r.area() < f.window.area() * 3 / 4)
        .collect();
    if paragraphs.values().map(|r| r.area()).sum::<i64>() < f.window.area() / 30
        || paragraphs.keys().map(|s| s.chars().count()).sum::<usize>() < 120
        || images.is_empty()
    {
        return Ok(None);
    }
    Ok(Some(Article {
        title: selected.title.clone(),
        publisher: selected.publisher.clone(),
        paragraphs,
        images,
    }))
}
fn body_paragraphs(
    trace: &Trace,
    frame: usize,
    below: Option<i64>,
) -> Result<BTreeMap<String, Rect>, String> {
    let f = trace.frames.get(frame).ok_or("news body frame absent")?;
    let mut result = BTreeMap::new();
    for n in nodes(trace.body(f.after)?)?.iter().filter(|n| {
        usable(n)
            && n["clickable"] == false
            && n["editable"] == false
            && paragraph(text(n, "text"))
            && trace.rendered(frame, n)
    }) {
        let r = Rect::parse(&n["bounds_array"])?;
        if below.is_none_or(|y| r.0[1] >= y) && f.window.contains(r) {
            result.insert(text(n, "text").into(), r);
        }
    }
    Ok(result)
}
fn visible_identity(trace: &Trace, frame: usize, story: &Story) -> Result<bool, String> {
    let f = trace
        .frames
        .get(frame)
        .ok_or("news identity frame absent")?;
    let ns = nodes(trace.body(f.after)?)?;
    Ok(ns.iter().any(|n| {
        usable(n) && same_title(text(n, "text"), &story.title) && trace.rendered(frame, n)
    }) && ns
        .iter()
        .any(|n| usable(n) && text(n, "text") == story.publisher && trace.rendered(frame, n)))
}
fn same_story(a: &Story, b: &Story) -> bool {
    same_title(&a.title, &b.title) && a.publisher == b.publisher
}

#[derive(Clone)]
struct ArticleFlow {
    feed: usize,
    selected: Story,
    clicked: usize,
    opened: usize,
    facts: Option<Article>,
    forward: Option<usize>,
    scrolled: Option<usize>,
    backward: Option<usize>,
    restored: Option<usize>,
    back: Option<usize>,
    returned: Option<usize>,
}
struct SearchFlow {
    entry: usize,
    input: usize,
    typed: [usize; 2],
    readback: [usize; 2],
    submitted: [usize; 2],
    results: [usize; 2],
    cleared: usize,
    clear_readback: usize,
    back: usize,
    returned: usize,
}
struct Phase {
    trace: Trace,
    article: Option<ArticleFlow>,
    search: Option<SearchFlow>,
    stop: &'static str,
}
impl Phase {
    fn new(second: bool) -> Self {
        Self {
            trace: Trace::new(second),
            article: None,
            search: None,
            stop: "not_observed",
        }
    }
}
struct Reopen {
    trace: Trace,
    frame: usize,
    feed_titles_preserved: bool,
}
pub(super) struct NewsExecution {
    first: Phase,
    reopened: Option<Reopen>,
    original_end: Instant,
}

fn article_flow(
    p: &mut Phase,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    end: Instant,
) -> Result<(), String> {
    let feed = p.trace.frame(s, i, end)?;
    let rows = stories(&p.trace, feed, None)?;
    if rows.len() < 2 {
        p.stop = "public_feed_has_no_two_unambiguous_rendered_article_cards";
        return Ok(());
    }
    let selected = rows[0].clone();
    let origin = p.trace.frames[feed].after;
    let Some(t) = choose(
        &p.trace,
        origin,
        Role::Story,
        &selected.title_node,
        Some(Rect::parse(&selected.card["bounds_array"])?),
    )?
    else {
        p.stop = "article_card_has_no_unique_actual_selector";
        return Ok(());
    };
    let clicked = p.trace.perform(s, i, t, Operation::Click, None, end)?;
    let opened = p.trace.frame(s, i, end)?;
    if !visible_identity(&p.trace, opened, &selected)? {
        p.stop = "opened_article_title_or_publisher_does_not_match_feed";
        return Ok(());
    }
    let facts = article(&p.trace, opened, &selected)?;
    p.article = Some(ArticleFlow {
        feed,
        selected,
        clicked,
        opened,
        facts,
        forward: None,
        scrolled: None,
        backward: None,
        restored: None,
        back: None,
        returned: None,
    });
    if p.article.as_ref().unwrap().facts.is_some() {
        let origin = p.trace.frames[opened].after;
        if let Some(t) = one_control(&p.trace, origin, Role::Scroll, None)? {
            if t.node["supported_actions"]
                .as_array()
                .is_some_and(|a| a.iter().any(|v| v == 0x1000))
            {
                let forward = p.trace.perform(s, i, t, Operation::Forward, None, end)?;
                let scrolled = p.trace.frame(s, i, end)?;
                let f = p.article.as_mut().unwrap();
                f.forward = Some(forward);
                f.scrolled = Some(scrolled);
                let origin = p.trace.frames[scrolled].after;
                if let Some(t) = one_control(&p.trace, origin, Role::Scroll, None)? {
                    if t.node["supported_actions"]
                        .as_array()
                        .is_some_and(|a| a.iter().any(|v| v == 0x2000))
                    {
                        let back = p.trace.perform(s, i, t, Operation::Backward, None, end)?;
                        let restored = p.trace.frame(s, i, end)?;
                        p.article.as_mut().unwrap().backward = Some(back);
                        p.article.as_mut().unwrap().restored = Some(restored);
                    }
                }
            }
        }
    }
    let origin = p.trace.dump(s, i, end)?;
    let Some(back) = click_back(&mut p.trace, s, i, origin, end)? else {
        p.stop = "actual_owned_article_back_control_unavailable";
        return Ok(());
    };
    let returned = p.trace.frame(s, i, end)?;
    if stories(&p.trace, returned, None)?
        .iter()
        .any(|row| same_story(row, &p.article.as_ref().unwrap().selected))
    {
        let f = p.article.as_mut().unwrap();
        f.back = Some(back);
        f.returned = Some(returned);
        p.stop = "article_returned_to_actual_feed";
    } else {
        p.stop = "returned_feed_does_not_retain_the_selected_story";
    }
    Ok(())
}

fn search_flow(
    p: &mut Phase,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    end: Instant,
) -> Result<(), String> {
    let Some(feed) = p.article.as_ref().and_then(|a| a.returned) else {
        return Ok(());
    };
    let origin = p.trace.frames[feed].after;
    let Some(entry) = one_control(&p.trace, origin, Role::SearchEntry, None)? else {
        p.stop = "actual_feed_search_entry_unavailable";
        return Ok(());
    };
    let entry = p.trace.perform(s, i, entry, Operation::Click, None, end)?;
    let input = p.trace.dump(s, i, end)?;
    let mut current = input;
    let mut typed = Vec::new();
    let mut readbacks = Vec::new();
    let mut submitted = Vec::new();
    let mut frames = Vec::new();
    for (number, query) in QUERIES.iter().enumerate() {
        let mut control = one_control(&p.trace, current, Role::Input, None)?;
        if control.is_none() && number == 1 {
            if let Some(edit) = one_control(&p.trace, current, Role::EditQuery, Some(QUERIES[0]))? {
                p.trace.perform(s, i, edit, Operation::Click, None, end)?;
                current = p.trace.dump(s, i, end)?;
                control = one_control(&p.trace, current, Role::Input, None)?;
            }
        }
        let Some(control) = control else {
            p.stop = "actual_search_editor_unavailable";
            return Ok(());
        };
        let previous = if number == 0 { "" } else { QUERIES[0] };
        if actual_input(&control.node) != Some(previous) {
            p.stop = "existing_nonempty_or_unowned_search_input_preserved";
            return Ok(());
        }
        typed.push(
            p.trace
                .perform(s, i, control, Operation::SetText, Some(query), end)?,
        );
        let readback = p.trace.dump(s, i, end)?;
        if !query_visible(p.trace.body(readback)?, query)? {
            p.stop = "unicode_search_query_actual_readback_differs";
            return Ok(());
        }
        readbacks.push(readback);
        let Some(submit) = one_control(&p.trace, readback, Role::Submit, None)? else {
            p.stop = "actual_search_submit_control_unavailable";
            return Ok(());
        };
        submitted.push(p.trace.perform(s, i, submit, Operation::Click, None, end)?);
        let frame = p.trace.frame(s, i, end)?;
        let results = stories(&p.trace, frame, Some(query))?;
        if results.len() < 2 {
            p.stop = "search_has_no_two_actual_rendered_topic_results";
            return Ok(());
        }
        current = p.trace.frames[frame].after;
        frames.push(frame);
    }
    let Some(clear) = one_control(&p.trace, current, Role::Input, None)? else {
        p.stop = "owned_query_restore_editor_unavailable";
        return Ok(());
    };
    if actual_input(&clear.node) != Some(QUERIES[1]) {
        p.stop = "owned_query_changed_before_empty_input_restoration";
        return Ok(());
    }
    let cleared = p
        .trace
        .perform(s, i, clear, Operation::SetText, Some(""), end)?;
    let clear_readback = p.trace.dump(s, i, end)?;
    if !query_visible(p.trace.body(clear_readback)?, "")? {
        p.stop = "original_empty_query_not_actually_restored";
        return Ok(());
    }
    let Some(back) = click_back(&mut p.trace, s, i, clear_readback, end)? else {
        p.stop = "search_back_control_unavailable";
        return Ok(());
    };
    let returned = p.trace.frame(s, i, end)?;
    if stories(&p.trace, returned, None)?.len() < 2 {
        p.stop = "search_returned_without_a_populated_feed";
        return Ok(());
    }
    p.search = Some(SearchFlow {
        entry,
        input,
        typed: [typed[0], typed[1]],
        readback: [readbacks[0], readbacks[1]],
        submitted: [submitted[0], submitted[1]],
        results: [frames[0], frames[1]],
        cleared,
        clear_readback,
        back,
        returned,
    });
    p.stop = "public_search_edit_and_original_empty_input_return_observed";
    Ok(())
}
fn scrolling_proved(trace: &Trace, flow: &ArticleFlow) -> Result<bool, String> {
    let (
        Some(facts),
        Some(forward),
        Some(scrolled),
        Some(backward),
        Some(restored),
        Some(back),
        Some(returned),
    ) = (
        &flow.facts,
        flow.forward,
        flow.scrolled,
        flow.backward,
        flow.restored,
        flow.back,
        flow.returned,
    )
    else {
        return Ok(false);
    };
    let a = &trace.frames[flow.opened];
    let z = &trace.frames[scrolled];
    let r = &trace.frames[restored];
    let old = body_paragraphs(trace, flow.opened, None)?;
    let new = body_paragraphs(trace, scrolled, None)?;
    let restored_body = body_paragraphs(trace, restored, None)?;
    let (_, _, scroll_node, _) = trace.steps[forward]
        .target
        .as_ref()
        .ok_or("news scroll source absent")?;
    let area = Rect::parse(&scroll_node["bounds_array"])?;
    let forward_pixels = a
        .patches
        .get(&area)
        .zip(z.patches.get(&area))
        .is_some_and(|(a, b)| materially_changed(a, b));
    let reverse_pixels = z
        .patches
        .get(&area)
        .zip(r.patches.get(&area))
        .is_some_and(|(a, b)| materially_changed(a, b));
    let moved_up = old
        .iter()
        .any(|(body, rect)| new.get(body).is_some_and(|r| r.0[1] + 24 < rect.0[1]));
    let replaced =
        old.keys().any(|k| !new.contains_key(k)) && new.keys().any(|k| !old.contains_key(k));
    let header_restored = visible_identity(trace, restored, &flow.selected)?
        && facts
            .paragraphs
            .keys()
            .any(|k| restored_body.contains_key(k));
    Ok(trace.steps[forward].op == Operation::Forward
        && trace.steps[backward].op == Operation::Backward
        && trace.steps[back].op == Operation::Click
        && flow.opened < scrolled
        && scrolled < restored
        && restored < returned
        && a.window == z.window
        && z.window == r.window
        && forward_pixels
        && reverse_pixels
        && (moved_up || replaced)
        && new.keys().map(|s| s.chars().count()).sum::<usize>() >= 80
        && header_restored
        && stories(trace, returned, None)?
            .iter()
            .any(|s| same_story(s, &flow.selected)))
}
impl NewsExecution {
    pub(super) fn first_counts(&self) -> (u32, u32) {
        self.first.trace.counts()
    }
    pub(super) fn reopened_counts(&self) -> Option<(u32, u32)> {
        self.reopened.as_ref().map(|r| r.trace.counts())
    }
    pub(super) fn should_reopen(&self) -> bool {
        self.first.search.is_some() && self.reopened.is_none()
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
            "news reopen is outside its original completed first flow",
        )?;
        self.guard_immutable(first, None)?;
        let mut trace = Trace::new(true);
        let frame = trace.frame(s, i, end)?;
        let last = self
            .first
            .search
            .as_ref()
            .ok_or("news first search absent")?
            .returned;
        let prior = stories(&self.first.trace, last, None)?;
        let after = stories(&trace, frame, None)?;
        let feed_titles_preserved = prior.len() >= 2
            && after.len() >= 2
            && prior.iter().all(|a| after.iter().any(|b| same_story(a, b)));
        self.reopened = Some(Reopen {
            trace,
            frame,
            feed_titles_preserved,
        });
        before(end)
    }
    fn guard_first(&self, t: &NativeUiTranscript) -> Result<(), String> {
        let p = &self.first;
        p.trace.guard(t)?;
        if let Some(a) = &p.article {
            need(
                stories(&p.trace, a.feed, None)?.len() >= 2
                    && stories(&p.trace, a.feed, None)?
                        .iter()
                        .any(|s| s == &a.selected)
                    && p.trace.steps[a.clicked].op == Operation::Click
                    && visible_identity(&p.trace, a.opened, &a.selected)?,
                "news retained selected feed/article identity differs",
            )?;
            if let Some(facts) = &a.facts {
                need(
                    article(&p.trace, a.opened, &a.selected)?.as_ref() == Some(facts),
                    "news retained article body/image facts differ",
                )?;
            }
            scrolling_proved(&p.trace, a)?;
        }
        if let Some(search) = &p.search {
            need(
                p.article.as_ref().and_then(|a| a.returned).is_some()
                    && p.trace.steps[search.entry].op == Operation::Click
                    && search.entry < search.input,
                "news search lacks actual owned entry",
            )?;
            let first_input = p.trace.steps[search.typed[0]]
                .target
                .as_ref()
                .ok_or("news first editor origin absent")?;
            need(
                first_input.0 == search.input
                    && first_input.1 == Role::Input
                    && actual_input(&first_input.2) == Some(""),
                "news search overwrote an existing input",
            )?;
            for n in 0..2 {
                need(
                    p.trace.steps[search.typed[n]].op == Operation::SetText
                        && p.trace.steps[search.typed[n]].written.as_deref() == Some(QUERIES[n])
                        && query_visible(p.trace.body(search.readback[n])?, QUERIES[n])?
                        && p.trace.steps[search.submitted[n]].op == Operation::Click
                        && search.typed[n] < search.readback[n]
                        && search.readback[n] < search.submitted[n]
                        && search.submitted[n] < p.trace.frames[search.results[n]].before
                        && stories(&p.trace, search.results[n], Some(QUERIES[n]))?.len() >= 2,
                    "news Unicode query/edit/result history lost its actual sequence",
                )?;
            }
            let second_input = p.trace.steps[search.typed[1]]
                .target
                .as_ref()
                .ok_or("news edited input absent")?;
            let cleared_input = p.trace.steps[search.cleared]
                .target
                .as_ref()
                .ok_or("news restored input absent")?;
            need(
                actual_input(&second_input.2) == Some(QUERIES[0])
                    && actual_input(&cleared_input.2) == Some(QUERIES[1])
                    && search.typed[0] < search.typed[1]
                    && search.typed[1] < search.cleared
                    && p.trace.steps[search.cleared].written.as_deref() == Some("")
                    && query_visible(p.trace.body(search.clear_readback)?, "")?
                    && search.cleared < search.clear_readback
                    && search.clear_readback < search.back
                    && p.trace.steps[search.back].op == Operation::Click
                    && stories(&p.trace, search.returned, None)?.len() >= 2,
                "news owned query restoration/return differs",
            )?;
        }
        Ok(())
    }
    pub(super) fn guard_immutable(
        &self,
        first: &NativeUiTranscript,
        reopened: Option<&NativeUiTranscript>,
    ) -> Result<(), String> {
        self.guard_first(first)?;
        match (&self.reopened, reopened) {
            (None, None) => Ok(()),
            (Some(r), Some(next)) => {
                r.trace.guard(next)?;
                need(
                    first.task() != next.task()
                        && first.journal() != next.journal()
                        && first.engine().application() == next.engine().application()
                        && first.engine().facts().main == next.engine().facts().main,
                    "news reopening requires distinct actual finished tasks under the same Main/application",
                )?;
                let source = self
                    .first
                    .search
                    .as_ref()
                    .ok_or("news reopened without completed first search")?;
                let before = stories(&self.first.trace, source.returned, None)?;
                let after = stories(&r.trace, r.frame, None)?;
                need(
                    r.feed_titles_preserved
                        == (before.len() >= 2
                            && after.len() >= 2
                            && before
                                .iter()
                                .all(|a| after.iter().any(|b| same_story(a, b)))),
                    "news real reopen feed comparison changed",
                )
            }
            _ => Err(
                "news saved second observations cannot replace an actual finished second history"
                    .into(),
            ),
        }
    }
    pub(super) fn completed_gates(&self) -> Vec<&'static str> {
        let mut out = Vec::new();
        if let Some(flow) = &self.first.article {
            out.push("news.feed");
            if scrolling_proved(&self.first.trace, flow) == Ok(true) {
                out.push("news.article");
            }
        }
        if self.first.search.is_some() {
            out.push("news.search");
        }
        // Navigation additionally requires preservation of preexisting private
        // history/bookmarks/preferences (or genuine positive fresh absence).
        // This actual UI flow does not manufacture either authority.
        out
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        let phase = |trace: &Trace| -> Result<Value, String> {
            Ok(
                json!({"actual_ui_requests":trace.requests(),"actual_input_actions":trace.actions(),
            "actual_commands":trace.counts().0,"retained_reply_bytes":trace.retained_bytes,
            "actual_scoped_pixels":trace.frames.iter().map(|f|f.pixels.comparison()).collect::<Result<Vec<_>,_>>()?,
            "decoded_rgb_retained":false}),
            )
        };
        Ok(
            json!({"schema":"droidloom.news-actual-guest-execution.v1","package":PACKAGE,"original_apk_sha256":ORIGINAL_APK_SHA256,
            "static_resources_sha256":"53581640ea957cee01601d64dd9d848ba493618af8bf5d6d6d3467e74f524fa3",
            "fixed_unicode_queries":QUERIES,"first":phase(&self.first.trace)?,"stop":self.first.stop,
            "reopened":self.reopened.as_ref().map(|r|phase(&r.trace)).transpose()?,
            "reopened_visible_feed_preserved":self.reopened.as_ref().is_some_and(|r|r.feed_titles_preserved),
            "selected_article":self.first.article.as_ref().map(|a|json!({"title_sha256":digest(a.selected.title.as_bytes()),
                "publisher_sha256":digest(a.selected.publisher.as_bytes()),"real_two_direction_scroll_and_return":scrolling_proved(&self.first.trace,a).unwrap_or(false)})),
            "completed_business_gates":self.completed_gates(),
            "navigation_pending":"actual_complete_preexisting_history_bookmarks_preferences_or_positive_fresh_absence",
            "media_pending":"same_news_item_advancing_frames_actual_output_audio_pause_resume_seek_stop",
            "recovery_pending":"source_owned_scoped_failure_prerequisite_restore_and_actual_successful_retry",
            "login_post_comment_order_payment_or_account_change_attempted":false,
            "host_network_or_permission_state_changed":false,
            "runtime_qualified":false,"production_ready":false,"comparison_only":true}),
        )
    }
}
pub(super) fn run(
    s: &mut NativeUiSession<'_, '_>,
    i: &mut NativeApplicationInspector,
    package: &str,
    end: Instant,
) -> Result<NewsExecution, String> {
    need(supports(package), "news executor package differs")?;
    before(end)?;
    let mut first = Phase::new(false);
    article_flow(&mut first, s, i, end)?;
    search_flow(&mut first, s, i, end)?;
    before(end)?;
    Ok(NewsExecution {
        first,
        reopened: None,
        original_end: end,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_supervisor::control::application_probe::{InstalledApk, RuntimeEpoch};

    #[test]
    fn news_source_contract_rejects_name_only_version_only_and_changed_split_sets() {
        let original = ApplicationInspection {
            package: PACKAGE.into(),
            user: 0,
            uid: 10213,
            version_code: 19300,
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
        // Comparison validation alone produces no NewsExecution, UI session,
        // retained transcript, application signature or accepted gate.
    }
    #[test]
    fn news_real_crop_rejects_blank_pale_wrong_dimensions_and_outside_window() {
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
    fn news_editor_does_not_promote_hint_password_or_existing_text_to_empty_owned_input() {
        let mut node = json!({"package":PACKAGE,"visible":true,"enabled":true,"password":false,
            "source":"native_accessibility","bounds_array":[0,0,200,50],"editable":true,
            "showing-hint":true,"text":"搜索","value":null});
        assert_eq!(actual_input(&node), Some(""));
        node["hint"] = Value::String("搜索新闻".into());
        assert!(search_editor_context(&node, &[]));
        node["hint"] = Value::String("手机号码".into());
        assert!(!search_editor_context(&node, &[]));
        node["hint"] = Value::String("Search account".into());
        assert!(!search_editor_context(&node, &[]));
        node["value"] = Value::String("existing user query".into());
        assert_eq!(actual_input(&node), Some("existing user query"));
        node["showing-hint"] = Value::Bool(false);
        node["value"] = Value::String(QUERIES[0].into());
        assert_eq!(actual_input(&node), Some(QUERIES[0]));
        node["password"] = Value::Bool(true);
        assert_eq!(actual_input(&node), None);
        node["password"] = Value::Bool(false);
        node["package"] = Value::String("foreign".into());
        assert_eq!(actual_input(&node), None);
    }
    #[test]
    fn news_source_selection_does_not_infer_article_identity_from_truncated_titles_or_ad_labels() {
        assert!(title("中国航天取得新的科学研究成果"));
        assert!(publisher("新华社"));
        for bad in ["广告", "2小时前", "12评论", "立即购买", "关注", "刚刚"] {
            assert!(!publisher(bad), "{bad}");
        }
        assert!(!same_title(
            "中国航天取得新的科学…",
            "中国航天取得新的科学研究成果"
        ));
        assert!(!title("中国航天取得新的科学…"));
        assert!(!paragraph(
            "正在加载中，请稍候，请稍候，请稍候，请稍候，请稍候，请稍候"
        ));
        assert!(duration_label("01:23"));
        assert!(duration_label("123:59"));
        assert!(!duration_label("news:title"));
        assert!(!duration_label("2026:11:28"));
    }
    #[test]
    fn news_source_bounds_leave_existing_family_contracts_and_original_deadline_intact() {
        assert_eq!(additional_window_seconds(), 6930);
        assert_eq!(second_business_seconds(), 770);
        assert_eq!(first_max_extra_ui_commands(), 200);
        assert_eq!(reopen_max_ui_commands(), 25);
        assert!(first_max_extra_ui_commands() + 39 < 512);
        assert!(RETAINED_REPLY_BYTES * 2 < 2_147_483_648);
        assert!(before(Instant::now()).is_err());
        assert!(!supports("com.ss.android.article.lite"));
    }
}
