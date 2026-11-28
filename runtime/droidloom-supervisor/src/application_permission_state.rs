//! Complete user-zero PackageManager permission comparison for the selected CP3A.
//!
//! The original owner alone runs literal "cmd package dump-package PACKAGE".
//! This is PM requested/install/runtime state, including the actual shared UID.
//! It does not prove AppOps, account visibility, data persistence or acceptance.
//! Source: selected services.jar bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86,
//! classes2.dex 4f4c674fd5cde3f716414854bb150d997584017ab1fb922c52ea7d9f1741ad31:
//! Settings.dumpPackagesLPr/dumpPackageLPr/dumpSharedUsersLPr and permission
//! helpers; PackageSetting/SharedUserSetting.toString. Hidden system packages
//! are separate historical records, never the current installed permission set.
use crate::control::application_probe::{ApplicationInspection, RuntimeEpoch};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;

// A distinct fixed query, not an enlargement of the original four-read API.
pub(crate) const OUTPUT_BYTES: usize = 1024 * 1024;
pub(crate) const MAX_WIRE_BYTES: usize = 196_608;
const STATE_BYTES: usize = 131_072;
const MAX_PERMISSIONS: usize = 2048;
const MAX_SHARED_PACKAGES: usize = 1024;
pub const SCHEMA: &str = "droidloom.application-pm-permission-state.v1";

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PermissionGrant {
    granted: bool,
    flags: BTreeSet<String>,
}
impl PermissionGrant {
    pub fn granted(&self) -> bool {
        self.granted
    }
    pub fn flags(&self) -> &BTreeSet<String> {
        &self.flags
    }
    fn valid(&self) -> bool {
        self.flags.len() <= 32 && self.flags.iter().all(|v| flag_name(v))
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SharedUidPermissionState {
    name: String,
    packages: BTreeSet<String>,
}
impl SharedUidPermissionState {
    pub fn name(&self) -> &str {
        &self.name
    }
    pub fn packages(&self) -> &BTreeSet<String> {
        &self.packages
    }
}
/// Same fixed dump-package output, for the selected GMS package only.
/// This is component-enable configuration, never running-service/API evidence.
/// Selected classes2.dex 4f4c674f... Settings.dumpPackageLPr prints the actual
/// user header and complete nonempty disabled/enabled component sets. Its
/// selected dump is c47bcb1d38a3dd7b934c3da7fa1e67e6fe7c71757ac066e857b05178891cff50.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct GmsComponentEnablement {
    enabled_setting: u8,
    hidden: bool,
    suspended: bool,
    app_lock_enabled: bool,
    quarantined: bool,
    enabled_components: BTreeSet<String>,
    disabled_components: BTreeSet<String>,
}
impl GmsComponentEnablement {
    fn valid(&self) -> bool {
        self.enabled_setting <= 4
            && self.enabled_components.len() <= 512
            && self.disabled_components.len() <= 512
            && self
                .enabled_components
                .iter()
                .chain(&self.disabled_components)
                .all(|v| component_name(v))
            && self
                .enabled_components
                .is_disjoint(&self.disabled_components)
    }
    pub(crate) fn application_enabled(&self, manifest_default: bool) -> bool {
        match self.enabled_setting {
            0 => manifest_default,
            1 => true,
            _ => false,
        }
    }
    pub(crate) fn require_unrestricted(&self) -> Result<(), String> {
        if !self.valid()
            || self.hidden
            || self.suspended
            || self.app_lock_enabled
            || self.quarantined
        {
            return Err("GMS actual user-zero component state is restricted or malformed".into());
        }
        Ok(())
    }
    pub(crate) fn service_enabled(&self, name: &str, manifest_default: bool) -> bool {
        if self.enabled_components.contains(name) {
            true
        } else if self.disabled_components.contains(name) {
            false
        } else {
            manifest_default
        }
    }
}
fn component_name(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 512
        && v.contains('.')
        && v.split('.').all(|p| {
            !p.is_empty()
                && p.bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'$')
        })
}
fn gms_components(
    package_body: &[&str],
    target_user: &[&str],
) -> Result<GmsComponentEnablement, String> {
    let header = one_prefix(package_body, "    User 0: ")?;
    let fields = header.split(' ').collect::<Vec<_>>();
    let field = |name: &str| -> Result<&str, String> {
        let values = fields
            .iter()
            .filter_map(|v| v.strip_prefix(name))
            .collect::<Vec<_>>();
        if values.len() != 1 {
            return Err(format!(
                "GMS actual PM user field {name} is missing or repeated"
            ));
        }
        Ok(values[0])
    };
    let boolean = |name: &str| -> Result<bool, String> {
        match field(name)? {
            "true" => Ok(true),
            "false" => Ok(false),
            _ => Err(format!("GMS actual PM user field {name} is not boolean")),
        }
    };
    let components = |title: &str| -> Result<BTreeSet<String>, String> {
        let rows = child_rows(target_user, title, "        ")?;
        // This selected formatter omits an empty set; it never prints an empty
        // header. Do not reinterpret damaged/indented rows as empty defaults.
        if rows.as_ref().is_some_and(Vec::is_empty) {
            return Err("GMS component override header has no complete rows".into());
        }
        let mut names = BTreeSet::new();
        for name in rows.unwrap_or_default() {
            if !component_name(name) || !names.insert(name.into()) || names.len() > 512 {
                return Err("GMS component override name/count is malformed or repeated".into());
            }
        }
        Ok(names)
    };
    for line in target_user {
        if (line.contains("enabledComponents") || line.contains("disabledComponents"))
            && !matches!(
                *line,
                "      enabledComponents:" | "      disabledComponents:"
            )
        {
            return Err(
                "GMS component override title/indentation differs from the selected formatter"
                    .into(),
            );
        }
    }
    let value = GmsComponentEnablement {
        enabled_setting: number(field("enabled=")?)?,
        hidden: boolean("hidden=")?,
        suspended: boolean("suspended=")?,
        app_lock_enabled: boolean("appLockEnabled=")?,
        quarantined: boolean("quarantined=")?,
        enabled_components: components("      enabledComponents:")?,
        disabled_components: components("      disabledComponents:")?,
    };
    if !value.valid() {
        return Err("GMS component override sets overlap or application setting is unknown".into());
    }
    Ok(value)
}

