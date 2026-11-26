//! A fresh, durable restoration preimage after actual runtime retirement.
//! This private core grants no retirement authority; the only product caller
//! must hold the once owner's opaque OriginalRetirement at every write fence.
use super::*;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum RuntimeClass {
    Log,
    Cache,
    Temporary,
    UserHome,
    ServiceHome,
    OnceEvidence,
}
fn below(path: &str, prefix: &str) -> bool {
    path == prefix
        || path
            .strip_prefix(prefix)
            .is_some_and(|v| v.starts_with('/'))
}
fn runtime_class(path: &Path, candidate: &str) -> Option<RuntimeClass> {
    let path = path.to_str()?;
    if below(path, "/home/alex/work")
        || below(path, "/var/lib/droidloom-qualification")
        || below(path, "/var/lib/droidloom/users/1000/data")
    {
        return None;
    }
    for (prefix, class) in [
        ("/var/log", RuntimeClass::Log),
        ("/var/cache", RuntimeClass::Cache),
        ("/var/tmp", RuntimeClass::Temporary),
        ("/home/alex", RuntimeClass::UserHome),
    ] {
        if below(path, prefix) {
            return Some(class);
        }
    }
    // Exact original service homes, read from the preserved original passwd.
    // Package state, source archives and arbitrary /var/lib prefixes are not
    // mutable by implication. Unknown paths keep the strict applied snapshot.
    for prefix in [
        "/var/spool/lpd",
        "/var/spool/news",
        "/var/spool/uucp",
        "/var/lib/usbmux",
        "/var/lib/tpm",
        "/var/lib/misc",
        "/var/lib/sss",
        "/var/lib/fwupd",
        "/var/lib/saned",
        "/var/lib/geoclue",
        "/var/lib/gnome-remote-desktop",
        "/var/lib/colord",
        "/var/lib/gdm3",
        "/var/lib/openvpn/chroot",
        "/var/lib/hepta-runtime",
    ] {
        if below(path, prefix) {
            return Some(RuntimeClass::ServiceHome);
        }
    }
    if fs::valid_digest(candidate)
        && below(
            path,
            &format!("/var/lib/droidloom/qualification/original-once-{candidate}/runtime-evidence"),
        )
    {
        return Some(RuntimeClass::OnceEvidence);
    }
    None
}
fn admit_current(
    applied: &Snapshot,
    current: &Snapshot,
    class: Option<RuntimeClass>,
) -> Result<()> {
    ensure(
        applied.handle == current.handle && applied.attributes == current.attributes,
        "post-runtime label or an unrelated xattr no longer matches the actual applied inode",
    )?;
    if class.is_none() {
        return ensure(
            applied == current,
            "immutable label source changed during runtime",
        );
    }
    let a = &applied.identity;
    let b = &current.identity;
    ensure(
        (a.dev, a.ino, a.mode, a.uid, a.gid) == (b.dev, b.ino, b.mode, b.uid, b.gid)
            && if FileType::from_raw_mode(a.mode) == FileType::Directory {
                b.nlink >= 2
            } else {
                a.nlink == b.nlink
            },
        "mutable runtime inode lost its identity, type, authority or hardlink contract",
    )?;
    ensure(
        matches!(
            FileType::from_raw_mode(a.mode),
            FileType::RegularFile | FileType::Directory
        ),
        "only existing normal files and directories have a mutable runtime metadata contract",
    )
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CurrentPreimage {
    schema: String,
    original_preimage: FilePin,
    applied: FilePin,
    retirement: FilePin,
    class: Option<RuntimeClass>,
    current: Snapshot,
}

/// The fresh current snapshot is immutable once the first restoration write
/// may occur. Continued writes require another genuine retirement, not ignored
/// clocks or a rewritten original copy/preimage receipt.
pub(in crate::cold_original_data::labels) struct RuntimeRestoreAttempt {
    original: DurableAttempt,
    records: Records,
    current: CurrentPreimage,
    pin: FilePin,
    intent: File,
    intent_identity: Identity,
}
impl RuntimeRestoreAttempt {
    fn applied(original: &DurableAttempt) -> Result<(FilePin, Snapshot)> {
        original.validate_intent()?;
        let (_, _, bytes) = original.records.read("APPLIED.json")?;
        let value: Value = serde_json::from_slice(&bytes)?;
        let after: Snapshot = serde_json::from_value(value["after"].clone())?;
        let mut expected = original.preimage.before.attributes.clone();
        expected.insert(
            original.preimage.attribute.clone(),
            original.preimage.desired.clone(),
        );
        ensure(
            value["schema"] == "droidloom.original-label-applied.v1"
                && value["preimage"] == serde_json::to_value(&original.pin)?
                && value["before"] == serde_json::to_value(&original.preimage.before)?
                && only_ctime_changed(&original.preimage.before.identity, &after.identity)
                && after.handle == original.preimage.before.handle
                && after.attributes == expected
                && value["target_metadata_durability"]["operation"] == "syncfs"
                && value["target_metadata_durability"]["filesystem_dev"] == after.identity.dev,
            "runtime restoration lacks its actual source-bound durable label application",
        )?;
        Ok((
            FilePin {
                path: original.records.path.join("APPLIED.json"),
                bytes: bytes.len() as u64,
                sha256: fs::digest(&bytes),
            },
            after,
        ))
    }
    pub(in crate::cold_original_data::labels) fn prepare(
        original: DurableAttempt,
        records: Records,
        retirement: &FilePin,
    ) -> Result<Self> {
        ensure(
            fs::valid_digest(&retirement.sha256) && retirement.bytes > 0,
            "actual enclosing retirement evidence pin required",
        )?;
        let (applied, after) = Self::applied(&original)?;
        let current = snapshot(&original.recovery)?;
        let class = runtime_class(
            &original.preimage.logical_path,
            &original.preimage.candidate_id,
        );
        admit_current(&after, &current, class)?;
        ensure(
            current.identity.dev == records.identity.dev,
            "runtime restore preimage requires same-filesystem durability",
        )?;
        let current = CurrentPreimage {
            schema: "droidloom.current-label-restore-preimage.v1".into(),
            original_preimage: original.pin.clone(),
            applied,
            retirement: retirement.clone(),
            class,
            current,
        };
        let pin = records.publish("CURRENT-PREIMAGE.json", &current)?;
        let (intent, intent_identity, _) = records.read("CURRENT-PREIMAGE.json")?;
        let value = Self {
            original,
            records,
            current,
            pin,
            intent,
            intent_identity,
        };
        value.validate()?;
        value.classify()?;
        Ok(value)
    }
    pub(in crate::cold_original_data::labels) fn reopen(
        original: DurableAttempt,
        records: Records,
        pin: &FilePin,
    ) -> Result<Self> {
        let (intent, intent_identity, bytes) = records.read("CURRENT-PREIMAGE.json")?;
        ensure(
            pin.path == records.path.join("CURRENT-PREIMAGE.json")
                && pin.bytes == bytes.len() as u64
                && pin.sha256 == fs::digest(&bytes),
            "complete current restoration preimage differs",
        )?;
        let current: CurrentPreimage = serde_json::from_slice(&bytes)?;
        let value = Self {
            original,
            records,
            current,
            pin: pin.clone(),
            intent,
            intent_identity,
        };
        value.validate()?;
        value.classify()?;
        Ok(value)
    }
    fn validate(&self) -> Result<()> {
        self.original.validate_intent()?;
        let (_, identity, bytes) = self.records.read("CURRENT-PREIMAGE.json")?;
        let (applied, after) = Self::applied(&self.original)?;
        ensure(
            identity == self.intent_identity
                && fs::stat(&self.intent)? == identity
                && bytes.len() as u64 == self.pin.bytes
                && fs::digest(&bytes) == self.pin.sha256
                && self.current.schema == "droidloom.current-label-restore-preimage.v1"
                && serde_json::to_value(&self.current.original_preimage)?
                    == serde_json::to_value(&self.original.pin)?
                && serde_json::to_value(&self.current.applied)? == serde_json::to_value(&applied)?
                && self.current.class
                    == runtime_class(
                        &self.original.preimage.logical_path,
                        &self.original.preimage.candidate_id,
                    ),
            "held current restoration evidence or its fixed source class changed",
        )?;
        admit_current(&after, &self.current.current, self.current.class)
    }
    fn classify(&self) -> Result<(Snapshot, bool)> {
        self.validate()?;
        let actual = snapshot(&self.original.recovery)?;
        let mut restored = self.current.current.attributes.clone();
        match self
            .original
            .preimage
            .before
            .attributes
            .get(&self.original.preimage.attribute)
        {
            Some(old) => {
                restored.insert(self.original.preimage.attribute.clone(), old.clone());
            }
            None => {
                restored.remove(&self.original.preimage.attribute);
            }
        }
        let done = actual.attributes == restored;
        ensure(
            only_ctime_changed(&self.current.current.identity, &actual.identity)
                && actual.handle == self.current.current.handle
                && (done || actual.attributes == self.current.current.attributes),
            "runtime restore has an unknown target or concurrent metadata/xattr outcome",
        )?;
        Ok((actual, done))
    }
    pub(in crate::cold_original_data::labels) fn restore(
        &self,
    ) -> Result<(LabelDerivation, FilePin)> {
        let (observed, done) = self.classify()?;
        if !done {
            set(
                &self.original.recovery,
                &self.original.preimage.attribute,
                self.original
                    .preimage
                    .before
                    .attributes
                    .get(&self.original.preimage.attribute)
                    .map(Vec::as_slice),
            )?;
        }
        let (after, done) = self.classify()?;
        ensure(
            done,
            "runtime label restoration did not reach the exact original label",
        )?;
        let durability = self.records.sync_target(&self.original.recovery, &after)?;
        let output = json!({"schema":"droidloom.current-label-restored.v1","current_preimage":self.pin,
            "original_preimage":self.original.pin,"retirement":self.current.retirement,
            "before":self.current.current,"observed_before_retry":observed,
            "after":after,"target_metadata_durability":durability,
            "original_content_claimed_unchanged":self.current.class.is_none()});
        let pin = if self.records.exists("RESTORED.json")? {
            let (_, _, bytes) = self.records.read("RESTORED.json")?;
            let record: Value = serde_json::from_slice(&bytes)?;
            ensure(
                record["schema"] == output["schema"]
                    && record["current_preimage"] == output["current_preimage"]
                    && record["original_preimage"] == output["original_preimage"]
                    && record["after"] == output["after"],
                "existing runtime restoration result differs from the actual current inode",
            )?;
            FilePin {
                path: self.records.path.join("RESTORED.json"),
                bytes: bytes.len() as u64,
                sha256: fs::digest(&bytes),
            }
        } else {
            self.records.publish("RESTORED.json", &output)?
        };
        let result = LabelDerivation {
            file: self.original.recovery.try_clone()?,
            before: self.current.current.clone(),
            after,
        };
        result.revalidate()?;
        self.validate()?;
        Ok((result, pin))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    fn setup(root: &Path, path: &str) -> DurableAttempt {
        std::fs::create_dir(root.join("apply")).unwrap();
        std::fs::set_permissions(root.join("apply"), std::fs::Permissions::from_mode(0o700))
            .unwrap();
        std::fs::write(root.join("inode"), b"runtime original bytes").unwrap();
        let held = File::from(
            rustix::fs::open(
                root.join("inode"),
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        );
        let pin = FilePin {
            path: root.join("source-plan"),
            bytes: 1,
            sha256: "a".repeat(64),
        };
        let source = DurableAttempt::prepare(
            Records::open(&root.join("apply")).unwrap(),
            held,
            &"b".repeat(64),
            &pin,
            0,
            Path::new(path),
            b"candidate",
            "user.droidloom.runtime-label",
        )
        .unwrap();
        source.apply().unwrap();
        source
    }
    fn recovery(root: &Path) -> Records {
        std::fs::create_dir(root.join("restore")).unwrap();
        std::fs::set_permissions(root.join("restore"), std::fs::Permissions::from_mode(0o700))
            .unwrap();
        Records::open(&root.join("restore")).unwrap()
    }
    fn retirement(root: &Path) -> FilePin {
        FilePin {
            path: root.join("actual-retirement"),
            bytes: 1,
            sha256: "c".repeat(64),
        }
    }
    #[test]
    fn actual_runtime_append_is_preserved_while_only_our_label_is_restored() {
        let tmp = tempfile::Builder::new()
            .prefix(".p4-current-restore-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let original = setup(tmp.path(), "/var/log/owned-test");
        std::fs::OpenOptions::new()
            .append(true)
            .open(tmp.path().join("inode"))
            .unwrap()
            .write_all(b" genuine normal runtime append")
            .unwrap();
        let current = snapshot(&original.recovery).unwrap();
        let attempt =
            RuntimeRestoreAttempt::prepare(original, recovery(tmp.path()), &retirement(tmp.path()))
                .unwrap();
        let (actual, _) = attempt.restore().unwrap();
        assert!(only_ctime_changed(
            &current.identity,
            &actual.after.identity
        ));
        assert_eq!(
            actual.after.attributes.get("user.droidloom.runtime-label"),
            None
        );
        assert_eq!(
            std::fs::read(tmp.path().join("inode")).unwrap(),
            b"runtime original bytes genuine normal runtime append"
        );
    }
    #[test]
    fn immutable_or_later_unknown_metadata_and_xattrs_do_not_restore() {
        for kind in 0..3 {
            let tmp = tempfile::Builder::new()
                .prefix(".p4-current-reject-")
                .tempdir_in(std::env::current_dir().unwrap())
                .unwrap();
            let original = setup(
                tmp.path(),
                if kind == 0 {
                    "/var/lib/dpkg/status"
                } else {
                    "/home/alex/Documents/owned-test"
                },
            );
            if kind == 0 {
                std::fs::write(
                    tmp.path().join("inode"),
                    b"changed immutable package database",
                )
                .unwrap();
            }
            if kind == 1 {
                set(
                    &original.recovery,
                    "user.unrelated",
                    Some(b"unadmitted attribute change"),
                )
                .unwrap();
            }
            let result = RuntimeRestoreAttempt::prepare(
                original,
                recovery(tmp.path()),
                &retirement(tmp.path()),
            );
            if kind < 2 {
                assert!(result.is_err());
            } else {
                let attempt = result.unwrap();
                std::fs::write(
                    tmp.path().join("inode"),
                    b"concurrent post-retirement write",
                )
                .unwrap();
                assert!(attempt.restore().is_err());
                assert_eq!(
                    snapshot(&attempt.original.recovery)
                        .unwrap()
                        .attributes
                        .get("user.droidloom.runtime-label"),
                    Some(&b"candidate".to_vec())
                );
            }
        }
    }
}
