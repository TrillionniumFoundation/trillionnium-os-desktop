//! Source-fixed, non-submitting Family control selection.
//!
//! This module only compares already parsed native observations. Its functions
//! cannot construct a live UI session, a Main fact, or an acceptance assertion.
use super::super::need;
use crate::control::application_probe::ApplicationInspection;
use crate::native_application_ui_protocol as wire;
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

const PLAN_BYTES: &[u8] = include_bytes!("native_family_controls.json");
pub(super) const MAX_NAVIGATIONS: usize = 2;
pub(super) const MAX_TEXT_BYTES: usize = 4_096;

#[derive(Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(super) enum Mode {
    Text,
    Number,
    ReadOnlyPanel,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Plan {
    pub package: String,
    pub version_code: u64,
    pub base_apk_sha256: String,
    pub source_resource_sha256: String,
    pub source_literal_sha256: Option<String>,
    pub mode: Mode,
    pub editor_ids: Vec<String>,
    pub editor_hints: Vec<String>,
    pub opener_ids: Vec<String>,
    pub opener_labels: Vec<String>,
    pub panel_ids: Vec<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Plans {
    schema: String,
    selected_sha256: String,
    packages: Vec<Plan>,
}
pub(super) fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
}
pub(super) fn all_plans() -> Result<Vec<Plan>, String> {
    let source: Plans = serde_json::from_slice(PLAN_BYTES).map_err(|e| e.to_string())?;
    need(
        source.schema == "droidloom.selected-family-controls.v1"
            && source.selected_sha256
                == "524cd083ee1362911078232eac99977049ad6238380732f0c0e04a0c6b0fed43"
            && source.packages.len() == 31,
        "compiled Family control roster or selected-material commitment differs",
    )?;
    let mut names = BTreeSet::new();
    for p in &source.packages {
        need(
            names.insert(p.package.clone())
                && p.version_code > 0
                && sha(&p.base_apk_sha256)
                && sha(&p.source_resource_sha256)
                && p.source_literal_sha256.as_deref().is_none_or(sha)
                && crate::engine_custody::selected_package(&p.package)
                && ![
                    "com.android.calendar",
                    "com.android.camera2",
                    "com.android.contacts",
                    "com.android.deskclock",
                    "com.android.documentsui",
                    "com.android.gallery3d",
                    "com.android.settings",
                    "com.ihg.apps.android",
                ]
                .contains(&p.package.as_str()),
            "compiled Family source identity is duplicated or incomplete",
        )?;
        for list in [&p.editor_ids, &p.opener_ids, &p.panel_ids] {
            need(
                list.len() <= 16
                    && list.iter().collect::<BTreeSet<_>>().len() == list.len()
                    && list.iter().all(|id| {
                        id.starts_with(&(p.package.clone() + ":id/"))
                            && id.len() <= 512
                            && !id.contains('\0')
                    }),
                "compiled Family resource selectors exceed their fixed package or bound",
            )?;
        }
        for list in [&p.editor_hints, &p.opener_labels] {
            need(
                list.len() <= 8
                    && list.iter().collect::<BTreeSet<_>>().len() == list.len()
                    && list
                        .iter()
                        .all(|s| !s.is_empty() && s.len() <= 128 && !s.contains('\0')),
                "compiled Family literal selectors differ",
            )?;
        }
        need(
            match p.mode {
                Mode::ReadOnlyPanel => !p.panel_ids.is_empty(),
                Mode::Text | Mode::Number => !p.editor_ids.is_empty() || !p.editor_hints.is_empty(),
            },
            "compiled Family plan has no actual selected-source control candidate",
        )?;
    }
    Ok(source.packages)
}
pub(super) fn plan(actual: &ApplicationInspection) -> Result<Plan, String> {
    let p = all_plans()?
        .into_iter()
        .find(|p| p.package == actual.package)
        .ok_or("package is outside the fixed thirty-one Family controls")?;
    let base: Vec<_> = actual
        .apks
        .iter()
        .filter(|a| a.name == "base.apk")
        .collect();
    need(
        actual.user == 0
            && actual.version_code == p.version_code
            && base.len() == 1
            && base[0].sha256 == p.base_apk_sha256,
        "Family control source does not match the actually inspected base APK/version",
    )?;
    Ok(p)
}
pub(super) fn plan_digest() -> String {
    hash(PLAN_BYTES)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum Locator {
    Resource(String),
    Description(String),
    Text(String),
    UniqueEditable,
}
impl Locator {
    pub fn selector(&self) -> Result<wire::Selector, String> {
        let result = match self {
            Self::Resource(v) => wire::Selector::resource_id(v),
            Self::Description(v) => wire::Selector::description(v),
            Self::Text(v) => wire::Selector::exact_text(v),
            Self::UniqueEditable => Ok(wire::Selector::editable()),
        };
        result
            .map(wire::Selector::enabled)
            .map_err(|e| e.to_string())
    }
    pub fn comparison(&self) -> Value {
        match self {
            Self::Resource(v) => json!({"kind":"resource_id","value":v}),
            Self::Description(v) => json!({"kind":"content_description","value":v}),
            Self::Text(v) => json!({"kind":"text","value":v}),
            Self::UniqueEditable => json!({"kind":"unique_editable_with_source_hint"}),
        }
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct Control {
    pub locator: Locator,
    pub resource_id: String,
    pub class: String,
    pub hint: String,
    pub value: String,
    pub bounds: [u32; 4],
    pub window_id: i64,
}
fn text<'a>(node: &'a Value, key: &str) -> Result<&'a str, String> {
    node.get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("native control {key} is absent"))
}
pub(super) fn rect(value: &Value) -> Result<[u32; 4], String> {
    let a = value
        .as_array()
        .filter(|v| v.len() == 4)
        .ok_or("native control rectangle absent")?;
    let mut out = [0; 4];
    for (n, v) in out.iter_mut().zip(a) {
        *n = v
            .as_u64()
            .and_then(|v| u32::try_from(v).ok())
            .ok_or("negative native bounds")?;
    }
    need(
        out[0] < out[2] && out[1] < out[3] && out[2] <= 8192 && out[3] <= 8192,
        "native control bounds empty or too large",
    )?;
    Ok(out)
}
fn usable(n: &Value, package: &str, window: i64) -> bool {
    n["package"] == package
        && n["window_id"].as_i64() == Some(window)
        && n["visible"] == true
        && n["enabled"] == true
        && n["password"] == false
}
pub(super) fn nodes<'a>(body: &'a Value, package: &str) -> Result<(&'a [Value], i64), String> {
    let c = &body["window_context"];
    let w = c["selected_window"]["window_id"]
        .as_i64()
        .ok_or("selected native window absent")?;
    let n = body["nodes"]
        .as_array()
        .ok_or("complete native tree absent")?;
    need(
        c["root"]["package"] == package
            && c["snapshot_complete"] == true
            && c["truncated"] == false
            && c["null_child_count"] == 0
            && !n.is_empty()
            && n.len() <= 2_000
            && c["visible_count"].as_u64() == Some(n.len() as u64),
        "Family needs a complete actual native tree of its owned foreground window",
    )?;
    Ok((n, w))
}
pub(super) fn editable_value(n: &Value) -> Result<String, String> {
    need(
        n["editable"] == true && n["password"] == false,
        "Family input is not a non-password editor",
    )?;
    let value = text(n, "value")?;
    need(
        value.len() <= MAX_TEXT_BYTES && !value.contains('\0'),
        "original native input exceeds the normal helper bound",
    )?;
    // The selected helper's editableValue() separates an empty input's hint
    // from its actual text. No empty-value precondition is imposed here.
    if n["showing-hint"] == true {
        need(
            value.is_empty(),
            "native hint was reported as an entered value",
        )?;
    } else {
        need(
            text(n, "text")? == value,
            "native text and actual editable value disagree",
        )?;
    }
    Ok(value.into())
}
fn control(n: &Value, p: &Plan, locator: Locator, window: i64) -> Result<Control, String> {
    need(
        usable(n, &p.package, window),
        "Family editor is not usable in its actual selected window",
    )?;
    Ok(Control {
        locator,
        resource_id: text(n, "resource-id")?.into(),
        class: text(n, "class")?.into(),
        hint: text(n, "hint")?.into(),
        value: editable_value(n)?,
        bounds: rect(&n["bounds_array"])?,
        window_id: window,
    })
}
pub(super) fn editor(body: &Value, p: &Plan) -> Result<Option<Control>, String> {
    let (rows, window) = nodes(body, &p.package)?;
    let all_editors: Vec<_> = rows
        .iter()
        .filter(|n| usable(n, &p.package, window) && n["editable"] == true)
        .collect();
    let mut found = Vec::new();
    for n in &all_editors {
        let id = text(n, "resource-id")?;
        let locator = if p.editor_ids.iter().any(|v| v == id) {
            Some(Locator::Resource(id.into()))
        } else if all_editors.len() == 1
            && p.editor_hints
                .iter()
                .any(|v| Some(v.as_str()) == n["hint"].as_str())
        {
            // A missing/obfuscated resource id is accepted only for this
            // selected-source literal hint and the sole actual editor.
            Some(Locator::UniqueEditable)
        } else {
            None
        };
        if let Some(locator) = locator {
            found.push(control(n, p, locator, window)?);
        }
    }
    need(
        found.len() <= 1,
        "multiple source-matching Family editors are visible",
    )?;
    Ok(found.pop())
}
pub(super) fn readback(
    body: &Value,
    p: &Plan,
    prior: &Control,
    expected: &str,
    same_window: bool,
) -> Result<Control, String> {
    let rows = body["matches"]
        .as_array()
        .ok_or("actual input readback has no match array")?;
    need(rows.len() == 1, "input readback is missing or ambiguous")?;
    let window = body["window_context"]["selected_window"]["window_id"]
        .as_i64()
        .ok_or("readback window absent")?;
    let now = control(&rows[0], p, prior.locator.clone(), window)?;
    need(
        now.value == expected
            && now.resource_id == prior.resource_id
            && now.class == prior.class
            && (!same_window || now.window_id == prior.window_id),
        "exact native input value/control readback changed",
    )?;
    Ok(now)
}
pub(super) fn opener(
    body: &Value,
    p: &Plan,
    already: &[Locator],
) -> Result<Option<Locator>, String> {
    let (rows, window) = nodes(body, &p.package)?;
    // A Search button alongside an existing editor may submit the query.
    // Such a button is never used as a fallback navigation target.
    if rows.iter().any(|n| {
        n["package"] == p.package
            && n["window_id"].as_i64() == Some(window)
            && n["visible"] == true
            && n["enabled"] == true
            && n["editable"] == true
    }) {
        return Ok(None);
    }
    let mut found = Vec::new();
    for n in rows.iter().filter(|n| {
        usable(n, &p.package, window) && n["clickable"] == true && n["editable"] == false
    }) {
        let id = text(n, "resource-id")?;
        let loc = if p.opener_ids.iter().any(|v| v == id) {
            Some(Locator::Resource(id.into()))
        } else if p
            .opener_labels
            .iter()
            .any(|v| Some(v.as_str()) == n["content-desc"].as_str())
            && (p.mode == Mode::ReadOnlyPanel
                || matches!(
                    n["class"].as_str(),
                    Some("android.widget.ImageButton" | "android.widget.ImageView")
                ))
        {
            Some(Locator::Description(text(n, "content-desc")?.into()))
        } else if p.mode == Mode::ReadOnlyPanel
            && p.opener_labels
                .iter()
                .any(|v| Some(v.as_str()) == n["text"].as_str())
        {
            Some(Locator::Text(text(n, "text")?.into()))
        } else {
            None
        };
        if let Some(l) = loc {
            if !already.contains(&l) {
                found.push(l)
            }
        }
    }
    // Count actual nodes, including duplicate descriptions/ids. A repeated
    // locator must be rejected before the helper could perform any click.
    found.sort_by_key(|l| l.comparison().to_string());
    need(
        found.len() <= 1,
        "Family safe navigation target is ambiguous",
    )?;
    Ok(found.pop())
}
pub(super) fn canary(p: &Plan, original: &str) -> &'static str {
    match p.mode {
        Mode::Number => {
            if original == "20517" {
                "20529"
            } else {
                "20517"
            }
        }
        Mode::Text | Mode::ReadOnlyPanel => {
            if original == "p4 probe 17" {
                "p4 probe 29"
            } else {
                "p4 probe 17"
            }
        }
    }
}
pub(super) fn panel(body: &Value, p: &Plan) -> Result<Option<Value>, String> {
    let (rows, window) = nodes(body, &p.package)?;
    let mut result = Vec::new();
    for n in rows
        .iter()
        .filter(|n| usable(n, &p.package, window) && n["editable"] == false)
    {
        if p.panel_ids
            .iter()
            .any(|id| Some(id.as_str()) == n["resource-id"].as_str())
        {
            result.push(
                json!({"resource_id":text(n,"resource-id")?,"class":text(n,"class")?,
                "text":text(n,"text")?,"description":text(n,"content-desc")?,
                "selected":n["selected"],"checked":n["checked"],"enabled":n["enabled"]}),
            );
        }
    }
    if result.is_empty() {
        return Ok(None);
    }
    need(
        result.len() <= 128
            && p.panel_ids
                .iter()
                .all(|id| result.iter().any(|n| n["resource_id"] == *id)),
        "read-only source panel is incomplete",
    )?;
    result.sort_by_key(Value::to_string);
    Ok(Some(Value::Array(result)))
}
pub(super) fn region_pixels(
    rgb: &[u8],
    width: u32,
    height: u32,
    window: &Value,
    bounds: [u32; 4],
) -> Result<Vec<u8>, String> {
    let b = &window["bounds"];
    let origin = [
        b["left"]
            .as_u64()
            .and_then(|v| u32::try_from(v).ok())
            .ok_or("scoped window origin absent")?,
        b["top"]
            .as_u64()
            .and_then(|v| u32::try_from(v).ok())
            .ok_or("scoped window origin absent")?,
    ];
    need(
        width > 0
            && height > 0
            && rgb.len() == width as usize * height as usize * 3
            && bounds[0] >= origin[0]
            && bounds[1] >= origin[1]
            && bounds[0] < bounds[2]
            && bounds[1] < bounds[3],
        "source control is outside the decoded owned window",
    )?;
    let r = [
        bounds[0] - origin[0],
        bounds[1] - origin[1],
        bounds[2] - origin[0],
        bounds[3] - origin[1],
    ];
    need(
        r[0] < r[2] && r[1] < r[3] && r[2] <= width && r[3] <= height,
        "source control crop exceeds actual scoped pixels",
    )?;
    let bytes = (r[2] - r[0]) as usize * (r[3] - r[1]) as usize * 3;
    need(
        bytes <= 4 * 1024 * 1024,
        "actual input control exceeds the finite private crop bound",
    )?;
    let mut out = Vec::with_capacity(bytes);
    for y in r[1]..r[3] {
        let start = (y as usize * width as usize + r[0] as usize) * 3;
        let end = (y as usize * width as usize + r[2] as usize) * 3;
        out.extend_from_slice(&rgb[start..end]);
    }
    Ok(out)
}

