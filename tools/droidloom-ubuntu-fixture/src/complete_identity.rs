//! Fresh qualification identities for a complete, normally configured Ubuntu
//! clone. The original service accounts and the complete package database stay
//! intact. Only this new private root can be modified.
use crate::boot_files;
use crate::complete_native::CompleteManifest;
use crate::complete_snapshot::Snapshot;
use crate::{Result, ensure, fs};
use rustix::fs::{self as rfs, AtFlags, FileType, Mode};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::io::{Seek, SeekFrom};
use std::path::Path;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Inputs {
    pub hostname: String,
    pub root_filesystem_uuid: String,
    pub network_connection_uuid: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct AccountBinding {
    pub schema: String,
    pub name: String,
    pub uid: u32,
    pub gid: u32,
    pub original_passwd_sha256: String,
    pub original_group_sha256: String,
    pub prepared_passwd_sha256: String,
    pub prepared_group_sha256: String,
}

impl AccountBinding {
    pub(super) fn verify(&self, passwd: &[u8], group: &[u8]) -> Result<()> {
        ensure(
            self.schema == "droidloom.complete-native-gdm-account.v1"
                && self.name == "gdm"
                && (1..1000).contains(&self.uid)
                && (1..1000).contains(&self.gid)
                && [
                    &self.original_passwd_sha256,
                    &self.original_group_sha256,
                    &self.prepared_passwd_sha256,
                    &self.prepared_group_sha256,
                ]
                .iter()
                .all(|s| fs::valid_digest(s))
                && fs::digest(passwd) == self.prepared_passwd_sha256
                && fs::digest(group) == self.prepared_group_sha256,
            "complete GDM account provenance changed",
        )?;
        let accounts = Accounts {
            users: fields(passwd, 7)?,
            groups: fields(group, 4)?,
        };
        ensure(
            accounts.gdm()? == (self.uid, self.gid),
            "complete GDM account identity differs",
        )
    }
}

#[derive(Clone, Debug)]
struct Accounts {
    users: BTreeMap<String, Vec<String>>,
    groups: BTreeMap<String, Vec<String>>,
}

fn fields(bytes: &[u8], count: usize) -> Result<BTreeMap<String, Vec<String>>> {
    let text = std::str::from_utf8(bytes)?;
    ensure(
        !text.contains('\0') && !text.contains('\r'),
        "invalid account encoding",
    )?;
    let mut result = BTreeMap::new();
    for line in text.lines() {
        let row: Vec<String> = line.split(':').map(str::to_owned).collect();
        ensure(
            row.len() == count && crate::boot_native::valid_name(&row[0]),
            "invalid complete account record",
        )?;
        ensure(
            ["x", "*", "!", ""].contains(&row[1].as_str()),
            "account password field is not a placeholder",
        )?;
        row[2].parse::<u32>()?;
        ensure(
            result.insert(row[0].clone(), row).is_none(),
            "duplicate complete account name",
        )?;
    }
    ensure(!result.is_empty(), "complete account database is empty")?;
    Ok(result)
}

impl Accounts {
    fn read(tree: &Snapshot) -> Result<(Self, Vec<u8>, Vec<u8>)> {
        let passwd = tree.bytes("/etc/passwd", 1024 * 1024)?;
        let group = tree.bytes("/etc/group", 1024 * 1024)?;
        let value = Self {
            users: fields(&passwd, 7)?,
            groups: fields(&group, 4)?,
        };
        let mut user_ids = BTreeSet::new();
        let mut group_ids = BTreeSet::new();
        for row in value.users.values() {
            let uid = row[2].parse::<u32>()?;
            row[3].parse::<u32>()?;
            ensure(
                user_ids.insert(uid),
                "complete native UID alias is not admitted",
            )?;
        }
        for row in value.groups.values() {
            ensure(
                group_ids.insert(row[2].parse::<u32>()?),
                "complete native GID alias is not admitted",
            )?;
        }
        ensure(
            value
                .users
                .get("root")
                .is_some_and(|r| r[2] == "0" && r[3] == "0")
                && value.groups.get("root").is_some_and(|r| r[2] == "0"),
            "normal root identity differs",
        )?;
        Ok((value, passwd, group))
    }

    fn gdm(&self) -> Result<(u32, u32)> {
        let user = self.users.get("gdm").ok_or("normal GDM account absent")?;
        let group = self.groups.get("gdm").ok_or("normal GDM group absent")?;
        let uid = user[2].parse::<u32>()?;
        let gid = user[3].parse::<u32>()?;
        ensure(
            (1..1000).contains(&uid) && (1..1000).contains(&gid) && group[2].parse::<u32>()? == gid,
            "normal GDM_GROUPNAME identity differs",
        )?;
        Ok((uid, gid))
    }

    fn additions(&self) -> Result<Vec<String>> {
        for (name, id) in [("alex", 1000u32), ("droidloom-cell-u1000", 976u32)] {
            ensure(
                !self.users.contains_key(name)
                    && !self.groups.contains_key(name)
                    && self.users.values().all(|r| r[2] != id.to_string())
                    && self.groups.values().all(|r| r[2] != id.to_string()),
                "fresh qualification identity collides with normal service account",
            )?;
        }
        // A bootstrap authority, not a copied personal root, is required. No
        // pre-existing interactive user or home is silently replaced.
        ensure(
            self.users
                .values()
                .all(|r| r[2].parse::<u32>().is_ok_and(|u| u < 1000 || u == 65534)),
            "complete source contains an existing personal user",
        )?;
        let mut result = vec![
            "g alex 1000".into(),
            "g droidloom-cell-u1000 976".into(),
            "u alex 1000:1000 \"Fresh qualification user\" /home/alex /bin/bash".into(),
            "u droidloom-cell-u1000 976:976 \"Android instance identity\" /var/lib/droidloom /usr/sbin/nologin".into(),
        ];
        for name in ["audio", "video", "render", "input", "netdev"] {
            ensure(self.groups.contains_key(name), "normal device group absent")?;
            result.push(format!("m alex {name}"));
        }
        Ok(result)
    }

    fn verify_after(&self, after: &Self) -> Result<()> {
        ensure(
            after.users.len() == self.users.len() + 2
                && after.groups.len() == self.groups.len() + 2,
            "normal account set changed beyond the two fresh identities",
        )?;
        for (name, row) in &self.users {
            ensure(
                after.users.get(name) == Some(row),
                "normal service account changed",
            )?;
        }
        for (name, row) in &self.groups {
            let mut expected = row.clone();
            if ["audio", "video", "render", "input", "netdev"].contains(&name.as_str()) {
                let mut members: BTreeSet<_> =
                    row[3].split(',').filter(|s| !s.is_empty()).collect();
                members.insert("alex");
                let actual: BTreeSet<_> = after.groups.get(name).ok_or("group disappeared")?[3]
                    .split(',')
                    .filter(|s| !s.is_empty())
                    .collect();
                ensure(actual == members, "normal group membership changed")?;
                expected[3] = after.groups[name][3].clone();
            }
            ensure(
                after.groups.get(name) == Some(&expected),
                "normal service group changed",
            )?;
        }
        for (name, id, home, shell) in [
            ("alex", "1000", "/home/alex", "/bin/bash"),
            (
                "droidloom-cell-u1000",
                "976",
                "/var/lib/droidloom",
                "/usr/sbin/nologin",
            ),
        ] {
            let row = after.users.get(name).ok_or("fresh account absent")?;
            ensure(
                row[2] == id
                    && row[3] == id
                    && row[5] == home
                    && row[6] == shell
                    && after.groups.get(name).is_some_and(|r| r[2] == id),
                "fresh qualification account differs",
            )?;
        }
        Ok(())
    }

    fn summary(&self) -> Value {
        json!({"users":self.users.values().map(|r| json!({"name":r[0],"uid":r[2].parse::<u32>().unwrap(),"gid":r[3].parse::<u32>().unwrap()})).collect::<Vec<_>>(),
            "groups":self.groups.iter().map(|(n,r)|(n.clone(),r[2].parse::<u32>().unwrap())).collect::<BTreeMap<_,_>>(),
            "original_service_accounts_preserved":true,"private_accounts_copied":false,
            "fixture_memberships":["audio","video","render","input","netdev"]})
    }
}

fn exists(tree: &Snapshot, path: &str) -> Result<bool> {
    match tree.identity(path) {
        Ok(_) => Ok(true),
        Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
            Ok(false)
        }
        Err(e) => Err(e),
    }
}

