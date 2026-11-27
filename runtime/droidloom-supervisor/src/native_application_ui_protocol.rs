//! Closed wire format for the already pinned native accessibility helper.
//!
//! These values are data, never execution or acceptance authority. Only a live
//! Main/PM/task owner may dispatch a request. Parsing a reply does not qualify an
//! application, establish visible rendering, or authorize another action.
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::BTreeMap;
use std::fmt;
use std::process::Output;

pub(crate) const HELPER_PACKAGE: &str = "local.pocket4.actions.v2";
pub(crate) const HELPER_COMPONENT: &str = "local.pocket4.actions.v2/.ActionRunner";
pub(crate) const HELPER_VERSION: u64 = 2;
pub(crate) const HELPER_APK_BYTES: u64 = 20_847;
pub(crate) const HELPER_APK_SHA256: &str =
    "a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058";
pub(crate) const DECODED_REPLY_BYTES: usize = 16 * 1024 * 1024;
pub(crate) const WIRE_REPLY_BYTES: usize = ((DECODED_REPLY_BYTES + 2) / 3) * 4 + 64 * 1024;
const REQUEST_BYTES: usize = 65_536;
const TEXT_BYTES: usize = 4_096;
const RESULT_PREFIX: &str = "INSTRUMENTATION_RESULT: sidecar_result_base64=";

type Result<T> = std::result::Result<T, ProtocolError>;

#[derive(Debug, Eq, PartialEq)]
pub struct ProtocolError {
    code: &'static str,
    outcome_unknown: bool,
}
impl ProtocolError {
    pub fn code(&self) -> &'static str {
        self.code
    }
    pub fn outcome_unknown(&self) -> bool {
        self.outcome_unknown
    }
    pub fn automatic_retry(&self) -> bool {
        false
    }
}
impl fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{} (outcome_unknown={}, automatic_retry=false)",
            self.code, self.outcome_unknown
        )
    }
}
impl std::error::Error for ProtocolError {}

fn need(condition: bool, code: &'static str, unknown: bool) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(ProtocolError {
            code,
            outcome_unknown: unknown,
        })
    }
}
fn bounded_text(text: &str, empty: bool) -> Result<()> {
    need(
        (empty || !text.is_empty()) && text.len() <= TEXT_BYTES && !text.contains('\0'),
        "UI_TEXT_BOUND",
        false,
    )
}

