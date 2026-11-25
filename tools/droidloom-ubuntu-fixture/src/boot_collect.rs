//! Read original native journals only after the owned VM has been reaped.
//! Filesystem recovery always acts on a new independent copy of its ended disk.
use crate::{
    Result,
    boot_child::OwnedChild,
    boot_files::{self, FilePin},
    ensure, fs,
    model::Identity,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    io::{BufRead, BufReader, Read},
    os::{
        fd::AsRawFd,
        unix::process::{CommandExt, ExitStatusExt},
    },
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

const UNIT: &str = "droidloom-mac-calibration.service";
const UNIT_BYTES: &[u8] =
    include_bytes!("../../../runtime/droidloom-supervisor/src/droidloom-mac-calibration.service");
const CAPTURE_LIMIT: u64 = 2 * (65536 * 2 + 132 * 1024 * 1024) + 65536;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct CollectPlan {
    schema: String,
    ended: FilePin,
    collection_name: String,
    e2fsck: FilePin,
    debugfs: FilePin,
    journalctl: FilePin,
}

#[derive(Serialize)]
struct ToolResult {
    tool: FilePin,
    args: Vec<String>,
    exit_code: Option<i32>,
    signal: Option<i32>,
    timed_out: bool,
    output_limited: bool,
    child_reaped: bool,
    tool_identity_preserved: bool,
    executed_held_descriptor: bool,
    stdout: FilePin,
    stderr: FilePin,
}

fn preserved(pin: &FilePin, file: &std::fs::File, identity: &Identity) -> Result<()> {
    ensure(
        fs::stat(file)? == *identity && boot_files::open_pin(pin)?.1 == *identity,
        "pinned path or held identity changed before final readback",
    )?;
    ensure(fs::hash(file)? == pin.sha256, "pinned content changed")?;
    ensure(
        fs::stat(file)? == *identity && boot_files::open_pin(pin)?.1 == *identity,
        "pinned path or held identity changed during final readback",
    )
}

fn execute(
    work: &Path,
    name: &str,
    tool: &FilePin,
    args: Vec<String>,
    seconds: u64,
    max_stdout: u64,
) -> Result<ToolResult> {
    ensure(
        !name.is_empty()
            && name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b)),
        "invalid evidence command name",
    )?;
    let held = boot_files::checked_file(tool)?;
    let before = fs::stat(&held)?;
    ensure(
        before.uid == 0 && before.mode & 0o022 == 0,
        "native diagnostic executable is not root protected",
    )?;
    let out_path = work.join(format!("{name}.stdout"));
    let err_path = work.join(format!("{name}.stderr"));
    let out = boot_files::new_file(&out_path, 0o600)?;
    let err = boot_files::new_file(&err_path, 0o600)?;
    ensure(
        boot_files::open_pin(tool)?.1 == before,
        "tool pathname changed before execution",
    )?;
    let mut command = Command::new(format!("/proc/self/fd/{}", held.as_raw_fd()));
    command.arg0(&tool.path);
    command
        .args(&args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C.UTF-8")
        .env("SYSTEMD_PAGER", "cat")
        .env("SYSTEMD_COLORS", "0")
        .env("SYSTEMD_LOG_COLOR", "0")
        .stdin(Stdio::null())
        .stdout(Stdio::from(out.try_clone()?))
        .stderr(Stdio::from(err.try_clone()?));
    let mut child = OwnedChild::spawn(&mut command)?;
    let start = Instant::now();
    let mut timed_out = false;
    let mut output_limited = false;
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        timed_out = start.elapsed() >= Duration::from_secs(seconds);
        output_limited =
            fs::stat(&out)?.size > max_stdout || fs::stat(&err)?.size > 8 * 1024 * 1024;
        if timed_out || output_limited {
            break child.stop_and_reap()?;
        }
        std::thread::sleep(Duration::from_millis(50));
    };
    output_limited |= fs::stat(&out)?.size > max_stdout || fs::stat(&err)?.size > 8 * 1024 * 1024;
    out.sync_all()?;
    err.sync_all()?;
    let tool_identity_preserved = preserved(tool, &held, &before).is_ok();
    let result = ToolResult {
        tool: tool.clone(),
        args,
        exit_code: status.code(),
        signal: status.signal(),
        timed_out,
        output_limited,
        child_reaped: true,
        tool_identity_preserved,
        executed_held_descriptor: true,
        stdout: boot_files::pin_file(&out_path)?,
        stderr: boot_files::pin_file(&err_path)?,
    };
    fs::write_json(
        &fs::absolute_string(&work.join(format!("{name}.json")))?,
        &result,
        rustix::process::geteuid().as_raw(),
    )?;
    Ok(result)
}

fn success(result: &ToolResult, accepted: &[i32]) -> bool {
    result.tool_identity_preserved
        && !result.timed_out
        && !result.output_limited
        && result.signal.is_none()
        && result
            .exit_code
            .is_some_and(|code| accepted.contains(&code))
}

fn field_path(value: &Value, name: &str) -> Result<PathBuf> {
    let path = PathBuf::from(
        value[name]
            .as_str()
            .ok_or("required absolute path missing")?,
    );
    fs::absolute_string(&path)?;
    Ok(path)
}

fn same_pin(left: &FilePin, right: &FilePin) -> bool {
    left.path == right.path && left.bytes == right.bytes && left.sha256 == right.sha256
}

fn safe_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
}

fn hex_id(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        && value.bytes().any(|b| b != b'0')
}

