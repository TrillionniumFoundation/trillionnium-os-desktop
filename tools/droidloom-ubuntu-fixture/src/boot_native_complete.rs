//! First-boot state for an independently materialized complete Ubuntu root.
//! Existing distribution accounts, package database and public aliases survive.
//! This module never starts a service and never operates on the source root.
use super::*;
use crate::complete_native::{self, CompleteManifest};
use crate::complete_snapshot::{CompleteEntry, Snapshot};
use crate::model::{Content, Identity};
use rustix::fs::{self as rfs, RenameFlags};
use std::path::PathBuf;

pub const SCHEMA: &str = "droidloom.complete-native-ubuntu-initialization.v1";

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CompleteNativeInputs {
    pub hostname: String,
    pub root_filesystem_uuid: String,
    pub network_connection_uuid: String,
    pub generate_fixture_ssh: bool,
}

const MEMBERSHIPS: &[&str] = &["audio", "video", "render", "input", "netdev"];
const ACCOUNT_FILES: &[&str] = &["/etc/passwd", "/etc/group", "/etc/shadow", "/etc/gshadow"];
const REPLACEMENTS: &[&str] = &[
    "/etc/gdm3/custom.conf",
    "/etc/machine-id",
    "/var/lib/dbus/machine-id",
    "/etc/hostname",
    "/etc/hosts",
    "/etc/fstab",
    "/etc/subuid",
    "/etc/subgid",
];
const HOST_KEYS: &[&str] = &[
    "/etc/ssh/ssh_host_rsa_key",
    "/etc/ssh/ssh_host_rsa_key.pub",
    "/etc/ssh/ssh_host_ecdsa_key",
    "/etc/ssh/ssh_host_ecdsa_key.pub",
    "/etc/ssh/ssh_host_ed25519_key",
    "/etc/ssh/ssh_host_ed25519_key.pub",
];
const NEW_FILES: &[&str] = &[
    "/etc/NetworkManager/conf.d/99-pocket4-fixture.conf",
    "/etc/NetworkManager/system-connections/pocket4-fixture-ethernet.nmconnection",
    "/etc/ssh/sshd_config.d/00-pocket4-fixture.conf",
    "/var/lib/AccountsService/users/alex",
];
const EMPTY_DIRS: &[&str] = &[
    "/home",
    "/root/.ssh",
    "/root/.cache",
    "/var/lib/AccountsService/users",
    "/etc/NetworkManager/system-connections",
    "/var/lib/NetworkManager",
    "/var/lib/bluetooth",
    "/var/snap",
    "/snap",
    "/var/lib/snapd/snaps/partial",
];
const NO_STATE: &[&str] = &[
    "/home/alex",
    "/var/lib/snapd/state.json",
    "/var/lib/snapd/state.json.tmp",
    "/var/lib/snapd/assertions",
    "/var/lib/snapd/cookie",
    "/var/lib/snapd/device",
    "/var/lib/snapd/sequence",
    "/root/.bash_history",
    "/root/.local",
    "/root/.config",
];

fn validate_inputs(inputs: &CompleteNativeInputs) -> Result<()> {
    ensure(
        valid_name(&inputs.hostname)
            && inputs.hostname.len() <= 63
            && !inputs.hostname.starts_with('-')
            && !inputs.hostname.ends_with('-'),
        "invalid complete fixture hostname",
    )?;
    ensure(
        valid_uuid(&inputs.root_filesystem_uuid)
            && valid_uuid(&inputs.network_connection_uuid)
            && inputs.root_filesystem_uuid != inputs.network_connection_uuid,
        "complete fixture filesystem/network UUIDs must be valid and distinct",
    )
}

fn rows(bytes: &[u8], columns: usize) -> Result<BTreeMap<String, Vec<String>>> {
    let mut result = BTreeMap::new();
    for line in std::str::from_utf8(bytes)?.lines() {
        let cols: Vec<String> = line.split(':').map(str::to_owned).collect();
        ensure(
            cols.len() == columns && valid_name(&cols[0]),
            "malformed normal account row",
        )?;
        ensure(
            result.insert(cols[0].clone(), cols).is_none(),
            "duplicate normal account name",
        )?;
    }
    ensure(!result.is_empty(), "normal account database is empty")?;
    Ok(result)
}

fn locked(bytes: &[u8], columns: usize) -> Result<BTreeMap<String, Vec<String>>> {
    let result = rows(bytes, columns)?;
    for row in result.values() {
        ensure(
            row[1].starts_with('!') || row[1].starts_with('*'),
            "complete baseline contains an unlocked account or group password",
        )?;
    }
    Ok(result)
}

#[derive(Clone)]
struct Accounts {
    passwd: BTreeMap<String, Vec<String>>,
    group: BTreeMap<String, Vec<String>>,
    shadow: BTreeMap<String, Vec<String>>,
    gshadow: BTreeMap<String, Vec<String>>,
}

