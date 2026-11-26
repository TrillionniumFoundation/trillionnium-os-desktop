//! Bounded public observations used as inputs to a later VINTF consumer.
//! None of these serializable facts grants execution authority or compatibility.
use super::application_custody::{
    CustodyFileIdentity, CustodyImage, CustodyNamespace, CustodyOwner,
};
use super::application_probe::RuntimeEpoch;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub(crate) const MAX_FILES: usize = 256;
pub(crate) const MAX_APEX: usize = 128;
pub(crate) const MAX_BYTES: usize = 2 * 1024 * 1024;
pub(crate) const MAX_FILE_BYTES: usize = 256 * 1024;
pub(crate) const MAX_PATH_BYTES: usize = 24 * 1024;
pub(crate) const MAX_NODES: usize = 512;
pub(crate) const VINTF_ROOTS: [&str; 5] = [
    "/system/etc/vintf",
    "/product/etc/vintf",
    "/system_ext/etc/vintf",
    "/vendor/etc/vintf",
    "/odm/etc/vintf",
];
pub(crate) const LEGACY: [&str; 5] = [
    "/system/manifest.xml",
    "/system/compatibility_matrix.xml",
    "/vendor/manifest.xml",
    "/vendor/compatibility_matrix.xml",
    "/odm/etc/manifest.xml",
];
pub(crate) const ODM_LINKS: [&str; 4] = ["/odm", "/odm/etc", "/vendor/odm", "/vendor/odm/etc"];
pub(crate) const APEX_INVENTORY: &str = "/apex/apex-info-list.xml";
pub(crate) const PROPERTIES: [(&str, &str); 4] = [
    ("ro.boot.product.vendor.sku", "exported_default_prop"),
    ("ro.boot.product.hardware.sku", "exported_default_prop"),
    ("apex.all.ready", "apex_ready_prop"),
    ("ro.product.first_api_level", "build_vendor_prop"),
];

/// Live owner and actual held mounts, with image hashes from original admission.
/// This operation revalidates those same source inodes; it does not rehash images.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RuntimeVintfBinding {
    pub owner: CustodyOwner,
    pub framework_namespaces: Vec<CustodyNamespace>,
    pub framework_root: CustodyFileIdentity,
    pub base_images: Vec<CustodyImage>,
    pub image_bodies_rehashed_by_this_observation: bool,
}
/// Actual output of one fixed property invocation. Empty does not prove absence.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RuntimeProperty {
    pub name: String,
    pub value: String,
    pub state: String,
    pub original_property_type: String,
}
/// All original attributes of an active entry in the actual APEX inventory.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ActiveApex {
    pub module_name: String,
    pub attributes: BTreeMap<String, String>,
}
/// One complete public XML document, captured between unchanged stat bookends.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct VintfDocument {
    pub path: String,
    pub bytes: usize,
    pub sha256: String,
    pub stat: PublicStat,
    pub utf8: String,
}
/// Actual no-follow stat, excluding atime but retaining nanosecond date strings.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicStat {
    pub path: String,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub links: u64,
    pub device: u64,
    pub inode: u64,
    pub bytes: u64,
    pub modified: String,
    pub changed: String,
}
/// One original-tool ENOENT. Permission errors and other failures are rejected.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct MissingPath {
    pub path: String,
    pub state: String,
    pub stderr_line: String,
}
/// Actual symbolic-link metadata and target, without reading its target body.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicLink {
    pub stat: PublicStat,
    pub target: String,
}
/// The finite runtime collection result; compatibility and apps are unevaluated.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RuntimeVintfObservation {
    pub schema: String,
    pub expected_epoch: RuntimeEpoch,
    pub epoch_before: RuntimeEpoch,
    pub epoch_after: RuntimeEpoch,
    pub binding_before: RuntimeVintfBinding,
    pub binding_after: RuntimeVintfBinding,
    pub kernel_release: String,
    pub machine: String,
    pub properties: Vec<RuntimeProperty>,
    pub apex_inventory: VintfDocument,
    pub active_apex: Vec<ActiveApex>,
    pub root_mappings: BTreeMap<String, String>,
    pub missing: Vec<MissingPath>,
    pub odm_links: Vec<PublicLink>,
    pub directories: Vec<PublicStat>,
    pub documents: Vec<VintfDocument>,
    pub query_receipts: Vec<serde_json::Value>,
    pub elapsed_millis: u64,
    pub compatibility_checked: bool,
    pub application_acceptance: bool,
}