fn private_tree(path: &Path) -> Result<()> {
    let tree = fs::Tree::open(&fs::absolute_string(path)?, 0)?;
    let id = fs::stat(&tree.root)?;
    ensure(
        id.mode & 0o7777 == 0o700,
        "qualification directory is no longer private",
    )
}

/// Only original PID 1 journal fields count, never arbitrary text in MESSAGE.
fn service_evidence(rows: &[Value], boot: &str, invocation: &str) -> Value {
    let matching: Vec<_> = rows
        .iter()
        .filter(|row| {
            row["_PID"] == "1"
                && row["_UID"] == "0"
                && row["_TRANSPORT"] == "journal"
                && row["UNIT"] == UNIT
                && row["_BOOT_ID"] == boot
                && row["INVOCATION_ID"] == invocation
        })
        .cloned()
        .collect();
    let zero = matching.iter().any(|r| {
        r["MESSAGE_ID"] == "98e322203f7a4ed290d09fe03c09fe15"
            && r["COMMAND"] == "ExecStart"
            && r["EXIT_CODE"] == "exited"
            && (r["EXIT_STATUS"] == "0" || r["EXIT_STATUS"] == 0)
    });
    let done = matching.iter().any(|r| {
        r["MESSAGE_ID"] == "39f53479d3a045ac8e11786248231fbf"
            && r["JOB_TYPE"] == "start"
            && r["JOB_RESULT"] == "done"
    });
    let error = matching.iter().any(|r| {
        r["JOB_RESULT"]
            .as_str()
            .is_some_and(|v| ["failed", "dependency", "timeout", "canceled"].contains(&v))
            || (r["COMMAND"] == "ExecStart"
                && !r["EXIT_STATUS"].is_null()
                && r["EXIT_STATUS"] != "0"
                && r["EXIT_STATUS"] != 0)
            || (r["COMMAND"] == "ExecStart"
                && !r["EXIT_CODE"].is_null()
                && r["EXIT_CODE"] != "exited")
    });
    json!({"boot_id":boot,"invocation_id":invocation,"explicit_exit_zero":zero,
        "ordinary_start_done":done,"error_observed":error,
        "pid1_service_proven":hex_id(boot) && hex_id(invocation) && zero && done && !error,
        "records":matching})
}

#[derive(Clone, Debug, Serialize)]
struct GuestEntry {
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    name: String,
    bytes: Option<u64>,
}

fn parse_directory(text: &str) -> Result<Vec<GuestEntry>> {
    let mut entries = Vec::new();
    let mut names = BTreeSet::new();
    for line in text.lines().filter(|line| !line.is_empty()) {
        let fields: Vec<_> = line.split('/').collect();
        ensure(
            fields.len() == 8 && fields[0].is_empty() && fields[7].is_empty(),
            "ambiguous native debugfs directory record",
        )?;
        let inode = fields[1].parse::<u64>()?;
        let mode = u32::from_str_radix(fields[2], 8)?;
        let uid = fields[3].parse::<u32>()?;
        let gid = fields[4].parse::<u32>()?;
        let name = fields[5];
        ensure(
            inode >= 2
                && !name.is_empty()
                && name.len() <= 255
                && !name.chars().any(char::is_control)
                && names.insert(name.to_owned()),
            "invalid or duplicate guest directory entry",
        )?;
        let bytes = if fields[6].is_empty() {
            None
        } else {
            Some(fields[6].parse::<u64>()?)
        };
        entries.push(GuestEntry {
            inode,
            mode,
            uid,
            gid,
            name: name.to_owned(),
            bytes,
        });
        ensure(
            entries.len() <= 1024,
            "guest directory entry limit exceeded",
        )?;
    }
    Ok(entries)
}

fn directory(
    plan: &CollectPlan,
    work: &Path,
    disk: &Path,
    inode: u64,
    index: &mut usize,
) -> Result<Vec<GuestEntry>> {
    ensure(*index < 1024, "guest directory walk limit exceeded")?;
    let name = format!("inode-directory-{}", *index);
    *index += 1;
    let result = execute(
        work,
        &name,
        &plan.debugfs,
        vec![
            "-R".into(),
            format!("ls -p <{inode}>"),
            disk.to_string_lossy().into(),
        ],
        30,
        512 * 1024,
    )?;
    ensure(
        success(&result, &[0]),
        "native inode directory inspection failed",
    )?;
    let bytes = boot_files::read_pin(&result.stdout, 512 * 1024)?;
    let entries = parse_directory(std::str::from_utf8(&bytes)?)?;
    ensure(
        entries
            .iter()
            .any(|e| e.name == "." && e.inode == inode && e.mode & 0o170000 == 0o040000),
        "guest directory inode differs",
    )?;
    Ok(entries)
}

/// Resolve fixed guest components by inode; no guest alias is followed.
fn resolve_inode(
    plan: &CollectPlan,
    work: &Path,
    disk: &Path,
    path: &str,
    index: &mut usize,
) -> Result<Option<GuestEntry>> {
    let names = crate::paths::parts(path)?;
    ensure(!names.is_empty(), "guest file path required")?;
    let mut inode = 2;
    for (position, name) in names.iter().enumerate() {
        let entries = directory(plan, work, disk, inode, index)?;
        let Some(entry) = entries.into_iter().find(|entry| entry.name == *name) else {
            return Ok(None);
        };
        if position + 1 == names.len() {
            return Ok(Some(entry));
        }
        ensure(
            entry.mode & 0o170000 == 0o040000,
            "guest path contains a non-directory alias",
        )?;
        inode = entry.inode;
    }
    Err("guest inode resolution incomplete".into())
}

