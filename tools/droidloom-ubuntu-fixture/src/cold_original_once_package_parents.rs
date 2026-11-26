//! Observe only the configuration namespace changes made by the selected
//! normal native packages. This module does not run a package script or mutate
//! a public inode. The once dispatcher owns the actual package operation.
use super::super::commands::CommandEvidence;
use super::*;
use std::collections::BTreeSet;

const SYSTEM: &str = "/etc/systemd/system";
const WANTS: &str = "/etc/systemd/system/local-fs.target.wants";
const DISPLAY: &str = "display-manager.service";
const TMP: &str = "tmp.mount";
const GDM_LINK: &str = "/lib/systemd/system/gdm3.service";
const OLD_TMP: &str = "/usr/share/systemd/tmp.mount";
const DEFAULT_DM: &str = "/etc/X11/default-display-manager";
const DEFAULT_DM_SHA: &str = "d4789869746ebc4ada9bd8c5abae3f1dfb24d94558309d151e8c0b1403b5178f";
const GDM_UNIT_SHA: &str = "922b26169adba30c6ad3104dec0623d047203465da9469cda4d41661127a3516";
// These complete, normally built archives were read independently together
// with their complete control.tar scripts. No script-success flag widens the
// allowed namespace delta. A different build must be reviewed explicitly.
const ARCHIVES: [(&str, &str, &str, u64, &str); 4] = [
    (
        "gdm3",
        "old",
        "50.1-0ubuntu0.1",
        246294,
        "6d979c79ce3492236e9a2467c5a11e4f5355f087f08ca0dfc0e0e3320b5d2aae",
    ),
    (
        "gdm3",
        "new",
        "50.1-0ubuntu0.1+p4fsuser3",
        873260,
        "9e9cb4637fd55d2fc0d62835518da20abc2600418d2bd60441457ba61c52ee88",
    ),
    (
        "systemd",
        "old",
        "259.9-0ubuntu0.1",
        3137006,
        "f4189a9737929afa8c7e9fcb3cc86ec4d93982477d272c55e67fb4e34a0a13b8",
    ),
    (
        "systemd",
        "new",
        "259.9-0ubuntu0.1+p4gentmp2",
        3337212,
        "6555069c0c2425eb22c1efadc92e23c30ce906ae3edcf1dbd7c62d2653a2e146",
    ),
];
const GDM_POSTINST: &str = "0003d9b9ac759e3d5b138c488a63c1e3aed7ed76fe15f1f425278b27a4b55e14";
const SYSTEMD_PREINST: &str = "6c1c399ae1b8c96b94115e4602133ab5bb9c4d32690255f521a5eab0b56693a2";
fn pin_eq(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(in crate::cold_original_qualification) enum NativeOperation {
    Install,
    Rollback,
}
impl NativeOperation {
    fn command(self) -> &'static str {
        match self {
            Self::Install => "native-apply",
            Self::Rollback => "native-rollback",
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Namespace {
    directories: BTreeMap<PathBuf, DirectoryState>,
    objects: BTreeMap<PathBuf, Option<Node>>,
    display_configuration: Node,
}

fn selected_paths(system: &Path) -> [PathBuf; 3] {
    [
        system.join(DISPLAY),
        system.join(TMP),
        system.join("local-fs.target.wants").join(TMP),
    ]
}
fn checked_default() -> Result<Node> {
    ensure(
        observe(Path::new("/etc/X11/default-display-manager.debconf-update"))?.is_none(),
        "pending display-manager reconfiguration is outside native upgrade custody",
    )?;
    let n = observe(Path::new(DEFAULT_DM))?.ok_or("original default display manager absent")?;
    ensure(
        FileType::from_raw_mode(n.identity.mode) == FileType::RegularFile
            && n.identity.mode & 0o7777 == 0o644
            && n.identity.size == 15
            && n.sha256.as_deref() == Some(DEFAULT_DM_SHA),
        "normal GDM selection differs",
    )?;
    Ok(n)
}
fn checked_gdm_unit() -> Result<()> {
    let alias = observe(Path::new("/usr/lib/systemd/system/gdm3.service"))?
        .ok_or("normal GDM service alias absent")?;
    ensure(
        alias.link.as_deref() == Some("gdm.service"),
        "normal GDM unit alias differs",
    )?;
    let unit = observe(Path::new("/usr/lib/systemd/system/gdm.service"))?
        .ok_or("normal GDM target unit absent")?;
    ensure(
        unit.identity.mode & 0o7777 == 0o644
            && unit.identity.size == 1185
            && unit.sha256.as_deref() == Some(GDM_UNIT_SHA),
        "normal GDM target unit bytes differ",
    )
}
fn capture_namespace(
    system: &Path,
    display_configuration: Node,
) -> Result<(Namespace, Vec<HeldDirectory>)> {
    let main = DirectoryState::capture(system)?;
    let wants = system.join("local-fs.target.wants");
    let has_wants = main.state.members.contains_key("local-fs.target.wants");
    let mut held = vec![main];
    if has_wants {
        held.push(DirectoryState::capture(&wants)?);
    }
    let mut objects = BTreeMap::new();
    for path in selected_paths(system) {
        let node = if path.parent() == Some(wants.as_path()) && !has_wants {
            None
        } else {
            observe(&path)?
        };
        objects.insert(path, node);
    }
    let directories = held
        .iter()
        .map(|d| (d.state.path.clone(), d.state.clone()))
        .collect();
    let result = Namespace {
        directories,
        objects,
        display_configuration,
    };
    for h in &held {
        ensure(
            DirectoryState::held(&h.state.path, &h.file)? == h.state,
            "native package parent changed during full capture",
        )?;
    }
    validate_namespace(&result, system)?;
    Ok((result, held))
}
fn validate_namespace(n: &Namespace, system: &Path) -> Result<()> {
    ensure(
        n.directories.contains_key(system) && n.directories.len() <= 2,
        "native configuration parent roster differs",
    )?;
    let wants = system.join("local-fs.target.wants");
    ensure(
        n.directories.keys().all(|p| p == system || p == &wants)
            && n.objects.keys().cloned().collect::<BTreeSet<_>>() == selected_paths(system).into(),
        "native configuration scope escaped fixed parents",
    )?;
    for (p, d) in &n.directories {
        ensure(&d.path == p, "native parent path mismatch")?;
    }
    for (path, node) in &n.objects {
        let member = n
            .directories
            .get(path.parent().ok_or("native object parent")?)
            .and_then(|d| d.members.get(path.file_name()?.to_str()?));
        match (member, node) {
            (None, None) => {}
            (Some(m), Some(v)) => ensure(
                m.identity == v.identity && m.handle == v.handle && m.handle_type == v.handle_type,
                "native object differs from complete parent inventory",
            )?,
            _ => return Err("native object presence differs from parent inventory".into()),
        }
    }
    if let Some(d) = n.directories.get(&wants) {
        let m = n.directories[system]
            .members
            .get("local-fs.target.wants")
            .ok_or("native wants parent disappeared")?;
        ensure(
            m.identity == d.identity && m.handle == d.handle && m.handle_type == d.handle_type,
            "native nested parent is not its actual generation",
        )?;
    } else {
        ensure(
            !n.directories[system]
                .members
                .contains_key("local-fs.target.wants"),
            "native wants parent not fully captured",
        )?;
    }
    Ok(())
}
fn ordinary_link(n: &Node, target: &str) -> bool {
    FileType::from_raw_mode(n.identity.mode) == FileType::Symlink
        && n.identity.uid == 0
        && n.identity.gid == 0
        && n.identity.nlink == 1
        && n.identity.mode & 0o7777 == 0o777
        && n.identity.size == target.len() as u64
        && n.link.as_deref() == Some(target)
        && n.sha256.is_none()
}
fn directory_delta(
    before: &DirectoryState,
    after: &DirectoryState,
    wanted: BTreeMap<String, MemberIdentity>,
    direct_child_change: bool,
) -> Result<()> {
    ensure(
        after.path == before.path
            && after.handle_type == before.handle_type
            && after.handle == before.handle
            && after.attributes == before.attributes
            && after.members == wanted,
        "normal native package changed an unrelated parent/member",
    )?;
    let mut id = after.identity.clone();
    if direct_child_change {
        ensure(
            wanted != before.members,
            "parent clock derivation needs a real direct child change",
        )?;
        // Only a fully accounted child removal/replacement explains clocks
        // and directory storage size. No subdirectory is created or removed.
        id.size = before.identity.size;
        id.mtime_sec = before.identity.mtime_sec;
        id.mtime_nsec = before.identity.mtime_nsec;
        id.ctime_sec = before.identity.ctime_sec;
        id.ctime_nsec = before.identity.ctime_nsec;
    }
    ensure(
        id == before.identity,
        "native parent-only drift or owner/mode/link/generation change",
    )
}
fn as_member(n: &Node) -> MemberIdentity {
    MemberIdentity {
        identity: n.identity.clone(),
        handle_type: n.handle_type,
        handle: n.handle.clone(),
    }
}

/// Check the actual finite script effects. `complete` is derived solely from
/// the real command chain by the caller below; either branch enforces every
/// unrelated inode and complete parent inventory. Incomplete observations
/// remain recovery metadata and never become package-completion evidence.
fn effects(
    before: &Namespace,
    after: &Namespace,
    system: &Path,
    complete: bool,
) -> Result<Vec<Value>> {
    validate_namespace(before, system)?;
    validate_namespace(after, system)?;
    ensure(
        before.display_configuration == after.display_configuration
            && before.directories.keys().eq(after.directories.keys()),
        "normal native upgrade changed display selection or parent namespace",
    )?;
    let [display, tmp, wanted_tmp] = selected_paths(system);
    let mut changes = Vec::new();
    let old_display = before.objects[&display].as_ref();
    let new_display = after.objects[&display].as_ref();
    match (old_display, new_display) {
        (Some(old), Some(new)) if ordinary_link(old, "/dev/null") =>
            ensure(old == new, "normal GDM postinst must preserve a display-manager mask")?,
        (Some(old), Some(new)) if ordinary_link(old, GDM_LINK) => {
            ensure(ordinary_link(new, GDM_LINK) && old.attributes == new.attributes,
                "normal GDM alias acquired another target, attributes or metadata")?;
            if old != new {
                ensure(!same_inode(old, new), "normal GDM alias drift is not a fresh symlink generation")?;
                changes.push(json!({"path":display,"effect":"gdm-postinst-same-target-replacement","script_sha256":GDM_POSTINST}));
            } else { ensure(!complete, "completed normal GDM configure did not produce its expected link")?; }
        },
        (Some(old), None) if ordinary_link(old, GDM_LINK) && !complete =>
            changes.push(json!({"path":display,"effect":"interrupted-gdm-alias-removal","script_sha256":GDM_POSTINST})),
        // An absent alias can only enter a rollback capture through a previous
        // sealed interrupted effect (checked by capture/reopen, never guessed).
        (None, Some(new)) if ordinary_link(new, GDM_LINK) =>
            changes.push(json!({"path":display,"effect":"gdm-postinst-interrupted-alias-recreation","script_sha256":GDM_POSTINST})),
        (None, None) if !complete => {},
        _ => return Err("normal GDM alias is outside the selected existing/masked link".into()),
    }
    let remove_main = before.objects[&tmp]
        .as_ref()
        .is_some_and(|n| ordinary_link(n, OLD_TMP));
    let remove_wants = remove_main
        || before.objects[&wanted_tmp]
            .as_ref()
            .is_some_and(|n| ordinary_link(n, OLD_TMP));
    for (path, permitted) in [(&tmp, remove_main), (&wanted_tmp, remove_wants)] {
        let old = &before.objects[path];
        let new = &after.objects[path];
        if old != new {
            ensure(
                permitted && old.is_some() && new.is_none(),
                "native tmp.mount change lacks its exact preinst predicate",
            )?;
            changes.push(json!({"path":path,"effect":"systemd-preinst-old-example-removal","script_sha256":SYSTEMD_PREINST}));
        } else if complete && permitted {
            ensure(
                old.is_none(),
                "completed native preinst left its selected obsolete tmp.mount",
            )?;
        }
    }
    let wants = system.join("local-fs.target.wants");
    let mut main_expected = before.directories[system].members.clone();
    for path in [&display, &tmp] {
        if before.objects[path] != after.objects[path] {
            match &after.objects[path] {
                Some(n) => {
                    main_expected.insert(
                        path.file_name().unwrap().to_str().unwrap().into(),
                        as_member(n),
                    );
                }
                None => {
                    main_expected.remove(path.file_name().unwrap().to_str().unwrap());
                }
            }
        }
    }
    if let Some(old) = before.directories.get(&wants) {
        let new = &after.directories[&wants];
        let mut members = old.members.clone();
        if before.objects[&wanted_tmp] != after.objects[&wanted_tmp] {
            members.remove(TMP);
        }
        directory_delta(
            old,
            new,
            members,
            before.objects[&wanted_tmp] != after.objects[&wanted_tmp],
        )?;
        if old != new {
            main_expected.insert(
                "local-fs.target.wants".into(),
                MemberIdentity {
                    identity: new.identity.clone(),
                    handle_type: new.handle_type,
                    handle: new.handle.clone(),
                },
            );
        }
    }
    directory_delta(
        &before.directories[system],
        &after.directories[system],
        main_expected,
        before.objects[&display] != after.objects[&display]
            || before.objects[&tmp] != after.objects[&tmp],
    )?;
    Ok(changes)
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ParentIntent {
    schema: String,
    candidate_id: String,
    owner_intent: FilePin,
    operation: NativeOperation,
    command_name: String,
    input_path: PathBuf,
    result_path: PathBuf,
    native_snapshot: FilePin,
    retained_snapshot: FilePin,
    attempt: String,
    materials: Value,
    native_release: FilePin,
    native_release_id: String,
    source_archives: Vec<FilePin>,
    prior: Option<FilePin>,
    before: Namespace,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ParentObservation {
    schema: String,
    before: FilePin,
    input: Option<FilePin>,
    command_result: Option<FilePin>,
    scope: String,
    effects: Vec<Value>,
    after: Namespace,
}

/// No public constructor, deserializer or caller-provided success bit. This
/// object only authorizes replay of the exact observed directory delta; the
/// normal package engine separately proves the complete package database.
pub(in crate::cold_original_qualification) struct Changes {
    intent: ParentIntent,
    observation: ParentObservation,
    source: SealedInput,
    guards: Vec<EvidenceGuard>,
    log: Option<CommandLog>,
}

// run_logged deliberately keeps its actual stdout/stderr at 0600. Bind that
// unchanged inode without pretending it is a 0400 SealedInput or weakening
// the latter's contract. It lives in the excluded private evidence tree.
struct CommandLog {
    pin: FilePin,
    held: File,
    identity: Identity,
}
impl CommandLog {
    fn open(pin: &FilePin, expected: &Path) -> Result<Self> {
        ensure(
            pin.path == expected && pin.bytes <= 64 * 1024 * 1024,
            "native stdout escaped its exact fixed command",
        )?;
        fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&pin.path)?)?;
        let (held, identity) = files::open_pin(pin)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode & 0o7777 == 0o600,
            "actual native stdout custody",
        )?;
        let value = Self {
            pin: pin.clone(),
            held,
            identity,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        let (named, id) = files::open_pin(&self.pin)?;
        let mut body = &self.held;
        body.rewind()?;
        ensure(
            id == self.identity
                && fs::stat(&self.held)? == self.identity
                && fs::xattrs(&self.held)?.is_empty()
                && fs::xattrs(&named)?.is_empty()
                && fs::hash(body)? == self.pin.sha256
                && fs::stat(&self.held)? == self.identity,
            "actual native stdout changed after normal command",
        )
    }
    fn read(&self) -> Result<Value> {
        self.revalidate()?;
        let value = serde_json::from_slice(&files::read_pin(&self.pin, 64 * 1024 * 1024)?)?;
        self.revalidate()?;
        Ok(value)
    }
}
pub(in crate::cold_original_qualification) struct Capture {
    intent: ParentIntent,
    source: SealedInput,
    guards: Vec<EvidenceGuard>,
    held: Vec<HeldDirectory>,
}

// Normal publication deliberately uses 0444, while per-attempt private
// evidence is 0400. Preserve the existing SealedInput contract unchanged.
struct NormalSource {
    pin: FilePin,
    held: File,
    identity: Identity,
}
impl NormalSource {
    fn open(pin: &FilePin) -> Result<Self> {
        ensure(
            pin.bytes > 0 && pin.bytes <= 128 * 1024 * 1024,
            "bounded normal native source",
        )?;
        fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&pin.path)?)?;
        let (held, identity) = files::open_pin(pin)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && [0o400, 0o444].contains(&(identity.mode & 0o7777)),
            "normal native source is not root-owned readonly publication",
        )?;
        let result = Self {
            pin: pin.clone(),
            held,
            identity,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> Result<()> {
        let named = fs::Tree::open("/", 0)?.file(&fs::absolute_string(&self.pin.path)?)?;
        ensure(
            fs::stat(&self.held)? == self.identity
                && fs::stat(&named)? == self.identity
                && fs::xattrs(&self.held)?.is_empty()
                && fs::xattrs(&named)?.is_empty(),
            "normal native source lost held/named metadata or attributes custody",
        )?;
        (&self.held).rewind()?;
        ensure(
            fs::hash(&self.held)? == self.pin.sha256
                && fs::stat(&self.held)? == self.identity
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&self.pin.path)?)?
                    == self.identity,
            "normal native source changed its bytes or inode",
        )
    }
    fn read(&self) -> Result<Vec<u8>> {
        self.revalidate()?;
        let b = files::read_pin(&self.pin, self.pin.bytes)?;
        self.revalidate()?;
        Ok(b)
    }
}
enum EvidenceGuard {
    Private(SealedInput),
    Normal(NormalSource),
}
impl EvidenceGuard {
    fn revalidate(&self) -> Result<()> {
        match self {
            Self::Private(v) => v.revalidate(),
            Self::Normal(v) => v.revalidate(),
        }
    }
}