/// Comparison data only. Only the Inspector's non-serializable token is live.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PackagePermissionState {
    package: String,
    user: u32,
    installed: bool,
    app_id: u32,
    version_code: u64,
    requested_permissions: BTreeSet<String>,
    install_permissions: BTreeMap<String, PermissionGrant>,
    runtime_permissions: BTreeMap<String, PermissionGrant>,
    gids: Option<String>,
    shared_uid: Option<SharedUidPermissionState>,
    // Absent for every other package: preserve their original serialized bytes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    gms_component_enablement: Option<GmsComponentEnablement>,
}
impl PackagePermissionState {
    pub fn package(&self) -> &str {
        &self.package
    }
    pub fn app_id(&self) -> u32 {
        self.app_id
    }
    pub fn version_code(&self) -> u64 {
        self.version_code
    }
    pub fn requested_permissions(&self) -> &BTreeSet<String> {
        &self.requested_permissions
    }
    pub fn install_permissions(&self) -> &BTreeMap<String, PermissionGrant> {
        &self.install_permissions
    }
    pub fn runtime_permissions(&self) -> &BTreeMap<String, PermissionGrant> {
        &self.runtime_permissions
    }
    pub fn gids(&self) -> Option<&str> {
        self.gids.as_deref()
    }
    pub fn shared_uid(&self) -> Option<&SharedUidPermissionState> {
        self.shared_uid.as_ref()
    }

    pub(crate) fn gms_component_enablement(&self) -> Option<&GmsComponentEnablement> {
        self.gms_component_enablement.as_ref()
    }
    fn validate(&self) -> Result<(), String> {
        match (&*self.package, &self.gms_component_enablement) {
            ("com.google.android.gms", Some(value)) if value.valid() => {}
            ("com.google.android.gms", _) | (_, Some(_)) => {
                return Err(
                    "GMS component comparison is absent, malformed or assigned to another package"
                        .into(),
                );
            }
            (_, None) => {}
        }
        let valid_map = |map: &BTreeMap<String, PermissionGrant>| {
            map.len() <= MAX_PERMISSIONS
                && map
                    .iter()
                    .all(|(name, grant)| dotted_name(name) && grant.valid())
        };
        if !crate::engine_custody::selected_package(&self.package)
            || self.user != 0
            || !self.installed
            || self.app_id == 0
            || self.app_id >= 100_000
            || self.requested_permissions.len() > MAX_PERMISSIONS
            || !self.requested_permissions.iter().all(|n| dotted_name(n))
            || !valid_map(&self.install_permissions)
            || !valid_map(&self.runtime_permissions)
            || self.gids.as_ref().is_some_and(|v| !gids_text(v))
            || self.shared_uid.as_ref().is_some_and(|s| {
                !dotted_name(&s.name)
                    || s.packages.is_empty()
                    || s.packages.len() > MAX_SHARED_PACKAGES
                    || !s.packages.contains(&self.package)
                    || !s.packages.iter().all(|p| p == "android" || dotted_name(p))
            })
            || serde_json::to_vec(self).map_err(|e| e.to_string())?.len() > STATE_BYTES
        {
            return Err("complete PM permission comparison shape or bound differs".into());
        }
        Ok(())
    }
    fn require_application(&self, actual: &ApplicationInspection) -> Result<(), String> {
        self.validate()?;
        if actual.user != 0
            || self.package != actual.package
            || self.app_id != actual.uid
            || self.version_code != actual.version_code
        {
            return Err(
                "PM permission comparison differs from the actual installed subject".into(),
            );
        }
        Ok(())
    }
}

