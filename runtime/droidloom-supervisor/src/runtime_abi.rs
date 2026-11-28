//! Comparison-only parsing of the selected CP3A ActivityManager process dump.
//!
//! The grammar is read from the actual selected services.jar (CP3A.260905.010,
//! SHA256 bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86):
//! ProcessList.dumpProcessesLSP, ProcessRecord.dump/toString/toShortString, and
//! PackageList.dump. It is not inferred from a different AOSP source revision.
//! Parsed numbers never select/open a process. The engine owner must join them
//! to its independently held PIDFD, guest PID, actual UID/command, Main epoch,
//! complete PM observation and positive executable/mapping evidence.
use super::{Result, reject, require};
use std::collections::BTreeSet;
use std::time::Instant;

pub(super) const OUTPUT_BYTES: usize = 1024 * 1024;
const MAX_LINES: usize = 8192;
const MAX_LINE_BYTES: usize = 4096;
const MAX_RECORDS: usize = 64;
const MAX_PACKAGES: usize = 64;
const HEADER: &str = "ACTIVITY MANAGER RUNNING PROCESSES (dumpsys activity processes)";

// Only a query selector. These names confer no process, package or ABI authority.
// Exact source-admitted SELECTED41.json:
// 592108 bytes / 4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0.
pub(crate) const PACKAGES: [&str; 41] = [
    "com.Hyatt.hyt",
    "com.MobileTicket",
    "com.amazon.mShop.android.shopping",
    "com.android.calendar",
    "com.android.camera2",
    "com.android.contacts",
    "com.android.deskclock",
    "com.android.dialer",
    "com.android.documentsui",
    "com.android.gallery3d",
    "com.android.messaging",
    "com.android.quicksearchbox",
    "com.android.settings",
    "com.bestbuy.android",
    "com.ehi.national.mobile",
    "com.google.android.gms",
    "com.hertz.android.digital",
    "com.hilton.android.hhonors",
    "com.ihg.apps.android",
    "com.jingdong.app.mall",
    "com.lianjia.beike",
    "com.marriott.mrt",
    "com.rytong.airchina",
    "com.rytong.ceair",
    "com.sankuai.meituan.takeoutnew",
    "com.sdu.didi.psnger",
    "com.ss.android.article.news",
    "com.ss.android.lark",
    "com.ss.android.ugc.aweme",
    "com.szzc",
    "com.taobao.taobao",
    "com.tencent.mm",
    "com.united.mobile.android",
    "com.xunmeng.pinduoduo",
    "com.zhubajie.client",
    "com.zillow.android.streeteasy",
    "ctrip.android.view",
    "jp.co.ana.android.tabidachi",
    "org.fcitx.fcitx5.android",
    "org.mozilla.firefox",
    "tv.danmaku.bili",
];

pub(super) fn validate_package(package: &str) -> Result<()> {
    require(
        PACKAGES.binary_search(&package).is_ok(),
        "runtime ABI package is outside the fixed selection",
    )
}

/// A parsed comparison record, not a runtime observation capability.
/// There is deliberately no public constructor, Deserialize, or Clone.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct RuntimeAbiRecord {
    record_identity: String,
    persistent: bool,
    guest_pid: u32,
    uid: u32,
    user: u32,
    process_name: String,
    packages: BTreeSet<String>,
    required_abi: Option<String>,
    instruction_set: Option<String>,
    thread: Option<String>,
    start_seq: u64,
    isolated_uid: Option<u32>,
    gids: Vec<u32>,
    removed: bool,
    pending_start: bool,
    terminating: bool,
    isolated_entry: bool,
}

impl RuntimeAbiRecord {
    pub(crate) fn guest_pid(&self) -> u32 {
        self.guest_pid
    }
    pub(crate) fn uid(&self) -> u32 {
        self.uid
    }
    pub(crate) fn user(&self) -> u32 {
        self.user
    }
    pub(crate) fn process_name(&self) -> &str {
        &self.process_name
    }
    pub(crate) fn required_abi(&self) -> Option<&str> {
        self.required_abi.as_deref()
    }
    pub(crate) fn instruction_set(&self) -> Option<&str> {
        self.instruction_set.as_deref()
    }
    pub(crate) fn start_seq(&self) -> u64 {
        self.start_seq
    }