pub(super) fn rendered_change(
    before: &[u8],
    after: &[u8],
    bounds: [u32; 4],
) -> Result<Value, String> {
    need(
        bounds[0] < bounds[2] && bounds[1] < bounds[3],
        "native input pixel comparison rectangle is empty or reversed",
    )?;
    let width = (bounds[2] - bounds[0]) as usize;
    let height = (bounds[3] - bounds[1]) as usize;
    need(
        width > 0
            && height > 0
            && before.len() == width * height * 3
            && after.len() == before.len(),
        "native input pixel comparison dimensions differ",
    )?;
    let mut changed = 0_usize;
    let mut columns = BTreeSet::new();
    let mut rows = BTreeSet::new();
    for (i, (a, b)) in before
        .chunks_exact(3)
        .zip(after.chunks_exact(3))
        .enumerate()
    {
        if a.iter()
            .zip(b)
            .map(|(x, y)| i32::from(*x).abs_diff(i32::from(*y)))
            .sum::<u32>()
            >= 48
        {
            changed += 1;
            columns.insert(i % width);
            rows.insert(i / width);
        }
    }
    need(
        changed >= 24 && columns.len() >= 6 && rows.len() >= 3,
        "actual source input has no rendered change beyond a caret or negligible pixel noise",
    )?;
    Ok(
        json!({"changed_pixels":changed,"changed_columns":columns.len(),"changed_rows":rows.len(),
        "before_region_sha256":hash(before),"after_region_sha256":hash(after)}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn selected() -> Plan {
        all_plans()
            .unwrap()
            .into_iter()
            .find(|p| p.package == "com.android.messaging")
            .unwrap()
    }
    fn node(p: &Plan, value: &str) -> Value {
        json!({"package":p.package,"window_id":7,"visible":true,"enabled":true,
            "password":false,"editable":true,"clickable":true,
            "resource-id":p.editor_ids[0],"class":"android.widget.EditText",
            "hint":"Search","showing-hint":false,"value":value,"text":value,
            "content-desc":"","bounds_array":[10,20,90,50]})
    }
    fn tree(p: &Plan, rows: Vec<Value>) -> Value {
        json!({"nodes":rows,"window_context":{"selected_window":{"window_id":7},
            "root":{"package":p.package},"snapshot_complete":true,"truncated":false,
            "null_child_count":0,"visible_count":rows.len()}})
    }
    fn found(n: Value) -> Value {
        json!({"matches":[n],"window_context":{"selected_window":{"window_id":7}}})
    }
    #[test]
    fn family_controls_compiled_roster_is_selected_exact_and_non_transactional() {
        let rows = all_plans().unwrap();
        assert_eq!(rows.len(), 31);
        assert_eq!(
            rows.iter()
                .filter(|p| p.mode == Mode::ReadOnlyPanel)
                .map(|p| p.package.as_str())
                .collect::<Vec<_>>(),
            vec!["com.google.android.gms"]
        );
        let dialer = rows
            .iter()
            .find(|p| p.package == "com.android.dialer")
            .unwrap();
        assert_eq!(dialer.mode, Mode::Number);
        assert!(
            !dialer
                .opener_ids
                .iter()
                .any(|id| id.ends_with("/floating_action_button"))
        );
        assert!(rows.iter().all(|p| {
            p.opener_ids
                .iter()
                .all(|id| !id.ends_with("/send") && !id.ends_with("/call") && !id.ends_with("/pay"))
        }));
    }
    #[test]
    fn family_controls_preserve_actual_nonempty_unicode_and_separate_hint() {
        let p = selected();
        let original = "已有 café 🧪";
        let n = node(&p, original);
        assert_eq!(editable_value(&n).unwrap(), original);
        let mut hint = node(&p, "");
        hint["showing-hint"] = true.into();
        hint["text"] = "Search".into();
        assert_eq!(editable_value(&hint).unwrap(), "");
        hint["value"] = "Search".into();
        assert!(editable_value(&hint).is_err());
        let mut password = n.clone();
        password["password"] = true.into();
        assert!(editable_value(&password).is_err());
        let mut changed = n;
        changed["text"] = "concurrent value".into();
        assert!(editable_value(&changed).is_err());
        assert_ne!(canary(&p, original), original);
        assert_ne!(canary(&p, "p4 probe 17"), "p4 probe 17");
    }
    #[test]
    fn family_controls_reject_ambiguous_or_changed_actual_editor() {
        let p = selected();
        let n = node(&p, "old");
        let selected = editor(&tree(&p, vec![n.clone()]), &p).unwrap().unwrap();
        assert!(editor(&tree(&p, vec![n.clone(), n.clone()]), &p).is_err());
        let mut unknown = n.clone();
        unknown["resource-id"] = "".into();
        unknown["hint"] = "unproven".into();
        assert!(
            editor(&tree(&p, vec![unknown.clone()]), &p)
                .unwrap()
                .is_none()
        );
        unknown["hint"] = "Search".into();
        assert_eq!(
            editor(&tree(&p, vec![unknown.clone()]), &p)
                .unwrap()
                .unwrap()
                .locator,
            Locator::UniqueEditable
        );
        let mut another = unknown.clone();
        another["hint"] = "Other".into();
        assert!(
            editor(&tree(&p, vec![unknown, another]), &p)
                .unwrap()
                .is_none()
        );
        assert!(readback(&found(n.clone()), &p, &selected, "new", true).is_err());
        let mut foreign = n.clone();
        foreign["resource-id"] = "com.android.messaging:id/other".into();
        assert!(readback(&found(foreign), &p, &selected, "old", true).is_err());
        let mut other_window = found(n);
        other_window["window_context"]["selected_window"]["window_id"] = 8.into();
        assert!(readback(&other_window, &p, &selected, "old", true).is_err());
    }
    #[test]
    fn family_controls_navigation_never_uses_submit_text_or_duplicate_targets() {
        let p = selected();
        let editor = node(&p, "existing query");
        let mut search = node(&p, "");
        search["resource-id"] = "".into();
        search["editable"] = false.into();
        search["class"] = "android.widget.Button".into();
        search["text"] = "Search".into();
        assert!(
            opener(&tree(&p, vec![search.clone()]), &p, &[])
                .unwrap()
                .is_none()
        );
        search["content-desc"] = "Search".into();
        search["class"] = "android.widget.ImageButton".into();
        assert!(
            opener(&tree(&p, vec![search.clone()]), &p, &[])
                .unwrap()
                .is_some()
        );
        assert!(opener(&tree(&p, vec![search.clone(), search.clone()]), &p, &[]).is_err());
        assert!(
            opener(&tree(&p, vec![editor.clone(), search.clone()]), &p, &[])
                .unwrap()
                .is_none()
        );
        let mut password = editor;
        password["password"] = true.into();
        assert!(
            opener(&tree(&p, vec![password, search]), &p, &[])
                .unwrap()
                .is_none()
        );
    }
    #[test]
    fn family_controls_crop_is_only_actual_owned_window_and_native_bounds() {
        let rgb: Vec<u8> = (0..12 * 10 * 3).map(|n| (n % 251) as u8).collect();
        let window = json!({"bounds":{"left":10,"top":20}});
        let crop = region_pixels(&rgb, 12, 10, &window, [12, 22, 20, 26]).unwrap();
        assert_eq!(crop.len(), 8 * 4 * 3);
        assert_eq!(&crop[..24], &rgb[(2 * 12 + 2) * 3..(2 * 12 + 10) * 3]);
        for bounds in [
            [9, 22, 20, 26],
            [12, 22, 23, 26],
            [12, 22, 20, 31],
            [20, 22, 12, 26],
        ] {
            assert!(region_pixels(&rgb, 12, 10, &window, bounds).is_err());
        }
        assert!(region_pixels(&rgb[..rgb.len() - 1], 12, 10, &window, [12, 22, 20, 26]).is_err());
    }
    #[test]
    fn family_controls_rendered_input_requires_change_beyond_caret_and_noise() {
        let before = vec![0_u8; 8 * 20 * 3];
        let mut caret = before.clone();
        for y in 0..20 {
            caret[y * 8 * 3] = 255;
        }
        assert!(rendered_change(&before, &caret, [0, 0, 8, 20]).is_err());
        let mut real = before.clone();
        for y in 0..3 {
            for x in 0..8 {
                real[(y * 8 + x) * 3] = 255;
            }
        }
        let proof = rendered_change(&before, &real, [0, 0, 8, 20]).unwrap();
        assert_eq!(proof["changed_pixels"], 24);
        assert_eq!(proof["changed_columns"], 8);
        assert!(rendered_change(&before, &before, [0, 0, 8, 20]).is_err());
        assert!(rendered_change(&before, &real, [8, 0, 0, 20]).is_err());
        assert!(rendered_change(&before, &real[..real.len() - 1], [0, 0, 8, 20]).is_err());
    }
}