fn locked_shadow(tree: &Snapshot) -> Result<()> {
    let bytes = tree.bytes("/etc/shadow", 1024 * 1024)?;
    for line in std::str::from_utf8(&bytes)?.lines() {
        let fields: Vec<_> = line.split(':').collect();
        ensure(
            fields.len() == 9 && (fields[1].starts_with('!') || fields[1].starts_with('*')),
            "fresh normal accounts must remain password locked",
        )?;
    }
    Ok(())
}

fn database(tree: &Snapshot) -> Result<Value> {
    let mut result = BTreeMap::new();
    for (path, identity) in tree.inventory()? {
        if path == "/var/lib/dpkg" || path.starts_with("/var/lib/dpkg/") {
            let content = match FileType::from_raw_mode(identity.mode) {
                FileType::RegularFile => {
                    let (id, sha, attrs) = tree.regular(&path)?;
                    ensure(id == identity, "normal package database changed while read")?;
                    json!({"sha256":sha,"xattrs":attrs})
                }
                FileType::Symlink => json!({"target":tree.link(&path)?.1}),
                FileType::Directory => Value::Null,
                _ => return Err("unexpected special object in complete package database".into()),
            };
            result.insert(path, json!({"identity":identity,"content":content}));
        }
    }
    ensure(
        result.contains_key("/var/lib/dpkg/status") && result.len() > 1000,
        "complete normal package database missing",
    )?;
    Ok(serde_json::to_value(result)?)
}

