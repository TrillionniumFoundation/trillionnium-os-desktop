//! Fresh ordinary-boot observation. Historical records cannot recreate a
//! working Complete or its old Main; this entry always reacquires real Main.
use super::*;
use crate::control::{DEFAULT_CONTROL_SOCKET, NativeApplicationInspector};
use std::collections::{BTreeMap, BTreeSet};
fn fields(raw: &[u8]) -> io::Result<BTreeMap<String, String>> {
    let text = std::str::from_utf8(raw).map_err(io::Error::other)?;
    let mut result = BTreeMap::new();
    for line in text.lines() {
        let (k, v) = line
            .split_once('=')
            .ok_or_else(|| error("normal PID1 property missing name"))?;
        if result.insert(k.into(), v.into()).is_some() {
            return Err(error("normal PID1 property duplicated"));
        }
    }
    Ok(result)
}
fn deadline(s: &Sources) -> io::Result<Instant> {
    let expected = if s.actor == Actor::Verify {
        include_str!("../../../packaging/systemd/system/droidloom-production-verify.service")
    } else {
        include_str!("../../../packaging/systemd/system/droidloom-production-verify-return.service")
    };
    let name = s.actor.unit();
    let path = PathBuf::from("/usr/lib/systemd/system").join(name);
    let unit = pio::Input::open(
        &path,
        &c::BytesPin {
            bytes: expected.len() as u64,
            sha256: sha(expected.as_bytes()),
        },
        0o444,
        None,
    )?;
    let start_end = Instant::now() + Duration::from_secs(30);
    let response = pio::invoke(
        &s.systemctl,
        &[
            "show",
            name,
            "--no-pager",
            "--property=MainPID,ExecMainStartTimestampMonotonic,ControlGroup,FragmentPath,InvocationID,RuntimeMaxUSec",
        ],
        None,
        start_end,
        16384,
    )?;
    response.success()?;
    unit.guard()?;
    let values = fields(&response.stdout)?;
    if values.len() != 6
        || values.get("MainPID") != Some(&std::process::id().to_string())
        || values.get("ControlGroup") != Some(&format!("/system.slice/{name}"))
        || values.get("FragmentPath") != Some(&path.to_string_lossy().into_owned())
        || values
            .get("InvocationID")
            .is_none_or(|v| v.len() != 32 || !v.bytes().all(|b| b.is_ascii_hexdigit()))
    {
        return Err(error(
            "normal verifier is not PID1's actual source-bound invocation",
        ));
    }
    let start = values
        .get("ExecMainStartTimestampMonotonic")
        .and_then(|s| s.parse::<u64>().ok())
        .filter(|v| *v > 0)
        .ok_or_else(|| error("actual PID1 start clock missing"))?;
    let seconds = if s.actor == Actor::Verify {
        c::VERIFY_SECONDS
    } else {
        c::RETURN_SECONDS
    };
    let expected_runtime = if s.actor == Actor::Verify {
        c::VERIFY_SERVICE_SECONDS
    } else {
        c::RETURN_SERVICE_SECONDS
    };
    let runtime = values
        .get("RuntimeMaxUSec")
        .ok_or_else(|| error("actual normal runtime bound absent"))?;
    if parse_duration(runtime)? != expected_runtime {
        return Err(error(
            "PID1 does not enforce the source normal verifier window",
        ));
    }
    let end_ns = start
        .checked_mul(1000)
        .and_then(|v| v.checked_add(seconds * 1_000_000_000))
        .ok_or_else(|| error("normal window overflow"))?;
    s.guard()?;
    instant_until(end_ns, Instant::now() + Duration::from_secs(seconds))
}
fn parse_duration(s: &str) -> io::Result<u64> {
    let mut total = 0u64;
    for term in s.split_ascii_whitespace() {
        let (unit, n) = if let Some(n) = term.strip_suffix("min") {
            (60, n)
        } else if let Some(n) = term.strip_suffix('h') {
            (3600, n)
        } else if let Some(n) = term.strip_suffix('s') {
            (1, n)
        } else {
            return Err(error("normal PID1 duration format differs"));
        };
        let n = n.parse::<u64>().map_err(io::Error::other)?;
        total = total
            .checked_add(
                n.checked_mul(unit)
                    .ok_or_else(|| error("duration overflow"))?,
            )
            .ok_or_else(|| error("duration overflow"))?;
    }
    Ok(total)
}
fn timestamp(v: &Value) -> io::Result<u64> {
    v["__MONOTONIC_TIMESTAMP"]
        .as_str()
        .and_then(|s| s.parse().ok())
        .filter(|v| *v > 0)
        .ok_or_else(|| error("trusted journal monotonic time absent"))
}
fn parse_journal(raw: &[u8], limit: usize) -> io::Result<Vec<Value>> {
    if raw.len() > limit {
        return Err(error("normal whole journal exceeds fixed bound"));
    }
    let mut rows = Vec::new();
    for line in raw.split(|b| *b == b'\n').filter(|s| !s.is_empty()) {
        if line.len() > 1024 * 1024 || rows.len() >= 100000 {
            return Err(error("normal journal row bounds differ"));
        }
        rows.push(serde_json::from_slice(line)?);
    }
    Ok(rows)
}
// Native datagrams carry kernel SCM_CREDENTIALS and provider-bound
// SCM_SECURITY. The fixed source boots place SELinux before AppArmor; both
// current providers are independently checked by Sources. A sealed child is
// non-dumpable, so journals need not (and must not gain ptrace to) read its exe.
// This is only a comparison with the actual private capture's protected record.
fn native_marker_matches(row: &Value, boot: &str, pid: u32, candidate: &str, digest: &str) -> bool {
    row["_BOOT_ID"] == boot
        && row["_TRANSPORT"] == "journal"
        && row["_PID"] == pid.to_string()
        && row["_UID"] == "0"
        && row["_GID"] == "0"
        && row["_SYSTEMD_UNIT"] == crate::native_working_contract::PARENT_UNIT
        && row["_SYSTEMD_CGROUP"]
            == format!(
                "/system.slice/{}",
                crate::native_working_contract::PARENT_UNIT
            )
        && row["_SELINUX_CONTEXT"] == "u:system_r:p4_linux_production_commit_t:s0"
        && row["SYSLOG_IDENTIFIER"] == "droidloom-production-commit"
        && row["DROIDLOOM_COMMIT_SHA256"] == digest
        && row["DROIDLOOM_CANDIDATE"] == candidate
        && row["MESSAGE"] == format!("DROIDLOOM_PRODUCTION_COMMIT {candidate} {digest}")
}
fn trusted_marker(rows: &[Value], s: &Sources, h: &records::History) -> io::Result<u64> {
    let boot = h.boot_id.replace('-', "");
    let mut found = None;
    for row in rows {
        if row["_BOOT_ID"] != boot {
            return Err(error("normal history query returned another boot"));
        }
        if row["DROIDLOOM_COMMIT_SHA256"] == h.digest
            && row["DROIDLOOM_CANDIDATE"] == s.config.candidate_id
        {
            if !native_marker_matches(row, &boot, h.commit_pid, &s.config.candidate_id, &h.digest)
                || found.replace(timestamp(row)?).is_some()
            {
                return Err(error(
                    "history marker lacks its unique actual source actor provenance",
                ));
            }
        }
    }
    found.ok_or_else(|| error("actual prior commit journal marker missing"))
}
fn normal_shutdown(rows: &[Value], boot: &str, after: u64) -> io::Result<Value> {
    let boot = boot.replace('-', "");
    let required = BTreeSet::from([
        "droidloom-production.service",
        "droidloom-instance-launcher.service",
        "droidloom-instance-factory.service",
        "droidloom-early-observer.service",
        "user@1000.service",
        crate::native_working_contract::PARENT_UNIT,
    ]);
    let mut stopped = BTreeSet::new();
    let mut reboot = None;
    let mut shutdown = None;
    for row in rows {
        if row["_BOOT_ID"] != boot {
            return Err(error("prior shutdown query returned another boot"));
        }
        if row["_PID"] != "1" || row["_UID"] != "0" || row["_EXE"] != "/usr/lib/systemd/systemd" {
            continue;
        }
        let time = timestamp(row)?;
        if time <= after {
            continue;
        }
        let unit = row["UNIT"].as_str().unwrap_or("");
        let relevant =
            required.contains(unit) || ["reboot.target", "systemd-reboot.service"].contains(&unit);
        if relevant
            && [("UNIT_RESULT", "success"), ("JOB_RESULT", "done")]
                .iter()
                .any(|(k, w)| row.get(*k).is_some_and(|v| v != *w))
        {
            return Err(error("actual PID1 reported failed production retirement"));
        }
        if row["MESSAGE_ID"] == "9d1aaa27d60140bd96365438aad20286"
            && row["JOB_RESULT"] == "done"
            && required.contains(unit)
        {
            stopped.insert(unit);
        }
        if row["MESSAGE_ID"] == "39f53479d3a045ac8e11786248231fbf"
            && row["JOB_RESULT"] == "done"
            && unit == "reboot.target"
        {
            reboot = Some(time);
        }
        if row["MESSAGE"] == "Shutting down." {
            shutdown = Some(time);
        }
    }
    if stopped != required || reboot.is_none() || shutdown.is_none() || shutdown < reboot {
        return Err(error(
            "actual prior PID1 did not complete normal stop/reboot/shutdown after the live commit",
        ));
    }
    Ok(
        json!({"boot_id":boot,"commit_monotonic_us":after,"stopped_units":stopped,
  "reboot_target_monotonic_us":reboot,"shutdown_monotonic_us":shutdown,
  "ordinary_shutdown_verified":true}),
    )
}
fn history_journal(s: &Sources, h: &records::History, end: Instant) -> io::Result<Value> {
    s.guard()?;
    let verify = pio::invoke(
        &s.journalctl,
        &["--verify", "--no-pager"],
        None,
        end,
        4 * 1024 * 1024,
    )?;
    if !verify.status.success() {
        return Err(error("normal journal integrity verification failed"));
    }
    let marker = pio::invoke(
        &s.journalctl,
        &[
            "--no-pager",
            "-b",
            &h.boot_id,
            "-o",
            "json",
            "SYSLOG_IDENTIFIER=droidloom-production-commit",
        ],
        None,
        end,
        4 * 1024 * 1024,
    )?;
    marker.success()?;
    let marker_time = trusted_marker(&parse_journal(&marker.stdout, 4 * 1024 * 1024)?, s, h)?;
    let shutdown = pio::invoke(
        &s.journalctl,
        &["--no-pager", "-b", &h.boot_id, "-o", "json", "_PID=1"],
        None,
        end,
        64 * 1024 * 1024,
    )?;
    shutdown.success()?;
    let result = normal_shutdown(
        &parse_journal(&shutdown.stdout, 64 * 1024 * 1024)?,
        &h.boot_id,
        marker_time,
    )?;
    s.guard()?;
    Ok(
        json!({"actual":result,"integrity_tool":verify.observation(),"marker_tool":marker.observation(),"shutdown_tool":shutdown.observation()}),
    )
}
pub(super) fn observe() -> io::Result<()> {
    let sources = Sources::open(Actor::Verify, None)?;
    let end = deadline(&sources)?;
    let mut records = records::Records::reopen(&sources)?;
    let history = records::History::observe(&sources, &records)?;
    let ready_end = end - Duration::from_secs(c::HISTORY_SECONDS + c::SELECTION_SECONDS);
    // Only fixed-socket absence before any peer admission is retryable.
    loop {
        match fs::symlink_metadata(DEFAULT_CONTROL_SOCKET) {
            Ok(_) => break,
            Err(e)
                if e.kind() == io::ErrorKind::NotFound
                    && Instant::now() + Duration::from_secs(70) < ready_end =>
            {
                sources.guard()?;
                std::thread::sleep(Duration::from_secs(1));
            }
            Err(e) => return Err(e),
        }
    }
    let mut inspector =
        NativeApplicationInspector::acquire_until(Path::new(DEFAULT_CONTROL_SOCKET), ready_end)
            .map_err(|e| error(&e.to_string()))?;
    let mut attempts = 0u32;
    let main = loop {
        if Instant::now() + Duration::from_secs(70) >= ready_end
            || attempts >= c::READY_SECONDS as u32
        {
            return Err(error(
                "normal Main did not become Ready in its original source window",
            ));
        }
        sources.guard()?;
        attempts += 1;
        if let Some(main) = inspector
            .observe_production_main_if_ready_until(ready_end)
            .map_err(|e| error(&e.to_string()))?
        {
            break main;
        }
        std::thread::sleep(Duration::from_secs(1));
    };
    sources.compare_main(&main)?;
    history.same_selected_pair(main.facts())?;
    records.guard()?;
    let history_end = end - Duration::from_secs(c::SELECTION_SECONDS);
    let journal = history_journal(&sources, &history, history_end)?;
    let refreshed = inspector
        .refresh_main_until(&main, end - Duration::from_secs(40))
        .map_err(|e| error(&e.to_string()))?;
    sources.compare_main(&refreshed)?;
    history.same_selected_pair(refreshed.facts())?;
    records.guard()?;
    let mut environment = pio::Environment::open()?;
    let selected = environment.is_active(&sources.config.candidate_id)?;
    if selected {
        if !records.has_active() {
            return Err(error(
                "persistent selector has no actual first-normal observation",
            ));
        }
        let prior: Value = serde_json::from_slice(&records.read("ACTIVE.json")?)?;
        if prior["schema"] != "droidloom.ordinary-production-observed.v1"
            || prior["candidate_id"] != sources.config.candidate_id
            || prior["configuration"] != json!(sources.config_input.pin)
            || prior["history_sha256"] != history.digest
            || !crate::native_working_contract::uuid(prior["normal_boot_id"].as_str().unwrap_or(""))
        {
            return Err(error(
                "persistent ordinary observation differs from the source lineage",
            ));
        }
    } else {
        if records.has_active() {
            return Err(error(
                "ordinary activation history exists without its live selector",
            ));
        }
        let actual = environment.select(&sources.grub, &sources.config.candidate_id, false, end)?;
        records.write_json("ACTIVE.json",&json!({"schema":"droidloom.ordinary-production-observed.v1",
   "candidate_id":sources.config.candidate_id,"configuration":sources.config_input.pin,
   "history_sha256":history.digest,"working_boot_id":history.boot_id,"normal_boot_id":sources.boot_id,
   "fresh_main":refreshed.facts(),"normal_shutdown":journal,"actual_persistent_selection":actual,
   "historical_complete_recreated":false,"new_epoch_business_cases_reexecuted":false,
   "original_user_data_migration_claimed":false,"production_activation_observed":true}))?;
    }
    sources.guard()?;
    records.guard()?;
    environment.guard()?;
    println!(
        "{}",
        json!({"schema":"droidloom.production-current-normal-observation.v1",
  "candidate_id":sources.config.candidate_id,"actual_boot_id":sources.boot_id,
  "current_main":refreshed.facts(),"retained_complete_sha256":history.digest,
  "persistent_selection_observed":true,"historical_complete_recreated":false})
    );
    Ok(())
}
pub(super) fn return_original() -> io::Result<()> {
    let sources = Sources::open(Actor::Return, None)?;
    let end = deadline(&sources)?;
    let mut environment = pio::Environment::open()?;
    let cleared = environment.clear_owned(
        &sources.grub,
        &sources.config.candidate_id,
        end - Duration::from_secs(30),
    )?;
    sources.guard()?;
    environment.guard()?;
    let request = pio::request_reboot(&sources.systemctl, end);
    let pid1 = pio::observe_reboot(&sources.systemctl, end)?;
    println!(
        "{}",
        json!({"schema":"droidloom.production-owned-fallback-request.v1","candidate_id":sources.config.candidate_id,
  "actual_boot_id":sources.boot_id,"own_selectors_cleared":cleared,
  "request":request.as_ref().map(pio::CommandResult::observation).unwrap_or_else(|e|json!({"error":e.to_string()})),
  "actual_pid1":pid1,"ordinary_shutdown_observed":false,"original_return_observed":false})
    );
    loop {
        if Instant::now() >= end {
            return Err(error(
                "normal fallback did not retire its real unit within the original end",
            ));
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn row(boot: &str, unit: &str, id: &str, t: u64) -> Value {
        json!({"_BOOT_ID":boot,"_PID":"1","_UID":"0","_EXE":"/usr/lib/systemd/systemd","UNIT":unit,"MESSAGE_ID":id,"JOB_RESULT":"done","__MONOTONIC_TIMESTAMP":t.to_string()})
    }
    #[test]
    fn production_native_marker_needs_kernel_actor_fields_without_a_proc_exe_exception() {
        let boot = "a".repeat(32);
        let candidate = "b".repeat(64);
        let digest = "c".repeat(64);
        let row = json!({"_BOOT_ID":boot,"_TRANSPORT":"journal","_PID":"123","_UID":"0","_GID":"0",
            "_SYSTEMD_UNIT":crate::native_working_contract::PARENT_UNIT,
            "_SYSTEMD_CGROUP":format!("/system.slice/{}",crate::native_working_contract::PARENT_UNIT),
            "_SELINUX_CONTEXT":"u:system_r:p4_linux_production_commit_t:s0",
            "SYSLOG_IDENTIFIER":"droidloom-production-commit","DROIDLOOM_COMMIT_SHA256":digest,
            "DROIDLOOM_CANDIDATE":candidate,"MESSAGE":format!("DROIDLOOM_PRODUCTION_COMMIT {candidate} {digest}")});
        assert!(row.get("_EXE").is_none());
        assert!(native_marker_matches(&row, &boot, 123, &candidate, &digest));
        for (key, value) in [
            ("_BOOT_ID", "foreign"),
            ("_TRANSPORT", "stdout"),
            ("_PID", "124"),
            ("_UID", "1000"),
            ("_GID", "1000"),
            ("_SYSTEMD_UNIT", "other.service"),
            ("_SYSTEMD_CGROUP", "/system.slice/other.service"),
            ("_SELINUX_CONTEXT", "droidloom-production-commit (enforce)"),
            ("SYSLOG_IDENTIFIER", "other"),
            ("DROIDLOOM_COMMIT_SHA256", "other"),
            ("DROIDLOOM_CANDIDATE", "other"),
            ("MESSAGE", "other"),
        ] {
            let mut wrong = row.clone();
            wrong[key] = value.into();
            wrong["_EXE"] = c::EXECUTABLE.into();
            assert!(
                !native_marker_matches(&wrong, &boot, 123, &candidate, &digest),
                "accepted wrong {key}"
            );
            wrong.as_object_mut().unwrap().remove(key);
            assert!(
                !native_marker_matches(&wrong, &boot, 123, &candidate, &digest),
                "accepted missing {key}"
            );
        }
    }
    #[test]
    fn production_requires_actual_shutdown_after_marker_not_a_request() {
        let boot = "a".repeat(32);
        let mut rows = Vec::new();
        for unit in [
            "droidloom-production.service",
            "droidloom-instance-launcher.service",
            "droidloom-instance-factory.service",
            "droidloom-early-observer.service",
            "user@1000.service",
            crate::native_working_contract::PARENT_UNIT,
        ] {
            rows.push(row(&boot, unit, "9d1aaa27d60140bd96365438aad20286", 20));
        }
        rows.push(row(
            &boot,
            "reboot.target",
            "39f53479d3a045ac8e11786248231fbf",
            30,
        ));
        let mut last = row(&boot, "", "", 40);
        last["MESSAGE"] = "Shutting down.".into();
        rows.push(last);
        normal_shutdown(&rows, &boot, 10).unwrap();
        assert!(normal_shutdown(&rows, &boot, 25).is_err());
        let mut changed = rows.clone();
        changed[0]["_PID"] = "123".into();
        assert!(normal_shutdown(&changed, &boot, 10).is_err());
        let mut changed = rows.clone();
        changed[0]["JOB_RESULT"] = "failed".into();
        assert!(normal_shutdown(&changed, &boot, 10).is_err());
        let mut changed = rows.clone();
        changed.pop();
        assert!(normal_shutdown(&changed, &boot, 10).is_err());
        assert!(normal_shutdown(&rows, &"b".repeat(32), 10).is_err());
    }
    #[test]
    fn production_finite_manager_window_parses_whole_units_only() {
        assert_eq!(parse_duration("18min 15s").unwrap(), 1095);
        for value in ["infinity", "18m15", "1095.0s", "1ms", "-1s"] {
            assert!(parse_duration(value).is_err());
        }
    }
}