fn member_set(s: &str) -> Result<BTreeSet<String>> {
    let mut result = BTreeSet::new();
    if !s.is_empty() {
        for value in s.split(',') {
            ensure(
                valid_name(value) && result.insert(value.to_owned()),
                "invalid or duplicate normal group member",
            )?;
        }
    }
    Ok(result)
}

fn accounts_before(contents: &[Vec<u8>; 4]) -> Result<Accounts> {
    let a = Accounts {
        passwd: rows(&contents[0], 7)?,
        group: rows(&contents[1], 4)?,
        shadow: locked(&contents[2], 9)?,
        gshadow: locked(&contents[3], 4)?,
    };
    ensure(
        a.passwd.keys().eq(a.shadow.keys()) && a.group.keys().eq(a.gshadow.keys()),
        "normal account/shadow names disagree",
    )?;
    let mut uids = BTreeSet::new();
    let mut gids = BTreeSet::new();
    for row in a.group.values() {
        let gid: u32 = row[2].parse()?;
        ensure(
            ["x", "!", "*"].contains(&row[1].as_str())
                && gids.insert(gid)
                && (gid < 1000 || gid == 65534)
                && gid != 976
                && !["alex", "droidloom-cell-u1000"].contains(&row[0].as_str()),
            "complete baseline contains an occupied or non-service group identity",
        )?;
        let members = member_set(&row[3])?;
        ensure(
            members.iter().all(|m| a.passwd.contains_key(m)),
            "normal group references an unknown account",
        )?;
        ensure(
            member_set(&a.gshadow[&row[0]][3])? == members,
            "normal group/gshadow membership differs",
        )?;
    }
    for row in a.passwd.values() {
        let uid: u32 = row[2].parse()?;
        let gid: u32 = row[3].parse()?;
        ensure(
            ["x", "!", "*", "!!"].contains(&row[1].as_str())
                && uids.insert(uid)
                && (uid < 1000 || uid == 65534)
                && uid != 976
                && gids.contains(&gid)
                && !["alex", "droidloom-cell-u1000"].contains(&row[0].as_str()),
            "complete baseline contains an occupied or non-service user identity",
        )?;
        account_path(&row[5])?;
        account_path(&row[6])?;
        ensure(
            !row[5].starts_with("/home/"),
            "complete baseline has an existing user home",
        )?;
    }
    ensure(
        a.passwd
            .get("root")
            .is_some_and(|r| r[2] == "0" && r[3] == "0")
            && a.group.get("root").is_some_and(|r| r[2] == "0"),
        "normal root identity is missing",
    )?;
    let gdm = a.passwd.get("gdm").ok_or("normal GDM user is missing")?;
    let gdm_group = a.group.get("gdm").ok_or("normal GDM group is missing")?;
    ensure(
        gdm[3] == gdm_group[2] && gdm[2].parse::<u32>()? > 0,
        "normal GDM user/group identity differs",
    )?;
    for name in MEMBERSHIPS {
        ensure(
            a.group.contains_key(*name),
            "required normal device group is missing",
        )?;
    }
    Ok(a)
}

fn sysusers_lines() -> Vec<String> {
    let mut lines = vec![
        "g alex 1000".into(),
        "g droidloom-cell-u1000 976".into(),
        "u alex 1000:1000 \"Pocket4 qualification user\" /home/alex /bin/bash".into(),
        "u droidloom-cell-u1000 976:976 \"Droidloom Android cell for host UID 1000\" /nonexistent /usr/sbin/nologin".into(),
    ];
    lines.extend(MEMBERSHIPS.iter().map(|g| format!("m alex {g}")));
    lines
}

fn accounts_after(before: &Accounts, contents: &[Vec<u8>; 4]) -> Result<Value> {
    let passwd = rows(&contents[0], 7)?;
    let group = rows(&contents[1], 4)?;
    let shadow = locked(&contents[2], 9)?;
    let gshadow = locked(&contents[3], 4)?;
    let expected_users: BTreeSet<_> = before
        .passwd
        .keys()
        .cloned()
        .chain(["alex".into(), "droidloom-cell-u1000".into()])
        .collect();
    let expected_groups: BTreeSet<_> = before
        .group
        .keys()
        .cloned()
        .chain(["alex".into(), "droidloom-cell-u1000".into()])
        .collect();
    ensure(
        passwd.keys().cloned().collect::<BTreeSet<_>>() == expected_users
            && shadow.keys().eq(passwd.keys())
            && group.keys().cloned().collect::<BTreeSet<_>>() == expected_groups
            && gshadow.keys().eq(group.keys()),
        "sysusers changed the normal account roster beyond the two fixture identities",
    )?;
    for (name, row) in &before.passwd {
        ensure(
            passwd.get(name) == Some(row) && shadow.get(name) == before.shadow.get(name),
            "sysusers altered an existing normal service account",
        )?;
    }
    for (name, row) in &before.group {
        let after = &group[name];
        let old_shadow = &before.gshadow[name];
        let new_shadow = &gshadow[name];
        let mut members = member_set(&row[3])?;
        if MEMBERSHIPS.contains(&name.as_str()) {
            members.insert("alex".into());
        }
        ensure(
            after[..3] == row[..3]
                && new_shadow[..3] == old_shadow[..3]
                && member_set(&after[3])? == members
                && member_set(&new_shadow[3])? == members,
            "sysusers altered normal groups beyond the approved alex memberships",
        )?;
    }
    for (name, uid, home, shell) in [
        ("alex", "1000", "/home/alex", "/bin/bash"),
        (
            "droidloom-cell-u1000",
            "976",
            "/nonexistent",
            "/usr/sbin/nologin",
        ),
    ] {
        let row = &passwd[name];
        ensure(
            row[2] == uid
                && row[3] == uid
                && row[5] == home
                && row[6] == shell
                && group[name][2] == uid
                && group[name][3].is_empty()
                && gshadow[name][2].is_empty()
                && gshadow[name][3].is_empty(),
            "fresh fixture account identity, home, shell or group differs",
        )?;
    }
    let (_, mut summary) = native_accounts(&contents[0], &contents[1])?;
    summary["normal_service_accounts_preserved"] = json!(true);
    summary["normal_memberships_preserved"] = json!(true);
    summary["cell_home"] = json!("/nonexistent");
    Ok(summary)
}