fn command_name_ok(name: &str, operation: NativeOperation) -> bool {
    name.strip_prefix("dispatch-")
        .and_then(|s| s.strip_suffix(&format!("-{}", operation.command())))
        .is_some_and(|n| n.len() == 4 && n.bytes().all(|b| b.is_ascii_digit()))
}
fn attempt_ok(attempt: &str, release: &str) -> bool {
    attempt
        .strip_prefix(release)
        .and_then(|s| s.strip_prefix('-'))
        .is_some_and(|s| {
            s.len() == 16
                && s.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        })
}
fn source_archives(release: &FilePin, index: &Value) -> Result<Vec<FilePin>> {
    ensure(
        index["schema"] == "droidloom-original-host-native-package-release-v1"
            && index["package_roles"]
                .as_array()
                .is_some_and(|a| a.len() == 22),
        "native parent effects require the exact original-host package profile",
    )?;
    let rows = index["package_roles"]
        .as_array()
        .ok_or("native package roles")?;
    let parent = release.path.parent().ok_or("native package root")?;
    let mut names = BTreeSet::new();
    for row in rows {
        ensure(
            names.insert(row["name"].as_str().ok_or("native package name")?),
            "duplicate native package name",
        )?;
    }
    let mut pins = Vec::new();
    for (name, side, version, bytes, sha) in ARCHIVES {
        let row = rows
            .iter()
            .find(|r| r["name"] == name)
            .ok_or("audited native package absent")?;
        ensure(
            row[format!("{side}_version")] == version,
            "native script version is not the audited normal source",
        )?;
        let p = &row[side]["package"];
        let relative = p["path"].as_str().ok_or("normal package path")?;
        let expected = match (name, side) {
            ("gdm3", "old") => "native-five/old-gdm.deb",
            ("gdm3", "new") => "native-five/new-gdm.deb",
            ("systemd", "old") => "systemd/systemd-old.deb",
            ("systemd", "new") => "systemd/systemd-new.deb",
            _ => return Err("unselected package effect".into()),
        };
        ensure(
            relative == expected && p["bytes"].as_u64() == Some(bytes) && p["sha256"] == sha,
            "native maintainer-script archive differs",
        )?;
        pins.push(FilePin {
            path: parent.join(relative),
            bytes,
            sha256: sha.into(),
        });
    }
    Ok(pins)
}
fn actual_materials(a: &OriginalQualificationAuthority) -> Result<Value> {
    let report: Value =
        serde_json::from_slice(&files::read_pin(a.materials.report(), 128 * 1024 * 1024)?)?;
    let materials = report["normal_initramfs"]["normal_materials"].clone();
    ensure(materials.is_object(), "normal admitted materials absent")?;
    Ok(materials)
}
fn validate_snapshot(i: &ParentIntent, value: &Value) -> Result<()> {
    let root = fs::stat(&File::open("/")?)?;
    ensure(
        value["schema"] == "droidloom-normal-native-snapshot-v1"
            && value["release_id"] == i.native_release_id
            && value["root_identity"] == json!([root.dev, root.ino]),
        "native package snapshot belongs to another root/release",
    )?;
    ensure(
        value["public_configs"].is_object()
            && value["all_packages"].is_object()
            && value["private_metadata"].is_object(),
        "incomplete normal native snapshot",
    )
}
fn validate_intent(i: &ParentIntent, source: &FilePin, work: &Path) -> Result<()> {
    ensure(
        i.schema == "droidloom.original-native-package-parent-intent.v1"
            && command_name_ok(&i.command_name, i.operation)
            && attempt_ok(&i.attempt, &i.native_release_id),
        "native parent intent format",
    )?;
    let dir = work.join("native-package-parents").join(&i.command_name);
    ensure(
        source.path == dir.join("BEFORE.json")
            && i.retained_snapshot.path == dir.join("NATIVE-SNAPSHOT.json")
            && i.retained_snapshot.bytes == i.native_snapshot.bytes
            && i.retained_snapshot.sha256 == i.native_snapshot.sha256
            && i.input_path
                == work
                    .join("commands")
                    .join(&i.command_name)
                    .join("INPUTS.json")
            && i.result_path
                == work
                    .join("commands")
                    .join(&i.command_name)
                    .join("RESULT.json")
            && i.native_snapshot.path
                == Path::new("/var/lib/droidloom-maintenance/native-transactions")
                    .join(&i.attempt)
                    .join("SNAPSHOT.json")
            && i.materials["native_release"] == serde_json::to_value(&i.native_release)?
            && i.materials["native_release_id"] == i.native_release_id,
        "native parent command/snapshot/source paths differ",
    )?;
    validate_namespace(&i.before, Path::new(SYSTEM))
}
fn intent_sources(i: &ParentIntent) -> Result<Vec<EvidenceGuard>> {
    let release = NormalSource::open(&i.native_release)?;
    let index: Value = serde_json::from_slice(&release.read()?)?;
    ensure(
        index["release_id"] == i.native_release_id
            && serde_json::to_value(source_archives(&i.native_release, &index)?)?
                == serde_json::to_value(&i.source_archives)?,
        "native parent normal source closure differs",
    )?;
    let retained = SealedInput::open(&i.retained_snapshot)?;
    let snapshot: Value = serde_json::from_slice(&retained.read()?)?;
    validate_snapshot(i, &snapshot)?;
    ensure(
        snapshot["closure_sha256"] == index["closure_sha256"],
        "native snapshot and normal archive closure differ",
    )?;
    let mut guards = vec![
        EvidenceGuard::Normal(release),
        EvidenceGuard::Private(retained),
    ];
    for p in &i.source_archives {
        guards.push(EvidenceGuard::Normal(NormalSource::open(p)?));
    }
    Ok(guards)
}
fn check_prior(i: &ParentIntent, prior: Option<&Changes>) -> Result<()> {
    let display = Path::new(SYSTEM).join(DISPLAY);
    match i.before.objects[&display].as_ref() {
        Some(n) => ensure(
            i.prior.is_none()
                && prior.is_none()
                && (ordinary_link(n, GDM_LINK) || ordinary_link(n, "/dev/null")),
            "native initial display alias has no audited source predicate",
        ),
        None => {
            let p = prior.ok_or("absent GDM alias lacks durable interrupted lineage")?;
            p.revalidate()?;
            ensure(
                i.prior.as_ref().is_some_and(|q| pin_eq(q, p.pin()))
                    && p.observation.scope == "interrupted-parent-metadata-only"
                    && p.intent.candidate_id == i.candidate_id
                    && pin_eq(&p.intent.owner_intent, &i.owner_intent)
                    && pin_eq(&p.intent.native_snapshot, &i.native_snapshot)
                    && p.intent.attempt == i.attempt
                    && pin_eq(&p.intent.native_release, &i.native_release)
                    && p.observation.after == i.before
                    && (p
                        .observation
                        .effects
                        .iter()
                        .any(|e| e["effect"] == "interrupted-gdm-alias-removal")
                        || p.intent.prior.is_some()),
                "absent alias is not the exact prior interrupted normal package effect",
            )
        }
    }
}
fn check_owner(a: &OriginalQualificationAuthority, i: &ParentIntent) -> Result<()> {
    a.verify_current_owner()?;
    ensure(
        i.candidate_id == a.candidate_id()
            && pin_eq(&i.owner_intent, a.intent.pin())
            && i.materials == actual_materials(a)?,
        "native parent observation belongs to another authority",
    )
}
fn private_parent(work: &Path) -> Result<PathBuf> {
    let parent = work.join("native-package-parents");
    match std::fs::symlink_metadata(&parent) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            files::private_dir(&parent)?;
            File::open(work)?.sync_all()?;
        }
        Err(e) => return Err(e.into()),
        Ok(_) => {}
    }
    let tree = fs::Tree::open(&fs::absolute_string(&parent)?, 0)?;
    let id = fs::stat(&tree.root)?;
    ensure(
        id.uid == 0 && id.gid == 0 && id.mode & 0o7777 == 0o700,
        "native parent evidence directory custody",
    )?;
    Ok(parent)
}

