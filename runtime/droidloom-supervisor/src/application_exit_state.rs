//! Complete comparison projection of the selected CP3A exit-info producer.
//!
//! The private original-owner query is the only live producer. Deserializing
//! these values does not mint an observation, elapsed stability, or acceptance.
//! Grammar comes from the selected ApplicationExitInfo/AppExitInfoTracker DEX,
//! not a guessed upstream version. Displayed sequence numbers are not event IDs.
use crate::control::application_probe::{ApplicationInspection, RuntimeEpoch};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::time::Instant;

pub(crate) const OUTPUT_BYTES: usize = 65_536;
pub(crate) const MAX_WIRE_BYTES: usize = 196_608;
pub const SCHEMA: &str = "droidloom.application-exit-state.v1";
const MAX_RECORDS: usize = 128;
const HEADER: &str = "ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)";
const PERSIST: &str = "Last Timestamp of Persistence Into Persistent Storage: ";

/// A full record comparison. No verbose description, trace path or ANR content
/// leaves the query parser; their exact bytes remain committed in record_sha256.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApplicationExitRecord {
    container_uid: u32,
    timestamp: String,
    pid: u32,
    real_uid: u32,
    package_uid: u32,
    defining_uid: i32,
    user: u32,
    process: String,
    reason: i32,
    subreason: i32,
    status: i32,
    record_sha256: String,
}
impl ApplicationExitRecord {
    pub fn pid(&self) -> u32 {
        self.pid
    }
    pub fn package_uid(&self) -> u32 {
        self.package_uid
    }
    pub fn real_uid(&self) -> u32 {
        self.real_uid
    }
    pub fn reason(&self) -> i32 {
        self.reason
    }
    pub fn subreason(&self) -> i32 {
        self.subreason
    }
    pub fn status(&self) -> i32 {
        self.status
    }
    pub fn process(&self) -> &str {
        &self.process
    }
    pub fn timestamp(&self) -> &str {
        &self.timestamp
    }
    pub fn record_sha256(&self) -> &str {
        &self.record_sha256
    }
    fn validate(&self) -> bool {
        self.pid > 0
            && datetime(&self.timestamp)
            && self.defining_uid >= -1
            && self.reason >= 0
            && self.subreason >= 0
            && process_name(&self.process)
            && digest(&self.record_sha256)
    }
}

