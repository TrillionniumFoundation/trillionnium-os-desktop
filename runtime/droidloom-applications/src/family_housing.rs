//! Readonly public housing flows for two exact selected original applications.
//! Actual native replies, complete PM APKs, decoded listing/detail pixels and
//! both genuine finished histories remain held. No JSON observation factory.
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, NativeUiReply, NativeUiSelector, NativeUiSession,
    NativeUiTranscript, RetainedScopedWindowPixels,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cell::OnceCell;
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use std::time::Instant;

const SOURCE_SELECTION_SHA256: &str =
    "4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0";
const SOURCE_READBACK_SHA256: &str =
    "24cbfcb6dcac907da0bcf563c8183ddce20e9bcb876274f1b2d955c1235b89f8";
const FIRST_REQUESTS: usize = 48;
const SECOND_REQUESTS: usize = 24;
const FIRST_CAPTURES: usize = 5;
const SECOND_CAPTURES: usize = 3;
const RETAINED_REPLY_BYTES: usize = 64 * 1024 * 1024;
pub(super) fn additional_window_seconds() -> u64 {
    (FIRST_REQUESTS + SECOND_REQUESTS) as u64 * 100
        + (FIRST_CAPTURES + SECOND_CAPTURES) as u64 * 170
}
pub(super) fn second_business_seconds() -> u64 {
    SECOND_REQUESTS as u64 * 100 + SECOND_CAPTURES as u64 * 170
}
pub(super) fn first_max_extra_ui_commands() -> u32 {
    FIRST_REQUESTS as u32 * 3 + FIRST_CAPTURES as u32 * 7
}
pub(super) fn first_max_extra_actions() -> u32 {
    17
}
pub(super) fn reopen_max_ui_commands() -> u32 {
    SECOND_REQUESTS as u32 * 3 + SECOND_CAPTURES as u32 * 7
}
pub(super) fn reopen_max_actions() -> u32 {
    10
}