pub(in crate::cold_original_qualification) fn capture(
    a: &OriginalQualificationAuthority,
    operation: NativeOperation,
    snapshot: &FilePin,
    attempt: &str,
    command_name: &str,
    prior: Option<&Changes>,
) -> Result<Capture> {
    a.verify_current_owner()?;
    ensure(
        command_name_ok(command_name, operation),
        "fixed native command attempt required",
    )?;
    let command_dir = a.work().join("commands").join(command_name);
    ensure(
        !command_dir.try_exists()?,
        "native command already started before parent preimage",
    )?;
    let materials = actual_materials(a)?;
    let native_release: FilePin = serde_json::from_value(materials["native_release"].clone())?;
    let release_id = materials["native_release_id"]
        .as_str()
        .ok_or("native release ID")?
        .to_owned();
    ensure(
        attempt_ok(attempt, &release_id)
            && snapshot.path
                == Path::new("/var/lib/droidloom-maintenance/native-transactions")
                    .join(attempt)
                    .join("SNAPSHOT.json"),
        "native snapshot attempt does not belong to admitted release",
    )?;
    let original_snapshot = SealedInput::open(snapshot)?;
    let release_guard = NormalSource::open(&native_release)?;
    let index: Value = serde_json::from_slice(&release_guard.read()?)?;
    let archives = source_archives(&native_release, &index)?;
    checked_gdm_unit()?;
    let (before, held) = capture_namespace(Path::new(SYSTEM), checked_default()?)?;
    let display = Path::new(SYSTEM).join(DISPLAY);
    if before.objects[&display].is_none() {
        let p = prior.ok_or("absent GDM alias lacks its earlier interrupted normal operation")?;
        p.revalidate()?;
        ensure(
            p.observation.scope == "interrupted-parent-metadata-only"
                && p.intent.candidate_id == a.candidate_id()
                && pin_eq(&p.intent.owner_intent, a.intent.pin())
                && pin_eq(&p.intent.native_snapshot, snapshot)
                && p.intent.attempt == attempt
                && pin_eq(&p.intent.native_release, &native_release)
                && p.observation.after == before
                && (p
                    .observation
                    .effects
                    .iter()
                    .any(|e| e["effect"] == "interrupted-gdm-alias-removal")
                    || p.intent.prior.is_some()),
            "absent GDM alias is not the exact recorded interrupted normal replacement",
        )?;
    } else {
        let n = before.objects[&display].as_ref().ok_or("display link")?;
        ensure(
            ordinary_link(n, GDM_LINK) || ordinary_link(n, "/dev/null"),
            "existing display alias is neither the normal GDM link nor a mask",
        )?;
        ensure(
            prior.is_none(),
            "unnecessary unrelated interrupted parent provenance",
        )?;
    }
    let dir = private_parent(a.work())?.join(command_name);
    files::private_dir(&dir)?;
    File::open(dir.parent().ok_or("parent evidence root")?)?.sync_all()?;
    files::copy_pin(snapshot, &dir.join("NATIVE-SNAPSHOT.json"), 0o400)?;
    let retained_snapshot = files::pin_file(&dir.join("NATIVE-SNAPSHOT.json"))?;
    let intent = ParentIntent {
        schema: "droidloom.original-native-package-parent-intent.v1".into(),
        candidate_id: a.candidate_id().into(),
        owner_intent: a.intent.pin().clone(),
        operation,
        command_name: command_name.into(),
        input_path: command_dir.join("INPUTS.json"),
        result_path: command_dir.join("RESULT.json"),
        native_snapshot: snapshot.clone(),
        retained_snapshot,
        attempt: attempt.into(),
        materials,
        native_release,
        native_release_id: release_id,
        source_archives: archives,
        prior: prior.map(|p| p.source.pin().clone()),
        before,
    };
    let guards = intent_sources(&intent)?;
    check_prior(&intent, prior)?;
    let pin = write_json(&dir.join("BEFORE.json"), &intent)?;
    validate_intent(&intent, &pin, a.work())?;
    original_snapshot.revalidate()?;
    release_guard.revalidate()?;
    ensure(
        checked_default()? == intent.before.display_configuration,
        "display configuration changed before durable native capture",
    )?;
    checked_gdm_unit()?;
    for h in &held {
        ensure(
            DirectoryState::held(&h.state.path, &h.file)? == h.state,
            "configuration changed while native preimage was being made durable",
        )?;
    }
    check_owner(a, &intent)?;
    Ok(Capture {
        intent,
        source: SealedInput::open(&pin)?,
        guards,
        held,
    })
}

