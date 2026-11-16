//! Exact parsers for the already-deployed task-list and ActionRunner v2 formats.
//! No parser result authorizes input, adopts an old task, or grants UI acceptance.
use serde::{Deserialize, Serialize};
#[cfg(test)]
use std::collections::{BTreeMap, BTreeSet};

#[cfg(test)]
pub(super) const SETTINGS: &str = "com.android.settings";
#[cfg(test)]
const LIMIT: usize = 64 * 1024;

#[cfg(test)]
fn bounded(raw: &str) -> Result<(), String> {
    if raw.is_empty() || raw.len() > LIMIT || raw.contains('\0') {
        return Err("Settings observation input is empty, oversized or contains NUL".into());
    }
    Ok(())
}

#[cfg(test)]
fn field<'a>(raw: &'a str, name: &str) -> Result<&'a str, String> {
    let values: Vec<_> = raw
        .split_whitespace()
        .filter_map(|s| s.strip_prefix(name))
        .collect();
    match values.as_slice() {
        [value] => Ok(value),
        _ => Err(format!("missing or repeated task field {name}")),
    }
}

#[cfg(test)]
fn number(raw: &str) -> Result<u32, String> {
    if raw.is_empty() || !raw.bytes().all(|b| b.is_ascii_digit()) {
        return Err("invalid unsigned task field".into());
    }
    let value: u32 = raw.parse().map_err(|_| "task field overflow")?;
    if value > i32::MAX as u32 {
        return Err("task field exceeds Android signed interface".into());
    }
    Ok(value)
}

#[cfg(test)]
pub(super) fn component(raw: &str) -> Result<String, String> {
    if raw.len() > 512 {
        return Err("component exceeds bound".into());
    }
    let (package, activity) = raw.split_once('/').ok_or("component lacks activity")?;
    if package.is_empty()
        || activity.is_empty()
        || !package.contains('.')
        || !package
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._".contains(&b))
        || !activity
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._$".contains(&b))
    {
        return Err("invalid component characters".into());
    }
    Ok(if activity.starts_with('.') {
        format!("{package}/{package}{activity}")
    } else {
        raw.into()
    })
}

#[cfg(test)]
pub(super) fn resolved_component(raw: &str) -> Result<String, String> {
    bounded(raw)?;
    let lines: Vec<_> = raw.lines().filter(|s| !s.trim().is_empty()).collect();
    if lines.len() != 1 {
        return Err("Settings page resolver is ambiguous".into());
    }
    let value = component(lines[0].trim())?;
    if value.split_once('/').map(|p| p.0) != Some(SETTINGS) {
        return Err("Settings page resolves outside Settings".into());
    }
    Ok(value)
}

/// A bounded rectangle reported by Android, never inferred screen geometry.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
pub struct Bounds(pub [i32; 4]);