/// Retire only a source-owned QA identity/config slot in this newly verified
/// copy. The original bootstrap source remains immutable. No caller path,
/// symlink traversal, recursive removal, or package database mutation.
fn retire_fixed(tree: &Snapshot, path: &str, actions: &mut Vec<Value>) -> Result<()> {
    const ALLOWED: &[&str] = &[
        "/etc/machine-id",
        "/var/lib/dbus/machine-id",
        "/etc/hostname",
        "/etc/hosts",
        "/etc/fstab",
        "/etc/localtime",
        "/etc/resolv.conf",
        "/etc/gdm3/custom.conf",
        "/etc/subuid",
        "/etc/subgid",
        "/etc/ssh/ssh_host_ed25519_key",
        "/etc/ssh/ssh_host_ed25519_key.pub",
        "/etc/ssh/ssh_host_rsa_key",
        "/etc/ssh/ssh_host_rsa_key.pub",
        "/etc/ssh/ssh_host_ecdsa_key",
        "/etc/ssh/ssh_host_ecdsa_key.pub",
    ];
    ensure(
        ALLOWED.contains(&path),
        "unapproved fresh identity replacement",
    )?;
    if !exists(tree, path)? {
        return Ok(());
    }
    let before = tree.identity(path)?;
    ensure(
        before.uid == 0 && before.gid == 0 && before.nlink == 1,
        "fresh identity slot owner or links differ",
    )?;
    let (held, evidence) = match FileType::from_raw_mode(before.mode) {
        FileType::RegularFile => {
            ensure(
                before.mode & 0o022 == 0,
                "fresh identity slot is writable by another user",
            )?;
            let mut file = tree.file(path)?;
            ensure(fs::stat(&file)? == before, "fresh identity slot changed")?;
            let sha = fs::hash(&file)?;
            file.seek(SeekFrom::Start(0))?;
            (Some(file), json!({"identity":before,"sha256":sha}))
        }
        FileType::Symlink => (None, json!({"identity":before,"target":tree.link(path)?.1})),
        _ => return Err("fresh identity slot is not a regular file or alias".into()),
    };
    let (parent, name) = tree.parent(path)?;
    ensure(
        tree.identity(path)? == before
            && held
                .as_ref()
                .is_none_or(|f| fs::stat(f).ok().as_ref() == Some(&before)),
        "fresh identity changed before retirement",
    )?;
    rfs::unlinkat(&parent, name.as_str(), AtFlags::empty())?;
    rfs::fsync(&parent)?;
    if let Some(file) = held {
        let after = fs::stat(&file)?;
        ensure(
            after.dev == before.dev && after.ino == before.ino && after.nlink == 0,
            "retired fresh identity remains aliased",
        )?;
    }
    ensure(!exists(tree, path)?, "fresh identity pathname was replaced")?;
    actions.push(
        json!({"operation":"retire_fresh_bootstrap_identity_only","path":path,"original":evidence}),
    );
    Ok(())
}