/// A fixed selector vocabulary. There is deliberately no Deserialize or raw map
/// constructor, regular expression, caller index, or alternate helper identity.
#[derive(Clone, Debug, Default, Serialize)]
pub struct Selector {
    #[serde(flatten)]
    strings: BTreeMap<&'static str, String>,
    #[serde(flatten)]
    flags: BTreeMap<&'static str, bool>,
}
impl Selector {
    pub fn resource_id(value: &str) -> Result<Self> {
        Self::string("id", value)
    }
    pub fn exact_text(value: &str) -> Result<Self> {
        Self::string("text", value)
    }
    pub fn description(value: &str) -> Result<Self> {
        Self::string("desc", value)
    }
    fn string(key: &'static str, value: &str) -> Result<Self> {
        bounded_text(value, false)?;
        Ok(Self {
            strings: BTreeMap::from([(key, value.into())]),
            flags: BTreeMap::new(),
        })
    }
    pub fn editable() -> Self {
        Self {
            strings: BTreeMap::new(),
            flags: BTreeMap::from([("editable", true)]),
        }
    }
    pub fn focused(mut self) -> Self {
        self.flags.insert("focused", true);
        self
    }
    pub fn enabled(mut self) -> Self {
        self.flags.insert("enabled", true);
        self
    }
    fn validate(&self) -> Result<()> {
        need(
            !self.strings.is_empty() || !self.flags.is_empty(),
            "UI_EMPTY_SELECTOR",
            false,
        )?;
        need(
            self.strings
                .keys()
                .all(|key| matches!(*key, "id" | "text" | "desc"))
                && self
                    .flags
                    .keys()
                    .all(|key| matches!(*key, "editable" | "focused" | "enabled")),
            "UI_SELECTOR_VOCABULARY",
            false,
        )?;
        for value in self.strings.values() {
            bounded_text(value, false)?;
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub(crate) enum Operation {
    Meta,
    Dump,
    Find(Selector),
    Click(Selector),
    SetText { selector: Selector, value: String },
}
impl Operation {
    pub(crate) fn mutation(&self) -> bool {
        matches!(self, Self::Click(_) | Self::SetText { .. })
    }
    pub(crate) fn name(&self) -> &'static str {
        match self {
            Self::Meta => "meta",
            Self::Dump => "dump",
            Self::Find(_) => "find",
            Self::Click(_) => "click",
            Self::SetText { .. } => "set-text",
        }
    }
}

#[derive(Clone, Debug)]
pub(crate) struct Request {
    package: String,
    operation: Operation,
}
impl Request {
    pub(crate) fn new(package: &str, operation: Operation) -> Result<Self> {
        need(
            crate::engine_custody::selected_package(package),
            "UI_PACKAGE_OUTSIDE_SELECTED39",
            false,
        )?;
        match &operation {
            Operation::Find(selector) | Operation::Click(selector) => selector.validate()?,
            Operation::SetText { selector, value } => {
                selector.validate()?;
                bounded_text(value, true)?;
            }
            Operation::Meta | Operation::Dump => {}
        }
        Ok(Self {
            package: package.into(),
            operation,
        })
    }
    pub(crate) fn package(&self) -> &str {
        &self.package
    }
    pub(crate) fn mutation(&self) -> bool {
        self.operation.mutation()
    }
    pub(crate) fn operation(&self) -> &'static str {
        self.operation.name()
    }

    /// One literal am instrumentation request. There is no shell, supplied
    /// executable, component, display, user, environment, or command suffix.
    pub(crate) fn arguments(&self) -> Result<Vec<String>> {
        let mut value = Map::from_iter([
            ("op".into(), Value::String(self.operation.name().into())),
            (
                "expected_package".into(),
                Value::String(self.package.clone()),
            ),
            ("display".into(), Value::from(0)),
            ("accessibility_mode".into(), Value::String("none".into())),
        ]);
        match &self.operation {
            Operation::Find(selector) | Operation::Click(selector) => {
                value.insert(
                    "selector".into(),
                    serde_json::to_value(selector).map_err(|_| ProtocolError {
                        code: "UI_SELECTOR_ENCODING",
                        outcome_unknown: false,
                    })?,
                );
            }
            Operation::SetText {
                selector,
                value: text,
            } => {
                value.insert(
                    "selector".into(),
                    serde_json::to_value(selector).map_err(|_| ProtocolError {
                        code: "UI_SELECTOR_ENCODING",
                        outcome_unknown: false,
                    })?,
                );
                value.insert("value".into(), Value::String(text.clone()));
            }
            Operation::Meta | Operation::Dump => {}
        }
        let bytes = serde_json::to_vec(&value).map_err(|_| ProtocolError {
            code: "UI_REQUEST_ENCODING",
            outcome_unknown: false,
        })?;
        need(
            !bytes.is_empty() && bytes.len() <= REQUEST_BYTES,
            "UI_REQUEST_BOUND",
            false,
        )?;
        Ok(vec![
            "/system/bin/am".into(),
            "instrument".into(),
            "-w".into(),
            "-r".into(),
            "-e".into(),
            "request".into(),
            encode64(&bytes),
            HELPER_COMPONENT.into(),
        ])
    }
}

/// Syntax-checked response only. Its body retains all original helper facts,
/// including the explicit absence of visual/business acceptance. No public
/// constructor, Deserialize, Clone, or method can turn it into a passed gate.
pub struct Reply {
    body: Value,
}
impl Reply {
    pub fn body(&self) -> &Value {
        &self.body
    }

