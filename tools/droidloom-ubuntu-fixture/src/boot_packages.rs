//! Original distribution package content, admitted only into a fresh private clone.
//! No maintainer scripts, dpkg state, live accounts or host configuration are changed.
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
    model::{Content, Manifest},
    paths,
};
use rustix::fs::{FileType, Mode, OFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Write,
    path::Path,
};

const MAX_TAR: u64 = 512 * 1024 * 1024;
const FUSE_PATH: &str = "/usr/bin/fusermount3";
const FUSE_SHA: &str = "2e69c3228b399df1f047d26c590ec820dbd8cd4108ee4d66ab903eac627594b2";

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PackageInput {
    pub package: String,
    pub version: String,
    pub architecture: String,
    pub archive: FilePin,
    pub provenance: FilePin,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetainedOriginal {
    pub path: String,
    pub package: String,
    pub archive_sha256: String,
    pub bytes: u64,
    pub sha256: String,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PublicPackages {
    pub schema: String,
    pub packages: Vec<PackageInput>,
    pub retained_originals: Vec<RetainedOriginal>,
    pub dependency_audit: FilePin,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Member {
    path: String,
    package: String,
    archive_sha256: String,
    mode: u32,
    uid: u32,
    gid: u32,
    bytes: u64,
    content: Content,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Action {
    Created,
    MatchedExisting,
    RetainedOriginal,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Installed {
    member: Member,
    action: Action,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    schema: String,
    input: FilePin,
    original_manifest_sha256: String,
    members: Vec<Installed>,
    packages: Vec<Value>,
    dependency_audit: FilePin,
    retained_originals: Vec<RetainedOriginal>,
    dpkg_database_updated: bool,
    maintainer_scripts_executed: bool,
    provenance_signature_reverified: bool,
    original_roots_written: bool,
    guest_qualified: bool,
    production_ready: bool,
}

struct Payload {
    member: Member,
    data: Vec<u8>,
}

fn relative_name(name: &str, directory: bool) -> Result<String> {
    let name = name.strip_prefix("./").unwrap_or(name);
    let name = if directory {
        name.strip_suffix('/').unwrap_or(name)
    } else {
        name
    };
    if directory && (name.is_empty() || name == ".") {
        return Ok(String::new());
    }
    ensure(
        !name.starts_with('/') && name.len() <= 4096,
        "absolute or excessive package member",
    )?;
    let absolute = format!("/{name}");
    paths::parts(&absolute)?;
    ensure(
        !name.bytes().any(|b| b.is_ascii_control()),
        "control byte in package path",
    )?;
    Ok(absolute)
}

fn beneath(path: &str, root: &str) -> bool {
    path == root || path.starts_with(&format!("{root}/"))
}

fn extra_config(package: &str, path: &str) -> bool {
    let allowed: &[&str] = match package {
        "amd64-microcode" => &["/etc/default/amd64-microcode"],
        "brltty" => &["/etc/brltty", "/etc/brltty.conf"],
        "fuse3" => &["/etc/fuse.conf"],
        "initramfs-tools-core" => &["/etc/initramfs-tools"],
        "intel-microcode" => &[
            "/etc/default/intel-microcode",
            "/etc/kernel/preinst.d/intel-microcode",
        ],
        "kmod" => &["/etc/depmod.d/ubuntu.conf"],
        "linux-base" => &["/etc/kernel/postinst.d/xx-update-initrd-links"],
        "kdump-tools" => &[
            "/etc/default/grub.d/kdump-tools.cfg",
            "/etc/init.d/kdump-tools",
            "/etc/kdump/sysctl.conf",
            "/etc/kernel/postinst.d/kdump-tools",
            "/etc/kernel/postrm.d/kdump-tools",
        ],
        "plymouth" => &[
            "/etc/init.d/plymouth",
            "/etc/init.d/plymouth-log",
            "/etc/logrotate.d/bootlog",
            "/etc/plymouth/plymouthd.conf",
        ],
        _ => &[],
    };
    allowed.iter().any(|p| beneath(path, p))
}

fn permitted(member: &Member) -> Result<()> {
    let p = &member.path;
    paths::parts(p)?;
    ensure(
        !paths::private(p) && !beneath(p, "/usr/lib/modules"),
        "private state or kernel content in public package supplement",
    )?;
    let directory = member.content == Content::Directory;
    let state = matches!(
        (member.package.as_str(), p.as_str()),
        ("brltty", "/var/lib/BrlAPI")
            | ("kdump-tools", "/var/lib/kdump")
            | ("plymouth", "/var/lib/plymouth")
    );
    let ancestors = [
        "/etc",
        "/etc/default",
        "/etc/default/grub.d",
        "/etc/init.d",
        "/etc/logrotate.d",
        "/etc/kernel",
        "/etc/kernel/preinst.d",
        "/etc/kernel/postinst.d",
        "/etc/kernel/postrm.d",
        "/etc/kdump",
        "/etc/plymouth",
        "/etc/depmod.d",
        "/var",
        "/var/lib",
    ];
    ensure(
        beneath(p, "/usr")
            || paths::public_config(p)
            || extra_config(&member.package, p)
            || directory
                && (ancestors.contains(&p.as_str())
                    || state
                    || member.package == "kexec-tools"
                        && p == "/etc/default/kexec.d"
                        && member.bytes == 0
                        && member.mode == 0o755),
        &format!(
            "package path is outside reviewed public content: {} {p}",
            member.package
        ),
    )?;
    ensure(
        member.uid == 0 && member.gid == 0,
        "package owner differs from reviewed root ownership",
    )?;
    if let Content::Symlink { target } = &member.content {
        ensure(member.mode == 0o777, "unexpected package symlink mode")?;
        paths::normalize_link(p, target)?;
    } else {
        let sticky_state = directory
            && member.package == "brltty"
            && p == "/var/lib/BrlAPI"
            && member.mode == 0o1777;
        let ntfs = matches!(&member.content, Content::Regular { .. })
            && member.package == "ntfs-3g"
            && p == "/usr/bin/ntfs-3g"
            && member.mode == 0o4755;
        ensure(
            sticky_state || member.mode & 0o022 == 0,
            "writable public package member",
        )?;
        ensure(
            member.mode & !0o777 == 0 || sticky_state || ntfs,
            "unreviewed package privilege mode",
        )?;
    }
    if state {
        ensure(
            directory && member.bytes == 0,
            "package private-state content refused",
        )?;
    }
    Ok(())
}

/// Parse the actual decompressed data member. Never delegate namespace extraction.
fn parse_tar(tar: &[u8], package: &str, archive_sha: &str) -> Result<Vec<Payload>> {
    ensure(
        tar.len() as u64 <= MAX_TAR && fs::valid_digest(archive_sha),
        "package tar outside bound",
    )?;
    let mut offset = 0usize;
    let mut seen = BTreeMap::<String, Member>::new();
    let mut out = Vec::new();
    loop {
        let h = tar
            .get(offset..offset + 512)
            .ok_or("truncated package tar header")?;
        offset += 512;
        if h.iter().all(|b| *b == 0) {
            ensure(
                tar.len() >= offset + 512
                    && tar.len() - offset <= 10752
                    && tar[offset..].iter().all(|b| *b == 0),
                "package tar termination differs",
            )?;
            break;
        }
        let sum: u64 = h
            .iter()
            .enumerate()
            .map(|(i, b)| {
                if (148..156).contains(&i) {
                    32
                } else {
                    u64::from(*b)
                }
            })
            .sum();
        ensure(
            crate::boot_host::octal(&h[148..156])? == sum,
            "package tar checksum differs",
        )?;
        let gnu = &h[257..265] == b"ustar  \0";
        let posix = &h[257..263] == b"ustar\0" && &h[263..265] == b"00";
        ensure(gnu || posix, "package tar is not reviewed GNU/POSIX ustar")?;
        if gnu {
            ensure(
                h[345..500].iter().all(|b| *b == 0),
                "GNU extension/sparse metadata refused",
            )?;
        }
        let kind = h[156];
        ensure(
            [0, b'0', b'1', b'2', b'5'].contains(&kind),
            "package extensions and special files refused",
        )?;
        let raw = crate::boot_host::text_field(&h[..100])?;
        let prefix = if gnu {
            ""
        } else {
            crate::boot_host::text_field(&h[345..500])?
        };
        let combined = if prefix.is_empty() {
            raw.to_owned()
        } else {
            format!("{prefix}/{raw}")
        };
        let path = relative_name(&combined, kind == b'5')?;
        let size = usize::try_from(crate::boot_host::octal(&h[124..136])?)?;
        let mode = u32::try_from(crate::boot_host::octal(&h[100..108])?)?;
        let uid = u32::try_from(crate::boot_host::octal(&h[108..116])?)?;
        let gid = u32::try_from(crate::boot_host::octal(&h[116..124])?)?;
        let link = crate::boot_host::text_field(&h[157..257])?;
        ensure(
            (kind == 0 || kind == b'0') || size == 0,
            "non-regular package member has payload",
        )?;
        ensure(
            matches!(kind, b'1' | b'2') || link.is_empty(),
            "unexpected package link field",
        )?;
        let end = offset.checked_add(size).ok_or("package size overflow")?;
        let body = tar.get(offset..end).ok_or("truncated package payload")?;
        offset = end;
        let padding = (512 - size % 512) % 512;
        ensure(
            tar.get(offset..offset + padding)
                .is_some_and(|v| v.iter().all(|b| *b == 0)),
            "package padding differs",
        )?;
        offset += padding;
        if path.is_empty() {
            ensure(
                kind == b'5' && mode == 0o755 && uid == 0 && gid == 0,
                "package archive root differs",
            )?;
            ensure(
                seen.insert(
                    String::new(),
                    Member {
                        path: String::new(),
                        package: package.into(),
                        archive_sha256: archive_sha.into(),
                        mode,
                        uid,
                        gid,
                        bytes: 0,
                        content: Content::Directory,
                    },
                )
                .is_none(),
                "duplicate package root",
            )?;
            continue;
        }
        let (content, bytes) = match kind {
            0 | b'0' => (
                Content::Regular {
                    sha256: fs::digest(body),
                },
                size as u64,
            ),
            b'5' => (Content::Directory, 0),
            b'2' => (
                Content::Symlink {
                    target: link.into(),
                },
                0,
            ),
            b'1' => {
                let target = relative_name(link, false)?;
                let original = seen
                    .get(&target)
                    .ok_or("package hardlink target is not an earlier package member")?;
                let Content::Regular { sha256 } = &original.content else {
                    return Err("package hardlink must name a primary regular member".into());
                };
                ensure(
                    original.mode == mode && original.uid == uid && original.gid == gid,
                    "package hardlink metadata differs",
                )?;
                (
                    Content::Hardlink {
                        target,
                        sha256: sha256.clone(),
                    },
                    original.bytes,
                )
            }
            _ => unreachable!(),
        };
        let member = Member {
            path: path.clone(),
            package: package.into(),
            archive_sha256: archive_sha.into(),
            mode,
            uid,
            gid,
            bytes,
            content,
        };
        permitted(&member)?;
        ensure(
            seen.len() < 32768 && seen.insert(path, member.clone()).is_none(),
            "duplicate/excessive package member",
        )?;
        out.push(Payload {
            member,
            data: body.to_vec(),
        });
    }
    ensure(!out.is_empty(), "empty public package tar")?;
    Ok(out)
}

fn provenance(input: &PackageInput) -> Result<()> {
    let v: Value =
        serde_json::from_slice(&boot_files::read_pin(&input.provenance, 8 * 1024 * 1024)?)?;
    ensure(
        v["host_install"] == false,
        "package intake does not bind a non-install acquisition",
    )?;
    let rows: Vec<&Value> = if let Some(a) = v.get("packages").and_then(Value::as_array) {
        a.iter().collect()
    } else if let Some(a) = v.get("files").and_then(Value::as_array) {
        a.iter().collect()
    } else {
        vec![&v]
    };
    let matched = rows
        .iter()
        .filter(|r| {
            r["package"]
                .as_str()
                .is_some_and(|s| s.split(':').next() == Some(input.package.as_str()))
                && r["version"] == input.version
                && r["bytes"] == input.archive.bytes
                && r["sha256"] == input.archive.sha256
                && r.get("retained_path").unwrap_or(&r["path"]).as_str()
                    == input.archive.path.to_str()
        })
        .count();
    ensure(
        matched == 1,
        "package bytes/version/path are not uniquely bound by their declared intake",
    )
}

fn same_member(a: &Member, b: &Member) -> bool {
    a.path == b.path
        && a.mode == b.mode
        && a.uid == b.uid
        && a.gid == b.gid
        && a.bytes == b.bytes
        && a.content == b.content
}

fn dependency_packages(audit: &Value) -> Result<BTreeSet<String>> {
    ensure(
        audit["schema"] == "p4-public-supplement-installed-dependency-closure-v1"
            && audit["unsatisfied"].as_array().is_some_and(Vec::is_empty)
            && audit["packages_installed_or_changed"] == false,
        "public dependency audit is incomplete",
    )?;
    let seeds = audit["seed_packages"]
        .as_array()
        .ok_or("dependency seeds absent")?;
    let added = audit["additional_packages"]
        .as_array()
        .ok_or("additional dependency packages absent")?;
    let mut expected = BTreeSet::new();
    for name in seeds
        .iter()
        .map(|v| v.as_str())
        .chain(added.iter().map(|v| v["package"].as_str()))
    {
        let name = name
            .ok_or("dependency package name absent")?
            .split(':')
            .next()
            .ok_or("invalid dependency name")?;
        ensure(
            !name.is_empty() && expected.insert(name.to_owned()),
            "duplicate dependency declaration",
        )?;
    }
    ensure(
        !expected.is_empty() && expected.len() <= 64,
        "dependency set outside bound",
    )?;
    Ok(expected)
}

fn readback(tree: &fs::Tree, member: &Member) -> Result<()> {
    let id = tree.identity(&member.path)?;
    ensure(
        id.mode & 0o7777 == member.mode
            && id.uid == member.uid
            && id.gid == member.gid
            && fs::content_type_matches(&id, &member.content),
        &format!("package member metadata differs: {}", member.path),
    )?;
    match &member.content {
        Content::Regular { sha256 } | Content::Hardlink { sha256, .. } => {
            let (actual, sha, attrs) = fs::read_regular(tree, &member.path)?;
            ensure(
                actual.size == member.bytes && sha == *sha256 && attrs.is_empty(),
                "package content or unexpected privilege xattr differs",
            )?;
            if let Content::Hardlink { target, .. } = &member.content {
                let other = tree.identity(target)?;
                ensure(
                    other.dev == actual.dev && other.ino == actual.ino,
                    "package hardlink group was split",
                )?;
            }
        }
        Content::Symlink { target } => ensure(
            tree.read_link(&member.path)?.1 == *target,
            "package symlink differs",
        )?,
        Content::Directory => {
            // The sole upstream sticky state leaf is empty and never used as a source parent.
            let (parent, name) = tree.parent(&member.path)?;
            let fd = std::fs::File::from(rustix::fs::openat(
                &parent,
                name.as_str(),
                OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )?);
            ensure(
                fs::xattrs(&fd)?.is_empty(),
                "package directory privilege attributes differ",
            )?;
            if member.mode & 0o022 != 0 {
                let mut directory = rustix::fs::Dir::read_from(&fd)?;
                for entry in &mut directory {
                    let entry = entry?;
                    let name = entry.file_name().to_str()?;
                    ensure(
                        name == "." || name == "..",
                        "fresh public state directory is not empty",
                    )?;
                }
            }
        }
    }
    Ok(())
}

fn retain(member: &mut Member, declaration: &RetainedOriginal, original: &Manifest) -> Result<()> {
    ensure(
        declaration.path == FUSE_PATH
            && declaration.package == "fuse3"
            && member.path == FUSE_PATH
            && member.package == "fuse3"
            && member.archive_sha256 == declaration.archive_sha256
            && member.mode == 0o755
            && member.uid == 0
            && member.gid == 0
            && member.bytes == 39376
            && member.content
                == (Content::Regular {
                    sha256: FUSE_SHA.into(),
                })
            && declaration.sha256 == FUSE_SHA
            && declaration.bytes == 39376
            && declaration.mode == 0o4755
            && declaration.uid == 0
            && declaration.gid == 0,
        "retained-original exception is outside the reviewed fusermount contract",
    )?;
    let e = original
        .entries
        .iter()
        .find(|e| e.path == FUSE_PATH)
        .ok_or("retained original missing from the verified base manifest")?;
    ensure(
        e.source.mode == 0o104755
            && e.source.uid == 0
            && e.source.gid == 0
            && e.source.nlink == 1
            && e.source.size == 39376
            && e.content == member.content
            && e.xattrs.is_empty(),
        "retained original metadata/content not bound to base manifest",
    )?;
    member.mode = declaration.mode;
    Ok(())
}

/// Resolve links entirely in the composed, pinned guest namespace. Every
/// existing component is read through NOFOLLOW descriptors and checked against
/// the original manifest; package components come from verified archive bytes.
fn resolve_public_link(
    tree: &fs::Tree,
    members: &BTreeMap<String, Payload>,
    original: &BTreeMap<&str, &crate::model::Entry>,
    path: &str,
    target: &str,
) -> Result<String> {
    let mut current = paths::normalize_link(path, target)?;
    let mut visited = BTreeSet::new();
    'resolve: for _ in 0..40 {
        ensure(
            current.len() <= 4096 && visited.insert(current.clone()),
            "package link resolution exceeds its bound or contains a cycle",
        )?;
        let parts = paths::parts(&current)?;
        let mut prefix = String::new();
        for (index, name) in parts.iter().enumerate() {
            prefix.push('/');
            prefix.push_str(name);
            let content = if let Some(payload) = members.get(&prefix) {
                payload.member.content.clone()
            } else {
                let entry = original.get(prefix.as_str()).ok_or_else(|| {
                    format!("package link component is absent from pinned inventory: {prefix}")
                })?;
                let id = tree.identity(&prefix)?;
                ensure(
                    id.uid == entry.source.uid
                        && id.gid == entry.source.gid
                        && id.uid == tree.owner
                        && id.mode & 0o177777 == entry.source.mode & 0o177777
                        && fs::content_type_matches(&id, &entry.content),
                    &format!("original link component metadata changed: {prefix}"),
                )?;
                match &entry.content {
                    Content::Directory => ensure(
                        id.mode & 0o022 == 0 && fs::xattrs(&tree.dir(&prefix)?)? == entry.xattrs,
                        "original link ancestor permissions changed",
                    )?,
                    Content::Symlink { target } => {
                        let (actual, link) = tree.read_link(&prefix)?;
                        ensure(
                            actual == id && link == *target,
                            "original link component differs from pinned inventory",
                        )?;
                    }
                    Content::Regular { sha256 } | Content::Hardlink { sha256, .. } => {
                        let (actual, hash, attrs) = fs::read_regular(tree, &prefix)?;
                        ensure(
                            actual == id
                                && actual.size == entry.source.size
                                && hash == *sha256
                                && attrs == entry.xattrs,
                            "original link target bytes or privilege metadata changed",
                        )?;
                    }
                }
                entry.content.clone()
            };
            if let Content::Symlink { target } = content {
                let base = paths::normalize_link(&prefix, &target)?;
                let remaining = &parts[index + 1..];
                let next = if remaining.is_empty() {
                    base
                } else {
                    format!("{base}/{}", remaining.join("/"))
                };
                // Validate again after appending the suffix: an admitted alias
                // cannot turn a public name into a private runtime descendant.
                current = paths::normalize_link(path, &next)?;
                continue 'resolve;
            }
            ensure(
                index + 1 == parts.len() || content == Content::Directory,
                "package link target crosses a non-directory component",
            )?;
        }
        return Ok(current);
    }
    Err("package link resolution exceeds forty expansions".into())
}

fn preflight(
    tree: &fs::Tree,
    members: &mut BTreeMap<String, Payload>,
    retained: &[RetainedOriginal],
    original: &Manifest,
) -> Result<Vec<Installed>> {
    let mut used = BTreeSet::new();
    let mut installed = Vec::new();
    let original_entries: BTreeMap<_, _> = original
        .entries
        .iter()
        .map(|e| (e.path.as_str(), e))
        .collect();
    ensure(
        original_entries.len() == original.entries.len(),
        "duplicate original inventory path",
    )?;
    for (path, payload) in members.iter_mut() {
        let found = match tree.identity(path) {
            Ok(v) => Some(v),
            Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
                None
            }
            Err(e) => return Err(e),
        };
        let action = if let Some(id) = found {
            if let Some(r) = retained.iter().find(|r| &r.path == path) {
                retain(&mut payload.member, r, original)?;
                ensure(
                    id.nlink == 1 && used.insert(path.clone()),
                    "retained original hardlink or duplicate",
                )?;
                readback(tree, &payload.member)?;
                Action::RetainedOriginal
            } else {
                readback(tree, &payload.member)?;
                Action::MatchedExisting
            }
        } else {
            ensure(
                !retained.iter().any(|r| &r.path == path),
                "retained original is absent",
            )?;
            Action::Created
        };
        installed.push(Installed {
            member: payload.member.clone(),
            action,
        });
    }
    ensure(
        used.len() == retained.len(),
        "unused or repeated retained-original declaration",
    )?;
    for (path, payload) in members.iter() {
        let mut parent = paths::parent(path);
        while parent != "/" {
            if let Some(p) = members.get(parent) {
                ensure(
                    p.member.content == Content::Directory && p.member.mode & 0o022 == 0,
                    "package destination traverses alias/writable member",
                )?;
            } else {
                let id = tree.identity(parent)?;
                ensure(
                    FileType::from_raw_mode(id.mode) == FileType::Directory
                        && id.uid == tree.owner
                        && id.mode & 0o022 == 0,
                    "package ancestor absent or unsafe",
                )?;
            }
            parent = paths::parent(parent);
        }
        if let Content::Symlink { target } = &payload.member.content {
            resolve_public_link(tree, members, &original_entries, path, target)?;
        }
        if let Content::Hardlink { target, .. } = &payload.member.content {
            let primary = installed
                .iter()
                .find(|e| e.member.path == *target)
                .ok_or("hardlink primary absent")?;
            let alias = installed
                .iter()
                .find(|e| e.member.path == *path)
                .ok_or("hardlink alias absent")?;
            ensure(
                (primary.action == Action::Created) == (alias.action == Action::Created),
                "partial existing hardlink group refused",
            )?;
        }
    }
    Ok(installed)
}

fn materialize(
    tree: &fs::Tree,
    members: &BTreeMap<String, Payload>,
    installed: &[Installed],
) -> Result<()> {
    let mut dirs: Vec<_> = installed
        .iter()
        .filter(|e| e.action == Action::Created && e.member.content == Content::Directory)
        .collect();
    dirs.sort_by_key(|e| (e.member.path.matches('/').count(), e.member.path.as_str()));
    for e in &dirs {
        tree.mkdir(&e.member.path)?;
    }
    for e in installed.iter().filter(|e| e.action == Action::Created) {
        match &e.member.content {
            Content::Regular { sha256 } => {
                let mut f = tree.create_file(&e.member.path)?;
                let data = &members
                    .get(&e.member.path)
                    .ok_or("package payload absent")?
                    .data;
                ensure(
                    fs::digest(data) == *sha256 && data.len() as u64 == e.member.bytes,
                    "in-memory package content changed",
                )?;
                f.write_all(data)?;
                let mut id = boot_files::clean_metadata(0o100000 | e.member.mode);
                id.uid = e.member.uid;
                id.gid = e.member.gid;
                fs::set_metadata(&f, &id, &BTreeMap::new())?;
            }
            Content::Symlink { target } => {
                let mut id = boot_files::clean_metadata(0o120777);
                id.uid = e.member.uid;
                id.gid = e.member.gid;
                tree.symlink(&e.member.path, target, &id)?;
            }
            _ => (),
        }
    }
    for e in installed.iter().filter(|e| e.action == Action::Created) {
        if let Content::Hardlink { target, .. } = &e.member.content {
            tree.hardlink(&e.member.path, target)?;
        }
    }
    for e in dirs.iter().rev() {
        let mut id = boot_files::clean_metadata(0o40000 | e.member.mode);
        id.uid = e.member.uid;
        id.gid = e.member.gid;
        fs::set_metadata(&tree.dir(&e.member.path)?, &id, &BTreeMap::new())?;
    }
    rustix::fs::fsync(&tree.root)?;
    verify_members(tree, installed)
}

fn verify_members(tree: &fs::Tree, members: &[Installed]) -> Result<()> {
    for e in members {
        readback(tree, &e.member)?;
    }
    let mut groups = BTreeMap::<&str, u64>::new();
    for e in members.iter().filter(|e| e.action == Action::Created) {
        if let Content::Hardlink { target, .. } = &e.member.content {
            *groups.entry(target).or_insert(1) += 1;
        }
    }
    for (path, count) in groups {
        ensure(
            tree.identity(path)?.nlink == count,
            "new package hardlink group has extra links",
        )?;
    }
    Ok(())
}

pub fn apply(
    root: &Path,
    work: &Path,
    input: &FilePin,
    original: &Manifest,
    original_sha: &str,
) -> Result<FilePin> {
    ensure(
        work.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
            && root == work.join("root"),
        "public package supplement needs a fresh qualification clone",
    )?;
    let private = fs::Tree::open(&fs::absolute_string(work)?, 0)?;
    ensure(
        fs::stat(&private.root)?.mode & 0o7777 == 0o700,
        "public package work is not private",
    )?;
    let plan: PublicPackages =
        serde_json::from_slice(&boot_files::read_pin(input, 8 * 1024 * 1024)?)?;
    ensure(
        plan.schema == "droidloom.ubuntu-public-packages.v1"
            && !plan.packages.is_empty()
            && plan.packages.len() <= 64,
        "unsupported public package plan",
    )?;
    ensure(
        fs::valid_digest(original_sha),
        "invalid original manifest identity",
    )?;
    let dependency: Value = serde_json::from_slice(&boot_files::read_pin(
        &plan.dependency_audit,
        8 * 1024 * 1024,
    )?)?;
    let required_packages = dependency_packages(&dependency)?;
    for required in dependency["additional_packages"]
        .as_array()
        .ok_or("dependency packages absent")?
    {
        let name = required["package"]
            .as_str()
            .ok_or("dependency package name absent")?
            .split(':')
            .next()
            .ok_or("invalid dependency package")?;
        ensure(
            plan.packages.iter().any(|p| {
                p.package == name
                    && required["version"] == p.version
                    && required["architecture"] == p.architecture
            }),
            "additional dependency package version/architecture is absent",
        )?;
    }
    let layer = work.join("public-packages");
    boot_files::private_dir(&layer)?;
    let mut seen = BTreeSet::new();
    let mut members = BTreeMap::<String, Payload>::new();
    let mut reports = Vec::new();
    for (index, package) in plan.packages.iter().enumerate() {
        ensure(
            !package.package.is_empty()
                && package
                    .package
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"+.-".contains(&b))
                && !package.version.is_empty()
                && !package
                    .version
                    .bytes()
                    .any(|b| b.is_ascii_whitespace() || b.is_ascii_control())
                && ["amd64", "all"].contains(&package.architecture.as_str())
                && seen.insert(package.package.clone()),
            "invalid or duplicate native package identity",
        )?;
        ensure(
            package.archive.bytes <= 128 * 1024 * 1024,
            "public package exceeds bound",
        )?;
        provenance(package)?;
        let area = layer.join(format!("package-{index:02}"));
        boot_files::private_dir(&area)?;
        let archive = area.join("original.deb");
        boot_files::copy_pin(&package.archive, &archive, 0o400)?;
        let control = boot_files::run_logged(
            &area,
            "metadata",
            "/usr/bin/dpkg-deb",
            &[
                "--field".into(),
                archive.to_string_lossy().into(),
                "Package".into(),
                "Version".into(),
                "Architecture".into(),
            ],
            30,
        )?;
        let actual = String::from_utf8(boot_files::read_pin(&control.log, 4096)?)?;
        ensure(
            actual
                == format!(
                    "Package: {}\nVersion: {}\nArchitecture: {}\n",
                    package.package, package.version, package.architecture
                ),
            "actual original Debian package metadata differs",
        )?;
        let tar = crate::boot_runtime::redirected(
            &area,
            "data",
            "/usr/bin/dpkg-deb",
            &["--fsys-tarfile".into(), archive.to_string_lossy().into()],
            None,
            None,
            &area.join("data.tar"),
            MAX_TAR,
            60,
        )?;
        let parsed = parse_tar(
            &boot_files::read_pin(&tar, MAX_TAR)?,
            &package.package,
            &package.archive.sha256,
        )?;
        let count = parsed.len();
        for payload in parsed {
            if let Some(old) = members.get(&payload.member.path) {
                ensure(
                    same_member(&old.member, &payload.member),
                    "cross-package member content or metadata conflicts",
                )?;
            } else {
                members.insert(payload.member.path.clone(), payload);
            }
        }
        ensure(
            members.len() <= 65536
                && members.values().map(|p| p.data.len() as u64).sum::<u64>() <= 1024 * 1024 * 1024,
            "public supplement total exceeds reviewed bound",
        )?;
        reports.push(
            json!({"input":package,"actual_metadata":control.log,"data_tar":tar,"members":count}),
        );
    }
    ensure(
        seen == required_packages,
        "public package input set differs from its complete declared dependency closure",
    )?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let installed = preflight(&tree, &mut members, &plan.retained_originals, original)?;
    materialize(&tree, &members, &installed)?;
    fs::assert_root_namespace(&fs::absolute_string(root)?, &tree)?;
    let result = Receipt {
        schema: "droidloom.ubuntu-public-packages-verified.v1".into(),
        input: input.clone(),
        original_manifest_sha256: original_sha.into(),
        members: installed,
        packages: reports,
        dependency_audit: plan.dependency_audit,
        retained_originals: plan.retained_originals,
        dpkg_database_updated: false,
        maintainer_scripts_executed: false,
        provenance_signature_reverified: false,
        original_roots_written: false,
        guest_qualified: false,
        production_ready: false,
    };
    let path = layer.join("SUPPLEMENT-VERIFIED.json");
    fs::write_json(&fs::absolute_string(&path)?, &result, 0)?;
    boot_files::pin_file(&path)
}

pub fn verify(root: &Path, pin: &FilePin) -> Result<Value> {
    let receipt: Receipt = serde_json::from_slice(&boot_files::read_pin(pin, 32 * 1024 * 1024)?)?;
    ensure(
        receipt.schema == "droidloom.ubuntu-public-packages-verified.v1"
            && !receipt.dpkg_database_updated
            && !receipt.maintainer_scripts_executed
            && !receipt.original_roots_written
            && !receipt.guest_qualified
            && !receipt.production_ready,
        "invalid public supplement receipt",
    )?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    verify_members(&tree, &receipt.members)?;
    fs::assert_root_namespace(&fs::absolute_string(root)?, &tree)?;
    Ok(
        json!({"receipt":pin,"packages":receipt.packages.len(),"members":receipt.members.len(),
        "created":receipt.members.iter().filter(|e|e.action==Action::Created).count(),
        "retained_originals":receipt.retained_originals,"full_content_readback":true,"guest_qualified":false,"production_ready":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    fn record(path: &str, kind: u8, body: &[u8], mode: u32, link: &str) -> Vec<u8> {
        assert!(path.len() <= 100 && link.len() <= 100);
        let mut h = [0u8; 512];
        h[..path.len()].copy_from_slice(path.as_bytes());
        h[100..108].copy_from_slice(format!("{mode:07o}\0").as_bytes());
        h[108..116].copy_from_slice(b"0000000\0");
        h[116..124].copy_from_slice(b"0000000\0");
        h[124..136].copy_from_slice(format!("{:011o}\0", body.len()).as_bytes());
        h[136..148].copy_from_slice(b"00000000000\0");
        h[148..156].fill(b' ');
        h[156] = kind;
        h[157..157 + link.len()].copy_from_slice(link.as_bytes());
        h[257..265].copy_from_slice(b"ustar  \0");
        let sum: u64 = h.iter().map(|v| u64::from(*v)).sum();
        h[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
        let mut out = h.to_vec();
        out.extend_from_slice(body);
        out.resize(out.len().div_ceil(512) * 512, 0);
        out
    }
    fn tar(rows: Vec<Vec<u8>>) -> Vec<u8> {
        let mut out = rows.concat();
        out.resize(out.len() + 1024, 0);
        out
    }
    fn base_manifest() -> Manifest {
        Manifest {
            schema: crate::model::MANIFEST_SCHEMA.into(),
            selection_sha256: "a".repeat(64),
            audit_sha256: "b".repeat(64),
            source_root: "/".into(),
            source_root_identity: boot_files::clean_metadata(0o40755),
            target_kernel_release: "6.18.0-test".into(),
            kernel: None,
            entries: Vec::new(),
            unresolved_requirements: vec!["real runtime remains required".into()],
            unresolved_public_links: Vec::new(),
            guest_qualified: false,
        }
    }
    fn owned(rows: Vec<Payload>) -> BTreeMap<String, Payload> {
        rows.into_iter()
            .map(|mut p| {
                p.member.uid = rustix::process::geteuid().as_raw();
                p.member.gid = rustix::process::getegid().as_raw();
                (p.member.path.clone(), p)
            })
            .collect()
    }
    fn fixture() -> Result<(tempfile::TempDir, fs::Tree)> {
        let temp = tempfile::tempdir()?;
        std::fs::set_permissions(temp.path(), std::fs::Permissions::from_mode(0o700))?;
        let tree = fs::Tree::create(
            &fs::absolute_string(&temp.path().join("root"))?,
            rustix::process::geteuid().as_raw(),
        )?;
        Ok((temp, tree))
    }

    #[test]
    fn original_absolute_directory_alias_is_resolved_inside_pinned_guest_inventory() -> Result<()> {
        let (temp, tree) = fixture()?;
        let root = temp.path().join("root");
        for dir in [
            "usr/share/X11",
            "usr/share/xkeyboard-config-2/rules",
            "usr/share/doc/keyboard-configuration",
        ] {
            std::fs::create_dir_all(root.join(dir))?;
        }
        std::fs::write(
            root.join("usr/share/xkeyboard-config-2/rules/base.lst"),
            b"pinned xkb rules",
        )?;
        std::os::unix::fs::symlink(
            "/usr/share/xkeyboard-config-2",
            root.join("usr/share/X11/xkb"),
        )?;
        std::os::unix::fs::symlink(
            "base.lst",
            root.join("usr/share/xkeyboard-config-2/rules/xorg.lst"),
        )?;
        let mut original = base_manifest();
        for path in [
            "/usr",
            "/usr/share",
            "/usr/share/X11",
            "/usr/share/xkeyboard-config-2",
            "/usr/share/xkeyboard-config-2/rules",
        ] {
            original.entries.push(crate::model::Entry {
                path: path.into(),
                component: crate::model::Component::Native,
                origin: "pinned original fixture".into(),
                source: tree.identity(path)?,
                content: Content::Directory,
                xattrs: BTreeMap::new(),
            });
        }
        for (path, target) in [
            ("/usr/share/X11/xkb", "/usr/share/xkeyboard-config-2"),
            ("/usr/share/xkeyboard-config-2/rules/xorg.lst", "base.lst"),
        ] {
            original.entries.push(crate::model::Entry {
                path: path.into(),
                component: crate::model::Component::Native,
                origin: "pinned original fixture".into(),
                source: tree.identity(path)?,
                content: Content::Symlink {
                    target: target.into(),
                },
                xattrs: BTreeMap::new(),
            });
        }
        let path = "/usr/share/xkeyboard-config-2/rules/base.lst";
        original.entries.push(crate::model::Entry {
            path: path.into(),
            component: crate::model::Component::Native,
            origin: "pinned original fixture".into(),
            source: tree.identity(path)?,
            content: Content::Regular {
                sha256: fs::digest(b"pinned xkb rules"),
            },
            xattrs: BTreeMap::new(),
        });
        let mut members = owned(parse_tar(
            &tar(vec![record(
                "./usr/share/doc/keyboard-configuration/xorg.lst",
                b'2',
                b"",
                0o777,
                "../../X11/xkb/rules/xorg.lst",
            )]),
            "keyboard-configuration",
            &"c".repeat(64),
        )?);
        let installed = preflight(&tree, &mut members, &[], &original)?;
        assert_eq!(installed.len(), 1);
        let mut missing = original.clone();
        missing.entries.retain(|e| e.path != "/usr/share/X11/xkb");
        assert!(preflight(&tree, &mut members, &[], &missing).is_err());
        std::fs::write(
            root.join("usr/share/xkeyboard-config-2/rules/base.lst"),
            b"changed rules",
        )?;
        assert!(preflight(&tree, &mut members, &[], &original).is_err());
        std::fs::write(
            root.join("usr/share/xkeyboard-config-2/rules/base.lst"),
            b"pinned xkb rules",
        )?;
        std::fs::remove_file(root.join("usr/share/X11/xkb"))?;
        std::os::unix::fs::symlink("/etc/shadow", root.join("usr/share/X11/xkb"))?;
        assert!(preflight(&tree, &mut members, &[], &original).is_err());
        assert!(
            !root
                .join("usr/share/doc/keyboard-configuration/xorg.lst")
                .exists()
        );
        Ok(())
    }

    #[test]
    fn composed_package_alias_cycles_fail_before_materialization() -> Result<()> {
        let (temp, tree) = fixture()?;
        let mut members = owned(parse_tar(
            &tar(vec![
                record("./usr/", b'5', b"", 0o755, ""),
                record("./usr/share/", b'5', b"", 0o755, ""),
                record("./usr/share/loop-a", b'2', b"", 0o777, "/usr/share/loop-b"),
                record("./usr/share/loop-b", b'2', b"", 0o777, "/usr/share/loop-a"),
            ]),
            "original",
            &"c".repeat(64),
        )?);
        assert!(preflight(&tree, &mut members, &[], &base_manifest()).is_err());
        assert!(!temp.path().join("root/usr").exists());
        Ok(())
    }

    #[test]
    fn gnu_original_archive_and_real_hardlink_topology_roundtrip() -> Result<()> {
        let bytes = tar(vec![
            record("./", b'5', b"", 0o755, ""),
            record("./usr/", b'5', b"", 0o755, ""),
            record("./usr/lib/", b'5', b"", 0o755, ""),
            record("./usr/lib/klibc/", b'5', b"", 0o755, ""),
            record(
                "./usr/lib/klibc/gunzip",
                b'0',
                b"actual synthetic ELF bytes",
                0o755,
                "",
            ),
            record(
                "./usr/lib/klibc/gzip",
                b'1',
                b"",
                0o755,
                "./usr/lib/klibc/gunzip",
            ),
            record("./usr/lib/klibc/alias", b'2', b"", 0o777, "gunzip"),
        ]);
        let mut members = owned(parse_tar(&bytes, "klibc-utils", &"c".repeat(64))?);
        let (temp, tree) = fixture()?;
        let installed = preflight(&tree, &mut members, &[], &base_manifest())?;
        materialize(&tree, &members, &installed)?;
        let a = std::fs::metadata(temp.path().join("root/usr/lib/klibc/gunzip"))?;
        let b = std::fs::metadata(temp.path().join("root/usr/lib/klibc/gzip"))?;
        assert_eq!((a.dev(), a.ino(), a.nlink()), (b.dev(), b.ino(), 2));
        std::fs::hard_link(
            temp.path().join("root/usr/lib/klibc/gunzip"),
            temp.path().join("extra-link"),
        )?;
        assert!(verify_members(&tree, &installed).is_err());
        Ok(())
    }

    #[test]
    fn public_package_parser_rejects_escape_private_modules_extensions_and_devices() {
        for path in [
            "../escape",
            "/usr/bin/bad",
            "./usr/../escape",
            "./etc/shadow",
            "./home/alex/file",
            "./usr/lib/modules/7.0/foreign.ko",
        ] {
            assert!(
                parse_tar(
                    &tar(vec![record(path, b'0', b"x", 0o644, "")]),
                    "original",
                    &"c".repeat(64)
                )
                .is_err()
            );
        }
        for kind in [b'x', b'g', b'L', b'K', b'3', b'4', b'6', b'S'] {
            assert!(
                parse_tar(
                    &tar(vec![record("./usr/bin/bad", kind, b"", 0o644, "")]),
                    "original",
                    &"c".repeat(64)
                )
                .is_err()
            );
        }
        for target in ["../../../../outside", "/etc/shadow", "/home/alex/private"] {
            assert!(
                parse_tar(
                    &tar(vec![record("./usr/bin/link", b'2', b"", 0o777, target)]),
                    "original",
                    &"c".repeat(64)
                )
                .is_err()
            );
        }
    }

    #[test]
    fn package_parser_rejects_duplicate_bad_digest_padding_and_truncated_end() {
        let row = record("./usr/bin/tool", b'0', b"x", 0o755, "");
        let good = tar(vec![row.clone()]);
        assert!(parse_tar(&tar(vec![row.clone(), row]), "original", &"c".repeat(64)).is_err());
        let mut bad = good.clone();
        bad[0] ^= 1;
        assert!(parse_tar(&bad, "original", &"c".repeat(64)).is_err());
        bad = good.clone();
        bad[513] = 1;
        assert!(parse_tar(&bad, "original", &"c".repeat(64)).is_err());
        assert!(parse_tar(&good[..good.len() - 512], "original", &"c".repeat(64)).is_err());
        assert!(parse_tar(&good, "original", "not a digest").is_err());
    }

    #[test]
    fn hardlinks_cannot_name_other_packages_aliases_or_later_members() {
        let symlink = record("./usr/lib/alias", b'2', b"", 0o777, "target");
        for rows in [
            vec![record(
                "./usr/lib/linked",
                b'1',
                b"",
                0o644,
                "./usr/lib/outside",
            )],
            vec![
                symlink,
                record("./usr/lib/linked", b'1', b"", 0o777, "./usr/lib/alias"),
            ],
            vec![
                record("./usr/lib/original", b'0', b"x", 0o644, ""),
                record("./usr/lib/linked", b'1', b"", 0o755, "./usr/lib/original"),
            ],
        ] {
            assert!(parse_tar(&tar(rows), "original", &"c".repeat(64)).is_err());
        }
    }

    #[test]
    fn conflicting_existing_content_fails_before_any_public_root_write() -> Result<()> {
        let (temp, tree) = fixture()?;
        std::fs::create_dir(temp.path().join("root/usr"))?;
        std::fs::create_dir(temp.path().join("root/usr/bin"))?;
        std::fs::write(temp.path().join("root/usr/bin/keep"), b"unchanged original")?;
        let before = std::fs::read(temp.path().join("root/usr/bin/keep"))?;
        let mut members = owned(parse_tar(
            &tar(vec![
                record("./usr/bin/keep", b'0', b"different", 0o644, ""),
                record("./usr/bin/new", b'0', b"new", 0o644, ""),
            ]),
            "original",
            &"c".repeat(64),
        )?);
        assert!(preflight(&tree, &mut members, &[], &base_manifest()).is_err());
        assert_eq!(
            before,
            std::fs::read(temp.path().join("root/usr/bin/keep"))?
        );
        assert!(!temp.path().join("root/usr/bin/new").exists());
        Ok(())
    }

    #[test]
    fn destination_parent_alias_and_writable_directory_are_refused() -> Result<()> {
        let (temp, tree) = fixture()?;
        std::fs::create_dir(temp.path().join("root/usr"))?;
        std::fs::create_dir(temp.path().join("outside"))?;
        std::os::unix::fs::symlink(
            temp.path().join("outside"),
            temp.path().join("root/usr/bin"),
        )?;
        let mut members = owned(parse_tar(
            &tar(vec![record("./usr/bin/tool", b'0', b"x", 0o755, "")]),
            "original",
            &"c".repeat(64),
        )?);
        assert!(preflight(&tree, &mut members, &[], &base_manifest()).is_err());
        assert!(!temp.path().join("outside/tool").exists());
        assert!(
            parse_tar(
                &tar(vec![record("./usr/writable/", b'5', b"", 0o777, "")]),
                "original",
                &"c".repeat(64)
            )
            .is_err()
        );
        Ok(())
    }

    #[test]
    fn retained_fusermount_mode_requires_all_original_and_package_bindings() -> Result<()> {
        let mut member = Member {
            path: FUSE_PATH.into(),
            package: "fuse3".into(),
            archive_sha256: "a".repeat(64),
            mode: 0o755,
            uid: 0,
            gid: 0,
            bytes: 39376,
            content: Content::Regular {
                sha256: FUSE_SHA.into(),
            },
        };
        let r = RetainedOriginal {
            path: FUSE_PATH.into(),
            package: "fuse3".into(),
            archive_sha256: "a".repeat(64),
            bytes: 39376,
            sha256: FUSE_SHA.into(),
            mode: 0o4755,
            uid: 0,
            gid: 0,
        };
        let mut manifest = base_manifest();
        let mut source = boot_files::clean_metadata(0o104755);
        source.size = 39376;
        manifest.entries.push(crate::model::Entry {
            path: FUSE_PATH.into(),
            component: crate::model::Component::Native,
            origin: "fuse3 original installation".into(),
            source,
            content: member.content.clone(),
            xattrs: BTreeMap::new(),
        });
        retain(&mut member, &r, &manifest)?;
        assert_eq!(member.mode, 0o4755);
        member.mode = 0o755;
        let mut wrong = r.clone();
        wrong.mode = 0o4777;
        assert!(retain(&mut member, &wrong, &manifest).is_err());
        wrong = r.clone();
        wrong.sha256 = "f".repeat(64);
        assert!(retain(&mut member, &wrong, &manifest).is_err());
        wrong = r.clone();
        wrong.archive_sha256 = "b".repeat(64);
        assert!(retain(&mut member, &wrong, &manifest).is_err());
        manifest.entries[0].source.nlink = 2;
        assert!(retain(&mut member, &r, &manifest).is_err());
        Ok(())
    }

    #[test]
    fn privileges_and_empty_state_directory_are_narrowly_scoped() {
        assert!(
            parse_tar(
                &tar(vec![record("./usr/bin/ntfs-3g", b'0', b"x", 0o4755, "")]),
                "ntfs-3g",
                &"c".repeat(64)
            )
            .is_ok()
        );
        assert!(
            parse_tar(
                &tar(vec![record("./usr/bin/other", b'0', b"x", 0o4755, "")]),
                "ntfs-3g",
                &"c".repeat(64)
            )
            .is_err()
        );
        assert!(
            parse_tar(
                &tar(vec![record("./var/lib/BrlAPI/", b'5', b"", 0o1777, "")]),
                "brltty",
                &"c".repeat(64)
            )
            .is_ok()
        );
        assert!(
            parse_tar(
                &tar(vec![record(
                    "./var/lib/BrlAPI/token",
                    b'0',
                    b"x",
                    0o600,
                    ""
                )]),
                "brltty",
                &"c".repeat(64)
            )
            .is_err()
        );
    }

    #[test]
    fn kexec_original_empty_config_directory_does_not_authorize_files() {
        assert!(
            parse_tar(
                &tar(vec![record("./etc/default/kexec.d/", b'5', b"", 0o755, "")]),
                "kexec-tools",
                &"c".repeat(64)
            )
            .is_ok()
        );
        assert!(
            parse_tar(
                &tar(vec![record("./etc/default/kexec.d/", b'5', b"", 0o700, "")]),
                "kexec-tools",
                &"c".repeat(64)
            )
            .is_err()
        );
        assert!(
            parse_tar(
                &tar(vec![record("./etc/default/kexec.d/", b'5', b"", 0o755, "")]),
                "other",
                &"c".repeat(64)
            )
            .is_err()
        );
        assert!(
            parse_tar(
                &tar(vec![record(
                    "./etc/default/kexec.d/secret",
                    b'0',
                    b"not admitted",
                    0o600,
                    ""
                )]),
                "kexec-tools",
                &"c".repeat(64)
            )
            .is_err()
        );
    }
    #[test]
    fn dependency_closure_is_exact_and_must_have_no_unresolved_groups() -> Result<()> {
        let mut audit = json!({"schema":"p4-public-supplement-installed-dependency-closure-v1","unsatisfied":[],"packages_installed_or_changed":false,
            "seed_packages":["plymouth"],"additional_packages":[{"package":"libplymouth5:amd64"}]});
        assert_eq!(
            dependency_packages(&audit)?,
            BTreeSet::from(["plymouth".into(), "libplymouth5".into()])
        );
        audit["unsatisfied"] = json!(["missing"]);
        assert!(dependency_packages(&audit).is_err());
        audit["unsatisfied"] = json!([]);
        audit["seed_packages"] = json!(["libplymouth5"]);
        assert!(dependency_packages(&audit).is_err());
        Ok(())
    }
}
