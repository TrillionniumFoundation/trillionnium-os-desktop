//! Bounded comparison produced by the normal, fixed Calendar counts class.
//!
//! Parsing these bytes does not create a live observation or award a gate.
//! The factory consumer must retain its actual Main, original JAR, provider
//! identity, stdout/receipt and retirement before exposing a comparison.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::time::{Duration, Instant};

pub(crate) const OUTPUT_BYTES: usize = 8192;
pub(crate) const MAX_DURATION: Duration = Duration::from_secs(14);
pub(crate) const SUBJECT: &str = "com.android.calendar";
pub(crate) const PROVIDER: &str = "com.android.providers.calendar";
pub(crate) const OBSERVER_UID: u32 = 10017;
pub(crate) const DATABASE: &str =
    "/data/user/0/com.android.providers.calendar/databases/calendar.db";
const DATABASE_CONTEXT: &str = "u:object_r:privapp_data_file:s0:c512,c768";
pub(crate) const CLASS: &str = "com.android.droidloom.calendar.CalendarCounts";
const SCHEMA: &str = "droidloom.native-calendar-counts.android.v1";
const QUERY: &str = "eight-table-counts-one-sqlite-statement.v1";
pub(crate) const TABLES: [&str; 8] = [
    "Calendars", "Events", "Reminders", "Attendees", "Instances",
    "CalendarAlerts", "EventsRawTimes", "ExtendedProperties",
];

