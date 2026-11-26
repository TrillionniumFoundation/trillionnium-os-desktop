//! A complete read-only original-root label plan from the actual normal host
//! package and matcher. No deserialized plan grants label mutation authority.
use super::{
    Snapshot,
    scope::{Entry, Inventory, RootScope},
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    boot_runtime::LabelTools,
    ensure, fs,
    model::Identity,
};
use rustix::fs::FileType;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::Seek,
    path::{Path, PathBuf},
};

const QUALIFICATION: &str = "/var/lib/droidloom-qualification";
const MATCHER_MAX_PATHS: usize = 512;
const MATCHER_ARG_BYTES: usize = 160 * 1024;
fn matcher_batches(
    paths: &[String],
    prefix: &[String],
    program: &str,
) -> Result<Vec<std::ops::Range<usize>>> {
    let base = prefix.iter().map(|v| v.len() + 1).sum::<usize>() + program.len() + 1;
    ensure(
        base < MATCHER_ARG_BYTES,
        "normal matcher fixed argv exceeds its byte bound",
    )?;
    let mut result = Vec::new();
    let mut start = 0;
    let mut bytes = base;
    for (index, path) in paths.iter().enumerate() {
        ensure(
            Path::new(path).is_absolute()
                && !path.as_bytes().contains(&0)
                && base + path.len() + 1 <= MATCHER_ARG_BYTES,
            "one normal matcher pathname exceeds the exact argv bound",
        )?;
        if index - start == MATCHER_MAX_PATHS || bytes + path.len() + 1 > MATCHER_ARG_BYTES {
            result.push(start..index);
            start = index;
            bytes = base;
        }
        bytes += path.len() + 1;
    }
    if start < paths.len() {
        result.push(start..paths.len());
    }
    Ok(result)
}

const TOOLS: [(&str, u64, &str, u32); 3] = [
    (
        "setfiles",
        22920,
        "02597f1eceaa93a877ab8dd2a5fd0dbbd2d5dfdba8481e5421bfb0834783f5a5",
        0o500,
    ),
    (
        "matchpathcon",
        14728,
        "48cdccc40775e3db029b1d20af97f37e13a350d894b86150993cfc71d10ca51a",
        0o500,
    ),
    (
        "libsepol.so.2",
        941928,
        "d96adef8761310b409df7280f0f92aa3083b5eb6b177f6718d7bcdb2b0e64365",
        0o444,
    ),
];
struct Guard {
    pin: FilePin,
    file: File,
    identity: Identity,
    #[cfg(test)]
    hashed_bytes: std::cell::Cell<u64>,
}
impl Guard {
    fn open(pin: &FilePin) -> Result<Self> {
        let tree = fs::Tree::open("/", 0)?;
        tree.parent(&fs::absolute_string(&pin.path)?)?;
        let (file, identity) = files::open_pin(pin)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode & 0o6022 == 0,
            "normal label input has lost root custody",
        )?;
        ensure(
            fs::xattrs(&file)?.is_empty(),
            "normal label input has ACL or capability",
        )?;
        let result = Self {
            pin: pin.clone(),
            file,
            identity,
            #[cfg(test)]
            hashed_bytes: std::cell::Cell::new(0),
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> Result<()> {
        self.revalidate_custody()?;
        let mut file = &self.file;
        file.rewind()?;
        #[cfg(test)]
        self.hashed_bytes
            .set(self.hashed_bytes.get() + self.pin.bytes);
        ensure(
            fs::stat(&self.file)? == self.identity
                && fs::hash(&self.file)? == self.pin.sha256
                && fs::stat(&self.file)? == self.identity,
            "held normal label source was changed or replaced",
        )?;
        self.revalidate_custody()
    }
    fn revalidate_custody(&self) -> Result<()> {
        ensure(
            fs::stat(&self.file)? == self.identity
                && fs::xattrs(&self.file)?.is_empty()
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.pin.path)?)?
                    == self.identity
                && fs::stat(&self.file)? == self.identity,
            "held normal label source custody, metadata or attributes changed",
        )
    }
}
fn pin(path: &Path) -> Result<FilePin> {
    let pin = files::pin_file(path)?;
    Guard::open(&pin)?;
    Ok(pin)
}
pub(super) fn save(path: &Path, value: &impl Serialize) -> Result<FilePin> {
    let body = serde_json::to_vec(value)?;
    ensure(
        body.len() <= 512 * 1024 * 1024,
        "bounded complete original label plan required",
    )?;
    files::write_new(path, &body, 0o400)?;
    let file = File::open(path)?;
    file.sync_all()?;
    File::open(path.parent().ok_or("label plan parent missing")?)?.sync_all()?;
    pin(path)
}
fn source_work(path: &Path) -> Result<()> {
    let name = path
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("label source work name missing")?;
    ensure(
        path.parent() == Some(Path::new(QUALIFICATION))
            && name.starts_with("original-initramfs-label-")
            && name.len() <= 80
            && name
                .bytes()
                .all(|v| v.is_ascii_lowercase() || v.is_ascii_digit() || v == b'-'),
        "original label sources require a create-only protected qualification work",
    )
}
fn raw_context(line: &str) -> Result<Vec<u8>> {
    ensure(
        line.starts_with("u:object_r:")
            && line.ends_with(":s0")
            && line.len() <= 4095
            && line
                .bytes()
                .all(|v| v.is_ascii_alphanumeric() || b"_:".contains(&v))
            && line.split(':').count() == 4,
        "normal matcher did not return one canonical Linux inode context",
    )?;
    let kind = line.split(':').nth(2).ok_or("Linux label type missing")?;
    ensure(
        !kind.is_empty() && kind.bytes().all(|v| v.is_ascii_alphanumeric() || v == b'_'),
        "canonical nonempty Linux label type required",
    )?;
    let mut raw = line.as_bytes().to_vec();
    raw.push(0);
    Ok(raw)
}

