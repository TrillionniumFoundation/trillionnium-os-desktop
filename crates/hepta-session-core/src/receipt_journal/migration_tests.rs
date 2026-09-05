//! Actual private files; no daemon, event replay, signing or cutover authority.
use super::*;
use persistence_tests::{Action, Armed, ID, Temp, event};
use std::collections::BTreeMap;
use std::os::unix::fs::symlink;

fn legacy(temp: &Temp) -> Vec<PathBuf> {
    let root = temp.0.join("legacy");
    fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
    let first = root.join("first");
    let second = root.join("second");
    let mut writer = ReceiptJournal::create(&first, ID, 1).unwrap();
    for state in [LifecycleState::Requested, LifecycleState::Interrupted] {
        writer.append(event("old-id", state)).unwrap();
    }
    let (_, mut writer) = writer.rotate(&second, 2).unwrap();
    for state in [LifecycleState::Requested, LifecycleState::Dispatched] {
        let mut item = event("unresolved", state);
        item.effect_class = EffectClass::PotentialExternalEffect;
        item.privacy_class = PrivacyClass::SecretRedacted;
        writer.append(item).unwrap();
    }
    drop(writer);
    vec![first, second]
}
fn snapshot(root: &Path) -> BTreeMap<String, Vec<u8>> {
    fs::read_dir(root)
        .unwrap()
        .map(|e| {
            let e = e.unwrap();
            (
                e.file_name().into_string().unwrap(),
                fs::read(e.path()).unwrap(),
            )
        })
        .collect()
}
fn copy(paths: &[PathBuf], target: &Path) -> Result<ReceiptMigrationReport, JournalError> {
    ReceiptJournal::copy_legacy_chain_to_managed(paths, ID, target)
}
fn no_destination(paths: &[PathBuf], temp: &Temp) {
    assert!(copy(paths, &temp.store()).is_err());
    assert!(!temp.store().exists());
}

#[test]
fn copy_preserves_every_byte_and_source_sidecar() {
    let temp = Temp::new();
    let paths = legacy(&temp);
    let original = snapshot(&temp.0.join("legacy"));
    let report = copy(&paths, &temp.store()).unwrap();
    assert_eq!(report.record_count, 4);
    assert_eq!(report.unresolved_receipts, 1);
    assert_eq!(report.next_sequence, 5);
    assert_eq!(report.journal_id, ID);
    assert_eq!(snapshot(&temp.0.join("legacy")), original);
    assert_eq!(report.segments.len(), 2);
    for segment in &report.segments {
        assert_eq!(
            fs::read(&segment.source).unwrap(),
            fs::read(&segment.destination).unwrap()
        );
        assert_eq!(sha256(&fs::read(&segment.source).unwrap()), segment.sha256);
        assert_ne!(
            identity(&fs::metadata(&segment.source).unwrap()),
            identity(&fs::metadata(&segment.destination).unwrap())
        );
        let meta = fs::metadata(&segment.destination).unwrap();
        assert_eq!(meta.nlink(), 1);
        assert_eq!(meta.permissions().mode() & 0o777, 0o600);
    }
    assert_eq!(
        fs::metadata(temp.store()).unwrap().permissions().mode() & 0o777,
        0o700
    );
    assert!(!temp.store().join(MIGRATION_PENDING).exists());
    let mut writer =
        ReceiptJournal::open_managed(temp.store(), ID, ManagedOpenPolicy::STRICT).unwrap();
    let recovered = writer.inspect().unwrap();
    assert_eq!(report.last_record_sha256, recovered.last_record_sha256);
    assert_eq!(
        recovered.unresolved[0].replay,
        ReplayDirective::NeverAutomatic
    );
    assert_eq!(
        recovered.records[0].event.privacy_class,
        PrivacyClass::SecretRedacted
    );
    assert_eq!(snapshot(&temp.0.join("legacy")), original);
}

#[test]
fn copied_namespace_rejects_prior_ids_and_preserves_pending_lifecycle() {
    let temp = Temp::new();
    let paths = legacy(&temp);
    assert_eq!(copy(&paths, &temp.store()).unwrap().record_count, 4);
    let mut writer =
        ReceiptJournal::open_managed(temp.store(), ID, ManagedOpenPolicy::STRICT).unwrap();
    assert!(
        writer
            .append(event("old-id", LifecycleState::Requested))
            .is_err()
    );
    assert!(
        writer
            .append(event("unresolved", LifecycleState::Requested))
            .is_err()
    );
    let mut terminal = event("unresolved", LifecycleState::Indeterminate);
    terminal.effect_class = EffectClass::PotentialExternalEffect;
    terminal.privacy_class = PrivacyClass::SecretRedacted;
    assert_eq!(writer.append(terminal).unwrap().sequence, 5);
    drop(writer);
    let mut writer =
        ReceiptJournal::open_managed(temp.store(), ID, ManagedOpenPolicy::STRICT).unwrap();
    assert!(writer.inspect().unwrap().unresolved.is_empty());
    assert_eq!(
        writer
            .append(event("new", LifecycleState::Requested))
            .unwrap()
            .sequence,
        6
    );
}