#[derive(Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Time {
    seconds: u64,
    nanos: u32,
}
#[derive(Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct FileState {
    device: u64,
    inode: u64,
    uid: u32,
    gid: u32,
    mode: u32,
    links: u64,
    size: u64,
    selinux: String,
    mtime: Time,
    ctime: Time,
}
impl FileState {
    fn validate(&self) -> Result<(), String> {
        if self.device == 0 || self.inode == 0 || self.uid != OBSERVER_UID
            || self.mode & 0o170000 != 0o100000 || self.mode & 0o400 == 0
            || self.mode & 0o002 != 0 || self.links != 1
            || self.selinux != DATABASE_CONTEXT
            || self.mtime.nanos >= 1_000_000_000 || self.ctime.nanos >= 1_000_000_000
        {
            return Err("Calendar database file identity differs".into());
        }
        Ok(())
    }
    fn same_inode(&self, other: &Self) -> bool {
        self.device == other.device && self.inode == other.inode
            && self.uid == other.uid && self.gid == other.gid
            && self.mode == other.mode && self.links == other.links
            && self.selinux == other.selinux
    }
    fn legacy_identity(&self) -> Value {
        serde_json::json!({
            "st_dev": self.device, "st_ino": self.inode,
            "st_uid": self.uid, "st_gid": self.gid,
            "st_mode": self.mode, "st_nlink": self.links,
        })
    }
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TableCount {
    name: String,
    count: u64,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct AndroidCounts {
    schema: String,
    provider: String,
    user: u32,
    observer_uid: u32,
    observer_gid: u32,
    database: String,
    read_only: bool,
    query: String,
    cursor_rows: u32,
    window_rows: u32,
    before: FileState,
    after: FileState,
    tables: Vec<TableCount>,
}

/// Immutable parsed data; deliberately has no Deserialize or public fields.
/// Actual authority belongs only to the normal factory observation wrapper.
#[derive(Debug)]
pub(crate) struct ParsedCalendarCounts {
    before: FileState,
    after: FileState,
    counts: BTreeMap<String, u64>,
}
impl ParsedCalendarCounts {
    pub(crate) fn comparison(&self) -> Value {
        serde_json::json!({
            "counts": self.counts,
            "db_identity": self.before.legacy_identity(),
            "database_before": self.before,
            "database_after": self.after,
            "identity_namespace": "selected_android_user_zero",
            "database_body_read_by": "fixed_guest_readonly_sqlite_observer",
            "application_rows_disclosed": false,
            "comparison_only": true,
        })
    }
    pub(crate) fn require_same_database(&self, other: &Self) -> Result<(), String> {
        if !self.before.same_inode(&other.before) {
            return Err("Calendar database was replaced between observations".into());
        }
        Ok(())
    }
}
fn before(end: Instant) -> Result<(), String> {
    if Instant::now() >= end {
        Err("Calendar original observation deadline elapsed".into())
    } else {
        Ok(())
    }
}
fn object_shapes(raw: &Value) -> bool {
    raw.is_object()
        && ["before", "after"].iter().all(|key| {
            raw.get(key).is_some_and(|file| file.is_object()
                && ["mtime", "ctime"].iter().all(|time| file.get(time).is_some_and(Value::is_object)))
        })
        && raw.get("tables").and_then(Value::as_array)
            .is_some_and(|rows| rows.iter().all(Value::is_object))
}
pub(crate) fn parse(raw: &[u8], end: Instant) -> Result<ParsedCalendarCounts, String> {
    before(end)?;
    if raw.is_empty() || raw.len() > OUTPUT_BYTES || raw.first() != Some(&b'{')
        || raw.last() != Some(&b'\n')
        || raw[..raw.len() - 1].iter().any(u8::is_ascii_control)
    {
        return Err("Calendar counts output is incomplete or exceeds its fixed bound".into());
    }
    let shape: Value = serde_json::from_slice(raw)
        .map_err(|_| "Calendar count output schema differs".to_string())?;
    if !object_shapes(&shape) {
        return Err("Calendar count records must be closed objects".into());
    }
    // Deserialize the original bytes again, not the Value: a duplicate named
    // field must be rejected instead of being silently collapsed by a map.
    let wire: AndroidCounts = serde_json::from_slice(raw)
        .map_err(|_| "Calendar count output fields differ".to_string())?;
    if wire.schema != SCHEMA || wire.provider != PROVIDER || wire.user != 0
        || wire.observer_uid != OBSERVER_UID || wire.observer_gid != OBSERVER_UID
        || wire.database != DATABASE || !wire.read_only || wire.query != QUERY
        || wire.cursor_rows != TABLES.len() as u32 || wire.window_rows != TABLES.len() as u32
        || wire.tables.len() != TABLES.len()
    {
        return Err("Calendar fixed observer, statement or complete window differs".into());
    }
    wire.before.validate()?;
    wire.after.validate()?;
    if !wire.before.same_inode(&wire.after) {
        return Err("Calendar database inode changed during the statement".into());
    }
    let mut counts = BTreeMap::new();
    for (row, expected) in wire.tables.into_iter().zip(TABLES) {
        if row.name != expected || row.count > i64::MAX as u64
            || counts.insert(row.name, row.count).is_some()
        {
            return Err("Calendar eight-table roster or count differs".into());
        }
    }
    before(end)?;
    Ok(ParsedCalendarCounts { before: wire.before, after: wire.after, counts })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::Duration;
    fn end() -> Instant { Instant::now() + Duration::from_secs(5) }
    fn fixture() -> Value {
        let file = json!({
            "device": 66306, "inode": 98765, "uid": OBSERVER_UID,
            "gid": OBSERVER_UID, "mode": 0o100600, "links": 1, "size": 40960,
            "selinux": DATABASE_CONTEXT,
            "mtime": {"seconds": 1730000000, "nanos": 123456789},
            "ctime": {"seconds": 1730000000, "nanos": 123456789},
        });
        json!({
            "schema": SCHEMA, "provider": PROVIDER, "user": 0,
            "observer_uid": OBSERVER_UID, "observer_gid": OBSERVER_UID,
            "database": DATABASE, "read_only": true, "query": QUERY,
            "cursor_rows": 8, "window_rows": 8, "before": file, "after": file,
            "tables": TABLES.into_iter().enumerate()
                .map(|(i, name)| json!({"name": name, "count": i as u64}))
                .collect::<Vec<_>>(),
        })
    }
    fn bytes(value: &Value) -> Vec<u8> { (value.to_string() + "\n").into_bytes() }
    fn read(value: &Value) -> Result<ParsedCalendarCounts, String> {
        parse(&bytes(value), end())
    }
    #[test]
    fn calendar_counts_preserve_all_eight_tables_and_report_checkpoint_metadata_honestly() {
        let value = fixture();
        let first = read(&value).unwrap();
        assert_eq!(first.counts.len(), 8);
        assert_eq!(first.counts["EventsRawTimes"], 6);
        assert_eq!(first.counts["Calendars"], 0);
        let mut checkpoint = value.clone();
        checkpoint["after"]["size"] = json!(81920);
        checkpoint["after"]["mtime"]["nanos"] = json!(987654321);
        checkpoint["after"]["ctime"]["seconds"] = json!(1730000001);
        let second = read(&checkpoint).unwrap();
        first.require_same_database(&second).unwrap();
        assert_eq!(first.counts, second.counts);
        assert_ne!(second.comparison()["database_before"], second.comparison()["database_after"]);
        let mut different_counts = value.clone();
        different_counts["tables"][0]["count"] = json!(9_007_199_254_740_993_u64);
        let third = read(&different_counts).unwrap();
        first.require_same_database(&third).unwrap();
        assert_ne!(first.counts, third.counts);
        assert_eq!(third.counts["Calendars"], 9_007_199_254_740_993);
        assert_eq!(third.comparison()["comparison_only"], json!(true));
    }
    #[test]
    fn calendar_counts_reject_foreign_inode_observer_writable_and_incomplete_samples() {
        let base = fixture();
        for (field, value) in [
            ("schema", json!("imported-success")), ("provider", json!("com.example.other")),
            ("user", json!(1)), ("observer_uid", json!(0)), ("observer_gid", json!(0)),
            ("database", json!("/data/other.db")), ("read_only", json!(false)),
            ("query", json!("SELECT 1")), ("cursor_rows", json!(7)), ("window_rows", json!(7)),
            ("passed", json!(true)),
        ] {
            let mut bad = base.clone(); bad[field] = value;
            assert!(read(&bad).is_err(), "{field}");
        }
        for side in ["before", "after"] {
            for (field, value) in [
                ("device", json!(0)), ("inode", json!(0)), ("uid", json!(10018)),
                ("mode", json!(0o120777)), ("mode", json!(0o100666)),
                ("mode", json!(0o100200)), ("links", json!(2)), ("imported", json!(true)),
            ] {
                let mut bad = base.clone(); bad[side][field] = value;
                assert!(read(&bad).is_err(), "{side}.{field}");
            }
            let mut bad = base.clone(); bad[side]["mtime"]["nanos"] = json!(1_000_000_000);
            assert!(read(&bad).is_err());
            let mut bad = base.clone(); bad[side]["ctime"] = json!([1730000000, 0]);
            assert!(read(&bad).is_err());
        }
        for field in ["device", "inode", "gid", "mode"] {
            let mut bad = base.clone();
            let n = bad["after"][field].as_u64().unwrap();
            bad["after"][field] = json!(n + 1);
            assert!(read(&bad).is_err(), "changed {field}");
        }
        let first = read(&base).unwrap();
        let mut replaced = base.clone();
        replaced["before"]["inode"] = json!(99999);
        replaced["after"]["inode"] = json!(99999);
        assert!(first.require_same_database(&read(&replaced).unwrap()).is_err());
    }
    #[test]
    fn calendar_counts_require_actual_exact_database_context_on_both_bookends() {
        let base = fixture();
        for side in ["before", "after"] {
            for context in [
                "u:object_r:privapp_data_file:s0",
                "u:object_r:privapp_data_file:s0:c512,c769",
                "u:object_r:app_data_file:s0:c512,c768",
                "u:object_r:privapp_data_file:s0:c512,c768\0",
            ] {
                let mut bad = base.clone();
                bad[side]["selinux"] = json!(context);
                assert!(read(&bad).is_err(), "{side}: {context:?}");
            }
            let mut missing = base.clone();
            missing[side].as_object_mut().unwrap().remove("selinux");
            assert!(read(&missing).is_err(), "missing {side} context");
        }
        let ordinary = String::from_utf8(bytes(&base)).unwrap();
        let field = format!("\"selinux\":\"{DATABASE_CONTEXT}\"");
        let duplicate = ordinary.replacen(&field, &format!("{field},{field}"), 1);
        assert_ne!(duplicate, ordinary);
        assert!(parse(duplicate.as_bytes(), end()).is_err());
        assert_eq!(read(&base).unwrap().comparison()["database_before"]["selinux"],
            json!(DATABASE_CONTEXT));
    }
    #[test]
    fn calendar_counts_reject_missing_duplicate_extra_rows_fields_and_unbounded_output() {
        let base = fixture();
        for value in [json!(-1), json!(1.5), json!(i64::MAX as u64 + 1), json!("1")] {
            let mut bad = base.clone(); bad["tables"][0]["count"] = value;
            assert!(read(&bad).is_err());
        }
        for replacement in [
            json!([]), json!([{"name":"Calendars","count":0}]),
            json!(vec![json!({"name":"Calendars","count":0}); 8]),
        ] {
            let mut bad = base.clone(); bad["tables"] = replacement;
            assert!(read(&bad).is_err());
        }
        let mut extra = base.clone();
        extra["tables"].as_array_mut().unwrap().push(json!({"name":"Secret","count":1}));
        assert!(read(&extra).is_err());
        for value in [json!(["Calendars", 0]), json!({"name":"Calendars","count":0,"body":"private"})] {
            let mut bad = base.clone(); bad["tables"][0] = value;
            let error = read(&bad).unwrap_err();
            assert!(!error.contains("private"));
        }
        let ordinary = String::from_utf8(bytes(&base)).unwrap();
        let duplicate = ordinary.replacen("\"read_only\":true", "\"read_only\":true,\"read_only\":true", 1);
        assert_ne!(ordinary, duplicate);
        assert!(parse(duplicate.as_bytes(), end()).is_err());
        assert!(parse(ordinary.trim_end().as_bytes(), end()).is_err());
        assert!(parse(&(ordinary.clone() + "\n").into_bytes(), end()).is_err());
        assert!(parse(&(ordinary.clone() + "{}\n").into_bytes(), end()).is_err());
        assert!(parse(&vec![b'x'; OUTPUT_BYTES + 1], end()).is_err());
        assert!(parse(ordinary.as_bytes(), Instant::now()).is_err());
    }
}
