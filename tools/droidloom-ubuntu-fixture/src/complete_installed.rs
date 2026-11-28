//! Installed roots require a complete baseline clone and actual normal transactions.
use super::*;
use crate::{
    boot_files::{self, FilePin},
    boot_packages::Member,
    boot_systemd_candidate::dependencies::{self, Fields, control, field},
};
const ADMISSION_SCHEMA: &str = "droidloom.complete-ubuntu-installed-admission.v1";
const RELEASE_SCHEMA: &str = "droidloom.complete-ubuntu-native-release.v1";
const ARCHIVE_LIMIT: u64 = 512 * 1024 * 1024;
const QUERY_FORMAT: &str = concat!(
    "-f=$",
    "{binary:Package}\t$",
    "{Version}\t$",
    "{Architecture}\t$",
    "{db:Status-Abbrev}\n"
);
const SYSTEMD: [&str; 10] = [
    "libnss-systemd",
    "libpam-systemd",
    "libsystemd-shared",
    "libsystemd0",
    "libudev1",
    "systemd",
    "systemd-resolved",
    "systemd-sysv",
    "systemd-timesyncd",
    "udev",
];
const NATIVE: [&str; 6] = [
    "libselinux1",
    "apparmor",
    "libapparmor1",
    "gdm3",
    "libgdm1",
    "gir1.2-gdm-1.0",
];

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct RecordedText {
    pin: EvidencePin,
    body: String,
}
impl RecordedText {
    fn validate(&self) -> Result<&str> {
        ensure(
            self.pin.bytes <= LIMIT
                && self.pin.bytes == self.body.len() as u64
                && fs::valid_digest(&self.pin.sha256)
                && fs::digest(self.body.as_bytes()) == self.pin.sha256
                && !self.body.contains('\0'),
            "installed evidence text is unbounded or its digest differs",
        )?;
        Ok(&self.body)
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ArchiveInput {
    package: String,
    version: String,
    architecture: String,
    archive: EvidencePin,
    guest_path: String,
    source: EvidencePin,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ArchiveControl {
    archive: EvidencePin,
    source: EvidencePin,
    control: Fields,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Admission {
    schema: String,
    status: RecordedText,
    archives: Vec<ArchiveControl>,
    command_outputs: Vec<RecordedText>,
    systemd: Value,
    native_candidates: Value,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct NativeRelease {
    schema: String,
    systemd: FilePin,
    native_candidates: FilePin,
}

fn qualification_child(path: &Path) -> bool {
    path.is_absolute()
        && path.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
        && path.file_name().and_then(|s| s.to_str()).is_some_and(|s| {
            !s.is_empty()
                && s.len() <= 160
                && s.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        })
}
pub(super) fn source_shape(source: &SourceReceipt) -> Result<()> {
    let work = source
        .installed_admission_directory
        .as_deref()
        .ok_or("installed source lacks its create-only admission directory")?;
    ensure(
        source.baseline_manifest.is_some()
            && source.baseline_receipt.is_some()
            && source.native_release.is_some()
            && source.native_transaction.is_some()
            && source.package_transactions.last() == source.native_transaction.as_ref()
            && qualification_child(work)
            && source.root.path.parent().is_some_and(qualification_child)
            && source.root.path.file_name().and_then(|v| v.to_str()) == Some("root")
            && !source.root.path.starts_with(work)
            && !work.starts_with(&source.root.path),
        "installed source lacks its bounded clone/transaction/native authority",
    )
}
fn pin(value: &Value) -> Result<EvidencePin> {
    let result: EvidencePin = serde_json::from_value(value.clone())?;
    ensure(
        result.path.is_absolute()
            && fs::valid_digest(&result.sha256)
            && result.mode & 0o022 == 0
            && result.uid == 0
            && result.gid == 0,
        "normal transaction evidence pin is not protected",
    )?;
    Ok(result)
}
fn file_pin(value: &EvidencePin) -> FilePin {
    FilePin {
        path: value.path.clone(),
        bytes: value.bytes,
        sha256: value.sha256.clone(),
    }
}
fn content_equal(a: &EvidencePin, b: &EvidencePin) -> bool {
    a.bytes == b.bytes
        && a.sha256 == b.sha256
        && a.mode == b.mode
        && a.uid == b.uid
        && a.gid == b.gid
}
fn baseline(
    record: &RecordedJson,
    source: &SourceReceipt,
    release: &str,
) -> Result<CompleteManifest> {
    ensure(
        source.baseline_manifest.as_ref() == Some(&record.pin),
        "installed source baseline body does not match its exact original pin",
    )?;
    let value = record.validate_with_limit(BASELINE_LIMIT)?;
    ensure(
        value["baseline_manifest_record"].is_null() && value["installed_admission"].is_null(),
        "installed baseline cannot contain recursive installed lineage",
    )?;
    let result: CompleteManifest = serde_json::from_value(value)?;
    let original = super::source(&result.source)?;
    ensure(
        original.stage == "baseline" && result.target_kernel_release == release,
        "installed source requires a baseline for the same shared kernel",
    )?;
    super::validate(&result)?;
    ensure(
        source.bootstrap_receipt == original.bootstrap_receipt
            && source.root.path != original.root.path
            && (source.root.device, source.root.inode)
                != (original.root.device, original.root.inode),
        "installed source rewrote the original bootstrap root or failed to clone it",
    )?;
    Ok(result)
}
fn materialization(value: &Value, source: &SourceReceipt, base: &CompleteManifest) -> Result<()> {
    let original = super::source(&base.source)?;
    let destination: Identity = serde_json::from_value(value["destination_identity"].clone())?;
    let mut regular = 0usize;
    let mut bytes = 0u64;
    for entry in &base.entries {
        match entry.content {
            Content::Regular { .. } => {
                regular += 1;
                bytes = bytes
                    .checked_add(entry.source.size)
                    .ok_or("baseline size overflow")?;
            }
            Content::Hardlink { .. } => regular += 1,
            _ => (),
        }
    }
    ensure(
        value["schema"] == "droidloom.complete-ubuntu-materialization.v1"
            && value["manifest_sha256"].as_str()
                == source.baseline_manifest.as_ref().map(|p| p.sha256.as_str())
            && value["destination"].as_str() == source.root.path.to_str()
            && destination.dev == source.root.device
            && destination.ino == source.root.inode
            && destination.uid == 0
            && destination.gid == 0
            && FileType::from_raw_mode(destination.mode) == FileType::Directory
            && (destination.dev, destination.ino) != (original.root.device, original.root.inode)
            && value["entries_verified"].as_u64()
                == Some((base.entries.len() + base.static_devices.len()) as u64)
            && value["regular_paths_verified"].as_u64() == Some(regular as u64)
            && value["unique_regular_bytes"].as_u64() == Some(bytes)
            && value["source_stage"] == "baseline"
            && value["complete_package_database"] == true
            && value["materialization_complete"] == true
            && value["kernel_present"] == false
            && value["guest_qualified"] == false,
        "installed source is not the complete normally materialized baseline clone",
    )
}
fn roster(proofs: &[RecordedJson], value: &Value, baseline: &[Package]) -> Result<Vec<Package>> {
    let document: Packages = serde_json::from_value(proof(proofs, &pin(value)?)?.validate()?)?;
    let current = package_map(&document.packages)?;
    let old = package_map(baseline)?;
    let original_exact = old.iter().all(|(k, v)| current.get(k) == Some(v));
    ensure(
        document.schema == "droidloom.actual-native-package-state.v1"
            && document.configured
            && document.original_requested_count == 971
            && document.original_requested_versions_exact == original_exact
            && current.len() >= old.len()
            && old.keys().all(|k| current.contains_key(k)),
        "installed package roster dropped baseline packages or misreported configuration",
    )?;
    Ok(document.packages)
}
fn output<'a>(admission: &'a Admission, value: &Value) -> Result<&'a str> {
    let wanted = pin(value)?;
    let matched: Vec<_> = admission
        .command_outputs
        .iter()
        .filter(|r| r.pin == wanted)
        .collect();
    ensure(
        matched.len() == 1,
        "normal command output is missing or duplicated",
    )?;
    matched[0].validate()
}
fn command(value: &Value, source: &SourceReceipt, program: &str) -> Result<Vec<String>> {
    let args: Vec<String> = serde_json::from_value(value["command"].clone())?;
    ensure(
        value["exit_code"] == 0
            && value["seconds"]
                .as_f64()
                .is_some_and(|s| s.is_finite() && (0.0..=7200.0).contains(&s))
            && args.len() >= 3
            && args[0] == "/usr/bin/chroot"
            && Path::new(&args[1]) == source.root.path
            && args[2] == program,
        "normal package command did not succeed inside the exact private root",
    )?;
    Ok(args)
}
fn query_rows(text: &str) -> Result<Vec<Package>> {
    ensure(
        !text.contains('\r') && !text.contains('\0'),
        "invalid dpkg-query encoding",
    )?;
    let mut rows = Vec::new();
    for line in text.lines() {
        let parts: Vec<_> = line.split('\t').collect();
        ensure(parts.len() == 4, "normal dpkg-query output columns differ")?;
        rows.push(Package {
            package: parts[0].into(),
            version: parts[1].into(),
            architecture: parts[2].into(),
            status: parts[3].into(),
        });
    }
    package_map(&rows)?;
    Ok(rows)
}
fn query(
    tx: &Value,
    name: &str,
    admission: &Admission,
    source: &SourceReceipt,
    expected: &[Package],
) -> Result<()> {
    let op = &tx[name];
    let args = command(op, source, "/usr/bin/dpkg-query")?;
    ensure(
        args[3..] == ["-W", QUERY_FORMAT]
            && output(admission, &op["stderr"])?.is_empty()
            && package_map(&query_rows(output(admission, &op["stdout"])?)?)?
                == package_map(expected)?,
        "normal dpkg-query does not bind the complete configured roster",
    )
}
fn apt(
    op: &Value,
    source: &SourceReceipt,
    archives: &[ArchiveInput],
    simulate: bool,
) -> Result<()> {
    let args = command(op, source, "/usr/bin/apt-get")?;
    let mut expected: Vec<String> = [
        "-o",
        "Dir::Etc::sourcelist=/etc/apt/sources.list.snapshot-original-cohort-r2",
        "-o",
        "Dir::Etc::sourceparts=-",
        "-o",
        "Dir::State::lists=/var/lib/apt/lists-snapshot-original-cohort-r2",
        if simulate { "--simulate" } else { "--yes" },
        "--no-download",
        "--no-install-recommends",
        "--no-remove",
        "install",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    expected.extend(archives.iter().map(|a| a.guest_path.clone()));
    ensure(
        args[3..] == expected,
        "normal transaction must install the exact pinned cache archives without removals/downloads",
    )
}
fn archive_controls<'a>(
    source: &SourceReceipt,
    inputs: &[ArchiveInput],
    admission: &'a Admission,
) -> Result<BTreeMap<String, &'a Fields>> {
    ensure(
        !inputs.is_empty() && inputs.len() <= 128,
        "normal archive cohort is unbounded",
    )?;
    let mut result = BTreeMap::new();
    for item in inputs {
        paths::parts(&item.guest_path)?;
        ensure(
            Path::new(&item.guest_path).parent() == Some(Path::new("/var/cache/apt/archives"))
                && item.guest_path.ends_with(".deb")
                && item.archive.path
                    == source
                        .root
                        .path
                        .join(item.guest_path.trim_start_matches('/'))
                && item.archive.bytes > 0
                && item.archive.bytes <= ARCHIVE_LIMIT
                && item.archive.bytes == item.source.bytes
                && item.archive.sha256 == item.source.sha256,
            "normal package archive is not the pinned private cache copy",
        )?;
        let matched: Vec<_> = admission
            .archives
            .iter()
            .filter(|a| a.archive == item.archive && a.source == item.source)
            .collect();
        ensure(
            matched.len() == 1,
            "actual archive control evidence missing or duplicated",
        )?;
        let fields = &matched[0].control;
        ensure(
            field(fields, "Package")? == item.package
                && field(fields, "Version")? == item.version
                && field(fields, "Architecture")? == item.architecture,
            "actual binary control differs from the normal install request",
        )?;
        let key = normalize_package(&item.package, &item.architecture)?;
        ensure(
            result.insert(key, fields).is_none(),
            "duplicate normal package archive",
        )?;
    }
    Ok(result)
}
fn transition(
    before: &[Package],
    after: &[Package],
    actual: &BTreeMap<String, &Fields>,
) -> Result<BTreeMap<String, String>> {
    let old = package_map(before)?;
    let observed = package_map(after)?;
    let mut expected = old.clone();
    let mut changed = BTreeMap::new();
    for (key, fields) in actual {
        let version = field(fields, "Version")?.to_owned();
        ensure(
            old.get(key) != Some(&version),
            "normal transaction contains an unperformed reinstall",
        )?;
        expected.insert(key.clone(), version.clone());
        changed.insert(key.clone(), version);
    }
    ensure(
        expected == observed,
        "normal transaction removed or changed a package outside its actual archive controls",
    )?;
    Ok(changed)
}
fn simulation(text: &str, expected: &BTreeMap<String, String>) -> Result<()> {
    ensure(
        !text.contains('\r') && !text.contains('\0'),
        "invalid APT simulation encoding",
    )?;
    let mut actual = BTreeMap::new();
    for line in text.lines() {
        ensure(
            !line.starts_with("Remv "),
            "normal APT simulation planned a removal",
        )?;
        if !line.starts_with("Inst ") {
            continue;
        }
        let name = line
            .split_whitespace()
            .nth(1)
            .ok_or("simulation package missing")?;
        let version = line
            .split_once(" (")
            .and_then(|(_, s)| s.split_whitespace().next())
            .ok_or("simulation candidate version missing")?;
        let candidates: Vec<_> = expected
            .keys()
            .filter(|key| {
                key.as_str() == name || key.split_once(':').is_some_and(|(p, _)| p == name)
            })
            .collect();
        ensure(
            candidates.len() == 1,
            "simulation introduced an unrequested package",
        )?;
        ensure(
            actual
                .insert(candidates[0].clone(), version.to_owned())
                .is_none(),
            "simulation repeated a package",
        )?;
    }
    ensure(
        &actual == expected,
        "simulation does not match the complete normal transaction delta",
    )
}
fn chain(
    source: &SourceReceipt,
    base: &CompleteManifest,
    proofs: &[RecordedJson],
    admission: &Admission,
) -> Result<Vec<Package>> {
    ensure(
        admission.schema == ADMISSION_SCHEMA
            && admission.archives.len() <= 512
            && admission.command_outputs.len() <= 512
            && admission.status.pin == source.dpkg_status,
        "installed admission shape or current database binding differs",
    )?;
    let original = super::source(&base.source)?;
    materialization(
        &proof(
            proofs,
            source
                .baseline_receipt
                .as_ref()
                .ok_or("clone receipt missing")?,
        )?
        .validate()?,
        source,
        base,
    )?;
    let mut previous = base.packages.clone();
    let mut prior_status: Option<EvidencePin> = None;
    let mut all_controls: BTreeMap<String, Fields> = BTreeMap::new();
    for transaction_pin in &source.package_transactions {
        let tx = proof(proofs, transaction_pin)?.validate()?;
        let start = pin(&tx["dpkg_status_before"])?;
        let end = pin(&tx["dpkg_status_after"])?;
        ensure(
            tx["schema"] == "p4-complete-ubuntu-normal-package-install-v1"
                && tx["configured"] == true
                && tx["root"] == serde_json::to_value(&source.root)?
                && tx["baseline_materialization"]
                    == serde_json::to_value(
                        source.baseline_receipt.as_ref().ok_or("clone missing")?,
                    )?
                && tx["source_baseline_unchanged"] == true
                && tx["host_dpkg_unchanged"] == true
                && tx["host_services_modified"] == false
                && tx["original_private_data_read"] == false
                && tx["guest_booted"] == false
                && tx["production_ready"] == false
                && start.path == source.dpkg_status.path
                && end.path == source.dpkg_status.path,
            "normal transaction is not isolated from the unchanged baseline and host",
        )?;
        if let Some(prior) = &prior_status {
            ensure(
                prior == &start,
                "normal package transactions have a database gap",
            )?;
        } else {
            ensure(
                content_equal(&start, &original.dpkg_status)
                    && (start.device, start.inode)
                        != (original.dpkg_status.device, original.dpkg_status.inode),
                "first normal transaction did not start with the independent materialized database",
            )?;
        }
        let prepared = proof(proofs, &pin(&tx["prepared"])?)?.validate()?;
        ensure(
            prepared["root"] == serde_json::to_value(&source.root)?
                && prepared["archive_inputs"] == tx["archive_inputs"],
            "normal install changed the prepared root or archive set",
        )?;
        for ns in ["user", "mnt", "pid", "net"] {
            let inner = tx["namespaces"][ns]
                .as_str()
                .ok_or("normal namespace missing")?;
            let outer = prepared["outer_namespaces"][ns]
                .as_str()
                .ok_or("outer namespace missing")?;
            ensure(
                inner != outer && inner.starts_with(&format!("{ns}:[")) && inner.ends_with(']'),
                "normal package install reused an outer namespace",
            )?;
        }
        let before = roster(proofs, &tx["packages_before"], &base.packages)?;
        ensure(
            package_map(&before)? == package_map(&previous)?,
            "transaction prior roster differs",
        )?;
        let after = roster(proofs, &tx["packages"], &base.packages)?;
        let inputs: Vec<ArchiveInput> = serde_json::from_value(tx["archive_inputs"].clone())?;
        let controls = archive_controls(source, &inputs, admission)?;
        let changed = transition(&before, &after, &controls)?;
        apt(&tx["simulation"], source, &inputs, true)?;
        apt(&tx["install"], source, &inputs, false)?;
        simulation(output(admission, &tx["simulation"]["stdout"])?, &changed)?;
        output(admission, &tx["simulation"]["stderr"])?;
        output(admission, &tx["install"]["stdout"])?;
        output(admission, &tx["install"]["stderr"])?;
        let audit = command(&tx["audit"], source, "/usr/bin/dpkg")?;
        ensure(
            audit[3..] == ["--audit"]
                && output(admission, &tx["audit"]["stdout"])?.is_empty()
                && output(admission, &tx["audit"]["stderr"])?.is_empty(),
            "normal dpkg audit left an unresolved package",
        )?;
        query(&tx, "before_query", admission, source, &before)?;
        query(&tx, "query", admission, source, &after)?;
        for (key, fields) in controls {
            all_controls.insert(key, fields.clone());
        }
        previous = after;
        prior_status = Some(end);
    }
    let last = proof(
        proofs,
        source
            .package_transactions
            .last()
            .ok_or("transaction missing")?,
    )?
    .validate()?;
    ensure(
        prior_status.as_ref() == Some(&source.dpkg_status)
            && last["packages"] == serde_json::to_value(&source.packages)?
            && package_map(&previous)?
                == package_map(&roster(
                    proofs,
                    &serde_json::to_value(&source.packages)?,
                    &base.packages,
                )?)?,
        "installed source is not the final complete normal transaction",
    )?;
    let status = admission.status.validate()?;
    ensure(
        package_map(&status_packages(status.as_bytes())?)? == package_map(&previous)?,
        "actual final database differs from the complete normal query",
    )?;
    dependencies::closure(
        &control(status)?,
        &all_controls.into_values().collect::<Vec<_>>(),
    )?;
    Ok(previous)
}
fn release(source: &SourceReceipt, proofs: &[RecordedJson]) -> Result<NativeRelease> {
    let result: NativeRelease = serde_json::from_value(
        proof(
            proofs,
            source
                .native_release
                .as_ref()
                .ok_or("native release missing")?,
        )?
        .validate()?,
    )?;
    ensure(
        result.schema == RELEASE_SCHEMA,
        "unsupported complete native release",
    )?;
    Ok(result)
}
fn prior_native<'a>(proofs: &'a [RecordedJson], pin: &FilePin) -> Result<&'a RecordedJson> {
    let matched: Vec<_> = proofs
        .iter()
        .filter(|p| {
            p.pin.path == pin.path && p.pin.bytes == pin.bytes && p.pin.sha256 == pin.sha256
        })
        .collect();
    ensure(
        matched.len() == 1,
        "native source admission input missing or duplicated",
    )?;
    Ok(matched[0])
}
fn native_report(
    manifest: &CompleteManifest,
    source: &SourceReceipt,
    report: &Value,
    prior: &RecordedJson,
    schema: &str,
    family: &[&str],
) -> Result<()> {
    let original = prior.validate()?;
    let installed = &report["installed_source"];
    let preserved: FilePin = serde_json::from_value(report["preserved_input"].clone())?;
    let original_input: FilePin = serde_json::from_value(original["input"].clone())?;
    let directory = if family == SYSTEMD.as_slice() {
        "systemd"
    } else {
        "native"
    };
    let work = source
        .installed_admission_directory
        .as_ref()
        .ok_or("admission directory absent")?;
    ensure(
        report["source_admission"] == serde_json::to_value(file_pin(&prior.pin))?
            && preserved.bytes == original_input.bytes
            && preserved.sha256 == original_input.sha256
            && preserved.path == work.join(directory).join("SOURCE-INPUTS.json"),
        "fresh native source admission did not preserve its exact original input",
    )?;
    let root_identity: Identity = serde_json::from_value(installed["root_identity"].clone())?;
    let status: FilePin = serde_json::from_value(installed["dpkg_status"].clone())?;
    ensure(
        report["schema"] == schema
            && original["schema"] == schema
            && report["input"] == original["input"]
            && !report["input"].is_null()
            && installed["root"].as_str() == source.root.path.to_str()
            && root_identity.dev == source.root.device
            && root_identity.ino == source.root.inode
            && status.path == source.dpkg_status.path
            && status.bytes == source.dpkg_status.bytes
            && status.sha256 == source.dpkg_status.sha256
            && report["package_installation_performed_by_admission"] == false
            && report["maintainer_scripts_executed_by_admission"] == false
            && report["source_files_modified_by_admission"] == false
            && report["guest_qualified"] == false
            && report["production_ready"] == false,
        "native admission was not freshly bound to the exact normal installed root",
    )?;
    let packages = report["packages"]
        .as_array()
        .ok_or("native package controls missing")?;
    let admission = manifest
        .installed_admission
        .as_ref()
        .ok_or("installed archive evidence missing")?;
    let mut archive_hashes = BTreeMap::new();
    let mut names = BTreeSet::new();
    let roster = package_map(&manifest.packages)?;
    for package in packages {
        let fields: Fields = serde_json::from_value(package["control"].clone())?;
        let name = field(&fields, "Package")?;
        let arch = field(&fields, "Architecture")?;
        ensure(
            family.contains(&name)
                && arch == "amd64"
                && names.insert(name.to_owned())
                && roster
                    .get(&normalize_package(name, arch)?)
                    .map(String::as_str)
                    == Some(field(&fields, "Version")?),
            "native report contains a different or unconfigured package",
        )?;
        let archives: Vec<_> = admission
            .archives
            .iter()
            .filter(|a| a.control == fields)
            .collect();
        ensure(
            archives.len() == 1,
            "native source admission control is not the actual normally installed binary",
        )?;
        archive_hashes.insert(name.to_owned(), archives[0].archive.sha256.as_str());
    }
    ensure(names.len() == family.len(), "native family is incomplete")?;
    let raw: Vec<Member> = serde_json::from_value(report["complete_selected_payload"].clone())?;
    let actual: Vec<Member> =
        serde_json::from_value(installed["complete_installed_payload"].clone())?;
    ensure(
        !raw.is_empty() && raw.len() <= 50000 && actual.len() == raw.len(),
        "native complete payload report is missing or unbounded",
    )?;
    let expected_paths: BTreeSet<_> = raw.iter().map(|m| m.path.as_str()).collect();
    let actual_paths: BTreeSet<_> = actual.iter().map(|m| m.path.as_str()).collect();
    ensure(
        expected_paths.len() == raw.len() && expected_paths == actual_paths,
        "native installed payload omitted or duplicated a package member",
    )?;
    let raw_members: BTreeMap<_, _> = raw.iter().map(|m| (m.path.as_str(), m)).collect();
    let entries: BTreeMap<_, _> = manifest
        .entries
        .iter()
        .map(|e| (e.path.as_str(), e))
        .collect();
    for member in actual {
        let mut expected = (**raw_members
            .get(member.path.as_str())
            .ok_or("raw native member absent")?)
        .clone();
        if directory == "systemd"
            && ["/etc/credstore", "/etc/credstore.encrypted"].contains(&member.path.as_str())
        {
            ensure(
                expected.content == Content::Directory
                    && expected.mode == 0o755
                    && expected.uid == 0
                    && expected.gid == 0,
                "normal credential directory archive metadata differs",
            )?;
            expected.mode = 0o700;
            let transforms = installed["normal_tmpfiles_directory_transforms_verified"]
                .as_array()
                .ok_or("normal credential directory source proof missing")?;
            let matched: Vec<_> = transforms
                .iter()
                .filter(|t| t["path"].as_str() == Some(member.path.as_str()))
                .collect();
            ensure(
                matched.len() == 1
                    && matched[0]["archive_mode"] == 493
                    && matched[0]["installed_mode"] == 448
                    && matched[0]["uid"] == 0
                    && matched[0]["gid"] == 0
                    && matched[0]["rule"] == format!("d {} 0700 root root", member.path),
                "normal credential directory transform is not the exact package rule",
            )?;
            let rule: FilePin = serde_json::from_value(matched[0]["normal_package_rule"].clone())?;
            let raw_rule = raw_members
                .get("/usr/lib/tmpfiles.d/credstore.conf")
                .ok_or("credential rule absent")?;
            ensure(
                rule.path == source.root.path.join("usr/lib/tmpfiles.d/credstore.conf")
                    && rule.bytes == raw_rule.bytes
                    && matches!(&raw_rule.content, Content::Regular { sha256 } if sha256 == &rule.sha256),
                "credential directory transformation is not bound to actual package rule bytes",
            )?;
        }
        ensure(
            member == expected,
            "native installed payload has an unproven post-install transformation",
        )?;
        ensure(
            family.contains(&member.package.as_str())
                && fs::valid_digest(&member.archive_sha256)
                && archive_hashes.get(&member.package).copied()
                    == Some(member.archive_sha256.as_str()),
            "native payload member lacks its actual normally installed archive binding",
        )?;
        let observed = entries.get(member.path.as_str()).ok_or_else(|| {
            format!(
                "complete capture omitted native package member: {}",
                member.path
            )
        })?;
        let same_content = match (&observed.content, &member.content) {
            (
                Content::Regular { sha256: a } | Content::Hardlink { sha256: a, .. },
                Content::Regular { sha256: b } | Content::Hardlink { sha256: b, .. },
            ) => a == b,
            (a, b) => a == b,
        };
        ensure(
            observed.source.mode & 0o7777 == member.mode
                && observed.source.uid == member.uid
                && observed.source.gid == member.gid
                && fs::content_type_matches(&observed.source, &member.content)
                && same_content
                && (!matches!(
                    member.content,
                    Content::Regular { .. } | Content::Hardlink { .. }
                ) || observed.source.size == member.bytes),
            &format!(
                "complete capture changed native package member: {}",
                member.path
            ),
        )?;
        if let Content::Hardlink { target, .. } = &member.content {
            let target = entries
                .get(target.as_str())
                .ok_or("native hardlink target omitted")?;
            ensure(
                observed.source.dev == target.source.dev
                    && observed.source.ino == target.source.ino,
                "complete capture split a normal native package hardlink",
            )?;
        }
    }
    Ok(())
}
pub(super) fn validate(
    manifest: &CompleteManifest,
    source: &SourceReceipt,
) -> Result<Vec<Package>> {
    let base = baseline(
        manifest
            .baseline_manifest_record
            .as_ref()
            .ok_or("complete baseline body missing")?,
        source,
        &manifest.target_kernel_release,
    )?;
    let admission = manifest
        .installed_admission
        .as_ref()
        .ok_or("installed admission missing")?;
    let packages = chain(source, &base, &manifest.proofs, admission)?;
    let release = release(source, &manifest.proofs)?;
    native_report(
        manifest,
        source,
        &admission.systemd,
        prior_native(&manifest.proofs, &release.systemd)?,
        "droidloom.systemd-candidate-admitted.v1",
        &SYSTEMD,
    )?;
    native_report(
        manifest,
        source,
        &admission.native_candidates,
        prior_native(&manifest.proofs, &release.native_candidates)?,
        "droidloom.native-family-candidate-admission.v1",
        &NATIVE,
    )?;
    Ok(packages)
}
fn push_json(
    wanted: EvidencePin,
    proofs: &mut Vec<RecordedJson>,
    held: &mut Vec<HeldInput>,
) -> Result<()> {
    if proofs.iter().any(|p| p.pin == wanted) {
        return Ok(());
    }
    ensure(
        proofs.len() < 512,
        "installed JSON proof count exceeds bound",
    )?;
    let mut input = HeldInput::open(wanted, LIMIT)?;
    proofs.push(input.json()?);
    held.push(input);
    Ok(())
}
fn text(wanted: EvidencePin, held: &mut Vec<HeldInput>) -> Result<RecordedText> {
    let mut input = HeldInput::open(wanted, LIMIT)?;
    input.file.seek(SeekFrom::Start(0))?;
    let mut body = String::new();
    Read::by_ref(&mut input.file)
        .take(LIMIT + 1)
        .read_to_string(&mut body)?;
    input.revalidate()?;
    let record = RecordedText {
        pin: input.pin.clone(),
        body,
    };
    record.validate()?;
    held.push(input);
    Ok(record)
}
pub(super) fn capture(
    source: &SourceReceipt,
    release_name: &str,
    proofs: &mut Vec<RecordedJson>,
    held: &mut Vec<HeldInput>,
) -> Result<(RecordedJson, Admission)> {
    source_shape(source)?;
    let mut baseline_file = HeldInput::open(
        source
            .baseline_manifest
            .clone()
            .ok_or("baseline pin missing")?,
        BASELINE_LIMIT,
    )?;
    let baseline_record = baseline_file.json_with_limit(BASELINE_LIMIT)?;
    let base = baseline(&baseline_record, source, release_name)?;
    held.push(baseline_file);
    push_json(
        source
            .baseline_receipt
            .clone()
            .ok_or("materialization missing")?,
        proofs,
        held,
    )?;
    push_json(
        source
            .native_release
            .clone()
            .ok_or("native release missing")?,
        proofs,
        held,
    )?;
    let work = source
        .installed_admission_directory
        .as_deref()
        .ok_or("admission work missing")?;
    crate::boot::create_work(work)?;
    let archives_work = work.join("transaction-archives");
    boot_files::private_dir(&archives_work)?;
    let mut admission = Admission {
        schema: ADMISSION_SCHEMA.into(),
        status: text(source.dpkg_status.clone(), held)?,
        archives: Vec::new(),
        command_outputs: Vec::new(),
        systemd: Value::Null,
        native_candidates: Value::Null,
    };
    for transaction_pin in &source.package_transactions {
        let tx = proof(proofs, transaction_pin)?.validate()?;
        for key in ["prepared", "packages_before", "packages"] {
            push_json(pin(&tx[key])?, proofs, held)?;
        }
        for op in ["simulation", "install", "audit", "before_query", "query"] {
            for stream in ["stdout", "stderr"] {
                let wanted = pin(&tx[op][stream])?;
                if !admission.command_outputs.iter().any(|o| o.pin == wanted) {
                    admission.command_outputs.push(text(wanted, held)?);
                }
            }
        }
        let inputs: Vec<ArchiveInput> = serde_json::from_value(tx["archive_inputs"].clone())?;
        ensure(inputs.len() <= 128, "too many normal archives")?;
        for item in inputs {
            if admission
                .archives
                .iter()
                .any(|a| a.archive == item.archive && a.source == item.source)
            {
                continue;
            }
            ensure(
                admission.archives.len() < 512,
                "installed archive evidence exceeds bound",
            )?;
            let archive = HeldInput::open(item.archive.clone(), ARCHIVE_LIMIT)?;
            let original = HeldInput::open(item.source.clone(), ARCHIVE_LIMIT)?;
            ensure(
                archive.pin.bytes == original.pin.bytes
                    && archive.pin.sha256 == original.pin.sha256,
                "normal cached archive differs from its exact staged source",
            )?;
            let area = archives_work.join(format!("{:03}", admission.archives.len()));
            boot_files::private_dir(&area)?;
            let copied = area.join("package.deb");
            boot_files::copy_pin(&file_pin(&item.archive), &copied, 0o400)?;
            let operation = boot_files::run_logged(
                &area,
                "control",
                "/usr/bin/dpkg-deb",
                &["--field".into(), fs::absolute_string(&copied)?],
                30,
            )?;
            let mut fields = control(std::str::from_utf8(&boot_files::read_pin(
                &operation.log,
                128 * 1024,
            )?)?)?;
            ensure(
                fields.len() == 1,
                "actual binary package has multiple control paragraphs",
            )?;
            admission.archives.push(ArchiveControl {
                archive: item.archive,
                source: item.source,
                control: fields.remove(0),
            });
            held.push(archive);
            held.push(original);
        }
    }
    chain(source, &base, proofs, &admission)?;
    let native = release(source, proofs)?;
    for candidate in [&native.systemd, &native.native_candidates] {
        let mut file = HeldInput::from_path(&candidate.path, &candidate.sha256)?;
        ensure(
            file.pin.bytes == candidate.bytes,
            "native admission receipt size differs",
        )?;
        let document = file.json()?;
        if !proofs.iter().any(|p| p.pin == document.pin) {
            proofs.push(document);
        }
        held.push(file);
    }
    admission.systemd = crate::boot_systemd_candidate::verify_installed_systemd(
        &source.root.path,
        &native.systemd,
        &work.join("systemd"),
    )?;
    admission.native_candidates = crate::boot_native_candidates::verify_installed_native(
        &source.root.path,
        &native.native_candidates,
        &work.join("native"),
    )?;
    ensure(
        serde_json::to_vec(&admission)?.len() <= 16 * 1024 * 1024,
        "installed admission report exceeds bound",
    )?;
    Ok((baseline_record, admission))
}
#[cfg(test)]
mod tests {
    use super::*;
    fn package(name: &str, version: &str) -> Package {
        Package {
            package: name.into(),
            version: version.into(),
            architecture: "amd64".into(),
            status: "ii ".into(),
        }
    }
    fn fields(name: &str, version: &str) -> Fields {
        BTreeMap::from([
            ("Package".into(), name.into()),
            ("Version".into(), version.into()),
            ("Architecture".into(), "amd64".into()),
        ])
    }
    #[test]
    fn normal_delta_rejects_unlisted_updates_removals_and_missing_install() {
        let before = vec![package("systemd", "1"), package("keep", "1")];
        let actual = fields("systemd", "2");
        let controls = BTreeMap::from([("systemd:amd64".into(), &actual)]);
        let good = vec![package("systemd", "2"), package("keep", "1")];
        assert!(transition(&before, &good, &controls).is_ok());
        assert!(transition(&before, &before, &controls).is_err());
        assert!(transition(&before, &[package("systemd", "2")], &controls).is_err());
        assert!(
            transition(
                &before,
                &[package("systemd", "2"), package("keep", "3")],
                &controls
            )
            .is_err()
        );
    }
    #[test]
    fn apt_simulation_requires_exact_versions_no_extra_dependency_or_removal() {
        let expected = BTreeMap::from([("liba:amd64".into(), "1:2.0-1+p4".into())]);
        assert!(
            simulation(
                "Inst liba [1:1] (1:2.0-1+p4 local-deb [amd64])\n",
                &expected
            )
            .is_ok()
        );
        for bad in [
            "Inst liba [1:1] (1:2.0-1 local-deb [amd64])\n",
            "Inst extra (1 local-deb [amd64])\n",
            "Remv other [1]\nInst liba (1:2.0-1+p4 local-deb [amd64])\n",
            "",
        ] {
            assert!(simulation(bad, &expected).is_err());
        }
    }
    #[test]
    fn actual_query_requires_complete_configured_rows() {
        assert!(query_rows("liba:amd64\t1:2\tamd64\tii \n").is_ok());
        for bad in [
            "liba\t1:2\tamd64\tiU \n",
            "liba\t1:2\tamd64\tii \nliba:amd64\t1:2\tamd64\tii \n",
            "liba\t1:2\tamd64\n",
        ] {
            assert!(query_rows(bad).is_err());
        }
    }
    #[test]
    fn admission_directory_cannot_alias_source_or_a_host_path() {
        assert!(qualification_child(Path::new(
            "/var/lib/droidloom-qualification/installed-r1"
        )));
        for path in [
            "/",
            "/tmp/admit",
            "/var/lib/droidloom-qualification/a/root",
            "/var/lib/droidloom-qualification/a/../b",
        ] {
            assert!(!qualification_child(Path::new(path)));
        }
    }

