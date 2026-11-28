//! Read comparison frames from verified journals of the actually ended guest.
//! Reassembled JSON is evidence data only; it cannot recreate any live owner.
use super::*;
use crate::empty_meituan_contract as fixed;

fn token(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
}

fn frames(rows: &[Value], boots: &BTreeSet<String>) -> Result<(Vec<u8>, Value)> {
    let mut identity: Option<(String, String, String)> = None;
    let mut lines = Vec::new();
    for row in rows {
        if row["_SYSTEMD_UNIT"] != fixed::UNIT {
            continue;
        }
        let Some(message) = row["MESSAGE"].as_str() else {
            continue;
        };
        if !message.contains(fixed::JOURNAL_SCHEMA) {
            continue;
        }
        let boot = row["_BOOT_ID"]
            .as_str()
            .ok_or("EMPTY journal boot absent")?;
        let invocation = row["_SYSTEMD_INVOCATION_ID"]
            .as_str()
            .ok_or("EMPTY journal invocation absent")?;
        let pid = row["_PID"].as_str().ok_or("EMPTY journal PID absent")?;
        ensure(
            token(boot)
                && boots.contains(boot)
                && token(invocation)
                && pid
                    .parse::<u32>()
                    .is_ok_and(|v| v > 1 && v.to_string() == pid)
                && row["_UID"] == "0"
                && row["_TRANSPORT"] == "stdout",
            "EMPTY journal does not retain the actual normal root unit invocation",
        )?;
        let actual = (boot.to_owned(), invocation.to_owned(), pid.to_owned());
        ensure(
            identity.as_ref().is_none_or(|v| v == &actual),
            "EMPTY journal contains multiple diagnostic invocations",
        )?;
        identity = Some(actual);
        lines.push(message.to_owned());
        ensure(
            lines.len() <= fixed::JOURNAL_REPORT_LIMIT.div_ceil(fixed::JOURNAL_CHUNK_BYTES),
            "EMPTY journal exceeded its complete report bound",
        )?;
    }
    let body = fixed::journal_body(&lines)?;
    let (boot, invocation, pid) = identity.ok_or("EMPTY journal has no report invocation")?;
    let report: Value = serde_json::from_slice(&body)?;
    ensure(
        report["schema"] == fixed::SCHEMA
            && report["production_ready"] == false
            && report["original_data_migration"] == false
            && report["business_acceptance"] == false,
        "EMPTY report tried to claim production, migration or business acceptance",
    )?;
    if let Some(main_boot) = report["main"]["epoch"]["boot_id"].as_str() {
        ensure(
            main_boot.replace('-', "") == boot,
            "EMPTY Main comparison names another guest boot",
        )?;
    }
    Ok((
        body,
        json!({"boot_id":boot,"invocation_id":invocation,"pid":pid,"frame_count":lines.len(),
        "source_reported_phase":report["phase"],"source_reported_ok":report["ok"],
        "transport_comparison_only":true,"runtime_qualified":false,"production_ready":false,
        "original_data_migration":false,"business_acceptance":false}),
    ))
}

pub(super) fn collect(
    plan: &CollectPlan,
    work: &Path,
    replay: &Path,
    prepared: &Value,
    rows: &[Value],
    boots: &BTreeSet<String>,
    verified: bool,
    ordinary_shutdown: bool,
    index: &mut usize,
) -> Result<Value> {
    if !prepared["android_release"]["empty_meituan_diagnostic"].is_object() {
        return Ok(Value::Null);
    }
    let unit_path = format!("/usr/lib/systemd/system/{}", fixed::UNIT);
    let unit = dump_regular(
        plan,
        work,
        replay,
        &unit_path,
        "empty-meituan-unit",
        0o444,
        65536,
        index,
    )?;
    let bytes = include_bytes!(
        "../../../packaging/systemd/system/droidloom-empty-meituan-diagnostic.service"
    );
    let unit_unchanged = unit
        .as_ref()
        .is_some_and(|p| p.bytes == bytes.len() as u64 && p.sha256 == fs::digest(bytes));
    let manifest_pin: FilePin =
        serde_json::from_value(prepared["host_release"]["normal_host_manifest"].clone())?;
    let manifest: crate::boot_host::HostManifest =
        serde_json::from_slice(&boot_files::read_pin(&manifest_pin, 1024 * 1024)?)?;
    crate::boot_host::validate_manifest(&manifest)?;
    let expected = manifest
        .files
        .iter()
        .find(|p| p.path == "usr/bin/droidloomctl")
        .ok_or("normal host manifest omits diagnostic executable")?;
    let executable = dump_regular(
        plan,
        work,
        replay,
        fixed::PROGRAM,
        "empty-meituan-program",
        0o755,
        32 * 1024 * 1024,
        index,
    )?;
    let executable_unchanged = executable
        .as_ref()
        .is_some_and(|p| p.bytes == expected.size && p.sha256 == expected.sha256);
    let result = (|| -> Result<Value> {
        ensure(
            verified && ordinary_shutdown && unit_unchanged && executable_unchanged,
            "EMPTY journal/normal shutdown/source bytes did not all verify",
        )?;
        let (body, comparison) = frames(rows, boots)?;
        let destination = work.join("EMPTY-MEITUAN-REPORT.json");
        boot_files::write_new(&destination, &body, 0o400)?;
        Ok(json!({"report":boot_files::pin_file(&destination)?,"comparison":comparison}))
    })();
    let (complete, report, error) = match result {
        Ok(v) => (true, Some(v), None),
        Err(e) => (false, None, Some(e.to_string())),
    };
    Ok(
        json!({"complete_comparison_report":complete,"report":report,"error":error,
        "unit":unit,"unit_source_unchanged":unit_unchanged,"executable":executable,
        "executable_source_unchanged":executable_unchanged,"normal_host_manifest":manifest_pin,
        "ordinary_shutdown":ordinary_shutdown,"journal_integrity_verified":verified,
        "runtime_qualified":false,"production_ready":false,"original_data_migration":false,"business_acceptance":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_meituan_actual_report_framing_and_journal_attribution_reject_cross_invocation_and_missing_chunks()
     {
        let boot = "a".repeat(32);
        let invocation = "b".repeat(32);
        let boots = BTreeSet::from([boot.clone()]);
        let source = json!({"schema":fixed::SCHEMA,"phase":"failure","ok":false,"production_ready":false,
            "original_data_migration":false,"business_acceptance":false,"details":"long immutable comparison".repeat(300)});
        let messages = fixed::journal_lines(&source).unwrap();
        let rows=messages.iter().map(|v|json!({"_SYSTEMD_UNIT":fixed::UNIT,"_BOOT_ID":boot,
            "_SYSTEMD_INVOCATION_ID":invocation,"_PID":"42","_UID":"0","_TRANSPORT":"stdout","MESSAGE":v})).collect::<Vec<_>>();
        let (body, comparison) = frames(&rows, &boots).unwrap();
        assert_eq!(serde_json::from_slice::<Value>(&body).unwrap(), source);
        assert_eq!(comparison["runtime_qualified"], false);
        assert!(frames(&rows[1..], &boots).is_err());
        let mut crossed = rows.clone();
        crossed[1]["_SYSTEMD_INVOCATION_ID"] = "c".repeat(32).into();
        assert!(frames(&crossed, &boots).is_err());
        let mut untrusted = rows.clone();
        untrusted[0]["_UID"] = "1000".into();
        assert!(frames(&untrusted, &boots).is_err());
        assert!(frames(&rows, &BTreeSet::from(["d".repeat(32)])).is_err());
    }
}