fn validate_input(i: &ParentIntent, input: &Value) -> Result<()> {
    ensure(
        input["schema"] == "droidloom.original-once-fixed-command.v1"
            && input["candidate_id"] == i.candidate_id
            && input["intent"] == serde_json::to_value(&i.owner_intent)?
            && input["operation"] == i.operation.command()
            && input["materials"] == i.materials,
        "actual native command input differs from durable parent intent",
    )?;
    let args = input["arguments"]
        .as_object()
        .ok_or("actual native arguments")?;
    let keys = args.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = if i.operation == NativeOperation::Install {
        BTreeSet::from(["attempt", "snapshot"])
    } else {
        BTreeSet::from(["attempt", "snapshot", "restored_metadata"])
    };
    ensure(
        keys == expected
            && args["snapshot"] == serde_json::to_value(&i.native_snapshot)?
            && args["attempt"] == i.attempt,
        "actual native command used a different snapshot/attempt",
    )?;
    if let Some(v) = args.get("restored_metadata").filter(|v| !v.is_null()) {
        let _: FilePin = serde_json::from_value(v.clone())?;
    }
    Ok(())
}
fn validate_result(i: &ParentIntent, input: &FilePin, result: &Value, raw: &Value) -> Result<()> {
    ensure(
        result["schema"] == "droidloom.original-once-command-evidence.v1"
            && result["input"] == serde_json::to_value(input)?
            && result["actual"] == *raw
            && result["command"]["exit_code"] == 0
            && result["command"]["timed_out"] == false,
        "native result lacks its actual successful normal command",
    )?;
    ensure(
        raw["schema"] == "droidloom.original-once-fixed-command-result.v1"
            && raw["candidate_id"] == i.candidate_id
            && raw["operation"] == i.operation.command()
            && raw["intent"] == serde_json::to_value(&i.owner_intent)?,
        "native stdout belongs to another transaction",
    )?;
    let tx = &raw["result"];
    ensure(
        tx["kind"] == "native"
            && tx["attempt"] == i.attempt
            && tx["snapshot"] == serde_json::to_value(&i.native_snapshot)?
            && tx["directory"]
                == serde_json::to_value(
                    i.native_snapshot
                        .path
                        .parent()
                        .ok_or("native snapshot parent")?,
                )?,
        "normal native result used another actual package transaction",
    )?;
    let events = tx["events"]
        .as_array()
        .ok_or("normal native durable events absent")?;
    ensure(
        !events.is_empty() && events.len() <= 64,
        "normal native event bound",
    )?;
    for (n, e) in events.iter().enumerate() {
        ensure(
            e["schema"] == "droidloom-normal-native-event-v1"
                && e["attempt"] == i.attempt
                && e["sequence"].as_u64() == Some((n + 1) as u64),
            "normal native event sequence differs",
        )?;
    }
    let expected = if i.operation == NativeOperation::Install {
        "normal-native-installed"
    } else {
        "normal-native-rolled-back"
    };
    ensure(
        events.last().is_some_and(|e| e["stage"] == expected),
        "normal native command did not reach its source-owned completion event",
    )
}