    fn require_running_primary(&self) -> Result<()> {
        require(
            self.user == 0
                && self.uid > 0
                && self.guest_pid > 1
                && self.start_seq > 0
                && self.thread.is_some()
                && self.isolated_uid.is_none()
                && !self.isolated_entry
                && !self.removed
                && !self.pending_start
                && !self.terminating,
            "runtime ABI record is not an attached ordinary running process",
        )
    }
}

/// All bounded, complete records in the package-filtered "All known processes"
/// section. Trailing global/isolated summaries cannot supply a missing field.
pub(crate) struct RuntimeAbiRecords {
    package: String,
    records: Vec<RuntimeAbiRecord>,
}

impl RuntimeAbiRecords {
    pub(crate) fn records(&self) -> &[RuntimeAbiRecord] {
        &self.records
    }

    /// Mode comparison only. The caller must still discover/hold its process
    /// independently; this method neither uses nor returns an execution handle.
    pub(crate) fn main_process(&self, uid: u32, command: &str) -> Result<&RuntimeAbiRecord> {
        require(
            command == self.package,
            "runtime ABI command differs from the fixed primary package",
        )?;
        let mut candidates = self
            .records
            .iter()
            .filter(|r| r.user == 0 && r.uid == uid && r.process_name == command);
        let record = candidates
            .next()
            .ok_or_else(|| reject("runtime ABI has no matching primary process"))?;
        require(
            candidates.next().is_none(),
            "runtime ABI primary process is ambiguous",
        )?;
        record.require_running_primary()?;
        Ok(record)
    }

    /// Compare a guest PID obtained from an already held, namespace-checked
    /// process. It is never accepted as a /proc selector or command argument.
    pub(crate) fn match_process(
        &self,
        guest_pid: u32,
        uid: u32,
        command: &str,
    ) -> Result<&RuntimeAbiRecord> {
        let record = self.main_process(uid, command)?;
        require(
            record.guest_pid == guest_pid,
            "runtime ABI differs from the held guest PID",
        )?;
        Ok(record)
    }
}

#[derive(Debug)]
struct Header {
    identity: String,
    persistent: bool,
    pid: u32,
    uid: u32,
    name: String,
    uid_text: String,
}
#[derive(Debug)]
struct UserRow {
    user: u32,
    info_uid: u32,
    isolated_uid: Option<u32>,
    gids: Vec<u32>,
}
#[derive(Default)]
struct Body {
    user: Option<UserRow>,
    abi: Option<(Option<String>, Option<String>)>,
    packages: Option<BTreeSet<String>>,
    thread: Option<Option<String>>,
    pid: Option<u32>,
    start_seq: Option<u64>,
    flags: Option<(bool, bool)>,
    pending_start: Option<bool>,
    terminating: Option<bool>,
    isolated_entry: Option<bool>,
}