#[test]
fn empty_legacy_header_and_historical_revision_are_not_rewritten() {
    for historical in [false, true] {
        let temp = Temp::new();
        let path = temp.0.join("legacy");
        let mut writer = ReceiptJournal::create(&path, ID, 17).unwrap();
        if historical {
            let mut value = event("historical", LifecycleState::Requested);
            value.plan_revision = "2026-08-28-d5".into();
            writer.append(value).unwrap();
        }
        drop(writer);
        let bytes = fs::read(&path).unwrap();
        let result = copy(&[path], &temp.store()).unwrap();
        assert_eq!(result.record_count, u64::from(historical));
        assert_eq!(fs::read(&result.segments[0].destination).unwrap(), bytes);
    }
}

#[test]
fn source_descriptors_are_read_only_and_create_no_lease() {
    let temp = Temp::new();
    let paths = legacy(&temp);
    let before = snapshot(&temp.0.join("legacy"));
    let mut source = LegacySource::acquire(&paths, ID).unwrap();
    for segment in &mut source.pinned {
        assert!(segment.file.write_all(b"cannot-write").is_err());
    }
    drop(source);
    assert_eq!(snapshot(&temp.0.join("legacy")), before);
}

#[test]
fn rejects_active_source_writer_before_creating_destination() {
    let temp = Temp::new();
    let paths = legacy(&temp);
    let _writer = ReceiptJournal::open_chain(&paths, ID, OpenPolicy::STRICT).unwrap();
    assert!(matches!(
        copy(&paths, &temp.store()),
        Err(JournalError::WriterBusy)
    ));
    assert!(!temp.store().exists());
}

#[test]
fn incomplete_or_reordered_chain_and_wrong_identity_never_create_destination() {
    let temp = Temp::new();
    let paths = legacy(&temp);
    for selected in [
        vec![],
        vec![paths[1].clone()],
        vec![paths[1].clone(), paths[0].clone()],
        vec![paths[0].clone(), paths[0].clone()],
    ] {
        no_destination(&selected, &temp);
    }
    for id in [JournalId([0; 16]), JournalId([9; 16])] {
        assert!(ReceiptJournal::copy_legacy_chain_to_managed(&paths, id, temp.store()).is_err());
        assert!(!temp.store().exists());
    }
}

#[test]
fn torn_and_corrupt_source_is_rejected_without_repair() {
    for corrupt in [false, true] {
        let temp = Temp::new();
        let paths = legacy(&temp);
        if corrupt {
            let mut bytes = fs::read(&paths[1]).unwrap();
            bytes[150] ^= 1;
            fs::write(&paths[1], bytes).unwrap();
        } else {
            OpenOptions::new()
                .append(true)
                .open(&paths[1])
                .unwrap()
                .write_all(b"HPTREC01")
                .unwrap();
        }
        let before = snapshot(&temp.0.join("legacy"));
        no_destination(&paths, &temp);
        assert_eq!(snapshot(&temp.0.join("legacy")), before);
    }
}

#[test]
fn managed_source_is_not_accepted_as_legacy() {
    let temp = Temp::new();
    let source = temp.0.join("source-store");
    let writer = ReceiptJournal::create_managed(&source, ID, 1).unwrap();
    let path = writer.path().to_owned();
    drop(writer);
    no_destination(&[path], &temp);
}

#[test]
fn source_links_permissions_and_ancestor_links_are_rejected() {
    for mode in ["symlink", "hardlink", "permissions", "ancestor"] {
        let temp = Temp::new();
        let mut paths = legacy(&temp);
        match mode {
            "symlink" => {
                let link = temp.0.join("alias");
                symlink(&paths[0], &link).unwrap();
                paths[0] = link;
            }
            "hardlink" => {
                fs::hard_link(&paths[0], temp.0.join("alias")).unwrap();
            }
            "permissions" => {
                fs::set_permissions(&paths[0], fs::Permissions::from_mode(0o644)).unwrap();
            }
            "ancestor" => {
                symlink(temp.0.join("legacy"), temp.0.join("alias")).unwrap();
                paths[0] = temp.0.join("alias/first");
            }
            _ => unreachable!(),
        }
        no_destination(&paths, &temp);
    }
}

#[test]
fn existing_destination_file_directory_or_symlink_is_never_overwritten() {
    for kind in ["file", "directory", "symlink"] {
        let temp = Temp::new();
        let paths = legacy(&temp);
        let other = temp.0.join("other");
        fs::write(&other, b"preserve").unwrap();
        match kind {
            "file" => fs::write(temp.store(), b"preserve").unwrap(),
            "directory" => fs::create_dir(temp.store()).unwrap(),
            "symlink" => symlink(&other, temp.store()).unwrap(),
            _ => unreachable!(),
        }
        let before = fs::symlink_metadata(temp.store()).unwrap();
        assert!(copy(&paths, &temp.store()).is_err());
        assert_eq!(
            identity(&fs::symlink_metadata(temp.store()).unwrap()),
            identity(&before)
        );
        assert_eq!(fs::read(&other).unwrap(), b"preserve");
        if kind == "file" {
            assert_eq!(fs::read(temp.store()).unwrap(), b"preserve");
        }
        if kind == "directory" {
            assert!(fs::read_dir(temp.store()).unwrap().next().is_none());
        }
    }
}