// Kept opaque and live. It can be retained by the sealed once owner across its
// normal package transaction; creating this source object never applies labels.
pub(crate) struct OriginalLabelSources {
    report: Value,
    source_record: FilePin,
    work: PathBuf,
    guards: Vec<Guard>,
    matcher: FilePin,
    contexts: FilePin,
    policy: FilePin,
    environment: BTreeMap<String, String>,
}
fn state_archive(report: &Value, package: &str) -> Result<FilePin> {
    let selected = report["normal_materials"]["packages"]
        .as_array()
        .ok_or("normal package source roster missing")?
        .iter()
        .filter(|row| row["name"] == package)
        .collect::<Vec<_>>();
    ensure(
        selected.len() == 1,
        "normal systemd state unit package is not uniquely admitted",
    )?;
    Ok(serde_json::from_value(selected[0]["package"].clone())?)
}
fn admit_service_units(
    work: &Path,
    report: &Value,
    extractor: &FilePin,
    guards: &mut Vec<Guard>,
) -> Result<Value> {
    let root = work.join("normal-native-state-payload");
    files::private_dir(&root)?;
    let mut commands = BTreeMap::new();
    for name in ["systemd", "systemd-timesyncd"] {
        let archive = state_archive(report, name)?;
        guards.push(Guard::open(&archive)?);
        let destination = root.join(name);
        files::private_dir(&destination)?;
        let command = files::run_logged(
            work,
            &format!("normal-state-unit-{name}"),
            &fs::absolute_string(&extractor.path)?,
            &[
                "--extract".into(),
                fs::absolute_string(&archive.path)?,
                fs::absolute_string(&destination)?,
            ],
            180,
        )?;
        commands.insert(name, command);
    }
    let mut rows = Vec::new();
    for unit in super::service_state::UNITS {
        let source = pin(&root
            .join(unit.package)
            .join("usr/lib/systemd/system")
            .join(unit.name))?;
        ensure(
            source.bytes == unit.bytes && source.sha256 == unit.sha256,
            "normal systemd unit no longer matches its exact source-owned state contract",
        )?;
        guards.push(Guard::open(&source)?);
        rows.push(
            json!({"unit":unit.name,"normal_archive":state_archive(report,unit.package)?,
            "source":source,"state":unit.state}),
        );
    }
    Ok(
        json!({"schema":"droidloom.normal-systemd-label-state-contract.v1","units":rows,
        "normal_extracts":commands,"random_seed_source_sha256":super::service_state::RANDOM_SEED_SOURCE,
        "timesync_source_sha256":super::service_state::TIMESYNC_SOURCE}),
    )
}
fn reopen_service_units(
    work: &Path,
    report: &Value,
    value: &Value,
    guards: &mut Vec<Guard>,
) -> Result<()> {
    ensure(
        value["schema"] == "droidloom.normal-systemd-label-state-contract.v1"
            && value["random_seed_source_sha256"] == super::service_state::RANDOM_SEED_SOURCE
            && value["timesync_source_sha256"] == super::service_state::TIMESYNC_SOURCE,
        "preserved normal systemd state contract differs",
    )?;
    let rows = value["units"]
        .as_array()
        .ok_or("normal systemd state unit proofs missing")?;
    ensure(
        rows.len() == super::service_state::UNITS.len(),
        "normal systemd state unit count differs",
    )?;
    for (row, unit) in rows.iter().zip(super::service_state::UNITS) {
        let source: FilePin = serde_json::from_value(row["source"].clone())?;
        ensure(
            row["unit"] == unit.name
                && row["state"] == unit.state
                && row["normal_archive"]
                    == serde_json::to_value(state_archive(report, unit.package)?)?
                && source.path
                    == work
                        .join("normal-native-state-payload")
                        .join(unit.package)
                        .join("usr/lib/systemd/system")
                        .join(unit.name)
                && source.bytes == unit.bytes
                && source.sha256 == unit.sha256,
            "preserved normal state unit no longer belongs to the admitted normal package",
        )?;
        guards.push(Guard::open(&source)?);
    }
    Ok(())
}
impl OriginalLabelSources {
    pub(crate) fn source_pin(&self) -> &FilePin {
        &self.source_record
    }
    pub(crate) fn fresh_initramfs_report(&self) -> &Value {
        &self.report
    }

