//! Preserve a private capture interrupted before its durable BEFORE record.
//! This classification has no directory delta and never constructs Changes.
use super::*;
use crate::cold_original_qualification::state::Phase;

struct SnapshotSource {
    pins: Value,
    bytes: Vec<u8>,
    guards: Vec<EvidenceGuard>,
    log: CommandLog,
}
impl SnapshotSource {
    fn revalidate(&self) -> Result<()> {
        for g in &self.guards {
            g.revalidate()?;
        }
        self.log.revalidate()
    }
}

fn snapshot_command_name(name: &str) -> bool {
    name.strip_prefix("dispatch-")
        .and_then(|v| v.strip_suffix("-native-snapshot"))
        .is_some_and(|v| v.len() == 4 && v.bytes().all(|b| b.is_ascii_digit()))
}

fn source_result(
    a: &OriginalQualificationAuthority,
    operation: NativeOperation,
    name: &str,
) -> Result<FilePin> {
    let original = a.journal.borrow().observation(Phase::NativeInstallIntent)?;
    match operation {
        NativeOperation::Install => {
            ensure(
                original.is_none(),
                "uncommitted capture contradicts native install intent",
            )?;
            let number = name[9..13].parse::<u16>()?;
            ensure(
                number > 0,
                "uncommitted install has no preceding native snapshot",
            )?;
            files::pin_file(
                &a.work()
                    .join("commands")
                    .join(format!("dispatch-{:04}-native-snapshot", number - 1))
                    .join("RESULT.json"),
            )
        }
        NativeOperation::Rollback => {
            let value = original.ok_or("uncommitted rollback has no original native snapshot")?;
            Ok(serde_json::from_value(value["normal_snapshot"].clone())?)
        }
    }
}

fn snapshot_source(
    a: &OriginalQualificationAuthority,
    result_pin: &FilePin,
) -> Result<SnapshotSource> {
    let dir = result_pin
        .path
        .parent()
        .ok_or("native snapshot command directory")?;
    ensure(
        dir.parent() == Some(a.work().join("commands").as_path())
            && dir
                .file_name()
                .and_then(|v| v.to_str())
                .is_some_and(snapshot_command_name)
            && result_pin
                .path
                .file_name()
                .is_some_and(|v| v == "RESULT.json"),
        "native snapshot result escaped the exact source command",
    )?;
    let result = SealedInput::open(result_pin)?;
    let rv: Value = serde_json::from_slice(&result.read()?)?;
    let input_pin = files::pin_file(&dir.join("INPUTS.json"))?;
    let input = SealedInput::open(&input_pin)?;
    let iv: Value = serde_json::from_slice(&input.read()?)?;
    let materials = actual_materials(a)?;
    ensure(
        iv["schema"] == "droidloom.original-once-fixed-command.v1"
            && iv["candidate_id"] == a.candidate_id()
            && iv["intent"] == serde_json::to_value(a.intent.pin())?
            && iv["operation"] == "native-snapshot"
            && iv["arguments"] == json!({})
            && iv["materials"] == materials,
        "native snapshot input is not this original preparation",
    )?;
    let log_pin: FilePin = serde_json::from_value(rv["command"]["log"].clone())?;
    let log = CommandLog::open(&log_pin, &dir.join("normal-command.log"))?;
    let raw = log.read()?;
    ensure(
        rv["schema"] == "droidloom.original-once-command-evidence.v1"
            && rv["input"] == serde_json::to_value(&input_pin)?
            && rv["actual"] == raw
            && rv["command"]["exit_code"] == 0
            && rv["command"]["timed_out"] == false
            && raw["schema"] == "droidloom.original-once-fixed-command-result.v1"
            && raw["candidate_id"] == a.candidate_id()
            && raw["operation"] == "native-snapshot"
            && raw["intent"] == serde_json::to_value(a.intent.pin())?,
        "native snapshot lacks its actual completed source command",
    )?;
    let release: FilePin = serde_json::from_value(materials["native_release"].clone())?;
    let release_guard = NormalSource::open(&release)?;
    let index: Value = serde_json::from_slice(&release_guard.read()?)?;
    let release_id = materials["native_release_id"]
        .as_str()
        .ok_or("native release ID")?;
    ensure(
        index["release_id"] == release_id,
        "snapshot native release differs",
    )?;
    let archives = source_archives(&release, &index)?;
    let tx = &raw["result"];
    let attempt = tx["attempt"].as_str().ok_or("native snapshot attempt")?;
    let snapshot: FilePin = serde_json::from_value(tx["snapshot"].clone())?;
    let expected = Path::new("/var/lib/droidloom-maintenance/native-transactions").join(attempt);
    ensure(
        attempt_ok(attempt, release_id)
            && tx["kind"] == "native"
            && snapshot.path == expected.join("SNAPSHOT.json")
            && tx["directory"] == expected.to_string_lossy().as_ref()
            && tx["events"].as_array().is_some_and(|v| {
                v.len() == 1
                    && v[0]["schema"] == "droidloom-normal-native-event-v1"
                    && v[0]["attempt"] == attempt
                    && v[0]["sequence"] == 1
                    && v[0]["stage"] == "snapshot-complete"
            }),
        "uncommitted capture requires the actual original snapshot, not package completion",
    )?;
    let snapshot_guard = SealedInput::open(&snapshot)?;
    let bytes = snapshot_guard.read()?;
    ensure(bytes.len() <= 32 * 1024 * 1024, "bounded native snapshot")?;
    let value: Value = serde_json::from_slice(&bytes)?;
    let root = fs::stat(&File::open("/")?)?;
    ensure(
        value["schema"] == "droidloom-normal-native-snapshot-v1"
            && value["release_id"] == release_id
            && value["closure_sha256"] == index["closure_sha256"]
            && value["root_identity"] == json!([root.dev, root.ino])
            && value["public_configs"].is_object()
            && value["private_metadata"].is_object()
            && value["all_packages"].is_object(),
        "uncommitted capture snapshot lost its complete original source",
    )?;
    let mut guards = vec![
        EvidenceGuard::Private(result),
        EvidenceGuard::Private(input),
        EvidenceGuard::Private(snapshot_guard),
        EvidenceGuard::Normal(release_guard),
    ];
    for p in &archives {
        guards.push(EvidenceGuard::Normal(NormalSource::open(p)?));
    }
    let source = SnapshotSource {
        pins: json!({"result":result_pin,"input":input_pin,"stdout":log_pin,
            "snapshot":snapshot,"native_release":release,"source_archives":archives}),
        bytes,
        guards,
        log,
    };
    source.revalidate()?;
    Ok(source)
}