#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApplicationPermissionStateFacts {
    schema: String,
    epoch: RuntimeEpoch,
    state: PackagePermissionState,
    state_sha256: String,
    stdout_bytes: usize,
    stdout_sha256: String,
    query_receipt: Value,
    comparison_only: bool,
}
pub(crate) type ParsedPermissionState = PackagePermissionState;
fn hash(b: &[u8]) -> String {
    format!("{:x}", Sha256::digest(b))
}
fn digest(v: &str) -> bool {
    v.len() == 64
        && v.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn dotted_name(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 255
        && v.contains('.')
        && v.split('.')
            .all(|p| !p.is_empty() && p.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_'))
}
fn flag_name(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 96
        && (v
            .bytes()
            .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_')
            || v.strip_prefix("0x").is_some_and(|n| {
                !n.is_empty() && n.len() <= 8 && n.bytes().all(|b| b.is_ascii_hexdigit())
            }))
}
fn gids_text(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 4096
        && v.bytes()
            .all(|b| b.is_ascii_digit() || b" ,[]".contains(&b))
        && v.bytes().any(|b| b.is_ascii_digit())
}
fn check(end: Instant) -> Result<(), String> {
    if Instant::now() >= end {
        Err("original PM permission observation deadline elapsed".into())
    } else {
        Ok(())
    }
}
fn number<T: std::str::FromStr + ToString>(s: &str) -> Result<T, String> {
    let n = s
        .parse::<T>()
        .map_err(|_| "invalid PM permission integer".to_string())?;
    if n.to_string() != s {
        return Err("noncanonical PM permission integer".into());
    }
    Ok(n)
}
fn prefixed<'a>(s: &'a str, prefix: &str) -> Result<&'a str, String> {
    s.strip_prefix(prefix)
        .ok_or_else(|| "unexpected PM permission line".into())
}
fn one_prefix<'a>(ls: &[&'a str], prefix: &str) -> Result<&'a str, String> {
    let found = ls
        .iter()
        .filter_map(|s| s.strip_prefix(prefix))
        .collect::<Vec<_>>();
    if found.len() != 1 {
        return Err(format!("missing or duplicate PM field {prefix:?}"));
    }
    Ok(found[0])
}
fn optional_prefix<'a>(ls: &[&'a str], prefix: &str) -> Result<Option<&'a str>, String> {
    let found = ls
        .iter()
        .filter_map(|s| s.strip_prefix(prefix))
        .collect::<Vec<_>>();
    if found.len() > 1 {
        return Err(format!("duplicate PM field {prefix:?}"));
    }
    Ok(found.first().copied())
}
fn section<'a>(ls: &'a [&'a str], title: &str) -> Result<Option<&'a [&'a str]>, String> {
    let found = ls
        .iter()
        .enumerate()
        .filter(|(_, s)| **s == title)
        .map(|(i, _)| i)
        .collect::<Vec<_>>();
    if found.len() > 1 {
        return Err(format!("duplicate PM section {title}"));
    }
    let Some(start) = found.first().copied() else {
        return Ok(None);
    };
    let end = (start + 1..ls.len())
        .find(|i| !ls[*i].is_empty() && !ls[*i].starts_with(' '))
        .unwrap_or(ls.len());
    Ok(Some(&ls[start + 1..end]))
}
fn object_header<'a>(line: &'a str, prefix: &str) -> Result<(&'a str, &'a str), String> {
    let body = prefixed(line, prefix)?
        .strip_suffix("):")
        .ok_or("PM object header suffix")?;
    let (name, pointer) = body.split_once("] (").ok_or("PM object header fields")?;
    if !dotted_name(name)
        || pointer.is_empty()
        || pointer.len() > 8
        || !pointer
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("PM object name or identity hash differs".into());
    }
    Ok((name, pointer))
}
fn object_value<'a>(value: &'a str, prefix: &str) -> Result<(&'a str, &'a str, u32), String> {
    let body = prefixed(value, prefix)?
        .strip_suffix('}')
        .ok_or("PM object value suffix")?;
    let (pointer, rest) = body.split_once(' ').ok_or("PM object identity separator")?;
    let (name, uid) = rest.rsplit_once('/').ok_or("PM object appId separator")?;
    if pointer.is_empty()
        || pointer.len() > 8
        || !pointer
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        || !(name == "android" || dotted_name(name))
    {
        return Err("PM object value identity differs".into());
    }
    Ok((pointer, name, number(uid)?))
}
fn body<'a>(ls: &'a [&'a str], prefix: &str) -> Result<(&'a str, &'a [&'a str]), String> {
    let nonempty = ls
        .iter()
        .position(|l| !l.is_empty())
        .ok_or("empty PM object section")?;
    let header = ls[nonempty];
    prefixed(header, prefix)?;
    if ls[nonempty + 1..]
        .iter()
        .any(|l| !l.is_empty() && (!l.starts_with("    ") || l.starts_with(prefix)))
    {
        return Err("PM current object section contains another object or unbounded line".into());
    }
    Ok((header, &ls[nonempty + 1..]))
}
fn child_rows<'a>(
    ls: &'a [&'a str],
    title: &str,
    child_prefix: &str,
) -> Result<Option<Vec<&'a str>>, String> {
    let indexes = ls
        .iter()
        .enumerate()
        .filter(|(_, s)| **s == title)
        .map(|(i, _)| i)
        .collect::<Vec<_>>();
    if indexes.len() > 1 {
        return Err("duplicate PM permission subsection".into());
    }
    let Some(index) = indexes.first().copied() else {
        return Ok(None);
    };
    let mut rows = Vec::new();
    let indent = title.bytes().take_while(|b| *b == b' ').count();
    for line in &ls[index + 1..] {
        if line.is_empty() {
            continue;
        }
        if line.bytes().take_while(|b| *b == b' ').count() <= indent {
            break;
        }
        // Selected dumpPackageLPr prints this later non-permission field with
        // the same eight-space indent as runtime rows.
        if line.starts_with("        harmfulAppWarning: ") {
            break;
        }
        let row = prefixed(line, child_prefix)?;
        if row.starts_with(' ') || rows.len() >= MAX_PERMISSIONS * 4 {
            return Err("PM permission row indentation or count differs".into());
        }
        rows.push(row);
    }
    Ok(Some(rows))
}
fn grant(s: &str, install: bool) -> Result<(String, u32, PermissionGrant), String> {
    let (s, user) = match s.rsplit_once(", userId=") {
        Some((s, n)) if install => {
            let user = number::<u32>(n)?;
            if user == 0 || user > 21_474 {
                return Err("noncanonical foreign install user".into());
            }
            (s, user)
        }
        Some(_) => return Err("user selector inside runtime permission".into()),
        None => (s, 0),
    };
    let (name, rest) = s
        .split_once(": granted=")
        .ok_or("incomplete PM grant row")?;
    if !dotted_name(name) {
        return Err("invalid PM permission name".into());
    }
    let (granted, flags) = match rest.split_once(", flags=") {
        Some((v, f)) => {
            let values = f
                .strip_prefix("[ ")
                .and_then(|f| f.strip_suffix(']'))
                .ok_or("PM flags delimiters")?;
            let mut flags = BTreeSet::new();
            for value in values.split('|') {
                if !flag_name(value) || !flags.insert(value.to_string()) {
                    return Err("invalid or duplicate PM flag".into());
                }
            }
            if flags.len() > 32 {
                return Err("PM flag count exceeds one bitset".into());
            }
            (v, flags)
        }
        None => (rest, BTreeSet::new()),
    };
    let granted = match granted {
        "true" => true,
        "false" => false,
        _ => return Err("invalid PM grant boolean".into()),
    };
    Ok((name.into(), user, PermissionGrant { granted, flags }))
}
fn grants(
    ls: &[&str],
    title: &str,
    prefix: &str,
    install: bool,
    required: bool,
) -> Result<BTreeMap<String, PermissionGrant>, String> {
    let rows = child_rows(ls, title, prefix)?;
    if required && rows.is_none() {
        return Err("required complete runtime permission header is absent".into());
    }
    let mut all = BTreeMap::new();
    for row in rows.unwrap_or_default() {
        let (name, user, state) = grant(row, install)?;
        if all.insert((user, name), state).is_some() {
            return Err("duplicate package permission/user grant".into());
        }
    }
    let result = all
        .into_iter()
        .filter_map(|((user, name), state)| (user == 0).then_some((name, state)))
        .collect::<BTreeMap<_, _>>();
    if result.len() > MAX_PERMISSIONS {
        return Err("PM user-zero grant count exceeds bound".into());
    }
    Ok(result)
}
fn user_zero<'a>(ls: &'a [&'a str], installed: bool) -> Result<Option<&'a [&'a str]>, String> {
    let mut users = BTreeSet::new();
    let mut zero = None;
    let mut starts = Vec::new();
    for (i, l) in ls.iter().enumerate() {
        if let Some(rest) = l.strip_prefix("    User ") {
            let (n, tail) = rest.split_once(": ").ok_or("PM user header suffix")?;
            let user = number::<u32>(n)?;
            if user > 21_474 || !users.insert(user) {
                return Err("duplicate or out-of-range PM user".into());
            }
            if user == 0 {
                if installed {
                    let values = tail
                        .split(' ')
                        .filter_map(|s| s.strip_prefix("installed="))
                        .collect::<Vec<_>>();
                    if values != ["true"] {
                        return Err(
                            "target package is not unambiguously installed for user zero".into(),
                        );
                    }
                } else if !tail.is_empty() {
                    return Err("shared user header carries unexpected fields".into());
                }
                zero = Some(starts.len());
            }
            starts.push(i);
        }
    }
    let Some(z) = zero else {
        return Ok(None);
    };
    Ok(Some(
        &ls[starts[z] + 1..*starts.get(z + 1).unwrap_or(&ls.len())],
    ))
}
fn gids(ls: &[&str]) -> Result<Option<String>, String> {
    let v = optional_prefix(ls, "      gids=")?;
    if v.is_some_and(|v| !gids_text(v)) {
        return Err("invalid bounded PM GID comparison".into());
    }
    Ok(v.map(str::to_string))
}

fn grant_coverage(ls: &[&str]) -> Result<(), String> {
    // Do not silently convert a damaged or missing permission header to an
    // empty set. Validate foreign-user rows too, but never promote them to 0.
    let mut covered = BTreeSet::new();
    for row in child_rows(ls, "    install permissions:", "      ")?.unwrap_or_default() {
        grant(row, true)?;
        covered.insert(format!("      {row}"));
    }
    let starts = ls
        .iter()
        .enumerate()
        .filter(|(_, l)| l.starts_with("    User "))
        .map(|(i, _)| i)
        .collect::<Vec<_>>();
    for (j, start) in starts.iter().enumerate() {
        let end = *starts.get(j + 1).unwrap_or(&ls.len());
        let user = &ls[start + 1..end];
        // Also reject duplicate names in a nonzero user's actual subsection.
        grants(user, "      runtime permissions:", "        ", false, false)?;
        for row in child_rows(user, "      runtime permissions:", "        ")?.unwrap_or_default() {
            covered.insert(format!("        {row}"));
        }
    }
    if ls
        .iter()
        .any(|line| line.contains(": granted=") && !covered.contains(*line))
    {
        return Err("orphan or malformed PM grant row outside a complete subsection".into());
    }
    Ok(())
}

pub(crate) fn parse(
    package: &str,
    raw: &str,
    end: Instant,
) -> Result<ParsedPermissionState, String> {
    check(end)?;
    if !crate::engine_custody::selected_package(package)
        || raw.is_empty()
        || raw.len() > OUTPUT_BYTES
        || !raw.ends_with('\n')
        || raw.chars().any(|c| c.is_control() && c != '\n')
    {
        return Err(
            "complete selected PM output is invalid, truncated or exceeds its bound".into(),
        );
    }
    let ls = raw.lines().collect::<Vec<_>>();
    if ls.len() > 16_384
        || ls.iter().any(|l| l.len() > 8192)
        || ls.iter().any(|l| {
            ["Error:", "Failure", "Exception", "Permission Denial:"]
                .iter()
                .any(|p| l.starts_with(p))
        })
    {
        return Err("PM output line limit or explicit diagnostic differs".into());
    }
    let current = section(&ls, "Packages:")?.ok_or("current Packages section is absent")?;
    let (header, package_body) = body(current, "  Package [")?;
    let (name, package_pointer) = object_header(header, "  Package [")?;
    if name != package {
        return Err("current PM package is not the selected target".into());
    }
    grant_coverage(package_body)?;
    let app_id = number::<u32>(one_prefix(package_body, "    appId=")?)?;
    let version = one_prefix(package_body, "    versionCode=")?;
    let version_code = number::<u64>(version.split(' ').next().ok_or("PM version is absent")?)?;
    let mut requested_permissions = BTreeSet::new();
    for p in child_rows(package_body, "    requested permissions:", "      ")?.unwrap_or_default() {
        if !dotted_name(p)
            || !requested_permissions.insert(p.into())
            || requested_permissions.len() > MAX_PERMISSIONS
        {
            return Err("requested PM permission names duplicate or exceed their bound".into());
        }
    }
    let install_permissions = grants(
        package_body,
        "    install permissions:",
        "      ",
        true,
        false,
    )?;
    let target_user =
        user_zero(package_body, true)?.ok_or("target user zero package state is absent")?;
    let shared = optional_prefix(package_body, "    sharedUser=")?;
    let (runtime_permissions, gids, shared_uid) = if let Some(value) = shared {
        if child_rows(target_user, "      runtime permissions:", "        ")?.is_some()
            || gids(target_user)?.is_some()
        {
            return Err(
                "shared UID package contains a conflicting private runtime permission set".into(),
            );
        }
        let (pointer, shared_name, shared_id) = object_value(value, "SharedUserSetting{")?;
        if shared_id != app_id {
            return Err("package shared UID appId differs".into());
        }
        let shared_section = section(&ls, "Shared users:")?
            .ok_or("actual shared UID permission section is absent")?;
        let (shared_header, shared_body) = body(shared_section, "  SharedUser [")?;
        grant_coverage(shared_body)?;
        let (observed_name, observed_pointer) = object_header(shared_header, "  SharedUser [")?;
        if observed_name != shared_name
            || observed_pointer != pointer
            || number::<u32>(one_prefix(shared_body, "    appId=")?)? != app_id
        {
            return Err("shared UID object does not join the actual target package".into());
        }
        let rows = child_rows(shared_body, "    Packages", "      ")?
            .ok_or("shared UID package roster is absent")?;
        let mut packages = BTreeSet::new();
        for row in rows {
            let (member_pointer, member, uid) = object_value(row, "PackageSetting{")?;
            if uid != app_id
                || !packages.insert(member.into())
                || packages.len() > MAX_SHARED_PACKAGES
                || (member == package && member_pointer != package_pointer)
            {
                return Err("shared UID package membership differs or duplicates".into());
            }
        }
        if !packages.contains(package) {
            return Err("target is missing from its actual shared UID roster".into());
        }
        let shared_install = grants(
            shared_body,
            "    install permissions:",
            "      ",
            true,
            false,
        )?;
        if shared_install != install_permissions {
            return Err("package/shared UID complete install grants differ".into());
        }
        match user_zero(shared_body, false)? {
            Some(user) => (
                grants(user, "      runtime permissions:", "        ", false, true)?,
                gids(user)?,
                Some(SharedUidPermissionState {
                    name: shared_name.into(),
                    packages,
                }),
            ),
            None => {
                // Selected Settings skips this user only when both GIDs and
                // the entire permission collection are empty. An install
                // grant/flags above disproves that omission. A permission that
                // exists only for another user is printed as denied/flags-zero
                // for user zero by dumpInstallPermissionsLPr and is preserved.
                if install_permissions
                    .values()
                    .any(|g| g.granted || !g.flags.is_empty())
                {
                    return Err("shared UID user-zero state is missing despite nonempty install grant state".into());
                }
                (
                    BTreeMap::new(),
                    None,
                    Some(SharedUidPermissionState {
                        name: shared_name.into(),
                        packages,
                    }),
                )
            }
        }
    } else {
        if section(&ls, "Shared users:")?.is_some() {
            return Err("nonshared target returned an unrelated shared UID".into());
        }
        (
            grants(
                target_user,
                "      runtime permissions:",
                "        ",
                false,
                true,
            )?,
            gids(target_user)?,
            None,
        )
    };
    let state = PackagePermissionState {
        package: package.into(),
        user: 0,
        installed: true,
        app_id,
        version_code,
        requested_permissions,
        install_permissions,
        runtime_permissions,
        gids,
        shared_uid,
        gms_component_enablement: if package == "com.google.android.gms" {
            Some(gms_components(package_body, target_user)?)
        } else {
            None
        },
    };
    state.validate()?;
    check(end)?;
    Ok(state)
}
impl ApplicationPermissionStateFacts {
    #[cfg(target_os = "linux")]
    pub(crate) fn from_actual(
        actual: &crate::production_application::ApplicationPermissionStateObservation,
        expected: &RuntimeEpoch,
    ) -> Result<Self, String> {
        let state = actual.parsed().clone();
        let facts = Self {
            schema: SCHEMA.into(),
            epoch: actual.epoch().clone(),
            state_sha256: hash(&serde_json::to_vec(&state).map_err(|e| e.to_string())?),
            state,
            stdout_bytes: actual.stdout_bytes(),
            stdout_sha256: actual.stdout_sha256().into(),
            query_receipt: serde_json::to_value(actual.receipt()).map_err(|e| e.to_string())?,
            comparison_only: true,
        };
        facts.validate(expected, actual.package())?;
        Ok(facts)
    }
    pub(crate) fn validate(&self, expected: &RuntimeEpoch, package: &str) -> Result<(), String> {
        self.state.validate()?;
        if self.schema != SCHEMA
            || &self.epoch != expected
            || self.state.package != package
            || !self.comparison_only
            || !(1..=OUTPUT_BYTES).contains(&self.stdout_bytes)
            || !digest(&self.stdout_sha256)
            || self.state_sha256
                != hash(&serde_json::to_vec(&self.state).map_err(|e| e.to_string())?)
            || !crate::package_inventory_observation::receipt_valid(
                &self.query_receipt,
                self.stdout_bytes,
                &self.stdout_sha256,
            )
        {
            return Err(
                "actual PM permission identity, full comparison or retirement differs".into(),
            );
        }
        Ok(())
    }
    pub fn epoch(&self) -> &RuntimeEpoch {
        &self.epoch
    }
    pub fn state(&self) -> &PackagePermissionState {
        &self.state
    }
    pub fn state_sha256(&self) -> &str {
        &self.state_sha256
    }
    pub fn stdout_sha256(&self) -> &str {
        &self.stdout_sha256
    }
    pub fn require_application(&self, actual: &ApplicationInspection) -> Result<(), String> {
        self.validate(&actual.epoch, &actual.package)?;
        self.state.require_application(actual)
    }
    /// Two real observations compare semantic user-zero tables, never fresh
    /// process/retirement receipts or Java object identity presentation hashes.
    pub fn same_permissions(&self, other: &Self) -> Result<(), String> {
        self.validate(&self.epoch, &self.state.package)?;
        other.validate(&self.epoch, &self.state.package)?;
        if self.state != other.state {
            return Err("complete user-zero PM permissions changed".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn end() -> Instant {
        Instant::now() + std::time::Duration::from_secs(5)
    }
    fn normal() -> String {
        "Activity Resolver Table:\n  unrelated public metadata\n\nPackages:\n  Package [com.android.settings] (a1):\n    appId=1000\n    versionCode=36 minSdk=36 targetSdk=36\n    requested permissions:\n      android.permission.CAMERA\n      android.permission.INTERNET\n    install permissions:\n      android.permission.INTERNET: granted=true\n      android.permission.INTERNET: granted=false, userId=10\n    User 0: ceDataInode=1 deDataInode=2 installed=true hidden=false\n      gids=[3003]\n      runtime permissions:\n        android.permission.CAMERA: granted=false, flags=[ USER_SET|USER_FIXED]\n    User 10: ceDataInode=3 deDataInode=4 installed=true hidden=false\n      runtime permissions:\n        android.permission.CAMERA: granted=true\n\nHidden system packages:\n  Package [com.android.settings] (b2):\n    appId=1000\n    versionCode=1 targetSdk=36\n    User 0: installed=false\n      runtime permissions:\n        android.permission.CAMERA: granted=true\n".into()
    }
    fn shared() -> String {
        "Packages:\n  Package [com.android.settings] (a1):\n    appId=1000\n    sharedUser=SharedUserSetting{c3 android.uid.system/1000}\n    versionCode=36 minSdk=36 targetSdk=36\n    requested permissions:\n      android.permission.CAMERA\n    install permissions:\n      android.permission.INTERNET: granted=true\n    User 0: ceDataInode=1 deDataInode=2 installed=true hidden=false\n\nShared users:\n  SharedUser [android.uid.system] (c3):\n    appId=1000\n    Packages\n      PackageSetting{a1 com.android.settings/1000}\n      PackageSetting{d4 android/1000}\n    install permissions:\n      android.permission.INTERNET: granted=true\n    User 0: \n      gids=[3003]\n      runtime permissions:\n        android.permission.CAMERA: granted=true, flags=[ SYSTEM_FIXED]\n".into()
    }
    #[test]
    fn pm_permissions_keep_current_user_zero_distinct_from_hidden_and_other_users() {
        let p = parse("com.android.settings", &normal(), end()).unwrap();
        assert_eq!(p.app_id(), 1000);
        assert_eq!(p.version_code(), 36);
        assert!(!p.runtime_permissions()["android.permission.CAMERA"].granted());
        assert!(p.install_permissions()["android.permission.INTERNET"].granted());
        assert_eq!(p.requested_permissions().len(), 2);
        assert!(p.shared_uid().is_none());
        let other_pointers = normal().replace("(a1)", "(feed)").replace("(b2)", "(beef)");
        assert_eq!(
            p,
            parse("com.android.settings", &other_pointers, end()).unwrap()
        );
    }
    #[test]
    fn pm_permissions_join_real_shared_uid_object_members_and_complete_runtime() {
        let p = parse("com.android.settings", &shared(), end()).unwrap();
        assert!(p.runtime_permissions()["android.permission.CAMERA"].granted());
        assert_eq!(p.shared_uid().unwrap().packages().len(), 2);
        let p2 = parse(
            "com.android.settings",
            &shared().replace("c3", "f00").replace("a1", "abc"),
            end(),
        )
        .unwrap();
        assert_eq!(p, p2);
        for raw in [
            shared().replace("SharedUser [android.uid.system] (c3)","SharedUser [android.uid.system] (e5)"),
            shared().replace("PackageSetting{a1 com.android.settings/1000}","PackageSetting{f6 com.android.settings/1000}"),
            shared().replace("PackageSetting{d4 android/1000}","PackageSetting{d4 android/1001}"),
            shared().replace("      PackageSetting{a1 com.android.settings/1000}\n",""),
            shared().replace("    User 0: \n      gids=[3003]\n      runtime permissions:\n        android.permission.CAMERA: granted=true, flags=[ SYSTEM_FIXED]\n",""),
        ]{assert!(parse("com.android.settings",&raw,end()).is_err());}
    }
    #[test]
    fn pm_permissions_allow_source_empty_sets_but_not_missing_nonshared_runtime() {
        let empty = "Packages:\n  Package [com.android.settings] (a1):\n    appId=1000\n    versionCode=36 targetSdk=36\n    User 0: installed=true\n      runtime permissions:\n";
        let p = parse("com.android.settings", empty, end()).unwrap();
        assert!(p.requested_permissions().is_empty());
        assert!(p.runtime_permissions().is_empty());
        assert!(
            parse(
                "com.android.settings",
                &empty.replace("      runtime permissions:\n", ""),
                end()
            )
            .is_err()
        );
        let shared_empty = "Packages:\n  Package [com.android.settings] (a1):\n    appId=1000\n    sharedUser=SharedUserSetting{c3 android.uid.system/1000}\n    versionCode=36 targetSdk=36\n    User 0: installed=true\nShared users:\n  SharedUser [android.uid.system] (c3):\n    appId=1000\n    Packages\n      PackageSetting{a1 com.android.settings/1000}\n";
        assert!(
            parse("com.android.settings", shared_empty, end())
                .unwrap()
                .runtime_permissions()
                .is_empty()
        );
    }
    #[test]
    fn pm_permissions_reject_ambiguous_truncated_foreign_and_malformed_state() {
        let r = normal();
        for bad in [
            r.trim_end().to_string(),
            format!("{r}\0"),
            format!("{r}Packages:\n"),
            r.replacen("appId=1000", "appId=01000", 1),
            r.replacen("installed=true", "installed=false", 1),
            r.replacen("User 0:", "User 10:", 1),
            r.replacen(
                "Package [com.android.settings]",
                "Package [com.example.other]",
                1,
            ),
            r.replacen(
                "      android.permission.CAMERA\n",
                "      android.permission.CAMERA\n      android.permission.CAMERA\n",
                1,
            ),
            r.replacen("USER_SET|USER_FIXED", "USER_SET|USER_SET", 1),
            r.replacen("granted=false, flags=", "granted=maybe, flags=", 1),
            r.replacen("granted=false, userId=10", "granted=false, userId=0", 1),
            r.replacen("    appId=1000", "    appId=1000\n    appId=1000", 1),
            r.replacen(
                "        android.permission.CAMERA:",
                "        truncated android.permission.CAMERA:",
                1,
            ),
            "x".repeat(OUTPUT_BYTES + 1),
            format!("{r}Failure dumping service: denied\n"),
        ] {
            assert!(parse("com.android.settings", &bad, end()).is_err());
        }
        assert!(parse("com.example.unselected", &r, end()).is_err());
        assert!(parse("com.android.settings", &r, Instant::now()).is_err());
    }
    #[test]
    fn pm_permissions_semantic_comparison_detects_grants_flags_roster_and_requested_changes() {
        let a = parse("com.android.settings", &normal(), end()).unwrap();
        for raw in [
            normal().replacen("CAMERA: granted=false", "CAMERA: granted=true", 1),
            normal().replace("USER_SET|USER_FIXED", "USER_SET"),
            normal().replace("      android.permission.CAMERA\n", ""),
            normal().replacen("gids=[3003]", "gids=[3003, 3002]", 1),
        ] {
            assert_ne!(a, parse("com.android.settings", &raw, end()).unwrap());
        }
        let a = parse("com.android.settings", &shared(), end()).unwrap();
        let b = shared().replace("      PackageSetting{d4 android/1000}\n", "");
        assert_ne!(a, parse("com.android.settings", &b, end()).unwrap());
    }

    fn gms() -> String {
        "Packages:\n  Package [com.google.android.gms] (a1):\n    appId=10118\n    versionCode=252432036 minSdk=19 targetSdk=29\n    User 0: installed=true hidden=false suspended=false appLockEnabled=false stopped=false notLaunched=false enabled=0 instant=false virtual=false quarantined=false\n      runtime permissions:\n      disabledComponents:\n        org.microg.DisabledService\n      enabledComponents:\n        org.microg.EnabledService\n    User 10: installed=true hidden=true suspended=true appLockEnabled=true enabled=3 quarantined=true\n      runtime permissions:\n      disabledComponents:\n        org.microg.EnabledService\n\nHidden system packages:\n  Package [com.google.android.gms] (b2):\n    appId=10118\n    versionCode=1\n    User 0: installed=false hidden=true enabled=3\n".into()
    }
    #[test]
    fn gms_component_state_joins_only_current_package_user_zero() {
        let state = parse("com.google.android.gms", &gms(), end()).unwrap();
        assert_eq!(state.version_code(), 252432036);
        assert_eq!(state.app_id(), 10118);
        let v = state.gms_component_enablement().unwrap();
        v.require_unrestricted().unwrap();
        assert!(v.application_enabled(true));
        assert!(!v.application_enabled(false));
        assert!(v.service_enabled("org.microg.EnabledService", false));
        assert!(!v.service_enabled("org.microg.DisabledService", true));
        assert!(!v.service_enabled("org.microg.DefaultDisabled", false));
        assert!(v.service_enabled("org.microg.DefaultEnabled", true));
        assert_eq!(v.enabled_components.len(), 1);
        assert_eq!(v.disabled_components.len(), 1);
    }
    #[test]
    fn gms_component_state_rejects_missing_duplicate_conflicting_and_malformed_values() {
        for raw in [
            gms().replacen(" enabled=0", "", 1),
            gms().replacen(" enabled=0", " enabled=0 enabled=1", 1),
            gms().replacen(" enabled=0", " enabled=5", 1),
            gms().replacen(" enabled=0", " enabled=00", 1),
            gms().replacen(" hidden=false", "", 1),
            gms().replacen(" suspended=false", " suspended=no", 1),
            gms().replacen(" appLockEnabled=false", "", 1),
            gms().replacen(" quarantined=false", "", 1),
            gms().replacen("org.microg.DisabledService", "org.microg.EnabledService", 1),
            gms().replacen("      enabledComponents:", "     enabledComponents:", 1),
            gms().replacen("        org.microg.EnabledService\n", "", 1),
            gms().replacen(
                "        org.microg.EnabledService\n",
                "        org.microg.EnabledService\n        org.microg.EnabledService\n",
                1,
            ),
            gms().replacen(
                "org.microg.DisabledService",
                "org.microg/DisabledService",
                1,
            ),
            gms().replacen("    User 0:", "    User 1:", 1),
        ] {
            assert!(
                parse("com.google.android.gms", &raw, end()).is_err(),
                "{raw}"
            );
        }
    }
    #[test]
    fn gms_disabled_application_and_restrictions_never_become_enabled_success() {
        for n in 0..=4 {
            let raw = gms().replacen("enabled=0", &format!("enabled={n}"), 1);
            let state = parse("com.google.android.gms", &raw, end()).unwrap();
            assert_eq!(
                state
                    .gms_component_enablement()
                    .unwrap()
                    .application_enabled(false),
                n == 1
            );
        }
        for field in ["hidden", "suspended", "appLockEnabled", "quarantined"] {
            let raw = gms().replacen(&format!("{field}=false"), &format!("{field}=true"), 1);
            let state = parse("com.google.android.gms", &raw, end()).unwrap();
            assert!(
                state
                    .gms_component_enablement()
                    .unwrap()
                    .require_unrestricted()
                    .is_err()
            );
        }
    }
    #[test]
    fn gms_component_extension_is_required_only_for_exact_gms_wire_identity() {
        let state = parse("com.google.android.gms", &gms(), end()).unwrap();
        let mut wire = serde_json::to_value(&state).unwrap();
        wire.as_object_mut()
            .unwrap()
            .remove("gms_component_enablement");
        let missing: PackagePermissionState = serde_json::from_value(wire).unwrap();
        assert!(missing.validate().is_err());
        let mut wire = serde_json::to_value(&state).unwrap();
        wire["package"] = Value::String("com.android.settings".into());
        let foreign: PackagePermissionState = serde_json::from_value(wire).unwrap();
        assert!(foreign.validate().is_err());
    }
    #[test]
    fn non_gms_permission_serialization_and_semantics_remain_unchanged() {
        let a = parse("com.android.settings", &normal(), end()).unwrap();
        let raw = normal()
            .replacen(
                "installed=true hidden=false",
                "installed=true hidden=false suspended=false enabled=0",
                1,
            )
            .replacen(
                "    User 10:",
                "      disabledComponents:\n        org.example.Service\n    User 10:",
                1,
            );
        let b = parse("com.android.settings", &raw, end()).unwrap();
        assert_eq!(a, b);
        assert_eq!(
            serde_json::to_vec(&a).unwrap(),
            serde_json::to_vec(&b).unwrap()
        );
        assert!(
            !serde_json::to_value(&a)
                .unwrap()
                .as_object()
                .unwrap()
                .contains_key("gms_component_enablement")
        );
    }
}