fn journal_manifest(
    plan: &CollectPlan,
    work: &Path,
    disk: &Path,
    index: &mut usize,
) -> Result<Vec<GuestEntry>> {
    let root = resolve_inode(plan, work, disk, "/var/log/journal", index)?
        .ok_or("ended guest has no persistent journal directory")?;
    ensure(
        root.mode & 0o170000 == 0o040000 && root.uid == 0,
        "persistent journal root is not an original root-owned directory",
    )?;
    let mut todo = vec![(root.inode, 0usize)];
    let mut seen = BTreeSet::from([root.inode]);
    let mut files = Vec::new();
    let mut total = 0u64;
    while let Some((inode, depth)) = todo.pop() {
        ensure(depth <= 4, "journal directory depth exceeds fixture bound")?;
        for entry in directory(plan, work, disk, inode, index)? {
            if entry.name == "." || entry.name == ".." {
                continue;
            }
            ensure(
                seen.insert(entry.inode) && seen.len() <= 1024,
                "journal tree contains a repeated inode or exceeds its entry bound",
            )?;
            ensure(
                entry.uid == 0,
                "persistent journal tree contains a non-root owner",
            )?;
            match entry.mode & 0o170000 {
                0o040000 => todo.push((entry.inode, depth + 1)),
                0o100000 => {
                    ensure(
                        entry.name.ends_with(".journal") || entry.name.ends_with(".journal~"),
                        "unexpected regular file in native journal tree",
                    )?;
                    let bytes = entry.bytes.ok_or("journal inode size absent")?;
                    total = total.checked_add(bytes).ok_or("journal size overflow")?;
                    ensure(
                        bytes > 0 && bytes <= 256 * 1024 * 1024 && total <= 512 * 1024 * 1024,
                        "persistent journal exceeds fixture size bounds",
                    )?;
                    files.push(entry);
                }
                _ => return Err("journal tree contains a symbolic link or special inode".into()),
            }
        }
    }
    ensure(
        !files.is_empty(),
        "ended guest produced no persistent journal",
    )?;
    files.sort_by_key(|entry| entry.inode);
    Ok(files)
}

fn parse_rows(pin: &FilePin) -> Result<Vec<Value>> {
    let held = boot_files::checked_file(pin)?;
    let before = fs::stat(&held)?;
    let mut rows = Vec::new();
    let mut reader = BufReader::new(&held);
    loop {
        let mut bytes = Vec::new();
        let count = std::io::Read::by_ref(&mut reader)
            .take(1024 * 1024 + 1)
            .read_until(b'\n', &mut bytes)?;
        if count == 0 {
            break;
        }
        ensure(
            count <= 1024 * 1024 && bytes.last() == Some(&b'\n'),
            "oversized or truncated journal JSON entry",
        )?;
        let row: Value = serde_json::from_slice(&bytes)?;
        ensure(row.is_object(), "journal JSON entry is not an object")?;
        rows.push(row);
        ensure(rows.len() <= 200000, "too many journal entries")?;
    }
    ensure(
        fs::stat(&held)? == before,
        "journal output changed during analysis",
    )?;
    Ok(rows)
}

/// Only parse the actual inode/user lines, never the legacy fragment "Size:".
fn regular_inode_owned(text: &str, mode: u32, maximum: u64, uid: u32, gid: u32) -> Result<u64> {
    let inode = text
        .lines()
        .find(|l| l.starts_with("Inode: "))
        .ok_or("inode metadata absent")?;
    let fields: Vec<_> = inode.split_whitespace().collect();
    let value = |key: &str| {
        fields
            .iter()
            .position(|v| *v == key)
            .and_then(|n| fields.get(n + 1).copied())
    };
    ensure(
        value("Type:") == Some("regular"),
        "capture is not a regular guest inode",
    )?;
    ensure(
        u32::from_str_radix(value("Mode:").ok_or("inode mode absent")?, 8)? == mode,
        "guest inode permissions differ",
    )?;
    let owner = text
        .lines()
        .find(|l| l.starts_with("User: "))
        .ok_or("inode ownership absent")?;
    let fields: Vec<_> = owner.split_whitespace().collect();
    let value = |key: &str| {
        fields
            .iter()
            .position(|v| *v == key)
            .and_then(|n| fields.get(n + 1).copied())
    };
    ensure(
        value("User:").ok_or("inode uid absent")?.parse::<u32>()? == uid
            && value("Group:").ok_or("inode gid absent")?.parse::<u32>()? == gid,
        "guest inode owner differs",
    )?;
    let size: u64 = value("Size:").ok_or("inode size absent")?.parse()?;
    let links = text
        .lines()
        .find(|l| l.starts_with("Links: "))
        .ok_or("link count absent")?;
    ensure(
        links.split_whitespace().nth(1) == Some("1") && size > 0 && size <= maximum,
        "guest inode link count or size differs",
    )?;
    Ok(size)
}

#[cfg(test)]
fn regular_inode(text: &str, mode: u32, maximum: u64) -> Result<u64> {
    regular_inode_owned(text, mode, maximum, 0, 0)
}