    pub(crate) fn admit(prepared: &FilePin, tools: &LabelTools, work: &Path) -> Result<Self> {
        source_work(work)?;
        let report =
            crate::cold_original_initramfs::verify_prepared_original_initramfs(prepared, work)?;
        let source_record = pin(&work.join("ORIGINAL-INITRAMFS-READBACK.json"))?;
        let package_rows = report["normal_materials"]["packages"]
            .as_array()
            .ok_or("admitted complete packages missing")?;
        let selected = package_rows
            .iter()
            .filter(|p| p["role"] == "host")
            .collect::<Vec<_>>();
        ensure(
            selected.len() == 1,
            "one normally admitted host package is required for labels",
        )?;
        let host: FilePin = serde_json::from_value(selected[0]["package"].clone())?;
        let mut guards = vec![Guard::open(&source_record)?, Guard::open(&host)?];
        let extract_tool = pin(Path::new("/usr/bin/dpkg-deb"))?;
        // This original host executable is legitimately labeled later. Its
        // extraction-window custody ends before the full-root label phase;
        // only immutable qualification sources remain in the long-lived set.
        let extract_guard = Guard::open(&extract_tool)?;
        let host_root = work.join("normal-host-payload");
        files::private_dir(&host_root)?;
        let extract = files::run_logged(
            work,
            "normal-label-host-package-extract",
            &fs::absolute_string(&extract_tool.path)?,
            &[
                "--extract".into(),
                fs::absolute_string(&host.path)?,
                fs::absolute_string(&host_root)?,
            ],
            180,
        )?;
        let contexts = pin(&host_root.join("etc/selinux/droidloom/contexts/files/file_contexts"))?;
        let policy =
            pin(&host_root.join("usr/lib/droidloom/production/current/board-policy/joint.policy"))?;
        guards.push(Guard::open(&contexts)?);
        guards.push(Guard::open(&policy)?);
        let tool_root = work.join("original-label-tools");
        files::private_dir(&tool_root)?;
        let mut tool_pins = Vec::new();
        for ((name, bytes, digest, mode), source) in TOOLS.iter().zip([
            &tools.setfiles,
            &tools.matchpathcon,
            &tools.producer_libsepol,
        ]) {
            ensure(
                source.bytes == *bytes && source.sha256 == *digest,
                "original label matcher/source library is outside its fixed normal producer",
            )?;
            guards.push(Guard::open(source)?);
            let destination = tool_root.join(name);
            files::copy_pin(source, &destination, *mode)?;
            let pinned = pin(&destination)?;
            guards.push(Guard::open(&pinned)?);
            tool_pins.push(pinned);
        }
        let environment =
            BTreeMap::from([("LD_LIBRARY_PATH".into(), fs::absolute_string(&tool_root)?)]);
        let empty = work.join("empty-policy-validation-root");
        files::private_dir(&empty)?;
        // -n is mandatory: normal setfiles validates all contexts against the
        // actual selected policy, and never labels even this disposable root.
        let validation = files::run_logged_env(
            work,
            "normal-label-context-policy-check",
            &fs::absolute_string(&tool_root.join("setfiles"))?,
            &[
                "-n".into(),
                "-F".into(),
                "-E".into(),
                "-m".into(),
                "-r".into(),
                fs::absolute_string(&empty)?,
                "-c".into(),
                fs::absolute_string(&policy.path)?,
                fs::absolute_string(&contexts.path)?,
                fs::absolute_string(&empty)?,
            ],
            60,
            &environment,
        )?;
        let normal_service_state = admit_service_units(work, &report, &extract_tool, &mut guards)?;
        for guard in &guards {
            guard.revalidate()?;
        }
        extract_guard.revalidate()?;
        let source = save(
            &work.join("ORIGINAL-LABEL-SOURCES.json"),
            &json!({"schema":"droidloom.original-label-sources.v1",
            "fresh_normal_initramfs_readback":source_record,"host_package":host,"host_extract":extract,
            "normal_extractor":{"source":extract_tool,"identity":extract_guard.identity},
            "contexts":contexts,"joint_policy":policy,"normal_label_tools":tool_pins,"context_policy_validation":validation,
            "host_source_commit":report["host_source_commit"],"host_source_tree":report["host_source_tree"],
            "normal_materials":report["normal_materials"],"normal_service_state":normal_service_state,
            "physical_labels_applied":false}),
        )?;
        guards.push(Guard::open(&source)?);
        let matcher = tool_pins[1].clone();
        Ok(Self {
            report,
            source_record: source,
            work: work.to_owned(),
            guards,
            matcher,
            contexts,
            policy,
            environment,
        })
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        for guard in &self.guards {
            guard.revalidate()?;
        }
        Ok(())
    }
    /// Only the once owner's live, bounded label window may substitute this
    /// check for a full rehash between its two complete source readbacks.
    pub(crate) fn revalidate_custody(&self) -> Result<()> {
        for guard in &self.guards {
            guard.revalidate_custody()?;
        }
        Ok(())
    }
    pub(super) fn lookup_entries(
        &self,
        entries: &[Entry],
        work: &Path,
    ) -> Result<(Vec<Vec<u8>>, FilePin)> {
        self.revalidate()?;
        let mut groups: BTreeMap<&str, Vec<usize>> = BTreeMap::new();
        for (index, entry) in entries.iter().enumerate() {
            groups.entry(&entry.matcher_type).or_default().push(index);
        }
        let mut labels = vec![Vec::new(); entries.len()];
        let mut commands = Vec::new();
        let program = fs::absolute_string(&self.matcher.path)?;
        for (kind, indices) in groups {
            let prefix = vec![
                "-N".into(),
                "-n".into(),
                "-m".into(),
                kind.into(),
                "-f".into(),
                fs::absolute_string(&self.contexts.path)?,
            ];
            let paths = indices
                .iter()
                .map(|i| fs::absolute_string(&entries[*i].path))
                .collect::<Result<Vec<_>>>()?;
            for (batch, range) in matcher_batches(&paths, &prefix, &program)?
                .into_iter()
                .enumerate()
            {
                let mut args = prefix.clone();
                args.extend_from_slice(&paths[range.clone()]);
                let chunk = &indices[range];
                let command = files::run_logged_env(
                    work,
                    &format!("normal-contexts-{kind}-{batch:06}"),
                    &program,
                    &args,
                    30,
                    &self.environment,
                )?;
                // raw_context permits at most 4096 bytes per row. Preserve a
                // bounded complete result for every supplied pathname.
                let limit = ((chunk.len() + 1) * 4097) as u64;
                let log = String::from_utf8(files::read_pin(&command.log, limit)?)?;
                let rows = log.lines().collect::<Vec<_>>();
                ensure(
                    rows.len() == chunk.len(),
                    "normal matcher returned missing/ambiguous contexts",
                )?;
                for (index, row) in chunk.iter().zip(rows) {
                    labels[*index] = raw_context(row)?;
                }
                commands.push(command);
            }
        }
        ensure(
            labels.iter().all(|v| !v.is_empty()),
            "complete original root label coverage is required",
        )?;
        self.revalidate()?;
        Ok((
            labels,
            save(&work.join("NORMAL-CONTEXT-LOOKUPS.json"), &commands)?,
        ))
    }
    pub(crate) fn inspect(&self, cold_clone: &FilePin) -> Result<Value> {
        self.revalidate()?;
        let scope = RootScope::original(cold_clone)?;
        let inventory = scope.collect()?;
        let matched = self.work.join("root-context-lookups");
        files::private_dir(&matched)?;
        let (labels, commands) = self.lookup_entries(&inventory.entries, &matched)?;
        verify_hardlink_labels(
            &inventory
                .entries
                .iter()
                .map(|e| (&e.snapshot, e.path.as_path()))
                .collect::<Vec<_>>(),
            &labels,
        )?;
        self.revalidate()?;
        let final_readback = scope.verify_inventory(&inventory)?;
        let rows = inventory
            .entries
            .iter()
            .zip(&labels)
            .map(|(entry, label)| {
                json!({"path":entry.path,"before":entry.snapshot,
            "expected_selinux":label,"matcher_type":entry.matcher_type})
            })
            .collect::<Vec<_>>();
        let complete = save(
            &self.work.join("ORIGINAL-ROOT-LABEL-PLAN.json"),
            &json!({
            "schema":"droidloom.original-root-label-plan.v1","normal_sources":self.source_record,
            "root_uuid":inventory.root_uuid,"root_identity":inventory.root_identity,"root_handle":inventory.root_handle,
            "scope":inventory,"matched_entries":rows,"actual_lookup_commands":commands,"complete_final_readback":final_readback,
            "normal_materials":self.report["normal_materials"],"policy":self.policy,"contexts":self.contexts,
            "read_only_inspection":true,"physical_labels_applied":false,"physical_boot_authorized":false,
            "original_image_bodies_read":false,"home_file_bodies_read":false}),
        )?;
        Ok(
            json!({"plan":complete,"entries":labels.len(),"normal_sources":self.source_record,
            "physical_labels_applied":false,"physical_boot_authorized":false}),
        )
    }
}
pub(super) fn verify_hardlink_labels(
    entries: &[(&Snapshot, &Path)],
    labels: &[Vec<u8>],
) -> Result<()> {
    ensure(
        entries.len() == labels.len(),
        "complete label/member association required",
    )?;
    let mut groups: BTreeMap<(u64, u64), Vec<usize>> = BTreeMap::new();
    let mut paths = BTreeSet::new();
    for (index, (snapshot, path)) in entries.iter().enumerate() {
        ensure(paths.insert(*path), "duplicate original label pathname")?;
        if FileType::from_raw_mode(snapshot.identity.mode) != FileType::Directory {
            groups
                .entry((snapshot.identity.dev, snapshot.identity.ino))
                .or_default()
                .push(index);
        }
    }
    for indices in groups.values() {
        let first = indices[0];
        let source = entries[first].0;
        ensure(
            indices.len() as u64 == source.identity.nlink,
            "an included inode has an uninspected hardlink, potentially inside an excluded tree",
        )?;
        for index in indices {
            ensure(
                entries[*index].0 == source && labels[*index] == labels[first],
                "hardlink aliases require the same full preimage and source context",
            )?;
        }
    }
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InspectionPlan {
    schema: String,
    work_directory: PathBuf,
    prepared_initramfs: FilePin,
    cold_clone: FilePin,
    label_tools: LabelTools,
}
pub(crate) fn inspect_files(path: &Path, expected: &str) -> Result<()> {
    ensure(
        fs::valid_digest(expected),
        "complete original label inspection plan hash required",
    )?;
    let input = pin(path)?;
    ensure(
        input.sha256 == expected,
        "original label inspection input hash differs",
    )?;
    let plan: InspectionPlan = serde_json::from_slice(&files::read_pin(&input, 1024 * 1024)?)?;
    ensure(
        plan.schema == "droidloom.original-label-inspection-plan.v1",
        "original label inspection schema differs",
    )?;
    let source = OriginalLabelSources::admit(
        &plan.prepared_initramfs,
        &plan.label_tools,
        &plan.work_directory,
    )?;
    let result = source.inspect(&plan.cold_clone)?;
    Guard::open(&input)?;
    println!("{result}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_matcher_batches_preserve_order_and_both_resource_bounds() {
        let prefix = vec![
            "-N".into(),
            "-n".into(),
            "-m".into(),
            "file".into(),
            "-f".into(),
            "/normal/file_contexts".into(),
        ];
        let program = "/normal/matchpathcon";
        for paths in [
            (0..100_000)
                .map(|i| format!("/usr/share/normal/{i:06}"))
                .collect::<Vec<_>>(),
            (0..2000)
                .map(|i| format!("/{i:04}/{}", "a".repeat(4000)))
                .collect(),
        ] {
            let ranges = matcher_batches(&paths, &prefix, program).unwrap();
            let mut seen = Vec::new();
            for range in &ranges {
                assert!(!range.is_empty() && range.len() <= MATCHER_MAX_PATHS);
                let bytes = prefix.iter().map(|v| v.len() + 1).sum::<usize>()
                    + program.len()
                    + 1
                    + paths[range.clone()]
                        .iter()
                        .map(|v| v.len() + 1)
                        .sum::<usize>();
                assert!(bytes <= MATCHER_ARG_BYTES);
                seen.extend(range.clone());
            }
            assert_eq!(seen, (0..paths.len()).collect::<Vec<_>>());
            if paths.len() == 100_000 {
                assert_eq!(ranges.len(), 196);
            }
        }
        assert!(
            matcher_batches(
                &[format!("/{}", "a".repeat(MATCHER_ARG_BYTES))],
                &prefix,
                program
            )
            .is_err()
        );
        assert!(matcher_batches(&["/path\0other".into()], &prefix, program).is_err());
        assert!(matcher_batches(&["relative".into()], &prefix, program).is_err());
        assert!(matcher_batches(&[], &prefix, program).unwrap().is_empty());
    }
    #[test]
    fn representative_source_custody_does_not_reread_archive_bodies() {
        // A real fixed root-owned executable is read, never changed. The test
        // counts actual SHA input bytes rather than substituting a mock guard.
        let actual = std::fs::canonicalize("/usr/bin/true").unwrap();
        let source = files::pin_file(&actual).unwrap();
        let guard = Guard::open(&source).unwrap();
        let before = guard.hashed_bytes.get();
        for _ in 0..100_000 {
            guard.revalidate_custody().unwrap();
        }
        assert_eq!(guard.hashed_bytes.get(), before);
        guard.revalidate().unwrap();
        assert_eq!(guard.hashed_bytes.get(), before + source.bytes);
        println!(
            "actual source custody: steps=100000 loop_hashed_bytes=0 final_full_hash_bytes={}",
            source.bytes
        );
    }
    #[test]
    fn raw_matcher_contexts_cannot_carry_an_empty_or_ambiguous_label() {
        assert_eq!(
            raw_context("u:object_r:p4_linux_product_store_t:s0")
                .unwrap()
                .last(),
            Some(&0)
        );
        for value in [
            "<<none>>",
            "u:object_r:t:s0\nother",
            "u:object_r:t:s0\0",
            "u:object_r:t:s0:c1",
            "",
            "system_u:object_r:t:s0",
        ] {
            assert!(raw_context(value).is_err());
        }
    }
    #[test]
    fn original_label_work_cannot_target_evidence_or_a_generic_caller_directory() {
        assert!(
            source_work(Path::new(
                "/var/lib/droidloom-qualification/original-initramfs-label-a1"
            ))
            .is_ok()
        );
        for path in [
            "/home/alex/work/original-initramfs-label-a1",
            "/var/lib/droidloom-qualification/../original-initramfs-label-a1",
            "/var/lib/droidloom-qualification/original-initramfs-other-a1",
        ] {
            assert!(source_work(Path::new(path)).is_err());
        }
    }
    #[test]
    fn actual_hardlinks_need_every_alias_and_identical_source_labels() {
        let area = tempfile::Builder::new()
            .prefix(".p4-alias-label-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let one = area.path().join("one");
        let two = area.path().join("two");
        std::fs::write(&one, b"public test inode").unwrap();
        std::fs::hard_link(&one, &two).unwrap();
        let held = File::from(
            rustix::fs::open(
                &one,
                rustix::fs::OFlags::PATH
                    | rustix::fs::OFlags::NOFOLLOW
                    | rustix::fs::OFlags::CLOEXEC,
                rustix::fs::Mode::empty(),
            )
            .unwrap(),
        );
        let before = super::super::snapshot(&held).unwrap();
        let label = raw_context("u:object_r:p4_linux_native_data_t:s0").unwrap();
        assert!(verify_hardlink_labels(&[(&before, one.as_path())], &[label.clone()]).is_err());
        verify_hardlink_labels(
            &[(&before, one.as_path()), (&before, two.as_path())],
            &[label.clone(), label.clone()],
        )
        .unwrap();
        assert!(
            verify_hardlink_labels(
                &[(&before, one.as_path()), (&before, two.as_path())],
                &[
                    label,
                    raw_context("u:object_r:p4_linux_auth_data_t:s0").unwrap()
                ]
            )
            .is_err()
        );
    }
}

/// Separate read-only custody of the exact source chain selected *before* the
/// original transaction. It cannot be passed to label preparation or apply,
/// cannot manufacture OriginalLabelSources, and never says the old original
/// dpkg status describes the returned candidate package database.
pub(crate) struct OriginalLabelRestoreSources {
    source_record: FilePin,
    historical_readback: Value,
    guards: Vec<Guard>,
}
impl OriginalLabelRestoreSources {
    pub(crate) fn source_pin(&self) -> &FilePin {
        &self.source_record
    }
    pub(crate) fn historical_initramfs_readback(&self) -> &Value {
        &self.historical_readback
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        for guard in &self.guards {
            guard.revalidate()?;
        }
        Ok(())
    }
    pub(crate) fn revalidate_custody(&self) -> Result<()> {
        for guard in &self.guards {
            guard.revalidate_custody()?;
        }
        Ok(())
    }
    pub(crate) fn reopen(source_record: &FilePin) -> Result<Self> {
        // These observations prove the real returned original environment,
        // without comparing its current dpkg bytes with the historical source.
        crate::cold_original_initramfs::original_context()?;
        let work = source_record
            .path
            .parent()
            .ok_or("original label source parent absent")?;
        source_work(work)?;
        ensure(
            source_record.path == work.join("ORIGINAL-LABEL-SOURCES.json"),
            "restoration requires the exact preserved source factory record",
        )?;
        let mut guards = vec![Guard::open(source_record)?];
        let source: Value =
            serde_json::from_slice(&files::read_pin(source_record, 16 * 1024 * 1024)?)?;
        ensure(
            source["schema"] == "droidloom.original-label-sources.v1",
            "preserved normal label source schema differs",
        )?;
        let readback: FilePin =
            serde_json::from_value(source["fresh_normal_initramfs_readback"].clone())?;
        ensure(
            readback.path == work.join("ORIGINAL-INITRAMFS-READBACK.json"),
            "historical normal admission is outside the source factory's actual work",
        )?;
        guards.push(Guard::open(&readback)?);
        let historical: Value =
            serde_json::from_slice(&files::read_pin(&readback, 16 * 1024 * 1024)?)?;
        ensure(
            historical["schema"] == "droidloom.original-initramfs-readback.v1"
                && source["normal_materials"] == historical["normal_materials"]
                && source["host_source_commit"] == historical["host_source_commit"]
                && source["host_source_tree"] == historical["host_source_tree"],
            "restoration source chain differs from the actual earlier normal admission",
        )?;
        crate::cold_original_initramfs::verify_archived_normal_materials(
            &historical["normal_materials"],
        )?;
        // Only preserved qualification objects become long-lived guards. Old
        // original_host/dpkg/account pins remain historical facts, never a
        // claim about today's returned original-machine state.
        for field in [
            "source_prepared",
            "producer_input",
            "producer_stage",
            "actual_private_build",
            "initrd",
        ] {
            let pin: FilePin = serde_json::from_value(historical[field].clone())?;
            ensure(
                pin.path.starts_with(QUALIFICATION),
                "restoration proof left the protected qualification tree",
            )?;
            guards.push(Guard::open(&pin)?);
        }
        let prepared_pin: FilePin = serde_json::from_value(historical["source_prepared"].clone())?;
        let prepared: Value =
            serde_json::from_slice(&files::read_pin(&prepared_pin, 2 * 1024 * 1024)?)?;
        ensure(
            prepared["schema"] == "droidloom.original-host-initramfs-prepared.v1"
                && prepared["input"] == historical["producer_input"]
                && prepared["actual_private_build"] == historical["actual_private_build"]
                && prepared["initrd"] == historical["initrd"],
            "preserved source and normal producer references no longer agree",
        )?;
        for field in ["public_release", "native_release"] {
            let pin: FilePin =
                serde_json::from_value(historical["normal_materials"][field].clone())?;
            ensure(
                pin.path.starts_with(QUALIFICATION),
                "normal release source left protected qualification custody",
            )?;
            guards.push(Guard::open(&pin)?);
        }
        for package in historical["normal_materials"]["packages"]
            .as_array()
            .ok_or("normal archive roster missing")?
        {
            let pin: FilePin = serde_json::from_value(package["package"].clone())?;
            ensure(
                pin.path.starts_with(QUALIFICATION),
                "normal package archive left protected qualification custody",
            )?;
            guards.push(Guard::open(&pin)?);
        }
        let host: FilePin = serde_json::from_value(source["host_package"].clone())?;
        let selected = historical["normal_materials"]["packages"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|row| row["role"] == "host" && row["package"] == source["host_package"])
            .count();
        ensure(
            selected == 1,
            "label source no longer identifies the unique admitted normal host archive",
        )?;
        guards.push(Guard::open(&host)?);
        for (field, relative) in [
            (
                "contexts",
                "etc/selinux/droidloom/contexts/files/file_contexts",
            ),
            (
                "joint_policy",
                "usr/lib/droidloom/production/current/board-policy/joint.policy",
            ),
        ] {
            let pin: FilePin = serde_json::from_value(source[field].clone())?;
            ensure(
                pin.path == work.join("normal-host-payload").join(relative),
                "preserved normal FC/policy source location differs",
            )?;
            guards.push(Guard::open(&pin)?);
        }
        let tools = source["normal_label_tools"]
            .as_array()
            .ok_or("normal label tool source roster missing")?;
        ensure(
            tools.len() == TOOLS.len(),
            "normal label tool count differs",
        )?;
        for (value, (name, bytes, sha, mode)) in tools.iter().zip(TOOLS) {
            let pin: FilePin = serde_json::from_value(value.clone())?;
            ensure(
                pin.path == work.join("original-label-tools").join(name)
                    && pin.bytes == bytes
                    && pin.sha256 == sha,
                "preserved normal matcher/library source differs",
            )?;
            let guard = Guard::open(&pin)?;
            ensure(
                guard.identity.mode & 0o7777 == mode,
                "preserved normal label tool mode differs",
            )?;
            guards.push(guard);
        }
        reopen_service_units(
            work,
            &historical,
            &source["normal_service_state"],
            &mut guards,
        )?;
        let result = Self {
            source_record: source_record.clone(),
            historical_readback: historical,
            guards,
        };
        result.revalidate()?;
        Ok(result)
    }
}