fn absent_command(commands: &Path, name: &str) -> Result<()> {
    let parent = DirectoryState::capture(commands)?;
    ensure(
        !parent.state.members.contains_key(name),
        "a command directory, input or execution evidence exists for the unsealed capture",
    )?;
    parent.state.reopen()?;
    Ok(())
}

/// Only the private pre-copy/partial-copy/complete-copy states precede BEFORE.
/// The source record and every captured inode remain untouched by this reader.
fn observe_uncommitted(record: &Path, commands: &Path, name: &str, source: &[u8]) -> Result<Value> {
    ensure(
        source.len() <= 32 * 1024 * 1024 && !source.is_empty(),
        "bounded snapshot source",
    )?;
    absent_command(commands, name)?;
    let parent = DirectoryState::capture(record)?;
    ensure(
        parent.state.identity.mode & 0o7777 == 0o700
            && parent.state.attributes.is_empty()
            && parent
                .state
                .members
                .keys()
                .all(|s| s == "NATIVE-SNAPSHOT.json"),
        "unsealed capture contains an intent, result or unknown private member",
    )?;
    let path = record.join("NATIVE-SNAPSHOT.json");
    let node = observe(&path)?;
    let state = if let Some(n) = &node {
        ensure(
            n.identity.mode == 0o100400
                && n.identity.nlink == 1
                && n.attributes.is_empty()
                && n.identity.size <= source.len() as u64,
            "unsealed native snapshot is not its readonly bounded regular prefix",
        )?;
        let file = fs::Tree::open("/", 0)?.file(&fs::absolute_string(&path)?)?;
        ensure(
            fs::stat(&file)? == n.identity,
            "unsealed snapshot read fd differs",
        )?;
        let mut bytes = Vec::new();
        (&file)
            .take((source.len() + 1) as u64)
            .read_to_end(&mut bytes)?;
        ensure(
            bytes.len() <= source.len()
                && bytes == source[..bytes.len()]
                && fs::stat(&file)? == n.identity
                && observe(&path)?.as_ref() == Some(n),
            "partial snapshot is not the actual normal source prefix",
        )?;
        if bytes.len() == source.len() {
            "complete-copy-before-intent"
        } else {
            "partial-copy-before-intent"
        }
    } else {
        "directory-before-copy"
    };
    parent.state.reopen()?;
    absent_command(commands, name)?;
    Ok(json!({"directory":parent.state,"snapshot":node,"copy_state":state}))
}