fn dump_entry(
    plan: &CollectPlan,
    work: &Path,
    disk: &Path,
    entry: &GuestEntry,
    name: &str,
    maximum: u64,
) -> Result<FilePin> {
    ensure(
        entry.mode & 0o170000 == 0o100000,
        "only regular guest inodes can be extracted",
    )?;
    let stat = execute(
        work,
        &format!("{name}-stat"),
        &plan.debugfs,
        vec![
            "-R".into(),
            format!("stat <{}>", entry.inode),
            disk.to_string_lossy().into(),
        ],
        30,
        65536,
    )?;
    ensure(success(&stat, &[0]), "debugfs inode inspection failed")?;
    let text = String::from_utf8(boot_files::read_pin(&stat.stdout, 65536)?)?;
    let inode = text
        .lines()
        .find(|line| line.starts_with("Inode: "))
        .and_then(|line| line.split_whitespace().nth(1))
        .ok_or("stat inode absent")?
        .parse::<u64>()?;
    ensure(inode == entry.inode, "debugfs stat returned another inode")?;
    let size = regular_inode_owned(&text, entry.mode & 0o7777, maximum, entry.uid, entry.gid)?;
    ensure(
        entry.bytes == Some(size),
        "guest inode size changed after preflight",
    )?;
    // Only the already opened stdout file is written. No guest name becomes a host path.
    let output = execute(
        work,
        &format!("{name}-dump"),
        &plan.debugfs,
        vec![
            "-R".into(),
            format!("dump <{}> /proc/self/fd/1", entry.inode),
            disk.to_string_lossy().into(),
        ],
        60,
        maximum,
    )?;
    ensure(
        success(&output, &[0]) && output.stdout.bytes == size,
        "bounded inode extraction failed or returned a different size",
    )?;
    Ok(output.stdout)
}

fn dump_regular(
    plan: &CollectPlan,
    work: &Path,
    disk: &Path,
    guest: &str,
    name: &str,
    mode: u32,
    maximum: u64,
    index: &mut usize,
) -> Result<Option<FilePin>> {
    let Some(entry) = resolve_inode(plan, work, disk, guest, index)? else {
        return Ok(None);
    };
    ensure(
        entry.mode & 0o7777 == mode && entry.uid == 0 && entry.gid == 0,
        "capture or unit ownership/permissions differ",
    )?;
    Ok(Some(dump_entry(plan, work, disk, &entry, name, maximum)?))
}