#[test]
fn malformed_destination_and_infinite_source_iterator_are_bounded() {
    let temp = Temp::new();
    let paths = legacy(&temp);
    for path in [
        "relative",
        "/",
        "/tmp/../invalid",
        "/tmp//invalid",
        "/tmp/space name",
    ] {
        assert!(copy(&paths, Path::new(path)).is_err());
    }
    assert!(
        ReceiptJournal::copy_legacy_chain_to_managed(
            std::iter::repeat(&paths[0]),
            ID,
            temp.store()
        )
        .is_err()
    );
    assert!(!temp.store().exists());
}

#[test]
fn maximum_chain_copies_and_oversized_source_is_rejected_before_reading() {
    let temp = Temp::new();
    let mut paths = vec![temp.0.join("first")];
    let mut writer = ReceiptJournal::create(&paths[0], ID, 1).unwrap();
    writer
        .append(event("seed", LifecycleState::Requested))
        .unwrap();
    writer
        .append(event("seed", LifecycleState::Interrupted))
        .unwrap();
    for index in 2..=MAX_CHAIN_SEGMENTS {
        let path = temp.0.join(format!("old-{index}"));
        let (_, next) = writer.rotate(&path, index as u64).unwrap();
        writer = next;
        paths.push(path);
    }
    drop(writer);
    assert_eq!(
        copy(&paths, &temp.store()).unwrap().segments.len(),
        MAX_CHAIN_SEGMENTS
    );
    let other = temp.0.join("too-large");
    let writer = ReceiptJournal::create(&other, ID, 1).unwrap();
    drop(writer);
    OpenOptions::new()
        .write(true)
        .open(&other)
        .unwrap()
        .set_len(MAX_SEGMENT_BYTES + 1)
        .unwrap();
    let target = temp.0.join("not-created");
    assert!(copy(&[other], &target).is_err());
    assert!(!target.exists());
}

#[test]
fn revalidation_detects_same_length_source_tampering_and_path_swap() {
    for swap in [false, true] {
        let temp = Temp::new();
        let paths = legacy(&temp);
        let mut source = LegacySource::acquire(&paths, ID).unwrap();
        let mut bytes = fs::read(&paths[0]).unwrap();
        if swap {
            fs::rename(&paths[0], temp.0.join("preserved-source")).unwrap();
        } else {
            bytes[0] ^= 1;
        }
        fs::write(&paths[0], bytes).unwrap();
        fs::set_permissions(&paths[0], fs::Permissions::from_mode(0o600)).unwrap();
        assert!(source.verify_all().is_err());
    }
}

// These user-space I/O faults do not emulate device caches or physical power loss.
const CUTS: &[&str] = &[
    "migration.before_directory_create",
    "migration.after_directory_create",
    "migration_marker.before_write",
    "migration_marker.partial_write",
    "migration.after_marker_sync",
    "migration_segment_0.before_write",
    "migration_segment_0.partial_write",
    "migration_segment_0.before_sync",
    "migration_segment_0.after_sync",
    "migration_segment_1.before_write",
    "migration_segment_1.partial_write",
    "migration_segment_1.before_sync",
    "migration_segment_1.after_sync",
    "migration.before_publish",
    "migration.after_publish",
    "migration.after_directory_sync",
];

#[test]
fn injected_io_faults_preserve_sources_and_never_admit_partial_copy() {
    assert_eq!(CUTS.len(), 16);
    for &point in CUTS {
        for code in [5, 28] {
            let temp = Temp::new();
            let paths = legacy(&temp);
            let before = snapshot(&temp.0.join("legacy"));
            let armed = Armed::new(point, Action::Error(code));
            let result = copy(&paths, &temp.store());
            assert!(armed.reached(), "missed {point}");
            assert_eq!(
                result.unwrap_err().to_string(),
                map_io_error(io::Error::from_raw_os_error(code)).to_string()
            );
            drop(armed);
            assert_eq!(snapshot(&temp.0.join("legacy")), before, "{point}/{code}");
            let published = matches!(
                point,
                "migration.after_publish" | "migration.after_directory_sync"
            );
            let result =
                ReceiptJournal::open_managed(temp.store(), ID, ManagedOpenPolicy::RECOVER_CRASH);
            assert_eq!(result.is_ok(), published, "{point}/{code}");
            drop(result);
            if temp.store().exists() {
                let staged = snapshot(&temp.store());
                assert!(copy(&paths, &temp.store()).is_err(), "retry must not adopt");
                assert_eq!(snapshot(&temp.store()), staged);
                for index in 1..=2 {
                    let file = temp.store().join(segment_name(index));
                    if file.exists() {
                        assert!(ReceiptJournal::open(&file, OpenPolicy::RECOVER_CRASH).is_err());
                        assert!(
                            ReceiptJournal::open_chain([&file], ID, OpenPolicy::STRICT).is_err()
                        );
                    }
                }
            }
            println!("migration-io-cut point={point} errno={code} preserved=PASS");
        }
    }
}