    fn evidence(path: &str, body: &str) -> EvidencePin {
        EvidencePin {
            path: path.into(),
            bytes: body.len() as u64,
            sha256: fs::digest(body.as_bytes()),
            device: 1,
            inode: 7,
            mode: 0o400,
            uid: 0,
            gid: 0,
        }
    }
    fn original_source() -> SourceReceipt {
        let root = "/var/lib/droidloom-qualification/original/root";
        let p = evidence("/proof", "{}");
        SourceReceipt {
            schema: SOURCE_SCHEMA.into(),
            stage: "baseline".into(),
            root: RootIdentity {
                path: root.into(),
                device: 1,
                inode: 2,
            },
            bootstrap_receipt: p.clone(),
            baseline_receipt: None,
            baseline_manifest: None,
            installed_admission_directory: None,
            package_transactions: vec![p.clone()],
            packages: p.clone(),
            dpkg_status: evidence(&format!("{root}/var/lib/dpkg/status"), "status"),
            native_release: None,
            native_transaction: None,
            fresh_generated_root: true,
            private_accounts_copied: false,
            configured: true,
        }
    }
    #[test]
    fn opaque_apt_progress_is_preserved_without_accepting_changed_evidence() {
        let body = "Reading database...\r20%\rDone\n";
        let record = RecordedText {
            pin: evidence("/progress", body),
            body: body.into(),
        };
        assert_eq!(record.validate().unwrap(), body);
        let mut changed = record.clone();
        changed.body = changed.body.replace('\r', "");
        assert!(changed.validate().is_err());
        assert!(query_rows("p\t1\tamd64\tii \r\n").is_err());
    }
    #[test]
    fn baseline_body_cannot_nest_another_baseline_or_installed_authority() {
        for value in [
            serde_json::json!({"baseline_manifest_record":{},"installed_admission":null}),
            serde_json::json!({"baseline_manifest_record":null,"installed_admission":{}}),
        ] {
            let body = serde_json::to_string(&value).unwrap();
            let record = RecordedJson {
                pin: evidence("/baseline", &body),
                body,
            };
            let mut source = original_source();
            source.baseline_manifest = Some(record.pin.clone());
            let error = baseline(&record, &source, "6.18.64-test")
                .unwrap_err()
                .to_string();
            assert!(error.contains("recursive installed lineage"), "{error}");
        }
    }
}