impl Capture {
    pub(in crate::cold_original_qualification) fn before_pin(&self) -> &FilePin {
        self.source.pin()
    }
    pub(in crate::cold_original_qualification) fn reopen(
        a: &OriginalQualificationAuthority,
        name: &str,
    ) -> Result<Self> {
        ensure(
            [NativeOperation::Install, NativeOperation::Rollback]
                .iter()
                .any(|op| command_name_ok(name, *op)),
            "fixed native command name required",
        )?;
        let pin = files::pin_file(
            &a.work()
                .join("native-package-parents")
                .join(name)
                .join("BEFORE.json"),
        )?;
        let source = SealedInput::open(&pin)?;
        let intent: ParentIntent = serde_json::from_slice(&source.read()?)?;
        validate_intent(&intent, &pin, a.work())?;
        check_owner(a, &intent)?;
        let guards = intent_sources(&intent)?;
        let prior = intent
            .prior
            .as_ref()
            .map(|p| Changes::reopen_depth(a, p, 0))
            .transpose()?;
        check_prior(&intent, prior.as_ref())?;
        // Reopening a preimage never requires unchanged children: a crashed
        // native command may already have performed exactly the audited work.
        let mut held = Vec::new();
        for old in intent.before.directories.values() {
            let h = DirectoryState::capture(&old.path)?;
            ensure(
                h.state.handle == old.handle
                    && h.state.handle_type == old.handle_type
                    && h.state.identity.dev == old.identity.dev
                    && h.state.identity.ino == old.identity.ino,
                "native parent replaced across interruption",
            )?;
            held.push(h);
        }
        Ok(Self {
            intent,
            source,
            guards,
            held,
        })
    }
    pub(in crate::cold_original_qualification) fn finish(
        self,
        a: &OriginalQualificationAuthority,
        command: &CommandEvidence,
    ) -> Result<Changes> {
        ensure(
            command.pin.path == self.intent.result_path,
            "native parent result path differs",
        )?;
        self.observe_result(a, Some(command))
    }
    pub(in crate::cold_original_qualification) fn reconcile_interrupted(
        self,
        a: &OriginalQualificationAuthority,
    ) -> Result<Changes> {
        if self.intent.result_path.try_exists()? {
            let pin = files::pin_file(&self.intent.result_path)?;
            let seal = SealedInput::open(&pin)?;
            let value: Value = serde_json::from_slice(&seal.read()?)?;
            let actual = CommandEvidence {
                pin,
                report: value["actual"]["result"].clone(),
            };
            // This is not a fabricated completion: observe_result reopens the
            // real INPUTS, stdout and complete terminal result below.
            self.observe_result(a, Some(&actual))
        } else {
            self.observe_result(a, None)
        }
    }
    fn observe_result(
        self,
        a: &OriginalQualificationAuthority,
        command: Option<&CommandEvidence>,
    ) -> Result<Changes> {
        check_owner(a, &self.intent)?;
        self.source.revalidate()?;
        for g in &self.guards {
            g.revalidate()?;
        }
        let observed_path = self.source.pin().path.with_file_name("OBSERVATION.json");
        if observed_path.try_exists()? {
            let previous = Changes::reopen(a, &files::pin_file(&observed_path)?)?;
            ensure(
                pin_eq(&previous.observation.before, self.source.pin())
                    && match (previous.observation.command_result.as_ref(), command) {
                        (Some(old), Some(new)) => pin_eq(old, &new.pin),
                        (None, None) => true,
                        _ => false,
                    },
                "existing native observation belongs to a different command outcome",
            )?;
            let (now, _) = capture_namespace(Path::new(SYSTEM), checked_default()?)?;
            ensure(
                now == previous.observation.after,
                "native namespace evolved after a durable unacknowledged observation",
            )?;
            check_owner(a, &self.intent)?;
            return Ok(previous);
        }
        let mut guards = self.guards;
        let input_pin = match std::fs::symlink_metadata(&self.intent.input_path) {
            Ok(_) => {
                let p = files::pin_file(&self.intent.input_path)?;
                let g = SealedInput::open(&p)?;
                validate_input(&self.intent, &serde_json::from_slice(&g.read()?)?)?;
                guards.push(EvidenceGuard::Private(g));
                Some(p)
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ensure(
                    command.is_none() && command_not_started(&self.intent)?,
                    "native input missing after command activity",
                )?;
                None
            }
            Err(e) => return Err(e.into()),
        };
        let mut log_guard = None;
        if let Some(c) = command {
            let g = SealedInput::open(&c.pin)?;
            let result: Value = serde_json::from_slice(&g.read()?)?;
            let log: FilePin = serde_json::from_value(result["command"]["log"].clone())?;
            let lg = CommandLog::open(
                &log,
                &self.intent.input_path.with_file_name("normal-command.log"),
            )?;
            let raw = lg.read()?;
            validate_result(
                &self.intent,
                input_pin
                    .as_ref()
                    .ok_or("completed command without input")?,
                &result,
                &raw,
            )?;
            ensure(
                raw["result"] == c.report,
                "supplied normal command report differs from actual stdout",
            )?;
            guards.push(EvidenceGuard::Private(g));
            log_guard = Some(lg);
        }
        checked_gdm_unit()?;
        let (after, after_held) = capture_namespace(Path::new(SYSTEM), checked_default()?)?;
        // The original open parent descriptors and newly resolved names must
        // still be the same generations after the complete source-bound delta.
        for h in &self.held {
            ensure(
                DirectoryState::held(&h.state.path, &h.file)? == after.directories[&h.state.path],
                "held native parent differs from its named readback",
            )?;
        }
        let actual_effects = if input_pin.is_some() {
            effects(
                &self.intent.before,
                &after,
                Path::new(SYSTEM),
                command.is_some(),
            )?
        } else {
            ensure(
                after == self.intent.before,
                "unstarted command cannot explain any namespace drift",
            )?;
            Vec::new()
        };
        let scope = if command.is_some() {
            "normal-command-parent-effects"
        } else if input_pin.is_some() {
            "interrupted-parent-metadata-only"
        } else {
            "not-started-parent-metadata-only"
        };
        let observation = ParentObservation {
            schema: "droidloom.original-native-package-parent-observation.v1".into(),
            before: self.source.pin().clone(),
            input: input_pin,
            command_result: command.map(|c| c.pin.clone()),
            scope: scope.into(),
            effects: actual_effects,
            after,
        };
        let path = self
            .source
            .pin()
            .path
            .parent()
            .ok_or("native parent work")?
            .join("OBSERVATION.json");
        let pin = write_json(&path, &observation)?;
        for h in &after_held {
            ensure(
                DirectoryState::held(&h.state.path, &h.file)? == h.state,
                "native namespace changed while readback became durable",
            )?;
        }
        self.source.revalidate()?;
        for g in &guards {
            g.revalidate()?;
        }
        ensure(
            checked_default()? == observation.after.display_configuration,
            "display configuration changed after native readback",
        )?;
        checked_gdm_unit()?;
        check_owner(a, &self.intent)?;
        guards.push(EvidenceGuard::Private(self.source));
        Ok(Changes {
            intent: self.intent,
            observation,
            source: SealedInput::open(&pin)?,
            guards,
            log: log_guard,
        })
    }
}