#[derive(Clone, Debug, Serialize)]
struct Preimage {
    path: String,
    identity: Identity,
    sha256: String,
    xattrs: BTreeMap<String, String>,
}

fn verify_file(tree: &Snapshot, entry: &CompleteEntry) -> Result<Preimage> {
    let expected_sha = match &entry.content {
        Content::Regular { sha256 } => sha256,
        _ => return Err("complete initialization requires an independent regular preimage".into()),
    };
    let (identity, sha256, xattrs) = tree.regular(&entry.path)?;
    ensure(
        fs::same_metadata(&identity, &entry.source)
            && identity.size == entry.source.size
            && identity.nlink == 1
            && entry.source.nlink == 1
            && (identity.dev, identity.ino) != (entry.source.dev, entry.source.ino)
            && sha256 == *expected_sha
            && xattrs == entry.xattrs,
        &format!("complete clone preimage differs: {}", entry.path),
    )?;
    Ok(Preimage {
        path: entry.path.clone(),
        identity,
        sha256,
        xattrs,
    })
}

fn unchanged(tree: &Snapshot, p: &Preimage) -> Result<()> {
    let (id, sha, attrs) = tree.regular(&p.path)?;
    ensure(
        id == p.identity && sha == p.sha256 && attrs == p.xattrs,
        &format!("complete clone input changed: {}", p.path),
    )
}

fn read_verified(tree: &Snapshot, p: &Preimage, limit: u64) -> Result<Vec<u8>> {
    let bytes = tree.bytes(&p.path, limit)?;
    ensure(
        tree.identity(&p.path)? == p.identity && fs::digest(&bytes) == p.sha256,
        "complete preimage changed while parsed",
    )?;
    Ok(bytes)
}

fn absent(tree: &Snapshot, path: &str) -> Result<bool> {
    match tree.identity(path) {
        Ok(_) => Ok(false),
        Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
            Ok(true)
        }
        Err(e) => Err(e),
    }
}

fn empty_if_present(tree: &Snapshot, path: &str) -> Result<()> {
    if !absent(tree, path)? {
        ensure(
            tree.names(path)?.is_empty(),
            &format!("complete clone contains prior state: {path}"),
        )?;
    }
    Ok(())
}

fn verify_alias(tree: &Snapshot, entry: &CompleteEntry, expected: &str) -> Result<Value> {
    let (id, target) = tree.link(&entry.path)?;
    ensure(
        matches!(&entry.content, Content::Symlink { target: t } if t == expected)
            && target == expected
            && fs::same_metadata(&id, &entry.source)
            && id.uid == 0
            && id.gid == 0,
        "complete clone normal alias differs",
    )?;
    Ok(json!({"path":entry.path,"target":target,"identity":id}))
}