pub(crate) fn component(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 128
        && s != "."
        && s != ".."
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.'))
}
fn apex_component(value: &str) -> bool {
    component(value)
        || value.split_once('@').is_some_and(|(name, version)| {
            component(name)
                && !version.is_empty()
                && version.len() <= 20
                && version.bytes().all(|b| b.is_ascii_digit())
        })
}
fn safe_path(path: &str) -> bool {
    if path.len() > 512 || !path.starts_with('/') {
        return false;
    }
    let parts: Vec<_> = path.split('/').skip(1).collect();
    parts.iter().enumerate().all(|(i, value)| {
        if i == 1 && parts.first() == Some(&"apex") {
            apex_component(value)
        } else {
            component(value)
        }
    })
}
pub(crate) fn metadata_path(path: &str) -> bool {
    if !safe_path(path) {
        return false;
    }
    if path == APEX_INVENTORY || ODM_LINKS.contains(&path) || LEGACY.contains(&path) {
        return true;
    }
    if path == "/vendor/odm/etc/manifest.xml" {
        return true;
    }
    if ["/odm/etc/manifest_", "/vendor/odm/etc/manifest_"]
        .iter()
        .any(|prefix| {
            path.strip_prefix(prefix)
                .and_then(|p| p.strip_suffix(".xml"))
                .is_some_and(component)
        })
    {
        return true;
    }
    let roots = [
        "/system/etc/vintf",
        "/system/product/etc/vintf",
        "/system/system_ext/etc/vintf",
        "/product/etc/vintf",
        "/system_ext/etc/vintf",
        "/vendor/etc/vintf",
        "/odm/etc/vintf",
        "/vendor/odm/etc/vintf",
    ];
    if roots
        .iter()
        .any(|r| path == *r || path.strip_prefix(r).is_some_and(|p| p.starts_with('/')))
    {
        return path.split('/').count() <= 12;
    }
    if let Some(rest) = path.strip_prefix("/apex/") {
        if let Some((name, rest)) = rest.split_once('/') {
            return apex_component(name)
                && (rest == "etc/vintf" || rest.starts_with("etc/vintf/"))
                && rest.split('/').count() <= 10;
        }
    }
    false
}
pub(crate) fn canonical_for(requested: &str, observed: &str) -> bool {
    if requested == observed {
        return metadata_path(observed);
    }
    let map = [
        ("/product/", "/system/product/"),
        ("/system_ext/", "/system/system_ext/"),
        ("/odm/etc/", "/vendor/odm/etc/"),
    ];
    if map.iter().any(|(a, b)| {
        requested
            .strip_prefix(a)
            .is_some_and(|tail| observed == format!("{b}{tail}") && metadata_path(observed))
    }) {
        return true;
    }
    // The caller additionally matches this exact version to the active
    // inventory. This only recognizes the finite syntactic APEX mapping.
    match (
        requested.strip_prefix("/apex/"),
        observed.strip_prefix("/apex/"),
    ) {
        (Some(a), Some(b)) => match (a.split_once('/'), b.split_once('/')) {
            (Some((module, suffix)), Some((versioned, actual_suffix))) => {
                component(module)
                    && suffix == actual_suffix
                    && versioned
                        .strip_prefix(module)
                        .and_then(|v| v.strip_prefix('@'))
                        .is_some_and(|v| {
                            !v.is_empty() && v.len() <= 20 && v.bytes().all(|b| b.is_ascii_digit())
                        })
                    && metadata_path(observed)
            }
            _ => false,
        },
        _ => false,
    }
}
pub(crate) fn property(index: usize, bytes: &[u8]) -> Result<RuntimeProperty, String> {
    let (name, label) = *PROPERTIES.get(index).ok_or("unknown fixed property")?;
    if bytes.len() > 512 {
        return Err("property output exceeds bound".into());
    }
    let text = std::str::from_utf8(bytes).map_err(|_| "property is not UTF-8")?;
    let value = text
        .strip_suffix('\n')
        .ok_or("getprop did not produce its complete line")?;
    if value.bytes().any(|b| b.is_ascii_control()) {
        return Err("property contains control bytes".into());
    }
    match index {
        0 | 1 if !value.is_empty() && !component(value) => {
            return Err("invalid observed SKU component".into());
        }
        2 if value != "true" => return Err(format!("APEX is not ready; actual value {value:?}")),
        3 => {
            let n: u32 = value
                .parse()
                .map_err(|_| "first API level missing or not an integer")?;
            if n == 0 || n > 10_000 || value != n.to_string() {
                return Err("noncanonical first API level".into());
            }
        }
        _ => {}
    }
    Ok(RuntimeProperty {
        name: name.into(),
        value: value.into(),
        state: if value.is_empty() {
            "observed_empty_or_unset"
        } else {
            "observed_value"
        }
        .into(),
        original_property_type: label.into(),
    })
}
pub(crate) fn active_apex(raw: &[u8]) -> Result<Vec<ActiveApex>, String> {
    use quick_xml::{Reader, events::Event};
    if raw.is_empty() || raw.len() > MAX_FILE_BYTES {
        return Err("APEX inventory byte bound".into());
    }
    let mut reader = Reader::from_reader(raw);
    let mut depth = 0;
    let mut root = false;
    let mut closed = false;
    let mut names = BTreeSet::new();
    let mut active = Vec::new();
    let mut entries = 0;
    loop {
        match reader
            .read_event()
            .map_err(|e| format!("invalid APEX XML: {e}"))?
        {
            Event::Decl(_) if !root => {}
            Event::Start(e) if !root && e.name().as_ref() == b"apex-info-list" => {
                if e.attributes().next().is_some() {
                    return Err("unexpected APEX inventory root attributes".into());
                }
                root = true;
                depth = 1;
            }
            Event::Empty(e) if depth == 1 && e.name().as_ref() == b"apex-info" => {
                entries += 1;
                if entries > 2 * MAX_APEX {
                    return Err("APEX inventory entry bound".into());
                }
                let mut attrs = BTreeMap::new();
                for a in e.attributes() {
                    let a = a.map_err(|e| format!("duplicate/invalid APEX attribute: {e}"))?;
                    let key = std::str::from_utf8(a.key.as_ref())
                        .map_err(|_| "APEX key encoding")?
                        .to_owned();
                    let value = a
                        .decode_and_unescape_value(reader.decoder())
                        .map_err(|_| "APEX attribute encoding")?
                        .into_owned();
                    if key.len() > 64
                        || value.len() > 512
                        || value.bytes().any(|b| b.is_ascii_control())
                        || attrs.insert(key, value).is_some()
                    {
                        return Err("APEX attribute bound or duplicate".into());
                    }
                }
                let is_active = attrs.get("isActive").ok_or("missing actual isActive")?;
                if !["true", "false"].contains(&is_active.as_str()) {
                    return Err("invalid actual isActive".into());
                }
                let name = attrs.get("moduleName").ok_or("missing APEX moduleName")?;
                if !component(name) {
                    return Err("invalid APEX module name".into());
                }
                let version = attrs.get("versionCode").ok_or("missing APEX versionCode")?;
                if version.is_empty() || !version.bytes().all(|b| b.is_ascii_digit()) {
                    return Err("invalid APEX version".into());
                }
                if is_active == "true" {
                    if active.len() >= MAX_APEX || !names.insert(name.clone()) {
                        return Err("duplicate/excess active APEX".into());
                    }
                    active.push(ActiveApex {
                        module_name: name.clone(),
                        attributes: attrs,
                    });
                }
            }
            Event::End(e) if depth == 1 && e.name().as_ref() == b"apex-info-list" => {
                depth = 0;
                closed = true;
            }
            Event::Text(e) if e.as_ref().iter().all(u8::is_ascii_whitespace) => {}
            Event::Comment(_) => {}
            Event::Eof if root && closed && depth == 0 => break,
            _ => return Err("APEX inventory is not the finite flat XML schema".into()),
        }
    }
    if active.is_empty() {
        return Err("actual active APEX inventory is empty".into());
    }
    active.sort_by(|a, b| a.module_name.cmp(&b.module_name));
    Ok(active)
}
pub(crate) fn stat_output(
    paths: &[String],
    stdout: &[u8],
    stderr: &[u8],
    code: i32,
) -> Result<(BTreeMap<String, PublicStat>, Vec<MissingPath>), String> {
    if paths.is_empty()
        || paths.len() > MAX_NODES
        || !paths.iter().all(|p| metadata_path(p))
        || stdout.len() > 256 * 1024
        || stderr.len() > 64 * 1024
    {
        return Err("stat input/output bound".into());
    }
    let expected: BTreeSet<_> = paths.iter().map(String::as_str).collect();
    if expected.len() != paths.len() {
        return Err("duplicate stat input".into());
    }
    let text = std::str::from_utf8(stdout).map_err(|_| "stat output encoding")?;
    let errors = std::str::from_utf8(stderr).map_err(|_| "stat stderr encoding")?;
    if (!text.is_empty() && !text.ends_with('\n'))
        || (!errors.is_empty() && !errors.ends_with('\n'))
    {
        return Err("truncated stat output".into());
    }
    let mut found = BTreeMap::new();
    for line in text.lines() {
        let p: Vec<_> = line.split('|').collect();
        if p.len() != 10 || !expected.contains(p[0]) {
            return Err("stat row shape or path".into());
        }
        let number = |s: &str| {
            s.parse::<u64>()
                .map_err(|_| "invalid stat integer".to_owned())
        };
        let mode = u32::from_str_radix(p[1], 16).map_err(|_| "invalid stat mode")?;
        let uid = u32::try_from(number(p[2])?).map_err(|_| "stat uid overflow")?;
        let gid = u32::try_from(number(p[3])?).map_err(|_| "stat gid overflow")?;
        let row = PublicStat {
            path: p[0].into(),
            mode,
            uid,
            gid,
            links: number(p[4])?,
            device: number(p[5])?,
            inode: number(p[6])?,
            bytes: number(p[7])?,
            modified: p[8].into(),
            changed: p[9].into(),
        };
        if row.inode == 0
            || row.links == 0
            || row.modified.len() < 20
            || row.changed.len() < 20
            || row.modified.len() > 64
            || row.changed.len() > 64
            || found.insert(row.path.clone(), row).is_some()
        {
            return Err("invalid or duplicate stat identity".into());
        }
    }
    let mut missing = Vec::new();
    let mut absent = BTreeSet::new();
    for line in errors.lines() {
        let path = paths
            .iter()
            .find(|p| {
                line == format!("stat: '{}': No such file or directory", p)
                    || line == format!("stat: {}: No such file or directory", p)
            })
            .ok_or("stat failed for a reason other than exact original-tool ENOENT")?;
        if found.contains_key(path) || !absent.insert(path.clone()) {
            return Err("ambiguous stat absence".into());
        }
        missing.push(MissingPath {
            path: path.clone(),
            state: "observed_lookup_enoent".into(),
            stderr_line: line.into(),
        });
    }
    if found.len() + absent.len() != expected.len()
        || (missing.is_empty() && code != 0)
        || (!missing.is_empty() && code != 1)
    {
        return Err("incomplete stat roster or inconsistent actual exit".into());
    }
    missing.sort_by(|a, b| a.path.cmp(&b.path));
    Ok((found, missing))
}
pub(crate) fn directory_roster(raw: &[u8], roots: &[String]) -> Result<Vec<String>, String> {
    if raw.is_empty() || raw.len() > 64 * 1024 || !raw.ends_with(&[0]) {
        return Err("directory roster incomplete or oversized".into());
    }
    let mut paths = BTreeSet::new();
    for bytes in raw[..raw.len() - 1].split(|b| *b == 0) {
        let path = std::str::from_utf8(bytes).map_err(|_| "directory path encoding")?;
        if !metadata_path(path)
            || !roots
                .iter()
                .any(|r| path == r || path.strip_prefix(r).is_some_and(|p| p.starts_with('/')))
            || !paths.insert(path.to_owned())
            || paths.len() > MAX_NODES
        {
            return Err("directory path escaped, repeated or exceeded bound".into());
        }
    }
    if !roots.iter().all(|r| paths.contains(r)) {
        return Err("directory root missing from actual find output".into());
    }
    Ok(paths.into_iter().collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_request_accepts_only_an_epoch_comparison() {
        let epoch = RuntimeEpoch {
            boot_id: "boot".into(),
            cell_host_pid: 12,
            framework_host_pid: 34,
            framework_start_ticks: 56,
        };
        let value = serde_json::json!({"command":"observe_runtime_vintf","expected_epoch":epoch});
        assert!(serde_json::from_value::<super::super::ControlRequest>(value.clone()).is_ok());
        for field in ["pid", "path", "argv", "property", "limits", "passed"] {
            let mut extra = value.clone();
            extra[field] = serde_json::json!(1);
            assert!(serde_json::from_value::<super::super::ControlRequest>(extra).is_err());
        }
        let mut extra = value;
        extra["expected_epoch"]["selector"] = serde_json::json!(true);
        assert!(serde_json::from_value::<super::super::ControlRequest>(extra).is_err());
    }
    #[test]
    fn finite_paths_cannot_read_accounts_or_escape_apex() {
        for p in [
            "/system/etc/vintf/manifest.xml",
            "/vendor/etc/vintf/manifest/foo.xml",
            "/apex/com.android.art/etc/vintf/manifest.xml",
            "/apex/com.android.art@370000000/etc/vintf/manifest.xml",
            "/vendor/odm/etc/vintf",
            "/vendor/odm/etc/manifest.xml",
            "/vendor/odm/etc/manifest_board.xml",
        ] {
            assert!(metadata_path(p), "{p}");
        }
        for p in [
            "/data/system/accounts.xml",
            "/apex/com.android.art/etc/vintf/../x",
            "/apex/../../data/etc/vintf/x",
            "/vendor/etc/passwd",
            "/proc/self/mountinfo",
            "/system/etc/vintf//x",
            "/system/etc/vintf/x\n",
            "/vendor/etc/vintf/x@y.xml",
            "/apex/com.android.art@x/etc/vintf/x",
            "/apex/com.android.art@1@2/etc/vintf/x",
        ] {
            assert!(!metadata_path(p), "{p}");
        }
        assert!(canonical_for("/odm/etc/vintf", "/vendor/odm/etc/vintf"));
        assert!(!canonical_for("/odm/etc/vintf", "/data/local/tmp/vintf"));
        assert!(canonical_for(
            "/apex/com.android.art/etc/vintf",
            "/apex/com.android.art@370000000/etc/vintf"
        ));
        assert!(!canonical_for(
            "/apex/com.android.art/etc/vintf",
            "/apex/com.android.runtime@370000000/etc/vintf"
        ));
        assert!(!canonical_for(
            "/apex/com.android.art/etc/vintf",
            "/apex/com.android.art@1/etc/private"
        ));
    }
    #[test]
    fn property_empty_unset_unready_and_denial_are_distinct() {
        assert_eq!(property(0, b"\n").unwrap().state, "observed_empty_or_unset");
        assert!(property(0, b"").is_err());
        assert!(property(2, b"false\n").is_err());
        assert!(property(2, b"\n").is_err());
        assert!(property(3, b"037\n").is_err());
        assert_eq!(property(3, b"37\n").unwrap().value, "37");
        assert!(property(0, b"../../private\n").is_err());
    }
    #[test]
    fn actual_apex_inventory_rejects_duplicates_doctype_and_unknown_nesting() {
        let row = r#"<apex-info moduleName="com.android.art" versionCode="1" isActive="true"/>"#;
        let xml = format!("<apex-info-list>{row}</apex-info-list>");
        assert_eq!(active_apex(xml.as_bytes()).unwrap().len(), 1);
        for bad in [
            format!("<apex-info-list>{row}{row}</apex-info-list>"),
            format!("<!DOCTYPE apex-info-list SYSTEM 'file:///private'>{xml}"),
            xml.replace("com.android.art", "../../data"),
            xml.replace("isActive=\"true\"", "isActive=\"maybe\""),
            xml.replace("</apex-info-list>", ""),
            "<apex-info-list/>".into(),
        ] {
            assert!(active_apex(bad.as_bytes()).is_err(), "{bad}");
        }
    }
    #[test]
    fn stat_absence_requires_exact_error_actual_exit_and_complete_roster() {
        let p = vec!["/odm/etc/vintf".to_owned()];
        let err = b"stat: '/odm/etc/vintf': No such file or directory\n";
        assert_eq!(stat_output(&p, b"", err, 1).unwrap().1.len(), 1);
        for (e, c) in [
            (b"stat: '/odm/etc/vintf': Permission denied\n".as_slice(), 1),
            (err.as_slice(), 0),
            (b"".as_slice(), 0),
            (b"stat: '/other': No such file or directory\n".as_slice(), 1),
        ] {
            assert!(stat_output(&p, b"", e, c).is_err());
        }
    }
    #[test]
    fn full_directory_roster_rejects_truncation_escape_and_duplicates() {
        let roots = vec!["/vendor/etc/vintf".to_owned()];
        let ok = b"/vendor/etc/vintf\0/vendor/etc/vintf/manifest.xml\0";
        assert_eq!(directory_roster(ok, &roots).unwrap().len(), 2);
        for bad in [
            b"/vendor/etc/vintf".as_slice(),
            b"/vendor/etc/vintf\0/private\0".as_slice(),
            b"/vendor/etc/vintf\0/vendor/etc/vintf\0".as_slice(),
        ] {
            assert!(directory_roster(bad, &roots).is_err());
        }
    }
}