impl Changes {
    pub(in crate::cold_original_qualification) fn pin(&self) -> &FilePin {
        self.source.pin()
    }
    pub(in crate::cold_original_qualification) fn is_completed_command(&self) -> bool {
        self.observation.command_result.is_some()
    }
    fn revalidate(&self) -> Result<()> {
        self.source.revalidate()?;
        for g in &self.guards {
            g.revalidate()?;
        }
        if let Some(g) = &self.log {
            g.revalidate()?;
        }
        if self.observation.input.is_none() {
            ensure(
                self.observation.scope == "not-started-parent-metadata-only"
                    && self.observation.command_result.is_none()
                    && self.observation.effects.is_empty()
                    && self.intent.before == self.observation.after,
                "unstarted native parent observation changed",
            )
        } else {
            ensure(
                self.observation.scope
                    == if self.observation.command_result.is_some() {
                        "normal-command-parent-effects"
                    } else {
                        "interrupted-parent-metadata-only"
                    }
                    && self.observation.effects
                        == effects(
                            &self.intent.before,
                            &self.observation.after,
                            Path::new(SYSTEM),
                            self.observation.command_result.is_some(),
                        )?,
                "native parent effect report differs from full actual snapshots",
            )
        }
    }
    pub(in crate::cold_original_qualification) fn reopen(
        a: &OriginalQualificationAuthority,
        pin: &FilePin,
    ) -> Result<Self> {
        Self::reopen_depth(a, pin, 0)
    }
    fn reopen_depth(
        a: &OriginalQualificationAuthority,
        pin: &FilePin,
        depth: usize,
    ) -> Result<Self> {
        ensure(depth < 64, "native parent interrupted lineage bound")?;
        let source = SealedInput::open(pin)?;
        let observation: ParentObservation = serde_json::from_slice(&source.read()?)?;
        ensure(
            observation.schema == "droidloom.original-native-package-parent-observation.v1"
                && pin.path == observation.before.path.with_file_name("OBSERVATION.json"),
            "native parent observation schema/path",
        )?;
        let before_guard = SealedInput::open(&observation.before)?;
        let intent: ParentIntent = serde_json::from_slice(&before_guard.read()?)?;
        validate_intent(&intent, &observation.before, a.work())?;
        check_owner(a, &intent)?;
        let mut guards = intent_sources(&intent)?;
        let prior = intent
            .prior
            .as_ref()
            .map(|p| Self::reopen_depth(a, p, depth + 1))
            .transpose()?;
        check_prior(&intent, prior.as_ref())?;
        let mut log = None;
        if let Some(p) = &observation.input {
            ensure(
                p.path == intent.input_path,
                "native observed input escaped original command",
            )?;
            let g = SealedInput::open(p)?;
            validate_input(&intent, &serde_json::from_slice(&g.read()?)?)?;
            guards.push(EvidenceGuard::Private(g));
            if let Some(r) = &observation.command_result {
                ensure(
                    r.path == intent.result_path,
                    "native observed result escaped original command",
                )?;
                let g = SealedInput::open(r)?;
                let result: Value = serde_json::from_slice(&g.read()?)?;
                let lp: FilePin = serde_json::from_value(result["command"]["log"].clone())?;
                let lg =
                    CommandLog::open(&lp, &intent.input_path.with_file_name("normal-command.log"))?;
                validate_result(&intent, p, &result, &lg.read()?)?;
                log = Some(lg);
                guards.push(EvidenceGuard::Private(g));
            }
        }
        guards.push(EvidenceGuard::Private(before_guard));
        let result = Self {
            intent,
            observation,
            source,
            guards,
            log,
        };
        result.revalidate()?;
        Ok(result)
    }
    /// Compose verified bulk changes into the dispatcher checkpoint. Nested
    /// parent metadata is accounted once; no ancestor gets an unrelated clock
    /// waiver. This operation does not inspect a later, already evolved tree.
    pub(super) fn apply_to(&self, states: &mut BTreeMap<PathBuf, DirectoryState>) -> Result<()> {
        self.revalidate()?;
        for (path, before) in &self.intent.before.directories {
            if let Some(known) = states.get(path) {
                ensure(
                    known == before,
                    "normal native parent event does not extend exact configuration checkpoint",
                )?;
            }
        }
        for (path, before) in &self.intent.before.directories {
            if let Some(parent) = path
                .parent()
                .filter(|p| !self.intent.before.directories.contains_key(*p))
            {
                if let Some(ancestor) = states.get_mut(parent) {
                    let name = path
                        .file_name()
                        .and_then(|s| s.to_str())
                        .ok_or("native parent member name")?;
                    let m = ancestor
                        .members
                        .get_mut(name)
                        .ok_or("native parent missing from ancestor checkpoint")?;
                    ensure(
                        m.identity == before.identity
                            && m.handle == before.handle
                            && m.handle_type == before.handle_type,
                        "native parent ancestor generation changed",
                    )?;
                    m.identity = self.observation.after.directories[path].identity.clone();
                }
            }
        }
        states.extend(self.observation.after.directories.clone());
        Ok(())
    }
}

