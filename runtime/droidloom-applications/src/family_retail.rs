//! Actual guest retail interactions for the five selected retail packages.
//! No constructor consumes comparison JSON, a caller selector, a passed flag,
//! an account, or an order. All replies and pixels originate in the borrowed
//! NativeUiSession. The parent retains both genuine completed transcripts.
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeUiReply, NativeUiSelector, NativeUiSession,
    NativeUiTranscript, RetainedScopedWindowPixels, ScopedWindowPixels,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cell::OnceCell;
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use std::time::Instant;

const FIRST_REQUESTS: usize = 26;
const SECOND_REQUESTS: usize = 12;
const CAPTURES_PER_PHASE: usize = 2;
// A UI request is task-list(15), source-owned helper(70), task-list(15).
// A capture is two task-list(15), two Meta(15), two WM(15), screencap(20).
// The existing local capture allowance is 120s for two decoded images.
pub(super) fn additional_window_seconds() -> u64 {
    (FIRST_REQUESTS + SECOND_REQUESTS) as u64 * (15 + 70 + 15)
        + 4 * (2 * 15 + 2 * 15 + 2 * 15 + 20)
        + 4 * 60
}
pub(super) fn first_max_extra_ui_commands() -> u32 {
    FIRST_REQUESTS as u32 * 3 + 2 * 7
}
pub(super) fn first_max_extra_actions() -> u32 {
    11
}
pub(super) fn reopen_max_ui_commands() -> u32 {
    SECOND_REQUESTS as u32 * 3 + 2 * 7
}
pub(super) fn reopen_max_actions() -> u32 {
    4
}