fn publish_preservation(path: &Path, value: &Value) -> Result<FilePin> {
    let parent = path.parent().ok_or("preservation parent")?;
    let leaf = path
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("preservation name")?;
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_nanos();
    let pending = parent.join(format!("{leaf}.pending-{}-{nonce}", std::process::id()));
    // A torn earlier pending record is retained under its own create-only
    // name. It can neither occupy the final receipt nor block a fresh proof.
    let temporary = write_json(&pending, value)?;
    let before = observe(&pending)?.ok_or("new preservation pending disappeared")?;
    ensure(
        before.identity.mode == 0o100400 && before.attributes.is_empty(),
        "preservation pending custody",
    )?;
    let held = DirectoryState::capture(parent)?;
    rustix::fs::renameat_with(
        &held.file,
        pending.file_name().ok_or("pending name")?,
        &held.file,
        path.file_name().ok_or("receipt name")?,
        RenameFlags::NOREPLACE,
    )?;
    held.file.sync_all()?;
    let after = observe(path)?.ok_or("preservation publication disappeared")?;
    ensure(
        same_except_ctime(&before, &after) && after.sha256.as_deref() == Some(&temporary.sha256),
        "preservation publication changed its actual inode or bytes",
    )?;
    let pin = files::pin_file(path)?;
    SealedInput::open(&pin)?;
    Ok(pin)
}