#[cfg(test)]
impl Bounds {
    fn valid(self) -> bool {
        let [l, t, r, b] = self.0;
        l >= 0
            && t >= 0
            && r > l
            && b > t
            && r <= 8192
            && b <= 8192
            && i64::from(r - l) * i64::from(b - t) <= 32 * 1024 * 1024
    }
    fn contains(self, other: Self) -> bool {
        let [l, t, r, b] = self.0;
        let [ol, ot, or, ob] = other.0;
        self.valid() && other.valid() && l <= ol && t <= ot && r >= or && b >= ob
    }
    fn parse(raw: &str) -> Result<Self, String> {
        let raw = raw
            .strip_prefix('[')
            .and_then(|s| s.strip_suffix(']'))
            .ok_or("task rectangle syntax differs")?;
        let (a, b) = raw
            .split_once("][")
            .ok_or("task rectangle lacks second corner")?;
        let (l, t) = a
            .split_once(',')
            .ok_or("task rectangle lacks first corner")?;
        let (r, b) = b
            .split_once(',')
            .ok_or("task rectangle lacks second corner")?;
        let parse = |s: &str| {
            s.parse::<i32>()
                .map_err(|_| "invalid task rectangle integer".to_owned())
        };
        let parsed = Self([parse(l)?, parse(t)?, parse(r)?, parse(b)?]);
        if parsed.0.iter().any(|n| !(-16384..=16384).contains(n)) {
            return Err("task rectangle exceeds bounds".into());
        }
        Ok(parsed)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
#[cfg(test)]
pub(super) struct Task {
    pub id: u32,
    pub component: String,
    pub user: u32,
    pub top: Option<String>,
    pub visible: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
#[cfg(test)]
pub(super) struct Root {
    pub display: u32,
    pub user: u32,
    pub bounds: Bounds,
    pub freeform: bool,
    pub tasks: Vec<Task>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
#[cfg(test)]
pub(super) struct Tasks(pub BTreeMap<u32, Root>);

#[cfg(test)]
impl Tasks {
    pub fn parse(raw: &str) -> Result<Self, String> {
        bounded(raw)?;
        let mut roots = BTreeMap::new();
        let mut ids = BTreeSet::new();
        let mut current = None;
        for line in raw.lines() {
            let trimmed = line.trim();
            if line.starts_with("RootTask id=") {
                let id = number(field(line, "id=")?)?;
                let root = Root {
                    display: number(field(line, "displayId=")?)?,
                    user: number(field(line, "userId=")?)?,
                    bounds: Bounds::parse(field(line, "bounds=")?)?,
                    freeform: false,
                    tasks: Vec::new(),
                };
                if id == 0 || roots.insert(id, root).is_some() {
                    return Err("duplicate or zero task root".into());
                }
                current = Some(id);
            } else if trimmed.starts_with("RootTask") {
                return Err("unparsed task root".into());
            } else if let Some(rest) = trimmed.strip_prefix("taskId=") {
                let root = roots
                    .get_mut(&current.ok_or("task precedes root")?)
                    .ok_or("missing root")?;
                let (id, fields) = rest.split_once(':').ok_or("unparsed task record")?;
                let id = number(id)?;
                if id == 0 || !ids.insert(id) {
                    return Err("duplicate or zero task id".into());
                }
                let name = component(
                    fields
                        .split_whitespace()
                        .next()
                        .ok_or("missing task component")?,
                )?;
                let top_fields: Vec<_> = fields
                    .split_whitespace()
                    .filter_map(|s| s.strip_prefix("topActivity="))
                    .collect();
                let top = match top_fields.as_slice() {
                    [] => None,
                    [s] => Some(component(
                        s.strip_prefix("ComponentInfo{")
                            .and_then(|s| s.strip_suffix('}'))
                            .ok_or("malformed task top activity")?,
                    )?),
                    _ => return Err("repeated top activity".into()),
                };
                let visible = match field(fields, "visible=")? {
                    "true" => true,
                    "false" => false,
                    _ => return Err("invalid task visibility".into()),
                };
                root.tasks.push(Task {
                    id,
                    component: name,
                    user: number(field(fields, "userId=")?)?,
                    top,
                    visible,
                });
            } else if trimmed.starts_with("taskId") {
                return Err("unparsed task line".into());
            }
            if line
                .split(|c: char| c.is_whitespace() || "{},".contains(c))
                .any(|s| s == "mWindowingMode=freeform")
            {
                roots
                    .get_mut(&current.ok_or("configuration precedes root")?)
                    .ok_or("missing root")?
                    .freeform = true;
            }
        }
        if roots.is_empty() || ids.is_empty() || roots.len() > 1024 || ids.len() > 2048 {
            return Err("unrecognized or oversized task snapshot".into());
        }
        Ok(Self(roots))
    }

    pub fn has_settings(&self) -> bool {
        self.0.values().flat_map(|r| &r.tasks).any(|t| {
            t.component.split_once('/').map(|p| p.0) == Some(SETTINGS)
                || t.top
                    .as_deref()
                    .and_then(|s| s.split_once('/'))
                    .map(|p| p.0)
                    == Some(SETTINGS)
        })
    }

    fn topology(
        &self,
    ) -> BTreeMap<u32, (u32, u32, Bounds, Vec<(u32, String, u32, Option<String>)>)> {
        self.0
            .iter()
            .map(|(id, r)| {
                (
                    *id,
                    (
                        r.display,
                        r.user,
                        r.bounds,
                        r.tasks
                            .iter()
                            .map(|t| (t.id, t.component.clone(), t.user, t.top.clone()))
                            .collect(),
                    ),
                )
            })
            .collect()
    }

    pub fn candidate_after(&self, before: &Self, id: u32) -> Result<TaskCandidate, String> {
        if before.has_settings()
            || before.0.contains_key(&id)
            || before.0.values().flat_map(|r| &r.tasks).any(|t| t.id == id)
        {
            return Err("Settings task was not absent before this launch".into());
        }
        let owned = self.candidate(id)?;
        let mut remaining = self.clone();
        remaining.0.remove(&id);
        if remaining.topology() != before.topology() || remaining.has_settings() {
            return Err("other task topology changed during Settings launch".into());
        }
        Ok(owned)
    }

    pub fn candidate(&self, id: u32) -> Result<TaskCandidate, String> {
        let root = self.0.get(&id).ok_or("owned root absent")?;
        let [task] = root.tasks.as_slice() else {
            return Err("owned root is not one leaf".into());
        };
        let top = task.top.clone().ok_or("owned task top activity absent")?;
        if root.display != 0
            || root.user != 0
            || !root.freeform
            || !root.bounds.valid()
            || task.id != id
            || task.user != 0
            || !task.visible
            || task.component.split_once('/').map(|p| p.0) != Some(SETTINGS)
            || top.split_once('/').map(|p| p.0) != Some(SETTINGS)
        {
            return Err("Settings task is not an exact visible freeform leaf".into());
        }
        Ok(TaskCandidate {
            id,
            component: task.component.clone(),
            top_activity: top,
            bounds: root.bounds,
        })
    }

    pub fn removed_to(&self, before: &Self, id: u32) -> bool {
        !self.0.contains_key(&id)
            && !self.0.values().flat_map(|r| &r.tasks).any(|t| t.id == id)
            && self.topology() == before.topology()
    }

    pub fn removal_pending(&self, before: &Self, owned: &TaskCandidate) -> Result<(), String> {
        let root = self
            .0
            .get(&owned.id)
            .ok_or("removed root still has an unowned child task")?;
        let mut others = self.clone();
        others.0.remove(&owned.id);
        if others.topology() != before.topology()
            || root.display != 0
            || root.user != 0
            || !root.freeform
            || root.bounds != owned.bounds
        {
            return Err("other task topology or owned root changed during removal".into());
        }
        if root.tasks.is_empty() {
            return Ok(());
        }
        let [task] = root.tasks.as_slice() else {
            return Err("removal target acquired foreign children".into());
        };
        if task.id != owned.id
            || task.user != 0
            || task.component != owned.component
            || task.top.as_deref() != Some(owned.top_activity.as_str())
        {
            return Err("removal target identity changed".into());
        }
        Ok(()) // Closing visibility may change; only readbacks follow this state.
    }
}

/// Structural task candidate only. Snapshot differences do not prove its creator
/// and never authorize cleanup of a real Android task.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TaskCandidate {
    /// New root and child task ID (the exact same leaf).
    pub id: u32,
    /// Base activity recorded by ActivityTaskManager.
    pub component: String,
    /// Actual completed top activity, allowing framework-resolved aliases.
    pub top_activity: String,
    /// Snapshot-reported bounds; no task creation or cleanup authority.
    pub bounds: Bounds,
}

#[cfg(test)]
pub(super) fn launch_task(raw: &str) -> Result<u32, String> {
    bounded(raw)?;
    if raw.split_whitespace().count() != 4 || raw.lines().count() != 1 {
        return Err("Settings native ACK differs".into());
    }
    for name in ["object=", "composer_display="] {
        field(raw, name)?
            .parse::<u64>()
            .map_err(|_| "invalid native ACK identity")?;
    }
    let task = number(field(raw, "task=")?)?;
    if number(field(raw, "android_display=")?)? != 0 || task == 0 {
        return Err("Settings native ACK task/display differs".into());
    }
    Ok(task)
}

/// One fresh WindowManager focus identity.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Focus {
    /// Opaque WindowManager token; not an accessibility connection ID.
    pub token: String,
    /// Focused activity in the observed Settings task candidate.
    pub component: String,
}

#[cfg(test)]
pub(super) fn focus(raw: &str, owned: &TaskCandidate) -> Result<Focus, String> {
    bounded(raw)?;
    let lines: Vec<_> = raw
        .lines()
        .filter(|s| s.contains("mCurrentFocus="))
        .collect();
    let [line] = lines.as_slice() else {
        return Err("ambiguous WindowManager current focus".into());
    };
    let value = line
        .trim()
        .strip_prefix("mCurrentFocus=Window{")
        .and_then(|s| s.strip_suffix('}'))
        .ok_or("unrecognized focused window")?;
    let fields: Vec<_> = value.split_whitespace().collect();
    let [token, user, activity] = fields.as_slice() else {
        return Err("focused window fields differ".into());
    };
    if token.is_empty()
        || token.len() > 32
        || !token.bytes().all(|b| b.is_ascii_hexdigit())
        || *user != "u0"
        || component(activity)? != owned.top_activity
    {
        return Err("focus is not the claimed Settings task activity".into());
    }
    Ok(Focus {
        token: token.to_ascii_lowercase(),
        component: component(activity)?,
    })
}

#[derive(Deserialize)]
#[cfg(test)]
struct RootMeta {
    present: bool,
    package: String,
    window_id: i32,
    bounds: Bounds,
    visible: bool,
}
#[derive(Deserialize)]
#[cfg(test)]
struct NativeWindow {
    display_id: u32,
    focused: bool,
    #[serde(rename = "type")]
    kind: u32,
    window_id: i32,
    bounds: Bounds,
    root: RootMeta,
}
#[derive(Deserialize)]
#[cfg(test)]
struct WindowContext {
    selected_window: NativeWindow,
    root: RootMeta,
    snapshot_complete: bool,
    semantic_controls_available: bool,
    truncated: bool,
    null_child_count: u32,
    visited_count: u32,
    visible_count: u32,
    tree_status: String,
}
#[derive(Deserialize)]
#[cfg(test)]
struct Node {
    package: String,
    window_id: i32,
    visible: bool,
    source: String,
    bounds_array: Bounds,
}

#[derive(Deserialize)]
#[cfg(test)]
struct NativeDump {
    ok: bool,
    accessibility_mode_restoration_verified: bool,
    window_context: Option<WindowContext>,
    nodes: Option<Vec<Node>>,
}

/// Window and complete visible native-tree observations; no pixel claim.
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct WindowObservation {
    /// Stable WindowManager focus observed on both sides of native collection.
    pub focus: Focus,
    /// This one instrumentation connection's ID, never reused for later input.
    pub accessibility_window_id: i32,
    /// The exact observed application window rectangle.
    pub bounds: Bounds,
    /// Number of visible, window-bound native nodes actually returned.
    pub visible_nodes: usize,
    /// Raw helper JSON, retained for audit; no synthesized rendering evidence.
    pub native_json: String,
    /// A text/tree observation has not checked screen pixels or image crop.
    pub pixel_observation_verified: bool,
}

#[cfg(test)]
impl NativeDump {
    fn validate(
        self,
        owned: &TaskCandidate,
        focus: Focus,
        raw: String,
    ) -> Result<WindowObservation, String> {
        let meta = self.window_context.ok_or("native window context absent")?;
        let window = meta.selected_window;
        let nodes = self.nodes.ok_or("native nodes absent")?;
        if !self.ok
            || !self.accessibility_mode_restoration_verified
            || !meta.snapshot_complete
            || !meta.semantic_controls_available
            || meta.truncated
            || meta.null_child_count != 0
            || meta.tree_status != "available"
            || meta.visible_count == 0
            || meta.visited_count < meta.visible_count
            || nodes.len() != meta.visible_count as usize
            || nodes.len() > 2048
            || window.display_id != 0
            || !window.focused
            || window.kind != 1
            || window.window_id < 0
            || !owned.bounds.contains(window.bounds)
        {
            return Err(
                "native Settings observation is incomplete or outside the owned task".into(),
            );
        }
        for root in [window.root, meta.root] {
            if !root.present
                || !root.visible
                || root.package != SETTINGS
                || root.window_id != window.window_id
                || !window.bounds.contains(root.bounds)
            {
                return Err("native root is outside the owned Settings window".into());
            }
        }
        if nodes.iter().any(|n| {
            !n.visible
                || n.package != SETTINGS
                || n.window_id != window.window_id
                || n.source != "native_accessibility"
                || !window.bounds.contains(n.bounds_array)
        }) {
            return Err("native node is outside the one observed Settings window".into());
        }
        Ok(WindowObservation {
            focus,
            accessibility_window_id: window.window_id,
            bounds: window.bounds,
            visible_nodes: nodes.len(),
            native_json: raw,
            pixel_observation_verified: false,
        })
    }
}

#[derive(Deserialize)]
#[cfg(test)]
pub(super) struct NativeOutcome {
    pub ok: bool,
    pub accessibility_mode_restoration_verified: bool,
}

#[cfg(test)]
pub(super) fn validate_dump(
    raw: String,
    owned: &TaskCandidate,
    focus: Focus,
) -> Result<WindowObservation, String> {
    let dump: NativeDump =
        serde_json::from_str(&raw).map_err(|e| format!("invalid native tree: {e}"))?;
    dump.validate(owned, focus, raw)
}

#[cfg(test)]
pub(super) fn native_dump(raw: &str) -> Result<(NativeOutcome, String), String> {
    bounded(raw)?;
    const PREFIX: &str = "INSTRUMENTATION_RESULT: sidecar_result_base64=";
    let values: Vec<_> = raw.lines().filter_map(|s| s.strip_prefix(PREFIX)).collect();
    let [value] = values.as_slice() else {
        return Err("native instrumentation result absent or repeated".into());
    };
    let decoded = decode_base64(value)?;
    let text = String::from_utf8(decoded).map_err(|_| "native JSON is not UTF-8")?;
    let value = serde_json::from_str(&text).map_err(|e| format!("invalid native JSON: {e}"))?;
    Ok((value, text))
}

// Strict padded RFC4648 alphabet and canonical low bits; no whitespace fallback.
#[cfg(test)]
fn decode_base64(raw: &str) -> Result<Vec<u8>, String> {
    if raw.is_empty() || raw.len() > LIMIT || raw.len() % 4 != 0 {
        return Err("invalid bounded base64 length".into());
    }
    fn digit(b: u8) -> Option<u8> {
        match b {
            b'A'..=b'Z' => Some(b - b'A'),
            b'a'..=b'z' => Some(b - b'a' + 26),
            b'0'..=b'9' => Some(b - b'0' + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    }
    let mut out = Vec::with_capacity(raw.len() / 4 * 3);
    for (i, c) in raw.as_bytes().chunks_exact(4).enumerate() {
        let a = digit(c[0]).ok_or("invalid base64 digit")?;
        let b = digit(c[1]).ok_or("invalid base64 digit")?;
        let last = (i + 1) * 4 == raw.len();
        out.push((a << 2) | (b >> 4));
        if c[2] == b'=' {
            if !last || c[3] != b'=' || b & 15 != 0 {
                return Err("noncanonical base64 padding".into());
            }
            continue;
        }
        let d = digit(c[2]).ok_or("invalid base64 digit")?;
        out.push((b << 4) | (d >> 2));
        if c[3] == b'=' {
            if !last || d & 3 != 0 {
                return Err("noncanonical base64 padding".into());
            }
        } else {
            out.push((d << 6) | digit(c[3]).ok_or("invalid base64 digit")?);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strict_base64_accepts_canonical_vectors_and_rejects_aliases() {
        for (raw, expected) in [
            ("Zg==", "f"),
            ("Zm8=", "fo"),
            ("Zm9v", "foo"),
            ("Zm9vYg==", "foob"),
            ("Zm9vYmE=", "fooba"),
            ("Zm9vYmFy", "foobar"),
        ] {
            assert_eq!(decode_base64(raw).unwrap(), expected.as_bytes());
        }
        for raw in [
            "", "Zg", "Zh==", "Zm9=", "Zg==AAAA", "Zg=\n", "Zg-_", "====", "Zm=v",
        ] {
            assert!(decode_base64(raw).is_err(), "{raw:?}");
        }
        assert!(decode_base64(&"A".repeat(LIMIT + 4)).is_err());
    }
    #[test]
    fn malformed_or_repeated_native_ack_never_yields_a_task_id() {
        for raw in [
            "object=1 composer_display=2 android_display=0 task=42\nobject=1 composer_display=2 android_display=0 task=42",
            "object=1 composer_display=2 android_display=1 task=42",
            "object=1 composer_display=2 android_display=0 task=0",
            "object=1 composer_display=2 android_display=0 task=2147483648",
            "object=1 object=2 android_display=0 task=42",
        ] {
            assert!(launch_task(raw).is_err());
        }
        assert_eq!(
            launch_task("object=1 composer_display=2 android_display=0 task=42").unwrap(),
            42
        );
    }
    #[test]
    fn task_parser_rejects_duplicated_unparsed_and_ambiguous_roots() {
        let raw = "RootTask id=1 bounds=[0,0][800,600] displayId=0 userId=0\n configuration={mWindowingMode=fullscreen}\n taskId=1: com.example/.Main userId=0 visible=true topActivity=ComponentInfo{com.example/.Main}\n";
        assert!(Tasks::parse(raw).is_ok());
        for wrong in [
            format!("{raw}{raw}"),
            raw.replace("taskId=1:", "taskId=?"),
            raw.replace("userId=0 visible", "userId=0 userId=0 visible"),
            raw.replace("bounds=[0,0]", "bounds=[text,0]"),
            raw.replace("RootTask id=1", "RootTask id=?"),
        ] {
            assert!(Tasks::parse(&wrong).is_err(), "{wrong}");
        }
    }
    #[test]
    fn focus_cannot_be_a_foreign_user_component_or_ambiguous_window() {
        let owned = TaskCandidate {
            id: 42,
            component: "com.android.settings/com.android.settings.Settings".into(),
            top_activity: "com.android.settings/com.android.settings.Settings".into(),
            bounds: Bounds([0, 0, 800, 600]),
        };
        let raw = "mCurrentFocus=Window{ab12 u0 com.android.settings/.Settings}";
        assert!(focus(raw, &owned).is_ok());
        for bad in [
            raw.replace("u0", "u10"),
            raw.replace("/.Settings", "/.Other"),
            format!("{raw}\n{raw}"),
            raw.replace("ab12", "../../bad"),
        ] {
            assert!(focus(&bad, &owned).is_err());
        }
    }
}