struct Contract {
    package: &'static str,
    query: &'static str,
    entry_ids: &'static [&'static str],
    input_ids: &'static [&'static str],
    back_ids: &'static [&'static str],
    filter_ids: &'static [&'static str],
    facets: &'static [&'static str],
}
const CONTRACTS: [Contract; 5] = [
    Contract {
        package: "com.amazon.mShop.android.shopping",
        query: "USB C cable",
        entry_ids: &[
            "chrome_search_box",
            "rs_search_entry_container",
            "search_bar",
        ],
        input_ids: &[
            "chrome_search_src_text",
            "rs_search_src_text",
            "search_src_text",
            "search_input_box",
        ],
        back_ids: &[
            "chrome_action_bar_back_icon",
            "rs_search_back_button",
            "back",
        ],
        filter_ids: &[
            "bottom_toolbar_search_refine_filter",
            "rs_filter_icon_header_btn",
            "filter",
        ],
        facets: &["Free Shipping", "Free shipping", "Free Shipping by Amazon"],
    },
    Contract {
        package: "com.bestbuy.android",
        query: "USB C cable",
        entry_ids: &[
            "searchBarContainer",
            "toolbarSearchTextContainer",
            "open_search_bar_text_view_container",
            "search_bar",
        ],
        input_ids: &[
            "open_search_view_edit_text",
            "search_src_text",
            "toolbarSearchText",
        ],
        back_ids: &["searchBarBackIcon"],
        filter_ids: &["filter"],
        facets: &["Free Shipping", "Free shipping"],
    },
    Contract {
        package: "com.jingdong.app.mall",
        query: "USB-C 数据线",
        entry_ids: &[],
        input_ids: &[],
        back_ids: &[],
        filter_ids: &[],
        facets: &["京东物流", "包邮"],
    },
    Contract {
        package: "com.taobao.taobao",
        query: "USB-C 数据线",
        entry_ids: &[
            "ll_action_bar_search_container",
            "ll_search_container",
            "search_bar_container",
            "search_bar",
        ],
        input_ids: &["searchEdit", "et_search_bar", "search_src_text"],
        back_ids: &["iv_detail_back", "nav_back", "back", "btn_back", "go_back"],
        filter_ids: &[],
        facets: &["包邮"],
    },
    Contract {
        package: "com.xunmeng.pinduoduo",
        query: "USB-C 数据线",
        entry_ids: &[],
        input_ids: &[],
        back_ids: &[],
        filter_ids: &[],
        facets: &["包邮"],
    },
];
pub(super) fn supports(package: &str) -> bool {
    CONTRACTS.iter().any(|c| c.package == package)
}
fn contract(package: &str) -> Result<&'static Contract, String> {
    CONTRACTS
        .iter()
        .find(|c| c.package == package)
        .ok_or_else(|| "retail package is outside the fixed five".into())
}
fn need(ok: bool, why: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(why.into())
    }
}
fn before(end: Instant) -> Result<(), String> {
    need(
        Instant::now() < end,
        "retail original case deadline expired",
    )
}
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn text<'a>(node: &'a Value, key: &str) -> &'a str {
    node.get(key).and_then(Value::as_str).unwrap_or("")
}
fn norm(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}
fn same_title(a: &str, b: &str) -> bool {
    let a = norm(a);
    let b = norm(b);
    a == b
        || a.strip_suffix('…')
            .filter(|p| p.chars().count() >= 24)
            .is_some_and(|p| b.starts_with(p))
}
fn product_title(value: &str, c: &Contract) -> bool {
    let n = norm(value);
    (8..=512).contains(&value.len())
        && n != norm(c.query)
        && n.contains("usb")
        && (n.contains("cable") || n.contains("数据线"))
        && ![
            "search for ",
            "搜索",
            "sign in",
            "checkout",
            "立即购买",
            "立即支付",
        ]
        .iter()
        .any(|x| n.starts_with(x))
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct Rect([i64; 4]);
impl Rect {
    fn parse(v: &Value) -> Result<Self, String> {
        let a = v
            .as_array()
            .filter(|a| a.len() == 4)
            .ok_or("retail rectangle absent")?;
        let n = a
            .iter()
            .map(Value::as_i64)
            .collect::<Option<Vec<_>>>()
            .ok_or("retail rectangle noninteger")?;
        need(
            n.iter().all(|n| (0..=8192).contains(n)) && n[2] > n[0] && n[3] > n[1],
            "retail rectangle bound",
        )?;
        Ok(Self([n[0], n[1], n[2], n[3]]))
    }
    fn area(self) -> i64 {
        (self.0[2] - self.0[0]) * (self.0[3] - self.0[1])
    }
    fn contains(self, b: Self) -> bool {
        self.0[0] <= b.0[0] && self.0[1] <= b.0[1] && self.0[2] >= b.0[2] && self.0[3] >= b.0[3]
    }
}
fn nodes<'a>(body: &'a Value, c: &Contract) -> Result<&'a [Value], String> {
    let ctx = &body["window_context"];
    need(
        body["ok"] == true
            && ctx["root"]["package"] == c.package
            && ctx["selected_window"]["root"]["package"] == c.package
            && ctx["snapshot_complete"] == true
            && ctx["truncated"] == false
            && ctx["selected_window"]["focused"] == true
            && ctx["selected_window"]["display_id"] == 0,
        "retail requires the complete actual selected package tree",
    )?;
    let ns = body["nodes"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 2000)
        .ok_or("retail actual nodes absent")?;
    Ok(ns)
}
fn usable(node: &Value, c: &Contract) -> bool {
    node["package"] == c.package
        && node["visible"] == true
        && node["enabled"] == true
        && node["password"] == false
        && node["source"] == "native_accessibility"
        && Rect::parse(&node["bounds_array"]).is_ok()
}
fn source_id(node: &Value, c: &Contract, ids: &[&str]) -> bool {
    text(node, "resource-id")
        .strip_prefix(c.package)
        .and_then(|s| s.strip_prefix(":id/"))
        .is_some_and(|s| ids.contains(&s))
}
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct Money {
    currency: &'static str,
    minor: u64,
}
fn money(s: &str) -> Option<Money> {
    let s = s.trim();
    let (currency, n) = if let Some(n) = s.strip_prefix('$') {
        ("USD", n)
    } else if let Some(n) = s.strip_prefix('¥').or_else(|| s.strip_prefix('￥')) {
        ("CNY", n)
    } else {
        return None;
    };
    let n = n.trim();
    if n.is_empty()
        || n.len() > 18
        || n.chars()
            .any(|c| !c.is_ascii_digit() && c != '.' && c != ',')
    {
        return None;
    }
    let mut it = n.split('.');
    let integer = it.next()?;
    if integer.contains(',') {
        let groups = integer.split(',').collect::<Vec<_>>();
        if groups.first().is_none_or(|g| g.is_empty() || g.len() > 3)
            || groups.iter().skip(1).any(|g| g.len() != 3)
        {
            return None;
        }
    }
    let whole = integer.replace(',', "");
    let frac = it.next();
    if it.next().is_some() || whole.is_empty() || !whole.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let cents = match frac {
        None => 0,
        Some(s) if s.len() == 1 && s.bytes().all(|b| b.is_ascii_digit()) => {
            s.parse::<u64>().ok()? * 10
        }
        Some(s) if s.len() == 2 && s.bytes().all(|b| b.is_ascii_digit()) => {
            s.parse::<u64>().ok()?
        }
        _ => return None,
    };
    let minor = whole
        .parse::<u64>()
        .ok()?
        .checked_mul(100)?
        .checked_add(cents)?;
    (minor > 0 && minor <= 100_000_000).then_some(Money { currency, minor })
}
#[derive(Clone, Debug)]
struct ImageSample {
    rgb: Vec<u8>,
    spread: u8,
    varied: usize,
    sha256: String,
}
fn sample(
    rgb: &[u8],
    width: usize,
    height: usize,
    window: Rect,
    rect: Rect,
) -> Result<ImageSample, String> {
    need(
        window.contains(rect)
            && width == (window.0[2] - window.0[0]) as usize
            && height == (window.0[3] - window.0[1]) as usize
            && rgb.len()
                == width
                    .checked_mul(height)
                    .and_then(|n| n.checked_mul(3))
                    .ok_or("retail RGB overflow")?,
        "retail image crop is outside the actual scoped pixels",
    )?;
    need(
        rect.0[2] - rect.0[0] >= 48 && rect.0[3] - rect.0[1] >= 48,
        "retail product image is too small",
    )?;
    let mut out = Vec::with_capacity(768);
    for y in 0..16 {
        for x in 0..16 {
            let sx = (rect.0[0] - window.0[0]) as usize
                + (2 * x + 1) * (rect.0[2] - rect.0[0]) as usize / 32;
            let sy = (rect.0[1] - window.0[1]) as usize
                + (2 * y + 1) * (rect.0[3] - rect.0[1]) as usize / 32;
            out.extend_from_slice(&rgb[3 * (sy * width + sx)..3 * (sy * width + sx) + 3]);
        }
    }
    let low = *out.iter().min().ok_or("retail image empty")?;
    let high = *out.iter().max().unwrap();
    let varied = out
        .chunks_exact(3)
        .filter(|p| p.iter().any(|v| *v < 220))
        .count();
    need(
        high - low >= 48 && varied >= 20 && out.chunks_exact(3).any(|p| p.iter().any(|v| *v < 160)),
        "retail image is blank, pale, or lacks actual product contrast",
    )?;
    Ok(ImageSample {
        sha256: digest(&out),
        rgb: out,
        spread: high - low,
        varied,
    })
}
fn image_matches(a: &ImageSample, b: &ImageSample) -> bool {
    a.rgb.len() == 768
        && b.rgb.len() == 768
        && a.spread >= 48
        && b.spread >= 48
        && a.varied >= 20
        && b.varied >= 20
        && a.rgb
            .iter()
            .zip(&b.rgb)
            .map(|(a, b)| a.abs_diff(*b) as u64)
            .sum::<u64>()
            <= 768 * 24
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
enum Role {
    Entry,
    Input,
    Submit,
    Product,
    Back,
    Filter,
    Facet,
    Apply,
}
fn role_matches(n: &Value, c: &Contract, role: Role) -> bool {
    if !usable(n, c) {
        return false;
    }
    let t = text(n, "text");
    let d = text(n, "content-desc");
    let label = |labels: &[&str]| labels.contains(&t) || labels.contains(&d);
    match role {
        Role::Entry => {
            source_id(n, c, c.entry_ids)
                || label(&["Search Amazon", "Search Best Buy", "Search", "搜索"])
        }
        Role::Input => {
            n["editable"] == true && (source_id(n, c, c.input_ids) || !text(n, "class").is_empty())
        }
        Role::Submit => {
            n["editable"] == false
                && (source_id(
                    n,
                    c,
                    &[
                        "search_go_btn",
                        "search_button",
                        "searchBarSearchIcon",
                        "btn_search",
                        "searchbtn",
                    ],
                ) || label(&["Search", "搜索", "提交查询"]))
        }
        Role::Product => n["editable"] == false && product_title(t, c),
        Role::Back => {
            n["editable"] == false
                && (source_id(n, c, c.back_ids)
                    || label(&["Back", "Navigate up", "返回", "向上导航"]))
        }
        Role::Filter => {
            n["editable"] == false
                && (source_id(n, c, c.filter_ids) || label(&["Filter", "Filters", "筛选"]))
        }
        Role::Facet => {
            label(c.facets)
                && ["CheckBox", "RadioButton", "CompoundButton", "Switch"]
                    .iter()
                    .any(|v| text(n, "class").ends_with(v))
        }
        Role::Apply => {
            n["editable"] == false
                && (label(&[
                    "Apply",
                    "Show results",
                    "See results",
                    "确定",
                    "查看结果",
                    "查看商品",
                ]) || [t, d].iter().any(|s| {
                    s.strip_prefix("Show ")
                        .and_then(|s| s.strip_suffix(" results"))
                        .is_some_and(|s| {
                            !s.is_empty()
                                && s.len() <= 12
                                && s.bytes().all(|b| b.is_ascii_digit() || b == b',')
                        })
                }))
        }
    }
}
fn input_context(trace: &Trace, dump: usize, c: &Contract, n: &Value) -> bool {
    source_id(n, c, c.input_ids)
        || ["hint", "content-desc"].iter().any(|key| {
            let v = norm(text(n, key));
            v.contains("search") || v.contains("搜索")
        })
        || dump
            .checked_sub(1)
            .and_then(|i| trace.steps.get(i))
            .is_some_and(|s| {
                s.operation == Operation::Click
                    && s.target
                        .as_ref()
                        .is_some_and(|(_, role, _)| *role == Role::Entry)
            })
}
struct Target {
    selector: NativeUiSelector,
    node: Value,
    dump: usize,
    role: Role,
}
fn target(
    trace: &Trace,
    dump: usize,
    c: &Contract,
    role: Role,
    exact: Option<&str>,
) -> Result<Option<Target>, String> {
    let ns = nodes(trace.body(dump)?, c)?;
    let eligible = |n: &&Value| {
        role_matches(n, c, role)
            && exact.is_none_or(|v| text(n, "text") == v || text(n, "content-desc") == v)
            && (role != Role::Input || input_context(trace, dump, c, n))
    };
    let mut matches: Vec<_> = ns.iter().filter(eligible).collect();
    let preferred = match role {
        Role::Entry => c.entry_ids,
        Role::Input => c.input_ids,
        Role::Back => c.back_ids,
        Role::Filter => c.filter_ids,
        Role::Submit => &[
            "search_go_btn",
            "search_button",
            "searchBarSearchIcon",
            "btn_search",
            "searchbtn",
        ],
        _ => &[],
    };
    for id in preferred {
        let exact_id: Vec<_> = matches
            .iter()
            .copied()
            .filter(|n| source_id(n, c, &[*id]))
            .collect();
        if exact_id.len() > 1 {
            return Ok(None);
        }
        if exact_id.len() == 1 {
            matches = exact_id;
            break;
        }
    }
    if matches.len() != 1 {
        return Ok(None);
    }
    let node = matches[0];
    for (field, make) in [
        (
            "resource-id",
            NativeUiSelector::resource_id as fn(&str) -> Result<NativeUiSelector, _>,
        ),
        ("text", NativeUiSelector::exact_text),
        ("content-desc", NativeUiSelector::description),
    ] {
        let value = text(node, field);
        if !value.is_empty() && ns.iter().filter(|n| text(n, field) == value).count() == 1 {
            return Ok(Some(Target {
                selector: make(value).map_err(|e| e.to_string())?.enabled(),
                node: node.clone(),
                dump,
                role,
            }));
        }
    }
    if role == Role::Input
        && ns
            .iter()
            .filter(|n| usable(n, c) && n["editable"] == true)
            .count()
            == 1
    {
        return Ok(Some(Target {
            selector: NativeUiSelector::editable().enabled(),
            node: node.clone(),
            dump,
            role,
        }));
    }
    Ok(None)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
enum Operation {
    Dump,
    Click,
    SetText,
}
struct Step {
    operation: Operation,
    reply: NativeUiReply,
    target: Option<(usize, Role, Value)>,
}
struct Frame {
    before: usize,
    after: usize,
    pixels: RetainedScopedWindowPixels,
    images: BTreeMap<Rect, ImageSample>,
}
struct Trace {
    steps: Vec<Step>,
    frames: Vec<Frame>,
    request_limit: usize,
    action_limit: u32,
}
impl Trace {
    fn new(second: bool) -> Self {
        Self {
            steps: Vec::new(),
            frames: Vec::new(),
            request_limit: if second {
                SECOND_REQUESTS
            } else {
                FIRST_REQUESTS
            },
            action_limit: if second {
                reopen_max_actions()
            } else {
                first_max_extra_actions()
            },
        }
    }
    fn requests(&self) -> usize {
        self.steps
            .iter()
            .map(|s| {
                if s.operation == Operation::SetText {
                    2
                } else {
                    1
                }
            })
            .sum()
    }
    fn actions(&self) -> u32 {
        self.steps
            .iter()
            .filter(|s| s.operation != Operation::Dump)
            .count() as u32
    }
    fn reserve(&self, n: usize, action: bool, end: Instant) -> Result<(), String> {
        before(end)?;
        need(
            self.requests() + n <= self.request_limit
                && self.actions() + u32::from(action) <= self.action_limit,
            "retail fixed source operation budget exceeded",
        )
    }
    fn body(&self, i: usize) -> Result<&Value, String> {
        self.steps
            .get(i)
            .map(|s| s.reply.body())
            .ok_or_else(|| "retail retained reply index differs".into())
    }
    fn dump(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &NativeApplicationInspector,
        end: Instant,
    ) -> Result<usize, String> {
        self.reserve(1, false, end)?;
        let reply = s.dump(i)?;
        let n = self.steps.len();
        self.steps.push(Step {
            operation: Operation::Dump,
            reply,
            target: None,
        });
        Ok(n)
    }
    fn click(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &NativeApplicationInspector,
        t: Target,
        end: Instant,
    ) -> Result<usize, String> {
        self.reserve(1, true, end)?;
        let reply = s.click(i, t.selector)?;
        let n = self.steps.len();
        for k in [
            "resource-id",
            "text",
            "content-desc",
            "window_id",
            "bounds_array",
        ] {
            need(
                reply.body()["target"][k] == t.node[k],
                "retail actual click target differs from the observed source choice",
            )?;
        }
        self.steps.push(Step {
            operation: Operation::Click,
            reply,
            target: Some((t.dump, t.role, t.node)),
        });
        Ok(n)
    }
    fn set_text(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &NativeApplicationInspector,
        t: Target,
        q: &str,
        end: Instant,
    ) -> Result<usize, String> {
        self.reserve(2, true, end)?;
        let reply = s.set_text(i, t.selector, q)?;
        let n = self.steps.len();
        self.steps.push(Step {
            operation: Operation::SetText,
            reply,
            target: Some((t.dump, t.role, t.node)),
        });
        Ok(n)
    }
    fn frame(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &NativeApplicationInspector,
        c: &Contract,
        end: Instant,
    ) -> Result<usize, String> {
        need(
            self.frames.len() < CAPTURES_PER_PHASE,
            "retail fixed scoped capture count exceeded",
        )?;
        self.reserve(2, false, end)?;
        let first = self.dump(s, i, end)?;
        let pixels = s.scoped_window_pixels(i)?;
        let after = self.dump(s, i, end)?;
        let a = self.body(first)?;
        let z = self.body(after)?;
        let ns = nodes(a, c)?;
        nodes(z, c)?;
        let window = Rect::parse(&a["window_context"]["selected_window"]["bounds"])?;
        need(
            a["window_context"]["selected_window"]["window_id"]
                == z["window_context"]["selected_window"]["window_id"]
                && a["window_context"]["selected_window"]["bounds"]
                    == z["window_context"]["selected_window"]["bounds"],
            "retail tree changed window during the actual scoped capture",
        )?;
        let cmp = pixels.comparison()?;
        let w = &cmp["window"]["bounds"];
        need(
            window
                == Rect([
                    w["left"].as_i64().ok_or("pixel left")?,
                    w["top"].as_i64().ok_or("pixel top")?,
                    w["right"].as_i64().ok_or("pixel right")?,
                    w["bottom"].as_i64().ok_or("pixel bottom")?,
                ]),
            "retail UI bounds do not match the actual scoped screenshot",
        )?;
        let mut images = BTreeMap::new();
        for n in ns.iter().filter(|n| usable(n, c) && image_node(n)) {
            if let Ok(rect) = Rect::parse(&n["bounds_array"]) {
                if window.contains(rect) && image_present(z, c, rect)? {
                    if let Ok(v) = sample(
                        pixels.rgb(),
                        pixels.width() as usize,
                        pixels.height() as usize,
                        window,
                        rect,
                    ) {
                        images.insert(rect, v);
                    }
                }
            }
        }
        need(
            images.len() <= 128,
            "retail actual image candidate bound exceeded",
        )?;
        let index = self.frames.len();
        self.frames.push(Frame {
            before: first,
            after,
            pixels: pixels.into_retained()?,
            images,
        });
        Ok(index)
    }
    fn guard(&self, c: &Contract, transcript: &NativeUiTranscript) -> Result<(), String> {
        need(
            self.requests() <= self.request_limit
                && self.actions() <= self.action_limit
                && self.frames.len() <= 2,
            "retail retained operation shape exceeds its source budget",
        )?;
        for (idx, s) in self.steps.iter().enumerate() {
            need(s.reply.body()["ok"] == true, "retail retained reply failed")?;
            if let Some((origin, role, n)) = &s.target {
                need(
                    *origin < idx
                        && self.steps[*origin].operation == Operation::Dump
                        && nodes(self.body(*origin)?, c)?.iter().any(|x| x == n)
                        && role_matches(n, c, *role)
                        && (*role != Role::Input || input_context(self, *origin, c, n)),
                    "retail mutation is detached from its actual observed source selector",
                )?;
                need(
                    s.reply.body()["performed"]
                        == if s.operation == Operation::SetText {
                            "set-text"
                        } else {
                            "click"
                        },
                    "retail retained mutation kind changed",
                )?;
            } else {
                need(
                    s.operation == Operation::Dump,
                    "retail mutation lacks actual source target",
                )?;
            }
        }
        for f in &self.frames {
            f.pixels.require_transcript(transcript)?;
            nodes(self.body(f.before)?, c)?;
            nodes(self.body(f.after)?, c)?;
        }
        Ok(())
    }
}
fn image_node(n: &Value) -> bool {
    text(n, "class").ends_with("ImageView")
        || [
            "product_image",
            "imgProduct",
            "product_information_image",
            "product_list_image_container_view",
        ]
        .iter()
        .any(|id| text(n, "resource-id").ends_with(&format!(":id/{id}")))
}
fn image_present(body: &Value, c: &Contract, rect: Rect) -> Result<bool, String> {
    Ok(nodes(body, c)?
        .iter()
        .any(|n| usable(n, c) && image_node(n) && Rect::parse(&n["bounds_array"]) == Ok(rect)))
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct Product {
    title: String,
    price: Money,
    title_bounds: Rect,
    card: Rect,
    image: Rect,
}
fn products(body: &Value, c: &Contract) -> Result<Vec<Product>, String> {
    let ns = nodes(body, c)?;
    let titles: Vec<_> = ns
        .iter()
        .filter(|n| usable(n, c) && n["editable"] == false && product_title(text(n, "text"), c))
        .collect();
    let mut out = Vec::new();
    for t in &titles {
        let title = text(t, "text");
        if ns.iter().filter(|n| text(n, "text") == title).count() != 1 {
            continue;
        }
        let tr = Rect::parse(&t["bounds_array"])?;
        let mut cards: Vec<_> = ns
            .iter()
            .filter(|n| usable(n, c) && n["clickable"] == true)
            .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
            .filter(|r| r.contains(tr))
            .collect();
        cards.sort_by_key(|r| r.area());
        cards.dedup();
        for card in cards {
            if titles
                .iter()
                .filter(|n| Rect::parse(&n["bounds_array"]).is_ok_and(|r| card.contains(r)))
                .count()
                != 1
            {
                continue;
            }
            let inside: Vec<_> = ns
                .iter()
                .filter(|n| {
                    usable(n, c) && Rect::parse(&n["bounds_array"]).is_ok_and(|r| card.contains(r))
                })
                .collect();
            let prices: BTreeSet<_> = inside
                .iter()
                .filter_map(|n| money(text(n, "text")))
                .collect();
            let mut images: Vec<_> = inside
                .iter()
                .filter(|n| image_node(n))
                .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
                .filter(|r| r.0[2] - r.0[0] >= 48 && r.0[3] - r.0[1] >= 48)
                .collect();
            images.sort_by_key(|r| std::cmp::Reverse(r.area()));
            images.dedup();
            if prices.len() != 1
                || images.is_empty()
                || images.get(1).is_some_and(|r| r.area() == images[0].area())
            {
                continue;
            }
            out.push(Product {
                title: title.into(),
                price: prices.into_iter().next().unwrap(),
                title_bounds: tr,
                card,
                image: images[0],
            });
            break;
        }
    }
    out.sort_by_key(|p| (p.card.0[1], p.card.0[0]));
    out.dedup_by(|a, b| a.title == b.title);
    Ok(out)
}
fn query_visible(body: &Value, c: &Contract) -> Result<bool, String> {
    Ok(nodes(body, c)?.iter().any(|n| {
        usable(n, c)
            && n["editable"] == true
            && n["showing-hint"] == false
            && (text(n, "value") == c.query || text(n, "text") == c.query)
    }))
}
fn populated(trace: &Trace, frame: usize, c: &Contract) -> Result<Option<Vec<Product>>, String> {
    let f = trace
        .frames
        .get(frame)
        .ok_or("retail actual result frame absent")?;
    let a = trace.body(f.before)?;
    let b = trace.body(f.after)?;
    if !query_visible(a, c)? || !query_visible(b, c)? {
        return Ok(None);
    }
    let pa = products(a, c)?;
    let pb = products(b, c)?;
    if pa.len() < 2 || pa != pb || pa.iter().any(|p| !f.images.contains_key(&p.image)) {
        return Ok(None);
    }
    Ok(Some(pa))
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct Detail {
    title: String,
    price: Money,
    variants: Vec<String>,
    availability: String,
    image: Rect,
}
fn detail(body: &Value, c: &Contract, chosen: &Product) -> Result<Option<Detail>, String> {
    let ns = nodes(body, c)?;
    let titles: Vec<_> = ns
        .iter()
        .filter(|n| {
            usable(n, c) && n["editable"] == false && same_title(&chosen.title, text(n, "text"))
        })
        .collect();
    if titles.len() != 1 {
        return Ok(None);
    }
    if !ns
        .iter()
        .any(|n| usable(n, c) && money(text(n, "text")).as_ref() == Some(&chosen.price))
    {
        return Ok(None);
    }
    let mut variants: BTreeSet<String> = BTreeSet::new();
    let mut available = BTreeSet::new();
    let mut images = Vec::new();
    for n in ns.iter().filter(|n| usable(n, c)) {
        let t = text(n, "text").trim();
        let prefix = [
            "Color:",
            "Colour:",
            "Size:",
            "Style:",
            "Length:",
            "颜色：",
            "规格：",
            "已选：",
            "颜色:",
            "规格:",
            "已选:",
        ]
        .iter()
        .any(|p| t.strip_prefix(p).is_some_and(|v| !v.trim().is_empty()));
        let id = text(n, "resource-id").to_lowercase();
        if t.len() <= 160
            && !t.is_empty()
            && (prefix
                || ((n["selected"] == true || n["checked"] == true)
                    && ["variant", "sku", "color", "size", "capacity"]
                        .iter()
                        .any(|k| id.contains(k))))
        {
            variants.insert(t.into());
        }
        if ["in stock", "in stock.", "现货", "有货", "库存充足"].contains(&norm(t).as_str())
        {
            available.insert(t.to_owned());
        }
        if image_node(n) {
            if let Ok(r) = Rect::parse(&n["bounds_array"]) {
                if r.0[2] - r.0[0] >= 48 && r.0[3] - r.0[1] >= 48 {
                    images.push(r);
                }
            }
        }
    }
    images.sort_by_key(|r| std::cmp::Reverse(r.area()));
    images.dedup();
    if variants.is_empty()
        || variants.len() > 8
        || available.len() != 1
        || images.is_empty()
        || images.get(1).is_some_and(|r| r.area() == images[0].area())
    {
        return Ok(None);
    }
    Ok(Some(Detail {
        title: text(titles[0], "text").into(),
        price: chosen.price.clone(),
        variants: variants.into_iter().collect(),
        availability: available.into_iter().next().unwrap(),
        image: images[0],
    }))
}
struct SearchFlow {
    initial_dump: usize,
    typed: Option<(usize, usize, usize)>,
    frame: usize,
    original_input_sha256: Option<String>,
}
struct DetailFlow {
    selected: Product,
    clicked: usize,
    frame: usize,
    facts: Detail,
}
struct FilterFlow {
    label: String,
    before: usize,
    checked: usize,
    applied: usize,
    restore_before: usize,
    restored: usize,
    returned: usize,
}
struct Phase {
    trace: Trace,
    search: Option<SearchFlow>,
    detail: Option<DetailFlow>,
    back: Option<usize>,
    filter: Option<FilterFlow>,
    stop: &'static str,
}
impl Phase {
    fn new(second: bool) -> Self {
        Self {
            trace: Trace::new(second),
            search: None,
            detail: None,
            back: None,
            filter: None,
            stop: "not_started",
        }
    }
}
struct FinishedReopen {
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    first_task: u32,
    second_task: u32,
    first_journal: PathBuf,
    second_journal: PathBuf,
}
pub(super) struct RetailExecution {
    contract: &'static Contract,
    first: Phase,
    second: Option<Phase>,
    original_end: Instant,
    finished_reopen: OnceCell<FinishedReopen>,
}
fn empty_input(n: &Value) -> bool {
    if n["showing-hint"] == true {
        let hint = text(n, "hint");
        (text(n, "value").is_empty() || text(n, "value") == hint)
            && (text(n, "text").is_empty() || text(n, "text") == hint)
    } else {
        text(n, "value").is_empty() && text(n, "text").is_empty()
    }
}
fn execute_search(
    p: &mut Phase,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    c: &Contract,
    end: Instant,
    retained: bool,
) -> Result<(), String> {
    let initial = p.trace.dump(s, i, end)?;
    if retained && query_visible(p.trace.body(initial)?, c)? {
        let f = p.trace.frame(s, i, c, end)?;
        let observed = populated(&p.trace, f, c)?;
        let initial_products = products(p.trace.body(initial)?, c)?;
        if observed.as_ref().is_some_and(|v| v == &initial_products) {
            p.search = Some(SearchFlow {
                initial_dump: initial,
                typed: None,
                frame: f,
                original_input_sha256: None,
            });
            p.stop = "search_observed_before_new_input";
        } else {
            p.stop = "reopened_query_results_were_not_complete_in_first_dump";
        }
        return Ok(());
    }
    let mut form = initial;
    if target(&p.trace, form, c, Role::Input, None)?.is_none() {
        let Some(t) = target(&p.trace, form, c, Role::Entry, None)? else {
            p.stop = "unique_visible_search_entry_absent";
            return Ok(());
        };
        p.trace.click(s, i, t, end)?;
        form = p.trace.dump(s, i, end)?;
    }
    let Some(input) = target(&p.trace, form, c, Role::Input, None)? else {
        p.stop = "unique_nonpassword_search_field_absent";
        return Ok(());
    };
    if !empty_input(&input.node) {
        p.stop = "existing_nonempty_search_input_preserved";
        return Ok(());
    }
    // A single editable field is accepted only inside an actual search page:
    // a fixed unique Search submit must already be present, never a login form.
    if target(&p.trace, form, c, Role::Submit, None)?.is_none() {
        p.stop = "source_search_submit_absent";
        return Ok(());
    }
    let original = digest(
        serde_json::to_vec(&input.node)
            .map_err(|e| e.to_string())?
            .as_slice(),
    );
    let typed = p.trace.set_text(s, i, input, c.query, end)?;
    let readback = p.trace.dump(s, i, end)?;
    if !query_visible(p.trace.body(readback)?, c)? {
        p.stop = "actual_query_readback_differs";
        return Ok(());
    }
    let Some(submit) = target(&p.trace, readback, c, Role::Submit, None)? else {
        p.stop = "unique_search_submission_absent";
        return Ok(());
    };
    let sent = p.trace.click(s, i, submit, end)?;
    let f = p.trace.frame(s, i, c, end)?;
    if populated(&p.trace, f, c)?.is_none() {
        p.stop = "matching_populated_results_or_rendered_images_absent";
        return Ok(());
    }
    p.search = Some(SearchFlow {
        initial_dump: initial,
        typed: Some((typed, readback, sent)),
        frame: f,
        original_input_sha256: Some(original),
    });
    p.stop = "search_observed";
    Ok(())
}
fn execute_detail(
    p: &mut Phase,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    c: &Contract,
    end: Instant,
    expected: Option<&DetailFlow>,
) -> Result<(), String> {
    let search = p
        .search
        .as_ref()
        .ok_or("retail detail requires the actual search")?;
    let list = populated(&p.trace, search.frame, c)?
        .ok_or("retail original search no longer validates")?;
    let chosen = if let Some(expected) = expected {
        match list.into_iter().find(|v| {
            same_title(&expected.selected.title, &v.title) && v.price == expected.selected.price
        }) {
            Some(v) => v,
            None => {
                p.stop = "same_product_absent_after_reopen";
                return Ok(());
            }
        }
    } else {
        list.into_iter()
            .next()
            .ok_or("retail actual result selection absent")?
    };
    let from = p.trace.frames[search.frame].after;
    let Some(t) = target(&p.trace, from, c, Role::Product, Some(&chosen.title))? else {
        p.stop = "unique_actual_product_control_absent";
        return Ok(());
    };
    let clicked = p.trace.click(s, i, t, end)?;
    let actual = Rect::parse(&p.trace.body(clicked)?["actual_target"]["bounds_array"])?;
    need(
        chosen.card.contains(actual) && actual.contains(chosen.title_bounds),
        "retail actual product click escaped its observed card",
    )?;
    let frame = p.trace.frame(s, i, c, end)?;
    let f = &p.trace.frames[frame];
    let a = detail(p.trace.body(f.before)?, c, &chosen)?;
    let b = detail(p.trace.body(f.after)?, c, &chosen)?;
    let Some(facts) = a.filter(|a| Some(a) == b.as_ref()) else {
        p.stop = "selected_product_variant_price_or_availability_unverified";
        return Ok(());
    };
    let selection = &p.trace.frames[search.frame];
    let matched = selection
        .images
        .get(&chosen.image)
        .zip(f.images.get(&facts.image))
        .is_some_and(|(a, b)| image_matches(a, b));
    if !matched {
        p.stop = "selected_product_image_did_not_match_rendered_detail";
        return Ok(());
    }
    if expected.is_some_and(|v| {
        !same_title(&v.facts.title, &facts.title)
            || v.facts.price != facts.price
            || v.facts.variants != facts.variants
            || v.facts.availability != facts.availability
    }) {
        p.stop = "detail_state_changed_after_reopen";
        return Ok(());
    }
    p.detail = Some(DetailFlow {
        selected: chosen,
        clicked,
        frame,
        facts,
    });
    p.stop = "detail_observed";
    Ok(())
}
fn checked(body: &Value, c: &Contract, label: &str) -> Result<Option<bool>, String> {
    let v: Vec<_> = nodes(body, c)?
        .iter()
        .filter(|n| {
            role_matches(n, c, Role::Facet)
                && (text(n, "text") == label || text(n, "content-desc") == label)
        })
        .collect();
    Ok(if v.len() == 1 {
        v[0]["checked"].as_bool()
    } else {
        None
    })
}
fn facet_results(body: &Value, c: &Contract, label: &str) -> Result<bool, String> {
    if !query_visible(body, c)? {
        return Ok(false);
    }
    let ns = nodes(body, c)?;
    let list = products(body, c)?;
    Ok(list.len() >= 2
        && list.iter().all(|p| {
            ns.iter().any(|n| {
                usable(n, c)
                    && (text(n, "text") == label || text(n, "content-desc") == label)
                    && Rect::parse(&n["bounds_array"]).is_ok_and(|r| p.card.contains(r))
            })
        }))
}
fn execute_return_filter(
    p: &mut Phase,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    c: &Contract,
    end: Instant,
) -> Result<(), String> {
    let detail = p
        .detail
        .as_ref()
        .ok_or("retail back requires the actual detail")?;
    let from = p.trace.frames[detail.frame].after;
    let Some(back) = target(&p.trace, from, c, Role::Back, None)? else {
        p.stop = "unique_visible_detail_back_absent";
        return Ok(());
    };
    p.trace.click(s, i, back, end)?;
    let returned = p.trace.dump(s, i, end)?;
    if !query_visible(p.trace.body(returned)?, c)?
        || !products(p.trace.body(returned)?, c)?.iter().any(|v| {
            same_title(&detail.selected.title, &v.title) && v.price == detail.selected.price
        })
    {
        p.stop = "actual_back_did_not_restore_same_query_product";
        return Ok(());
    }
    p.back = Some(returned);
    let Some(open) = target(&p.trace, returned, c, Role::Filter, None)? else {
        p.stop = "unique_visible_filters_absent";
        return Ok(());
    };
    p.trace.click(s, i, open, end)?;
    let initial = p.trace.dump(s, i, end)?;
    let mut choice = None;
    for label in c.facets {
        if checked(p.trace.body(initial)?, c, label)? == Some(false) {
            if let Some(t) = target(&p.trace, initial, c, Role::Facet, Some(label))? {
                choice = Some(((*label).to_owned(), t));
                break;
            }
        }
    }
    let Some((label, toggle)) = choice else {
        p.stop = "safe_unselected_source_facet_absent";
        return Ok(());
    };
    if target(&p.trace, initial, c, Role::Apply, None)?.is_none() {
        p.stop = "unique_filter_apply_absent";
        return Ok(());
    }
    p.trace.click(s, i, toggle, end)?;
    let on = p.trace.dump(s, i, end)?;
    need(
        checked(p.trace.body(on)?, c, &label)? == Some(true),
        "retail facet mutation did not produce its actual checked readback",
    )?;
    let apply = target(&p.trace, on, c, Role::Apply, None)?
        .ok_or("retail apply disappeared after actual facet change")?;
    p.trace.click(s, i, apply, end)?;
    let applied = p.trace.dump(s, i, end)?;
    let effect = facet_results(p.trace.body(applied)?, c, &label)?;
    // Restore the exact previously unchecked source facet even when its result
    // semantics did not qualify. A lost/ambiguous state remains Err, not partial.
    let open = target(&p.trace, applied, c, Role::Filter, None)?
        .ok_or("retail cannot safely reopen the changed filter")?;
    p.trace.click(s, i, open, end)?;
    let restore_before = p.trace.dump(s, i, end)?;
    need(
        checked(p.trace.body(restore_before)?, c, &label)? == Some(true),
        "retail changed facet lost actual custody",
    )?;
    let toggle = target(&p.trace, restore_before, c, Role::Facet, Some(&label))?
        .ok_or("retail exact facet restore control absent")?;
    p.trace.click(s, i, toggle, end)?;
    let off = p.trace.dump(s, i, end)?;
    need(
        checked(p.trace.body(off)?, c, &label)? == Some(false),
        "retail original facet was not restored",
    )?;
    let apply = target(&p.trace, off, c, Role::Apply, None)?
        .ok_or("retail exact restored filter apply absent")?;
    p.trace.click(s, i, apply, end)?;
    let final_results = p.trace.dump(s, i, end)?;
    need(
        query_visible(p.trace.body(final_results)?, c)?
            && products(p.trace.body(final_results)?, c)?.iter().any(|v| {
                same_title(&detail.selected.title, &v.title) && v.price == detail.selected.price
            }),
        "retail restored filter did not restore the actual query/product state",
    )?;
    if effect {
        p.filter = Some(FilterFlow {
            label,
            before: initial,
            checked: on,
            applied,
            restore_before,
            restored: off,
            returned: final_results,
        });
        p.stop = "first_navigation_observed";
    } else {
        p.stop = "facet_effect_unqualified_original_filter_restored";
    }
    Ok(())
}
pub(super) fn run(
    s: &mut NativeUiSession<'_, '_>,
    i: &mut NativeApplicationInspector,
    package: &str,
    original_end: Instant,
) -> Result<RetailExecution, String> {
    before(original_end)?;
    let c = contract(package)?;
    let mut first = Phase::new(false);
    execute_search(&mut first, s, i, c, original_end, false)?;
    if first.search.is_some() {
        execute_detail(&mut first, s, i, c, original_end, None)?;
    }
    if first.detail.is_some() {
        execute_return_filter(&mut first, s, i, c, original_end)?;
    }
    before(original_end)?;
    Ok(RetailExecution {
        contract: c,
        first,
        second: None,
        original_end,
        finished_reopen: OnceCell::new(),
    })
}
impl RetailExecution {
    pub(super) fn first_counts(&self) -> (u32, u32) {
        (
            (3 * self.first.trace.requests() + 7 * self.first.trace.frames.len()) as u32,
            self.first.trace.actions(),
        )
    }
    pub(super) fn reopened_counts(&self) -> Option<(u32, u32)> {
        self.second.as_ref().map(|p| {
            (
                (3 * p.trace.requests() + 7 * p.trace.frames.len()) as u32,
                p.trace.actions(),
            )
        })
    }
    pub(super) fn should_reopen(&self) -> bool {
        self.first.detail.is_some() && self.first.back.is_some() && self.second.is_none()
    }
    pub(super) fn observe_reopen(
        &mut self,
        s: &mut NativeUiSession<'_, '_>,
        i: &mut NativeApplicationInspector,
        first: &NativeUiTranscript,
        original_end: Instant,
    ) -> Result<(), String> {
        need(
            original_end == self.original_end && self.should_reopen(),
            "retail reopen must retain the same original deadline and first actual flow",
        )?;
        self.guard_immutable(first, None)?;
        before(original_end)?;
        let mut next = Phase::new(true);
        execute_search(&mut next, s, i, self.contract, original_end, true)?;
        if next.search.is_some() {
            execute_detail(
                &mut next,
                s,
                i,
                self.contract,
                original_end,
                self.first.detail.as_ref(),
            )?;
        }
        if let (Some(a), Some(b)) = (&self.first.detail, &next.detail) {
            let same = self.first.trace.frames[a.frame]
                .images
                .get(&a.facts.image)
                .zip(next.trace.frames[b.frame].images.get(&b.facts.image))
                .is_some_and(|(a, b)| image_matches(a, b));
            if !same {
                next.detail = None;
                next.stop = "reopened_product_image_state_differs";
            }
        }
        self.second = Some(next);
        before(original_end)
    }
    fn guard_phase(&self, p: &Phase, t: &NativeUiTranscript, second: bool) -> Result<(), String> {
        let c = self.contract;
        p.trace.guard(c, t)?;
        need(
            t.engine().application().package == c.package,
            "retail completed transcript belongs to a different package",
        )?;
        if let Some(search) = &p.search {
            need(
                populated(&p.trace, search.frame, c)?.is_some(),
                "retail retained search semantics changed",
            )?;
            if let Some((typed, readback, sent)) = search.typed {
                need(
                    p.trace.steps[typed].operation == Operation::SetText
                        && p.trace.body(typed)?["characters"].as_u64()
                            == Some(c.query.chars().count() as u64)
                        && p.trace.body(typed)?["readback_verified"] == true
                        && query_visible(p.trace.body(readback)?, c)?
                        && p.trace.steps[sent].operation == Operation::Click,
                    "retail search lacks its actual set, readback, and submission",
                )?;
            } else {
                let frame = &p.trace.frames[search.frame];
                need(second&&self.first.search.is_some()&&search.initial_dump==0
                    && p.trace.steps[search.initial_dump..=frame.after].iter().all(|s|s.operation==Operation::Dump)
                    && query_visible(p.trace.body(search.initial_dump)?,c)?
                    && populated(&p.trace,search.frame,c)?.as_ref()==Some(&products(p.trace.body(search.initial_dump)?,c)?),
                    "retail preserved state must exist in the first actual reopen dump before new business input")?;
            }
        }
        if let Some(detail_flow) = &p.detail {
            let search = p
                .search
                .as_ref()
                .ok_or("retail retained detail lacks actual search")?;
            let f = &p.trace.frames[detail_flow.frame];
            let selection = &p.trace.frames[search.frame];
            need(
                p.trace.steps[detail_flow.clicked].operation == Operation::Click
                    && detail(p.trace.body(f.before)?, c, &detail_flow.selected)?.as_ref()
                        == Some(&detail_flow.facts)
                    && detail(p.trace.body(f.after)?, c, &detail_flow.selected)?.as_ref()
                        == Some(&detail_flow.facts)
                    && selection
                        .images
                        .get(&detail_flow.selected.image)
                        .zip(f.images.get(&detail_flow.facts.image))
                        .is_some_and(|(a, b)| image_matches(a, b)),
                "retail retained detail no longer matches selected product and actual image",
            )?;
        }
        if let Some(back) = p.back {
            need(
                p.detail.is_some() && query_visible(p.trace.body(back)?, c)?,
                "retail back evidence lacks actual detail/query",
            )?;
        }
        if let Some(f) = &p.filter {
            need(
                p.back.is_some()
                    && checked(p.trace.body(f.before)?, c, &f.label)? == Some(false)
                    && checked(p.trace.body(f.checked)?, c, &f.label)? == Some(true)
                    && facet_results(p.trace.body(f.applied)?, c, &f.label)?
                    && checked(p.trace.body(f.restore_before)?, c, &f.label)? == Some(true)
                    && checked(p.trace.body(f.restored)?, c, &f.label)? == Some(false)
                    && query_visible(p.trace.body(f.returned)?, c)?,
                "retail filter effect/restoration bookends differ",
            )?;
        }
        Ok(())
    }
    pub(super) fn guard_immutable(
        &self,
        first: &NativeUiTranscript,
        reopened: Option<&NativeUiTranscript>,
    ) -> Result<(), String> {
        self.guard_phase(&self.first, first, false)?;
        match (&self.second,reopened) {
            (None,None)=>Ok(()),
            (Some(second),Some(next))=>{
                self.guard_phase(second,next,true)?;
                need(first.task()!=next.task()&&first.journal()!=next.journal()
                    && first.engine().application()==next.engine().application()
                    && first.engine().facts().main==next.engine().facts().main,
                    "retail reopen must be a different finished task under the same complete Main/application")?;
                if let (Some(a),Some(b))=(&self.first.detail,&second.detail) {
                    need(same_title(&a.facts.title,&b.facts.title)&&a.facts.price==b.facts.price
                        &&a.facts.variants==b.facts.variants&&a.facts.availability==b.facts.availability
                        &&self.first.trace.frames[a.frame].images.get(&a.facts.image)
                            .zip(second.trace.frames[b.frame].images.get(&b.facts.image)).is_some_and(|(a,b)|image_matches(a,b)),
                        "retail independently reopened detail differs")?;
                    if second.search.as_ref().is_some_and(|s|s.typed.is_none()) && self.first.back.is_some() {
                        let binding=FinishedReopen{main:first.engine().facts().main.clone(),application:first.engine().application().clone(),
                            first_task:first.task(),second_task:next.task(),first_journal:first.journal().into(),second_journal:next.journal().into()};
                        if let Some(old)=self.finished_reopen.get(){
                            need(old.main==binding.main&&old.application==binding.application&&old.first_task==binding.first_task
                                &&old.second_task==binding.second_task&&old.first_journal==binding.first_journal&&old.second_journal==binding.second_journal,
                                "retail finished reopen binding changed")?;
                        }else{
                            before(self.original_end)?;
                            self.finished_reopen.set(binding).map_err(|_|"retail finished reopen sealed twice")?;
                        }
                    }
                }
                Ok(())
            },
            _=>Err("retail retained second observations require their real completed second transcript".into()),
        }
    }
    pub(super) fn preserves_reopen_state(&self) -> bool {
        self.finished_reopen.get().is_some()
    }
    pub(super) fn completed_gates(&self) -> &[&'static str] {
        if self.preserves_reopen_state() && self.first.filter.is_some() && self.first.back.is_some()
        {
            &["retail.search", "retail.detail", "retail.navigation"]
        } else if self.first.detail.is_some() {
            &["retail.search", "retail.detail"]
        } else if self.first.search.is_some() {
            &["retail.search"]
        } else {
            &[]
        }
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        let phase = |p: &Phase| -> Result<Value, String> {
            let pixels = p
                .trace
                .frames
                .iter()
                .map(|f| f.pixels.comparison())
                .collect::<Result<Vec<_>, _>>()?;
            Ok(
                json!({"stop":p.stop,"actual_ui_requests":p.trace.requests(),"actual_input_actions":p.trace.actions(),
                "actual_commands":3*p.trace.requests()+7*p.trace.frames.len(),"scoped_pixels":pixels,
                "original_input_sha256":p.search.as_ref().and_then(|s|s.original_input_sha256.as_ref()),
                "detail":p.detail.as_ref().map(|d|json!({"title_sha256":digest(d.facts.title.as_bytes()),"price":d.facts.price,
                    "variants":d.facts.variants,"availability":d.facts.availability})),
                "filter":p.filter.as_ref().map(|f|json!({"label":f.label,"before_checked":false,"observed_checked":true,"restored_checked":false})),
                "input_or_account_contents_disclosed":false}),
            )
        };
        Ok(
            json!({"schema":"droidloom.retail-actual-guest-execution.v1","package":self.contract.package,"fixed_query":self.contract.query,
            "first":phase(&self.first)?,"reopened":self.second.as_ref().map(phase).transpose()?,
            "completed_business_gates":self.completed_gates(),"actual_reopen_state_preserved":self.preserves_reopen_state(),
            "query_reentered_after_reopen":self.second.as_ref().and_then(|p|p.search.as_ref()).is_some_and(|s|s.typed.is_some()),
            "account_gate":"pending_authorized_test_account",
            "purchases_or_cart_mutation_attempted":false,"existing_nonempty_input_overwritten":false,
            "saved_search_history_erased":false,"account_or_data_preservation_inferred":false,
            "comparison_only":true,"runtime_qualified":false,"production_ready":false}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retail_source_scope_and_derived_command_budget_are_finite() {
        assert_eq!(CONTRACTS.len(), 5);
        assert_eq!(additional_window_seconds(), 4480);
        assert_eq!(first_max_extra_ui_commands(), 92);
        assert_eq!(reopen_max_ui_commands(), 50);
        assert!(!supports("com.ubercab"));
        assert!(!supports("com.sankuai.meituan.takeoutnew"));
        assert!(!supports("com.bestbuy.android.evil"));
        assert!(!supports(""));
        for c in &CONTRACTS {
            assert!(supports(c.package));
            assert!(product_title(&format!("Premium {} 2 pack", c.query), c));
            assert!(!product_title(c.query, c));
        }
    }
    #[test]
    fn retail_prices_do_not_accept_labels_ranges_or_free_text() {
        assert_eq!(
            money("$12.34"),
            Some(Money {
                currency: "USD",
                minor: 1234
            })
        );
        assert_eq!(
            money("￥ 18.9"),
            Some(Money {
                currency: "CNY",
                minor: 1890
            })
        );
        for s in [
            "12.34",
            "$0",
            "$-1",
            "$1–$2",
            "$1.999",
            "$12 each",
            "Pay $12",
            "shipping $12",
            "$1.2.3",
            "$1,,2",
            "$1,23",
        ] {
            assert!(money(s).is_none(), "{s}");
        }
    }
    #[test]
    fn retail_image_matching_rejects_blank_pale_and_different_products() {
        let r = Rect([0, 0, 64, 64]);
        let blank = vec![255; 64 * 64 * 3];
        assert!(sample(&blank, 64, 64, r, r).is_err());
        let mut a = blank.clone();
        let mut b = blank.clone();
        for y in 0..64 {
            for x in 0..64 {
                if x < 32 {
                    a[3 * (y * 64 + x)..3 * (y * 64 + x) + 3].fill(40);
                }
                if x >= 32 {
                    b[3 * (y * 64 + x)..3 * (y * 64 + x) + 3].fill(40);
                }
            }
        }
        let aa = sample(&a, 64, 64, r, r).unwrap();
        let bb = sample(&b, 64, 64, r, r).unwrap();
        assert!(image_matches(&aa, &aa));
        assert!(!image_matches(&aa, &bb));
        assert_eq!(aa.sha256.len(), 64);
        assert!(sample(&a, 64, 64, r, Rect([0, 0, 65, 64])).is_err());
    }
    #[test]
    fn retail_existing_input_is_never_overwritten_as_a_hint() {
        assert!(empty_input(
            &json!({"showing-hint":false,"value":"","text":""})
        ));
        assert!(empty_input(
            &json!({"showing-hint":true,"value":null,"text":"Search","hint":"Search"})
        ));
        assert!(!empty_input(
            &json!({"showing-hint":true,"value":"private previous query","text":"Search","hint":"Search"})
        ));
        assert!(!empty_input(
            &json!({"showing-hint":false,"value":"previous query","text":"previous query"})
        ));
    }
    #[test]
    fn retail_product_query_and_owned_crop_reject_decoys() {
        let c = &CONTRACTS[0];
        assert!(product_title("USB C cable braided 2m", c));
        for s in [
            "USB C cable",
            "Search for USB C cable",
            "Sign in",
            "Checkout",
            "USB charger",
        ] {
            assert!(!product_title(s, c), "{s}");
        }
        assert!(Rect::parse(&json!([0, 0, 50, 50])).is_ok());
        assert!(Rect::parse(&json!([-1, 0, 50, 50])).is_err());
        assert!(Rect::parse(&json!([0, 0, 0, 50])).is_err());
        assert!(Rect::parse(&json!([0, 0, 9000, 50])).is_err());
        assert!(!same_title("USB C cable 1m", "USB C cable 2m"));
    }
}