pub(super) fn initialize(
    root: &Path,
    work: &Path,
    inputs: &Inputs,
    manifest: &CompleteManifest,
) -> Result<Value> {
    ensure(
        rustix::process::geteuid().as_raw() == 0 && root == work.join("root"),
        "complete initialization requires its private root",
    )?;
    let snapshot = Snapshot::open(root)?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    ensure(
        crate::boot_native::valid_name(&inputs.hostname)
            && inputs.hostname.len() <= 63
            && !inputs.hostname.starts_with('-')
            && !inputs.hostname.ends_with('-')
            && crate::boot_native::valid_uuid(&inputs.root_filesystem_uuid)
            && crate::boot_native::valid_uuid(&inputs.network_connection_uuid)
            && inputs.root_filesystem_uuid != inputs.network_connection_uuid,
        "invalid fresh complete identities",
    )?;
    let (original, passwd_before, group_before) = Accounts::read(&snapshot)?;
    let (gdm_uid, gdm_gid) = original.gdm()?;
    let additions = original.additions()?;
    locked_shadow(&snapshot)?;
    ensure(
        !exists(&snapshot, "/home/alex")? && snapshot.names("/home")?.is_empty(),
        "fresh complete root contains an existing user home",
    )?;
    ensure(
        !exists(&snapshot, "/var/lib/snapd/state.json")?,
        "unreviewed Snap account state in fresh root",
    )?;
    for path in ["/etc/subuid", "/etc/subgid"] {
        ensure(
            !exists(&snapshot, path)? || snapshot.bytes(path, 65536)?.is_empty(),
            "fresh complete source already delegates subordinate IDs",
        )?;
    }
    let config = snapshot.bytes(crate::boot_gdm_proof::CONFIG, 65536)?;
    let timed = crate::boot_native::gdm_timed_login(&config)?;
    let greeter_session = crate::boot_gdm_proof::original_session(&tree)?;
    for (path, _) in crate::boot_gdm_proof::FILES {
        ensure(
            !exists(&snapshot, path)?,
            "fresh greeter proof is create-only",
        )?;
    }
    let expected_status = manifest
        .entries
        .iter()
        .find(|e| e.path == "/var/lib/dpkg/status")
        .ok_or("source database binding missing")?;
    let (_, sha, _) = snapshot.regular("/var/lib/dpkg/status")?;
    ensure(
        matches!(&expected_status.content,crate::model::Content::Regular{sha256} if *sha256 == sha),
        "normal package status changed before fresh identity initialization",
    )?;
    let database_before = database(&snapshot)?;
    let database_sha = fs::digest(&serde_json::to_vec(&database_before)?);
    boot_files::write_new(
        &work.join("COMPLETE-NATIVE-INIT-STARTED.json"),
        &serde_json::to_vec_pretty(
            &json!({"schema":"droidloom.complete-native-init-started.v1",
            "inputs":inputs,"root":root,"database_sha256":database_sha,
            "original_passwd_sha256":fs::digest(&passwd_before),"original_group_sha256":fs::digest(&group_before),
            "gdm_uid":gdm_uid,"gdm_gid":gdm_gid,"guest_qualified":false}),
        )?,
        0o600,
    )?;
    let mut actions = Vec::new();
    let mut commands = Vec::new();
    rfs::fchmod(&tree.root, Mode::from_raw_mode(0o755))?;
    for path in [
        "/etc/systemd/system",
        "/etc/systemd/user",
        "/etc/ssh/sshd_config.d",
        "/run",
        "/dev",
        "/proc",
        "/sys",
        "/home",
        "/var/lib/dbus",
    ] {
        crate::boot_native::directory(root, path, 0o755)?;
    }
    let root_name = fs::absolute_string(root)?;
    let root_arg = format!("--root={root_name}");
    let mut args = vec![root_arg.clone(), "--inline".into()];
    args.extend(additions);
    crate::boot_native::run_native(
        root,
        work,
        &tree,
        "complete-native-sysusers",
        "/usr/bin/systemd-sysusers",
        &args,
        &mut commands,
    )?;
    let (after, passwd_after, group_after) = Accounts::read(&snapshot)?;
    original.verify_after(&after)?;
    locked_shadow(&snapshot)?;
    for path in [
        "/etc/machine-id",
        "/var/lib/dbus/machine-id",
        "/etc/hostname",
        "/etc/localtime",
    ] {
        retire_fixed(&snapshot, path, &mut actions)?;
    }
    crate::boot_native::run_native(
        root,
        work,
        &tree,
        "complete-native-firstboot",
        "/usr/bin/systemd-firstboot",
        &[
            root_arg.clone(),
            "--setup-machine-id".into(),
            format!("--hostname={}", inputs.hostname),
            "--timezone=UTC".into(),
            "--welcome=no".into(),
        ],
        &mut commands,
    )?;
    let machine = snapshot.bytes("/etc/machine-id", 128)?;
    let machine_id = std::str::from_utf8(&machine)?.trim();
    ensure(
        machine_id.len() == 32
            && machine_id.bytes().all(|b| b.is_ascii_hexdigit())
            && machine_id.bytes().any(|b| b != b'0'),
        "fresh complete machine ID invalid",
    )?;
    let old_machine = manifest
        .entries
        .iter()
        .find(|e| e.path == "/etc/machine-id");
    ensure(old_machine.is_none_or(|e| !matches!(&e.content,crate::model::Content::Regular{sha256} if *sha256 == fs::digest(&machine))),
           "machine ID was not regenerated")?;
    crate::boot_native::link_guest(
        root,
        &tree,
        "/var/lib/dbus/machine-id",
        "/etc/machine-id",
        &mut actions,
    )?;
    for (path, bytes, mode) in [
        (
            "/etc/hosts",
            format!(
                "127.0.0.1 localhost\n127.0.1.1 {}\n::1 localhost ip6-localhost ip6-loopback\n",
                inputs.hostname
            )
            .into_bytes(),
            0o644,
        ),
        (
            "/etc/fstab",
            format!(
                "# Fresh qualification root only.\nUUID={} / ext4 defaults 0 1\n",
                inputs.root_filesystem_uuid
            )
            .into_bytes(),
            0o644,
        ),
        ("/etc/gdm3/custom.conf", timed, 0o644),
        (
            "/etc/subuid",
            b"droidloom-cell-u1000:200000:100000\n".to_vec(),
            0o644,
        ),
        (
            "/etc/subgid",
            b"droidloom-cell-u1000:200000:100000\n".to_vec(),
            0o644,
        ),
    ] {
        retire_fixed(&snapshot, path, &mut actions)?;
        crate::boot_native::write_guest(root, path, &bytes, mode, &mut actions)?;
    }
    retire_fixed(&snapshot, "/etc/resolv.conf", &mut actions)?;
    crate::boot_native::link_guest(
        root,
        &tree,
        "/etc/resolv.conf",
        "/run/systemd/resolve/stub-resolv.conf",
        &mut actions,
    )?;
    crate::boot_native::write_guest(
        root,
        "/etc/NetworkManager/conf.d/99-pocket4-fixture.conf",
        b"# Fresh qualification guest only.\n[keyfile]\nunmanaged-devices=\n",
        0o644,
        &mut actions,
    )?;
    crate::boot_native::write_guest(root,"/etc/NetworkManager/system-connections/pocket4-fixture-ethernet.nmconnection",
        format!("[connection]\nid=pocket4-fixture-ethernet\nuuid={}\ntype=ethernet\nautoconnect=true\n\n[ethernet]\n\n[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=disabled\n",inputs.network_connection_uuid).as_bytes(),0o600,&mut actions)?;
    for (path, bytes) in crate::boot_gdm_proof::FILES {
        crate::boot_native::write_guest(root, path, bytes, 0o444, &mut actions)?;
    }
    crate::boot_native::run_native(
        root,
        work,
        &tree,
        "complete-native-tmpfiles",
        "/usr/bin/systemd-tmpfiles",
        &[root_arg.clone(), "--create".into(), "--boot".into()],
        &mut commands,
    )?;
    crate::boot_native::directory(root, "/home/alex", 0o700)?;
    crate::boot_native::directory(root, "/home/alex/.ssh", 0o700)?;
    crate::boot_native::write_guest(
        root,
        "/home/alex/.dmrc",
        b"[Desktop]\nSession=ubuntu\n",
        0o600,
        &mut actions,
    )?;
    crate::boot_native::write_guest(
        root,
        "/var/lib/AccountsService/users/alex",
        b"[User]\nSession=ubuntu\nXSession=ubuntu\nSystemAccount=false\n",
        0o600,
        &mut actions,
    )?;
    crate::boot_native::write_guest(root,"/etc/ssh/sshd_config.d/00-pocket4-fixture.conf",
        b"# Fresh generated key and loopback qualification only.\nPermitRootLogin no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPubkeyAuthentication yes\nAuthenticationMethods publickey\nAllowUsers alex\n",0o644,&mut actions)?;
    for path in [
        "/etc/ssh/ssh_host_ed25519_key",
        "/etc/ssh/ssh_host_ed25519_key.pub",
        "/etc/ssh/ssh_host_rsa_key",
        "/etc/ssh/ssh_host_rsa_key.pub",
        "/etc/ssh/ssh_host_ecdsa_key",
        "/etc/ssh/ssh_host_ecdsa_key.pub",
    ] {
        retire_fixed(&snapshot, path, &mut actions)?;
    }
    crate::boot_native::run_native(
        root,
        work,
        &tree,
        "complete-native-ssh-hostkeys",
        "/usr/bin/ssh-keygen",
        &["-A".into(), "-f".into(), root_name.clone()],
        &mut commands,
    )?;
    let key = work.join("fixture-ssh-client-key");
    let public = work.join("fixture-ssh-client-key.pub");
    ensure(
        std::fs::symlink_metadata(&key).is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound)
            && std::fs::symlink_metadata(&public)
                .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound),
        "fresh SSH identity destination exists",
    )?;
    crate::boot_native::run_native(
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
    let public_pin = boot_files::pin_file(&public)?;
    let public_bytes = boot_files::read_pin(&public_pin, 4096)?;
    let public_text = std::str::from_utf8(&public_bytes)?;
    ensure(
        public_text.starts_with("ssh-ed25519 ") && public_text.lines().count() == 1,
        "fresh SSH public key format differs",
    )?;
    crate::boot_native::write_guest(
        root,
        "/home/alex/.ssh/authorized_keys",
        &public_bytes,
        0o600,
        &mut actions,
    )?;
    for (path, mode) in [
        ("/home/alex/.dmrc", 0o600),
        ("/home/alex/.ssh/authorized_keys", 0o600),
    ] {
        crate::boot_native::set_owned(&tree.file(path)?, 1000, 1000, mode)?;
    }
    crate::boot_native::set_owned(&tree.dir("/home/alex/.ssh")?, 1000, 1000, 0o700)?;
    crate::boot_native::set_owned(&tree.dir("/home/alex")?, 1000, 1000, 0o700)?;
    let (parent, name) = fs::absolute_parent(&fs::absolute_string(&key)?)?;
    let private = fs::identity(&rfs::statat(&parent, name, AtFlags::SYMLINK_NOFOLLOW)?);
    ensure(
        FileType::from_raw_mode(private.mode) == FileType::RegularFile
            && private.nlink == 1
            && private.uid == 0
            && private.gid == 0
            && private.mode & 0o7777 == 0o600,
        "fresh client key is not protected",
    )?;
    let mut units: Vec<String> = crate::boot_native::SYSTEM_UNITS
        .iter()
        .map(|s| s.to_string())
        .collect();
    units.push("ssh.socket".into());
    let mut args = vec![root_arg.clone(), "enable".into()];
    args.extend(units.clone());
    crate::boot_native::run_native(
        root,
        work,
        &tree,
        "complete-native-enable-system",
        "/usr/bin/systemctl",
        &args,
        &mut commands,
    )?;
    crate::boot_native::run_native(
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
    args.extend(crate::boot_native::USER_UNITS.iter().map(|s| s.to_string()));
    crate::boot_native::run_native(
        root,
        work,
        &tree,
        "complete-native-enable-user",
        "/usr/bin/systemctl",
        &args,
        &mut commands,
    )?;
    let (final_accounts, final_passwd, final_group) = Accounts::read(&snapshot)?;
    original.verify_after(&final_accounts)?;
    ensure(
        passwd_after == final_passwd && group_after == final_group,
        "native initialization changed accounts after sysusers",
    )?;
    locked_shadow(&snapshot)?;
    let database_after = database(&snapshot)?;
    ensure(
        database_before == database_after,
        "fresh initialization changed the normal package database",
    )?;
    fs::assert_root_namespace(&root_name, &tree)?;
    let binding = AccountBinding {
        schema: "droidloom.complete-native-gdm-account.v1".into(),
        name: "gdm".into(),
        uid: gdm_uid,
        gid: gdm_gid,
        original_passwd_sha256: fs::digest(&passwd_before),
        original_group_sha256: fs::digest(&group_before),
        prepared_passwd_sha256: fs::digest(&final_passwd),
        prepared_group_sha256: fs::digest(&final_group),
    };
    Ok(
        json!({"schema":"droidloom.complete-native-initialization.v1","root":root,"work":work,"inputs":inputs,
        "accounts":final_accounts.summary(),"gdm_account_binding":binding,
        "complete_package_database_preserved":true,"package_database_before_after_sha256":database_sha,
        "normal_package_database_updated":false,"original_service_accounts_preserved":true,
        "machine_id":machine_id,"actions":actions,"native_commands":commands,
        "fresh_ssh":{"fresh_private_key_path":key,"public_key":public_pin,"private_key_contents_read":false,
            "network_scope":"subsequent VM loopback forwarding only"},
        "fresh_greeter_proof_session":greeter_session,"fresh_shadow_locked":true,
        "system_units_enabled":units,"user_units_enabled":crate::boot_native::USER_UNITS,
        "private_accounts_copied":false,"native_initialization_complete":true,
        "guest_started":false,"guest_qualified":false,"production_ready":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_service_accounts_are_preserved_and_collisions_fail() {
        let users = fields(
            b"root:x:0:0:root:/root:/bin/bash\ngdm:x:981:981:GDM:/var/lib/gdm3:/bin/false\n",
            7,
        )
        .unwrap();
        let groups = fields(b"root:x:0:\ngdm:x:981:\naudio:x:29:\nvideo:x:44:\nrender:x:989:\ninput:x:993:\nnetdev:x:103:\n",4).unwrap();
        let original = Accounts { users, groups };
        assert_eq!(original.gdm().unwrap(), (981, 981));
        assert!(original.additions().is_ok());
        let mut collision = original.clone();
        collision.users.insert(
            "foreign".into(),
            vec![
                "foreign".into(),
                "x".into(),
                "1000".into(),
                "1000".into(),
                "".into(),
                "/home/foreign".into(),
                "/bin/bash".into(),
            ],
        );
        assert!(collision.additions().is_err());
        let mut changed = original.clone();
        changed.users.get_mut("gdm").unwrap()[3] = "121".into();
        assert!(changed.gdm().is_err());
        assert!(original.verify_after(&changed).is_err());
    }
    #[test]
    #[ignore = "requires the independently verified root-owned complete materialization"]
    fn actual_complete_fresh_initialization_preserves_the_whole_database() -> Result<()> {
        let work = std::path::PathBuf::from(std::env::var("DROIDLOOM_COMPLETE_INIT_WORK")?);
        let manifest_path = std::env::var("DROIDLOOM_COMPLETE_INIT_MANIFEST")?;
        let manifest_sha = std::env::var("DROIDLOOM_COMPLETE_INIT_MANIFEST_SHA256")?;
        let manifest: CompleteManifest = fs::read_json(&manifest_path, &manifest_sha)?;
        let root = work.join("root");
        crate::complete_native::verify(&manifest, &manifest_sha, &root)?;
        let inputs = Inputs {
            hostname: "p4-complete-init-proof".into(),
            root_filesystem_uuid: "92658f37-0d65-4f63-919b-a445619185dd".into(),
            network_connection_uuid: "e970b83f-4112-4557-a90f-732f73ea306e".into(),
        };
        let result = initialize(&root, &work, &inputs, &manifest)?;
        let tree = Snapshot::open(&root)?;
        let binding: AccountBinding =
            serde_json::from_value(result["gdm_account_binding"].clone())?;
        binding.verify(
            &tree.bytes("/etc/passwd", 1048576)?,
            &tree.bytes("/etc/group", 1048576)?,
        )?;
        ensure(
            result["complete_package_database_preserved"] == true
                && result["original_service_accounts_preserved"] == true
                && result["normal_package_database_updated"] == false,
            "complete initializer did not preserve the normal package authority",
        )?;
        fs::write_json(
            &fs::absolute_string(&work.join("INIT-RESULT.json"))?,
            &result,
            0,
        )?;
        Ok(())
    }
}
