//! Public travel searches from actual owned native UI histories.
//! Whole PM sources, exact form readbacks, decoded result/detail pixels and
//! normal separate task histories are retained. No comparison is a constructor.
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeUiReply, NativeUiSelector, NativeUiSession,
    NativeUiTranscript, RetainedScopedWindowPixels,
};
use serde::Serialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::time::{Instant, SystemTime, UNIX_EPOCH};
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
enum Kind {
    Hotel,
    Flight,
    Rental,
    Train,
}
#[path = "family_travel_sources.rs"]
mod sources;
use sources::Source;
const FIRST_REQUESTS: usize = 96;
const SECOND_REQUESTS: usize = 24;
const FIRST_CAPTURES: usize = 12;
const SECOND_CAPTURES: usize = 4;
const REOPEN_CALENDAR_LIMIT: usize = 2;
const RETAINED_REPLY_BYTES: usize = 64 * 1024 * 1024;
pub(super) fn supports(package: &str) -> bool {
    sources::source(package).is_ok()
}
pub(super) fn profile(package: &str) -> Result<&'static str, String> {
    Ok(sources::source(package)?.profile)
}
pub(super) fn require_application(a: &ApplicationInspection) -> Result<(), String> {
    sources::require_application(a)
}
fn route_count(package: &str) -> usize {
    sources::source(package)
        .map(|s| s.routes.len())
        .unwrap_or(0)
}
fn request_limit(c: &Source, second: bool) -> usize {
    if second {
        SECOND_REQUESTS
    } else {
        FIRST_REQUESTS * c.routes.len()
    }
}
fn capture_limit(c: &Source, second: bool) -> usize {
    if second {
        SECOND_CAPTURES
    } else {
        FIRST_CAPTURES * c.routes.len()
    }
}
fn action_limit(c: &Source, second: bool) -> u32 {
    if second {
        12
    } else {
        48 * c.routes.len() as u32
    }
}
pub(super) fn additional_window_seconds(package: &str) -> u64 {
    (FIRST_REQUESTS * route_count(package) + SECOND_REQUESTS) as u64 * 100
        + (FIRST_CAPTURES * route_count(package) + SECOND_CAPTURES) as u64 * 170
}
pub(super) fn second_business_seconds() -> u64 {
    SECOND_REQUESTS as u64 * 100 + SECOND_CAPTURES as u64 * 170
}
pub(super) fn first_max_extra_ui_commands(package: &str) -> u32 {
    ((FIRST_REQUESTS * 3 + FIRST_CAPTURES * 7) * route_count(package)) as u32
}
pub(super) fn first_max_extra_actions(package: &str) -> u32 {
    48 * route_count(package) as u32
}
pub(super) fn reopen_max_ui_commands() -> u32 {
    (SECOND_REQUESTS * 3 + SECOND_CAPTURES * 7) as u32
}
pub(super) fn reopen_max_actions() -> u32 {
    12
}
pub(super) fn capture_members_bound(package: &str) -> usize {
    2 * (FIRST_CAPTURES * route_count(package) + SECOND_CAPTURES)
}
fn need(ok: bool, why: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn before(end: Instant) -> Result<(), String> {
    need(Instant::now() < end, "travel original window expired")
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
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct Rect([i64; 4]);
impl Rect {
    fn parse(v: &Value) -> Result<Self, String> {
        let a = v
            .as_array()
            .filter(|v| v.len() == 4)
            .ok_or("travel rectangle absent")?;
        let v = a
            .iter()
            .map(Value::as_i64)
            .collect::<Option<Vec<_>>>()
            .ok_or("travel rectangle noninteger")?;
        need(
            v.iter().all(|v| (0..=8192).contains(v)) && v[2] > v[0] && v[3] > v[1],
            "travel rectangle bound",
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
fn nodes<'a>(body: &'a Value, c: &Source) -> Result<&'a [Value], String> {
    let w = &body["window_context"];
    need(
        body["ok"] == true
            && w["root"]["package"] == c.package
            && w["selected_window"]["root"]["package"] == c.package
            && w["selected_window"]["focused"] == true
            && w["selected_window"]["display_id"] == 0
            && w["snapshot_complete"] == true
            && w["truncated"] == false,
        "travel requires the actual complete owned package tree",
    )?;
    body["nodes"]
        .as_array()
        .filter(|v| !v.is_empty() && v.len() <= 2000)
        .map(Vec::as_slice)
        .ok_or_else(|| "travel actual nodes absent".into())
}
fn usable(n: &Value, c: &Source) -> bool {
    n["package"] == c.package
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
        "checked",
        "selected",
        "value",
        "showing-hint",
    ]
    .iter()
    .all(|k| a[*k] == b[*k])
}
fn image(n: &Value, c: &Source) -> bool {
    usable(n, c)
        && text(n, "text").is_empty()
        && text(n, "class").contains("Image")
        && Rect::parse(&n["bounds_array"]).is_ok_and(|r| r.0[2] - r.0[0] >= 64 && r.height() >= 48)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
enum Role {
    Result,
    OpenQuery,
    Input,
    Submit,
    EditQuery,
    Back,
    Scroll,
    Date,
    NextMonth,
    Day,
    Choice,
    Restore,
}
fn action_allowed(n: &Value, role: Role) -> bool {
    if n["password"] != false {
        return false;
    }
    let value = norm(&format!("{} {}", text(n, "text"), text(n, "content-desc")));
    ![
        "pay now",
        "purchase",
        "confirm booking",
        "confirm reservation",
        "reserve now",
        "book now",
        "send message",
        "send code",
        "sign in",
        "log in",
        "sign up",
        "cancel booking",
        "立即支付",
        "立即预订",
        "确认预订",
        "确认订单",
        "发送",
        "验证码",
        "登录",
        "登陆",
        "注册",
        "取消订单",
        "立即购买",
    ]
    .iter()
    .any(|s| value.contains(s))
        && (role != Role::Input
            || ![
                "password",
                "email",
                "phone",
                "account",
                "passport",
                "traveller name",
                "密码",
                "邮箱",
                "手机号",
                "证件",
                "姓名",
            ]
            .iter()
            .any(|s| norm(&format!("{} {}", value, text(n, "hint"))).contains(s)))
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
        "travel pixel crop does not match actual window",
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
    let lo = *out.iter().min().ok_or("travel pixel patch empty")?;
    let hi = *out.iter().max().unwrap();
    need(
        hi - lo >= 48
            && out
                .chunks_exact(3)
                .filter(|p| p.iter().any(|v| *v < 220))
                .count()
                >= 8
            && out.chunks_exact(3).any(|p| p.iter().any(|v| *v < 160)),
        "travel crop is blank, pale, or lacks contrast",
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
    source: &'static Source,
    steps: Vec<Step>,
    frames: Vec<Frame>,
    second: bool,
    retained_bytes: usize,
}
impl Trace {
    fn new(source: &'static Source, second: bool) -> Self {
        Self {
            source,
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
            self.requests() + requests <= request_limit(self.source, self.second) as u32
                && self.actions() + u32::from(action) <= action_limit(self.source, self.second),
            "travel fixed request/action budget exhausted",
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
            .ok_or("travel retained reply byte overflow")?;
        need(
            self.retained_bytes <= RETAINED_REPLY_BYTES,
            "travel retained reply memory bound exceeded",
        )?;
        let idx = self.steps.len();
        self.steps.push(step);
        Ok(idx)
    }
    fn body(&self, n: usize) -> Result<&Value, String> {
        self.steps
            .get(n)
            .map(|s| s.reply.body())
            .ok_or_else(|| "travel reply index differs".into())
    }
    fn dump(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &NativeApplicationInspector,
        end: Instant,
    ) -> Result<usize, String> {
        self.reserve(1, false, end)?;
        let reply = s.dump(i)?;
        nodes(reply.body(), self.source)?;
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
        need(
            action_allowed(&target.node, target.role),
            "travel source refuses a purchase, account, communication or reservation mutation",
        )?;
        let reply = match op {
            Operation::Click => s.click(i, target.selector)?,
            Operation::SetText => s.set_text(
                i,
                target.selector,
                written.ok_or("travel typed text absent")?,
            )?,
            Operation::Forward => s.scroll_forward(i, target.selector)?,
            Operation::Backward => s.scroll_backward(i, target.selector)?,
            Operation::Dump => return Err("travel mutation cannot select Dump".into()),
        };
        if op != Operation::SetText {
            need(
                same_node(&reply.body()["target"], &target.node),
                "travel acknowledged target differs from its actual observed node",
            )?;
            if op == Operation::Click {
                let actual = &reply.body()["actual_target"];
                let a = Rect::parse(&actual["bounds_array"])?;
                let n = Rect::parse(&target.node["bounds_array"])?;
                need(
                    nodes(self.body(target.origin)?, self.source)?
                        .iter()
                        .any(|v| same_node(v, actual))
                        && a.contains(n)
                        && target.container.map_or(a == n, |c| c.contains(a)),
                    "travel click climbed outside the actual source-chosen control/card",
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
            self.frames.len() < capture_limit(self.source, self.second),
            "travel fixed scoped image budget exhausted",
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
            "travel window changed across the real pixel observation",
        )?;
        let cmp = pixels.comparison()?;
        let p = &cmp["window"]["bounds"];
        need(
            window
                == Rect([
                    p["left"].as_i64().ok_or("travel pixel left")?,
                    p["top"].as_i64().ok_or("travel pixel top")?,
                    p["right"].as_i64().ok_or("travel pixel right")?,
                    p["bottom"].as_i64().ok_or("travel pixel bottom")?,
                ]),
            "travel scoped pixel window differs from actual semantic tree",
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
        for n in nodes(before, self.source)?
            .iter()
            .filter(|n| usable(n, self.source))
        {
            let rect = Rect::parse(&n["bounds_array"])?;
            if window.contains(rect)
                && nodes(after, self.source)?.iter().any(|v| same_node(n, v))
                && (image(n, self.source)
                    || !text(n, "text").is_empty()
                    || !text(n, "content-desc").is_empty()
                    || n["editable"] == true
                    || n["scrollable"] == true)
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
            "travel actual rendered patch count exceeds source bound",
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
                    .and_then(|body| nodes(body, self.source))
                    .is_ok_and(|ns| ns.iter().any(|v| same_node(v, n)))
                && self
                    .body(f.after)
                    .and_then(|body| nodes(body, self.source))
                    .is_ok_and(|ns| ns.iter().any(|v| same_node(v, n)))
        })
    }
    fn guard(&self, transcript: &NativeUiTranscript) -> Result<(), String> {
        require_application(transcript.engine().application())?;
        need(
            transcript.engine().application().package == self.source.package,
            "travel history belongs to another actual source",
        )?;
        need(
            self.requests() <= request_limit(self.source, self.second) as u32
                && self.actions() <= action_limit(self.source, self.second)
                && self.frames.len() <= capture_limit(self.source, self.second)
                && self.retained_bytes <= RETAINED_REPLY_BYTES,
            "travel retained trace limits differ",
        )?;
        for (idx, step) in self.steps.iter().enumerate() {
            need(
                step.reply.body()["ok"] == true,
                "travel retained reply failed",
            )?;
            if let Some((origin, _, node, _)) = &step.target {
                need(
                    *origin < idx
                        && self.steps[*origin].op == Operation::Dump
                        && nodes(self.body(*origin)?, self.source)?
                            .iter()
                            .any(|v| v == node)
                        && usable(node, self.source)
                        && step.reply.body()["performed"] == step.op.name(),
                    "travel retained action lost its actual source choice",
                )?;
                if step.op != Operation::SetText {
                    need(
                        same_node(node, &step.reply.body()["target"]),
                        "travel retained target changed",
                    )?;
                } else {
                    need(
                        step.written.as_ref().is_some_and(|v| {
                            step.reply.body()["characters"].as_u64()
                                == Some(v.chars().count() as u64)
                        }) && step.reply.body()["readback_verified"] == true,
                        "travel text readback changed",
                    )?;
                }
            } else {
                need(
                    step.op == Operation::Dump,
                    "travel action lacks observed target",
                )?;
            }
        }
        for f in &self.frames {
            f.pixels.require_transcript(transcript)?;
            nodes(self.body(f.before)?, self.source)?;
            nodes(self.body(f.after)?, self.source)?;
            need(
                f.patches.contains_key(&f.window)
                    && f.patches
                        .values()
                        .all(|p| p.rgb.len() == 768 && digest(&p.rgb) == p.sha256),
                "travel actual decoded patch history changed",
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
    let ns = nodes(trace.body(origin)?, trace.source)?;
    need(
        usable(selected, trace.source) && ns.iter().any(|n| n == selected),
        "travel choice is not an actual usable node",
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
            .filter(|n| usable(n, trace.source) && n["editable"] == true)
            .count()
            == 1
    {
        Some(NativeUiSelector::editable().enabled())
    } else if role == Role::Scroll
        && ns
            .iter()
            .filter(|n| usable(n, trace.source) && n["scrollable"] == true)
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

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
struct Date {
    year: u32,
    month: u32,
    day: u32,
}
impl Date {
    fn from_days(mut days: u64) -> Result<Self, String> {
        need(
            days <= 47_481,
            "travel clock outside the bounded 1970-2099 calendar",
        )?;
        let mut year = 1970;
        loop {
            let length = if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) {
                366
            } else {
                365
            };
            if days < length {
                break;
            }
            days -= length;
            year += 1;
        }
        let months = [
            31,
            if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) {
                29
            } else {
                28
            },
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ];
        let mut month = 0;
        while days >= months[month] {
            days -= months[month];
            month += 1;
        }
        Ok(Self {
            year: year as u32,
            month: month as u32 + 1,
            day: days as u32 + 1,
        })
    }
    fn iso(self) -> String {
        format!("{:04}-{:02}-{:02}", self.year, self.month, self.day)
    }
    fn month_names(self) -> Vec<String> {
        let name = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ][(self.month - 1) as usize];
        vec![
            format!("{name} {}", self.year),
            format!("{} {name}", self.year),
            format!("{}年{}月", self.year, self.month),
            format!("{:04}-{:02}", self.year, self.month),
        ]
    }
    fn variants(self, short: bool) -> Vec<String> {
        let month = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ][(self.month - 1) as usize];
        let mut v = vec![
            self.iso(),
            format!("{:04}/{:02}/{:02}", self.year, self.month, self.day),
            format!("{:02}/{:02}/{:04}", self.month, self.day, self.year),
            format!("{month} {}, {}", self.day, self.year),
            format!("{} {month} {}", self.day, self.year),
            format!("{}年{}月{}日", self.year, self.month, self.day),
        ];
        if short {
            v.extend([
                format!("{month} {}", self.day),
                format!("{} {month}", self.day),
                format!("{}月{}日", self.month, self.day),
                format!("{:02}/{:02}", self.month, self.day),
            ]);
        }
        v
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
enum Slot {
    Origin,
    Destination,
    Start,
    End,
    People,
    Rooms,
    PickupTime,
    DropoffTime,
    OneWay,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct Field {
    slot: Slot,
    value: String,
    aliases: Vec<String>,
    date: Option<Date>,
}
impl Field {
    fn new(slot: Slot, value: &str, aliases: &[&str]) -> Self {
        Self {
            slot,
            value: value.into(),
            aliases: aliases.iter().map(|v| (*v).into()).collect(),
            date: None,
        }
    }
    fn date(slot: Slot, date: Date) -> Self {
        Self {
            slot,
            value: date.iso(),
            aliases: date.variants(false),
            date: Some(date),
        }
    }
    fn matches(&self, value: &str, calendar_proved: bool) -> bool {
        let options = if let Some(d) = self.date {
            // A short label is not allowed to hide an explicit different year.
            // This is intentionally checked even when a calendar was observed:
            // the actual result/detail can still contradict the selected date.
            if value
                .split(|c: char| !c.is_ascii_digit())
                .filter(|v| v.len() == 4)
                .filter_map(|v| v.parse::<u32>().ok())
                .filter(|year| *year != d.year)
                .any(|year| {
                    Date { year, ..d }
                        .variants(false)
                        .iter()
                        .any(|v| term(value, v))
                })
            {
                return false;
            }
            d.variants(calendar_proved)
        } else {
            self.aliases.clone()
        };
        options.iter().any(|v| term(value, v))
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct Query {
    kind: Kind,
    fields: Vec<Field>,
    day: u64,
    edited: bool,
}
fn query(source: &Source, kind: Kind, day: u64, edited: bool) -> Result<Query, String> {
    let offset = day
        .checked_add(u64::from(edited))
        .ok_or("travel date arithmetic overflow")?;
    let start = Date::from_days(
        offset
            .checked_add(7)
            .ok_or("travel date arithmetic overflow")?,
    )?;
    let end = Date::from_days(
        offset
            .checked_add(9)
            .ok_or("travel date arithmetic overflow")?,
    )?;
    let mut fields = match kind {
        Kind::Hotel => vec![Field::new(
            Slot::Destination,
            "London",
            &["London", "伦敦", "ロンドン"],
        )],
        Kind::Train => vec![
            Field::new(Slot::Origin, "北京南", &["北京南", "Beijing South"]),
            Field::new(
                Slot::Destination,
                "上海虹桥",
                &["上海虹桥", "Shanghai Hongqiao"],
            ),
        ],
        Kind::Rental => {
            let place = if source.package == "com.szzc" {
                (
                    "北京首都国际机场",
                    vec!["北京首都国际机场", "北京首都机场", "PEK"],
                )
            } else {
                (
                    "London Heathrow Airport",
                    vec![
                        "London Heathrow Airport",
                        "London Heathrow",
                        "Heathrow",
                        "LHR",
                    ],
                )
            };
            vec![
                Field::new(Slot::Origin, place.0, &place.1),
                Field::new(Slot::Destination, place.0, &place.1),
            ]
        }
        Kind::Flight => {
            let (origin, destination, origins, destinations) = match source.package {
                "com.united.mobile.android" => ("JFK", "SFO", vec!["JFK"], vec!["SFO"]),
                "jp.co.ana.android.tabidachi" => {
                    ("HND", "ITM", vec!["HND", "羽田"], vec!["ITM", "伊丹"])
                }
                _ => (
                    "PEK",
                    "SHA",
                    vec!["PEK", "北京首都"],
                    vec!["SHA", "上海虹桥"],
                ),
            };
            vec![
                Field::new(
                    Slot::OneWay,
                    "One way",
                    &["one way", "one-way", "单程", "片道"],
                ),
                Field::new(Slot::Origin, origin, &origins),
                Field::new(Slot::Destination, destination, &destinations),
            ]
        }
    };
    fields.push(Field::date(Slot::Start, start));
    if matches!(kind, Kind::Hotel | Kind::Rental) {
        fields.push(Field::date(Slot::End, end));
    }
    if kind != Kind::Rental {
        fields.push(Field::new(
            Slot::People,
            "1",
            &[
                "1 adult",
                "1 adults",
                "1 passenger",
                "1 traveller",
                "1 traveler",
                "1位成人",
                "1成人",
                "成人1",
                "大人1名",
            ],
        ));
    }
    if kind == Kind::Hotel {
        fields.push(Field::new(
            Slot::Rooms,
            "1",
            &["1 room", "1 rooms", "1间客房", "1间", "1室"],
        ));
    }
    if kind == Kind::Rental {
        fields.extend([
            Field::new(
                Slot::PickupTime,
                "10:00",
                &["10:00", "10:00 AM", "上午10:00"],
            ),
            Field::new(
                Slot::DropoffTime,
                "10:00",
                &["10:00", "10:00 AM", "上午10:00"],
            ),
        ]);
    }
    Ok(Query {
        kind,
        fields,
        day,
        edited,
    })
}
fn term(hay: &str, needle: &str) -> bool {
    let h = norm(hay);
    let n = norm(needle);
    if n.is_empty() {
        return false;
    }
    h.match_indices(&n).any(|(at, _)| {
        let left = h[..at].chars().next_back();
        let right = h[at + n.len()..].chars().next();
        let first = n.chars().next().unwrap();
        let last = n.chars().next_back().unwrap();
        (!first.is_ascii_alphanumeric() || left.is_none_or(|v| !v.is_ascii_alphanumeric()))
            && (!last.is_ascii_alphanumeric() || right.is_none_or(|v| !v.is_ascii_alphanumeric()))
    })
}
fn labels(slot: Slot) -> &'static [&'static str] {
    match slot {
        Slot::Origin => &[
            "origin",
            "from",
            "departure city",
            "departing from",
            "出发地",
            "出发站",
            "出发",
            "pickup location",
            "pick-up location",
            "取车地点",
            "出発地",
        ],
        Slot::Destination => &[
            "destination",
            "to",
            "where to",
            "city",
            "destination city",
            "目的地",
            "到达站",
            "到达",
            "dropoff location",
            "drop-off location",
            "还车地点",
            "目的地・ホテル名",
            "到着地",
        ],
        Slot::Start => &[
            "check-in",
            "check in",
            "arrival date",
            "departure date",
            "depart date",
            "pickup date",
            "pick-up date",
            "入住",
            "入住日期",
            "出发日期",
            "去程",
            "取车日期",
            "出発日",
        ],
        Slot::End => &[
            "check-out",
            "check out",
            "checkout date",
            "return date",
            "dropoff date",
            "drop-off date",
            "退房",
            "离店",
            "还车日期",
            "返却日",
        ],
        Slot::People => &[
            "guests",
            "adults",
            "adult",
            "passengers",
            "travelers",
            "travellers",
            "rooms and guests",
            "入住人数",
            "成人",
            "乘客",
            "人数",
            "大人",
        ],
        Slot::Rooms => &[
            "rooms",
            "room",
            "rooms and guests",
            "客房",
            "房间",
            "间数",
            "部屋",
        ],
        Slot::PickupTime => &["pickup time", "pick-up time", "取车时间", "出発時間"],
        Slot::DropoffTime => &[
            "dropoff time",
            "drop-off time",
            "return time",
            "还车时间",
            "返却時間",
        ],
        Slot::OneWay => &["one way", "one-way", "单程", "片道"],
    }
}
fn actual_input(n: &Value) -> Option<&str> {
    if n["editable"] != true || n["password"] != false {
        return None;
    }
    if n["showing-hint"] == true && n["value"].as_str().is_none_or(str::is_empty) {
        Some("")
    } else {
        n["value"].as_str().or_else(|| n["text"].as_str())
    }
}
fn description(n: &Value) -> String {
    format!(
        "{} {} {} {}",
        text(n, "text"),
        text(n, "content-desc"),
        text(n, "hint"),
        text(n, "resource-id").replace('_', " ")
    )
}
fn field_value(n: &Value, ns: &[Value], c: &Source) -> String {
    if let Some(value) = actual_input(n) {
        return value.into();
    }
    let r = Rect::parse(&n["bounds_array"]).ok();
    ns.iter()
        .filter(|v| {
            usable(v, c)
                && v["editable"] != true
                && r.is_some_and(|r| Rect::parse(&v["bounds_array"]).is_ok_and(|s| r.contains(s)))
        })
        .flat_map(|v| [text(v, "text"), text(v, "content-desc")])
        .filter(|v| !v.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}
fn field_label(n: &Value, ns: &[Value], c: &Source, slot: Slot) -> bool {
    if labels(slot).iter().any(|l| term(&description(n), l)) {
        return true;
    }
    let Ok(rect) = Rect::parse(&n["bounds_array"]) else {
        return false;
    };
    ns.iter()
        .filter(|label| usable(label, c) && label["editable"] != true && label["clickable"] != true)
        .any(|label| {
            Rect::parse(&label["bounds_array"]).is_ok_and(|r| {
                let same_row = r.0[1] < rect.0[3]
                    && rect.0[1] < r.0[3]
                    && r.0[2] <= rect.0[0]
                    && rect.0[0] - r.0[2] <= 320;
                let directly_above = r.0[3] <= rect.0[1]
                    && rect.0[1] - r.0[3] <= 40
                    && r.0[0] >= rect.0[0]
                    && r.0[2] <= rect.0[2];
                (same_row || directly_above)
                    && labels(slot).iter().any(|l| term(text(label, "text"), l))
            })
        })
}
fn field_node_matches(
    field: &Field,
    node: &Value,
    ns: &[Value],
    source: &Source,
    calendar: bool,
) -> bool {
    if matches!(field.slot, Slot::People | Slot::Rooms)
        && actual_input(node).is_some_and(|v| v.trim() == "1")
        && field_label(node, ns, source, field.slot)
    {
        return true;
    }
    field.matches(&field_value(node, ns, source), calendar)
}

fn field_node(trace: &Trace, origin: usize, field: &Field) -> Result<Option<Value>, String> {
    let ns = nodes(trace.body(origin)?, trace.source)?;
    let candidates: Vec<_> = ns
        .iter()
        .filter(|n| {
            usable(n, trace.source)
                && (n["editable"] == true || n["clickable"] == true)
                && action_allowed(n, Role::Input)
                && field_label(n, ns, trace.source, field.slot)
        })
        .collect();
    Ok((candidates.len() == 1).then(|| candidates[0].clone()))
}
fn control(
    trace: &Trace,
    origin: usize,
    role: Role,
    names: &[&str],
) -> Result<Option<Target>, String> {
    let ns = nodes(trace.body(origin)?, trace.source)?;
    let matching: Vec<_> = ns
        .iter()
        .filter(|n| {
            usable(n, trace.source)
                && n["editable"] != true
                && action_allowed(n, role)
                && (names.iter().any(|v| norm(text(n, "text")) == norm(v))
                    || names
                        .iter()
                        .any(|v| norm(text(n, "content-desc")) == norm(v)))
        })
        .collect();
    if matching.len() != 1 {
        return Ok(None);
    }
    choose(trace, origin, role, matching[0], None)
}
fn back(
    trace: &mut Trace,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    origin: usize,
    end: Instant,
) -> Result<Option<usize>, String> {
    let Some(t) = control(
        trace,
        origin,
        Role::Back,
        &["Back", "Navigate up", "返回", "上一页", "戻る"],
    )?
    else {
        return Ok(None);
    };
    Ok(Some(trace.perform(s, i, t, Operation::Click, None, end)?))
}
fn entry_names(kind: Kind) -> &'static [&'static str] {
    match kind {
        Kind::Hotel => &[
            "Find a hotel",
            "Find hotels",
            "Search hotels",
            "Hotels",
            "Hotel search",
            "酒店",
            "查找酒店",
            "查找酒店和度假村",
            "ホテル",
        ],
        Kind::Flight => &[
            "Search flights",
            "Find flights",
            "Flights",
            "Flight search",
            "机票",
            "航班查询",
            "国内机票",
            "空席照会",
        ],
        Kind::Rental => &[
            "Find a car",
            "Search cars",
            "Rent a car",
            "Car rental",
            "租车",
            "车辆查询",
            "用车查询",
        ],
        Kind::Train => &[
            "Trains",
            "Train tickets",
            "Search trains",
            "火车票",
            "车票查询",
            "查询车票",
        ],
    }
}
fn submit_names(kind: Kind) -> &'static [&'static str] {
    match kind {
        Kind::Hotel => &[
            "Search",
            "Find hotels",
            "Search hotels",
            "Check availability",
            "查找酒店",
            "查询",
            "搜索",
            "查看房价",
            "空室検索",
        ],
        Kind::Flight => &[
            "Search",
            "Search flights",
            "Find flights",
            "查询",
            "搜索",
            "查找航班",
            "航班查询",
            "空席照会",
            "検索",
        ],
        Kind::Rental => &[
            "Search",
            "Search cars",
            "Find cars",
            "Search vehicles",
            "查询",
            "查找车辆",
            "搜索车辆",
            "検索",
        ],
        Kind::Train => &["Search", "Search trains", "查询车票", "查询", "搜索"],
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct FieldEvidence {
    field: Field,
    initial: Value,
    initial_value: String,
    origin: usize,
    actions: Vec<usize>,
    readback: usize,
    final_node: Value,
    calendar: Option<(usize, usize, Date)>,
}
impl FieldEvidence {
    fn guard(&self, trace: &Trace) -> Result<(), String> {
        let ns = nodes(trace.body(self.origin)?, trace.source)?;
        need(
            ns.iter().any(|v| v == &self.initial)
                && field_label(&self.initial, ns, trace.source, self.field.slot)
                && field_value(&self.initial, ns, trace.source) == self.initial_value,
            "travel initial field observation changed",
        )?;
        need(
            self.readback >= self.origin
                && self.actions.windows(2).all(|v| v[0] < v[1])
                && self.actions.iter().all(|n| {
                    *n > self.origin && *n < self.readback && trace.steps[*n].op != Operation::Dump
                }),
            "travel field action order changed",
        )?;
        if let Some((month, day, date)) = self.calendar {
            need(
                self.field.date == Some(date)
                    && month < day
                    && day < self.readback
                    && calendar_month(trace, month, date)?
                    && trace.steps[day]
                        .target
                        .as_ref()
                        .is_some_and(|(_, role, n, _)| {
                            *role == Role::Day && text(n, "text").trim() == date.day.to_string()
                        }),
                "travel selected calendar month/day proof changed",
            )?;
        }
        let after = nodes(trace.body(self.readback)?, trace.source)?;
        need(
            after.iter().any(|v| v == &self.final_node)
                && field_node_matches(
                    &self.field,
                    &self.final_node,
                    after,
                    trace.source,
                    self.calendar.is_some(),
                ),
            "travel exact field readback does not match its original query",
        )?;
        if self.field.slot == Slot::OneWay {
            need(
                self.final_node["checked"] == true || self.final_node["selected"] == true,
                "travel trip mode lacks actual selected state",
            )?;
        }
        Ok(())
    }
}
fn calendar_month(trace: &Trace, origin: usize, date: Date) -> Result<bool, String> {
    let expected = date.month_names();
    let ns = nodes(trace.body(origin)?, trace.source)?;
    Ok(ns
        .iter()
        .filter(|n| {
            usable(n, trace.source)
                && n["editable"] != true
                && expected.iter().any(|v| {
                    norm(text(n, "text")) == norm(v) || norm(text(n, "content-desc")) == norm(v)
                })
        })
        .count()
        == 1)
}
fn set_field(
    trace: &mut Trace,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    field: &Field,
    origin: usize,
    end: Instant,
) -> Result<Option<FieldEvidence>, String> {
    let Some(initial) = field_node(trace, origin, field)? else {
        return Ok(None);
    };
    let initial_value = field_value(
        &initial,
        nodes(trace.body(origin)?, trace.source)?,
        trace.source,
    );
    let mut current = origin;
    let mut actions = Vec::new();
    let mut calendar = None;
    let already = field_node_matches(
        field,
        &initial,
        nodes(trace.body(origin)?, trace.source)?,
        trace.source,
        false,
    ) && (field.slot != Slot::OneWay
        || initial["checked"] == true
        || initial["selected"] == true);
    if !already {
        if initial["editable"] == true {
            let Some(t) = choose(trace, current, Role::Input, &initial, None)? else {
                return Ok(None);
            };
            actions.push(trace.perform(s, i, t, Operation::SetText, Some(&field.value), end)?);
            current = trace.dump(s, i, end)?;
        } else if let Some(date) = field.date {
            let Some(t) = choose(trace, current, Role::Date, &initial, None)? else {
                return Ok(None);
            };
            actions.push(trace.perform(s, i, t, Operation::Click, None, end)?);
            current = trace.dump(s, i, end)?;
            for _ in 0..2 {
                if calendar_month(trace, current, date)? {
                    break;
                }
                let Some(t) = control(
                    trace,
                    current,
                    Role::NextMonth,
                    &["Next month", "Next Month", "下个月", "下一月", "翌月"],
                )?
                else {
                    return Ok(None);
                };
                actions.push(trace.perform(s, i, t, Operation::Click, None, end)?);
                current = trace.dump(s, i, end)?;
            }
            if !calendar_month(trace, current, date)? {
                return Ok(None);
            }
            let month = current;
            let day = date.day.to_string();
            let Some(t) = control(trace, current, Role::Day, &[&day])? else {
                return Ok(None);
            };
            let action = trace.perform(s, i, t, Operation::Click, None, end)?;
            actions.push(action);
            calendar = Some((month, action, date));
            current = trace.dump(s, i, end)?;
            if field_node(trace, current, field)?.is_none() {
                if let Some(t) = control(
                    trace,
                    current,
                    Role::Choice,
                    &["Done", "Apply", "OK", "完成", "确定", "完了"],
                )? {
                    actions.push(trace.perform(s, i, t, Operation::Click, None, end)?);
                    current = trace.dump(s, i, end)?;
                }
            }
        } else if field.slot == Slot::OneWay {
            let Some(t) = choose(trace, current, Role::Choice, &initial, None)? else {
                return Ok(None);
            };
            actions.push(trace.perform(s, i, t, Operation::Click, None, end)?);
            current = trace.dump(s, i, end)?;
        } else if matches!(field.slot, Slot::Origin | Slot::Destination) {
            let Some(t) = choose(trace, current, Role::OpenQuery, &initial, None)? else {
                return Ok(None);
            };
            actions.push(trace.perform(s, i, t, Operation::Click, None, end)?);
            current = trace.dump(s, i, end)?;
            let ns = nodes(trace.body(current)?, trace.source)?;
            let editors: Vec<_> = ns
                .iter()
                .filter(|n| {
                    usable(n, trace.source)
                        && n["editable"] == true
                        && action_allowed(n, Role::Input)
                        && [
                            "search",
                            "city",
                            "airport",
                            "station",
                            "location",
                            "搜索",
                            "城市",
                            "机场",
                            "车站",
                            "地点",
                            "キーワード",
                        ]
                        .iter()
                        .any(|v| term(&description(n), v))
                })
                .collect();
            if editors.len() != 1 {
                return Ok(None);
            }
            let Some(t) = choose(trace, current, Role::Input, editors[0], None)? else {
                return Ok(None);
            };
            actions.push(trace.perform(s, i, t, Operation::SetText, Some(&field.value), end)?);
            current = trace.dump(s, i, end)?;
            let ns = nodes(trace.body(current)?, trace.source)?;
            let rows: Vec<_> = ns
                .iter()
                .filter(|n| {
                    usable(n, trace.source)
                        && n["editable"] != true
                        && n["clickable"] == true
                        && field.aliases.iter().any(|v| {
                            term(
                                &format!("{} {}", text(n, "text"), text(n, "content-desc")),
                                v,
                            )
                        })
                        && action_allowed(n, Role::Choice)
                })
                .collect();
            if rows.len() != 1 {
                return Ok(None);
            }
            let Some(t) = choose(trace, current, Role::Choice, rows[0], None)? else {
                return Ok(None);
            };
            actions.push(trace.perform(s, i, t, Operation::Click, None, end)?);
            current = trace.dump(s, i, end)?;
        } else {
            return Ok(None);
        }
    }
    let Some(final_node) = field_node(trace, current, field)? else {
        return Ok(None);
    };
    if !field_node_matches(
        field,
        &final_node,
        nodes(trace.body(current)?, trace.source)?,
        trace.source,
        calendar.is_some(),
    ) {
        return Ok(None);
    }
    if field.slot == Slot::OneWay && final_node["checked"] != true && final_node["selected"] != true
    {
        return Ok(None);
    }
    let observed = FieldEvidence {
        field: field.clone(),
        initial,
        initial_value,
        origin,
        actions,
        readback: current,
        final_node,
        calendar,
    };
    observed.guard(trace)?;
    Ok(Some(observed))
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct Form {
    fields: Vec<FieldEvidence>,
    frame: usize,
}
fn form_matches(trace: &Trace, q: &Query, form: &Form) -> Result<bool, String> {
    if q.fields.len() != form.fields.len() {
        return Ok(false);
    }
    let frame = &trace.frames[form.frame];
    let body = trace.body(frame.after)?;
    for (expected, observed) in q.fields.iter().zip(&form.fields) {
        if expected != &observed.field {
            return Ok(false);
        }
        observed.guard(trace)?;
        let Some(n) = field_node(trace, frame.after, expected)? else {
            return Ok(false);
        };
        if !trace.rendered(form.frame, &n)
            || !field_node_matches(
                expected,
                &n,
                nodes(body, trace.source)?,
                trace.source,
                observed.calendar.is_some(),
            )
        {
            return Ok(false);
        }
    }
    Ok(true)
}
fn enter_form(
    trace: &mut Trace,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    q: &Query,
    end: Instant,
) -> Result<Option<Form>, String> {
    let mut current = trace.dump(s, i, end)?;
    if field_node(trace, current, &q.fields[0])?.is_none() {
        let Some(t) = control(trace, current, Role::OpenQuery, entry_names(q.kind))? else {
            return Ok(None);
        };
        trace.perform(s, i, t, Operation::Click, None, end)?;
        current = trace.dump(s, i, end)?;
    }
    // A field named "city" on its own is not a public travel form. Observe
    // the complete fixed query and its normal search control before the first
    // SetText/date action, so an unrelated address/account form cannot qualify.
    if control(trace, current, Role::Submit, submit_names(q.kind))?.is_none() {
        return Ok(None);
    }
    for field in &q.fields {
        if field_node(trace, current, field)?.is_none() {
            return Ok(None);
        }
    }
    let mut observed = Vec::new();
    for f in &q.fields {
        let Some(e) = set_field(trace, s, i, f, current, end)? else {
            return Ok(None);
        };
        current = e.readback;
        observed.push(e);
    }
    let frame = trace.frame(s, i, end)?;
    let form = Form {
        fields: observed,
        frame,
    };
    if !form_matches(trace, q, &form)? {
        return Ok(None);
    }
    Ok(Some(form))
}
fn frame_nodes(trace: &Trace, frame: usize) -> Result<Vec<&Value>, String> {
    let f = trace
        .frames
        .get(frame)
        .ok_or("travel scoped frame absent")?;
    Ok(nodes(trace.body(f.after)?, trace.source)?
        .iter()
        .filter(|n| usable(n, trace.source) && trace.rendered(frame, n))
        .collect())
}
fn strings(trace: &Trace, frame: usize) -> Result<Vec<String>, String> {
    Ok(frame_nodes(trace, frame)?
        .iter()
        .filter(|n| n["editable"] != true)
        .flat_map(|n| [text(n, "text"), text(n, "content-desc")])
        .filter(|v| !v.is_empty())
        .map(str::to_owned)
        .collect())
}
fn label_values(value: &str, slot: Slot) -> Vec<String> {
    let value = norm(value);
    let mut found = Vec::new();
    for kind in [
        Slot::Origin,
        Slot::Destination,
        Slot::Start,
        Slot::End,
        Slot::People,
        Slot::Rooms,
        Slot::PickupTime,
        Slot::DropoffTime,
        Slot::OneWay,
    ] {
        for label in labels(kind) {
            let label = norm(label);
            for (at, _) in value.match_indices(&label) {
                let end = at + label.len();
                let left = value[..at].chars().next_back();
                let right = value[end..].chars().next();
                if (!label.chars().next().unwrap().is_ascii_alphanumeric()
                    || left.is_none_or(|c| !c.is_ascii_alphanumeric()))
                    && (!label.chars().next_back().unwrap().is_ascii_alphanumeric()
                        || right.is_none_or(|c| !c.is_ascii_alphanumeric()))
                {
                    found.push((at, end, kind));
                }
            }
        }
    }
    // Prefer "departure date" to its overlapping "departure" label, and
    // do not let a larger control's text assign one value to both roles.
    found.sort_by_key(|(start, end, _)| (*start, std::cmp::Reverse(*end)));
    found.dedup();
    let mut labels_in_order = Vec::new();
    let mut end = 0;
    for item in found {
        if item.0 >= end {
            end = item.1;
            labels_in_order.push(item);
        }
    }
    labels_in_order
        .iter()
        .enumerate()
        .filter_map(|(index, (_, end, kind))| {
            if *kind != slot {
                return None;
            }
            let next = labels_in_order.get(index + 1).map_or(value.len(), |v| v.0);
            let segment =
                value[*end..next].trim_matches(|c: char| c.is_whitespace() || ":：".contains(c));
            (!segment.is_empty()).then(|| segment.to_owned())
        })
        .collect()
}

fn directional_values_match(value: &str, left: &Field, right: &Field, short_dates: bool) -> bool {
    // Actual direction/range syntax is required. Mere token presence does not
    // distinguish JFK -> SFO from SFO -> JFK or check-in from check-out.
    let value = norm(value);
    let mut matched = false;
    for separator in ["→", "⟶", "➝", "->", " to ", "至", "到", " – ", " — ", " - "] {
        for (at, _) in value.match_indices(separator) {
            let (a, b) = (&value[..at], &value[at + separator.len()..]);
            let forward = left.matches(a, short_dates)
                && right.matches(b, short_dates)
                && !right.matches(a, short_dates)
                && !left.matches(b, short_dates);
            let reverse = right.matches(a, short_dates) && left.matches(b, short_dates);
            if reverse {
                return false;
            }
            matched |= forward;
        }
    }
    matched
}

fn paired_values_match(value: &str, left: &Field, right: &Field, short_dates: bool) -> bool {
    let a = label_values(value, left.slot);
    let b = label_values(value, right.slot);
    // Any explicit conflicting role takes precedence over an incidental
    // matching string elsewhere in the header/detail. "JFK to SFO" has only
    // a destination label, so its actual direction is checked below as well.
    let identical_value =
        left.value == right.value && left.aliases == right.aliases && left.date == right.date;
    if a.iter().any(|v| {
        !left.matches(v, short_dates) || (!identical_value && right.matches(v, short_dates))
    }) || b.iter().any(|v| {
        !right.matches(v, short_dates) || (!identical_value && left.matches(v, short_dates))
    }) {
        return false;
    }
    if !a.is_empty() && !b.is_empty() {
        return true;
    }
    directional_values_match(value, left, right, short_dates)
}

fn query_values_match(value: &str, q: &Query, short_dates: bool) -> bool {
    let field = |slot| q.fields.iter().find(|f| f.slot == slot);
    for (a, b) in [
        (Slot::Origin, Slot::Destination),
        (Slot::Start, Slot::End),
        (Slot::PickupTime, Slot::DropoffTime),
    ] {
        if let (Some(left), Some(right)) = (field(a), field(b)) {
            if !paired_values_match(value, left, right, short_dates) {
                return false;
            }
        }
    }
    q.fields.iter().filter(|f| f.slot != Slot::OneWay).all(|f| {
        if matches!(f.slot, Slot::People | Slot::Rooms) {
            return f.matches(value, short_dates);
        }
        let labelled = label_values(value, f.slot);
        if labelled.is_empty() {
            f.matches(value, short_dates)
        } else {
            labelled.iter().all(|v| f.matches(v, short_dates))
        }
    })
}

fn query_header(
    trace: &Trace,
    frame: usize,
    q: &Query,
    form: Option<&Form>,
) -> Result<bool, String> {
    // Only a real form from this same trace can qualify a shortened result
    // date. A separately reopened task never receives the first trace's form.
    let short_dates = if let Some(form) = form {
        form_matches(trace, q, form)? && trace.frames[form.frame].after < trace.frames[frame].before
    } else {
        false
    };
    let f = &trace.frames[frame];
    let text = frame_nodes(trace, frame)?
        .iter()
        .filter(|n| {
            Rect::parse(&n["bounds_array"])
                .is_ok_and(|r| r.0[1] < f.window.0[1] + f.window.height() / 3)
        })
        .flat_map(|n| [text(n, "text"), text(n, "content-desc"), text(n, "value")])
        .collect::<Vec<_>>()
        .join(" ");
    Ok(query_values_match(&text, q, short_dates))
}
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct Amount {
    currency: &'static str,
    minor: u64,
}
fn amount(text: &str) -> Option<Amount> {
    let mut value = text.trim();
    for prefix in ["From ", "from ", "Starting at ", "起价 "] {
        if let Some(v) = value.strip_prefix(prefix) {
            value = v;
            break;
        }
    }
    let (currency, number) = if let Some(v) = value.strip_prefix("US$") {
        ("USD", v)
    } else if let Some(v) = value.strip_prefix("USD ") {
        ("USD", v)
    } else if let Some(v) = value.strip_prefix('$') {
        ("$", v)
    } else if let Some(v) = value
        .strip_prefix('£')
        .or_else(|| value.strip_prefix("GBP "))
    {
        ("GBP", v)
    } else if let Some(v) = value
        .strip_prefix('€')
        .or_else(|| value.strip_prefix("EUR "))
    {
        ("EUR", v)
    } else if let Some(v) = value.strip_prefix("CNY ") {
        ("CNY", v)
    } else if let Some(v) = value.strip_prefix('¥').or_else(|| value.strip_prefix('￥')) {
        ("¥", v)
    } else if let Some(v) = value
        .strip_suffix('円')
        .or_else(|| value.strip_prefix("JPY "))
    {
        ("JPY", v)
    } else {
        return None;
    };
    let number = number.trim();
    let mut end = number.len();
    for (i, ch) in number.char_indices() {
        if !ch.is_ascii_digit() && ch != '.' && ch != ',' {
            end = i;
            break;
        }
    }
    let tail = number[end..].trim();
    let number = &number[..end];
    if !tail.is_empty()
        && ![
            "/night",
            "/ night",
            "per night",
            "/day",
            "/ day",
            "per day",
            "起",
            "每晚",
            "/晚",
            "每人",
        ]
        .contains(&tail)
    {
        return None;
    }
    if number.is_empty() || number.len() > 18 {
        return None;
    }
    let mut p = number.split('.');
    let integer = p.next()?;
    if integer.contains(',') {
        let pieces: Vec<_> = integer.split(',').collect();
        if pieces[0].is_empty()
            || pieces[0].len() > 3
            || pieces.iter().skip(1).any(|x| x.len() != 3)
        {
            return None;
        }
    }
    let whole = integer.replace(',', "");
    if whole.is_empty() || !whole.bytes().all(|v| v.is_ascii_digit()) {
        return None;
    }
    let fraction = match p.next() {
        None => 0,
        Some(v) if v.len() == 1 && v.bytes().all(|v| v.is_ascii_digit()) => {
            v.parse::<u64>().ok()? * 10
        }
        Some(v) if v.len() == 2 && v.bytes().all(|v| v.is_ascii_digit()) => {
            v.parse::<u64>().ok()?
        }
        _ => return None,
    };
    if p.next().is_some() {
        return None;
    }
    let minor = whole
        .parse::<u64>()
        .ok()?
        .checked_mul(100)?
        .checked_add(fraction)?;
    (minor > 0 && minor <= 100_000_000).then_some(Amount { currency, minor })
}

fn dangerous_text(s: &str) -> bool {
    [
        "loading",
        "please wait",
        "network error",
        "no availability",
        "sold out",
        "no results",
        "try again",
        "加载中",
        "网络错误",
        "暂无结果",
        "售罄",
        "sponsored",
        "advertisement",
        "sign in",
        "log in",
        "password",
        "pay now",
        "book now",
        "reserve now",
        "广告",
        "推广",
        "登录",
        "登陆",
        "密码",
        "立即支付",
        "立即预订",
        "发送",
    ]
    .iter()
    .any(|v| term(s, v))
}
fn service_id(s: &str, kind: Kind, source: &Source) -> Option<String> {
    let compact = s.split_whitespace().collect::<String>().to_uppercase();
    if compact.len() > 8 {
        return None;
    }
    let (letters, digits) = match kind {
        Kind::Train => (1, compact.get(1..)?),
        Kind::Flight => (2, compact.get(2..)?),
        _ => return None,
    };
    if !(1..=5).contains(&digits.len()) || !digits.bytes().all(|v| v.is_ascii_digit()) {
        return None;
    }
    let prefix = compact.get(..letters)?;
    let accepted = if kind == Kind::Train {
        ["G", "D", "C", "Z", "T", "K"].contains(&prefix)
    } else {
        match source.package {
            "com.united.mobile.android" => prefix == "UA",
            "jp.co.ana.android.tabidachi" => prefix == "NH",
            "com.rytong.airchina" => prefix == "CA",
            "com.rytong.ceair" => ["MU", "FM"].contains(&prefix),
            _ => ["CA", "MU", "FM", "CZ", "HO", "HU", "ZH", "SC"].contains(&prefix),
        }
    };
    accepted.then_some(compact)
}
fn clock_labels(s: &str) -> Vec<String> {
    s.split(|c: char| !c.is_ascii_digit() && c != ':')
        .filter(|t| {
            let mut p = t.split(':');
            let (Some(h), Some(m)) = (p.next(), p.next()) else {
                return false;
            };
            p.next().is_none()
                && (1..=2).contains(&h.len())
                && m.len() == 2
                && h.parse::<u32>().is_ok_and(|v| v < 24)
                && m.parse::<u32>().is_ok_and(|v| v < 60)
        })
        .map(str::to_owned)
        .collect()
}
#[derive(Clone, Debug, PartialEq, Serialize)]
struct Row {
    title: String,
    title_node: Value,
    card: Value,
    price: Amount,
    times: Vec<String>,
    availability: String,
    image: Option<Rect>,
}
fn readable_title(s: &str) -> bool {
    (5..=180).contains(&s.chars().count())
        && s.chars().filter(|c| c.is_alphabetic()).count() >= 3
        && !dangerous_text(s)
        && !s.contains("http")
        && !s.contains('…')
        && !s.ends_with("...")
        && amount(s).is_none()
        && clock_labels(s).is_empty()
        && ![
            "search",
            "total",
            "tax",
            "fee",
            "rooms",
            "room rate",
            "per night",
            "best rate",
            "available",
            "查询",
            "搜索",
            "总价",
            "税费",
            "房价",
            "每晚",
            "有房",
            "空房",
        ]
        .iter()
        .any(|v| term(s, v))
}
fn result_rows(trace: &Trace, frame: usize, q: &Query, form: &Form) -> Result<Vec<Row>, String> {
    if !query_header(trace, frame, q, Some(form))? {
        return Ok(vec![]);
    }
    let ns = frame_nodes(trace, frame)?;
    let window = trace.frames[frame].window;
    let mut found = Vec::<Row>::new();
    for card in &ns {
        let r = Rect::parse(&card["bounds_array"])?;
        if card["clickable"] != true
            || r.height() < 70
            || r.area() > window.area() * 2 / 3
            || !window.contains(r)
        {
            continue;
        }
        let mut inside: Vec<_> = ns
            .iter()
            .copied()
            .filter(|n| Rect::parse(&n["bounds_array"]).is_ok_and(|b| r.contains(b)))
            .collect();
        inside.sort_by_key(|n| {
            Rect::parse(&n["bounds_array"])
                .map(|b| (b.0[1], b.0[0]))
                .unwrap_or((i64::MAX, i64::MAX))
        });
        let values: Vec<_> = inside
            .iter()
            .filter(|n| n["editable"] != true)
            .map(|n| text(n, "text"))
            .filter(|s| !s.is_empty())
            .collect();
        if values.iter().any(|v| dangerous_text(v)) {
            continue;
        }
        let prices: Vec<_> = values.iter().filter_map(|s| amount(s)).collect();
        if prices.is_empty() {
            continue;
        }
        let candidate = match q.kind {
            Kind::Flight | Kind::Train => inside
                .iter()
                .find(|n| service_id(text(n, "text"), q.kind, trace.source).is_some()),
            Kind::Hotel => inside.iter().find(|n| {
                readable_title(text(n, "text"))
                    && !q
                        .fields
                        .iter()
                        .any(|f| f.aliases.iter().any(|v| same_title(v, text(n, "text"))))
            }),
            Kind::Rental => inside.iter().find(|n| {
                readable_title(text(n, "text"))
                    && [
                        "economy",
                        "compact",
                        "intermediate",
                        "full-size",
                        "standard",
                        "suv",
                        "premium",
                        "luxury",
                        "van",
                        "经济",
                        "紧凑",
                        "舒适",
                        "商务",
                        "豪华",
                    ]
                    .iter()
                    .any(|v| term(text(n, "text"), v))
            }),
        };
        let Some(title_node) = candidate else {
            continue;
        };
        let title = service_id(text(title_node, "text"), q.kind, trace.source)
            .unwrap_or_else(|| text(title_node, "text").to_owned());
        let times = values
            .iter()
            .flat_map(|v| clock_labels(v))
            .collect::<Vec<_>>();
        let availability = values
            .iter()
            .filter(|v| {
                [
                    "available",
                    "seats",
                    "rooms",
                    "有房",
                    "有",
                    "余票",
                    "张",
                    "二等座",
                    "一等座",
                    "商务座",
                ]
                .iter()
                .any(|a| term(v, a))
            })
            .copied()
            .collect::<Vec<_>>()
            .join(" ");
        if matches!(q.kind, Kind::Flight | Kind::Train) && times.len() < 2 {
            continue;
        }
        if q.kind == Kind::Train
            && (availability.is_empty()
                || !["有", "张", "available"]
                    .iter()
                    .any(|v| term(&availability, v)))
        {
            continue;
        }
        let image = inside
            .iter()
            .find(|n| image(n, trace.source))
            .and_then(|n| Rect::parse(&n["bounds_array"]).ok());
        if q.kind == Kind::Hotel && image.is_none() {
            continue;
        }
        let row = Row {
            title,
            title_node: (*title_node).clone(),
            card: (*card).clone(),
            price: prices[0].clone(),
            times,
            availability,
            image,
        };
        if let Some(previous) = found
            .iter_mut()
            .find(|v| v.title == row.title && v.price == row.price)
        {
            if r.area() < Rect::parse(&previous.card["bounds_array"])?.area() {
                *previous = row
            }
        } else {
            found.push(row)
        }
    }
    found.sort_by_key(|r| {
        Rect::parse(&r.card["bounds_array"])
            .map(|v| (v.0[1], v.0[0]))
            .unwrap_or((i64::MAX, i64::MAX))
    });
    let mut disjoint = Vec::<Row>::new();
    for row in found {
        let rect = Rect::parse(&row.card["bounds_array"])?;
        if disjoint
            .iter()
            .all(|other| Rect::parse(&other.card["bounds_array"]).is_ok_and(|r| r.disjoint(rect)))
        {
            disjoint.push(row);
        }
        if disjoint.len() == 16 {
            break;
        }
    }
    Ok(disjoint)
}
fn same_row(a: &Row, b: &Row) -> bool {
    same_title(&a.title, &b.title) && a.price == b.price && a.times == b.times
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct PriceProof {
    amount: Amount,
    components: Vec<(String, Amount)>,
    explicitly_inclusive: bool,
    coverage: &'static str,
}
fn complete_price(trace: &Trace, frame: usize) -> Result<Option<PriceProof>, String> {
    let ns = frame_nodes(trace, frame)?;
    let mut total = None;
    let mut components = Vec::new();
    let mut inclusive = false;
    let all = strings(trace, frame)?.join(" ");
    inclusive |= [
        "includes taxes and fees",
        "taxes and fees included",
        "including taxes",
        "含税",
        "含税费",
        "税费已含",
        "税込",
    ]
    .iter()
    .any(|v| term(&all, v));
    for node in &ns {
        let Some(value) = amount(text(node, "text")) else {
            continue;
        };
        let rect = Rect::parse(&node["bounds_array"])?;
        let context = ns
            .iter()
            .filter(|n| {
                Rect::parse(&n["bounds_array"]).is_ok_and(|r| {
                    r.0[1] < rect.0[3]
                        && rect.0[1] < r.0[3]
                        && r.0[0] < rect.0[2]
                        && (rect.0[0] - r.0[2]).abs() <= 480
                })
            })
            .map(|n| text(n, "text"))
            .collect::<Vec<_>>()
            .join(" ");
        if ["total", "total price", "total fare", "总价", "合计", "总额"]
            .iter()
            .any(|v| term(&context, v))
        {
            if total.as_ref().is_some_and(|previous| previous != &value) {
                return Ok(None);
            }
            total = Some(value);
        } else if [
            "base fare",
            "subtotal",
            "room subtotal",
            "vehicle subtotal",
            "基础票价",
            "小计",
        ]
        .iter()
        .any(|v| term(&context, v))
        {
            components.push(("base".into(), value));
        } else if ["tax", "taxes", "税"].iter().any(|v| term(&context, v)) {
            components.push(("tax".into(), value));
        } else if ["fee", "fees", "费"].iter().any(|v| term(&context, v)) {
            components.push(("fee".into(), value));
        }
    }
    let Some(total) = total else { return Ok(None) };
    if !components.is_empty() {
        if components.iter().filter(|(kind, _)| kind == "base").count() != 1
            || components.iter().any(|(_, v)| v.currency != total.currency)
            || components
                .iter()
                .try_fold(0u64, |sum, (_, v)| sum.checked_add(v.minor))
                != Some(total.minor)
        {
            return Ok(None);
        }
    } else if !inclusive {
        return Ok(None);
    }
    Ok(Some(PriceProof {
        amount: total,
        components,
        explicitly_inclusive: inclusive,
        coverage: "displayed_total_with_components_or_inclusive_label",
    }))
}
#[derive(Clone, Debug, PartialEq, Serialize)]
struct Detail {
    price: PriceProof,
    address: Option<String>,
    required_text: Vec<String>,
    matching_image: bool,
}
fn similar_image(a: &Patch, b: &Patch) -> bool {
    a.rgb.len() == 768
        && b.rgb.len() == 768
        && a.rgb
            .iter()
            .zip(&b.rgb)
            .map(|(a, b)| u64::from(a.abs_diff(*b)))
            .sum::<u64>()
            <= 768 * 48
}
fn detail_frames(
    trace: &Trace,
    frames: &[usize],
    selected: &Row,
    q: &Query,
    results: usize,
    form: &Form,
) -> Result<Option<Detail>, String> {
    if frames.is_empty()
        || frames.len() > 2
        || !form_matches(trace, q, form)?
        || frames
            .iter()
            .any(|f| trace.frames[form.frame].after >= trace.frames[*f].before)
    {
        return Ok(None);
    }
    let mut values = Vec::new();
    for frame in frames {
        values.extend(strings(trace, *frame)?);
    }
    let all = values.join(" ");
    if !values.iter().any(|v| {
        same_title(v, &selected.title)
            || service_id(v, q.kind, trace.source).as_ref() == Some(&selected.title)
    }) {
        return Ok(None);
    }
    let mut price = None;
    for frame in frames {
        if let Some(total) = complete_price(trace, *frame)? {
            price = Some(total);
        }
    }
    if price.is_none()
        && matches!(q.kind, Kind::Flight | Kind::Train)
        && values
            .iter()
            .filter_map(|v| amount(v))
            .any(|v| v == selected.price)
    {
        price = Some(PriceProof {
            amount: selected.price.clone(),
            components: vec![],
            explicitly_inclusive: false,
            coverage: "exact_selected_displayed_fare_without_tax_inclusion_inference",
        });
    }
    let Some(price) = price else { return Ok(None) };
    if price.amount.currency != selected.price.currency
        || !values
            .iter()
            .filter_map(|v| amount(v))
            .any(|v| v == selected.price)
    {
        return Ok(None);
    }
    let mut required_text = Vec::new();
    let mut address = None;
    let mut matching_image = false;
    match q.kind {
        Kind::Hotel => {
            address = values
                .iter()
                .find(|v| {
                    ["London", "伦敦", "ロンドン"]
                        .iter()
                        .any(|city| term(v, city))
                        && (v.chars().any(|v| v.is_ascii_digit())
                            || ["road", "street", "lane", "avenue", "街", "路"]
                                .iter()
                                .any(|x| term(v, x)))
                })
                .cloned();
            if address.is_none() {
                return Ok(None);
            }
            let amenities = [
                "wifi",
                "wi-fi",
                "pool",
                "fitness",
                "breakfast",
                "parking",
                "无线",
                "泳池",
                "健身",
                "早餐",
                "停车",
            ]
            .iter()
            .filter(|v| term(&all, v))
            .map(|v| (*v).to_owned())
            .collect::<Vec<_>>();
            if amenities.len() < 2
                || ![
                    "king", "queen", "twin", "suite", "standard", "double", "大床", "双床", "套房",
                ]
                .iter()
                .any(|v| term(&all, v))
                || !["per night", "nightly", "room rate", "每晚", "房价"]
                    .iter()
                    .any(|v| term(&all, v))
            {
                return Ok(None);
            }
            required_text.extend(amenities);
            if let Some(original) = selected
                .image
                .and_then(|r| trace.frames[results].patches.get(&r))
            {
                for frame in frames {
                    matching_image |= frame_nodes(trace, *frame)?
                        .iter()
                        .filter(|n| image(n, trace.source))
                        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
                        .filter_map(|r| trace.frames[*frame].patches.get(&r))
                        .any(|p| similar_image(original, p));
                }
            }
            if !matching_image {
                return Ok(None);
            }
        }
        Kind::Flight => {
            if !selected
                .times
                .iter()
                .all(|v| values.iter().any(|t| clock_labels(t).contains(v)))
            {
                return Ok(None);
            }
            let restrictions = values
                .iter()
                .filter(|v| {
                    v.chars().count() >= 12
                        && [
                            "refundable",
                            "non-refundable",
                            "baggage",
                            "changes",
                            "refund",
                            "退改",
                            "行李",
                            "変更",
                            "払戻",
                        ]
                        .iter()
                        .any(|r| term(v, r))
                })
                .cloned()
                .collect::<Vec<_>>();
            if restrictions.is_empty() {
                return Ok(None);
            }
            required_text.extend(restrictions);
        }
        Kind::Train => {
            if !selected
                .times
                .iter()
                .all(|v| values.iter().any(|t| clock_labels(t).contains(v)))
                || !["二等座", "一等座", "商务座", "second class", "first class"]
                    .iter()
                    .any(|v| term(&all, v))
            {
                return Ok(None);
            }
            required_text.push(selected.availability.clone());
        }
        Kind::Rental => {
            if !query_values_match(&all, q, true) {
                return Ok(None);
            }
            required_text.push(selected.title.clone());
        }
    }
    let start = q.fields.iter().find(|f| f.slot == Slot::Start);
    let end = q.fields.iter().find(|f| f.slot == Slot::End);
    let dates_match = match (start, end) {
        (Some(a), Some(b)) => paired_values_match(&all, a, b, true),
        (Some(a), None) => a.matches(&all, true),
        _ => false,
    };
    if !dates_match {
        return Ok(None);
    }
    Ok(Some(Detail {
        price,
        address,
        required_text,
        matching_image,
    }))
}

#[derive(Clone, Debug, PartialEq, Serialize)]
struct Search {
    query: Query,
    form: Form,
    submitted: usize,
    results: usize,
    rows: Vec<Row>,
}
#[derive(Clone, Debug, PartialEq, Serialize)]
struct Opened {
    clicked: usize,
    frames: Vec<usize>,
    actions: Vec<usize>,
    detail: Option<Detail>,
    backs: Vec<(usize, usize)>,
}
#[derive(Clone, Debug, PartialEq, Serialize)]
struct Flow {
    first: Search,
    selected: Row,
    opened: Option<Opened>,
    second: Option<Search>,
    returned: Option<(usize, usize)>,
}
struct Phase {
    trace: Trace,
    flows: Vec<Flow>,
    stop: &'static str,
}
struct Reopen {
    trace: Trace,
    frame: usize,
    dates: Vec<ReopenedDate>,
    query_preserved: bool,
}

// These indices are created only by the second session's normal UI factory.
// No first-session FieldEvidence or comparison document can construct them.
#[derive(Serialize)]
struct ReopenedDate {
    field: Field,
    origin: usize,
    opened: usize,
    calendar: usize,
    closed: usize,
    readback: usize,
}

fn selected_calendar_date(trace: &Trace, frame: usize, date: Date) -> Result<bool, String> {
    let ns = frame_nodes(trace, frame)?;
    selected_calendar_nodes(&ns, date)
}

fn selected_calendar_nodes(ns: &[&Value], date: Date) -> Result<bool, String> {
    // A day in a neighbouring month cannot borrow this month's heading. Only
    // one actual rendered month/year heading is admitted by this small reader.
    let mut years = ns
        .iter()
        .flat_map(|n| [text(n, "text"), text(n, "content-desc")])
        .flat_map(|v| v.split(|c: char| !c.is_ascii_digit()))
        .filter(|v| v.len() == 4)
        .filter_map(|v| v.parse::<u32>().ok())
        .collect::<BTreeSet<_>>();
    years.insert(date.year);
    if years.len() > 16 {
        return Ok(false);
    }
    let month_labels = (1..=12)
        .flat_map(|month| {
            years.iter().flat_map(move |year| {
                Date {
                    year: *year,
                    month,
                    day: 1,
                }
                .month_names()
            })
        })
        .collect::<Vec<_>>();
    let headings = ns
        .iter()
        .filter(|n| {
            month_labels.iter().any(|v| {
                norm(text(n, "text")) == norm(v) || norm(text(n, "content-desc")) == norm(v)
            })
        })
        .collect::<Vec<_>>();
    if headings.len() != 1
        || !date.month_names().iter().any(|v| {
            norm(text(headings[0], "text")) == norm(v)
                || norm(text(headings[0], "content-desc")) == norm(v)
        })
    {
        return Ok(false);
    }
    let month_rect = Rect::parse(&headings[0]["bounds_array"])?;
    Ok(ns
        .iter()
        .filter(|n| {
            text(n, "text").trim() == date.day.to_string()
                && (n["selected"] == true || n["checked"] == true)
                && Rect::parse(&n["bounds_array"]).is_ok_and(|r| r.0[1] >= month_rect.0[3])
        })
        .count()
        == 1)
}

impl ReopenedDate {
    fn guard(&self, trace: &Trace, initial_frame: usize, q: &Query) -> Result<(), String> {
        let date = self
            .field
            .date
            .ok_or("travel fresh calendar field is not a date")?;
        need(
            trace.second && q.fields.iter().any(|f| f == &self.field),
            "travel calendar observation is not from the fixed second query",
        )?;
        let initial = field_node(trace, trace.frames[initial_frame].after, &self.field)?
            .ok_or("travel fresh calendar lacks its initial field")?;
        let before = field_node(trace, self.origin, &self.field)?
            .ok_or("travel fresh calendar lacks its actual open target")?;
        let after = field_node(trace, self.readback, &self.field)?
            .ok_or("travel fresh calendar did not restore its actual field")?;
        let original_value = field_value(
            &initial,
            nodes(trace.body(trace.frames[initial_frame].after)?, trace.source)?,
            trace.source,
        );
        need(
            trace.rendered(initial_frame, &initial)
                && self.field.matches(&original_value, true)
                && trace.frames[initial_frame].after <= self.origin
                && self.origin < self.opened
                && self.opened < trace.frames[self.calendar].before
                && trace.frames[self.calendar].after < self.closed
                && self.closed < self.readback
                && trace.steps[self.opened].op == Operation::Click
                && trace.steps[self.opened].target.as_ref().is_some_and(
                    |(origin, role, node, _)| {
                        *origin == self.origin && *role == Role::Date && node == &before
                    },
                )
                && trace.steps[self.opened + 1..self.closed]
                    .iter()
                    .all(|s| s.op == Operation::Dump)
                && trace.steps[self.closed].op == Operation::Click
                && trace.steps[self.closed]
                    .target
                    .as_ref()
                    .is_some_and(|(_, role, node, _)| {
                        *role == Role::Back
                            && calendar_close_names().iter().any(|v| {
                                same_title(text(node, "text"), v)
                                    || same_title(text(node, "content-desc"), v)
                            })
                    })
                && field_value(
                    &before,
                    nodes(trace.body(self.origin)?, trace.source)?,
                    trace.source,
                ) == original_value
                && field_value(
                    &after,
                    nodes(trace.body(self.readback)?, trace.source)?,
                    trace.source,
                ) == original_value
                && selected_calendar_date(trace, self.calendar, date)?,
            "travel reopened date lost its own selected year/month/day or nonmutating return",
        )
    }
}

fn calendar_close_names() -> &'static [&'static str] {
    &[
        "Cancel",
        "取消",
        "キャンセル",
        "Back",
        "Navigate up",
        "返回",
        "上一页",
        "戻る",
    ]
}

fn observe_reopened_dates(
    trace: &mut Trace,
    frame: usize,
    q: &Query,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    end: Instant,
) -> Result<Vec<ReopenedDate>, String> {
    need(
        trace.second,
        "travel fresh calendar requires the second actual trace",
    )?;
    let mut current = trace.frames[frame].after;
    let mut dates = Vec::new();
    for field in q.fields.iter().filter(|f| f.date.is_some()) {
        need(
            dates.len() < REOPEN_CALENDAR_LIMIT,
            "travel fresh calendar count exceeds the fixed query",
        )?;
        let Some(initial) = field_node(trace, trace.frames[frame].after, field)? else {
            break;
        };
        let value = field_value(
            &initial,
            nodes(trace.body(trace.frames[frame].after)?, trace.source)?,
            trace.source,
        );
        if field.matches(&value, false) {
            continue;
        }
        if !trace.rendered(frame, &initial) || !field.matches(&value, true) {
            break;
        }
        let Some(node) = field_node(trace, current, field)? else {
            break;
        };
        if field_value(
            &node,
            nodes(trace.body(current)?, trace.source)?,
            trace.source,
        ) != value
        {
            break;
        }
        let Some(target) = choose(trace, current, Role::Date, &node, None)? else {
            break;
        };
        let origin = current;
        let opened = trace.perform(s, i, target, Operation::Click, None, end)?;
        let calendar = trace.frame(s, i, end)?;
        // Never select another day or month. Closing an unproved calendar is
        // still an actual reversible UI action, but issues no date proof.
        let selected = selected_calendar_date(trace, calendar, field.date.unwrap())?;
        let Some(target) = control(
            trace,
            trace.frames[calendar].after,
            Role::Back,
            calendar_close_names(),
        )?
        else {
            break;
        };
        let closed = trace.perform(s, i, target, Operation::Click, None, end)?;
        current = trace.dump(s, i, end)?;
        if !selected {
            break;
        }
        let proof = ReopenedDate {
            field: field.clone(),
            origin,
            opened,
            calendar,
            closed,
            readback: current,
        };
        proof.guard(trace, frame, q)?;
        dates.push(proof);
    }
    Ok(dates)
}
pub(super) struct TravelExecution {
    source: &'static Source,
    day: u64,
    first: Phase,
    reopened: Option<Reopen>,
    original_end: Instant,
}
fn search_guard(trace: &Trace, search: &Search) -> Result<(), String> {
    need(
        form_matches(trace, &search.query, &search.form)?
            && trace.steps[search.submitted].op == Operation::Click
            && trace.steps[search.submitted]
                .target
                .as_ref()
                .is_some_and(|(_, role, _, _)| *role == Role::Submit)
            && trace.frames[search.form.frame].after < search.submitted
            && search.submitted < trace.frames[search.results].before,
        "travel query lost its complete actual form/submit/result order",
    )?;
    let rows = result_rows(trace, search.results, &search.query, &search.form)?;
    need(
        rows.len() >= 2 && rows == search.rows,
        "travel actual matching result identities changed",
    )
}
fn submit_search(
    trace: &mut Trace,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    q: Query,
    end: Instant,
) -> Result<Option<Search>, String> {
    let Some(form) = enter_form(trace, s, i, &q, end)? else {
        return Ok(None);
    };
    let origin = trace.frames[form.frame].after;
    let Some(t) = control(trace, origin, Role::Submit, submit_names(q.kind))? else {
        return Ok(None);
    };
    let submitted = trace.perform(s, i, t, Operation::Click, None, end)?;
    let results = trace.frame(s, i, end)?;
    let rows = result_rows(trace, results, &q, &form)?;
    if rows.len() < 2 {
        return Ok(None);
    }
    let search = Search {
        query: q,
        form,
        submitted,
        results,
        rows,
    };
    search_guard(trace, &search)?;
    Ok(Some(search))
}
fn extra_detail_names(kind: Kind) -> &'static [&'static str] {
    match kind {
        Kind::Hotel => &[
            "View rooms",
            "Rooms and rates",
            "Room options",
            "Room rates",
            "查看房型",
            "房型和房价",
            "查看房价",
        ],
        Kind::Flight => &[
            "Fare details",
            "Fare rules",
            "Fare conditions",
            "票价详情",
            "退改规则",
            "運賃規則",
        ],
        Kind::Rental => &[
            "Price details",
            "Rate details",
            "Price breakdown",
            "费用明细",
            "价格明细",
        ],
        Kind::Train => &["Timetable", "Train details", "时刻表", "列车详情"],
    }
}
fn opened_guard(trace: &Trace, flow: &Flow) -> Result<(), String> {
    let Some(opened) = &flow.opened else {
        return Ok(());
    };
    need(
        opened.frames.len() >= 1
            && opened.frames.len() <= 2
            && opened.actions.len() <= 1
            && flow.first.rows.iter().any(|row| row == &flow.selected)
            && trace.steps[opened.clicked].op == Operation::Click
            && trace.steps[opened.clicked].target.as_ref().is_some_and(
                |(origin, role, node, container)| {
                    *origin == trace.frames[flow.first.results].after
                        && *role == Role::Result
                        && node == &flow.selected.title_node
                        && *container == Rect::parse(&flow.selected.card["bounds_array"]).ok()
                },
            )
            && opened.clicked < trace.frames[opened.frames[0]].before,
        "travel selected result/detail entry changed",
    )?;
    for (index, action) in opened.actions.iter().enumerate() {
        need(
            trace.steps[*action].op == Operation::Click
                && trace.frames[opened.frames[index]].after < *action
                && *action < trace.frames[opened.frames[index + 1]].before
                && trace.steps[*action]
                    .target
                    .as_ref()
                    .is_some_and(|(_, role, node, _)| {
                        *role == Role::Choice
                            && extra_detail_names(flow.first.query.kind).iter().any(|v| {
                                same_title(text(node, "text"), v)
                                    || same_title(text(node, "content-desc"), v)
                            })
                    }),
            "travel detail route left its explicit read-only control",
        )?;
    }
    need(
        opened.detail
            == detail_frames(
                trace,
                &opened.frames,
                &flow.selected,
                &flow.first.query,
                flow.first.results,
                &flow.first.form,
            )?,
        "travel retained address/image/fare/restriction facts changed",
    )?;
    for (action, frame) in &opened.backs {
        need(
            trace.steps[*action].op == Operation::Click
                && trace.steps[*action]
                    .target
                    .as_ref()
                    .is_some_and(|(_, role, _, _)| *role == Role::Back)
                && *action < trace.frames[*frame].before,
            "travel normal detail return is not an actual Back",
        )?;
    }
    Ok(())
}
fn open_result(
    p: &mut Phase,
    index: usize,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    end: Instant,
) -> Result<bool, String> {
    let selected = p.flows[index].selected.clone();
    let first = p.flows[index].first.clone();
    let origin = p.trace.frames[first.results].after;
    let Some(t) = choose(
        &p.trace,
        origin,
        Role::Result,
        &selected.title_node,
        Some(Rect::parse(&selected.card["bounds_array"])?),
    )?
    else {
        p.stop = "selected_travel_result_has_no_unique_actual_control";
        return Ok(false);
    };
    let clicked = p.trace.perform(s, i, t, Operation::Click, None, end)?;
    let frame = p.trace.frame(s, i, end)?;
    let mut frames = vec![frame];
    let mut actions = Vec::new();
    let mut facts = detail_frames(
        &p.trace,
        &frames,
        &selected,
        &first.query,
        first.results,
        &first.form,
    )?;
    if facts.is_none() {
        let origin = p.trace.frames[frame].after;
        if let Some(t) = control(
            &p.trace,
            origin,
            Role::Choice,
            extra_detail_names(first.query.kind),
        )? {
            actions.push(p.trace.perform(s, i, t, Operation::Click, None, end)?);
            frames.push(p.trace.frame(s, i, end)?);
            facts = detail_frames(
                &p.trace,
                &frames,
                &selected,
                &first.query,
                first.results,
                &first.form,
            )?;
        }
    }
    let mut opened = Opened {
        clicked,
        frames,
        actions,
        detail: facts,
        backs: Vec::new(),
    };
    for _ in 0..2 {
        let origin = p.trace.dump(s, i, end)?;
        let Some(action) = back(&mut p.trace, s, i, origin, end)? else {
            break;
        };
        let frame = p.trace.frame(s, i, end)?;
        opened.backs.push((action, frame));
        if result_rows(&p.trace, frame, &first.query, &first.form)?
            .iter()
            .any(|row| same_row(row, &selected))
        {
            break;
        }
    }
    let returned = opened.backs.last().is_some_and(|(_, frame)| {
        result_rows(&p.trace, *frame, &first.query, &first.form)
            .is_ok_and(|rows| rows.iter().any(|row| same_row(row, &selected)))
    });
    p.flows[index].opened = Some(opened);
    opened_guard(&p.trace, &p.flows[index])?;
    if !returned {
        p.stop = "selected_travel_detail_did_not_return_to_matching_query_results";
    }
    Ok(returned)
}
fn edit_form(
    trace: &mut Trace,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    end: Instant,
) -> Result<bool, String> {
    let origin = trace.dump(s, i, end)?;
    if let Some(t) = control(
        trace,
        origin,
        Role::EditQuery,
        &[
            "Edit search",
            "Modify search",
            "Edit query",
            "Change search",
            "修改查询",
            "修改搜索",
            "更改搜索",
            "条件を変更",
        ],
    )? {
        trace.perform(s, i, t, Operation::Click, None, end)?;
        Ok(true)
    } else {
        Ok(back(trace, s, i, origin, end)?.is_some())
    }
}
fn flow(
    p: &mut Phase,
    source: &'static Source,
    kind: Kind,
    day: u64,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    end: Instant,
) -> Result<(), String> {
    let first_query = query(source, kind, day, false)?;
    let Some(first) = submit_search(&mut p.trace, s, i, first_query, end)? else {
        p.stop = "complete_travel_form_or_matching_populated_availability_unavailable";
        return Ok(());
    };
    let selected = first.rows[0].clone();
    let index = p.flows.len();
    p.flows.push(Flow {
        first,
        selected,
        opened: None,
        second: None,
        returned: None,
    });
    if !open_result(p, index, s, i, end)? {
        return Ok(());
    }
    if !edit_form(&mut p.trace, s, i, end)? {
        p.stop = "travel_query_edit_control_unavailable";
        return Ok(());
    }
    let edited = query(source, kind, day, true)?;
    let Some(second) = submit_search(&mut p.trace, s, i, edited, end)? else {
        p.stop = "edited_travel_dates_or_matching_availability_unavailable";
        return Ok(());
    };
    p.flows[index].second = Some(second);
    let origin = p.trace.dump(s, i, end)?;
    let Some(action) = back(&mut p.trace, s, i, origin, end)? else {
        p.stop = "edited_query_back_control_unavailable";
        return Ok(());
    };
    let frame = p.trace.frame(s, i, end)?;
    let second = p.flows[index].second.as_ref().unwrap();
    let returned = Form {
        fields: second.form.fields.clone(),
        frame,
    };
    if form_matches(&p.trace, &second.query, &returned)? {
        p.flows[index].returned = Some((action, frame));
        p.stop = "actual_travel_query_detail_edit_and_return_observed";
    } else {
        p.stop = "edited_travel_query_not_preserved_on_return";
    }
    Ok(())
}
fn current_query(
    trace: &Trace,
    frame: usize,
    search: &Search,
    dates: &[ReopenedDate],
) -> Result<bool, String> {
    // Read only this second task's fresh indices and native fields. The original
    // query is separately guarded against its first finished history.
    need(
        trace.second && dates.len() <= REOPEN_CALENDAR_LIMIT,
        "travel reopen calendar provenance differs",
    )?;
    for date in dates {
        date.guard(trace, frame, &search.query)?;
    }
    if dates
        .iter()
        .map(|d| d.opened)
        .collect::<BTreeSet<_>>()
        .len()
        != dates.len()
        || trace
            .steps
            .iter()
            .filter(|s| {
                s.target
                    .as_ref()
                    .is_some_and(|(_, role, _, _)| *role == Role::Date)
            })
            .count()
            != dates.len()
    {
        // An attempted calendar that could not prove its actual selected date
        // must not fall back to the earlier visible text and issue a return gate.
        return Ok(false);
    }
    let body = trace.body(trace.frames[frame].after)?;
    let ns = nodes(body, trace.source)?;
    let mut matched = true;
    for field in &search.query.fields {
        let Some(node) = field_node(trace, trace.frames[frame].after, field)? else {
            matched = false;
            continue;
        };
        if !trace.rendered(frame, &node)
            || (field.slot == Slot::OneWay && node["checked"] != true && node["selected"] != true)
        {
            return Ok(false);
        }
        let short_date = dates.iter().any(|d| d.field == *field);
        if !field_node_matches(field, &node, ns, trace.source, short_date) {
            if !field_node_matches(field, &node, ns, trace.source, true) {
                return Ok(false);
            }
            matched = false;
        }
    }
    Ok(matched || query_header(trace, frame, &search.query, None)?)
}
impl TravelExecution {
    pub(super) fn first_counts(&self) -> (u32, u32) {
        self.first.trace.counts()
    }
    pub(super) fn reopened_counts(&self) -> Option<(u32, u32)> {
        self.reopened.as_ref().map(|r| r.trace.counts())
    }
    pub(super) fn should_reopen(&self) -> bool {
        self.reopened.is_none()
            && self.first.flows.len() == self.source.routes.len()
            && self
                .first
                .flows
                .last()
                .is_some_and(|f| f.second.is_some() && f.returned.is_some())
    }
    fn guard_first(&self, transcript: &NativeUiTranscript) -> Result<(), String> {
        self.first.trace.guard(transcript)?;
        need(
            self.first.flows.len() <= self.source.routes.len(),
            "travel route count exceeded its fixed source",
        )?;
        for (index, flow) in self.first.flows.iter().enumerate() {
            need(
                flow.first.query == query(self.source, self.source.routes[index], self.day, false)?,
                "travel original route/date/passenger query was substituted",
            )?;
            search_guard(&self.first.trace, &flow.first)?;
            opened_guard(&self.first.trace, flow)?;
            if let Some(second) = &flow.second {
                need(
                    second.query == query(self.source, self.source.routes[index], self.day, true)?
                        && flow.first.submitted < second.submitted
                        && flow.opened.as_ref().is_some_and(|o| !o.backs.is_empty()),
                    "travel edited query lost its preceding actual selected detail return",
                )?;
                search_guard(&self.first.trace, second)?;
                if let Some((action, frame)) = flow.returned {
                    need(
                        second.submitted < action
                            && self.first.trace.steps[action].op == Operation::Click
                            && self.first.trace.steps[action]
                                .target
                                .as_ref()
                                .is_some_and(|(_, role, _, _)| *role == Role::Back)
                            && action < self.first.trace.frames[frame].before
                            && form_matches(
                                &self.first.trace,
                                &second.query,
                                &Form {
                                    fields: second.form.fields.clone(),
                                    frame,
                                },
                            )?,
                        "travel edited query return state changed",
                    )?;
                }
            } else {
                need(
                    flow.returned.is_none(),
                    "travel return appeared without its actual edited query",
                )?;
            }
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
                    "travel requires two separate finished owned tasks under the same actual Main and full PM subject",
                )?;
                let search = self
                    .first
                    .flows
                    .last()
                    .and_then(|f| f.second.as_ref())
                    .ok_or("travel reopen lacks its actual edited query")?;
                need(
                    r.query_preserved == current_query(&r.trace, r.frame, search, &r.dates)?,
                    "travel separate reopen query comparison changed",
                )
            }
            _ => Err("travel comparison cannot replace an actual retained second task".into()),
        }
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
            "travel reopen outside the original complete first interval",
        )?;
        self.guard_immutable(first, None)?;
        let mut trace = Trace::new(self.source, true);
        let frame = trace.frame(s, i, end)?;
        let search = self
            .first
            .flows
            .last()
            .and_then(|f| f.second.as_ref())
            .ok_or("travel edited source absent")?;
        let dates = observe_reopened_dates(&mut trace, frame, &search.query, s, i, end)?;
        let query_preserved = current_query(&trace, frame, search, &dates)?;
        self.reopened = Some(Reopen {
            trace,
            frame,
            dates,
            query_preserved,
        });
        before(end)
    }
    pub(super) fn completed_gates(&self) -> Vec<&'static str> {
        if self.first.flows.len() != self.source.routes.len() {
            return vec![];
        }
        let mut out = Vec::new();
        let q = match self.source.profile {
            "hotel" => "hotel.query",
            "flight" => "flight.query",
            "train" => "train.query",
            "rental" => "rental.query",
            "travel" => "travel.query",
            _ => return out,
        };
        out.push(q);
        if self
            .first
            .flows
            .iter()
            .all(|f| f.opened.as_ref().is_some_and(|o| o.detail.is_some()))
        {
            out.push(match self.source.profile {
                "hotel" => "hotel.details",
                "flight" => "flight.details",
                "train" => "train.details",
                "rental" => "rental.details",
                _ => "travel.details",
            });
        }
        if self.source.profile != "travel"
            && self
                .first
                .flows
                .iter()
                .all(|f| f.second.is_some() && f.returned.is_some())
            && self.reopened.as_ref().is_some_and(|r| r.query_preserved)
        {
            out.push(match self.source.profile {
                "hotel" => "hotel.return",
                "flight" => "flight.return",
                "train" => "train.return",
                _ => "rental.return",
            });
        }
        out
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        let phase = |trace: &Trace| -> Result<Value, String> {
            Ok(json!({
             "actual_ui_requests":trace.requests(),"actual_input_actions":trace.actions(),"actual_commands":trace.counts().0,
             "retained_reply_bytes":trace.retained_bytes,"actual_scoped_pixels":trace.frames.iter().map(|f|f.pixels.comparison()).collect::<Result<Vec<_>,_>>()?
            }))
        };
        Ok(
            json!({"schema":"droidloom.travel-actual-guest-execution.v1","package":self.source.package,
   "whole_selected_source_sha256":sources::SELECTION_SHA256,"selected_original_apk_count":self.source.apks.len(),
   "source_route_count":self.source.routes.len(),"first":phase(&self.first.trace)?,"stop":self.first.stop,
   "observed_queries":self.first.flows.iter().map(|f|json!({"first":f.first.query,"edited":f.second.as_ref().map(|s|&s.query),"matching_results":f.first.rows.len(),
    "selected_identity_sha256":digest(f.selected.title.as_bytes()),"actual_complete_detail":f.opened.as_ref().and_then(|o|o.detail.as_ref())})).collect::<Vec<_>>(),
   "reopened":self.reopened.as_ref().map(|r|phase(&r.trace)).transpose()?,
   "reopened_own_calendar_observations":self.reopened.as_ref().map(|r|&r.dates),
   "separate_reopen_query_preserved":self.reopened.as_ref().is_some_and(|r|r.query_preserved),
   "completed_business_gates":self.completed_gates(),"account_or_booking_management_qualified":false,
   "purchase_payment_booking_message_or_account_change_attempted":false,
   "private_history_preservation_inferred":false,"runtime_qualified":false,"production_ready":false,"comparison_only":true}),
        )
    }
}
pub(super) fn run(
    s: &mut NativeUiSession<'_, '_>,
    i: &mut NativeApplicationInspector,
    package: &str,
    end: Instant,
) -> Result<TravelExecution, String> {
    before(end)?;
    let source = sources::source(package)?;
    let day = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs()
        / 86_400;
    let mut first = Phase {
        trace: Trace::new(source, false),
        flows: Vec::new(),
        stop: "travel_public_query_not_observed",
    };
    for (index, kind) in source.routes.iter().copied().enumerate() {
        if index > 0 {
            // Ctrip's three required routes remain separate positive observations.
            // Only actual in-App Back controls may return to its category selection.
            let origin = first.trace.dump(s, i, end)?;
            if let Some(action) = back(&mut first.trace, s, i, origin, end)? {
                let _ = action;
            } else {
                first.stop = "multi_route_category_return_unavailable";
                break;
            }
        }
        flow(&mut first, source, kind, day, s, i, end)?;
        if first.flows.len() != index + 1 || first.flows.last().is_none_or(|f| f.returned.is_none())
        {
            break;
        }
    }
    before(end)?;
    Ok(TravelExecution {
        source,
        day,
        first,
        reopened: None,
        original_end: end,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn shortened_dates_cannot_hide_an_explicit_conflicting_year() {
        let date = Field::date(
            Slot::Start,
            Date {
                year: 2027,
                month: 1,
                day: 1,
            },
        );
        for value in [
            "Jan 1, 2026",
            "01/01/2026",
            "1 Jan 2026",
            "2026年1月1日",
            "Jan 1, 2100",
            "Jan 1, 2027 and Jan 1, 2026",
        ] {
            assert!(!date.matches(value, true), "{value}");
        }
        for value in ["Jan 1, 2027", "01/01/2027", "1 Jan 2027", "2027年1月1日"] {
            assert!(date.matches(value, false), "{value}");
            assert!(date.matches(value, true), "{value}");
        }
        assert!(date.matches("Jan 1", true));
        assert!(!date.matches("Jan 1", false));
    }

    #[test]
    fn actual_route_readback_requires_direction_or_matching_role_labels() {
        let a = Field::new(Slot::Origin, "JFK", &["JFK"]);
        let b = Field::new(Slot::Destination, "SFO", &["SFO"]);
        for value in [
            "JFK → SFO",
            "JFK to SFO",
            "From: JFK To: SFO",
            "Origin JFK Destination SFO",
        ] {
            assert!(paired_values_match(value, &a, &b, false), "{value}");
        }
        for value in [
            "SFO → JFK",
            "SFO to JFK",
            "From SFO To JFK",
            "JFK SFO",
            "Origin SFO Destination JFK; JFK → SFO",
            "Origin JFK SFO Destination SFO",
            "Origin JFK Destination SFO JFK",
            "JFK → SFO JFK",
        ] {
            assert!(!paired_values_match(value, &a, &b, false), "{value}");
        }
    }

    #[test]
    fn result_dates_preserve_start_end_roles_and_new_trace_requires_its_own_year() {
        let a = Field::date(
            Slot::Start,
            Date {
                year: 2026,
                month: 12,
                day: 5,
            },
        );
        let b = Field::date(
            Slot::End,
            Date {
                year: 2026,
                month: 12,
                day: 7,
            },
        );
        for value in [
            "Check-in: Dec 5, 2026 Check-out: Dec 7, 2026",
            "Dec 5, 2026 → Dec 7, 2026",
        ] {
            assert!(paired_values_match(value, &a, &b, false), "{value}");
        }
        for value in [
            "Check-in: Dec 7, 2026 Check-out: Dec 5, 2026",
            "Dec 7, 2026 → Dec 5, 2026",
            "Dec 5, 2026 Dec 7, 2026",
            "Check-in: Dec 5, 2027 Check-out: Dec 7, 2027",
            "Check-in: Dec 7, 2026 Dec 5, 2026 Check-out: Dec 7, 2026",
        ] {
            assert!(!paired_values_match(value, &a, &b, true), "{value}");
        }
        let short = "Check-in Dec 5 Check-out Dec 7";
        assert!(paired_values_match(short, &a, &b, true));
        assert!(!paired_values_match(short, &a, &b, false));
    }

    #[test]
    fn public_result_header_cannot_repair_reversed_explicit_roles_with_other_text() {
        let q = query(
            sources::source("com.united.mobile.android").unwrap(),
            Kind::Flight,
            20812,
            false,
        )
        .unwrap();
        let start = q.fields.iter().find(|f| f.slot == Slot::Start).unwrap();
        let positive = format!(
            "Origin JFK Destination SFO Departure date {} 1 adult",
            start.value
        );
        assert!(query_values_match(&positive, &q, false));
        assert!(!query_values_match(
            &positive.replace("Origin JFK Destination SFO", "Origin SFO Destination JFK"),
            &q,
            false
        ));
        let short = format!(
            "Origin JFK Destination SFO Departure date {} 1 adult",
            start.date.unwrap().variants(true)[6]
        );
        assert!(query_values_match(&short, &q, true));
        assert!(!query_values_match(&short, &q, false));
    }

    #[test]
    fn fresh_calendar_comparison_requires_actual_selected_day_and_one_correct_month_year() {
        let date = Date {
            year: 2027,
            month: 1,
            day: 1,
        };
        let heading = json!({"text":"January 2027", "bounds_array":[0, 0, 300, 40]});
        let day =
            json!({"text":"1", "selected":true, "checked":false, "bounds_array":[0, 50, 40, 90]});
        assert!(selected_calendar_nodes(&[&heading, &day], date).unwrap());
        assert!(
            !selected_calendar_nodes(
                &[
                    &json!({"text":"January 2026", "bounds_array":[0, 0, 300, 40]}),
                    &day
                ],
                date
            )
            .unwrap()
        );
        assert!(!selected_calendar_nodes(&[&heading, &json!({"text":"1", "selected":false, "checked":false, "bounds_array":[0,50,40,90]})], date).unwrap());
        assert!(
            !selected_calendar_nodes(
                &[
                    &heading,
                    &json!({"text":"2", "selected":true, "bounds_array":[0,50,40,90]})
                ],
                date
            )
            .unwrap()
        );
        assert!(
            !selected_calendar_nodes(
                &[
                    &heading,
                    &day,
                    &json!({"text":"February 2027", "bounds_array":[0,100,300,140]})
                ],
                date
            )
            .unwrap()
        );
        assert!(
            !selected_calendar_nodes(
                &[
                    &heading,
                    &day,
                    &json!({"text":"January 2035", "bounds_array":[0,100,300,140]})
                ],
                date
            )
            .unwrap()
        );
    }

    #[test]
    fn independent_readonly_calendar_observation_fits_existing_second_session_budget() {
        // Initial frame: two dumps. Per date: open, two calendar dumps,
        // cancel/back, and a fresh restored-field dump. No day selection.
        let requests = 2 + REOPEN_CALENDAR_LIMIT * 5;
        let captures = 1 + REOPEN_CALENDAR_LIMIT;
        let actions = REOPEN_CALENDAR_LIMIT * 2;
        assert!(requests <= SECOND_REQUESTS);
        assert!(captures <= SECOND_CAPTURES);
        assert!(actions as u32 <= reopen_max_actions());
        assert!((requests * 3 + captures * 7) as u32 <= reopen_max_ui_commands());
        assert_eq!((requests, captures, actions), (12, 3, 4));
    }

    #[test]
    fn calendar_handles_leap_years_year_rollover_and_rejects_unbounded_clock() {
        assert_eq!(Date::from_days(0).unwrap().iso(), "1970-01-01");
        assert_eq!(Date::from_days(11016).unwrap().iso(), "2000-02-29");
        assert_eq!(Date::from_days(19782).unwrap().iso(), "2024-02-29");
        assert_eq!(Date::from_days(47481).unwrap().iso(), "2099-12-31");
        assert!(Date::from_days(47482).is_err());
        assert!(
            query(
                sources::source("com.Hyatt.hyt").unwrap(),
                Kind::Hotel,
                u64::MAX,
                true
            )
            .is_err()
        );
        let a = query(
            sources::source("com.Hyatt.hyt").unwrap(),
            Kind::Hotel,
            20812,
            false,
        )
        .unwrap();
        let b = query(
            sources::source("com.Hyatt.hyt").unwrap(),
            Kind::Hotel,
            20812,
            true,
        )
        .unwrap();
        assert_ne!(
            a.fields.iter().find(|f| f.slot == Slot::Start),
            b.fields.iter().find(|f| f.slot == Slot::Start)
        );
    }
    #[test]
    fn exact_field_tokens_reject_wrong_people_dates_and_route_substrings() {
        let q = query(
            sources::source("com.Hyatt.hyt").unwrap(),
            Kind::Hotel,
            19775,
            false,
        )
        .unwrap();
        let people = q.fields.iter().find(|f| f.slot == Slot::People).unwrap();
        let rooms = q.fields.iter().find(|f| f.slot == Slot::Rooms).unwrap();
        assert!(people.matches("Guests: 1 adult", false));
        assert!(!people.matches("11 adults", false));
        assert!(!people.matches("adult 10", false));
        assert!(rooms.matches("1 room", false));
        assert!(!rooms.matches("11 rooms", false));
        let source = sources::source("com.Hyatt.hyt").unwrap();
        let editable = json!({"value":"1","password":false,"editable":true,"resource-id":"adults"});
        assert!(field_node_matches(people, &editable, &[], source, false));
        assert!(!field_node_matches(
            people,
            &json!({"value":"11","password":false,"editable":true,"resource-id":"adults"}),
            &[],
            source,
            false
        ));
        assert!(!field_node_matches(
            people,
            &json!({"value":"1","password":false,"editable":true,"resource-id":"unrelated"}),
            &[],
            source,
            false
        ));
        let date = Field::date(
            Slot::Start,
            Date {
                year: 2027,
                month: 1,
                day: 1,
            },
        );
        assert!(!date.matches("Jan 1", false));
        assert!(date.matches("Jan 1", true));
        assert!(!date.matches("Jan 11", true));
        assert!(!date.matches("2026-01-01", false));
        assert!(term("JFK → SFO", "JFK"));
        assert!(!term("JFKX → SFO", "JFK"));
        assert!(!term("Shanghai", "SHA"));
        assert!(!term("北京南站", "上海虹桥"));
    }
    #[test]
    fn displayed_price_parser_preserves_currency_and_rejects_partial_or_invalid_numbers() {
        assert_eq!(
            amount("US$1,234.50"),
            Some(Amount {
                currency: "USD",
                minor: 123450
            })
        );
        assert_eq!(
            amount("$12.5 / night"),
            Some(Amount {
                currency: "$",
                minor: 1250
            })
        );
        assert_eq!(
            amount("£90.00"),
            Some(Amount {
                currency: "GBP",
                minor: 9000
            })
        );
        assert_eq!(
            amount("¥850"),
            Some(Amount {
                currency: "¥",
                minor: 85000
            })
        );
        assert_eq!(
            amount("850円"),
            Some(Amount {
                currency: "JPY",
                minor: 85000
            })
        );
        assert_ne!(amount("CNY 850"), amount("JPY 850"));
        for v in [
            "$-2",
            "$0",
            "$1,23.45",
            "$12.345",
            "$1.2.3",
            "$1,000.00 pay now",
            "123 USD",
            "$9999999999999999999",
            "$12.",
            "$",
            "£12€",
        ] {
            assert!(amount(v).is_none(), "{v}");
        }
    }
    #[test]
    fn selected_service_identity_rejects_other_carriers_nonservices_and_invalid_clocks() {
        let ua = sources::source("com.united.mobile.android").unwrap();
        assert_eq!(
            service_id("UA 123", Kind::Flight, ua).as_deref(),
            Some("UA123")
        );
        assert!(service_id("NH123", Kind::Flight, ua).is_none());
        assert!(service_id("UA12X", Kind::Flight, ua).is_none());
        assert!(service_id("Available", Kind::Flight, ua).is_none());
        let train = sources::source("com.MobileTicket").unwrap();
        assert_eq!(
            service_id("G101", Kind::Train, train).as_deref(),
            Some("G101")
        );
        assert!(service_id("G101 sold out", Kind::Train, train).is_none());
        assert!(service_id("¥101", Kind::Train, train).is_none());
        assert_eq!(
            clock_labels("25:00 12:60 00:00 23:59"),
            vec!["00:00", "23:59"]
        );
    }
    #[test]
    fn public_queries_cannot_choose_account_payment_message_or_booking_controls() {
        for value in [
            "Book now",
            "Confirm booking",
            "Send message",
            "Send code",
            "Sign in",
            "Cancel booking",
            "立即支付",
            "发送验证码",
            "确认订单",
        ] {
            let n = json!({"text":value,"content-desc":"","password":false});
            for role in [Role::Result, Role::Choice, Role::Input, Role::Submit] {
                assert!(!action_allowed(&n, role), "{value}");
            }
        }
        for hint in ["Passport", "Email", "Phone", "Password", "旅客姓名"] {
            assert!(!action_allowed(
                &json!({"text":"","hint":hint,"password":false}),
                Role::Input
            ));
        }
        assert!(!action_allowed(
            &json!({"text":"Search","password":true}),
            Role::Input
        ));
        assert!(action_allowed(
            &json!({"text":"Search flights","password":false}),
            Role::Submit
        ));
    }
    #[test]
    fn decoded_image_checks_reject_blank_pale_outside_and_unrelated_content() {
        let r = Rect([0, 0, 32, 32]);
        assert!(patch(&vec![255; 32 * 32 * 3], 32, 32, r, r).is_err());
        assert!(patch(&vec![232; 32 * 32 * 3], 32, 32, r, r).is_err());
        let mut rgb = vec![250; 32 * 32 * 3];
        for y in 0..32 {
            for x in 0..16 {
                for c in 0..3 {
                    rgb[3 * (y * 32 + x) + c] = 20;
                }
            }
        }
        let p = patch(&rgb, 32, 32, r, r).unwrap();
        assert!(similar_image(&p, &p));
        let inverse = Patch {
            rgb: p.rgb.iter().map(|v| 255 - *v).collect(),
            sha256: "comparison-only".into(),
        };
        assert!(!similar_image(&p, &inverse));
        assert!(materially_changed(&p, &inverse));
        assert!(patch(&rgb, 32, 32, r, Rect([0, 0, 40, 32])).is_err());
    }
    #[test]
    fn result_titles_exclude_loading_promoted_and_transactional_surfaces() {
        assert!(readable_title("Hyatt Regency London"));
        for value in [
            "Loading hotel",
            "No availability",
            "Sponsored Hotel London",
            "Book now London",
            "Network error",
            "£100",
            "12:00",
        ] {
            assert!(!readable_title(value), "{value}");
        }
    }
    #[test]
    fn fixed_routes_have_separate_finite_business_request_and_retention_bounds() {
        let one = sources::source("com.united.mobile.android").unwrap();
        let all = sources::source("ctrip.android.view").unwrap();
        assert_eq!(request_limit(one, false), 96);
        assert_eq!(request_limit(all, false), 288);
        assert_eq!(capture_limit(one, false), 12);
        assert_eq!(capture_limit(all, false), 36);
        assert_eq!(first_max_extra_ui_commands(one.package), 372);
        assert_eq!(first_max_extra_ui_commands(all.package), 1116);
        assert_eq!(reopen_max_ui_commands(), 100);
        assert_eq!(reopen_max_actions(), 12);
        assert_eq!(second_business_seconds(), 3080);
        assert_eq!(additional_window_seconds(one.package), 14720);
        assert_eq!(additional_window_seconds(all.package), 38000);
        assert_eq!(capture_members_bound(one.package), 32);
        assert_eq!(capture_members_bound(all.package), 80);
        assert_eq!(all.routes, &[Kind::Hotel, Kind::Flight, Kind::Train]);
        assert!(!supports("com.ihg.apps.android"));
        assert!(!supports("com.ubercab"));
    }
}