fn once<T>(slot: &mut Option<T>, value: T) -> Result<()> {
    require(slot.is_none(), "duplicate runtime ABI process field")?;
    *slot = Some(value);
    Ok(())
}
fn number(text: &str) -> Result<u64> {
    let value: u64 = text
        .parse()
        .map_err(|_| reject("invalid runtime ABI integer"))?;
    require(
        value.to_string() == text,
        "noncanonical runtime ABI integer",
    )?;
    Ok(value)
}
fn integer(text: &str) -> Result<u32> {
    let value = number(text)?;
    require(
        value <= i32::MAX as u64,
        "runtime ABI integer exceeds selected framework range",
    )?;
    Ok(value as u32)
}
fn boolean(text: &str) -> Result<bool> {
    match text {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(reject("invalid runtime ABI boolean")),
    }
}
fn name(text: &str) -> bool {
    !text.is_empty()
        && text.len() <= 255
        && text
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._:".contains(&b))
}
fn package_name(text: &str) -> bool {
    !text.is_empty()
        && text.len() <= 255
        && text
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._".contains(&b))
}
fn abi(text: &str, instruction: bool) -> Result<Option<String>> {
    let allowed: &[&str] = if instruction {
        &["x86_64", "arm64", "x86", "arm"]
    } else {
        &["x86_64", "arm64-v8a", "x86", "armeabi-v7a", "armeabi"]
    };
    if text == "null" {
        return Ok(None);
    }
    require(allowed.contains(&text), "unknown runtime ABI value")?;
    Ok(Some(text.into()))
}
fn header(text: &str) -> Result<Header> {
    let (persistent, rest) = if let Some(rest) = text.strip_prefix("  *APP* UID ") {
        (false, rest)
    } else if let Some(rest) = text.strip_prefix("  *PERS* UID ") {
        (true, rest)
    } else {
        return Err(reject("invalid runtime ABI process header"));
    };
    let (uid, record) = rest
        .split_once(" ProcessRecord{")
        .ok_or_else(|| reject("runtime ABI ProcessRecord header is absent"))?;
    let record = record
        .strip_suffix('}')
        .ok_or_else(|| reject("unterminated runtime ABI ProcessRecord"))?;
    let (identity, rest) = record
        .split_once(' ')
        .ok_or_else(|| reject("runtime ABI ProcessRecord identity is absent"))?;
    require(
        !identity.is_empty()
            && identity.len() <= 8
            && (identity.len() == 1 || !identity.starts_with('0'))
            && identity
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "invalid runtime ABI ProcessRecord identity",
    )?;
    let (pid, rest) = rest
        .split_once(':')
        .ok_or_else(|| reject("runtime ABI header PID is absent"))?;
    let (process_name, uid_text) = rest
        .rsplit_once('/')
        .ok_or_else(|| reject("runtime ABI header UID text is absent"))?;
    require(
        name(process_name)
            && !uid_text.is_empty()
            && uid_text.len() <= 32
            && uid_text.bytes().all(|b| b.is_ascii_alphanumeric()),
        "invalid runtime ABI process name or UID text",
    )?;
    Ok(Header {
        identity: identity.into(),
        persistent,
        pid: integer(pid)?,
        uid: integer(uid)?,
        name: process_name.into(),
        uid_text: uid_text.into(),
    })
}
fn user_row(text: &str) -> Result<UserRow> {
    let text = text
        .strip_prefix("user #")
        .ok_or_else(|| reject("runtime ABI user prefix"))?;
    let (user, rest) = text
        .split_once(" uid=")
        .ok_or_else(|| reject("runtime ABI user UID"))?;
    let (uids, gids) = rest
        .split_once(" gids={")
        .ok_or_else(|| reject("runtime ABI user groups"))?;
    let gids = gids
        .strip_suffix('}')
        .ok_or_else(|| reject("runtime ABI user groups terminator"))?;
    let (uid, isolated) = match uids.split_once(" ISOLATED uid=") {
        Some((uid, isolated)) => (uid, Some(integer(isolated)?)),
        None => (uids, None),
    };
    let user = integer(user)?;
    let info_uid = integer(uid)?;
    require(
        user <= 21_474
            && info_uid / 100_000 == user
            && isolated.is_none_or(|uid| uid / 100_000 == user),
        "runtime ABI user and UID disagree",
    )?;
    let mut values = Vec::new();
    if !gids.is_empty() {
        for gid in gids.split(", ") {
            require(values.len() < 128, "runtime ABI group bound")?;
            let gid = integer(gid)?;
            require(!values.contains(&gid), "duplicate runtime ABI group")?;
            values.push(gid);
        }
    }
    Ok(UserRow {
        user,
        info_uid,
        isolated_uid: isolated,
        gids: values,
    })
}
fn parse_body(body: &mut Body, line: &str) -> Result<()> {
    // Exact top-level ProcessRecord indentation. Deeper service/provider dump
    // text is not an authority source and cannot fill these mandatory fields.
    let Some(line) = line.strip_prefix("    ") else {
        return Err(reject("runtime ABI process body indentation"));
    };
    if line.starts_with(' ') || line.is_empty() {
        return Ok(());
    }
    let line = line.trim_end_matches(' ');
    if line.starts_with("user #") {
        return once(&mut body.user, user_row(line)?);
    }
    if let Some(value) = line.strip_prefix("mRequiredAbi=") {
        let (required, instruction) = value
            .split_once(" instructionSet=")
            .ok_or_else(|| reject("runtime ABI instruction set is absent"))?;
        return once(
            &mut body.abi,
            (abi(required, false)?, abi(instruction, true)?),
        );
    }
    if let Some(value) = line.strip_prefix("packageList={") {
        let value = value
            .strip_suffix('}')
            .ok_or_else(|| reject("runtime ABI package list terminator"))?;
        let mut packages = BTreeSet::new();
        for p in value.split(", ") {
            require(
                packages.len() < MAX_PACKAGES && package_name(p),
                "runtime ABI package list bound or syntax",
            )?;
            require(
                packages.insert(p.to_owned()),
                "duplicate runtime ABI package member",
            )?;
        }
        return once(&mut body.packages, packages);
    }
    if let Some(value) = line.strip_prefix("thread=") {
        require(
            !value.is_empty() && value.len() <= 512,
            "runtime ABI thread value",
        )?;
        return once(
            &mut body.thread,
            if value == "null" {
                None
            } else {
                Some(value.into())
            },
        );
    }
    if let Some(value) = line.strip_prefix("pid=") {
        return once(&mut body.pid, integer(value)?);
    }
    if let Some(value) = line.strip_prefix("startSeq=") {
        let (seq, lru) = value
            .split_once(" lruSeq=")
            .ok_or_else(|| reject("runtime ABI start sequence syntax"))?;
        // lruSeq is a volatile scheduling counter, not process birth identity.
        // Validate the actual selected field but do not compare it as a birth.
        let lru_value: i32 = lru
            .parse()
            .map_err(|_| reject("runtime ABI lru sequence"))?;
        require(
            lru_value.to_string() == lru,
            "runtime ABI noncanonical lru sequence",
        )?;
        let seq = number(seq)?;
        require(
            seq <= i64::MAX as u64,
            "runtime ABI start sequence exceeds Java long",
        )?;
        return once(&mut body.start_seq, seq);
    }
    if let Some(value) = line.strip_prefix("persistent=") {
        let (persistent, removed) = value
            .split_once(" removed=")
            .ok_or_else(|| reject("runtime ABI persistent flags"))?;
        return once(&mut body.flags, (boolean(persistent)?, boolean(removed)?));
    }
    if let Some(value) = line.strip_prefix("pendingStart=") {
        require(
            value == "true",
            "runtime ABI impossible pending-start field",
        )?;
        return once(&mut body.pending_start, true);
    }
    if let Some(value) = line.strip_prefix("killed=") {
        let (killed, rest) = value
            .split_once(" killedByAm=")
            .ok_or_else(|| reject("runtime ABI killed flags"))?;
        let (by_am, waiting) = rest
            .split_once(" waitingToKill=")
            .ok_or_else(|| reject("runtime ABI termination flags"))?;
        let killed = boolean(killed)?;
        let by_am = boolean(by_am)?;
        require(
            !waiting.is_empty() && (killed || by_am || waiting != "null"),
            "runtime ABI impossible termination field",
        )?;
        return once(&mut body.terminating, true);
    }
    if line.starts_with("isolatedEntryPoint=") {
        return once(&mut body.isolated_entry, true);
    }
    // A partial/shifted known field must not masquerade as an unrelated line.
    for prefix in [
        "user #",
        "mRequiredAbi",
        "instructionSet=",
        "packageList",
        "thread=",
        "pid=",
        "startSeq",
        "persistent=",
        "removed=",
        "pendingStart=",
        "killed=",
        "killedByAm=",
    ] {
        require(
            !line.starts_with(prefix),
            "malformed runtime ABI identity field",
        )?;
    }
    Ok(())
}
fn complete(h: Header, body: Body, package: &str) -> Result<RuntimeAbiRecord> {
    let user = body
        .user
        .ok_or_else(|| reject("runtime ABI user is missing"))?;
    let (required_abi, instruction_set) = body
        .abi
        .ok_or_else(|| reject("runtime ABI pair is missing"))?;
    let packages = body
        .packages
        .ok_or_else(|| reject("runtime ABI package list is missing"))?;
    let thread = body
        .thread
        .ok_or_else(|| reject("runtime ABI thread is missing"))?;
    let pid = body
        .pid
        .ok_or_else(|| reject("runtime ABI body PID is missing"))?;
    let seq = body
        .start_seq
        .ok_or_else(|| reject("runtime ABI start sequence is missing"))?;
    let (persistent, removed) = body.flags.unwrap_or((false, false));
    require(
        h.persistent == persistent,
        "runtime ABI persistent header disagrees",
    )?;
    require(
        h.pid == pid
            && h.uid == user.isolated_uid.unwrap_or(user.info_uid)
            && packages.contains(package),
        "runtime ABI header, body, or package filter disagree",
    )?;
    if user.isolated_uid.is_none() {
        let expected = if user.info_uid < 10_000 {
            h.uid.to_string()
        } else if user.info_uid % 100_000 >= 10_000 {
            format!("u{}a{}", user.user, user.info_uid % 100_000 - 10_000)
        } else {
            format!("u{}s{}", user.user, user.info_uid % 100_000)
        };
        require(
            h.uid_text == expected,
            "runtime ABI formatted UID disagrees",
        )?;
    }
    Ok(RuntimeAbiRecord {
        record_identity: h.identity,
        persistent,
        guest_pid: pid,
        uid: h.uid,
        user: user.user,
        process_name: h.name,
        packages,
        required_abi,
        instruction_set,
        thread,
        start_seq: seq,
        isolated_uid: user.isolated_uid,
        gids: user.gids,
        removed,
        pending_start: body.pending_start.unwrap_or(false),
        terminating: body.terminating.unwrap_or(false),
        isolated_entry: body.isolated_entry.unwrap_or(false),
    })
}
fn append_record(
    records: &mut Vec<RuntimeAbiRecord>,
    h: Header,
    body: Body,
    package: &str,
) -> Result<()> {
    require(
        records.len() < MAX_RECORDS,
        "runtime ABI process count bound",
    )?;
    let record = complete(h, body, package)?;
    require(
        !records.iter().any(|r| {
            (r.uid == record.uid && r.process_name == record.process_name)
                || (r.guest_pid != 0 && r.guest_pid == record.guest_pid)
        }),
        "duplicate runtime ABI process identity",
    )?;
    records.push(record);
    Ok(())
}