/// Return a preservation pin only for an operation that provably never began.
/// The capture stays in place so command ordinals cannot be silently reused.
/// Receipt publication is outside the untouched captured directory.
pub(in crate::cold_original_qualification) fn preserve_uncommitted(
    a: &OriginalQualificationAuthority,
    operation: NativeOperation,
    name: &str,
) -> Result<Option<FilePin>> {
    a.verify_current_owner()?;
    ensure(
        command_name_ok(name, operation),
        "fixed uncommitted capture name",
    )?;
    ensure(
        name[9..13].parse::<u16>()? < 4096,
        "bounded source dispatch ordinal",
    )?;
    let record = a.work().join("native-package-parents").join(name);
    let output_root = a.work().join("native-package-uncommitted");
    let output = output_root.join(format!("{name}.json"));
    match std::fs::symlink_metadata(record.join("BEFORE.json")) {
        Ok(_) => {
            match std::fs::symlink_metadata(&output) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => return Err(e.into()),
                Ok(_) => return Err("uncommitted preservation contradicts durable BEFORE".into()),
            }
            return Ok(None);
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
        Err(e) => return Err(e.into()),
    }
    let existing = match std::fs::symlink_metadata(&output) {
        Ok(_) => Some(SealedInput::open(&files::pin_file(&output)?)?),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
        Err(e) => return Err(e.into()),
    };
    if existing.is_none() {
        let phase = a
            .journal
            .borrow()
            .phase()
            .ok_or("uncommitted capture recovery phase")?;
        ensure(
            match operation {
                NativeOperation::Install => phase == Phase::Aborting,
                NativeOperation::Rollback => phase == Phase::CellRestored,
            },
            "uncommitted capture is not the active failed preparation",
        )?;
    }
    let source = snapshot_source(a, &source_result(a, operation, name)?)?;
    let observed = observe_uncommitted(&record, &a.work().join("commands"), name, &source.bytes)?;
    let value = json!({"schema":"droidloom.original-native-uncommitted-capture.v1",
        "scope":"private-capture-only-command-not-started","candidate_id":a.candidate_id(),
        "owner_intent":a.intent.pin(),"operation":operation,"command_name":name,
        "command_path":a.work().join("commands").join(name),"normal_snapshot_source":source.pins,
        "actual_preserved_capture":observed});
    let result = if let Some(seal) = existing {
        ensure(
            serde_json::from_slice::<Value>(&seal.read()?)? == value,
            "preserved uncommitted capture changed source, generation or bytes",
        )?;
        seal.revalidate()?;
        seal.pin().clone()
    } else {
        match std::fs::symlink_metadata(&output_root) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                files::private_dir(&output_root)?;
                File::open(a.work())?.sync_all()?;
            }
            Err(e) => return Err(e.into()),
            Ok(_) => {}
        }
        let directory = DirectoryState::capture(&output_root)?;
        ensure(
            directory.state.identity.mode & 0o7777 == 0o700
                && directory.state.attributes.is_empty(),
            "uncommitted preservation directory custody",
        )?;
        publish_preservation(&output, &value)?
    };
    source.revalidate()?;
    ensure(
        observe_uncommitted(&record, &a.work().join("commands"), name, &source.bytes)? == observed,
        "uncommitted capture changed while its preservation became durable",
    )?;
    a.verify_current_owner()?;
    Ok(Some(result))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn isolated() -> Result<PathBuf> {
        ensure(
            rustix::process::geteuid().is_root(),
            "isolated root filesystem test",
        )?;
        let t = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let p = PathBuf::from(format!(
            "/var/lib/droidloom-qualification/uncommitted-capture-{}-{t}",
            std::process::id()
        ));
        files::private_dir(&p)?;
        files::private_dir(&p.join("commands"))?;
        Ok(p)
    }
    #[test]
    fn snapshot_predecessor_names_are_exact() {
        assert!(snapshot_command_name("dispatch-0017-native-snapshot"));
        for n in [
            "dispatch-1-native-snapshot",
            "dispatch-0017-native-apply",
            "dispatch-0017-native-snapshot/RESULT.json",
            "../dispatch-0017-native-snapshot",
        ] {
            assert!(!snapshot_command_name(n));
        }
    }
    #[test]
    #[ignore = "root only; independent real private capture interruption states"]
    fn actual_uncommitted_copy_states_preserve_full_generations() -> Result<()> {
        let root = isolated()?;
        let source = b"{\"normal\":\"source snapshot\"}\n";
        for (ordinal, count) in [None, Some(0), Some(8), Some(source.len())]
            .into_iter()
            .enumerate()
        {
            let name = format!("dispatch-{ordinal:04}-native-apply");
            let record = root.join(&name);
            files::private_dir(&record)?;
            if let Some(n) = count {
                files::write_new(&record.join("NATIVE-SNAPSHOT.json"), &source[..n], 0o400)?;
            }
            let before = observe_uncommitted(&record, &root.join("commands"), &name, source)?;
            // Drop all observation descriptors, reopen the actual retained
            // directory, and prove the interrupted copy is still unchanged.
            let receipt = root.join(format!("{name}.json"));
            let incomplete = root.join(format!("{name}.json.pending-interrupted"));
            files::write_new(&incomplete, b"{\"interrupted\":", 0o400)?;
            let retained = observe(&incomplete)?;
            publish_preservation(&receipt, &before)?;
            assert_eq!(
                observe(&incomplete)?,
                retained,
                "older torn private evidence must remain unchanged"
            );
            let reopened = read_json(&receipt)?;
            assert_eq!(
                observe_uncommitted(&record, &root.join("commands"), &name, source)?,
                reopened
            );
            assert_eq!(before, reopened);
            let old = root.join(format!("{name}-old"));
            std::fs::rename(&record, &old)?;
            files::private_dir(&record)?;
            if let Some(n) = count {
                files::write_new(&record.join("NATIVE-SNAPSHOT.json"), &source[..n], 0o400)?;
            }
            assert_ne!(
                observe_uncommitted(&record, &root.join("commands"), &name, source)?,
                reopened,
                "same bytes in replacement generations must not reopen the old preservation"
            );
        }
        Ok(())
    }
    #[test]
    #[ignore = "root only; actual unknown capture/command evidence counterexamples"]
    fn actual_uncommitted_capture_rejects_unknown_or_started_states() -> Result<()> {
        let root = isolated()?;
        let source = b"normal original snapshot";
        for (ordinal, case) in [
            "wrong-prefix",
            "oversize",
            "mode",
            "symlink",
            "hardlink",
            "before",
            "observation",
            "unknown",
            "empty-command",
            "input",
            "log",
            "result",
        ]
        .into_iter()
        .enumerate()
        {
            let name = format!("dispatch-{ordinal:04}-native-rollback");
            let record = root.join(&name);
            files::private_dir(&record)?;
            let p = record.join("NATIVE-SNAPSHOT.json");
            match case {
                "wrong-prefix" => files::write_new(&p, b"foreign", 0o400)?,
                "oversize" => files::write_new(&p, &[b'x'; 64], 0o400)?,
                "mode" => files::write_new(&p, source, 0o600)?,
                "symlink" => {
                    rustix::fs::symlinkat(
                        "/dev/null",
                        &File::open(&record)?,
                        "NATIVE-SNAPSHOT.json",
                    )?;
                }
                "hardlink" => {
                    files::write_new(&p, source, 0o400)?;
                    std::fs::hard_link(&p, root.join(format!("link-{ordinal}")))?;
                }
                "before" | "observation" | "unknown" => files::write_new(
                    &record.join(match case {
                        "before" => "BEFORE.json",
                        "observation" => "OBSERVATION.json",
                        _ => "other",
                    }),
                    b"evidence",
                    0o400,
                )?,
                _ => {
                    let d = root.join("commands").join(&name);
                    files::private_dir(&d)?;
                    if case != "empty-command" {
                        files::write_new(
                            &d.join(match case {
                                "input" => "INPUTS.json",
                                "log" => "normal-command.log",
                                _ => "RESULT.json",
                            }),
                            b"existing execution evidence",
                            0o400,
                        )?;
                    }
                }
            }
            assert!(
                observe_uncommitted(&record, &root.join("commands"), &name, source).is_err(),
                "{case}"
            );
        }
        Ok(())
    }
}