fn snap_specs(entries: &BTreeMap<&str, &CompleteEntry>) -> Result<Vec<(SnapMount, Vec<u8>)>> {
    let mut result = Vec::new();
    let mut names = BTreeSet::new();
    for (path, e) in entries.range("/var/lib/snapd/snaps/".."/var/lib/snapd/snaps0") {
        if matches!(e.content, Content::Directory) {
            continue;
        }
        let leaf = path
            .strip_prefix("/var/lib/snapd/snaps/")
            .ok_or("invalid Snap prefix")?;
        let file = leaf
            .strip_suffix(".snap")
            .ok_or("unreviewed file in Snap archive tree")?;
        let (name, revision) = file
            .rsplit_once('_')
            .ok_or("invalid Snap archive filename")?;
        ensure(
            !leaf.contains('/')
                && SNAP_NAMES.contains(&name)
                && names.insert(name.to_owned())
                && !revision.is_empty()
                && revision.len() <= 12
                && revision.bytes().all(|b| b.is_ascii_digit())
                && matches!(e.content, Content::Regular { .. })
                && e.source.uid == 0
                && e.source.gid == 0
                && e.source.mode & 0o7777 == 0o644
                && e.source.size > 0
                && e.source.nlink == 1
                && e.xattrs.is_empty(),
            "unreviewed or duplicate complete Snap archive",
        )?;
        let unit = format!("snap-{}-{revision}.mount", name.replace('-', "\\x2d"));
        let image = format!("/var/lib/snapd/snaps/{name}_{revision}.snap");
        let mountpoint = format!("/snap/{name}/{revision}");
        let bytes = format!(
            "[Unit]\nDescription=Mount unit for {name}, revision {revision}\nAfter=snapd.mounts-pre.target\nBefore=snapd.mounts.target\n\n[Mount]\nWhat={image}\nWhere={mountpoint}\nType=squashfs\nOptions=nodev,ro,x-gdu.hide,x-gvfs-hide\nLazyUnmount=yes\n\n[Install]\nWantedBy=snapd.mounts.target\nWantedBy=multi-user.target\n"
        ).into_bytes();
        let guest_path = format!("/etc/systemd/system/{unit}");
        let spec = parse_snap(
            &PublicConfigInput {
                input: FilePin {
                    path: PathBuf::from(&guest_path),
                    bytes: bytes.len() as u64,
                    sha256: fs::digest(&bytes),
                },
                guest_path,
                mode: 0o644,
            },
            &bytes,
        )?;
        result.push((spec, bytes));
    }
    ensure(
        names == SNAP_NAMES.iter().map(|s| (*s).to_owned()).collect(),
        "complete manifest must contain exactly seven selected public Snap archives",
    )?;
    Ok(result)
}

/// Only these identity/configuration leaves can be retired from this new clone.
/// Account files and package databases are deliberately outside this allowlist.
fn replaceable(path: &str) -> bool {
    REPLACEMENTS.contains(&path) || HOST_KEYS.contains(&path)
}

fn retire(
    tree: &Snapshot,
    archive: &fs::Tree,
    preimage: &Preimage,
    actions: &mut Vec<Value>,
) -> Result<String> {
    ensure(
        replaceable(&preimage.path),
        "path is outside complete identity replacement scope",
    )?;
    unchanged(tree, preimage)?;
    let (parent, name) = tree.parent(&preimage.path)?;
    let backup = format!("{}-{}", actions.len(), fs::digest(preimage.path.as_bytes()));
    rfs::renameat_with(
        &parent,
        name.as_str(),
        &archive.root,
        backup.as_str(),
        RenameFlags::NOREPLACE,
    )?;
    let file = archive.file(&format!("/{backup}"))?;
    let id = fs::stat(&file)?;
    ensure(
        (id.dev, id.ino) == (preimage.identity.dev, preimage.identity.ino)
            && fs::same_metadata(&id, &preimage.identity)
            && id.nlink == 1
            && fs::hash(&file)? == preimage.sha256
            && fs::xattrs(&file)? == preimage.xattrs,
        "retired complete identity preimage readback differs",
    )?;
    rfs::fsync(&parent)?;
    rfs::fsync(&archive.root)?;
    actions.push(
        json!({"operation":"preserve_complete_preimage","preimage":preimage,
        "archive_leaf":backup,"physical_source_modified":false}),
    );
    Ok(backup)
}

fn replace(
    root: &Path,
    tree: &Snapshot,
    archive: &fs::Tree,
    before: &Preimage,
    bytes: &[u8],
    mode: u32,
    actions: &mut Vec<Value>,
) -> Result<()> {
    ensure(
        replaceable(&before.path),
        "path is outside complete identity replacement scope",
    )?;
    retire(tree, archive, before, actions)?;
    write_guest(root, &before.path, bytes, mode, actions)?;
    let (id, sha, attrs) = tree.regular(&before.path)?;
    ensure(
        id.uid == 0
            && id.gid == 0
            && id.mode & 0o7777 == mode
            && id.nlink == 1
            && id.size == bytes.len() as u64
            && sha == fs::digest(bytes)
            && attrs.is_empty(),
        "new complete identity replacement readback differs",
    )
}

fn account_contents(tree: &Snapshot) -> Result<[Vec<u8>; 4]> {
    Ok([
        tree.bytes(ACCOUNT_FILES[0], 1024 * 1024)?,
        tree.bytes(ACCOUNT_FILES[1], 1024 * 1024)?,
        tree.bytes(ACCOUNT_FILES[2], 1024 * 1024)?,
        tree.bytes(ACCOUNT_FILES[3], 1024 * 1024)?,
    ])
}