fn collect(
    plan: &CollectPlan,
    ended: &Value,
    prepared: &Value,
    work: &Path,
    disk: &FilePin,
    group_binding: &crate::boot_gdm_proof::GroupBinding,
) -> Result<Value> {
    let source = boot_files::checked_file(disk)?;
    let before = fs::stat(&source)?;
    ensure(
        before.uid == 0 && before.mode & 0o7777 == 0o600 && before.nlink == 1,
        "ended working disk is not the private independent image",
    )?;
    let replay = work.join("journal-replay.ext4");
    boot_files::copy_pin(disk, &replay, 0o600)?;
    let replay_pin = boot_files::pin_file(&replay)?;
    let (copy, copy_id) = boot_files::open_pin(&replay_pin)?;
    ensure(
        (copy_id.dev, copy_id.ino) != (before.dev, before.ino),
        "journal replay copy aliases the ended disk",
    )?;
    drop(copy);
    let replay_result = execute(
        work,
        "ext4-journal-replay",
        &plan.e2fsck,
        vec![
            "-p".into(),
            "-E".into(),
            "journal_only".into(),
            replay.to_string_lossy().into(),
        ],
        180,
        8 * 1024 * 1024,
    )?;
    ensure(
        success(&replay_result, &[0, 1]),
        "independent ext4 journal replay failed",
    )?;
    let mut directory_index = 0usize;
    let entries = journal_manifest(plan, work, &replay, &mut directory_index)?;
    fs::write_json(
        &fs::absolute_string(&work.join("JOURNAL-INODES.json"))?,
        &entries,
        rustix::process::geteuid().as_raw(),
    )?;
    let mut files = Vec::new();
    for (index, entry) in entries.iter().enumerate() {
        files.push(dump_entry(
            plan,
            work,
            &replay,
            entry,
            &format!("journal-file-{index}"),
            256 * 1024 * 1024,
        )?);
    }
    let mut all_rows = Vec::new();
    let mut journal_results = Vec::new();
    let mut verified = true;
    for (index, file) in files.iter().enumerate() {
        let verify = execute(
            work,
            &format!("journal-{index}-verify"),
            &plan.journalctl,
            vec![
                "--verify".into(),
                format!("--file={}", file.path.display()),
                "--no-pager".into(),
            ],
            120,
            8 * 1024 * 1024,
        )?;
        let integrity = success(&verify, &[0]);
        verified &= integrity;
        let rows = if integrity {
            let output = execute(
                work,
                &format!("journal-{index}-entries"),
                &plan.journalctl,
                vec![
                    format!("--file={}", file.path.display()),
                    "--no-pager".into(),
                    "--all".into(),
                    "--output=json".into(),
                ],
                120,
                64 * 1024 * 1024,
            )?;
            ensure(
                success(&output, &[0]),
                "verified native journal JSON read failed",
            )?;
            let rows = parse_rows(&output.stdout)?;
            ensure(
                all_rows.len() + rows.len() <= 200000,
                "total journal entry bound exceeded",
            )?;
            all_rows.extend(rows);
            Some(output)
        } else {
            None
        };
        journal_results.push(json!({"journal":file,"integrity":verify,"json":rows}));
    }
    let capture = dump_regular(
        plan,
        work,
        &replay,
        "/var/lib/droidloom-mac-calibration/capture.pending",
        "calibration-capture",
        0o600,
        CAPTURE_LIMIT,
        &mut directory_index,
    )?;
    let unit = dump_regular(
        plan,
        work,
        &replay,
        "/usr/lib/systemd/system/droidloom-mac-calibration.service",
        "calibration-unit",
        0o644,
        65536,
        &mut directory_index,
    )?;
    let unit_unchanged = unit.as_ref().is_some_and(|pin| {
        pin.bytes == UNIT_BYTES.len() as u64 && pin.sha256 == fs::digest(UNIT_BYTES)
    });
    let mut capture_identity = json!({"pid1_service_proven":false});
    let mut selected_capture = false;
    if let Some(pin) = &capture {
        let document: Value = serde_json::from_slice(&boot_files::read_pin(pin, CAPTURE_LIMIT)?)?;
        let raw_boot = document["calibration_boot_id"].as_str().unwrap_or("");
        let boot: String = raw_boot.chars().filter(|c| *c != '-').collect();
        let invocation = document["systemd_invocation_id"].as_str().unwrap_or("");
        let expected_base = prepared["android_release"]["cohort"]["sha256"].as_str();
        let expected_runtime = prepared["android_release"]["runtime"]["sha256"].as_str();
        selected_capture = expected_base.is_some_and(fs::valid_digest)
            && expected_runtime.is_some_and(fs::valid_digest)
            && raw_boot.len() == 36
            && raw_boot.bytes().enumerate().all(|(i, b)| {
                if [8, 13, 18, 23].contains(&i) {
                    b == b'-'
                } else {
                    b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
                }
            })
            && document["schema"] == 1
            && document["scope"] == "android_kernel_first_mac_release_v1"
            && document["base_cohort_sha256"] == prepared["android_release"]["cohort"]["sha256"]
            && document["runtime_manifest_sha256"]
                == prepared["android_release"]["runtime"]["sha256"];
        capture_identity = service_evidence(&all_rows, &boot, invocation);
    }
    let mut boot_ids = BTreeSet::new();
    let mut failures = Vec::new();
    let mut denials = Vec::new();
    let mut high_priority = Vec::new();
    for row in &all_rows {
        if let Some(id) = row["_BOOT_ID"].as_str() {
            boot_ids.insert(id.to_owned());
        }
        if row["_PID"] == "1"
            && row["JOB_RESULT"]
                .as_str()
                .is_some_and(|v| ["failed", "dependency", "timeout"].contains(&v))
        {
            failures.push(row.clone());
        }
        let message = row["MESSAGE"].as_str().unwrap_or("");
        if message.contains("avc:") || message.contains("apparmor=\"DENIED\"") {
            denials.push(row.clone());
        }
        if row["PRIORITY"]
            .as_str()
            .and_then(|v| v.parse::<u8>().ok())
            .is_some_and(|v| v <= 3)
        {
            high_priority.push(row.clone());
        }
    }
    let mut greeter_proof_files = Vec::new();
    let mut greeter_source_verified = verified;
    for (index, (path, bytes)) in crate::boot_gdm_proof::FILES.iter().enumerate() {
        let observed = dump_regular(
            plan,
            work,
            &replay,
            path,
            &format!("greeter-proof-source-{index}"),
            0o444,
            65536,
            &mut directory_index,
        )?;
        let matches = observed
            .as_ref()
            .is_some_and(|pin| pin.bytes == bytes.len() as u64 && pin.sha256 == fs::digest(bytes));
        greeter_source_verified &= matches;
        greeter_proof_files
            .push(json!({"path":path,"observed":observed,"matches_frozen_source":matches}));
    }
    let timed_config = dump_regular(
        plan,
        work,
        &replay,
        crate::boot_gdm_proof::CONFIG,
        "greeter-timed-login-config",
        0o644,
        65536,
        &mut directory_index,
    )?;
    let timed_config_verified = if let Some(pin) = &timed_config {
        crate::boot_gdm_proof::timed_config_valid(&boot_files::read_pin(pin, 65536)?)
    } else {
        false
    };
    greeter_source_verified &= timed_config_verified;
    let native_group = dump_regular(
        plan,
        work,
        &replay,
        "/etc/group",
        "native-gdm-group",
        0o644,
        1024 * 1024,
        &mut directory_index,
    )?;
    let group_check = native_group
        .as_ref()
        .ok_or_else(|| -> Box<dyn std::error::Error + Send + Sync> {
            "ended native group file absent".into()
        })
        .and_then(|pin| {
            crate::boot_gdm_proof::validate_bound_group(
                &boot_files::read_pin(pin, 1024 * 1024)?,
                group_binding,
            )
        });
    let group_verified = group_check.is_ok();
    let group_error = group_check.err().map(|e| e.to_string());
    greeter_source_verified &= group_verified;
    let greeter_proof = crate::boot_gdm_proof::journal_evidence_bound(
        &all_rows,
        &boot_ids,
        greeter_source_verified,
        group_binding,
    );
    let ordinary_shutdown =
        ended["exit_code"] == 0 && ended["signal"].is_null() && ended["forced_stop"] == false;
    let calibration_proven = verified
        && unit_unchanged
        && selected_capture
        && ordinary_shutdown
        && capture_identity["pid1_service_proven"] == true;
    preserved(disk, &source, &before)?;
    Ok(
        json!({"journal_replay":replay_result,"journal_inode_preflight":entries,
        "journals":journal_results,"journal_integrity_verified":verified,
        "capture":capture,"unit":unit,"ordinary_unit_byte_identical":unit_unchanged,
        "capture_matches_selected_android":selected_capture,
        "calibration_service":capture_identity,"calibration_capture_proven":calibration_proven,
        "ordinary_guest_shutdown":ordinary_shutdown,"boot_ids":boot_ids,
        "greeter_proof_source_files":greeter_proof_files,"greeter_timed_login_config":timed_config,
        "greeter_timed_login_config_verified":timed_config_verified,"dynamic_greeter_environment":greeter_proof,
        "native_group_file":native_group,"native_group_binding":group_binding,
        "native_group_matches_preparation":group_verified,"native_group_binding_error":group_error,
        "systemd_failed_jobs":failures,"mac_denials":denials,"priority_error_records":high_priority,
        "journal_entries":all_rows.len(),"ended_working_disk_preserved":true,
        "guest_qualified":false,"production_ready":false,
        "next_required":"Review the original full-native failures and denials; use the normal kernel-first MAC packager for five-file admission; run independent Android, desktop and application acceptance."}),
    )
}