    pub(crate) fn parse(request: &Request, output: &Output) -> Result<Self> {
        let mutation = request.mutation();
        need(
            output.status.code() == Some(0) && output.stderr.is_empty(),
            "UI_HELPER_PROCESS_FAILED",
            mutation,
        )?;
        need(
            !output.stdout.is_empty() && output.stdout.len() <= WIRE_REPLY_BYTES,
            "UI_HELPER_WIRE_BOUND",
            mutation,
        )?;
        let text = std::str::from_utf8(&output.stdout).map_err(|_| ProtocolError {
            code: "UI_HELPER_NON_UTF8",
            outcome_unknown: mutation,
        })?;
        let mut encoded = None;
        for line in text.lines() {
            let line = line.strip_suffix('\r').unwrap_or(line);
            if let Some(value) = line.strip_prefix(RESULT_PREFIX) {
                need(
                    encoded.replace(value).is_none(),
                    "UI_DUPLICATE_REPLY",
                    mutation,
                )?;
            }
            need(
                !line.starts_with("INSTRUMENTATION_FAILED:")
                    && !line.starts_with("INSTRUMENTATION_ABORTED:"),
                "UI_INSTRUMENTATION_FAILED",
                mutation,
            )?;
        }
        let encoded = encoded.ok_or(ProtocolError {
            code: "UI_REPLY_ABSENT",
            outcome_unknown: mutation,
        })?;
        let decoded = decode64(encoded, mutation)?;
        let body = strict_json(&decoded, mutation)?;
        need(
            body.is_object() && body.get("ok").is_some_and(Value::is_boolean),
            "UI_REPLY_SHAPE",
            mutation,
        )?;
        // Even a read temporarily acquires accessibility state. Failure to
        // restore that state is ambiguous and must stop the original session.
        need(
            body.get("accessibility_mode_restoration_verified") == Some(&Value::Bool(true)),
            "UI_ACCESSIBILITY_RESTORATION_UNVERIFIED",
            true,
        )?;
        if body["ok"] != true {
            need(
                body.get("outcome_unknown").is_some_and(Value::is_boolean)
                    && body.get("automatic_retry") == Some(&Value::Bool(false))
                    && body.get("error").and_then(Value::as_str).is_some_and(|s| {
                        !s.is_empty()
                            && s.len() <= 128
                            && s.bytes()
                                .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_')
                    }),
                "UI_FAILURE_REPLY_SHAPE",
                mutation,
            )?;
            return Err(ProtocolError {
                code: "UI_HELPER_REPORTED_FAILURE",
                outcome_unknown: mutation || body["outcome_unknown"] == true,
            });
        }
        for key in ["outcome_unknown", "automatic_retry"] {
            need(
                body.get(key).is_none_or(|v| v == &Value::Bool(false)),
                "UI_REPLY_OUTCOME_UNKNOWN",
                true,
            )?;
        }
        need(
            body.get("accessibility_mode").and_then(Value::as_str) == Some("none")
                && body.get("restored_flags").and_then(Value::as_u64).is_some()
                && body
                    .get("touch_exploration_after")
                    .is_some_and(Value::is_boolean),
            "UI_RESTORATION_FIELDS_CHANGED",
            true,
        )?;
        match &request.operation {
            Operation::Meta => {
                window_context(&body, request.package(), false)?;
            }
            Operation::Dump => {
                let context = window_context(&body, request.package(), true)?;
                let nodes = body
                    .get("nodes")
                    .and_then(Value::as_array)
                    .ok_or(ProtocolError {
                        code: "UI_DUMP_NODES_ABSENT",
                        outcome_unknown: false,
                    })?;
                need(
                    nodes.len() <= 2_000
                        && context.get("visible_count").and_then(Value::as_u64)
                            == Some(nodes.len() as u64),
                    "UI_DUMP_COUNT_CHANGED",
                    false,
                )?;
                for node in nodes {
                    described_node(node, None, false)?;
                }
            }
            Operation::Find(selector) => {
                window_context(&body, request.package(), true)?;
                let nodes = body
                    .get("matches")
                    .and_then(Value::as_array)
                    .ok_or(ProtocolError {
                        code: "UI_FIND_MATCHES_ABSENT",
                        outcome_unknown: false,
                    })?;
                need(
                    nodes.len() <= 2_000
                        && body.get("count").and_then(Value::as_u64) == Some(nodes.len() as u64),
                    "UI_FIND_COUNT_CHANGED",
                    false,
                )?;
                for node in nodes {
                    described_node(node, Some(request.package()), false)?;
                    need(
                        selector.matches_node(node),
                        "UI_FIND_SELECTOR_CHANGED",
                        false,
                    )?;
                }
            }
            Operation::Click(_) | Operation::SetText { .. } => {}
        }
        if mutation {
            need(
                body.get("performed").and_then(Value::as_str) == Some(request.operation()),
                "UI_MUTATION_OPERATION_CHANGED",
                true,
            )?;
            match &request.operation {
                Operation::Click(selector) => {
                    need(
                        body.get("target").is_some_and(Value::is_object)
                            && body.get("actual_target").is_some_and(Value::is_object)
                            && body.get("visual_verified") == Some(&Value::Bool(false))
                            && body.get("business_success_verified") == Some(&Value::Bool(false)),
                        "UI_CLICK_REPLY_SHAPE",
                        true,
                    )?;
                    described_node(&body["target"], Some(request.package()), true)?;
                    described_node(&body["actual_target"], Some(request.package()), true)?;
                    need(
                        selector.matches_node(&body["target"])
                            && body["target"]["window_id"] == body["actual_target"]["window_id"]
                            && body["actual_target"]["clickable"] == true,
                        "UI_CLICK_TARGET_CHANGED",
                        true,
                    )?;
                }
                Operation::SetText { value, .. } => {
                    need(
                        body.get("characters").and_then(Value::as_u64)
                            == Some(value.chars().count() as u64)
                            && body.get("password") == Some(&Value::Bool(false))
                            && body.get("readback_verified") == Some(&Value::Bool(true)),
                        "UI_TEXT_READBACK_UNVERIFIED_OR_PASSWORD",
                        true,
                    )?;
                }
                _ => unreachable!(),
            }
        }
        Ok(Self { body })
    }
}

impl Selector {
    fn matches_node(&self, node: &Value) -> bool {
        self.strings.iter().all(|(key, expected)| {
            let field = match *key {
                "id" => "resource-id",
                "text" => "text",
                "desc" => "content-desc",
                _ => return false,
            };
            node.get(field).and_then(Value::as_str) == Some(expected.as_str())
        }) && self
            .flags
            .iter()
            .all(|(key, expected)| node.get(*key).and_then(Value::as_bool) == Some(*expected))
    }
}
fn rectangle(value: &Value, positive: bool) -> bool {
    let Some(values) = value.as_array().filter(|v| v.len() == 4) else {
        return false;
    };
    let Some(coords) = values.iter().map(Value::as_i64).collect::<Option<Vec<_>>>() else {
        return false;
    };
    coords.iter().all(|v| i32::try_from(*v).is_ok())
        && (!positive || (coords[2] > coords[0] && coords[3] > coords[1]))
}
fn described_node(node: &Value, package: Option<&str>, mutation: bool) -> Result<()> {
    need(
        node.is_object()
            && [
                "text",
                "hint",
                "resource-id",
                "content-desc",
                "package",
                "class",
                "bounds",
            ]
            .iter()
            .all(|k| node.get(*k).is_some_and(Value::is_string))
            && [
                "showing-hint",
                "enabled",
                "focused",
                "editable",
                "clickable",
                "password",
                "visible",
                "scrollable",
                "selected",
                "checked",
                "important_for_accessibility",
            ]
            .iter()
            .all(|k| node.get(*k).is_some_and(Value::is_boolean))
            && node
                .get("window_id")
                .and_then(Value::as_i64)
                .is_some_and(|v| v >= 0 && i32::try_from(v).is_ok())
            && node
                .get("supported_actions")
                .and_then(Value::as_array)
                .is_some_and(|v| {
                    v.len() <= 128
                        && v.iter()
                            .all(|n| n.as_i64().is_some_and(|i| i32::try_from(i).is_ok()))
                })
            && rectangle(&node["bounds_array"], mutation)
            && node.get("source").and_then(Value::as_str) == Some("native_accessibility")
            && node
                .get("value")
                .is_some_and(|v| v.is_null() || v.is_string())
            && package.is_none_or(|p| node.get("package").and_then(Value::as_str) == Some(p)),
        "UI_NODE_SHAPE_OR_PACKAGE_CHANGED",
        mutation,
    )?;
    if node["password"] == true {
        need(
            ["text", "hint", "content-desc"]
                .iter()
                .all(|k| node[*k] == "")
                && node["value"].is_null(),
            "UI_PASSWORD_CONTENT_EXPOSED",
            true,
        )?;
    }
    if mutation {
        need(
            node["visible"] == true && node["enabled"] == true && node["password"] == false,
            "UI_MUTATION_TARGET_NOT_USABLE",
            true,
        )?;
    }
    Ok(())
}
fn root_node(value: &Value, package: &str, window: i64) -> bool {
    value.get("present") == Some(&Value::Bool(true))
        && value.get("package").and_then(Value::as_str) == Some(package)
        && value
            .get("class")
            .and_then(Value::as_str)
            .is_some_and(|v| !v.is_empty())
        && value.get("window_id").and_then(Value::as_i64) == Some(window)
        && value.get("visible") == Some(&Value::Bool(true))
        && value.get("child_count").and_then(Value::as_u64).is_some()
        && rectangle(&value["bounds"], true)
}
fn window_context<'a>(body: &'a Value, package: &str, complete: bool) -> Result<&'a Value> {
    let context = &body["window_context"];
    let selected = &context["selected_window"];
    let window = selected
        .get("window_id")
        .and_then(Value::as_i64)
        .filter(|id| *id >= 0 && i32::try_from(*id).is_ok())
        .ok_or(ProtocolError {
            code: "UI_SELECTED_WINDOW_ABSENT",
            outcome_unknown: false,
        })?;
    let windows = context
        .get("windows")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty() && v.len() <= 256)
        .ok_or(ProtocolError {
            code: "UI_WINDOW_LIST_ABSENT",
            outcome_unknown: false,
        })?;
    need(
        context.get("display_id") == Some(&Value::from(0))
            && selected.get("display_id") == Some(&Value::from(0))
            && selected.get("focused") == Some(&Value::Bool(true))
            && selected.get("type") == Some(&Value::from(1))
            && selected.get("active").is_some_and(Value::is_boolean)
            && rectangle(&selected["bounds"], true)
            && root_node(&selected["root"], package, window)
            && root_node(&context["root"], package, window)
            && windows
                .iter()
                .filter(|w| w.get("window_id").and_then(Value::as_i64) == Some(window))
                .count()
                == 1
            && windows
                .iter()
                .filter(|w| {
                    w.get("type") == Some(&Value::from(1))
                        && w.get("focused") == Some(&Value::Bool(true))
                })
                .count()
                == 1
            && windows.iter().any(|w| w == selected)
            && context.get("flags").and_then(Value::as_u64).is_some()
            && context
                .get("capabilities")
                .and_then(Value::as_u64)
                .is_some()
            && context.get("uptime_ms").and_then(Value::as_u64).is_some()
            && [
                "is_accessibility_tool",
                "accessibility_enabled",
                "touch_exploration_enabled",
            ]
            .iter()
            .all(|k| context.get(*k).is_some_and(Value::is_boolean)),
        "UI_WINDOW_CONTEXT_CHANGED",
        false,
    )?;
    if complete {
        let visited = context.get("visited_count").and_then(Value::as_u64);
        let visible = context.get("visible_count").and_then(Value::as_u64);
        need(
            context.get("snapshot_complete") == Some(&Value::Bool(true))
                && context.get("truncated") == Some(&Value::Bool(false))
                && context.get("null_child_count") == Some(&Value::from(0))
                && context.get("semantic_controls_available") == Some(&Value::Bool(true))
                && context.get("tree_status").and_then(Value::as_str) == Some("available")
                && visited
                    .zip(visible)
                    .is_some_and(|(all, shown)| shown > 0 && all >= shown && all <= 2_000),
            "UI_TREE_INCOMPLETE_OR_UNAVAILABLE",
            false,
        )?;
    }
    Ok(context)
}