/// The caller must first fully verify and independently materialize this
/// manifest. This function checks every consumed or replaced preimage again,
/// preserves the distribution's configured state, and starts no runtime.
pub fn initialize_complete(
    root: &Path,
    work: &Path,
    inputs: &CompleteNativeInputs,
    manifest: &CompleteManifest,
) -> Result<Value> {
    ensure(
        rustix::process::geteuid().as_raw() == 0,
        "complete native initialization requires existing root rights",
    )?;
    validate_inputs(inputs)?;
    ensure(
        root == work.join("root")
            && work.parent() == Some(Path::new("/var/lib/droidloom-qualification")),
        "complete initialization is restricted to a new protected qualification root",
    )?;
    let authority = complete_native::validate(manifest)?;
    ensure(
        authority.stage == "installed",
        "complete initialization requires a normally installed source authority",
    )?;
    let snapshot = Snapshot::open(root)?;
    let root_id = fs::stat(&snapshot.root)?;
    ensure(
        root != authority.root.path
            && (root_id.dev, root_id.ino) != (authority.root.device, authority.root.inode),
        "complete initializer refuses the original source root",
    )?;
    let console_source = super::console::verify(&snapshot, manifest)?;
    let remount_source = super::remount::verify(&snapshot, manifest)?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let work_tree = fs::Tree::open(&fs::absolute_string(work)?, 0)?;
    let work_id = fs::stat(&work_tree.root)?;
    ensure(
        work_id.mode & 0o7777 == 0o700
            && work_id.uid == 0
            && work_id.gid == 0
            && work_id.dev == root_id.dev,
        "complete work directory must be private and on the clone filesystem",
    )?;
    for p in [
        "/NATIVE-INIT-STARTED.json",
        "/complete-native-preimages",
        "/fixture-ssh-client-key",
        "/fixture-ssh-client-key.pub",
    ] {
        ensure(
            missing(&work_tree, p)?,
            "complete initialization destination already used",
        )?;
    }
    let mut entries = BTreeMap::new();
    for e in &manifest.entries {
        ensure(
            entries.insert(e.path.as_str(), e).is_none(),
            "duplicate complete manifest path",
        )?;
    }
    let entry = |path: &str| {
        entries
            .get(path)
            .copied()
            .ok_or_else(|| -> Box<dyn std::error::Error + Send + Sync> {
                format!("complete initializer missing manifest path: {path}").into()
            })
    };
    let mut preimages = BTreeMap::new();
    for p in ACCOUNT_FILES
        .iter()
        .chain(PUBLIC_CONFIGS)
        .chain(REPLACEMENTS)
        .chain(HOST_KEYS)
        .copied()
        .chain([
            "/var/lib/dpkg/status",
            "/usr/bin/systemd-sysusers",
            "/usr/bin/systemd-firstboot",
            "/usr/bin/systemd-tmpfiles",
            "/usr/bin/systemctl",
            "/usr/bin/ssh-keygen",
        ])
    {
        if !preimages.contains_key(p) {
            preimages.insert(p.to_owned(), verify_file(&snapshot, entry(p)?)?);
        }
    }
    let contents = account_contents(&snapshot)?;
    for (p, bytes) in ACCOUNT_FILES.iter().zip(&contents) {
        ensure(
            fs::digest(bytes) == preimages[*p].sha256
                && snapshot.identity(p)? == preimages[*p].identity,
            "normal account preimage changed",
        )?;
    }
    let before_accounts = accounts_before(&contents)?;
    for p in EMPTY_DIRS {
        empty_if_present(&snapshot, p)?;
    }
    for p in NO_STATE.iter().chain(NEW_FILES) {
        ensure(
            absent(&snapshot, p)?,
            &format!("complete initialization found prior state: {p}"),
        )?;
    }
    for p in ["/root/.bashrc", "/root/.profile"] {
        verify_file(&snapshot, entry(p)?)?;
    }
    let root_names = snapshot.names("/root")?;
    ensure(
        root_names
            .iter()
            .all(|p| [".bashrc", ".profile", ".cache", ".ssh"].contains(&p.as_str())),
        "normal clone contains unreviewed root home state",
    )?;
    for p in ["/etc/subuid", "/etc/subgid"] {
        ensure(
            read_verified(&snapshot, &preimages[p], 1024 * 1024)?.is_empty(),
            "normal clone already contains subordinate ID mappings",
        )?;
    }
    ensure(
        std::str::from_utf8(&read_verified(&snapshot, &preimages["/etc/hostname"], 256)?)?.trim()
            != inputs.hostname,
        "complete fixture hostname must differ from the bootstrap identity",
    )?;
    let old_machine_id = read_verified(&snapshot, &preimages["/etc/machine-id"], 128)?;
    ensure(
        read_verified(&snapshot, &preimages["/var/lib/dbus/machine-id"], 128)? == old_machine_id,
        "normal baseline machine ID copies disagree",
    )?;
    ensure(
        read_verified(&snapshot, &preimages["/etc/fstab"], 4096)?
            == b"# UNCONFIGURED FSTAB FOR BASE SYSTEM\n",
        "normal baseline fstab is already configured",
    )?;
    let gdm = gdm_timed_login(&read_verified(
        &snapshot,
        &preimages["/etc/gdm3/custom.conf"],
        65536,
    )?)?;
    let mut aliases = Vec::new();
    for (p, target) in ALIASES_TO_RESTORE.iter().copied().chain([
        ("/etc/localtime", "/usr/share/zoneinfo/Etc/UTC"),
        ("/etc/default/locale", "../locale.conf"),
        (
            "/etc/resolv.conf",
            "../run/systemd/resolve/stub-resolv.conf",
        ),
    ]) {
        aliases.push(verify_alias(&snapshot, entry(p)?, target)?);
    }
    let snaps = snap_specs(&entries)?;
    for (spec, _) in &snaps {
        let preimage = verify_file(&snapshot, entry(&spec.image)?)?;
        preimages.insert(spec.image.clone(), preimage);
        ensure(
            absent(&snapshot, &format!("/etc/systemd/system/{}", spec.unit))?
                && absent(&snapshot, &format!("/snap/{}/current", spec.name))?,
            "normal clone already contains active Snap aliases or units",
        )?;
    }
    let actual_snaps: BTreeSet<_> = snapshot
        .names("/var/lib/snapd/snaps")?
        .into_iter()
        .filter(|p| p != "partial")
        .collect();
    let expected_snaps: BTreeSet<_> = snaps
        .iter()
        .map(|(s, _)| format!("{}_{}.snap", s.name, s.revision))
        .collect();
    ensure(
        actual_snaps == expected_snaps,
        "complete clone has extra or missing Snap archives",
    )?;
    let greeter_session = crate::boot_gdm_proof::original_session(&tree)?;
    for (p, _) in crate::boot_gdm_proof::FILES {
        ensure(
            absent(&snapshot, p)?,
            "complete greeter proof is create-only",
        )?;
    }
    fs::assert_root_namespace(&fs::absolute_string(root)?, &tree)?;
    boot_files::write_new(
        &work.join("NATIVE-INIT-STARTED.json"),
        &serde_json::to_vec_pretty(&json!({
            "schema":"droidloom.complete-native-init-started.v1","root":root,"source":authority.root,
            "source_stage":authority.stage,"inputs":inputs,"consumed_preimages":preimages,
            "normal_aliases":aliases,"guest_qualified":false,
        }))?,
        0o600,
    )?;
    work_tree.mkdir("/complete-native-preimages")?;
    let archive = fs::Tree::open(
        &fs::absolute_string(&work.join("complete-native-preimages"))?,
        0,
    )?;
    let mut actions = Vec::new();
    let mut commands = Vec::new();
    rfs::fchmod(&snapshot.root, Mode::from_raw_mode(0o755))?;
    actions.push(
        json!({"operation":"set_fixture_root_mode","before":root_id.mode & 0o7777,"after":0o755}),
    );
    let root_arg = format!("--root={}", fs::absolute_string(root)?);
    let mut args = vec![root_arg.clone(), "--inline".into()];
    args.extend(sysusers_lines());
    run_native(
        root,
        work,
        &tree,
        "complete-native-sysusers",
        "/usr/bin/systemd-sysusers",
        &args,
        &mut commands,
    )?;
    let account_summary = accounts_after(&before_accounts, &account_contents(&snapshot)?)?;
    actions.push(
        json!({"operation":"normal_sysusers_add","added_users":["alex","droidloom-cell-u1000"],
        "existing_service_accounts_preserved":true,"memberships":MEMBERSHIPS}),
    );
    retire(
        &snapshot,
        &archive,
        &preimages["/etc/machine-id"],
        &mut actions,
    )?;
    retire(
        &snapshot,
        &archive,
        &preimages["/var/lib/dbus/machine-id"],
        &mut actions,
    )?;
    run_native(
        root,
        work,
        &tree,
        "complete-native-firstboot",
        "/usr/bin/systemd-firstboot",
        &[
            root_arg.clone(),
            "--setup-machine-id".into(),
            "--welcome=no".into(),
        ],
        &mut commands,
    )?;
    let machine_id = read_guest(&tree, "/etc/machine-id", 128)?;
    let id = std::str::from_utf8(&machine_id)?.trim();
    ensure(
        id.len() == 32
            && id.bytes().all(|b| b.is_ascii_hexdigit())
            && id.bytes().any(|b| b != b'0')
            && machine_id != old_machine_id,
        "complete fixture machine ID is not independently generated",
    )?;
    link_guest(
        root,
        &tree,
        "/var/lib/dbus/machine-id",
        "/etc/machine-id",
        &mut actions,
    )?;
    actions.push(json!({"operation":"generate_fresh_machine_id","sha256":fs::digest(&machine_id)}));
    let replacements = [
        ("/etc/hostname", format!("{}\n", inputs.hostname).into_bytes()),
        ("/etc/hosts", format!("127.0.0.1 localhost\n127.0.1.1 {}\n::1 localhost ip6-localhost ip6-loopback\nff02::1 ip6-allnodes\nff02::2 ip6-allrouters\n", inputs.hostname).into_bytes()),
        ("/etc/fstab", format!("# Isolated qualification root; no host filesystems.\nUUID={} / ext4 defaults 0 1\n", inputs.root_filesystem_uuid).into_bytes()),
        ("/etc/subuid", b"droidloom-cell-u1000:200000:100000\n".to_vec()),
        ("/etc/subgid", b"droidloom-cell-u1000:200000:100000\n".to_vec()),
        ("/etc/gdm3/custom.conf", gdm),
    ];
    for (p, bytes) in &replacements {
        replace(
            root,
            &snapshot,
            &archive,
            &preimages[*p],
            bytes,
            0o644,
            &mut actions,
        )?;
    }
    for (p, bytes) in crate::boot_gdm_proof::FILES {
        write_guest(root, p, bytes, 0o444, &mut actions)?;
    }
    write_guest(
        root,
        NEW_FILES[0],
        b"# Only the independent qualification guest.\n[keyfile]\nunmanaged-devices=\n",
        0o644,
        &mut actions,
    )?;
    write_guest(root, NEW_FILES[1], format!(
        "[connection]\nid=pocket4-fixture-ethernet\nuuid={}\ntype=ethernet\nautoconnect=true\n\n[ethernet]\n\n[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=disabled\n",
        inputs.network_connection_uuid).as_bytes(), 0o600, &mut actions)?;
    for (spec, bytes) in &snaps {
        directory(root, &spec.mountpoint, 0o755)?;
        write_guest(
            root,
            &format!("/etc/systemd/system/{}", spec.unit),
            bytes,
            0o644,
            &mut actions,
        )?;
        link_guest(
            root,
            &tree,
            &format!("/snap/{}/current", spec.name),
            &spec.revision,
            &mut actions,
        )?;
    }
    run_native(
        root,
        work,
        &tree,
        "complete-native-tmpfiles",
        "/usr/bin/systemd-tmpfiles",
        &[root_arg.clone(), "--create".into(), "--boot".into()],
        &mut commands,
    )?;
    directory(root, "/home/alex/.ssh", 0o700)?;
    let home = tree.dir("/home/alex")?;
    let ssh_dir = tree.dir("/home/alex/.ssh")?;
    let mut dmrc = tree.create_file("/home/alex/.dmrc")?;
    dmrc.write_all(b"[Desktop]\nSession=ubuntu\n")?;
    set_owned(&dmrc, 1000, 1000, 0o600)?;
    directory(root, "/var/lib/AccountsService/users", 0o700)?;
    write_guest(
        root,
        NEW_FILES[3],
        b"[User]\nSession=ubuntu\nXSession=ubuntu\nSystemAccount=false\n",
        0o600,
        &mut actions,
    )?;
    // These are freshly generated bootstrap keys, already authenticated by the
    // complete-source authority. Retire only this independent clone's copies.
    for p in HOST_KEYS {
        retire(&snapshot, &archive, &preimages[*p], &mut actions)?;
    }
    run_native(
        root,
        work,
        &tree,
        "complete-native-ssh-hostkeys",
        "/usr/bin/ssh-keygen",
        &["-A".into(), "-f".into(), fs::absolute_string(root)?],
        &mut commands,
    )?;
    let mut host_key_readback = Vec::new();
    for p in HOST_KEYS {
        let (identity, sha256, attrs) = snapshot.regular(p)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && attrs.is_empty()
                && identity.mode & 0o7777 == if p.ends_with(".pub") { 0o644 } else { 0o600 }
                && sha256 != preimages[*p].sha256,
            "fresh complete fixture SSH host key differs from required isolation",
        )?;
        host_key_readback.push(json!({"path":p,"identity":identity,"sha256":sha256}));
    }
    let mut ssh_result = Value::Null;
    if inputs.generate_fixture_ssh {
        write_guest(root, NEW_FILES[2], b"# Fresh guest identity only; key generated for loopback qualification.\nPermitRootLogin no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPubkeyAuthentication yes\nAuthenticationMethods publickey\nAllowUsers alex\n",
            0o644, &mut actions)?;
        let key = work.join("fixture-ssh-client-key");
        let public = work.join("fixture-ssh-client-key.pub");
        run_native(
            root,
            work,
            &tree,
            "complete-native-ssh-client-key",
            "/usr/bin/ssh-keygen",
            &[
                "-q".into(),
                "-t".into(),
                "ed25519".into(),
                "-N".into(),
                String::new(),
                "-C".into(),
                "pocket4-fixture-only".into(),
                "-f".into(),
                fs::absolute_string(&key)?,
            ],
            &mut commands,
        )?;
        let pub_pin = boot_files::pin_file(&public)?;
        let pub_bytes = boot_files::read_pin(&pub_pin, 4096)?;
        let text = std::str::from_utf8(&pub_bytes)?;
        ensure(
            text.starts_with("ssh-ed25519 ") && text.lines().count() == 1,
            "fresh fixture SSH public key format differs",
        )?;
        let mut authorized = tree.create_file("/home/alex/.ssh/authorized_keys")?;
        authorized.write_all(&pub_bytes)?;
        authorized.seek(SeekFrom::Start(0))?;
        ensure(
            fs::hash(&authorized)? == pub_pin.sha256,
            "fresh authorized key readback differs",
        )?;
        set_owned(&authorized, 1000, 1000, 0o600)?;
        let private_id = work_tree.identity("/fixture-ssh-client-key")?;
        ensure(
            FileType::from_raw_mode(private_id.mode) == FileType::RegularFile
                && private_id.uid == 0
                && private_id.gid == 0
                && private_id.nlink == 1
                && private_id.mode & 0o7777 == 0o600,
            "fresh private client key isolation differs",
        )?;
        ssh_result = json!({"fresh_private_key_path":key,"public_key":pub_pin,
            "private_key_contents_read":false,"network_scope":"subsequent VM loopback forwarding only"});
    }
    set_owned(&ssh_dir, 1000, 1000, 0o700)?;
    set_owned(&home, 1000, 1000, 0o700)?;
    actions.push(json!({"operation":"create_fresh_fixture_home","path":"/home/alex","uid":1000,"gid":1000,
        "home_mode":0o700,"ssh_directory_mode":0o700,"dmrc_sha256":fs::digest(b"[Desktop]\nSession=ubuntu\n"),
        "dmrc_mode":0o600,"prior_user_home_copied":false}));
    let mut units: Vec<String> = SYSTEM_UNITS.iter().map(|s| (*s).into()).collect();
    if inputs.generate_fixture_ssh {
        units.push("ssh.socket".into());
    }
    units.extend(snaps.iter().map(|(s, _)| s.unit.clone()));
    let mut args = vec![root_arg.clone(), "enable".into()];
    args.extend(units.clone());
    run_native(
        root,
        work,
        &tree,
        "complete-native-enable-system-units",
        "/usr/bin/systemctl",
        &args,
        &mut commands,
    )?;
    run_native(
        root,
        work,
        &tree,
        "complete-native-default-target",
        "/usr/bin/systemctl",
        &[
            root_arg.clone(),
            "set-default".into(),
            "graphical.target".into(),
        ],
        &mut commands,
    )?;
    let mut args = vec![root_arg, "--global".into(), "enable".into()];
    args.extend(USER_UNITS.iter().map(|s| (*s).into()));
    run_native(
        root,
        work,
        &tree,
        "complete-native-enable-user-units",
        "/usr/bin/systemctl",
        &args,
        &mut commands,
    )?;
    ensure(
        accounts_after(&before_accounts, &account_contents(&snapshot)?)? == account_summary,
        "normal account initialization changed after its verification",
    )?;
    unchanged(&snapshot, &preimages["/var/lib/dpkg/status"])?;
    for p in PUBLIC_CONFIGS
        .iter()
        .filter(|p| **p != "/etc/gdm3/custom.conf")
    {
        unchanged(&snapshot, &preimages[*p])?;
    }
    for a in &aliases {
        let path = a["path"].as_str().ok_or("alias path")?;
        verify_alias(
            &snapshot,
            entry(path)?,
            a["target"].as_str().ok_or("alias target")?,
        )?;
    }
    for (spec, _) in &snaps {
        ensure(
            snapshot.identity(&spec.image)? == preimages[&spec.image].identity,
            "selected public Snap archive changed during native preparation",
        )?;
    }
    for p in NO_STATE.iter().filter(|p| **p != "/home/alex") {
        ensure(
            absent(&snapshot, p)?,
            "native initialization unexpectedly created prior-user or Snap state",
        )?;
    }
    fs::assert_root_namespace(&fs::absolute_string(root)?, &tree)?;
    Ok(json!({
        "schema":SCHEMA,"root":root,"work":work,"inputs":inputs,
        "source_stage":authority.stage,"complete_source_root":authority.root,
        "normal_console_source_closure":console_source,
        "normal_remount_source_closure":remount_source,
        "actions":actions,"native_commands":commands,"accounts":account_summary,
        "fresh_shadow_locked":true,"host_passwords_keys_homes_imported":false,
        "preimages_directory":work.join("complete-native-preimages"),
        "normal_package_database_preserved":true,"normal_dpkg_status_sha256":preimages["/var/lib/dpkg/status"].sha256,
        "normal_public_configs_preserved_except_gdm":true,"normal_aliases_preserved":aliases,
        "fresh_ssh":ssh_result,"fresh_host_keys":host_key_readback,
        "system_units_enabled":units,"user_units_enabled":USER_UNITS,
        "fresh_greeter_proof_session":greeter_session,
        "fresh_greeter_proof_files":crate::boot_gdm_proof::FILES.iter().map(|(p,b)|json!({"path":p,"bytes":b.len(),"sha256":fs::digest(b),"mode":0o444})).collect::<Vec<_>>(),
        "snap_mounts_prepared":snaps.iter().map(|(s,_)|json!({"name":s.name,"revision":s.revision,"unit":s.unit,"image":preimages[&s.image]})).collect::<Vec<_>>(),
        "snap_state_or_assertions_manufactured":false,"native_initialization_complete":true,
        "guest_started":false,"guest_qualified":false,
        "unresolved_requirements":["Actual joined SELinux/AppArmor enforcing cold boot",
            "Real GDM/Wayland, D-Bus, NetworkManager and SSH sessions",
            "Fresh Snap registration/assertions and native profile generation",
            "Selected-kernel device and Android/userdata/application qualification"]
    }))
}

#[cfg(test)]
#[path = "boot_native_complete_tests.rs"]
mod tests;