pub fn run(path: &Path, expected: &str) -> Result<()> {
    let plan: CollectPlan = fs::read_json(&fs::absolute_string(path)?, expected)?;
    ensure(
        plan.schema == "droidloom.full-ubuntu-boot-collect-plan.v1"
            && safe_name(&plan.collection_name),
        "unsupported collection plan",
    )?;
    for (pin, actual) in [
        (&plan.e2fsck, "/usr/sbin/e2fsck"),
        (&plan.debugfs, "/usr/sbin/debugfs"),
        (&plan.journalctl, "/usr/bin/journalctl"),
    ] {
        ensure(
            pin.path == Path::new(actual),
            "only original native diagnostic tools are admitted",
        )?;
        boot_files::checked_file(pin)?;
    }
    let ended: Value = serde_json::from_slice(&boot_files::read_pin(&plan.ended, 1024 * 1024)?)?;
    ensure(
        ended["schema"] == "droidloom.full-ubuntu-run-ended.v1"
            && ended["source_image_preserved"] == true
            && ended["guest_qualified"] == false
            && ended["production_ready"] == false,
        "only a complete ended-run receipt can be collected",
    )?;
    let prepared_pin: FilePin = serde_json::from_value(ended["prepared"].clone())?;
    let prepared: Value =
        serde_json::from_slice(&boot_files::read_pin(&prepared_pin, 8 * 1024 * 1024)?)?;
    ensure(
        prepared["schema"] == "droidloom.full-ubuntu-boot-prepared.v1"
            && prepared["guest_qualified"] == false
            && prepared["production_ready"] == false,
        "run does not refer to a prepared private native fixture",
    )?;
    let root = field_path(&prepared, "work_directory")?;
    ensure(
        root.parent() == Some(Path::new("/var/lib/droidloom-qualification")),
        "collector is restricted to private qualification fixtures",
    )?;
    let boot = root.join("boot");
    ensure(
        field_path(&prepared, "boot_directory")? == boot
            && prepared_pin.path == boot.join("BOOT-PREPARED.json"),
        "prepared path binding differs",
    )?;
    let run = field_path(&ended, "run_directory")?;
    ensure(
        run.parent() == Some(boot.as_path())
            && run
                .file_name()
                .and_then(|v| v.to_str())
                .is_some_and(safe_name)
            && plan.ended.path == run.join("RUN-ENDED.json"),
        "run receipt path binding differs",
    )?;
    for dir in [&root, &boot, &run] {
        private_tree(dir)?;
    }
    let native_pin: FilePin = serde_json::from_value(prepared["native_receipt"].clone())?;
    ensure(
        native_pin.path == root.join("NATIVE-PREPARED.json"),
        "native GDM group authority is not the boot's own preparation receipt",
    )?;
    let native_file = boot_files::checked_file(&native_pin)?;
    let native_identity = fs::stat(&native_file)?;
    ensure(
        native_identity.uid == 0
            && native_identity.gid == 0
            && native_identity.mode & 0o7777 == 0o600
            && native_identity.nlink == 1,
        "native GDM preparation receipt is not root protected and private",
    )?;
    let native: Value =
        serde_json::from_slice(&boot_files::read_pin(&native_pin, 4 * 1024 * 1024)?)?;
    let group_binding = crate::boot_gdm_proof::native_group_binding(&native, &root)?;
    let disk: FilePin = serde_json::from_value(ended["working_disk"].clone())?;
    let serial: FilePin = serde_json::from_value(ended["serial"].clone())?;
    ensure(
        disk.path == run.join("working.ext4") && serial.path.parent() == Some(run.as_path()),
        "ended artifacts do not belong to this private run",
    )?;
    boot_files::checked_file(&serial)?;
    let original: FilePin = serde_json::from_value(ended["preserved_source_image"].clone())?;
    let expected_original: FilePin = serde_json::from_value(prepared["root_image"].clone())?;
    ensure(
        same_pin(&original, &expected_original) && original.path.parent() == Some(boot.as_path()),
        "source image custody differs",
    )?;
    let original_identity: Identity = serde_json::from_value(ended["source_identity"].clone())?;
    let original_file = boot_files::checked_file(&original)?;
    ensure(
        fs::stat(&original_file)? == original_identity,
        "original source image changed after run",
    )?;
    let working_identity = boot_files::open_pin(&disk)?.1;
    ensure(
        disk.bytes == original.bytes
            && (working_identity.dev, working_identity.ino)
                != (original_identity.dev, original_identity.ino),
        "ended disk aliases or differs in size from its prepared source image",
    )?;
    let work = run.join(&plan.collection_name);
    // debugfs command arguments are fixed paths; reject parser metacharacters.
    ensure(
        work.to_str().is_some_and(|v| {
            v.bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"/._-".contains(&b))
        }),
        "unsupported debugfs path characters",
    )?;
    boot_files::private_dir(&work)?;
    fs::write_json(
        &fs::absolute_string(&work.join("COLLECT-INPUTS.json"))?,
        &plan,
        0,
    )?;
    let result = collect(&plan, &ended, &prepared, &work, &disk, &group_binding);
    let source_check = preserved(&original, &original_file, &original_identity);
    let native_check = preserved(&native_pin, &native_file, &native_identity);
    let source_preserved = source_check.is_ok();
    let native_preserved = native_check.is_ok();
    let status = if result.is_ok() && source_preserved && native_preserved {
        "collected"
    } else {
        "failed"
    };
    let details = result.as_ref().ok().cloned().unwrap_or(Value::Null);
    let errors: Vec<_> = [
        result.as_ref().err().map(ToString::to_string),
        source_check.as_ref().err().map(ToString::to_string),
        native_check.as_ref().err().map(ToString::to_string),
    ]
    .into_iter()
    .flatten()
    .collect();
    let output = json!({"schema":"droidloom.full-ubuntu-boot-collected.v1",
        "input_sha256":expected,"ended":plan.ended,"prepared":prepared_pin,
        "native_receipt":native_pin,"native_receipt_identity":native_identity,"native_receipt_preserved":native_preserved,
        "collection_directory":work,"status":status,"errors":errors,"details":details,
        "preserved_source_image":original,"source_image_preserved":source_preserved,
        "guest_qualified":false,"production_ready":false});
    let receipt = work.join("COLLECTED.json");
    let sha = fs::write_json(&fs::absolute_string(&receipt)?, &output, 0)?;
    println!(
        "{}",
        json!({"receipt":receipt,"sha256":sha,"status":status,
        "guest_qualified":false,"production_ready":false})
    );
    source_check?;
    native_check?;
    result?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn real_ext4_inodes_reject_alias_traversal_and_extract_only_selected_bytes() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let layout = dir.path().join("root");
        std::fs::create_dir(&layout)?;
        std::fs::write(layout.join("payload"), b"original-inode")?;
        std::os::unix::fs::symlink("/outside", &layout.join("alias"))?;
        let disk = dir.path().join("test.ext4");
        let file = boot_files::new_file(&disk, 0o600)?;
        file.set_len(32 * 1024 * 1024)?;
        file.sync_all()?;
        let mkfs = boot_files::pin_file(Path::new("/usr/sbin/mke2fs"))?;
        let made = execute(
            dir.path(),
            "test-mkfs",
            &mkfs,
            vec![
                "-q".into(),
                "-F".into(),
                "-t".into(),
                "ext4".into(),
                "-d".into(),
                layout.to_string_lossy().into(),
                disk.to_string_lossy().into(),
            ],
            30,
            1024 * 1024,
        )?;
        assert!(success(&made, &[0]));
        let plan = CollectPlan {
            schema: String::new(),
            ended: boot_files::pin_file(&disk)?,
            collection_name: "test".into(),
            e2fsck: boot_files::pin_file(Path::new("/usr/sbin/e2fsck"))?,
            debugfs: boot_files::pin_file(Path::new("/usr/sbin/debugfs"))?,
            journalctl: boot_files::pin_file(Path::new("/usr/bin/journalctl"))?,
        };
        let mut index = 0;
        let entry = resolve_inode(&plan, dir.path(), &disk, "/payload", &mut index)?
            .ok_or("test payload absent")?;
        let actual = dump_entry(&plan, dir.path(), &disk, &entry, "test-payload", 1024)?;
        assert_eq!(boot_files::read_pin(&actual, 1024)?, b"original-inode");
        assert!(resolve_inode(&plan, dir.path(), &disk, "/alias/payload", &mut index).is_err());
        assert!(resolve_inode(&plan, dir.path(), &disk, "/absent", &mut index)?.is_none());
        Ok(())
    }
    #[test]
    fn actual_ext4_gdm_group_is_root_owned_and_bound_to_preparation() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let layout = dir.path().join("root");
        std::fs::create_dir(&layout)?;
        std::fs::create_dir(layout.join("etc"))?;
        std::fs::write(layout.join("etc/group"), b"root:x:0:\ngdm:x:981:\n")?;
        let disk = dir.path().join("group.ext4");
        let file = boot_files::new_file(&disk, 0o600)?;
        file.set_len(32 * 1024 * 1024)?;
        file.sync_all()?;
        let mkfs = boot_files::pin_file(Path::new("/usr/sbin/mke2fs"))?;
        let made = execute(
            dir.path(),
            "group-mkfs",
            &mkfs,
            vec![
                "-q".into(),
                "-F".into(),
                "-t".into(),
                "ext4".into(),
                "-d".into(),
                layout.to_string_lossy().into(),
                disk.to_string_lossy().into(),
            ],
            30,
            1024 * 1024,
        )?;
        assert!(success(&made, &[0]));
        let plan = CollectPlan {
            schema: String::new(),
            ended: boot_files::pin_file(&disk)?,
            collection_name: "group".into(),
            e2fsck: boot_files::pin_file(Path::new("/usr/sbin/e2fsck"))?,
            debugfs: boot_files::pin_file(Path::new("/usr/sbin/debugfs"))?,
            journalctl: boot_files::pin_file(Path::new("/usr/bin/journalctl"))?,
        };
        // Only this disposable ext4 image is modified; the host group database
        // and account identities are never changed by the regression.
        for (field, value) in [("uid", "0"), ("gid", "0"), ("mode", "0100644")] {
            let set = execute(
                dir.path(),
                &format!("group-set-{field}"),
                &plan.debugfs,
                vec![
                    "-w".into(),
                    "-R".into(),
                    format!("sif /etc/group {field} {value}"),
                    disk.to_string_lossy().into(),
                ],
                30,
                65536,
            )?;
            assert!(success(&set, &[0]));
        }
        let root = Path::new("/var/lib/droidloom-qualification/group-test");
        let native = json!({
            "schema":"droidloom.complete-ubuntu-native-prepared.v1",
            "work_directory":root,"root":root.join("root"),"guest_qualified":false,"production_ready":false,
            "native_initialization":{"schema":"droidloom.complete-native-ubuntu-initialization.v1",
                "root":root.join("root"),"work":root,"source_stage":"installed",
                "native_initialization_complete":true,"guest_started":false,"guest_qualified":false,
                "host_passwords_keys_homes_imported":false,
                "accounts":{"groups":{"gdm":981},"users":[{"name":"gdm","uid":981,"gid":981}],
                    "normal_service_accounts_preserved":true}}
        });
        let binding = crate::boot_gdm_proof::native_group_binding(&native, root)?;
        let mut index = 0;
        let group = dump_regular(
            &plan,
            dir.path(),
            &disk,
            "/etc/group",
            "group-readback",
            0o644,
            1024,
            &mut index,
        )?
        .ok_or("actual group absent")?;
        let bytes = boot_files::read_pin(&group, 1024)?;
        crate::boot_gdm_proof::validate_bound_group(&bytes, &binding)?;
        let changed = execute(
            dir.path(),
            "group-change-owner",
            &plan.debugfs,
            vec![
                "-w".into(),
                "-R".into(),
                "sif /etc/group uid 1000".into(),
                disk.to_string_lossy().into(),
            ],
            30,
            65536,
        )?;
        assert!(success(&changed, &[0]));
        assert!(
            dump_regular(
                &plan,
                dir.path(),
                &disk,
                "/etc/group",
                "group-wrong-owner",
                0o644,
                1024,
                &mut index
            )
            .is_err()
        );
        Ok(())
    }

    #[test]
    fn actual_pid1_identity_and_both_success_events_are_required() {
        let boot = "12345678123412341234123456781234";
        let invocation = "23456789123412341234123456781234";
        let base = json!({"_PID":"1","_UID":"0","_TRANSPORT":"journal","UNIT":UNIT,
            "_BOOT_ID":boot,"INVOCATION_ID":invocation});
        let mut exit = base.clone();
        exit["MESSAGE_ID"] = json!("98e322203f7a4ed290d09fe03c09fe15");
        exit["COMMAND"] = json!("ExecStart");
        exit["EXIT_CODE"] = json!("exited");
        exit["EXIT_STATUS"] = json!("0");
        let mut done = base;
        done["MESSAGE_ID"] = json!("39f53479d3a045ac8e11786248231fbf");
        done["JOB_TYPE"] = json!("start");
        done["JOB_RESULT"] = json!("done");
        let rows = vec![exit, done];
        assert_eq!(
            service_evidence(&rows, boot, invocation)["pid1_service_proven"],
            true
        );
        for (key, value) in [
            ("_PID", "2"),
            ("_UID", "1000"),
            ("_TRANSPORT", "stdout"),
            ("_BOOT_ID", "a2345678123412341234123456781234"),
            ("INVOCATION_ID", "b3456789123412341234123456781234"),
            ("EXIT_CODE", "killed"),
            ("EXIT_STATUS", "1"),
        ] {
            let mut changed = rows.clone();
            changed[0][key] = json!(value);
            assert_eq!(
                service_evidence(&changed, boot, invocation)["pid1_service_proven"],
                false,
                "{key}"
            );
        }
        assert_eq!(
            service_evidence(&rows[..1], boot, invocation)["pid1_service_proven"],
            false
        );
        let mut failed = rows.clone();
        let mut job = rows[1].clone();
        job["JOB_RESULT"] = json!("failed");
        failed.push(job);
        assert_eq!(
            service_evidence(&failed, boot, invocation)["pid1_service_proven"],
            false
        );
    }
    #[test]
    fn original_journalctl_rejects_plain_json_as_a_native_journal() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let path = dir.path().join("synthetic.journal");
        std::fs::write(&path, br#"{"_PID":"1","_UID":"0","MESSAGE_ID":"98e322203f7a4ed290d09fe03c09fe15","EXIT_STATUS":"0"}"#)?;
        let tool = boot_files::pin_file(Path::new("/usr/bin/journalctl"))?;
        let result = execute(
            dir.path(),
            "reject-synthetic",
            &tool,
            vec![
                "--verify".into(),
                format!("--file={}", path.display()),
                "--no-pager".into(),
            ],
            10,
            1024 * 1024,
        )?;
        assert!(!success(&result, &[0]));
        assert!(result.child_reaped && !result.timed_out && !result.output_limited);
        Ok(())
    }
    #[test]
    fn inode_checks_ignore_legacy_fragment_size_and_reject_privilege_changes() -> Result<()> {
        let inode = "Inode: 21   Type: regular    Mode: 0600   Flags: 0x80000\nUser: 0 Group: 0 Size: 1234\nLinks: 1 Blockcount: 8\nFragment: Address: 0 Number: 0 Size: 0\n";
        assert_eq!(regular_inode(inode, 0o600, 2000)?, 1234);
        assert!(regular_inode(&inode.replace("User: 0", "User: 1"), 0o600, 2000).is_err());
        assert!(regular_inode(&inode.replace("Links: 1", "Links: 2"), 0o600, 2000).is_err());
        assert!(regular_inode(inode, 0o644, 2000).is_err());
        assert!(regular_inode(inode, 0o600, 100).is_err());
        Ok(())
    }
}