fn encode64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(((bytes.len() + 2) / 3) * 4);
    for part in bytes.chunks(3) {
        let a = part[0];
        let b = part.get(1).copied().unwrap_or(0);
        let c = part.get(2).copied().unwrap_or(0);
        out.push(ALPHABET[(a >> 2) as usize] as char);
        out.push(ALPHABET[(((a & 3) << 4) | (b >> 4)) as usize] as char);
        out.push(if part.len() > 1 {
            ALPHABET[(((b & 15) << 2) | (c >> 6)) as usize] as char
        } else {
            '='
        });
        out.push(if part.len() > 2 {
            ALPHABET[(c & 63) as usize] as char
        } else {
            '='
        });
    }
    out
}
fn decode64(text: &str, unknown: bool) -> Result<Vec<u8>> {
    need(
        !text.is_empty()
            && text.len() <= ((DECODED_REPLY_BYTES + 2) / 3) * 4
            && text.len() % 4 == 0,
        "UI_BASE64_BOUND",
        unknown,
    )?;
    let digit = |byte| -> Result<u8> {
        Ok(match byte {
            b'A'..=b'Z' => byte - b'A',
            b'a'..=b'z' => byte - b'a' + 26,
            b'0'..=b'9' => byte - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            _ => {
                return Err(ProtocolError {
                    code: "UI_BASE64_CHARACTER",
                    outcome_unknown: unknown,
                });
            }
        })
    };
    let mut out = Vec::with_capacity(text.len() / 4 * 3);
    let total = text.len() / 4;
    for (i, part) in text.as_bytes().chunks_exact(4).enumerate() {
        let a = digit(part[0])?;
        let b = digit(part[1])?;
        out.push((a << 2) | (b >> 4));
        if part[2] == b'=' {
            need(
                i + 1 == total && part[3] == b'=' && b & 15 == 0,
                "UI_BASE64_PADDING",
                unknown,
            )?;
        } else {
            let c = digit(part[2])?;
            out.push((b << 4) | (c >> 2));
            if part[3] == b'=' {
                need(i + 1 == total && c & 3 == 0, "UI_BASE64_PADDING", unknown)?;
            } else {
                out.push((c << 6) | digit(part[3])?);
            }
        }
    }
    need(
        out.len() <= DECODED_REPLY_BYTES,
        "UI_DECODED_BOUND",
        unknown,
    )?;
    Ok(out)
}