fn command_not_started(i: &ParentIntent) -> Result<bool> {
    if i.result_path.try_exists()? {
        return Ok(false);
    }
    let dir = i.input_path.parent().ok_or("native command directory")?;
    match std::fs::symlink_metadata(dir) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(true),
        Err(e) => Err(e.into()),
        Ok(_) => {
            let tree = fs::Tree::open(&fs::absolute_string(dir)?, 0)?;
            ensure(
                fs::stat(&tree.root)?.mode & 0o7777 == 0o700,
                "unstarted command directory custody",
            )?;
            // call() fsyncs INPUTS before starting any process. A present
            // partial input, log or result is not this no-command branch.
            Ok(std::fs::read_dir(dir)?.next().is_none())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;

    #[test]
    fn command_and_attempt_names_cannot_select_another_transaction() {
        assert!(command_name_ok(
            "dispatch-0000-native-apply",
            NativeOperation::Install
        ));
        assert!(command_name_ok(
            "dispatch-9999-native-rollback",
            NativeOperation::Rollback
        ));
        for name in [
            "native-apply",
            "dispatch-1-native-apply",
            "dispatch-0000-native-rollback",
            "dispatch-0000-native-apply/RESULT.json",
            "dispatch-0000-native-apply-extra",
        ] {
            assert!(!command_name_ok(name, NativeOperation::Install));
        }
        let release = "a".repeat(64);
        assert!(attempt_ok(&format!("{release}-0123456789abcdef"), &release));
        for suffix in [
            "",
            "-0123456789abcde",
            "-0123456789abcdeF",
            "-0123456789abcdef/child",
        ] {
            assert!(!attempt_ok(&format!("{release}{suffix}"), &release));
        }
    }
    fn test_pin(path: &str) -> FilePin {
        FilePin {
            path: path.into(),
            bytes: 1,
            sha256: "a".repeat(64),
        }
    }
    fn test_node() -> Node {
        let mut identity = files::clean_metadata(0o100644);
        identity.uid = 0;
        identity.gid = 0;
        identity.size = 15;
        Node {
            identity,
            handle_type: 1,
            handle: "0102030405060708".into(),
            attributes: BTreeMap::new(),
            sha256: Some(DEFAULT_DM_SHA.into()),
            link: None,
        }
    }
    fn test_intent() -> ParentIntent {
        ParentIntent {
            schema: "droidloom.original-native-package-parent-intent.v1".into(),
            candidate_id: "b".repeat(64),
            owner_intent: test_pin("/private/INTENT.json"),
            operation: NativeOperation::Install,
            command_name: "dispatch-0001-native-apply".into(),
            input_path: "/private/commands/dispatch-0001-native-apply/INPUTS.json".into(),
            result_path: "/private/commands/dispatch-0001-native-apply/RESULT.json".into(),
            native_snapshot: test_pin("/native/release-attempt/SNAPSHOT.json"),
            retained_snapshot: test_pin("/private/native/SNAPSHOT.json"),
            attempt: "release-attempt".into(),
            materials: json!({"native_release_id":"release"}),
            native_release: test_pin("/normal/NATIVE-RELEASE.json"),
            native_release_id: "release".into(),
            source_archives: Vec::new(),
            prior: None,
            before: Namespace {
                directories: BTreeMap::new(),
                objects: BTreeMap::new(),
                display_configuration: test_node(),
            },
        }
    }
    #[test]
    fn actual_input_is_bound_to_operation_attempt_source_and_snapshot() -> Result<()> {
        let i = test_intent();
        let input = json!({"schema":"droidloom.original-once-fixed-command.v1",
            "candidate_id":i.candidate_id,"intent":i.owner_intent,"operation":"native-apply",
            "materials":i.materials,"arguments":{"snapshot":i.native_snapshot,"attempt":i.attempt}});
        validate_input(&i, &input)?;
        for field in ["candidate_id", "operation", "intent", "materials"] {
            let mut bad = input.clone();
            bad[field] = json!("another");
            assert!(validate_input(&i, &bad).is_err(), "{field}");
        }
        for field in ["snapshot", "attempt"] {
            let mut bad = input.clone();
            bad["arguments"][field] = json!("another");
            assert!(validate_input(&i, &bad).is_err(), "{field}");
        }
        let mut bad = input.clone();
        bad["arguments"]["passed"] = json!(true);
        assert!(validate_input(&i, &bad).is_err());
        Ok(())
    }
    #[test]
    fn stdout_and_terminal_event_are_required_beyond_exit_zero() -> Result<()> {
        let i = test_intent();
        let input = test_pin("/private/INPUTS.json");
        let raw = json!({"schema":"droidloom.original-once-fixed-command-result.v1",
            "candidate_id":i.candidate_id,"operation":"native-apply","intent":i.owner_intent,
            "result":{"kind":"native","attempt":i.attempt,"snapshot":i.native_snapshot,
                "directory":i.native_snapshot.path.parent(),"events":[
                    {"schema":"droidloom-normal-native-event-v1","attempt":i.attempt,"sequence":1,"stage":"snapshot-complete"},
                    {"schema":"droidloom-normal-native-event-v1","attempt":i.attempt,"sequence":2,"stage":"normal-native-installed"}]}});
        let result = json!({"schema":"droidloom.original-once-command-evidence.v1","input":input,
            "command":{"exit_code":0,"timed_out":false},"actual":raw});
        validate_result(&i, &input, &result, &raw)?;
        let mut bad = raw.clone();
        bad["result"]["events"][1]["stage"] = json!("unpacked-new");
        let mut changed = result.clone();
        changed["actual"] = bad.clone();
        assert!(validate_result(&i, &input, &changed, &bad).is_err());
        let mut bad = raw.clone();
        bad["result"]["snapshot"]["sha256"] = json!("c".repeat(64));
        let mut changed = result.clone();
        changed["actual"] = bad.clone();
        assert!(validate_result(&i, &input, &changed, &bad).is_err());
        let mut changed = result.clone();
        changed["command"]["timed_out"] = json!(true);
        assert!(validate_result(&i, &input, &changed, &raw).is_err());
        assert!(validate_result(&i, &test_pin("/another/INPUTS.json"), &result, &raw).is_err());
        Ok(())
    }
    fn ln(system: &Path, target: &str, leaf: &str) -> Result<()> {
        ensure(
            Command::new("/usr/bin/ln")
                .args(["-sf", target])
                .arg(system.join(leaf))
                .status()?
                .success(),
            "isolated normal ln -sf failed",
        )
    }
    fn capture_test(system: &Path, default: &Path) -> Result<Namespace> {
        Ok(capture_namespace(system, observe(default)?.ok_or("isolated display config")?)?.0)
    }
    #[test]
    #[ignore = "requires root; only changes newly created isolated configuration test inodes"]
    fn actual_normal_symlink_effects_and_interrupted_reopen_are_finite() -> Result<()> {
        ensure(
            rustix::process::geteuid().is_root(),
            "root isolated test required",
        )?;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let root = PathBuf::from(format!(
            "/var/lib/droidloom-qualification/native-package-parent-test-{}-{stamp}",
            std::process::id()
        ));
        files::private_dir(&root)?;
        let system = root.join("system");
        files::private_dir(&system)?;
        let wants = system.join("local-fs.target.wants");
        files::private_dir(&wants)?;
        let default = root.join("default-display-manager");
        files::write_new(&default, b"/usr/sbin/gdm3\n", 0o644)?;
        files::write_new(
            &system.join("unrelated.service"),
            b"unchanged public unit",
            0o644,
        )?;
        ln(&system, GDM_LINK, DISPLAY)?;
        let before = capture_test(&system, &default)?;
        let durable = write_json(&root.join("BEFORE-ALIAS.json"), &before)?;
        ln(&system, GDM_LINK, DISPLAY)?;
        let after = capture_test(&system, &default)?;
        assert_eq!(effects(&before, &after, &system, true)?.len(), 1);
        assert_ne!(
            before.objects[&system.join(DISPLAY)],
            after.objects[&system.join(DISPLAY)]
        );
        let sealed = SealedInput::open(&durable)?;
        let reopened: Namespace = serde_json::from_slice(&sealed.read()?)?;
        assert_eq!(effects(&reopened, &after, &system, true)?.len(), 1);
        let mut fake = after.clone();
        fake.objects
            .get_mut(&system.join(DISPLAY))
            .ok_or("test alias")?
            .as_mut()
            .ok_or("test alias")?
            .link = Some("/foreign/service".into());
        assert!(effects(&before, &fake, &system, true).is_err());

        // Real interruption in the unlink->symlink interval, retaining and
        // reopening the durable preimage. This never reports command success.
        let interrupted_before = capture_test(&system, &default)?;
        let durable = write_json(&root.join("BEFORE-INTERRUPTED.json"), &interrupted_before)?;
        std::fs::remove_file(system.join(DISPLAY))?;
        let partial = capture_test(&system, &default)?;
        assert_eq!(
            effects(&interrupted_before, &partial, &system, false)?[0]["effect"],
            "interrupted-gdm-alias-removal"
        );
        assert!(effects(&interrupted_before, &partial, &system, true).is_err());
        drop(interrupted_before);
        let reopened: Namespace = serde_json::from_slice(&SealedInput::open(&durable)?.read()?)?;
        assert_eq!(effects(&reopened, &partial, &system, false)?.len(), 1);
        ln(&system, GDM_LINK, DISPLAY)?;
        let recreated = capture_test(&system, &default)?;
        assert_eq!(
            effects(&partial, &recreated, &system, true)?[0]["effect"],
            "gdm-postinst-interrupted-alias-recreation"
        );

        // Exact preinst predicate removes the example link and its wants
        // entry, including the observed regular-file case of rm -f.
        ln(&system, OLD_TMP, TMP)?;
        files::write_new(&wants.join(TMP), b"captured old wants entry", 0o644)?;
        let before = capture_test(&system, &default)?;
        std::fs::remove_file(system.join(TMP))?;
        let partial = capture_test(&system, &default)?;
        assert!(effects(&before, &partial, &system, false).is_ok());
        std::fs::remove_file(wants.join(TMP))?;
        ln(&system, GDM_LINK, DISPLAY)?;
        let after = capture_test(&system, &default)?;
        assert_eq!(effects(&before, &after, &system, true)?.len(), 3);

        // The wants-only case changes the nested directory but provides no
        // reason to waive its parent's own clocks/storage metadata.
        ln(&system, "/dev/null", DISPLAY)?;
        ln(&wants, OLD_TMP, TMP)?;
        let before = capture_test(&system, &default)?;
        std::fs::remove_file(wants.join(TMP))?;
        let after = capture_test(&system, &default)?;
        assert_eq!(effects(&before, &after, &system, true)?.len(), 1);
        let before = after;
        files::write_new(&system.join("unowned-transient"), b"x", 0o644)?;
        std::fs::remove_file(system.join("unowned-transient"))?;
        let after = capture_test(&system, &default)?;
        assert!(
            effects(&before, &after, &system, true).is_err(),
            "parent-only clock drift"
        );

        let before = capture_test(&system, &default)?;
        files::write_new(&system.join("unowned-new.service"), b"foreign", 0o644)?;
        assert!(effects(&before, &capture_test(&system, &default)?, &system, false).is_err());
        std::fs::remove_file(system.join("unowned-new.service"))?;
        files::write_new(&wants.join(TMP), b"unselected regular entry", 0o644)?;
        let before = capture_test(&system, &default)?;
        std::fs::remove_file(wants.join(TMP))?;
        assert!(effects(&before, &capture_test(&system, &default)?, &system, false).is_err());
        let before = capture_test(&system, &default)?;
        std::fs::rename(
            system.join("unrelated.service"),
            root.join("retained-unrelated.service"),
        )?;
        files::write_new(
            &system.join("unrelated.service"),
            b"unchanged public unit",
            0o644,
        )?;
        assert!(effects(&before, &capture_test(&system, &default)?, &system, false).is_err());
        let before = capture_test(&system, &default)?;
        std::fs::rename(&wants, root.join("retained-wants"))?;
        files::private_dir(&wants)?;
        assert!(effects(&before, &capture_test(&system, &default)?, &system, false).is_err());
        write_json(
            &root.join("RESULT.json"),
            &json!({"schema":"droidloom.native-package-parent-isolated-test.v1",
            "normal_same_target_alias":true,"interrupted_preimage_reopened":true,
            "exact_tmp_predicates":true,"unrelated_changes_rejected":true,"physical_changes":false}),
        )?;
        println!("isolated_parent_test={}", root.display());
        Ok(())
    }
    #[test]
    #[ignore = "root read-only validation of the retained selected native22 normal archives"]
    fn actual_selected_native_sources_match_the_audited_parent_effects() -> Result<()> {
        let path = Path::new(
            "/var/lib/droidloom-qualification/p4-original-native22-credentials-release-4b91-r2/NATIVE-RELEASE.json",
        );
        let pin = files::pin_file(path)?;
        let release = NormalSource::open(&pin)?;
        let index: Value = serde_json::from_slice(&release.read()?)?;
        let archives = source_archives(&pin, &index)?;
        assert_eq!(archives.len(), 4);
        for p in &archives {
            NormalSource::open(p)?.revalidate()?;
        }
        release.revalidate()?;
        let mut changed = index.clone();
        let row = changed["package_roles"]
            .as_array_mut()
            .ok_or("roles")?
            .iter_mut()
            .find(|p| p["name"] == "gdm3")
            .ok_or("gdm")?;
        row["new"]["package"]["sha256"] = json!("0".repeat(64));
        assert!(source_archives(&pin, &changed).is_err());
        Ok(())
    }
}