pub(super) fn parse(package: &str, output: &str, deadline: Instant) -> Result<RuntimeAbiRecords> {
    crate::production_host_admission::check_observation_before(deadline)?;
    validate_package(package)?;
    require(
        !output.is_empty()
            && output.len() <= OUTPUT_BYTES
            && output.ends_with('\n')
            && output.bytes().all(|b| b == b'\n' || !b.is_ascii_control()),
        "runtime ABI output size, encoding, or completeness",
    )?;
    let mut seen_header = false;
    let mut seen_section = false;
    let mut closed_section = false;
    let mut current: Option<(Header, Body)> = None;
    let mut records = Vec::new();
    for (index, line) in output.lines().enumerate() {
        crate::production_host_admission::check_observation_before(deadline)?;
        require(
            index < MAX_LINES && line.len() <= MAX_LINE_BYTES,
            "runtime ABI output line bound",
        )?;
        if line.is_empty() {
            continue;
        }
        if !seen_header {
            require(line == HEADER, "runtime ABI dump header is absent")?;
            seen_header = true;
            continue;
        }
        require(line != HEADER, "duplicate runtime ABI dump header")?;
        if line == "  All known processes:" {
            require(
                !seen_section && !closed_section && current.is_none(),
                "duplicate runtime ABI process section",
            )?;
            seen_section = true;
            continue;
        }
        if line.starts_with("  *APP*") || line.starts_with("  *PERS*") {
            require(
                seen_section && !closed_section,
                "runtime ABI process is outside the selected section",
            )?;
            if let Some((h, body)) = current.take() {
                append_record(&mut records, h, body, package)?;
            }
            current = Some((header(line)?, Body::default()));
            continue;
        }
        if let Some((_, body)) = &mut current {
            if line.starts_with("    ") {
                parse_body(body, line)?;
                continue;
            }
            let (h, body) = current
                .take()
                .ok_or_else(|| reject("runtime ABI internal section state"))?;
            append_record(&mut records, h, body, package)?;
            closed_section = true;
        }
        if seen_section && !closed_section {
            return Err(reject("runtime ABI missing process after section header"));
        }
        // Other selected dump sections carry no RuntimeAbiRecord. In particular
        // an Isolated # / OOM summary cannot replace an All-known primary block.
    }
    if let Some((h, body)) = current.take() {
        append_record(&mut records, h, body, package)?;
    }
    require(
        seen_header && seen_section && !records.is_empty(),
        "runtime ABI process records are absent",
    )?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(RuntimeAbiRecords {
        package: package.into(),
        records,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    const PACKAGE: &str = "com.android.deskclock";

    fn end() -> Instant {
        Instant::now() + Duration::from_secs(5)
    }
    fn row(
        package: &str,
        name: &str,
        pid: u32,
        uid: u32,
        required: &str,
        instruction: &str,
        seq: u64,
    ) -> String {
        let uid_text = if uid < 10_000 {
            uid.to_string()
        } else {
            format!("u0a{}", uid - 10_000)
        };
        format!(
            "  *APP* UID {uid} ProcessRecord{{1abc {pid}:{name}/{uid_text}}}\n\
             \x20   user #0 uid={uid} gids={{}}\n\
             \x20   mRequiredAbi={required} instructionSet={instruction} \n\
             \x20   dir=/product/app/DeskClock/DeskClock.apk publicDir=/product/app/DeskClock/DeskClock.apk \n\
             \x20   packageList={{{package}}}\n\
             \x20   thread=com.android.server.am.ApplicationThreadDeferred@123 \n\
             \x20   pid={pid} \n\
             \x20   startSeq={seq} lruSeq=2 \n"
        )
    }
    fn dump(row: &str) -> String {
        format!("{HEADER}\n  All known processes:\n{row}")
    }
    fn native() -> String {
        dump(&row(PACKAGE, PACKAGE, 432, 10123, "x86_64", "null", 7))
    }

    #[test]
    fn runtime_abi_preserves_actual_nullable_instruction_set_without_granting_route() {
        for instruction in ["null", "x86_64"] {
            let text = dump(&row(PACKAGE, PACKAGE, 432, 10123, "x86_64", instruction, 7));
            let parsed = parse(PACKAGE, &text, end()).unwrap();
            let actual = parsed.match_process(432, 10123, PACKAGE).unwrap();
            assert_eq!(actual.required_abi(), Some("x86_64"));
            assert_eq!(
                actual.instruction_set(),
                if instruction == "null" {
                    None
                } else {
                    Some(instruction)
                }
            );
            assert_eq!(actual.user(), 0);
            assert_eq!(actual.start_seq(), 7);
        }
        let unset = parse(
            PACKAGE,
            &native().replace("mRequiredAbi=x86_64", "mRequiredAbi=null"),
            end(),
        )
        .unwrap();
        assert_eq!(
            unset
                .match_process(432, 10123, PACKAGE)
                .unwrap()
                .required_abi(),
            None
        );
    }
    #[test]
    fn runtime_abi_keeps_bridge_fields_and_rejects_unknown_abi() {
        let text = dump(&row(PACKAGE, PACKAGE, 432, 10123, "arm64-v8a", "arm64", 7));
        let parsed = parse(PACKAGE, &text, end()).unwrap();
        let record = parsed.match_process(432, 10123, PACKAGE).unwrap();
        assert_eq!(record.required_abi(), Some("arm64-v8a"));
        assert_eq!(record.instruction_set(), Some("arm64"));
        for value in ["riscv64", "", "x86_64 other=arm64", "null x86_64"] {
            assert!(
                parse(
                    PACKAGE,
                    &native().replace("mRequiredAbi=x86_64", &format!("mRequiredAbi={value}")),
                    end()
                )
                .is_err()
            );
        }
    }
    #[test]
    fn runtime_abi_joins_only_actual_uid_guest_pid_and_primary_command() {
        let mut rows = row(PACKAGE, PACKAGE, 432, 10123, "x86_64", "null", 7);
        rows.push_str(&row(
            PACKAGE,
            &format!("{PACKAGE}:remote"),
            433,
            10123,
            "arm64-v8a",
            "arm64",
            8,
        ));
        let parsed = parse(PACKAGE, &dump(&rows), end()).unwrap();
        assert_eq!(parsed.records().len(), 2);
        assert!(parsed.match_process(432, 10123, PACKAGE).is_ok());
        assert!(parsed.match_process(433, 10123, PACKAGE).is_err());
        assert!(parsed.match_process(432, 10124, PACKAGE).is_err());
        assert!(parsed.main_process(10123, "com.android.settings").is_err());
        assert!(
            parsed
                .main_process(10123, &format!("{PACKAGE}:remote"))
                .is_err()
        );
    }
    #[test]
    fn runtime_abi_rejects_duplicate_or_incomplete_identity_fields() {
        for line in [
            "    user #0 uid=10123 gids={}\n",
            "    mRequiredAbi=x86_64 instructionSet=null \n",
            "    packageList={com.android.deskclock}\n",
            "    thread=com.android.server.am.ApplicationThreadDeferred@123 \n",
            "    pid=432 \n",
            "    startSeq=7 lruSeq=2 \n",
        ] {
            let text = native();
            assert!(text.contains(line));
            assert!(parse(PACKAGE, &text.replace(line, ""), end()).is_err());
            assert!(
                parse(
                    PACKAGE,
                    &text.replace(line, &format!("{line}{line}")),
                    end()
                )
                .is_err()
            );
        }
        let row = row(PACKAGE, PACKAGE, 432, 10123, "x86_64", "null", 7);
        assert!(parse(PACKAGE, &dump(&format!("{row}{row}")), end()).is_err());
    }
    #[test]
    fn runtime_abi_rejects_cross_record_numbers_package_and_stale_states() {
        for (old, new) in [
            ("pid=432 ", "pid=434 "),
            ("user #0 uid=10123", "user #1 uid=10123"),
            ("u0a123}", "u0a124}"),
            (
                "packageList={com.android.deskclock}",
                "packageList={com.android.settings}",
            ),
            ("startSeq=7", "startSeq=07"),
            ("UID 10123", "UID +10123"),
        ] {
            assert!(parse(PACKAGE, &native().replace(old, new), end()).is_err());
        }
        for changed in [
            native().replace(
                "thread=com.android.server.am.ApplicationThreadDeferred@123",
                "thread=null",
            ),
            native().replace("startSeq=7", "startSeq=0"),
            format!("{}    pendingStart=true \n", native()),
            format!("{}    persistent=false removed=true \n", native()),
            format!(
                "{}    killed=false killedByAm=false waitingToKill=stopping \n",
                native()
            ),
            format!("{}    isolatedEntryPoint=com.example.Entry \n", native()),
        ] {
            let parsed = parse(PACKAGE, &changed, end()).unwrap();
            assert!(parsed.match_process(432, 10123, PACKAGE).is_err());
        }
    }
    #[test]
    fn runtime_abi_does_not_use_isolated_or_global_summary_as_primary_evidence() {
        let text = native().replace("    startSeq=7 lruSeq=2 \n", "");
        let text =
            format!("{text}  Isolated process list (sorted by uid):\n    startSeq=7 lruSeq=2 \n");
        assert!(parse(PACKAGE, &text, end()).is_err());
        assert!(
            parse(
                PACKAGE,
                &format!(
                    "{HEADER}\n  Isolated process list (sorted by uid):\n{}",
                    row(PACKAGE, PACKAGE, 432, 10123, "x86_64", "null", 7)
                ),
                end()
            )
            .is_err()
        );
        let parsed = parse(PACKAGE, &format!("{}  Isolated process list (sorted by uid):\n    Isolated #0: ProcessRecord{{def 999:other/u0a1i1}}\n", native()), end()).unwrap();
        assert_eq!(
            parsed
                .match_process(432, 10123, PACKAGE)
                .unwrap()
                .guest_pid(),
            432
        );
    }
    #[test]
    fn runtime_abi_birth_comparison_ignores_only_volatile_lru_and_relative_ages() {
        let before = parse(PACKAGE, &native(), end()).unwrap();
        let after = parse(PACKAGE, &native().replace("lruSeq=2", "lruSeq=91"), end()).unwrap();
        assert_eq!(
            before.match_process(432, 10123, PACKAGE).unwrap(),
            after.match_process(432, 10123, PACKAGE).unwrap()
        );
        for text in [
            native().replace("startSeq=7", "startSeq=8"),
            native().replace("ProcessRecord{1abc", "ProcessRecord{1abd"),
            native().replace("instructionSet=null", "instructionSet=x86_64"),
        ] {
            let changed = parse(PACKAGE, &text, end()).unwrap();
            assert_ne!(
                before.match_process(432, 10123, PACKAGE).unwrap(),
                changed.match_process(432, 10123, PACKAGE).unwrap()
            );
        }
    }
    #[test]
    fn runtime_abi_bounded_output_and_original_absolute_deadline_are_required() {
        for text in [
            native().trim_end_matches('\n').to_owned(),
            format!("{}\0\n", native()),
            native().replace('\n', "\r\n"),
            format!("{}\n", "x".repeat(OUTPUT_BYTES)),
            format!("{}{}\n", native(), "x".repeat(MAX_LINE_BYTES + 1)),
            format!("{}{}", native(), "\n".repeat(MAX_LINES)),
        ] {
            assert!(parse(PACKAGE, &text, end()).is_err());
        }
        assert!(parse(PACKAGE, &native(), Instant::now()).is_err());
        let mut rows = String::new();
        for i in 0..=MAX_RECORDS {
            rows.push_str(&row(
                PACKAGE,
                &format!("{PACKAGE}:r{i}"),
                1000 + i as u32,
                10123,
                "x86_64",
                "null",
                7 + i as u64,
            ));
        }
        assert!(parse(PACKAGE, &dump(&rows), end()).is_err());
        assert!(parse("com.example.other", &native(), end()).is_err());
    }
    #[test]
    fn runtime_abi_roster_is_exact_sorted_and_system_uid_format_is_supported() {
        assert_eq!(PACKAGES.len(), 41);
        assert!(PACKAGES.windows(2).all(|pair| pair[0] < pair[1]));
        let package = "com.android.settings";
        let text = dump(&row(package, package, 432, 1000, "x86_64", "null", 7));
        assert!(
            parse(package, &text, end())
                .unwrap()
                .match_process(432, 1000, package)
                .is_ok()
        );
        for invalid in [
            "",
            "com.example.other",
            "com.android.settings --user 0",
            "com.android.settings\n",
            "com.android.settings:remote",
        ] {
            assert!(validate_package(invalid).is_err());
        }
    }
}