/// Wire comparison only. The actual client observation also retains the normal
/// peer PIDFD, whole installed identity, actual observation time and Main.
#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApplicationExitStateFacts {
    schema: String,
    epoch: RuntimeEpoch,
    package: String,
    persistence_timestamp: String,
    records: Vec<ApplicationExitRecord>,
    records_sha256: String,
    stdout_bytes: usize,
    stdout_sha256: String,
    query_receipt: Value,
    comparison_only: bool,
}
pub(crate) struct ParsedExitState {
    persistence_timestamp: String,
    records: Vec<ApplicationExitRecord>,
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn digest(v: &str) -> bool {
    v.len() == 64
        && v.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn datetime(v: &str) -> bool {
    let b = v.as_bytes();
    b.len() == 23
        && b.iter().enumerate().all(|(i, c)| match i {
            4 | 7 => *c == b'-',
            10 => *c == b' ',
            13 | 16 => *c == b':',
            19 => *c == b'.',
            _ => c.is_ascii_digit(),
        })
        && v[5..7].parse::<u32>().is_ok_and(|n| (1..=12).contains(&n))
        && v[8..10].parse::<u32>().is_ok_and(|n| (1..=31).contains(&n))
        && v[11..13].parse::<u32>().is_ok_and(|n| n < 24)
        && v[14..16].parse::<u32>().is_ok_and(|n| n < 60)
        && v[17..19].parse::<u32>().is_ok_and(|n| n < 60)
}
fn process_name(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 255
        && v.bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._:-".contains(&c))
}
fn number<T: std::str::FromStr + ToString>(v: &str) -> Result<T, String> {
    let n = v
        .parse::<T>()
        .map_err(|_| "invalid exit-state integer".to_string())?;
    if n.to_string() != v {
        return Err("noncanonical exit-state integer".into());
    }
    Ok(n)
}
fn pair<'a>(v: &'a str, separator: &str) -> Result<(&'a str, &'a str), String> {
    let (a, b) = v
        .split_once(separator)
        .ok_or_else(|| "missing exit-state field".to_string())?;
    if a.is_empty() || b.is_empty() {
        return Err("empty exit-state field".into());
    }
    Ok((a, b))
}
fn prefixed<'a>(v: &'a str, prefix: &str) -> Result<&'a str, String> {
    v.strip_prefix(prefix)
        .ok_or_else(|| "unexpected exit-state line".into())
}
fn labelled_number(v: &str) -> Result<i32, String> {
    let (n, label) = pair(v, " (")?;
    let label = label
        .strip_suffix(')')
        .ok_or_else(|| "exit-state reason label".to_string())?;
    if label.is_empty() || label.len() > 160 || label.chars().any(char::is_control) {
        return Err("invalid exit-state reason label".into());
    }
    let n = number::<i32>(n)?;
    if n < 0 {
        return Err("negative exit-state reason".into());
    }
    Ok(n)
}
fn check_time(end: Instant) -> Result<(), String> {
    if Instant::now() >= end {
        Err("original exit-state observation deadline elapsed".into())
    } else {
        Ok(())
    }
}
fn record(uid: u32, body: &[&str]) -> Result<ApplicationExitRecord, String> {
    if body.len() != 5 {
        return Err("incomplete exit-state record".into());
    }
    let (timestamp, rest) = pair(prefixed(body[0], "          timestamp=")?, " pid=")?;
    let (pid, rest) = pair(rest, " realUid=")?;
    let (real_uid, rest) = pair(rest, " packageUid=")?;
    let (package_uid, rest) = pair(rest, " definingUid=")?;
    let (defining_uid, user) = pair(rest, " user=")?;
    let (process, rest) = pair(prefixed(body[1], "          process=")?, " reason=")?;
    let (reason, rest) = pair(rest, " subreason=")?;
    let (subreason, status) = pair(rest, " status=")?;
    let (importance, rest) = pair(prefixed(body[2], "          importance=")?, " pss=")?;
    let _: i32 = number(importance)?;
    let (pss, rest) = pair(rest, " rss=")?;
    let (rss, rest) = pair(rest, " state=")?;
    let (state, trace) = pair(rest, " trace=")?;
    if [pss, rss].iter().any(|v| {
        v.len() > 32
            || !v
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b" .".contains(&b))
    }) || trace.len() > 4096
        || trace.chars().any(char::is_control)
    {
        return Err("invalid bounded exit memory or trace comparison".into());
    }
    if state != "empty" {
        let _: u32 = number(
            state
                .strip_suffix(" bytes")
                .ok_or_else(|| "invalid exit-state payload length".to_string())?,
        )?;
    }
    prefixed(body[3], "          description=")?;
    prefixed(body[4], "          anrInfo=")?;
    let row = ApplicationExitRecord {
        container_uid: uid,
        timestamp: timestamp.into(),
        pid: number(pid)?,
        real_uid: number(real_uid)?,
        package_uid: number(package_uid)?,
        defining_uid: number(defining_uid)?,
        user: number(user)?,
        process: process.into(),
        reason: labelled_number(reason)?,
        subreason: labelled_number(subreason)?,
        status: number(status)?,
        // Sequence headers are presentation only. Preserve all five actual
        // record lines including opaque description/ANR/trace bytes.
        record_sha256: hash(format!("{uid}\n{}\n", body.join("\n")).as_bytes()),
    };
    if !row.validate() {
        return Err("exit-state record identity differs".into());
    }
    Ok(row)
}
pub(crate) fn parse(package: &str, raw: &str, end: Instant) -> Result<ParsedExitState, String> {
    check_time(end)?;
    if !crate::engine_custody::selected_package(package)
        || raw.is_empty()
        || raw.len() > OUTPUT_BYTES
        || !raw.ends_with('\n')
        || raw.chars().any(|c| c.is_control() && c != '\n')
    {
        return Err("complete selected-package exit output is invalid or exceeds its bound".into());
    }
    let lines = raw.lines().collect::<Vec<_>>();
    if lines.len() < 2 || lines[0] != HEADER || lines.iter().any(|l| l.len() > 8192) {
        return Err("complete exit-state header or line bound differs".into());
    }
    let persistence = prefixed(lines[1], PERSIST)?;
    if !datetime(persistence) {
        return Err("invalid exit-history persistence timestamp".into());
    }
    let mut records = Vec::new();
    if lines.len() > 2 {
        if lines[2] != format!("  package: {package}") {
            return Err(
                "exit-state output contains another package or an unexpected section".into(),
            );
        }
        let mut i = 3;
        let mut prior_uid = None;
        let mut seen = BTreeSet::new();
        while i < lines.len() {
            check_time(end)?;
            let uid = number::<u32>(prefixed(lines[i], "    Historical Process Exit for uid=")?)?;
            if prior_uid.is_some_and(|prior| prior >= uid) {
                return Err("exit-state UID groups repeat or are out of order".into());
            }
            prior_uid = Some(uid);
            i += 1;
            let mut index = 0usize;
            while i < lines.len() && lines[i].starts_with("        ApplicationExitInfo ") {
                if lines[i] != format!("        ApplicationExitInfo #{index}:")
                    || i + 6 > lines.len()
                    || records.len() >= MAX_RECORDS
                {
                    return Err("exit-state sequence, completeness or record limit differs".into());
                }
                let row = record(uid, &lines[i + 1..i + 6])?;
                if !seen.insert(row.record_sha256.clone()) {
                    return Err("duplicate complete exit-state record".into());
                }
                records.push(row);
                i += 6;
                index += 1;
            }
        }
    }
    check_time(end)?;
    Ok(ParsedExitState {
        persistence_timestamp: persistence.into(),
        records,
    })
}
impl ApplicationExitStateFacts {
    #[cfg(target_os = "linux")]
    pub(crate) fn from_actual(
        actual: &crate::production_application::ApplicationExitStateObservation,
        expected: &RuntimeEpoch,
    ) -> Result<Self, String> {
        let parsed = actual.parsed();
        let records = parsed.records.clone();
        let facts = Self {
            schema: SCHEMA.into(),
            epoch: actual.epoch().clone(),
            package: actual.package().into(),
            persistence_timestamp: parsed.persistence_timestamp.clone(),
            records_sha256: hash(&serde_json::to_vec(&records).map_err(|e| e.to_string())?),
            records,
            stdout_bytes: actual.stdout_bytes(),
            stdout_sha256: actual.stdout_sha256().into(),
            query_receipt: serde_json::to_value(actual.receipt()).map_err(|e| e.to_string())?,
            comparison_only: true,
        };
        facts.validate(expected, actual.package())?;
        Ok(facts)
    }
    pub(crate) fn validate(&self, expected: &RuntimeEpoch, package: &str) -> Result<(), String> {
        if self.schema != SCHEMA
            || &self.epoch != expected
            || self.package != package
            || !crate::engine_custody::selected_package(package)
            || !self.comparison_only
            || !datetime(&self.persistence_timestamp)
            || self.records.len() > MAX_RECORDS
            || !(1..=OUTPUT_BYTES).contains(&self.stdout_bytes)
            || !digest(&self.stdout_sha256)
            || self.records.iter().any(|r| !r.validate())
            || self
                .records
                .iter()
                .map(|r| &r.record_sha256)
                .collect::<BTreeSet<_>>()
                .len()
                != self.records.len()
            || self.records_sha256
                != hash(&serde_json::to_vec(&self.records).map_err(|e| e.to_string())?)
            || !crate::package_inventory_observation::receipt_valid(
                &self.query_receipt,
                self.stdout_bytes,
                &self.stdout_sha256,
            )
        {
            return Err(
                "actual exit-state comparison identity, complete records or retirement differs"
                    .into(),
            );
        }
        Ok(())
    }
    pub fn package(&self) -> &str {
        &self.package
    }
    pub fn epoch(&self) -> &RuntimeEpoch {
        &self.epoch
    }
    pub fn records(&self) -> &[ApplicationExitRecord] {
        &self.records
    }
    pub fn stdout_sha256(&self) -> &str {
        &self.stdout_sha256
    }
    pub fn records_sha256(&self) -> &str {
        &self.records_sha256
    }
    pub fn require_application(&self, application: &ApplicationInspection) -> Result<(), String> {
        self.validate(&application.epoch, &application.package)?;
        if application.user != 0 || application.uid == 0 || application.uid >= 100_000 {
            return Err(
                "exit-state comparison requires the actual selected user-zero application".into(),
            );
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
    fn head() -> String {
        format!("{HEADER}\n{PERSIST}2026-11-27 01:02:03.004\n")
    }
    fn body(index: usize, pid: u32, reason: i32) -> String {
        format!(
            "        ApplicationExitInfo #{index}:\n          timestamp=2026-11-27 01:02:03.004 pid={pid} realUid=10123 packageUid=10123 definingUid=-1 user=0\n          process=com.android.settings reason={reason} (NORMAL LABEL) subreason=0 (UNKNOWN) status=0\n          importance=100 pss=1.0MB rss=2.0MB state=empty trace=null\n          description=null\n          anrInfo=null\n"
        )
    }
    fn sample() -> String {
        format!(
            "{}  package: com.android.settings\n    Historical Process Exit for uid=10123\n{}",
            head(),
            body(0, 123, 6)
        )
    }
    #[test]
    fn exit_history_parses_complete_empty_and_uid_grouped_output_without_display_ids() {
        assert!(
            parse("com.android.settings", &head(), end())
                .unwrap()
                .records
                .is_empty()
        );
        let before = parse("com.android.settings", &sample(), end()).unwrap();
        let after = format!(
            "{}  package: com.android.settings\n    Historical Process Exit for uid=10123\n{}{}",
            head(),
            body(0, 124, 4),
            body(1, 123, 6)
        );
        let after = parse("com.android.settings", &after, end()).unwrap();
        assert_eq!(
            before.records[0].record_sha256,
            after.records[1].record_sha256
        );
        assert_eq!(after.records[0].reason(), 4);
        let multi = format!(
            "{}    Historical Process Exit for uid=110123\n{}",
            sample(),
            body(0, 321, 0)
                .replace(
                    "realUid=10123 packageUid=10123",
                    "realUid=110123 packageUid=110123"
                )
                .replace("user=0", "user=1")
        );
        assert_eq!(
            parse("com.android.settings", &multi, end())
                .unwrap()
                .records
                .len(),
            2
        );
    }
    #[test]
    fn exit_history_rejects_truncation_foreign_sections_duplicates_and_deadlines() {
        let raw = sample();
        let cases = [
            raw.trim_end().into(),
            raw.replace(
                "  package: com.android.settings",
                "  package: com.example.other",
            ),
            raw.replace("ApplicationExitInfo #0:", "ApplicationExitInfo #1:"),
            raw.replace("pid=123", "pid=00123"),
            raw.replace("2026-11-27", "2026-99-27"),
            raw.replace("          anrInfo=null\n", ""),
            raw.replace("          description=null", "          extra=true"),
            format!("{raw}Error: denied\n"),
            format!("{}{}", raw, body(1, 123, 6)),
            format!("{raw}    Historical Process Exit for uid=10123\n"),
            format!("{raw}\0"),
            "x".repeat(OUTPUT_BYTES + 1),
        ];
        for (i, bad) in cases.into_iter().enumerate() {
            assert!(parse("com.android.settings", &bad, end()).is_err(), "{i}");
        }
        assert!(parse("com.example.unselected", &raw, end()).is_err());
        assert!(parse("com.android.settings", &raw, Instant::now()).is_err());
    }
}
