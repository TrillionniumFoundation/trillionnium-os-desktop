//! Fresh native Ubuntu state for a verified, isolated public-root clone.
//! This never starts a service or imports host passwords, keys or user homes.
use crate::boot_files::{self, FilePin};
use crate::{Result, ensure, fs, paths};
use rustix::fs::{FileType, Mode};
use rustix::process::{Gid, Uid};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::Path;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PublicConfigInput {
    pub input: FilePin,
    pub guest_path: String,
    pub mode: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeInputs {
    pub public_passwd: FilePin,
    pub public_group: FilePin,
    pub alias_receipt: FilePin,
    pub public_configs: Vec<PublicConfigInput>,
    pub snap_mounts: Vec<PublicConfigInput>,
    pub hostname: String,
    pub username: String,
    pub uid: u32,
    pub gid: u32,
    pub root_filesystem_uuid: String,
    pub network_connection_uuid: String,
    pub generate_fixture_ssh: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AliasIdentity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    size: u64,
    mtime_ns: i64,
    ctime_ns: i64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Alias {
    path: String,
    target: String,
    target_bytes_sha256: String,
    source_identity: AliasIdentity,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Aliases {
    schema: String,
    source_root: String,
    entries: Vec<Alias>,
    followed_targets: bool,
    private_state_read: bool,
    guest_qualified: bool,
}

const PUBLIC_CONFIGS: &[&str] = &[
    "/etc/gdm3/custom.conf",
    "/etc/gdm3/greeter.dconf-defaults",
    "/etc/ssh/sshd_config",
    "/etc/locale.gen",
    "/etc/locale.conf",
    "/etc/environment",
    "/etc/X11/rgb.txt",
    "/etc/python3.14/sitecustomize.py",
    "/etc/modules",
];
const SNAP_NAMES: &[&str] = &[
    "snapd",
    "snapd-desktop-integration",
    "core24",
    "mesa-2404",
    "gtk-common-themes",
    "gnome-46-2404",
    "bare",
];
const SYSTEM_UNITS: &[&str] = &[
    "gdm.service",
    "NetworkManager.service",
    "wpa_supplicant.service",
    "systemd-resolved.service",
    "bluetooth.service",
    "apparmor.service",
    "snapd.socket",
    "snapd.apparmor.service",
];
const USER_UNITS: &[&str] = &[
    "dbus.socket",
    "pipewire.socket",
    "pipewire-pulse.socket",
    "wireplumber.service",
];
const ALIASES_TO_RESTORE: &[(&str, &str)] = &[
    ("/bin", "usr/bin"),
    ("/sbin", "usr/sbin"),
    ("/lib", "usr/lib"),
    ("/lib64", "usr/lib64"),
    ("/usr/share/X11/rgb.txt", "/etc/X11/rgb.txt"),
    ("/usr/share/zoneinfo/localtime", "/etc/localtime"),
    (
        "/usr/lib/environment.d/99-environment.conf",
        "/etc/environment",
    ),
    ("/etc/xdg/systemd/user", "../../systemd/user"),
    ("/etc/modules-load.d/modules.conf", "../modules"),
    (
        "/usr/lib/python3.14/sitecustomize.py",
        "/etc/python3.14/sitecustomize.py",
    ),
    (
        "/usr/share/gdm/dconf/90-debian-settings",
        "/etc/gdm3/greeter.dconf-defaults",
    ),
];

fn valid_name(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 64
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
}

fn valid_uuid(s: &str) -> bool {
    s.len() == 36
        && s.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
        && s.bytes().any(|b| b != b'0' && b != b'-')
}

#[derive(Clone, Debug)]
struct Account {
    name: String,
    uid: u32,
    gid: u32,
    home: String,
    shell: String,
}

fn account_path(field: &str) -> Result<String> {
    ensure(
        field.starts_with('/')
            && field.is_ascii()
            && !field
                .bytes()
                .any(|b| b.is_ascii_control() || b.is_ascii_whitespace() || b"\"'\\%".contains(&b)),
        "unsafe native account path",
    )?;
    // Stock gnome-initial-setup uses /run/gnome-initial-setup/. Removing
    // trailing separators preserves its directory identity; dot/parent and
    // internal empty components remain forbidden.
    let trimmed = field.trim_end_matches('/');
    let normalized = if trimmed.is_empty() { "/" } else { trimmed };
    if normalized != "/" {
        paths::parts(normalized)?;
    }
    Ok(normalized.to_owned())
}

fn native_accounts(passwd: &[u8], group: &[u8]) -> Result<(Vec<String>, Value)> {
    let mut groups = BTreeMap::<String, u32>::new();
    let mut group_ids = BTreeMap::<u32, String>::new();
    for line in std::str::from_utf8(group)?
        .lines()
        .filter(|s| !s.is_empty())
    {
        let cols: Vec<_> = line.split(':').collect();
        ensure(
            cols.len() == 4 && valid_name(cols[0]),
            "invalid public group record",
        )?;
        ensure(
            ["x", "*", "!", ""].contains(&cols[1]),
            "public group has a non-placeholder password field",
        )?;
        let gid: u32 = cols[2].parse()?;
        if gid < 1000 || gid == 65534 || cols[0] == "alex" {
            ensure(
                groups.insert(cols[0].into(), gid).is_none(),
                "duplicate native group",
            )?;
            ensure(
                group_ids.insert(gid, cols[0].into()).is_none(),
                "native group ID alias requires separate review",
            )?;
        }
    }
    let mut users = BTreeMap::<String, Account>::new();
    let mut user_ids = BTreeSet::new();
    for line in std::str::from_utf8(passwd)?
        .lines()
        .filter(|s| !s.is_empty())
    {
        let cols: Vec<_> = line.split(':').collect();
        ensure(
            cols.len() == 7 && valid_name(cols[0]),
            "invalid public passwd record",
        )?;
        ensure(
            ["x", "*", "!", "!!", ""].contains(&cols[1]),
            "public passwd has a non-placeholder password field",
        )?;
        let uid: u32 = cols[2].parse()?;
        let gid: u32 = cols[3].parse()?;
        if uid < 1000 || uid == 65534 || cols[0] == "alex" {
            ensure(group_ids.contains_key(&gid), "native primary group missing")?;
            let home = account_path(cols[5])?;
            let shell = account_path(cols[6])?;
            ensure(
                user_ids.insert(uid),
                "native user ID alias requires separate review",
            )?;
            let user = Account {
                name: cols[0].into(),
                uid,
                gid,
                home,
                shell,
            };
            ensure(
                users.insert(cols[0].into(), user).is_none(),
                "duplicate native user",
            )?;
        }
    }
    for (name, uid, gid) in [
        ("root", 0, 0),
        ("alex", 1000, 1000),
        ("droidloom-cell-u1000", 976, 976),
    ] {
        let user = users
            .get(name)
            .ok_or("required native numeric identity absent")?;
        ensure(
            user.uid == uid && user.gid == gid,
            "required native numeric identity differs",
        )?;
    }
    let alex = users.get_mut("alex").ok_or("fixture user absent")?;
    alex.home = "/home/alex".into();
    alex.shell = "/bin/bash".into();
    let mut lines = Vec::new();
    for (name, gid) in &groups {
        lines.push(format!("g {name} {gid}"));
    }
    for user in users.values() {
        lines.push(format!(
            "u {} {}:{} \"Fixture native account\" {} {}",
            user.name, user.uid, user.gid, user.home, user.shell
        ));
    }
    for group in ["audio", "video", "render", "input", "netdev"] {
        ensure(
            groups.contains_key(group),
            "required fixture device group absent",
        )?;
        lines.push(format!("m alex {group}"));
    }
    let summary = json!({"users":users.values().map(|u| json!({"name":u.name,"uid":u.uid,"gid":u.gid})).collect::<Vec<_>>(),
        "groups":groups,"host_memberships_imported":false,"host_passwords_imported":false,
        "fixture_memberships":["audio","video","render","input","netdev"]});
    Ok((lines, summary))
}

fn gdm_autologin(bytes: &[u8]) -> Result<Vec<u8>> {
    let s = std::str::from_utf8(bytes)?;
    let active: Vec<_> = s
        .lines()
        .map(str::trim)
        .filter(|l| !l.is_empty() && !l.starts_with('#'))
        .collect();
    ensure(
        active == ["[daemon]", "[security]", "[debug]"],
        "GDM input has unreviewed active settings",
    )?;
    ensure(
        s.matches("[daemon]").count() == 1,
        "ambiguous GDM daemon section",
    )?;
    Ok(s.replacen("[daemon]","[daemon]\n# Isolated qualification user; no original account secrets.\nAutomaticLoginEnable=true\nAutomaticLogin=alex\nWaylandEnable=true",1).into_bytes())
}

#[derive(Debug)]
struct SnapMount {
    name: String,
    revision: String,
    unit: String,
    image: String,
    mountpoint: String,
}

fn parse_snap(input: &PublicConfigInput, bytes: &[u8]) -> Result<SnapMount> {
    let s = std::str::from_utf8(bytes)?;
    let wheres: Vec<_> = s.lines().filter_map(|l| l.strip_prefix("Where=")).collect();
    ensure(wheres.len() == 1, "Snap mount must have one mountpoint")?;
    let p: Vec<_> = wheres[0].split('/').collect();
    ensure(
        p.len() == 4
            && p[0].is_empty()
            && p[1] == "snap"
            && SNAP_NAMES.contains(&p[2])
            && !p[3].is_empty()
            && p[3].len() <= 12
            && p[3].bytes().all(|b| b.is_ascii_digit()),
        "unapproved Snap mount identity",
    )?;
    let name = p[2].to_owned();
    let revision = p[3].to_owned();
    let unit = format!("snap-{}-{revision}.mount", name.replace('-', "\\x2d"));
    let guest_path = format!("/etc/systemd/system/{unit}");
    let image = format!("/var/lib/snapd/snaps/{name}_{revision}.snap");
    let mountpoint = format!("/snap/{name}/{revision}");
    let expected = format!(
        "[Unit]\nDescription=Mount unit for {name}, revision {revision}\nAfter=snapd.mounts-pre.target\nBefore=snapd.mounts.target\n\n[Mount]\nWhat={image}\nWhere={mountpoint}\nType=squashfs\nOptions=nodev,ro,x-gdu.hide,x-gvfs-hide\nLazyUnmount=yes\n\n[Install]\nWantedBy=snapd.mounts.target\nWantedBy=multi-user.target\n"
    );
    ensure(
        s == expected
            && input.guest_path == guest_path
            && input.input.path == Path::new(&guest_path)
            && input.mode == 0o644,
        "Snap unit differs from reviewed native read-only mount template",
    )?;
    Ok(SnapMount {
        name,
        revision,
        unit,
        image,
        mountpoint,
    })
}

fn missing(tree: &fs::Tree, path: &str) -> Result<bool> {
    match tree.identity(path) {
        Ok(_) => Ok(false),
        Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
            Ok(true)
        }
        Err(e) => Err(e),
    }
}

/// New parents must be traversable by native service users; private leaves are
/// requested separately. Do not silently chmod existing ancestor directories.
fn directory(root: &Path, guest: &str, mode: u32) -> Result<()> {
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let names = paths::parts(guest)?;
    let mut path = String::new();
    for (index, name) in names.iter().enumerate() {
        path.push('/');
        path.push_str(name);
        if missing(&tree, &path)? {
            tree.mkdir(&path)?;
            let fd = tree.dir(&path)?;
            rustix::fs::fchmod(
                &fd,
                Mode::from_raw_mode(if index + 1 == names.len() {
                    mode
                } else {
                    0o755
                }),
            )?;
        } else {
            let id = tree.identity(&path)?;
            ensure(
                FileType::from_raw_mode(id.mode) == FileType::Directory
                    && id.uid == 0
                    && id.mode & 0o022 == 0,
                "fixture directory is an alias, untrusted or writable by other users",
            )?;
        }
    }
    // Only the named leaf has an explicit requested mode.
    rustix::fs::fchmod(&tree.dir(guest)?, Mode::from_raw_mode(mode))?;
    Ok(())
}

fn parent_directory(root: &Path, guest: &str) -> Result<()> {
    let parent = paths::parent(guest);
    if parent == "/" {
        return Ok(());
    }
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    if missing(&tree, parent)? {
        directory(root, parent, 0o755)?;
    } else {
        tree.dir(parent)?;
    }
    Ok(())
}

fn write_guest(
    root: &Path,
    guest: &str,
    bytes: &[u8],
    mode: u32,
    actions: &mut Vec<Value>,
) -> Result<()> {
    parent_directory(root, guest)?;
    let path = boot_files::guest_path(root, guest)?;
    boot_files::write_new(&path, bytes, mode)?;
    actions.push(json!({"operation":"create_fixture_file","path":guest,"bytes":bytes.len(),"sha256":fs::digest(bytes),"mode":mode}));
    Ok(())
}

fn link_guest(
    root: &Path,
    tree: &fs::Tree,
    guest: &str,
    target: &str,
    actions: &mut Vec<Value>,
) -> Result<()> {
    parent_directory(root, guest)?;
    if !missing(tree, guest)? {
        let (id, old) = tree.read_link(guest)?;
        ensure(
            old == target && id.uid == 0 && id.gid == 0,
            "existing fixture alias differs",
        )?;
        return Ok(());
    }
    tree.symlink(guest, target, &boot_files::clean_metadata(0o120777))?;
    let (id, back) = tree.read_link(guest)?;
    ensure(
        back == target && id.uid == 0 && id.gid == 0,
        "fixture alias readback differs",
    )?;
    actions.push(json!({"operation":"create_fixture_symlink","path":guest,"target":target}));
    Ok(())
}

fn read_guest(tree: &fs::Tree, guest: &str, limit: u64) -> Result<Vec<u8>> {
    let mut f = tree.file(guest)?;
    let before = fs::stat(&f)?;
    ensure(before.size <= limit, "fixture file exceeds limit")?;
    let mut b = Vec::new();
    Read::by_ref(&mut f).take(limit + 1).read_to_end(&mut b)?;
    ensure(
        b.len() as u64 == before.size && fs::stat(&f)? == before && tree.identity(guest)? == before,
        "fixture changed while read",
    )?;
    Ok(b)
}

fn run_native(
    root: &Path,
    work: &Path,
    tree: &fs::Tree,
    name: &str,
    program: &str,
    args: &[String],
    commands: &mut Vec<Value>,
) -> Result<()> {
    fs::assert_root_namespace(&fs::absolute_string(root)?, tree)?;
    let (before, sha, attrs) = fs::read_regular(tree, program)?;
    ensure(
        before.mode & 0o111 != 0,
        "native fixture program is not executable",
    )?;
    let absolute = boot_files::guest_path(root, program)?;
    let result = boot_files::run_logged(work, name, &fs::absolute_string(&absolute)?, args, 60)?;
    let (after, after_sha, after_attrs) = fs::read_regular(tree, program)?;
    ensure(
        before == after && sha == after_sha && attrs == after_attrs,
        "native program changed during initialization",
    )?;
    fs::assert_root_namespace(&fs::absolute_string(root)?, tree)?;
    commands.push(json!({"executable_sha256":sha,"source_identity":before,"result":result}));
    Ok(())
}

fn set_owned(file: &File, uid: u32, gid: u32, mode: u32) -> Result<()> {
    rustix::fs::fchown(file, Some(Uid::from_raw(uid)), Some(Gid::from_raw(gid)))?;
    rustix::fs::fchmod(file, Mode::from_raw_mode(mode))?;
    rustix::fs::fsync(file)?;
    let i = fs::stat(file)?;
    ensure(
        i.uid == uid && i.gid == gid && i.mode & 0o7777 == mode,
        "fresh user ownership readback differs",
    )
}

/// `root` must be the separately verified clone created by prepare-native.
pub fn initialize(root: &Path, work: &Path, inputs: &NativeInputs) -> Result<Value> {
    ensure(
        rustix::process::geteuid().as_raw() == 0,
        "native initialization requires existing root rights",
    )?;
    let root_name = fs::absolute_string(root)?;
    let work_name = fs::absolute_string(work)?;
    ensure(
        work.starts_with("/var/lib/droidloom-qualification")
            && root.starts_with(work)
            && root != work
            && root != Path::new("/"),
        "native state is restricted to a private qualification work root",
    )?;
    let tree = fs::Tree::open(&root_name, 0)?;
    let work_tree = fs::Tree::open(&work_name, 0)?;
    ensure(
        fs::stat(&work_tree.root)?.mode & 0o777 == 0o700,
        "qualification work must be root-owned mode 0700",
    )?;
    ensure(
        inputs.username == "alex" && inputs.uid == 1000 && inputs.gid == 1000,
        "fixture identity must be alex 1000:1000",
    )?;
    ensure(
        valid_name(&inputs.hostname)
            && inputs.hostname.len() <= 63
            && !inputs.hostname.starts_with('-')
            && !inputs.hostname.ends_with('-'),
        "invalid fixture hostname",
    )?;
    ensure(
        valid_uuid(&inputs.root_filesystem_uuid)
            && valid_uuid(&inputs.network_connection_uuid)
            && inputs.root_filesystem_uuid != inputs.network_connection_uuid,
        "fresh filesystem/network UUIDs must be explicit and distinct",
    )?;
    ensure(
        inputs.public_passwd.path == Path::new("/etc/passwd")
            && inputs.public_group.path == Path::new("/etc/group"),
        "only reviewed public native account sources are accepted",
    )?;
    for p in [
        "/etc/passwd",
        "/etc/group",
        "/etc/shadow",
        "/etc/gshadow",
        "/etc/machine-id",
        "/etc/hostname",
        "/etc/fstab",
        "/home/alex",
        "/etc/ssh/ssh_host_ed25519_key",
        "/etc/ssh/ssh_host_rsa_key",
        "/etc/ssh/ssh_host_ecdsa_key",
        "/var/lib/snapd/state.json",
    ] {
        ensure(
            missing(&tree, p)?,
            "root already contains identity, secrets or active state; initialization is create-only",
        )?;
    }
    let passwd = boot_files::read_pin(&inputs.public_passwd, 1024 * 1024)?;
    let group = boot_files::read_pin(&inputs.public_group, 1024 * 1024)?;
    let (sysusers, account_summary) = native_accounts(&passwd, &group)?;
    let aliases: Aliases =
        serde_json::from_slice(&boot_files::read_pin(&inputs.alias_receipt, 1024 * 1024)?)?;
    ensure(
        aliases.schema == "droidloom.ubuntu-public-initialization-aliases.v1"
            && aliases.source_root == "/"
            && !aliases.followed_targets
            && !aliases.private_state_read
            && !aliases.guest_qualified,
        "wrong public alias evidence",
    )?;
    let mut alias_map = BTreeMap::new();
    for a in &aliases.entries {
        let i = &a.source_identity;
        ensure(
            i.uid == 0
                && i.gid == 0
                && i.mode == 0o120777
                && i.nlink == 1
                && i.dev > 0
                && i.ino > 0
                && i.size == a.target.len() as u64
                && i.mtime_ns >= 0
                && i.ctime_ns >= 0
                && fs::digest(a.target.as_bytes()) == a.target_bytes_sha256,
            "public alias metadata or digest differs",
        )?;
        ensure(
            alias_map
                .insert(a.path.as_str(), a.target.as_str())
                .is_none(),
            "duplicate public alias",
        )?;
    }
    for (p, target) in ALIASES_TO_RESTORE {
        ensure(
            alias_map.get(p) == Some(target),
            "required native alias differs or is absent",
        )?;
    }
    let mut configs = Vec::new();
    let mut config_paths = BTreeSet::new();
    for c in &inputs.public_configs {
        ensure(
            PUBLIC_CONFIGS.contains(&c.guest_path.as_str())
                && c.input.path == Path::new(&c.guest_path)
                && c.mode == 0o644
                && config_paths.insert(c.guest_path.as_str()),
            "unreviewed or duplicate public configuration",
        )?;
        let bytes = boot_files::read_pin(&c.input, 1024 * 1024)?;
        let output = if c.guest_path == "/etc/gdm3/custom.conf" {
            gdm_autologin(&bytes)?
        } else {
            bytes
        };
        configs.push((c, output));
    }
    ensure(
        config_paths == PUBLIC_CONFIGS.iter().copied().collect(),
        "reviewed native public configuration set is incomplete",
    )?;
    let mut snaps = Vec::new();
    let mut snap_names = BTreeSet::new();
    for c in &inputs.snap_mounts {
        let bytes = boot_files::read_pin(&c.input, 65536)?;
        let spec = parse_snap(c, &bytes)?;
        ensure(
            snap_names.insert(spec.name.clone()),
            "duplicate public Snap mount",
        )?;
        let alias = format!("/snap/{}/current", spec.name);
        ensure(
            alias_map.get(alias.as_str()) == Some(&spec.revision.as_str()),
            "Snap mount and source current alias disagree",
        )?;
        let image = tree.file(&spec.image)?;
        ensure(
            fs::stat(&image)?.size > 0,
            "selected public Snap image is empty",
        )?;
        snaps.push((c, bytes, spec));
    }
    ensure(
        snap_names == SNAP_NAMES.iter().map(|s| (*s).to_owned()).collect(),
        "public Snap dependency set is incomplete",
    )?;
    // Validate every input above before the first mutation. An interrupted run
    // retains its private partial root and cannot silently resume as a new one.
    boot_files::write_new(
        &work.join("NATIVE-INIT-STARTED.json"),
        &serde_json::to_vec_pretty(
            &json!({"schema":"droidloom.native-init-started.v1","root":root,"inputs":inputs,"guest_qualified":false}),
        )?,
        0o600,
    )?;
    let mut actions = Vec::new();
    let mut commands = Vec::new();
    // The outer work directory remains 0700 on the host. The filesystem's own
    // root must be traversable by service users after it becomes guest /.
    let root_mode_before = fs::stat(&tree.root)?.mode & 0o7777;
    rustix::fs::fchmod(&tree.root, Mode::from_raw_mode(0o755))?;
    actions
        .push(json!({"operation":"set_fixture_root_mode","before":root_mode_before,"after":0o755}));
    for d in [
        "/etc/systemd/system",
        "/etc/systemd/user",
        "/etc/ssh/sshd_config.d",
        "/etc/default",
        "/run",
        "/dev",
        "/proc",
        "/sys",
        "/root",
        "/var/lib/dbus",
        "/var/lib/NetworkManager",
        "/var/lib/bluetooth",
    ] {
        directory(root, d, if d == "/root" { 0o700 } else { 0o755 })?;
    }
    for (p, target) in &ALIASES_TO_RESTORE[..4] {
        link_guest(root, &tree, p, target, &mut actions)?;
    }
    for (c, bytes) in &configs {
        write_guest(root, &c.guest_path, bytes, c.mode, &mut actions)?;
        actions.push(json!({"operation":"reviewed_public_config","source":c.input,"guest_path":c.guest_path,
            "output_sha256":fs::digest(bytes),"fixture_change":if c.guest_path=="/etc/gdm3/custom.conf" {"explicit fresh alex autologin and Wayland"} else {"none"}}));
    }
    link_guest(
        root,
        &tree,
        "/etc/default/locale",
        "../locale.conf",
        &mut actions,
    )?;
    let root_arg = format!("--root={root_name}");
    let mut args = vec![root_arg.clone(), "--inline".into()];
    args.extend(sysusers);
    run_native(
        root,
        work,
        &tree,
        "native-sysusers",
        "/usr/bin/systemd-sysusers",
        &args,
        &mut commands,
    )?;
    run_native(
        root,
        work,
        &tree,
        "native-firstboot",
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
    for (p, target) in &ALIASES_TO_RESTORE[4..] {
        link_guest(root, &tree, p, target, &mut actions)?;
    }
    let machine_id = read_guest(&tree, "/etc/machine-id", 128)?;
    let id = std::str::from_utf8(&machine_id)?.trim();
    ensure(
        id.len() == 32
            && id.bytes().all(|b| b.is_ascii_hexdigit())
            && id.bytes().any(|b| b != b'0'),
        "native machine ID is missing or invalid",
    )?;
    link_guest(
        root,
        &tree,
        "/var/lib/dbus/machine-id",
        "/etc/machine-id",
        &mut actions,
    )?;
    write_guest(
        root,
        "/etc/hosts",
        format!(
            "127.0.0.1 localhost\n127.0.1.1 {}\n::1 localhost ip6-localhost ip6-loopback\n",
            inputs.hostname
        )
        .as_bytes(),
        0o644,
        &mut actions,
    )?;
    write_guest(
        root,
        "/etc/fstab",
        format!(
            "# Isolated qualification root; no host filesystems.\nUUID={} / ext4 defaults 0 1\n",
            inputs.root_filesystem_uuid
        )
        .as_bytes(),
        0o644,
        &mut actions,
    )?;
    for p in ["/etc/subuid", "/etc/subgid"] {
        write_guest(
            root,
            p,
            b"droidloom-cell-u1000:200000:100000\n",
            0o644,
            &mut actions,
        )?;
    }
    write_guest(
        root,
        "/etc/NetworkManager/conf.d/99-pocket4-fixture.conf",
        b"# Only the independent qualification guest.\n[keyfile]\nunmanaged-devices=\n",
        0o644,
        &mut actions,
    )?;
    let connection = format!(
        "[connection]\nid=pocket4-fixture-ethernet\nuuid={}\ntype=ethernet\nautoconnect=true\n\n[ethernet]\n\n[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=disabled\n",
        inputs.network_connection_uuid
    );
    write_guest(
        root,
        "/etc/NetworkManager/system-connections/pocket4-fixture-ethernet.nmconnection",
        connection.as_bytes(),
        0o600,
        &mut actions,
    )?;
    link_guest(
        root,
        &tree,
        "/etc/resolv.conf",
        "/run/systemd/resolve/stub-resolv.conf",
        &mut actions,
    )?;
    for (c, bytes, spec) in &snaps {
        directory(root, &spec.mountpoint, 0o755)?;
        write_guest(root, &c.guest_path, bytes, 0o644, &mut actions)?;
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
        "native-tmpfiles",
        "/usr/bin/systemd-tmpfiles",
        &[root_arg.clone(), "--create".into(), "--boot".into()],
        &mut commands,
    )?;
    directory(root, "/home/alex/.ssh", 0o700)?;
    let home = tree.dir("/home/alex")?;
    let ssh_dir = tree.dir("/home/alex/.ssh")?;
    let mut dmrc = tree.create_file("/home/alex/.dmrc")?;
    dmrc.write_all(b"[Desktop]\nSession=ubuntu\n")?;
    dmrc.sync_all()?;
    set_owned(&dmrc, 1000, 1000, 0o600)?;
    directory(root, "/var/lib/AccountsService/users", 0o700)?;
    write_guest(
        root,
        "/var/lib/AccountsService/users/alex",
        b"[User]\nSession=ubuntu\nXSession=ubuntu\nSystemAccount=false\n",
        0o600,
        &mut actions,
    )?;
    let mut ssh_result = Value::Null;
    if inputs.generate_fixture_ssh {
        write_guest(root,"/etc/ssh/sshd_config.d/00-pocket4-fixture.conf",b"# Fresh guest identity only; key generated for loopback qualification.\nPermitRootLogin no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPubkeyAuthentication yes\nAuthenticationMethods publickey\nAllowUsers alex\n",0o644,&mut actions)?;
        run_native(
            root,
            work,
            &tree,
            "native-ssh-hostkeys",
            "/usr/bin/ssh-keygen",
            &["-A".into(), "-f".into(), root_name.clone()],
            &mut commands,
        )?;
        let key = work.join("fixture-ssh-client-key");
        let public = work.join("fixture-ssh-client-key.pub");
        ensure(
            std::fs::symlink_metadata(&key)
                .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound)
                && std::fs::symlink_metadata(&public)
                    .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound),
            "fresh SSH key destination already exists",
        )?;
        run_native(
            root,
            work,
            &tree,
            "native-ssh-client-key",
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
        let pub_text = std::str::from_utf8(&pub_bytes)?;
        ensure(
            pub_text.starts_with("ssh-ed25519 ") && pub_text.lines().count() == 1,
            "generated SSH public key format differs",
        )?;
        let mut authorized = tree.create_file("/home/alex/.ssh/authorized_keys")?;
        authorized.write_all(&pub_bytes)?;
        authorized.sync_all()?;
        authorized.seek(SeekFrom::Start(0))?;
        ensure(
            fs::hash(&authorized)? == pub_pin.sha256,
            "authorized key readback differs",
        )?;
        set_owned(&authorized, 1000, 1000, 0o600)?;
        let (parent, name) = fs::absolute_parent(&fs::absolute_string(&key)?)?;
        let key_id = fs::identity(&rustix::fs::statat(
            &parent,
            name.as_str(),
            rustix::fs::AtFlags::SYMLINK_NOFOLLOW,
        )?);
        ensure(
            FileType::from_raw_mode(key_id.mode) == FileType::RegularFile
                && key_id.uid == 0
                && key_id.gid == 0
                && key_id.mode & 0o777 == 0o600
                && key_id.nlink == 1,
            "fresh client private key is not isolated",
        )?;
        ssh_result = json!({"fresh_private_key_path":key,"public_key":pub_pin,"private_key_contents_read":false,"network_scope":"subsequent VM loopback forwarding only"});
    }
    set_owned(&ssh_dir, 1000, 1000, 0o700)?;
    set_owned(&home, 1000, 1000, 0o700)?;
    let passwd_new = read_guest(&tree, "/etc/passwd", 1024 * 1024)?;
    let group_new = read_guest(&tree, "/etc/group", 1024 * 1024)?;
    let (_, new_account_summary) = native_accounts(&passwd_new, &group_new)?;
    ensure(
        new_account_summary["users"] == account_summary["users"],
        "fresh service numeric accounts differ",
    )?;
    let shadow = read_guest(&tree, "/etc/shadow", 1024 * 1024)?;
    for line in std::str::from_utf8(&shadow)?.lines() {
        let fields: Vec<_> = line.split(':').collect();
        ensure(
            fields.len() == 9 && (fields[1].starts_with('!') || fields[1].starts_with('*')),
            "fresh account shadow must remain locked",
        )?;
    }
    let mut units: Vec<String> = SYSTEM_UNITS.iter().map(|s| (*s).into()).collect();
    if inputs.generate_fixture_ssh {
        units.push("ssh.socket".into());
    }
    units.extend(snaps.iter().map(|(_, _, s)| s.unit.clone()));
    let mut args = vec![root_arg.clone(), "enable".into()];
    args.extend(units.clone());
    run_native(
        root,
        work,
        &tree,
        "native-enable-system-units",
        "/usr/bin/systemctl",
        &args,
        &mut commands,
    )?;
    run_native(
        root,
        work,
        &tree,
        "native-default-target",
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
        "native-enable-user-units",
        "/usr/bin/systemctl",
        &args,
        &mut commands,
    )?;
    fs::assert_root_namespace(&root_name, &tree)?;
    ensure(
        missing(&tree, "/var/lib/snapd/state.json")?,
        "initialization unexpectedly created Snap authentication/state",
    )?;
    let deferred: Vec<_> = aliases
        .entries
        .iter()
        .filter(|a| {
            !ALIASES_TO_RESTORE.iter().any(|(p, _)| *p == a.path) && !a.path.starts_with("/snap/")
        })
        .map(|a| json!({"path":a.path,"target":a.target}))
        .collect();
    Ok(
        json!({"schema":"droidloom.native-ubuntu-initialization.v1","root":root,"work":work,"inputs":inputs,
        "actions":actions,"native_commands":commands,"accounts":account_summary,"fresh_shadow_locked":true,
        "host_passwords_keys_homes_imported":false,"fresh_ssh":ssh_result,"system_units_enabled":units,
        "user_units_enabled":USER_UNITS,"snap_mounts_prepared":snaps.iter().map(|(_,_,s)|json!({"name":s.name,"revision":s.revision,"unit":s.unit})).collect::<Vec<_>>(),
        "snap_state_or_assertions_manufactured":false,"deferred_public_aliases":deferred,
        "native_initialization_complete":true,"guest_started":false,"guest_qualified":false,
        "unresolved_requirements":["Actual joined SELinux/AppArmor enforcing cold boot","Real GDM/Wayland, D-Bus, NetworkManager and SSH sessions","Fresh Snap registration/assertions and native profile generation","Selected-kernel device and Android/userdata/application qualification"]}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    fn accounts() -> (String, String) {
        ("root:x:0:0:REAL GECOS:/root:/bin/bash\nalex:x:1000:1000:PRIVATE GECOS:/home/alex:/bin/bash\ndroidloom-cell-u1000:x:976:976::/var/lib/droidloom:/usr/sbin/nologin\nreal-other:x:2000:2000:OTHER:/home/real-other:/bin/bash\n".into(),
         "root:x:0:alex\nalex:x:1000:\ndroidloom-cell-u1000:x:976:\naudio:x:29:real-other\nvideo:x:44:\nrender:x:992:\ninput:x:995:\nnetdev:x:110:\nreal-other:x:2000:\n".into())
    }
    #[test]
    fn account_generation_excludes_passwords_gecos_other_users_and_memberships() -> Result<()> {
        let (p, g) = accounts();
        let (lines, summary) = native_accounts(p.as_bytes(), g.as_bytes())?;
        let joined = lines.join("\n");
        assert!(
            !joined.contains("REAL GECOS")
                && !joined.contains("PRIVATE GECOS")
                && !joined.contains("real-other")
        );
        assert!(joined.contains("u alex 1000:1000") && joined.contains("m alex render"));
        assert_eq!(summary["host_memberships_imported"], false);
        Ok(())
    }
    #[test]
    fn account_generation_rejects_numeric_drift_and_sysusers_expansion() {
        let (p, g) = accounts();
        assert!(
            native_accounts(
                p.replace("alex:x:1000", "alex:x:1001").as_bytes(),
                g.as_bytes()
            )
            .is_err()
        );
        assert!(
            native_accounts(p.replace("/home/alex", "/home/%u").as_bytes(), g.as_bytes()).is_err()
        );
        assert!(
            native_accounts(
                p.replace("root:x:", "root:$6$secret:").as_bytes(),
                g.as_bytes()
            )
            .is_err()
        );
    }
    #[test]
    fn native_service_trailing_home_separator_preserves_identity() -> Result<()> {
        assert_eq!(
            account_path("/run/gnome-initial-setup/")?,
            "/run/gnome-initial-setup"
        );
        assert_eq!(account_path("/")?, "/");
        for bad in [
            "/run/../root/",
            "/run//service/",
            "/run/%u/",
            "/run/service name/",
        ] {
            assert!(account_path(bad).is_err());
        }
        Ok(())
    }
    #[test]
    fn gdm_fixture_autologin_requires_reviewed_empty_default_sections() -> Result<()> {
        let b = gdm_autologin(b"# default\n[daemon]\n[security]\n[debug]\n")?;
        assert!(std::str::from_utf8(&b)?.contains("AutomaticLogin=alex"));
        assert!(gdm_autologin(b"[daemon]\nAutomaticLogin=real\n[security]\n[debug]\n").is_err());
        Ok(())
    }
    #[test]
    fn snap_mount_rejects_writable_options_external_paths_and_exec_lines() -> Result<()> {
        let text = "[Unit]\nDescription=Mount unit for snapd, revision 28332\nAfter=snapd.mounts-pre.target\nBefore=snapd.mounts.target\n\n[Mount]\nWhat=/var/lib/snapd/snaps/snapd_28332.snap\nWhere=/snap/snapd/28332\nType=squashfs\nOptions=nodev,ro,x-gdu.hide,x-gvfs-hide\nLazyUnmount=yes\n\n[Install]\nWantedBy=snapd.mounts.target\nWantedBy=multi-user.target\n";
        let input = PublicConfigInput {
            input: FilePin {
                path: PathBuf::from("/etc/systemd/system/snap-snapd-28332.mount"),
                bytes: text.len() as u64,
                sha256: fs::digest(text.as_bytes()),
            },
            guest_path: "/etc/systemd/system/snap-snapd-28332.mount".into(),
            mode: 0o644,
        };
        assert_eq!(parse_snap(&input, text.as_bytes())?.name, "snapd");
        for changed in [
            text.replace("nodev,ro,", "nodev,rw,"),
            text.replace("What=/var/lib", "What=/home"),
            format!("{text}ExecStart=/bin/true\n"),
        ] {
            assert!(parse_snap(&input, changed.as_bytes()).is_err());
        }
        Ok(())
    }
    #[test]
    fn fixture_uuid_rejects_path_command_and_nil_values() {
        assert!(valid_uuid("f752fbea-fb44-4b0a-a7d2-7732637087dc"));
        for bad in [
            "../../root",
            "$(command)",
            "00000000-0000-0000-0000-000000000000",
        ] {
            assert!(!valid_uuid(bad));
        }
    }
}