struct ApkSource {
    bytes: u64,
    sha256: &'static str,
}
struct Contract {
    package: &'static str,
    version_code: u64,
    apks: &'static [ApkSource],
    query: &'static str,
    city: Option<&'static str>,
    entry_ids: &'static [&'static str],
    input_ids: &'static [&'static str],
    back_ids: &'static [&'static str],
    filter_ids: &'static [&'static str],
    apply_ids: &'static [&'static str],
}
const CONTRACTS: [Contract; 2] = [
    Contract {
        package: "com.lianjia.beike",
        version_code: 3_068_010,
        apks: &[ApkSource {
            bytes: 230_624_085,
            sha256: "2338cf0c67ab23896bf4d5042314c6a94fb1710c250cb079247205a335417f74",
        }],
        query: "望京",
        city: Some("北京"),
        entry_ids: &[
            "card_home_title_bar_two_ll_search_container",
            "card_home_condition_new_ll_search_container",
            "buy_searchbar",
            "bmui_search_capsule_view",
        ],
        input_ids: &[
            "search_title_et_search_bar",
            "search_title_et_search_bar2",
            "search_edittext",
            "search_et",
            "search_src_text",
            "et_search",
            "et_search_keyword",
            "et_search_sug",
            "et_search_location",
        ],
        back_ids: &[
            "search_result_back",
            "sh_list_search_nav_back",
            "activity_deal_house_detail_v2_iv_title_bar_back",
        ],
        filter_ids: &[
            "filter_more",
            "filter",
            "filters",
            "filter_type_guide_anchor",
        ],
        apply_ids: &[
            "card_common_filter_tv_confirm",
            "card_filter_ll_confirm_container",
        ],
    },
    Contract {
        package: "com.zillow.android.streeteasy",
        version_code: 23_117,
        apks: &[
            ApkSource {
                bytes: 48_197_513,
                sha256: "a43e08e564790ec2f24f93d123316e72ebf1b1b228260fc897d46c5695a3e928",
            },
            ApkSource {
                bytes: 3_588_647,
                sha256: "e3860fcb2406ca0c9814691a258349a7d2806c536a6af092520cfc3f7e0ef48e",
            },
            ApkSource {
                bytes: 114_898,
                sha256: "24deb36c71f4ba14a50abacde641787bf0ac52f26d54f99bdf38e1f3a16bbf3c",
            },
            ApkSource {
                bytes: 348_603,
                sha256: "7dedb608dc3843c38366cdf9a70c81c933f357797e02468c62fee31f10081dbe",
            },
        ],
        query: "Park Slope",
        city: None,
        entry_ids: &[
            "locationBar",
            "location_bar_layout",
            "neighborhoodSearch",
            "searchEntry",
            "open_search_bar_text_view_container",
        ],
        input_ids: &["open_search_view_edit_text", "search_src_text"],
        back_ids: &[],
        filter_ids: &["filter", "filters", "modifyFilters", "headerBeds"],
        apply_ids: &["searchCta", "search_button"],
    },
];
pub(super) fn supports(package: &str) -> bool {
    CONTRACTS.iter().any(|c| c.package == package)
}
fn contract(package: &str) -> Result<&'static Contract, String> {
    CONTRACTS
        .iter()
        .find(|c| c.package == package)
        .ok_or_else(|| "housing package outside the two source contracts".into())
}
pub(super) fn require_application(a: &ApplicationInspection) -> Result<(), String> {
    let c = contract(&a.package)?;
    need(
        a.user == 0
            && (10_000..20_000).contains(&a.uid)
            && a.version_code == c.version_code
            && a.apks.len() == c.apks.len()
            && a.apks.iter().filter(|p| p.name == "base.apk").count() == 1
            && a.apks
                .iter()
                .map(|p| &p.name)
                .collect::<BTreeSet<_>>()
                .len()
                == a.apks.len()
            && c.apks.iter().all(|p| {
                a.apks
                    .iter()
                    .filter(|v| v.bytes == p.bytes && v.sha256 == p.sha256)
                    .count()
                    == 1
            }),
        "housing source facts need actual complete PM versions and every original signed APK byte",
    )
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
        "housing original case deadline expired",
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
    norm(a) == norm(b)
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct Rect([i64; 4]);
impl Rect {
    fn parse(v: &Value) -> Result<Self, String> {
        let a = v
            .as_array()
            .filter(|a| a.len() == 4)
            .ok_or("housing rectangle absent")?;
        let n = a
            .iter()
            .map(Value::as_i64)
            .collect::<Option<Vec<_>>>()
            .ok_or("housing rectangle noninteger")?;
        need(
            n.iter().all(|n| (0..=8192).contains(n)) && n[2] > n[0] && n[3] > n[1],
            "housing rectangle bound",
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
        "housing requires the complete actual selected package tree",
    )?;
    let ns = body["nodes"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 2000)
        .ok_or("housing actual nodes absent")?;
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
    period: &'static str,
}
fn decimal(value: &str, scale: u64) -> Option<u64> {
    let value = value.trim();
    if value.is_empty()
        || value.len() > 24
        || value
            .chars()
            .any(|c| !c.is_ascii_digit() && c != '.' && c != ',')
    {
        return None;
    }
    let mut pieces = value.split('.');
    let first = pieces.next()?;
    let fraction = pieces.next();
    if pieces.next().is_some() {
        return None;
    }
    let groups = first.split(',').collect::<Vec<_>>();
    if groups.len() > 1
        && (groups[0].is_empty()
            || groups[0].len() > 3
            || groups.iter().skip(1).any(|g| g.len() != 3))
    {
        return None;
    }
    let whole = first.replace(',', "");
    if whole.is_empty() || !whole.bytes().all(|c| c.is_ascii_digit()) {
        return None;
    }
    let base = whole.parse::<u64>().ok()?.checked_mul(scale)?;
    let add = if let Some(f) = fraction {
        if f.is_empty() || f.len() > 4 || !f.bytes().all(|c| c.is_ascii_digit()) {
            return None;
        }
        let divisor = 10u64.checked_pow(f.len() as u32)?;
        let n = f.parse::<u64>().ok()?.checked_mul(scale)?;
        if n % divisor != 0 {
            return None;
        }
        n / divisor
    } else {
        0
    };
    base.checked_add(add)
}
fn money(value: &str) -> Option<Money> {
    let raw = value.trim().strip_prefix("Price ").unwrap_or(value.trim());
    let cny_monthly = raw.ends_with("元/月");
    let (period, raw) = if let Some(s) = raw
        .strip_suffix("/mo")
        .or_else(|| raw.strip_suffix("/month"))
        .or_else(|| raw.strip_suffix(" per month"))
        .or_else(|| raw.strip_suffix("元/月"))
    {
        ("monthly", s.trim())
    } else {
        ("total", raw)
    };
    let (currency, number, scale) = if let Some(s) = raw.strip_prefix('$') {
        ("USD", s, 100)
    } else if let Some(s) = raw.strip_suffix("万元").or_else(|| raw.strip_suffix('万')) {
        ("CNY", s, 1_000_000)
    } else if let Some(s) = raw.strip_prefix('¥').or_else(|| raw.strip_prefix('￥')) {
        ("CNY", s, 100)
    } else if cny_monthly {
        ("CNY", raw, 100)
    } else {
        return None;
    };
    let minor = decimal(number, scale)?;
    (minor > 0 && minor <= 10_000_000_000_000).then_some(Money {
        currency,
        minor,
        period,
    })
}
fn unsafe_control(value: &str) -> bool {
    let n = norm(value);
    [
        "contact",
        "message",
        "send",
        "schedule",
        "tour",
        "save search",
        "share",
        "apply now",
        "request",
        "subscribe",
        "sign in",
        "log in",
        "sign up",
        "咨询",
        "联系",
        "预约",
        "拨打",
        "打电话",
        "发送",
        "发布",
        "支付",
        "收藏",
        "关注",
        "验证码",
        "登录",
        "注册",
    ]
    .iter()
    .any(|v| n.contains(v))
}
fn address(value: &str, c: &Contract) -> bool {
    let v = norm(value);
    if !(5..=320).contains(&value.len())
        || unsafe_control(value)
        || value.chars().any(char::is_control)
    {
        return false;
    }
    if c.city.is_some() {
        [
            "小区", "公寓", "大厦", "花园", "西园", "东园", "南园", "北园", "家园", "新城", "号院",
            "广场", "路", "街", "里", "府", "湾",
        ]
        .iter()
        .any(|s| v.contains(s))
    } else {
        v.chars().next().is_some_and(|c| c.is_ascii_digit())
            && v.split_whitespace().any(|token| {
                [
                    "street",
                    "st",
                    "avenue",
                    "ave",
                    "place",
                    "pl",
                    "road",
                    "rd",
                    "boulevard",
                    "blvd",
                    "lane",
                    "ln",
                    "court",
                    "ct",
                    "drive",
                    "dr",
                    "way",
                ]
                .contains(&token.trim_end_matches('.'))
            })
    }
}
fn beds(value: &str) -> Option<u8> {
    let s = norm(value).replace(' ', "");
    let rest = s.strip_prefix(|c: char| c.is_ascii_digit())?;
    let n = s.chars().next()?.to_digit(10)? as u8;
    if n > 8 {
        return None;
    }
    (rest.starts_with('室') || rest.starts_with("bed") || rest.starts_with("br")).then_some(n)
}
fn area(value: &str) -> Option<(u64, &'static str)> {
    let s = norm(value).replace(' ', "");
    let (n, u) = if let Some(v) = s
        .strip_suffix("㎡")
        .or_else(|| s.strip_suffix("m²"))
        .or_else(|| s.strip_suffix("平方米"))
    {
        (v, "m2")
    } else if let Some(v) = s
        .strip_suffix("sqft")
        .or_else(|| s.strip_suffix("ft²"))
        .or_else(|| s.strip_suffix("squarefeet"))
    {
        (v, "ft2")
    } else {
        return None;
    };
    let v = decimal(n, 100)?;
    (100..=100_000_000).contains(&v).then_some((v, u))
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
                    .ok_or("housing RGB overflow")?,
        "housing image crop is outside the actual scoped pixels",
    )?;
    need(
        rect.0[2] - rect.0[0] >= 48 && rect.0[3] - rect.0[1] >= 48,
        "housing listing image is too small",
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
    let low = *out.iter().min().ok_or("housing image empty")?;
    let high = *out.iter().max().unwrap();
    let varied = out
        .chunks_exact(3)
        .filter(|p| p.iter().any(|v| *v < 220))
        .count();
    need(
        high - low >= 48 && varied >= 20 && out.chunks_exact(3).any(|p| p.iter().any(|v| *v < 160)),
        "housing image is blank, pale, or lacks actual listing contrast",
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
    City,
    CityChoice,
    Mode,
    Entry,
    Input,
    Submit,
    Suggestion,
    Listing,
    Back,
    Filter,
    Facet,
    Apply,
}
fn option_number(n: &Value, c: &Contract) -> Option<i8> {
    let label = norm(text(n, "text"));
    let label = if label.is_empty() {
        norm(text(n, "content-desc"))
    } else {
        label
    };
    if ["不限", "any", "any beds", "any bedrooms", "all"].contains(&label.as_str()) {
        return Some(-1);
    }
    if ["studio", "开间"].contains(&label.as_str()) {
        return Some(0);
    }
    for k in 1..=5 {
        if [
            format!("{k}室"),
            format!("{k}居"),
            format!("{k} bed"),
            format!("{k} beds"),
            format!("{k} bedroom"),
            format!("{k} bedrooms"),
            format!("{k}+"),
        ]
        .contains(&label)
        {
            return Some(k);
        }
    }
    for (id, k) in [
        ("oneBed", 1),
        ("twoBed", 2),
        ("twoBeds", 2),
        ("threeBed", 3),
        ("threeBeds", 3),
        ("fourOrMoreBeds", 4),
        ("fourPlusBed", 4),
    ] {
        if source_id(n, c, &[id]) && label == k.to_string() {
            return Some(k);
        }
    }
    None
}
fn selected(n: &Value) -> Option<bool> {
    if n["checkable"] == true
        || ["CheckBox", "RadioButton", "CompoundButton", "Switch"]
            .iter()
            .any(|v| text(n, "class").ends_with(v))
    {
        n["checked"].as_bool()
    } else {
        n["selected"].as_bool()
    }
}
fn filter_context(body: &Value, c: &Contract) -> Result<bool, String> {
    Ok(nodes(body, c)?
        .iter()
        .any(|n| usable(n, c) && ["户型", "Bedrooms", "Beds", "卧室"].contains(&text(n, "text"))))
}
fn role_matches(n: &Value, c: &Contract, role: Role) -> bool {
    if !usable(n, c) {
        return false;
    }
    let t = text(n, "text");
    let d = text(n, "content-desc");
    let label = |ls: &[&str]| ls.contains(&t) || ls.contains(&d);
    if role != Role::Input && (unsafe_control(t) || unsafe_control(d)) {
        return false;
    }
    match role {
        Role::City => source_id(
            n,
            c,
            &[
                "card_home_title_bar_one_ll_switch_city",
                "card_home_title_bar_one_tv_city",
                "city_tv",
                "city_view",
                "city",
            ],
        ),
        Role::CityChoice => c.city.is_some_and(|city| t == city) && n["editable"] == false,
        Role::Mode => {
            if c.city.is_some() {
                label(&["二手房"])
            } else {
                source_id(n, c, &["searchTypeBuy"])
            }
        }
        Role::Entry => {
            source_id(n, c, c.entry_ids) || label(&["Search", "搜索", "搜索小区", "Neighborhoods"])
        }
        Role::Input => {
            n["editable"] == true
                && (source_id(n, c, c.input_ids) || text(n, "class").ends_with("EditText"))
        }
        Role::Submit => {
            n["editable"] == false
                && (source_id(
                    n,
                    c,
                    &[
                        "search_title_tv_search_btn",
                        "tv_search_submit",
                        "btn_search",
                        "search_go_btn",
                        "search_button",
                        "searchCta",
                    ],
                ) || label(&["搜索", "Search", "Show listings", "查看房源"]))
        }
        Role::Suggestion => n["editable"] == false && norm(t) == norm(c.query),
        Role::Listing => n["editable"] == false && address(t, c),
        Role::Back => {
            n["editable"] == false
                && (source_id(n, c, c.back_ids)
                    || label(&["返回", "Back", "Navigate up", "向上导航"]))
        }
        Role::Filter => {
            n["editable"] == false
                && (source_id(n, c, c.filter_ids)
                    || label(&["Filters", "Filter", "筛选", "户型", "Beds", "Bedrooms"]))
        }
        Role::Facet => {
            n["editable"] == false && option_number(n, c).is_some() && selected(n).is_some()
        }
        Role::Apply => {
            n["editable"] == false
                && (source_id(n, c, c.apply_ids)
                    || label(&[
                        "确定",
                        "查看房源",
                        "Show listings",
                        "See listings",
                        "Search",
                        "Apply",
                        "Show results",
                    ])
                    || [t, d].iter().any(|s| {
                        s.strip_prefix("Show ")
                            .and_then(|s| s.strip_suffix(" listings"))
                            .is_some_and(|n| {
                                !n.is_empty()
                                    && n.len() < 12
                                    && n.bytes().all(|b| b.is_ascii_digit() || b == b',')
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
    let body = trace.body(dump)?;
    let ns = nodes(body, c)?;
    if role == Role::Facet && !filter_context(body, c)? {
        return Ok(None);
    }
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
    written: Option<String>,
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
    capture_limit: usize,
}
impl Trace {
    fn new(second: bool) -> Self {
        Self {
            capture_limit: if second {
                SECOND_CAPTURES
            } else {
                FIRST_CAPTURES
            },
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
    fn counts(&self) -> (u32, u32) {
        (
            (3 * self.requests() + 7 * self.frames.len()) as u32,
            self.actions(),
        )
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
            self.steps
                .iter()
                .map(|s| s.reply.body().to_string().len())
                .sum::<usize>()
                <= RETAINED_REPLY_BYTES,
            "housing retained reply body cap exceeded",
        )?;
        need(
            self.requests() + n <= self.request_limit
                && self.actions() + u32::from(action) <= self.action_limit,
            "housing fixed source operation budget exceeded",
        )
    }
    fn body(&self, i: usize) -> Result<&Value, String> {
        self.steps
            .get(i)
            .map(|s| s.reply.body())
            .ok_or_else(|| "housing retained reply index differs".into())
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
            written: None,
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
                "housing actual click target differs from the observed source choice",
            )?;
        }
        self.steps.push(Step {
            operation: Operation::Click,
            reply,
            target: Some((t.dump, t.role, t.node)),
            written: None,
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
            written: Some(q.into()),
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
            self.frames.len() < self.capture_limit,
            "housing fixed scoped capture count exceeded",
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
            "housing tree changed window during the actual scoped capture",
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
            "housing UI bounds do not match the actual scoped screenshot",
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
            "housing actual image candidate bound exceeded",
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
                && self.frames.len() <= self.capture_limit,
            "housing retained operation shape exceeds its source budget",
        )?;
        need(
            self.steps
                .iter()
                .map(|s| s.reply.body().to_string().len())
                .sum::<usize>()
                <= RETAINED_REPLY_BYTES,
            "housing retained reply body cap exceeded",
        )?;
        for (idx, s) in self.steps.iter().enumerate() {
            need(
                s.reply.body()["ok"] == true,
                "housing retained reply failed",
            )?;
            if let Some((origin, role, n)) = &s.target {
                need(
                    *origin < idx
                        && self.steps[*origin].operation == Operation::Dump
                        && nodes(self.body(*origin)?, c)?.iter().any(|x| x == n)
                        && role_matches(n, c, *role)
                        && (*role != Role::Input || input_context(self, *origin, c, n))
                        && (*role != Role::Facet || filter_context(self.body(*origin)?, c)?),
                    "housing mutation is detached from its actual observed source selector",
                )?;
                need(
                    s.written.is_some() == (s.operation == Operation::SetText)
                        && s.written.as_deref().is_none_or(|value| value == c.query),
                    "housing action changed its fixed public query payload",
                )?;
                if s.operation == Operation::Click {
                    need(
                        [
                            "resource-id",
                            "text",
                            "content-desc",
                            "window_id",
                            "bounds_array",
                        ]
                        .iter()
                        .all(|k| s.reply.body()["target"][*k] == n[*k]),
                        "housing retained click differs from its actual target",
                    )?;
                }
                need(
                    s.reply.body()["performed"]
                        == if s.operation == Operation::SetText {
                            "set-text"
                        } else {
                            "click"
                        },
                    "housing retained mutation kind changed",
                )?;
            } else {
                need(
                    s.operation == Operation::Dump,
                    "housing mutation lacks actual source target",
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
    ["ImageView", "SimpleDraweeView"]
        .iter()
        .any(|v| text(n, "class").ends_with(v))
        || ["listingImage", "listingPhoto"]
            .iter()
            .any(|id| text(n, "resource-id").ends_with(&format!(":id/{id}")))
}
fn image_present(body: &Value, c: &Contract, rect: Rect) -> Result<bool, String> {
    Ok(nodes(body, c)?
        .iter()
        .any(|n| usable(n, c) && image_node(n) && Rect::parse(&n["bounds_array"]) == Ok(rect)))
}
fn inside<'a>(ns: &'a [Value], c: &Contract, rect: Rect) -> Vec<&'a Value> {
    ns.iter()
        .filter(|n| usable(n, c) && Rect::parse(&n["bounds_array"]).is_ok_and(|r| rect.contains(r)))
        .collect()
}
fn public_location(value: &str, c: &Contract) -> bool {
    let s = norm(value);
    let q = norm(c.query);
    s == q
        || s.split([',', '，', '·', '/', '-', '|'])
            .any(|v| norm(v) == q)
        || (c.city.is_some() && s.contains(c.query) && s.len() <= 160)
}
fn query_visible(body: &Value, c: &Contract) -> Result<bool, String> {
    let ns = nodes(body, c)?;
    let window = Rect::parse(&body["window_context"]["selected_window"]["bounds"])?;
    Ok(ns.iter().any(|n| {
        usable(n, c)
            && !unsafe_control(text(n, "text"))
            && ((n["editable"] == true
                && n["showing-hint"] == false
                && (text(n, "value") == c.query || text(n, "text") == c.query))
                || (n["editable"] == false
                    && public_location(text(n, "text"), c)
                    && Rect::parse(&n["bounds_array"]).is_ok_and(|r| {
                        r.0[3] <= window.0[1] + (window.0[3] - window.0[1]) * 2 / 5
                    })
                    && (source_id(n, c, c.entry_ids)
                        || source_id(
                            n,
                            c,
                            &[
                                "locationLabel",
                                "locations_bar_view",
                                "search_word",
                                "tv_search_condition_text",
                                "search_result_word",
                            ],
                        )
                        || n["selected"] == true
                        || n["checked"] == true)))
    }))
}
fn actual_prices(ns: &[&Value], c: &Contract) -> BTreeSet<Money> {
    let mut found = BTreeSet::new();
    for n in ns {
        let id = text(n, "resource-id").to_lowercase();
        if [
            "old",
            "older",
            "cross",
            "strike",
            "unit_price",
            "avg",
            "average",
            "persquare",
        ]
        .iter()
        .any(|x| id.contains(x))
        {
            continue;
        }
        if let Some(v) = money(text(n, "text")) {
            found.insert(v);
        }
        if id.starts_with(&format!("{}:id/", c.package))
            && id.contains("price")
            && !id.contains("unit")
            && decimal(text(n, "text"), 100).is_some()
        {
            if let Ok(r) = Rect::parse(&n["bounds_array"]) {
                for u in ns {
                    let unit = text(u, "text");
                    if !["万", "万元", "元/月"].contains(&unit) {
                        continue;
                    }
                    if Rect::parse(&u["bounds_array"]).is_ok_and(|s| {
                        r.0[1] < s.0[3] && s.0[1] < r.0[3] && (s.0[0] - r.0[2]).abs() <= 96
                    }) {
                        if let Some(v) = money(&format!("{}{unit}", text(n, "text"))) {
                            found.insert(v);
                        }
                    }
                }
            }
        }
    }
    found
}
fn bed_values(ns: &[&Value], c: &Contract) -> BTreeSet<u8> {
    let mut out = BTreeSet::new();
    for n in ns {
        let t = text(n, "text");
        for token in t.split(['|', '·', '/', '\n']) {
            if let Some(v) = beds(token.trim()) {
                out.insert(v);
            }
        }
        if source_id(n, c, &["listingBeds", "beds", "salesBeds", "rentalsBeds"]) {
            if let Ok(v) = t.trim().parse::<u8>() {
                if v <= 8 {
                    out.insert(v);
                }
            }
        }
    }
    out
}
fn area_values(ns: &[&Value]) -> BTreeSet<(u64, &'static str)> {
    let mut out = BTreeSet::new();
    for n in ns {
        for token in text(n, "text").split(['|', '·', '/', '\n']) {
            if let Some(v) = area(token.trim()) {
                out.insert(v);
            }
        }
    }
    out
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct Listing {
    title: String,
    price: Money,
    beds: u8,
    area: Option<(u64, &'static str)>,
    title_bounds: Rect,
    card: Rect,
    image: Rect,
}
fn listings(body: &Value, c: &Contract) -> Result<Vec<Listing>, String> {
    let ns = nodes(body, c)?;
    let titles = ns
        .iter()
        .filter(|n| usable(n, c) && n["editable"] == false && address(text(n, "text"), c))
        .collect::<Vec<_>>();
    let mut out = Vec::new();
    for t in &titles {
        let title = text(t, "text");
        if ns.iter().filter(|n| text(n, "text") == title).count() != 1 {
            continue;
        }
        let tr = Rect::parse(&t["bounds_array"])?;
        let mut cards = ns
            .iter()
            .filter(|n| usable(n, c) && n["clickable"] == true)
            .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
            .filter(|r| r.contains(tr))
            .collect::<Vec<_>>();
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
            let values = inside(ns, c, card);
            if !values.iter().any(|n| public_location(text(n, "text"), c)) {
                continue;
            }
            let prices = actual_prices(&values, c);
            let rooms = bed_values(&values, c);
            let sizes = area_values(&values);
            let mut images = values
                .iter()
                .filter(|n| image_node(n))
                .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
                .filter(|r| r.0[2] - r.0[0] >= 48 && r.0[3] - r.0[1] >= 48)
                .collect::<Vec<_>>();
            images.sort_by_key(|r| std::cmp::Reverse(r.area()));
            images.dedup();
            if prices.len() != 1
                || rooms.len() != 1
                || sizes.len() > 1
                || images.is_empty()
                || images.get(1).is_some_and(|r| r.area() == images[0].area())
            {
                continue;
            }
            out.push(Listing {
                title: title.into(),
                price: prices.into_iter().next().unwrap(),
                beds: *rooms.iter().next().unwrap(),
                area: sizes.into_iter().next(),
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
fn populated(trace: &Trace, frame: usize, c: &Contract) -> Result<Option<Vec<Listing>>, String> {
    let f = trace
        .frames
        .get(frame)
        .ok_or("housing retained frame absent")?;
    let a = trace.body(f.before)?;
    let b = trace.body(f.after)?;
    if !query_visible(a, c)? || !query_visible(b, c)? {
        return Ok(None);
    }
    let first = listings(a, c)?;
    let second = listings(b, c)?;
    if first.len() < 2 || first != second || first.iter().any(|l| !f.images.contains_key(&l.image))
    {
        return Ok(None);
    }
    Ok(Some(first))
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct Detail {
    title: String,
    price: Money,
    beds: u8,
    area: (u64, &'static str),
    image: Rect,
}
fn detail(body: &Value, c: &Contract, chosen: &Listing) -> Result<Option<Detail>, String> {
    let ns = nodes(body, c)?;
    let ts = ns
        .iter()
        .filter(|n| {
            usable(n, c) && n["editable"] == false && same_title(text(n, "text"), &chosen.title)
        })
        .collect::<Vec<_>>();
    if ts.len() != 1 {
        return Ok(None);
    }
    let values = ns.iter().filter(|n| usable(n, c)).collect::<Vec<_>>();
    let rooms = bed_values(&values, c);
    let sizes = area_values(&values);
    let prices = actual_prices(&values, c);
    // Another visible current price makes this unscoped detail ambiguous;
    // a recommendation cannot supply the selected listing\'s expected price.
    if prices != BTreeSet::from([chosen.price.clone()])
        || rooms != BTreeSet::from([chosen.beds])
        || sizes.len() != 1
    {
        return Ok(None);
    }
    let size = *sizes.iter().next().unwrap();
    if chosen.area.is_some_and(|v| v != size) {
        return Ok(None);
    }
    let mut images = values
        .iter()
        .filter(|n| image_node(n))
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .filter(|r| r.0[2] - r.0[0] >= 48 && r.0[3] - r.0[1] >= 48)
        .collect::<Vec<_>>();
    images.sort_by_key(|r| std::cmp::Reverse(r.area()));
    images.dedup();
    if images.is_empty() || images.get(1).is_some_and(|r| r.area() == images[0].area()) {
        return Ok(None);
    }
    Ok(Some(Detail {
        title: text(ts[0], "text").into(),
        price: chosen.price.clone(),
        beds: chosen.beds,
        area: size,
        image: images[0],
    }))
}
fn same_listing(a: &Listing, b: &Listing) -> bool {
    same_title(&a.title, &b.title) && a.price == b.price && a.beds == b.beds && a.area == b.area
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
struct FacetOption {
    number: i8,
    label: String,
    selected: bool,
}
fn options(body: &Value, c: &Contract) -> Result<Vec<FacetOption>, String> {
    need(
        filter_context(body, c)?,
        "housing filter lacks its actual Bedrooms/户型 context",
    )?;
    let mut result = Vec::new();
    for n in nodes(body, c)?
        .iter()
        .filter(|n| role_matches(n, c, Role::Facet))
    {
        let number = option_number(n, c).ok_or("housing bedroom option absent")?;
        let label = if text(n, "text").is_empty() {
            text(n, "content-desc")
        } else {
            text(n, "text")
        };
        need(
            !label.is_empty() && result.iter().all(|old: &FacetOption| old.number != number),
            "housing bedroom options are ambiguous",
        )?;
        result.push(FacetOption {
            number,
            label: label.into(),
            selected: selected(n).ok_or("housing actual option state absent")?,
        });
    }
    result.sort_by_key(|v| v.number);
    need(
        result.len() >= 3 && result.len() <= 7 && result.iter().any(|v| v.number == 2),
        "housing complete observed bedroom group is absent",
    )?;
    Ok(result)
}
fn changed_facet(before: &[FacetOption], after: &[FacetOption]) -> Result<Option<String>, String> {
    need(
        before.len() == after.len()
            && before
                .iter()
                .zip(after)
                .all(|(a, b)| a.number == b.number && a.label == b.label),
        "housing filter options changed shape",
    )?;
    need(
        before
            .iter()
            .find(|v| v.number == 2)
            .is_some_and(|v| !v.selected)
            && after
                .iter()
                .find(|v| v.number == 2)
                .is_some_and(|v| v.selected),
        "housing owned two-bedroom selection lacks false-to-true readback",
    )?;
    let changed = before
        .iter()
        .zip(after)
        .filter(|(a, b)| a.number != 2 && a.selected != b.selected)
        .collect::<Vec<_>>();
    need(
        changed.len() <= 1 && changed.iter().all(|(a, b)| a.selected && !b.selected),
        "housing facet changed more than its exact prior radio selection",
    )?;
    Ok(changed.first().map(|(a, _)| a.label.clone()))
}
struct SearchFlow {
    initial_dump: usize,
    typed: Option<(usize, usize, usize)>,
    frame: usize,
    original_input_sha256: Option<String>,
}
struct DetailFlow {
    selected: Listing,
    clicked: usize,
    frame: usize,
    facts: Detail,
}
struct FilterFlow {
    label: String,
    before: usize,
    checked: usize,
    applied_frame: usize,
    restore_before: usize,
    restored: usize,
    returned_frame: usize,
    before_options: Vec<FacetOption>,
    checked_options: Vec<FacetOption>,
    restored_prior_label: Option<String>,
    effect: bool,
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
pub(super) struct HousingExecution {
    contract: &'static Contract,
    first: Phase,
    second: Option<Phase>,
    original_end: Instant,
    finished_reopen: OnceCell<FinishedReopen>,
}
fn empty_input(n: &Value) -> bool {
    if n["showing-hint"] == true {
        let h = text(n, "hint");
        (text(n, "value").is_empty() || text(n, "value") == h)
            && (text(n, "text").is_empty() || text(n, "text") == h)
    } else {
        text(n, "value").is_empty() && text(n, "text").is_empty()
    }
}
fn city_visible(body: &Value, c: &Contract) -> Result<bool, String> {
    let Some(city) = c.city else { return Ok(true) };
    let window = Rect::parse(&body["window_context"]["selected_window"]["bounds"])?;
    Ok(nodes(body, c)?.iter().any(|n| {
        usable(n, c)
            && text(n, "text") == city
            && source_id(
                n,
                c,
                &[
                    "card_home_title_bar_one_tv_city",
                    "city_tv",
                    "city_view",
                    "city",
                ],
            )
            && Rect::parse(&n["bounds_array"])
                .is_ok_and(|r| r.0[3] <= window.0[1] + (window.0[3] - window.0[1]) / 3)
    }))
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
        let frame = p.trace.frame(s, i, c, end)?;
        let observed = populated(&p.trace, frame, c)?;
        if observed.as_ref() == Some(&listings(p.trace.body(initial)?, c)?) && observed.is_some() {
            p.search = Some(SearchFlow {
                initial_dump: initial,
                typed: None,
                frame,
                original_input_sha256: None,
            });
            p.stop = "public_query_present_in_first_reopen_dump";
        } else {
            p.stop = "reopened_public_query_not_populated_before_input";
        }
        return Ok(());
    }
    let mut form = initial;
    if !retained && !city_visible(p.trace.body(form)?, c)? {
        let Some(city) = target(&p.trace, form, c, Role::City, None)? else {
            p.stop = "actual_public_city_control_absent";
            return Ok(());
        };
        p.trace.click(s, i, city, end)?;
        form = p.trace.dump(s, i, end)?;
        let Some(choice) = target(&p.trace, form, c, Role::CityChoice, c.city)? else {
            p.stop = "unique_declared_public_city_absent";
            return Ok(());
        };
        p.trace.click(s, i, choice, end)?;
        form = p.trace.dump(s, i, end)?;
        need(
            city_visible(p.trace.body(form)?, c)?,
            "housing actual selected city readback differs",
        )?;
    }
    if !retained {
        if let Some(mode) = target(&p.trace, form, c, Role::Mode, None)? {
            p.trace.click(s, i, mode, end)?;
            form = p.trace.dump(s, i, end)?;
        }
    }
    if target(&p.trace, form, c, Role::Input, None)?.is_none() {
        let Some(entry) = target(&p.trace, form, c, Role::Entry, None)? else {
            p.stop = "unique_public_location_search_entry_absent";
            return Ok(());
        };
        p.trace.click(s, i, entry, end)?;
        form = p.trace.dump(s, i, end)?;
    }
    let Some(input) = target(&p.trace, form, c, Role::Input, None)? else {
        p.stop = "unique_public_nonpassword_location_field_absent";
        return Ok(());
    };
    if !empty_input(&input.node) {
        p.stop = "existing_nonempty_location_query_preserved";
        return Ok(());
    }
    let original = digest(&serde_json::to_vec(&input.node).map_err(|e| e.to_string())?);
    let typed = p.trace.set_text(s, i, input, c.query, end)?;
    let readback = p.trace.dump(s, i, end)?;
    if !query_visible(p.trace.body(readback)?, c)? {
        p.stop = "public_location_exact_readback_missing";
        return Ok(());
    }
    let mut last = readback;
    let submitted = if let Some(choice) =
        target(&p.trace, last, c, Role::Suggestion, Some(c.query))?
    {
        let selected = p.trace.click(s, i, choice, end)?;
        last = p.trace.dump(s, i, end)?;
        if !listings(p.trace.body(last)?, c)?.is_empty() && query_visible(p.trace.body(last)?, c)? {
            selected
        } else if let Some(submit) = target(&p.trace, last, c, Role::Submit, None)? {
            p.trace.click(s, i, submit, end)?
        } else {
            p.stop = "public_location_suggestion_lacks_actual_list_or_submit";
            return Ok(());
        }
    } else if let Some(submit) = target(&p.trace, last, c, Role::Submit, None)? {
        p.trace.click(s, i, submit, end)?
    } else {
        p.stop = "unique_public_location_submission_absent";
        return Ok(());
    };
    let frame = p.trace.frame(s, i, c, end)?;
    if populated(&p.trace, frame, c)?.is_none() {
        p.stop = "matching_populated_listings_and_decoded_images_absent";
        return Ok(());
    }
    p.search = Some(SearchFlow {
        initial_dump: initial,
        typed: Some((typed, readback, submitted)),
        frame,
        original_input_sha256: Some(original),
    });
    p.stop = "public_location_results_observed";
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
        .ok_or("housing detail needs its actual public query")?;
    let results = populated(&p.trace, search.frame, c)?
        .ok_or("housing original populated result no longer verifies")?;
    let choice = if let Some(old) = expected {
        results.into_iter().find(|v| same_listing(v, &old.selected))
    } else {
        results.into_iter().find(|v| v.beds == 2)
    };
    let Some(chosen) = choice else {
        p.stop = "matching_two_bedroom_listing_absent";
        return Ok(());
    };
    let from = p.trace.frames[search.frame].after;
    let Some(t) = target(&p.trace, from, c, Role::Listing, Some(&chosen.title))? else {
        p.stop = "unique_actual_listing_address_control_absent";
        return Ok(());
    };
    let clicked = p.trace.click(s, i, t, end)?;
    let actual = Rect::parse(&p.trace.body(clicked)?["actual_target"]["bounds_array"])?;
    need(
        chosen.card.contains(actual) && actual.contains(chosen.title_bounds),
        "housing actual listing action escaped its observed card",
    )?;
    let frame = p.trace.frame(s, i, c, end)?;
    let f = &p.trace.frames[frame];
    let a = detail(p.trace.body(f.before)?, c, &chosen)?;
    let z = detail(p.trace.body(f.after)?, c, &chosen)?;
    let Some(facts) = a.filter(|a| Some(a) == z.as_ref()) else {
        p.stop = "listing_detail_address_price_bedrooms_or_area_missing";
        return Ok(());
    };
    let matched = p.trace.frames[search.frame]
        .images
        .get(&chosen.image)
        .zip(f.images.get(&facts.image))
        .is_some_and(|(a, b)| image_matches(a, b));
    if !matched {
        p.stop = "decoded_listing_photo_does_not_match_detail";
        return Ok(());
    }
    if expected.is_some_and(|v| {
        v.facts.title != facts.title
            || v.facts.price != facts.price
            || v.facts.beds != facts.beds
            || v.facts.area != facts.area
    }) {
        p.stop = "independent_reopen_detail_state_differs";
        return Ok(());
    }
    p.detail = Some(DetailFlow {
        selected: chosen,
        clicked,
        frame,
        facts,
    });
    p.stop = "matching_public_detail_observed";
    Ok(())
}
fn execute_back(
    p: &mut Phase,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    c: &Contract,
    end: Instant,
) -> Result<(), String> {
    let d = p
        .detail
        .as_ref()
        .ok_or("housing Back needs actual detail")?;
    let from = p.trace.frames[d.frame].after;
    let Some(back) = target(&p.trace, from, c, Role::Back, None)? else {
        p.stop = "unique_public_detail_back_absent";
        return Ok(());
    };
    p.trace.click(s, i, back, end)?;
    let returned = p.trace.dump(s, i, end)?;
    if !query_visible(p.trace.body(returned)?, c)?
        || !listings(p.trace.body(returned)?, c)?
            .iter()
            .any(|l| same_listing(l, &d.selected))
    {
        p.stop = "public_back_did_not_restore_query_and_listing";
        return Ok(());
    }
    p.back = Some(returned);
    Ok(())
}
fn filter_effect(
    trace: &Trace,
    frame: usize,
    c: &Contract,
    chosen: &Listing,
) -> Result<bool, String> {
    Ok(populated(trace, frame, c)?.is_some_and(|list| {
        list.iter().all(|l| l.beds == 2) && list.iter().any(|l| same_listing(l, chosen))
    }))
}
fn execute_filter(
    p: &mut Phase,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    c: &Contract,
    end: Instant,
) -> Result<(), String> {
    let returned = p
        .back
        .ok_or("housing filter needs its actual Back result")?;
    let Some(open) = target(&p.trace, returned, c, Role::Filter, None)? else {
        p.stop = "unique_public_filters_control_absent";
        return Ok(());
    };
    p.trace.click(s, i, open, end)?;
    let before = p.trace.dump(s, i, end)?;
    if !filter_context(p.trace.body(before)?, c)? {
        p.stop = "bedroom_filter_context_absent";
        return Ok(());
    }
    let prior = options(p.trace.body(before)?, c)?;
    let Some(choice) = prior.iter().find(|v| v.number == 2 && !v.selected) else {
        p.stop = "existing_selected_bedroom_filter_preserved";
        return Ok(());
    };
    let label = choice.label.clone();
    let Some(toggle) = target(&p.trace, before, c, Role::Facet, Some(&label))? else {
        p.stop = "unique_two_bedroom_filter_absent";
        return Ok(());
    };
    if target(&p.trace, before, c, Role::Apply, None)?.is_none() {
        p.stop = "public_filter_apply_absent";
        return Ok(());
    }
    p.trace.click(s, i, toggle, end)?;
    let checked = p.trace.dump(s, i, end)?;
    let changed = options(p.trace.body(checked)?, c)?;
    let restored_prior_label = changed_facet(&prior, &changed)?;
    let apply = target(&p.trace, checked, c, Role::Apply, None)?
        .ok_or("housing changed filter lost Apply")?;
    p.trace.click(s, i, apply, end)?;
    let applied_frame = p.trace.frame(s, i, c, end)?;
    let chosen = &p
        .detail
        .as_ref()
        .ok_or("housing filter detached from selected detail")?
        .selected;
    let effect = filter_effect(&p.trace, applied_frame, c, chosen)?;
    // Restore only this observed checkbox or the one observed radio choice.
    // Unknown/missing replies stop; no input action is retried.
    let from = p.trace.frames[applied_frame].after;
    let open = target(&p.trace, from, c, Role::Filter, None)?
        .ok_or("housing cannot reopen the changed filter")?;
    p.trace.click(s, i, open, end)?;
    let restore_before = p.trace.dump(s, i, end)?;
    need(
        options(p.trace.body(restore_before)?, c)? == changed,
        "housing changed bedroom group lost actual custody",
    )?;
    let restore_label = restored_prior_label.as_deref().unwrap_or(&label);
    let restore = target(
        &p.trace,
        restore_before,
        c,
        Role::Facet,
        Some(restore_label),
    )?
    .ok_or("housing exact original option restore absent")?;
    p.trace.click(s, i, restore, end)?;
    let restored = p.trace.dump(s, i, end)?;
    need(
        options(p.trace.body(restored)?, c)? == prior,
        "housing original visible bedroom group was not restored",
    )?;
    let apply = target(&p.trace, restored, c, Role::Apply, None)?
        .ok_or("housing restored filter lacks Apply")?;
    p.trace.click(s, i, apply, end)?;
    let returned_frame = p.trace.frame(s, i, c, end)?;
    let restored_list = populated(&p.trace, returned_frame, c)?;
    need(
        restored_list
            .as_ref()
            .is_some_and(|ls| ls.iter().any(|l| same_listing(l, chosen))),
        "housing restored filter lost the exact location/address/price state",
    )?;
    p.filter = Some(FilterFlow {
        label,
        before,
        checked,
        applied_frame,
        restore_before,
        restored,
        returned_frame,
        before_options: prior,
        checked_options: changed,
        restored_prior_label,
        effect,
    });
    p.stop = if effect {
        "matching_two_bedroom_filter_effect_and_restore_observed"
    } else {
        "filter_effect_unqualified_original_selection_restored"
    };
    Ok(())
}
pub(super) fn run(
    s: &mut NativeUiSession<'_, '_>,
    i: &mut NativeApplicationInspector,
    package: &str,
    original_end: Instant,
) -> Result<HousingExecution, String> {
    before(original_end)?;
    let c = contract(package)?;
    let mut first = Phase::new(false);
    execute_search(&mut first, s, i, c, original_end, false)?;
    if first.search.is_some() {
        execute_detail(&mut first, s, i, c, original_end, None)?;
    }
    if first.detail.is_some() {
        execute_back(&mut first, s, i, c, original_end)?;
    }
    if first.back.is_some() {
        execute_filter(&mut first, s, i, c, original_end)?;
    }
    before(original_end)?;
    Ok(HousingExecution {
        contract: c,
        first,
        second: None,
        original_end,
        finished_reopen: OnceCell::new(),
    })
}

impl HousingExecution {
    pub(super) fn first_counts(&self) -> (u32, u32) {
        self.first.trace.counts()
    }
    pub(super) fn reopened_counts(&self) -> Option<(u32, u32)> {
        self.second.as_ref().map(|p| p.trace.counts())
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
            "housing separate reopen must retain the first history and original fixed deadline",
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
            let matched = self.first.trace.frames[a.frame]
                .images
                .get(&a.facts.image)
                .zip(next.trace.frames[b.frame].images.get(&b.facts.image))
                .is_some_and(|(a, b)| image_matches(a, b));
            if !matched {
                next.detail = None;
                next.stop = "independent_reopen_photo_differs";
            }
        }
        if next.detail.is_some() {
            execute_back(&mut next, s, i, self.contract, original_end)?;
        }
        self.second = Some(next);
        before(original_end)
    }
    fn guard_phase(&self, p: &Phase, t: &NativeUiTranscript, second: bool) -> Result<(), String> {
        let c = self.contract;
        require_application(t.engine().application())?;
        need(
            t.engine().application().package == c.package,
            "housing retained history belongs to another original application",
        )?;
        p.trace.guard(c, t)?;
        need(
            p.trace.request_limit
                == if second {
                    SECOND_REQUESTS
                } else {
                    FIRST_REQUESTS
                }
                && p.trace.action_limit
                    == if second {
                        reopen_max_actions()
                    } else {
                        first_max_extra_actions()
                    }
                && p.trace.capture_limit
                    == if second {
                        SECOND_CAPTURES
                    } else {
                        FIRST_CAPTURES
                    },
            "housing phase changed its fixed source bounds",
        )?;
        if let Some(search) = &p.search {
            let f = p
                .trace
                .frames
                .get(search.frame)
                .ok_or("housing search frame absent")?;
            need(
                search.initial_dump == 0
                    && p.trace.steps[search.initial_dump].operation == Operation::Dump
                    && populated(&p.trace, search.frame, c)?.is_some(),
                "housing search lost actual populated listings or initial dump",
            )?;
            if let Some((typed, readback, sent)) = search.typed {
                let typed_step = p
                    .trace
                    .steps
                    .get(typed)
                    .ok_or("housing typed step absent")?;
                let origin = typed_step
                    .target
                    .as_ref()
                    .ok_or("housing typed source target absent")?;
                need(typed_step.operation==Operation::SetText &&origin.1==Role::Input
                    &&empty_input(&origin.2)
                    &&typed_step.written.as_deref()==Some(c.query)
                    &&p.trace.body(typed)?["characters"].as_u64()==Some(c.query.chars().count() as u64)
                    &&p.trace.body(typed)?["readback_verified"]==true
                    &&query_visible(p.trace.body(readback)?,c)?
                    &&p.trace.steps.get(sent).is_some_and(|s|s.operation==Operation::Click
                        &&s.target.as_ref().is_some_and(|(_,r,_)|matches!(r,Role::Submit|Role::Suggestion)))
                    &&typed<readback && readback<sent && sent<f.before
                    &&search.original_input_sha256.as_ref()==Some(&digest(&serde_json::to_vec(&origin.2).map_err(|e|e.to_string())?)),
                    "housing query overwritten, substituted, reordered, or missing actual submission/readback")?;
            } else {
                need(second &&self.first.search.is_some()&&search.original_input_sha256.is_none()
                    &&p.trace.steps[..=f.after].iter().all(|s|s.operation==Operation::Dump)
                    &&query_visible(p.trace.body(search.initial_dump)?,c)?
                    &&populated(&p.trace,search.frame,c)?.as_ref()==Some(&listings(p.trace.body(search.initial_dump)?,c)?),
                    "housing preserved query must exist before new input in the first actual reopen dump")?;
            }
        }
        if let Some(flow) = &p.detail {
            let search = p
                .search
                .as_ref()
                .ok_or("housing detail lacks its actual query")?;
            let selection = p
                .trace
                .frames
                .get(search.frame)
                .ok_or("housing selection frame absent")?;
            let f = p
                .trace
                .frames
                .get(flow.frame)
                .ok_or("housing detail frame absent")?;
            let clicked = p
                .trace
                .steps
                .get(flow.clicked)
                .ok_or("housing detail action absent")?;
            let chosen = clicked
                .target
                .as_ref()
                .ok_or("housing detail lost its actual source selector")?;
            let actual =
                Rect::parse(&p.trace.body(flow.clicked)?["actual_target"]["bounds_array"])?;
            need(populated(&p.trace,search.frame,c)?.as_ref().is_some_and(|l|l.contains(&flow.selected))
                &&clicked.operation==Operation::Click&&chosen.0==selection.after&&chosen.1==Role::Listing
                &&text(&chosen.2,"text")==flow.selected.title
                &&selection.after<flow.clicked&&flow.clicked<f.before
                &&flow.selected.card.contains(actual)&&actual.contains(flow.selected.title_bounds)
                &&detail(p.trace.body(f.before)?,c,&flow.selected)?.as_ref()==Some(&flow.facts)
                &&detail(p.trace.body(f.after)?,c,&flow.selected)?.as_ref()==Some(&flow.facts)
                &&selection.images.get(&flow.selected.image).zip(f.images.get(&flow.facts.image))
                    .is_some_and(|(a,b)|image_matches(a,b)),
                "housing detail no longer joins the actual selected address, price, room data and decoded photo")?;
        }
        if let Some(back) = p.back {
            let flow = p.detail.as_ref().ok_or("housing Back lost its detail")?;
            let previous = back
                .checked_sub(1)
                .and_then(|i| p.trace.steps.get(i))
                .ok_or("housing Back action absent")?;
            need(
                previous.operation == Operation::Click
                    && previous.target.as_ref().is_some_and(|(from, role, _)| {
                        *from == p.trace.frames[flow.frame].after && *role == Role::Back
                    })
                    && p.trace
                        .steps
                        .get(back)
                        .is_some_and(|s| s.operation == Operation::Dump)
                    && query_visible(p.trace.body(back)?, c)?
                    && listings(p.trace.body(back)?, c)?
                        .iter()
                        .any(|l| same_listing(l, &flow.selected)),
                "housing actual Back did not preserve the observed public query/address/price",
            )?;
        }
        if let Some(f) = &p.filter {
            let chosen = &p
                .detail
                .as_ref()
                .ok_or("housing filter lacks its selected listing")?
                .selected;
            let original = options(p.trace.body(f.before)?, c)?;
            let changed = options(p.trace.body(f.checked)?, c)?;
            let restored = options(p.trace.body(f.restored)?, c)?;
            let apply = p
                .trace
                .frames
                .get(f.applied_frame)
                .ok_or("housing filter actual frame absent")?;
            let returned = p
                .trace
                .frames
                .get(f.returned_frame)
                .ok_or("housing restored actual frame absent")?;
            need(
                !second
                    && p.back.is_some_and(|b| b < f.before)
                    && f.before_options == original
                    && f.checked_options == changed
                    && original
                        .iter()
                        .any(|v| v.number == 2 && v.label == f.label && !v.selected)
                    && changed_facet(&original, &changed)? == f.restored_prior_label
                    && options(p.trace.body(f.restore_before)?, c)? == changed
                    && restored == original
                    && f.before < f.checked
                    && f.checked < apply.before
                    && apply.after < f.restore_before
                    && f.restore_before < f.restored
                    && f.restored < returned.before
                    && f.effect == filter_effect(&p.trace, f.applied_frame, c, chosen)?
                    && populated(&p.trace, f.returned_frame, c)?
                        .is_some_and(|ls| ls.iter().any(|l| same_listing(l, chosen))),
                "housing filter actual effect or exact prior visible selection restoration differs",
            )?;
            for (after, role, label) in [
                (f.checked, Role::Facet, Some(f.label.as_str())),
                (apply.before, Role::Apply, None),
                (f.restore_before, Role::Filter, None),
                (
                    f.restored,
                    Role::Facet,
                    Some(f.restored_prior_label.as_deref().unwrap_or(&f.label)),
                ),
                (returned.before, Role::Apply, None),
            ] {
                let step = after
                    .checked_sub(1)
                    .and_then(|n| p.trace.steps.get(n))
                    .ok_or("housing filter action absent")?;
                need(
                    step.operation == Operation::Click
                        && step.target.as_ref().is_some_and(|(_, r, node)| {
                            *r == role
                                && label.is_none_or(|v| {
                                    text(node, "text") == v || text(node, "content-desc") == v
                                })
                        }),
                    "housing filter comparison lacks the actual action that caused each readback",
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
        self.guard_phase(&self.first, first, false)?;
        match (&self.second, reopened) {
            (None, None) => need(
                self.finished_reopen.get().is_none(),
                "housing finished reopen lost its second history",
            ),
            (Some(second), Some(next)) => {
                self.guard_phase(second, next, true)?;
                need(first.task()!=next.task()&&first.journal()!=next.journal()
                    &&first.engine().application()==next.engine().application()
                    &&first.engine().facts().main==next.engine().facts().main,
                    "housing reopen needs a different genuine finished task/journal under the same Main and complete original application")?;
                if let (Some(a), Some(b)) = (&self.first.detail, &second.detail) {
                    need(
                        same_listing(&a.selected, &b.selected)
                            && a.facts.price == b.facts.price
                            && same_title(&a.facts.title, &b.facts.title)
                            && a.facts.beds == b.facts.beds
                            && a.facts.area == b.facts.area
                            && self.first.trace.frames[a.frame]
                                .images
                                .get(&a.facts.image)
                                .zip(second.trace.frames[b.frame].images.get(&b.facts.image))
                                .is_some_and(|(a, b)| image_matches(a, b)),
                        "housing independent actual detail/photo differs",
                    )?;
                    if second.search.as_ref().is_some_and(|s| s.typed.is_none())
                        && self.first.back.is_some()
                        && second.back.is_some()
                    {
                        let binding = FinishedReopen {
                            main: first.engine().facts().main.clone(),
                            application: first.engine().application().clone(),
                            first_task: first.task(),
                            second_task: next.task(),
                            first_journal: first.journal().into(),
                            second_journal: next.journal().into(),
                        };
                        if let Some(old) = self.finished_reopen.get() {
                            need(
                                old.main == binding.main
                                    && old.application == binding.application
                                    && old.first_task == binding.first_task
                                    && old.second_task == binding.second_task
                                    && old.first_journal == binding.first_journal
                                    && old.second_journal == binding.second_journal,
                                "housing finished public reopen binding changed",
                            )?;
                        } else {
                            before(self.original_end)?;
                            self.finished_reopen
                                .set(binding)
                                .map_err(|_| "housing public reopen sealed twice")?;
                        }
                    }
                }
                Ok(())
            }
            _ => Err("housing comparison cannot replace an actual retained second history".into()),
        }
    }
    pub(super) fn completed_gates(&self) -> Vec<&'static str> {
        // The source registry requires both location AND filter results for
        // query. A filter toggle alone never supplies matching results.
        let mut gates = Vec::new();
        if self.first.search.is_some() && self.first.filter.as_ref().is_some_and(|f| f.effect) {
            gates.push("housing.query");
        }
        if self.first.detail.is_some() {
            gates.push("housing.details");
        }
        // Public Back/reopen is recorded separately. Neither an account
        // registration nor a sign-out control proves an authenticated route.
        // housing.navigation remains absent until such a normal factory exists.
        gates
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        let phase = |p: &Phase| -> Result<Value, String> {
            Ok(json!({
                "stop":p.stop,"actual_ui_requests":p.trace.requests(),"actual_input_actions":p.trace.actions(),
                "actual_commands":p.trace.counts().0,
                "retained_reply_bytes":p.trace.steps.iter().map(|s|s.reply.body().to_string().len()).sum::<usize>(),
                "actual_scoped_pixels":p.trace.frames.iter().map(|f|f.pixels.comparison()).collect::<Result<Vec<_>,_>>()?,
                "original_input_sha256":p.search.as_ref().and_then(|s|s.original_input_sha256.as_ref()),
                "actual_detail":p.detail.as_ref().map(|d|json!({
                    "address_sha256":digest(d.facts.title.as_bytes()),"price":d.facts.price,
                    "bedrooms":d.facts.beds,"area":d.facts.area,
                    "list_and_detail_same_actual_decoded_photo":true
                })),
                "actual_filter":p.filter.as_ref().map(|f|json!({"bedrooms":2,
                    "prior_visible_group_restored":true,"matching_populated_listings":f.effect,
                    "prior_radio_selection_restored":f.restored_prior_label.is_some()})),
                "public_back_observed":p.back.is_some(),"decoded_rgb_retained":false,
                "account_or_private_input_contents_disclosed":false
            }))
        };
        Ok(json!({
            "schema":"droidloom.housing-actual-guest-execution.v1","package":self.contract.package,
            "source_selection_sha256":SOURCE_SELECTION_SHA256,"source_readback_sha256":SOURCE_READBACK_SHA256,
            "fixed_public_location":self.contract.query,"first":phase(&self.first)?,
            "reopened":self.second.as_ref().map(phase).transpose()?,
            "actual_public_reopen_preserved_before_new_input":self.finished_reopen.get().is_some(),
            "query_reentered_after_reopen":self.second.as_ref().and_then(|p|p.search.as_ref()).is_some_and(|s|s.typed.is_some()),
            "completed_business_gates":self.completed_gates(),
            "navigation_pending":"legitimate_authenticated_route_and_same_account_state_from_an_actual_normal_factory",
            "public_reopen_inferred_as_authentication":false,"account_manager_count_inferred_as_login":false,
            "signout_or_login_router_inferred_as_authentication":false,
            "messages_contacts_tours_orders_payments_or_account_changes_attempted":false,
            "existing_nonempty_input_overwritten":false,"saved_query_history_erased":false,
            "runtime_qualified":false,"production_ready":false,"comparison_only":true
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_supervisor::control::application_probe::{InstalledApk, RuntimeEpoch};

    fn actual_source(c: &Contract) -> ApplicationInspection {
        ApplicationInspection {
            package: c.package.into(),
            user: 0,
            uid: 10_147,
            version_code: c.version_code,
            epoch: RuntimeEpoch {
                boot_id: "parser-test-only".into(),
                cell_host_pid: 10,
                framework_host_pid: 11,
                framework_start_ticks: 12,
            },
            apks: c
                .apks
                .iter()
                .enumerate()
                .map(|(i, a)| InstalledApk {
                    name: if i == 0 {
                        "base.apk".into()
                    } else {
                        format!("actual-split-{i}.apk")
                    },
                    path: format!("/data/app/parser-test/{i}.apk"),
                    bytes: a.bytes,
                    sha256: a.sha256.into(),
                })
                .collect(),
        }
    }
    fn node(c: &Contract, id: &str, label: &str, bounds: [i64; 4]) -> Value {
        json!({"package":c.package,"resource-id":format!("{}:id/{id}",c.package),
            "text":label,"content-desc":"","class":"android.widget.TextView",
            "visible":true,"enabled":true,"password":false,"editable":false,"clickable":false,
            "selected":false,"checked":false,"checkable":false,"source":"native_accessibility",
            "bounds_array":bounds,"window_id":7,"showing-hint":false})
    }
    fn tree(c: &Contract, ns: Vec<Value>) -> Value {
        json!({"ok":true,"window_context":{"root":{"package":c.package},
            "selected_window":{"root":{"package":c.package},"focused":true,
                "display_id":0,"window_id":7,"bounds":[0,0,600,1000]},
            "snapshot_complete":true,"truncated":false},"nodes":ns})
    }
    fn card(c: &Contract, title: &str, y: i64, price: &str, bed: &str, size: &str) -> Vec<Value> {
        let mut root = node(c, "card", "", [0, y, 600, y + 300]);
        root["clickable"] = json!(true);
        let mut image = node(c, "listingImage", "", [0, y, 160, y + 130]);
        image["class"] = json!("android.widget.ImageView");
        vec![
            root,
            image,
            node(c, "address", title, [170, y, 590, y + 40]),
            node(c, "location", c.query, [170, y + 45, 590, y + 75]),
            node(c, "price", price, [170, y + 80, 590, y + 115]),
            node(c, "listingBeds", bed, [170, y + 120, 300, y + 155]),
            node(c, "size", size, [320, y + 120, 590, y + 155]),
        ]
    }
    fn results(c: &Contract) -> Value {
        let mut ns = vec![node(c, "locationLabel", c.query, [0, 0, 580, 60])];
        if c.city.is_some() {
            ns.extend(card(c, "望京西园四区", 100, "580万", "2室1厅", "86.4㎡"));
            ns.extend(card(
                c,
                "望京东园五区",
                500,
                "620万元",
                "2室2厅",
                "92平方米",
            ));
        } else {
            ns.extend(card(
                c,
                "123 Seventh Avenue #2",
                100,
                "$1,250,000",
                "2 Beds",
                "950 ft²",
            ));
            ns.extend(card(
                c,
                "456 Fifth Street #3",
                500,
                "$1,100,000",
                "2 Beds",
                "900 sqft",
            ));
        }
        tree(c, ns)
    }
    fn filter_tree(c: &Contract, selected_numbers: &[i8]) -> Value {
        let mut ns = vec![node(
            c,
            "bedroomHeading",
            if c.city.is_some() {
                "户型"
            } else {
                "Bedrooms"
            },
            [0, 0, 600, 50],
        )];
        for (i, (number, label)) in [(-1, "Any"), (1, "1 Bed"), (2, "2 Beds"), (3, "3 Beds")]
            .iter()
            .enumerate()
        {
            let mut n = node(
                c,
                &format!("bed-{number}"),
                label,
                [0, 60 + i as i64 * 55, 200, 100 + i as i64 * 55],
            );
            n["checkable"] = json!(true);
            n["checked"] = json!(selected_numbers.contains(number));
            ns.push(n);
        }
        tree(c, ns)
    }

    #[test]
    fn housing_complete_original_apk_sets_reject_partial_splits_and_other_identity() {
        for c in &CONTRACTS {
            let a = actual_source(c);
            require_application(&a).unwrap();
            let mut reversed = a.clone();
            reversed.apks.reverse();
            require_application(&reversed).unwrap();
            for kind in 0..9 {
                let mut bad = a.clone();
                match kind {
                    0 => bad.apks[0].sha256 = "0".repeat(64),
                    1 => bad.apks[0].bytes += 1,
                    2 => {
                        bad.apks.pop();
                    }
                    3 => bad.apks.push(bad.apks[0].clone()),
                    4 => bad.version_code += 1,
                    5 => bad.user = 10,
                    6 => bad.uid = 2000,
                    7 => bad.apks[0].name = "configuration-only.apk".into(),
                    _ => bad.package.push_str(".other"),
                }
                assert!(
                    require_application(&bad).is_err(),
                    "{} mutation {kind}",
                    c.package
                );
            }
        }
        assert!(!supports("com.lianjia.link"));
        assert!(!supports("com.zillow.android.zillowmap"));
    }
    #[test]
    fn housing_prices_keep_currency_and_monthly_or_total_units() {
        assert_eq!(money("580万"), money("580.0000万元"));
        assert_eq!(money("580万").unwrap().minor, 580_000_000);
        assert_eq!(
            money("$1,250,000").unwrap(),
            Money {
                currency: "USD",
                minor: 125_000_000,
                period: "total"
            }
        );
        assert_eq!(
            money("8500元/月").unwrap(),
            Money {
                currency: "CNY",
                minor: 850_000,
                period: "monthly"
            }
        );
        assert_eq!(
            money("$5,000 /mo").unwrap(),
            Money {
                currency: "USD",
                minor: 500_000,
                period: "monthly"
            }
        );
        assert_ne!(money("$5,000"), money("$5,000/mo"));
        for wrong in [
            "$0",
            "580",
            "USD 580",
            "1000/mo",
            "$1-2",
            "580万起",
            "580-600万",
            "$1.999",
            "$1,25,000",
            "$1,,000",
            "$-1",
            "$1.2.3",
            "$18446744073709551615",
            "联系经纪人",
        ] {
            assert!(money(wrong).is_none(), "{wrong}");
        }
    }
    #[test]
    fn housing_room_and_area_parsers_reject_labels_ranges_and_ambiguous_units() {
        assert_eq!(beds("2室1厅"), Some(2));
        assert_eq!(beds("2 Beds"), Some(2));
        assert_eq!(beds("Studio"), None);
        assert_eq!(beds("12 beds"), None);
        assert_eq!(beds("2-3 beds"), None);
        assert_eq!(beds("2 baths"), None);
        assert_eq!(area("86.4㎡"), Some((8640, "m2")));
        assert_eq!(area("950 ft²"), Some((95000, "ft2")));
        assert_eq!(area("950 square feet"), Some((95000, "ft2")));
        for v in ["86.4", "0㎡", "86-90㎡", "$950 sqft", "86.123㎡"] {
            assert_eq!(area(v), None, "{v}");
        }
    }
    #[test]
    fn housing_public_addresses_do_not_accept_contact_or_similar_word_decoys() {
        assert!(address("望京西园四区", &CONTRACTS[0]));
        assert!(address("123 Seventh Avenue #2", &CONTRACTS[1]));
        assert!(address("456 Fifth St. #3", &CONTRACTS[1]));
        for s in [
            "123 studio",
            "Contact 123 Main Street",
            "123 Main Street Tour",
            "Sign in",
            "Schedule a tour",
            "123 stock listing",
        ] {
            assert!(!address(s, &CONTRACTS[1]), "{s}");
        }
        assert!(!address("望京路联系经纪人", &CONTRACTS[0]));
        assert!(!public_location("South Park Slope", &CONTRACTS[1]));
        assert!(public_location("Park Slope, Brooklyn", &CONTRACTS[1]));
        assert!(!same_title("123 Main Street #2", "123 Main Street #3"));
    }
    #[test]
    fn housing_listing_parser_joins_each_actual_address_price_beds_area_location_and_image() {
        for c in &CONTRACTS {
            let body = results(c);
            let ls = listings(&body, c).unwrap();
            assert_eq!(ls.len(), 2);
            assert_eq!(ls[0].beds, 2);
            assert!(ls[0].area.is_some());
            assert!(query_visible(&body, c).unwrap());
            let mut wrong = body.clone();
            wrong["nodes"][0]["text"] = json!("unrelated location");
            assert!(!query_visible(&wrong, c).unwrap());
            let mut wrong = body.clone();
            let target = wrong["nodes"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|n| text(n, "resource-id").ends_with(":id/location"))
                .unwrap();
            target["text"] = json!("unrelated location");
            if c.city.is_some() {
                // The Chinese address itself still names the declared public
                // neighborhood. Remove that independent match too before
                // asserting an actually mismatched result.
                assert_eq!(listings(&wrong, c).unwrap().len(), 2);
                wrong["nodes"]
                    .as_array_mut()
                    .unwrap()
                    .iter_mut()
                    .find(|n| text(n, "resource-id").ends_with(":id/address"))
                    .unwrap()["text"] = json!("朝阳西园四区");
            }
            assert_eq!(listings(&wrong, c).unwrap().len(), 1);
            let mut wrong = body.clone();
            let image = wrong["nodes"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|n| text(n, "resource-id").ends_with(":id/listingImage"))
                .unwrap();
            image["class"] = json!("android.widget.TextView");
            image["resource-id"] = json!("not_image");
            assert_eq!(listings(&wrong, c).unwrap().len(), 1);
            let mut wrong = body.clone();
            let extra = node(
                c,
                "other_price",
                if c.city.is_some() {
                    "610万"
                } else {
                    "$2,000,000"
                },
                [170, 250, 590, 280],
            );
            wrong["nodes"].as_array_mut().unwrap().push(extra);
            assert_eq!(listings(&wrong, c).unwrap().len(), 1);
        }
    }
    #[test]
    fn housing_partial_foreign_or_ambiguous_trees_cannot_supply_a_listing() {
        let c = &CONTRACTS[1];
        let good = results(c);
        for kind in 0..3 {
            let mut bad = good.clone();
            match kind {
                0 => bad["window_context"]["truncated"] = json!(true),
                1 => bad["window_context"]["selected_window"]["root"]["package"] = json!("foreign"),
                _ => bad["window_context"]["snapshot_complete"] = json!(false),
            }
            assert!(listings(&bad, c).is_err());
        }
        let mut repeated = good.clone();
        let address = repeated["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|n| text(n, "text") == "123 Seventh Avenue #2")
            .unwrap()
            .clone();
        repeated["nodes"].as_array_mut().unwrap().push(address);
        assert_eq!(listings(&repeated, c).unwrap().len(), 1);
        let mut foreign = good.clone();
        for n in foreign["nodes"].as_array_mut().unwrap() {
            if text(n, "resource-id").ends_with(":id/address") {
                n["package"] = json!("foreign");
            }
        }
        assert!(listings(&foreign, c).unwrap().is_empty());
    }
    #[test]
    fn housing_detail_requires_same_address_price_bedroom_area_and_image_node() {
        let c = &CONTRACTS[1];
        let chosen = listings(&results(c), c).unwrap().remove(0);
        let ns = card(c, &chosen.title, 100, "$1,250,000", "2 Beds", "950 ft²");
        let good = tree(c, ns);
        let d = detail(&good, c, &chosen).unwrap().unwrap();
        assert_eq!(d.price, chosen.price);
        assert_eq!(d.area, chosen.area.unwrap());
        let mut conflicting = good.clone();
        conflicting["nodes"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|n| text(n, "resource-id").ends_with(":id/price"))
            .unwrap()["text"] = json!("$1,300,000");
        conflicting["nodes"]
            .as_array_mut()
            .unwrap()
            .push(node(c, "recommended_price", "$1,250,000", [0, 700, 400, 740]));
        assert!(
            detail(&conflicting, c, &chosen).unwrap().is_none(),
            "a separate recommendation price cannot qualify the changed main listing price"
        );
        for (field, value) in [
            ("address", "124 Seventh Avenue #2"),
            ("price", "$1,250,001"),
            ("listingBeds", "3 Beds"),
            ("size", "960 ft²"),
        ] {
            let mut bad = good.clone();
            bad["nodes"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|n| text(n, "resource-id").ends_with(&format!(":id/{field}")))
                .unwrap()["text"] = json!(value);
            assert!(detail(&bad, c, &chosen).unwrap().is_none(), "{field}");
        }
    }
    #[test]
    fn housing_bedroom_filter_tracks_owned_checkbox_and_exact_prior_radio_choice() {
        let c = &CONTRACTS[1];
        let original = options(&filter_tree(c, &[-1]), c).unwrap();
        let changed = options(&filter_tree(c, &[2]), c).unwrap();
        assert_eq!(
            changed_facet(&original, &changed).unwrap(),
            Some("Any".into())
        );
        let none = options(&filter_tree(c, &[]), c).unwrap();
        assert_eq!(changed_facet(&none, &changed).unwrap(), None);
        assert_eq!(options(&filter_tree(c, &[-1]), c).unwrap(), original);
        assert!(changed_facet(&changed, &changed).is_err());
        let mut injected = changed.clone();
        injected[0].label = "different option".into();
        assert!(changed_facet(&original, &injected).is_err());
        assert!(changed_facet(&original, &options(&filter_tree(c, &[1, 2]), c).unwrap()).is_err());
        let ambiguous = options(&filter_tree(c, &[-1, 1]), c).unwrap();
        assert!(changed_facet(&ambiguous, &changed).is_err());
    }
    #[test]
    fn housing_filter_requires_real_context_unique_options_and_explicit_states() {
        let c = &CONTRACTS[1];
        let good = filter_tree(c, &[-1]);
        let mut wrong = good.clone();
        wrong["nodes"][0]["text"] = json!("Bathrooms");
        assert!(options(&wrong, c).is_err());
        let mut duplicate = good.clone();
        let two = duplicate["nodes"][3].clone();
        duplicate["nodes"].as_array_mut().unwrap().push(two);
        assert!(options(&duplicate, c).is_err());
        let mut unknown = good.clone();
        unknown["nodes"][3]["checked"] = Value::Null;
        assert!(options(&unknown, c).is_err());
        let mut password = good.clone();
        password["nodes"][3]["password"] = json!(true);
        assert!(options(&password, c).is_err());
    }
    #[test]
    fn housing_money_unit_needs_actual_adjacent_source_price_and_rejects_advertised_average() {
        let c = &CONTRACTS[0];
        let p = node(c, "listing_price", "580", [100, 100, 220, 140]);
        let unit = node(c, "price_unit", "万", [222, 100, 250, 140]);
        assert_eq!(
            actual_prices(&[&p, &unit], c),
            BTreeSet::from([money("580万").unwrap()])
        );
        let mut far = unit.clone();
        far["bounds_array"] = json!([400, 300, 500, 340]);
        assert!(actual_prices(&[&p, &far], c).is_empty());
        let mut average = p.clone();
        average["resource-id"] = json!(format!("{}:id/avg_price", c.package));
        assert!(actual_prices(&[&average, &unit], c).is_empty());
    }
    #[test]
    fn housing_image_matching_needs_real_nonblank_bounded_decoded_pixels() {
        let rect = Rect([0, 0, 64, 64]);
        for gray in [0, 128, 240, 255] {
            assert!(sample(&vec![gray; 64 * 64 * 3], 64, 64, rect, rect).is_err());
        }
        let mut rgb = vec![255; 64 * 64 * 3];
        for y in 0..64 {
            for x in 0..64 {
                let i = 3 * (y * 64 + x);
                rgb[i] = (x * 4) as u8;
                rgb[i + 1] = (y * 4) as u8;
                rgb[i + 2] = 40;
            }
        }
        let a = sample(&rgb, 64, 64, rect, rect).unwrap();
        assert!(image_matches(&a, &a));
        assert_eq!(a.sha256, digest(&a.rgb));
        let other = rgb.iter().map(|v| 255 - v).collect::<Vec<_>>();
        assert!(!image_matches(
            &a,
            &sample(&other, 64, 64, rect, rect).unwrap()
        ));
        assert!(sample(&rgb, 63, 64, rect, rect).is_err());
        assert!(sample(&rgb, 64, 64, rect, Rect([0, 0, 65, 64])).is_err());
        assert!(sample(&rgb, 64, 64, rect, Rect([0, 0, 20, 20])).is_err());
    }
    #[test]
    fn housing_preserves_existing_editor_and_disables_external_effect_controls() {
        assert!(empty_input(
            &json!({"showing-hint":false,"value":"","text":""})
        ));
        assert!(empty_input(
            &json!({"showing-hint":true,"value":null,"text":"Search","hint":"Search"})
        ));
        assert!(!empty_input(
            &json!({"showing-hint":true,"value":"existing search","text":"Search","hint":"Search"})
        ));
        assert!(!empty_input(
            &json!({"showing-hint":false,"value":"existing","text":"existing"})
        ));
        let c = &CONTRACTS[1];
        for label in [
            "Contact agent",
            "Schedule tour",
            "Send",
            "Message",
            "Apply now",
            "Sign in",
            "Save search",
            "预约看房",
            "登录",
        ] {
            let n = node(c, "search_button", label, [0, 0, 200, 60]);
            assert!(!role_matches(&n, c, Role::Submit), "{label}");
            assert!(!role_matches(&n, c, Role::Apply), "{label}");
        }
    }
    #[test]
    fn housing_fixed_budgets_bound_real_commands_captures_and_deadline() {
        assert_eq!(additional_window_seconds(), 8560);
        assert_eq!(second_business_seconds(), 2910);
        assert_eq!(first_max_extra_ui_commands(), 179);
        assert_eq!(reopen_max_ui_commands(), 93);
        assert!(first_max_extra_ui_commands() + 39 < 512);
        assert!(reopen_max_ui_commands() + 39 < 512);
        assert!(RETAINED_REPLY_BYTES * 2 < 2_147_483_648);
        assert!(before(Instant::now()).is_err());
        assert_eq!(SOURCE_SELECTION_SHA256.len(), 64);
        assert_eq!(SOURCE_READBACK_SHA256.len(), 64);
    }
}