// serde_json::Value normally keeps the last duplicate object key. A helper
// response cannot replace a failure with a later success field.
struct UniqueValue(Value);
impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = UniqueValue;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("bounded unique-key JSON")
            }
            fn visit_bool<E: serde::de::Error>(
                self,
                v: bool,
            ) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Bool(v)))
            }
            fn visit_i64<E: serde::de::Error>(self, v: i64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::from(v)))
            }
            fn visit_u64<E: serde::de::Error>(self, v: u64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::from(v)))
            }
            fn visit_f64<E: serde::de::Error>(self, v: f64) -> std::result::Result<Self::Value, E> {
                serde_json::Number::from_f64(v)
                    .map(|n| UniqueValue(Value::Number(n)))
                    .ok_or_else(|| E::custom("non-finite JSON"))
            }
            fn visit_str<E: serde::de::Error>(
                self,
                v: &str,
            ) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::String(v.into())))
            }
            fn visit_string<E: serde::de::Error>(
                self,
                v: String,
            ) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::String(v)))
            }
            fn visit_none<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut out = Vec::new();
                while let Some(v) = a.next_element::<UniqueValue>()? {
                    out.push(v.0);
                }
                Ok(UniqueValue(Value::Array(out)))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut out = Map::new();
                while let Some((key, value)) = a.next_entry::<String, UniqueValue>()? {
                    if out.insert(key, value.0).is_some() {
                        return Err(serde::de::Error::custom("duplicate JSON key"));
                    }
                }
                Ok(UniqueValue(Value::Object(out)))
            }
        }
        d.deserialize_any(Visitor)
    }
}
fn strict_json(bytes: &[u8], unknown: bool) -> Result<Value> {
    need(
        !bytes.is_empty() && bytes.len() <= DECODED_REPLY_BYTES,
        "UI_JSON_BOUND",
        unknown,
    )?;
    let mut decoder = serde_json::Deserializer::from_slice(bytes);
    let result =
        UniqueValue::deserialize(&mut decoder).and_then(|value| decoder.end().map(|()| value.0));
    result.map_err(|_| ProtocolError {
        code: "UI_JSON_MALFORMED_OR_DUPLICATE",
        outcome_unknown: unknown,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::process::ExitStatusExt;

    fn output(raw: &[u8]) -> Output {
        Output {
            status: std::process::ExitStatus::from_raw(0),
            stdout: format!(
                "{RESULT_PREFIX}{}\nINSTRUMENTATION_CODE: -1\n",
                encode64(raw)
            )
            .into_bytes(),
            stderr: Vec::new(),
        }
    }
    fn request(operation: Operation) -> Request {
        Request::new("com.android.settings", operation).unwrap()
    }
    #[test]
    fn native_ui_wire_has_one_fixed_helper_and_exact_unicode_argument() {
        let value = "中文 café 🛰️\n次行";
        let req = request(Operation::SetText {
            selector: Selector::editable().focused(),
            value: value.into(),
        });
        let args = req.arguments().unwrap();
        assert_eq!(
            &args[..6],
            ["/system/bin/am", "instrument", "-w", "-r", "-e", "request"]
        );
        assert_eq!(args.len(), 8);
        assert_eq!(args[7], HELPER_COMPONENT);
        let decoded = strict_json(&decode64(&args[6], false).unwrap(), false).unwrap();
        assert_eq!(decoded["value"], value);
        assert_eq!(decoded["expected_package"], "com.android.settings");
        assert_eq!(decoded["display"], 0);
        assert_eq!(decoded["accessibility_mode"], "none");
        assert!(decoded.get("index").is_none());
        assert!(Request::new("com.example.unselected", Operation::Dump).is_err());
        assert!(Selector::exact_text("x\0y").is_err());
        assert!(Selector::resource_id(&"a".repeat(TEXT_BYTES + 1)).is_err());
    }
    #[test]
    fn native_ui_reply_rejects_duplicate_success_trailing_json_and_noncanonical_base64() {
        let req = request(Operation::Dump);
        for raw in [
            br#"{"ok":false,"ok":true,"accessibility_mode_restoration_verified":true}"#.as_slice(),
            br#"{"ok":true,"accessibility_mode_restoration_verified":true}{}"#,
            br#"{"ok":true,"accessibility_mode_restoration_verified":true,"nested":{"a":1,"a":2}}"#,
        ] {
            assert!(Reply::parse(&req, &output(raw)).is_err());
        }
        for text in ["YR==", "YWJ=", "YQ==YQ==", "YQ=\n", "=Q=="] {
            assert!(decode64(text, false).is_err());
        }
        assert_eq!(decode64("YQ==", false).unwrap(), b"a");
        assert_eq!(decode64("YWI=", false).unwrap(), b"ab");
        assert_eq!(decode64("YWJj", false).unwrap(), b"abc");
    }
    #[test]
    fn native_ui_reply_never_erases_unrestored_or_unknown_action() {
        let req = request(Operation::Click(Selector::exact_text("Search").unwrap()));
        for raw in [
            br#"{"ok":true,"accessibility_mode_restoration_verified":false}"#.as_slice(),
            br#"{"ok":true,"accessibility_mode_restoration_verified":true,"outcome_unknown":true}"#,
            br#"{"ok":false,"accessibility_mode_restoration_verified":true,"outcome_unknown":true,"automatic_retry":false,"error":"ACTION_MAY_HAVE_OCCURRED"}"#,
        ] {
            let error = Reply::parse(&req, &output(raw)).err().unwrap();
            assert!(error.outcome_unknown());
            assert!(!error.automatic_retry());
        }
        let mut repeated = output(br#"{"ok":true,"accessibility_mode_restoration_verified":true}"#);
        repeated.stdout.extend_from_slice(&repeated.stdout.clone());
        assert_eq!(
            Reply::parse(&request(Operation::Meta), &repeated)
                .err()
                .unwrap()
                .code(),
            "UI_DUPLICATE_REPLY"
        );
    }

    fn success(mut body: Value) -> Output {
        let map = body.as_object_mut().unwrap();
        map.insert("ok".into(), Value::Bool(true));
        map.insert("accessibility_mode".into(), Value::String("none".into()));
        map.insert("restored_flags".into(), Value::from(0));
        map.insert("touch_exploration_after".into(), Value::Bool(false));
        map.insert(
            "accessibility_mode_restoration_verified".into(),
            Value::Bool(true),
        );
        output(&serde_json::to_vec(&body).unwrap())
    }
    fn node() -> Value {
        serde_json::json!({
            "text":"Open","hint":"","showing-hint":false,"value":null,
            "resource-id":"com.android.settings:id/open","content-desc":"Open",
            "package":"com.android.settings","class":"android.widget.Button",
            "window_id":12,"enabled":true,"focused":false,"editable":false,
            "clickable":true,"password":false,"visible":true,"scrollable":false,
            "selected":false,"checked":false,"important_for_accessibility":true,
            "supported_actions":[16],"bounds_array":[20,30,120,80],"bounds":"[20,30][120,80]",
            "source":"native_accessibility"
        })
    }
    fn context() -> Value {
        let root = serde_json::json!({"present":true,"package":"com.android.settings",
            "class":"android.widget.FrameLayout","window_id":12,"bounds":[0,0,640,480],
            "visible":true,"child_count":1});
        let window = serde_json::json!({"window_id":12,"display_id":0,"active":true,
            "focused":true,"type":1,"bounds":[0,0,640,480],"root":root});
        serde_json::json!({"display_id":0,"selected_window":window,"windows":[window],
            "root":root,"flags":82,"capabilities":3,"is_accessibility_tool":false,
            "accessibility_enabled":true,"touch_exploration_enabled":false,"uptime_ms":500,
            "visited_count":2,"visible_count":1,"null_child_count":0,"truncated":false,
            "semantic_controls_available":true,"snapshot_complete":true,"tree_status":"available"})
    }
    #[test]
    fn native_ui_action_ack_keeps_business_false_and_password_text_is_not_accepted() {
        let req = request(Operation::Click(
            Selector::description("Open").unwrap().enabled(),
        ));
        let mut body = serde_json::json!({"performed":"click","target":node(),"actual_target":node(),
            "visual_verified":false,"business_success_verified":false});
        let result = Reply::parse(&req, &success(body.clone())).unwrap();
        assert_eq!(result.body()["business_success_verified"], false);
        body["actual_target"]["package"] = Value::String("com.android.chrome".into());
        assert!(Reply::parse(&req, &success(body)).is_err());
        let text = request(Operation::SetText {
            selector: Selector::editable(),
            value: "fixture".into(),
        });
        assert!(
            Reply::parse(
                &text,
                &success(serde_json::json!({"performed":"set-text",
            "characters":7,"password":true,"readback_verified":false}))
            )
            .is_err()
        );
        let result = Reply::parse(
            &text,
            &success(serde_json::json!({"performed":"set-text",
            "characters":7,"password":false,"readback_verified":true})),
        )
        .unwrap();
        assert!(result.body().get("business_success_verified").is_none());
    }
    #[test]
    fn native_ui_read_requires_actual_complete_same_package_window_and_node_count() {
        let req = request(Operation::Dump);
        let body = serde_json::json!({"window_context":context(),"nodes":[node()]});
        assert!(Reply::parse(&req, &success(body.clone())).is_ok());
        for case in 0..8 {
            let mut changed = body.clone();
            match case {
                0 => changed["window_context"]["snapshot_complete"] = Value::Bool(false),
                1 => changed["window_context"]["truncated"] = Value::Bool(true),
                2 => changed["window_context"]["null_child_count"] = Value::from(1),
                3 => changed["window_context"]["selected_window"]["display_id"] = Value::from(1),
                4 => {
                    changed["window_context"]["root"]["package"] =
                        Value::String("foreign.package".into())
                }
                5 => changed["window_context"]["visible_count"] = Value::from(2),
                6 => changed["window_context"]["windows"]
                    .as_array_mut()
                    .unwrap()
                    .push(context()["selected_window"].clone()),
                _ => changed["nodes"][0]["password"] = Value::Bool(true),
            }
            assert!(
                Reply::parse(&req, &success(changed)).is_err(),
                "case {case}"
            );
        }
        assert!(Reply::parse(&request(Operation::Meta), &success(serde_json::json!({}))).is_err());
        let req = request(Operation::Find(Selector::exact_text("Open").unwrap()));
        let body = serde_json::json!({"window_context":context(),"count":1,"matches":[node()]});
        assert!(Reply::parse(&req, &success(body.clone())).is_ok());
        let mut changed = body.clone();
        changed["count"] = Value::from(0);
        assert!(Reply::parse(&req, &success(changed)).is_err());
        let mut changed = body;
        changed["matches"][0]["text"] = Value::String("Different".into());
        assert!(Reply::parse(&req, &success(changed)).is_err());
    }
    #[test]
    fn native_ui_set_text_compares_java_code_points_and_rejects_ambiguous_success_fields() {
        let value = "中文 🛰️";
        let req = request(Operation::SetText {
            selector: Selector::editable().focused(),
            value: value.into(),
        });
        let body = serde_json::json!({"performed":"set-text","characters":5,
            "password":false,"readback_verified":true});
        assert_eq!(value.chars().count(), 5);
        assert_ne!(value.encode_utf16().count(), 5);
        assert!(Reply::parse(&req, &success(body.clone())).is_ok());
        for case in 0..4 {
            let mut changed = body.clone();
            match case {
                0 => changed["characters"] = Value::from(value.encode_utf16().count()),
                1 => changed["outcome_unknown"] = Value::String("false".into()),
                2 => changed["automatic_retry"] = Value::Bool(true),
                _ => changed["automatic_retry"] = Value::Null,
            }
            assert!(Reply::parse(&req, &success(changed)).is_err());
        }
    }
}
