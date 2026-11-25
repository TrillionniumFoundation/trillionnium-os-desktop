//! Read-only admission of the normal console package and complete inode closure.
//! This runs on the separately materialized, still unmodified complete root.
//! It neither executes helpers nor installs/replaces distribution files.
use crate::complete_native::CompleteManifest;
use crate::complete_snapshot::Snapshot;
use crate::model::Identity;
use crate::{Result, ensure, fs};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;

const SOURCE: &str = include_str!(
    "../../../android/framework/droidloom-readiness/board-policy/native-console-setup.json"
);

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Closure {
    schema: String,
    console_setup_version: String,
    kbd_version: String,
    selected_keymap: Vec<String>,
    packages: BTreeMap<String, String>,
    aliases: Vec<Value>,
    files: Vec<Inode>,
    directory: Directory,
    unchanged_inputs: Vec<Fixed>,
    command_links: Vec<Link>,
    runtime_qualified: bool,
    ioctls: BTreeMap<String, u32>,
    source_documents: Vec<Value>,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Inode {
    paths: Vec<String>,
    bytes: u64,
    sha256: String,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    category: String,
    source_type: String,
    target_type: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Directory {
    path: String,
    mode: u32,
    uid: u32,
    gid: u32,
    source_type: String,
    target_type: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixed {
    path: String,
    bytes: u64,
    sha256: String,
    mode: u32,
    uid: u32,
    gid: u32,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Link {
    path: String,
    target: String,
    uid: u32,
    gid: u32,
}

fn valid_contract(c: &Closure) -> Result<()> {
    ensure(
        c.schema == "droidloom.native-console-source-closure.v1"
            && c.console_setup_version == "1.237ubuntu3.1"
            && c.kbd_version == "2.7.1-2ubuntu2"
            && c.selected_keymap == ["us", "pc105", "UTF-8", "del"]
            && !c.runtime_qualified
            && !c.aliases.is_empty()
            && !c.command_links.is_empty()
            && !c.ioctls.is_empty()
            && !c.source_documents.is_empty(),
        "normal console source contract is not the compiled selection",
    )?;
    for row in &c.files {
        ensure(
            row.uid == 0
                && row.gid == 0
                && row.mode & 0o022 == 0
                && row.source_type.starts_with("p4_linux_")
                && row.target_type.starts_with("p4_linux_console_")
                && matches!(
                    row.category.as_str(),
                    "entry"
                        | "vtrgb"
                        | "helper"
                        | "library"
                        | "config"
                        | "cache"
                        | "cache_exec"
                        | "public"
                ),
            "normal console inode has an unexpected authority or category",
        )?;
    }
    ensure(
        c.directory.path == "/etc/console-setup"
            && c.directory.uid == 0
            && c.directory.gid == 0
            && c.directory.mode == 0o755
            && c.directory.source_type == "p4_linux_rootdir_t"
            && c.directory.target_type == "p4_linux_console_cache_dir_t",
        "console cache directory is not the fixed normal directory",
    )
}

fn verify_inodes(tree: &Snapshot, rows: &[Inode]) -> Result<Value> {
    ensure(
        !rows.is_empty() && rows.len() <= 1024,
        "console inode bound exceeded",
    )?;
    let mut paths = BTreeSet::new();
    let mut inode_keys = BTreeSet::new();
    let mut held: Vec<(String, File, Identity)> = Vec::new();
    let mut unique_bytes = 0u64;
    for row in rows {
        ensure(
            !row.paths.is_empty()
                && row.paths.len() <= 256
                && row.nlink == row.paths.len() as u64
                && row.bytes <= 64 * 1024 * 1024
                && fs::valid_digest(&row.sha256),
            "console hardlink group or byte bound differs",
        )?;
        unique_bytes = unique_bytes
            .checked_add(row.bytes)
            .ok_or("console byte overflow")?;
        ensure(
            unique_bytes <= 512 * 1024 * 1024,
            "console closure exceeds byte bound",
        )?;
        let first_index = held.len();
        for path in &row.paths {
            crate::paths::parts(path)?;
            ensure(
                path.starts_with("/usr/") || path.starts_with("/etc/"),
                "console source must be a normal public /usr or /etc file",
            )?;
            ensure(paths.insert(path.clone()), "duplicate console inode alias")?;
            let file = tree.file(path)?;
            let before = fs::stat(&file)?;
            ensure(
                before.size == row.bytes
                    && before.mode & 0o7777 == row.mode
                    && before.uid == row.uid
                    && before.gid == row.gid
                    && before.nlink == row.nlink
                    && tree.identity(path)? == before,
                &format!("normal console identity differs: {path}"),
            )?;
            if first_index == held.len() {
                ensure(
                    inode_keys.insert((before.dev, before.ino)),
                    "two console label groups alias one inode",
                )?;
                ensure(
                    fs::hash(&file)? == row.sha256,
                    &format!("normal console source bytes differ: {path}"),
                )?;
            } else {
                ensure(
                    before == held[first_index].2,
                    "normal console hardlink aliases are not one inode",
                )?;
            }
            held.push((path.clone(), file, before));
        }
    }
    for (path, file, before) in &held {
        ensure(
            fs::stat(file)? == *before && tree.identity(path)? == *before,
            "normal console source changed across complete closure verification",
        )?;
    }
    Ok(
        json!({"inode_groups":rows.len(),"regular_aliases":held.len(),
        "unique_bytes":unique_bytes,"full_hashes_verified":inode_keys.len(),
        "held_descriptor_and_path_identity_rechecked":true,
        "all_hardlink_aliases_present":true}),
    )
}

fn verify_packages(c: &Closure, packages: &[crate::complete_native::Package]) -> Result<()> {
    let actual: Vec<_> = packages
        .iter()
        .map(|p| {
            Ok((
                crate::complete_native::normalize_package(&p.package, &p.architecture)?,
                p,
            ))
        })
        .collect::<Result<_>>()?;
    for (name, version) in &c.packages {
        let architecture = match name.as_str() {
            "console-setup"
            | "console-setup-linux"
            | "coreutils"
            | "keyboard-configuration"
            | "xkb-data" => "all",
            _ => "amd64",
        };
        let identity = format!("{name}:{architecture}");
        let matches: Vec<_> = actual.iter().filter(|(key, _)| key == &identity).collect();
        ensure(
            matches.len() == 1 && matches[0].1.version == *version && matches[0].1.status == "ii ",
            &format!("normal console package selection differs: {identity}"),
        )?;
    }
    Ok(())
}

pub(super) fn verify(tree: &Snapshot, manifest: &CompleteManifest) -> Result<Value> {
    let c: Closure = serde_json::from_str(SOURCE)?;
    valid_contract(&c)?;
    verify_packages(&c, &manifest.packages)?;
    let directory = tree.directory(&c.directory.path)?;
    let directory_id = fs::stat(&directory)?;
    ensure(
        directory_id.uid == c.directory.uid
            && directory_id.gid == c.directory.gid
            && directory_id.mode & 0o7777 == c.directory.mode,
        "normal console cache directory identity differs",
    )?;
    let mut rows = c.files.clone();
    for fixed in &c.unchanged_inputs {
        rows.push(Inode {
            paths: vec![fixed.path.clone()],
            bytes: fixed.bytes,
            sha256: fixed.sha256.clone(),
            mode: fixed.mode,
            uid: fixed.uid,
            gid: fixed.gid,
            nlink: 1,
            category: "normal_unit_or_rule".into(),
            source_type: String::new(),
            target_type: String::new(),
        });
    }
    let inputs = verify_inodes(tree, &rows)?;
    let mut links = Vec::new();
    for link in &c.command_links {
        let (id, target) = tree.link(&link.path)?;
        ensure(
            id.uid == link.uid && id.gid == link.gid && target == link.target,
            &format!("normal console command alias differs: {}", link.path),
        )?;
        links.push((link, id));
    }
    for (link, before) in links {
        let (id, target) = tree.link(&link.path)?;
        ensure(
            id == before && target == link.target,
            "console command alias changed",
        )?;
    }
    ensure(
        fs::stat(&directory)? == directory_id && tree.identity(&c.directory.path)? == directory_id,
        "console directory changed during source verification",
    )?;
    Ok(
        json!({"schema":"droidloom.normal-console-source-admission.v1",
        "source_contract_sha256":fs::digest(SOURCE.as_bytes()),
        "normal_packages":c.packages,"selected_keymap":c.selected_keymap,
        "verified_preinitialization_inputs":inputs,"command_aliases":c.command_links.len(),
        "normal_files_replaced":false,"runtime_started":false,"runtime_qualified":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn fixture() -> (std::path::PathBuf, Snapshot, Inode) {
        let root = std::env::temp_dir().join(format!(
            "console-closure-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir(&root).unwrap();
        std::fs::create_dir_all(root.join("usr/bin")).unwrap();
        std::fs::write(root.join("usr/bin/a"), b"alpha").unwrap();
        std::fs::set_permissions(
            root.join("usr/bin/a"),
            std::fs::Permissions::from_mode(0o755),
        )
        .unwrap();
        std::fs::hard_link(root.join("usr/bin/a"), root.join("usr/bin/b")).unwrap();
        let tree = Snapshot::test_open(&root).unwrap();
        let id = tree.identity("/usr/bin/a").unwrap();
        let row = Inode {
            paths: vec!["/usr/bin/a".into(), "/usr/bin/b".into()],
            bytes: 5,
            sha256: fs::digest(b"alpha"),
            mode: 0o755,
            uid: id.uid,
            gid: id.gid,
            nlink: 2,
            category: "helper".into(),
            source_type: "old".into(),
            target_type: "new".into(),
        };
        (root, tree, row)
    }

    #[test]
    fn compiled_contract_preserves_complete_coreutils_inode() {
        let c: Closure = serde_json::from_str(SOURCE).unwrap();
        valid_contract(&c).unwrap();
        let core = c
            .files
            .iter()
            .find(|r| r.paths.contains(&"/usr/bin/coreutils".to_owned()))
            .unwrap();
        assert_eq!(core.nlink, 116);
        assert_eq!(core.paths.len(), 116);
        assert!(
            core.paths
                .contains(&"/usr/lib/cargo/bin/coreutils/mktemp".to_owned())
        );
        assert!(
            c.command_links
                .iter()
                .any(|l| l.path == "/usr/bin/sh" && l.target == "dash")
        );
    }

    #[test]
    fn normal_alias_group_hash_and_full_link_count_are_required() {
        let (root, tree, row) = fixture();
        assert!(verify_inodes(&tree, &[row.clone()]).is_ok());
        let mut missing = row.clone();
        missing.paths.pop();
        missing.nlink = 1;
        assert!(verify_inodes(&tree, &[missing]).is_err());
        std::fs::hard_link(root.join("usr/bin/a"), root.join("usr/bin/outside")).unwrap();
        assert!(verify_inodes(&tree, &[row.clone()]).is_err());
        std::fs::remove_file(root.join("usr/bin/outside")).unwrap();
        std::fs::write(root.join("usr/bin/a"), b"bravo").unwrap();
        assert!(verify_inodes(&tree, &[row]).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn alias_symlink_or_independent_copy_cannot_replace_hardlink() {
        let (root, tree, row) = fixture();
        std::fs::remove_file(root.join("usr/bin/b")).unwrap();
        std::os::unix::fs::symlink("a", root.join("usr/bin/b")).unwrap();
        assert!(verify_inodes(&tree, &[row.clone()]).is_err());
        std::fs::remove_file(root.join("usr/bin/b")).unwrap();
        std::fs::copy(root.join("usr/bin/a"), root.join("usr/bin/b")).unwrap();
        assert!(verify_inodes(&tree, &[row]).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn actual_dpkg_query_status_and_multiarch_names_are_required() {
        let mut c: Closure = serde_json::from_str(SOURCE).unwrap();
        let version = c.packages["libc6"].clone();
        c.packages = BTreeMap::from([("libc6".into(), version.clone())]);
        let mut p = crate::complete_native::Package {
            package: "libc6:amd64".into(),
            architecture: "amd64".into(),
            status: "ii ".into(),
            version,
        };
        assert!(verify_packages(&c, &[p.clone()]).is_ok());
        assert!(verify_packages(&c, &[p.clone(), p.clone()]).is_err());
        p.package = "libc6:arm64".into();
        assert!(verify_packages(&c, &[p.clone()]).is_err());
        p.architecture = "arm64".into();
        assert!(verify_packages(&c, &[p.clone()]).is_err());
        p.package = "libc6".into();
        p.architecture = "amd64".into();
        assert!(verify_packages(&c, &[p.clone()]).is_ok());
        p.status = "iU ".into();
        assert!(verify_packages(&c, &[p.clone()]).is_err());
        p.status = "ii ".into();
        p.version.push_str("-different");
        assert!(verify_packages(&c, &[p]).is_err());
    }
    /// Explicit read-only validation of a normally captured complete root.
    #[test]
    #[ignore = "requires existing root access and an explicit complete source/manifest pin"]
    fn admitted_normal_source_readback() {
        use std::io::{Seek, SeekFrom};
        assert_eq!(rustix::process::geteuid().as_raw(), 0);
        let root =
            std::path::PathBuf::from(std::env::var("DROIDLOOM_CONSOLE_SOURCE_ROOT").unwrap());
        let path = std::env::var("DROIDLOOM_CONSOLE_SOURCE_MANIFEST").unwrap();
        let expected = std::env::var("DROIDLOOM_CONSOLE_SOURCE_SHA256").unwrap();
        assert!(fs::valid_digest(&expected));
        let (parent, name) = fs::absolute_parent(&path).unwrap();
        let mut file = File::from(
            rustix::fs::openat(
                &parent,
                name.as_str(),
                rustix::fs::OFlags::RDONLY
                    | rustix::fs::OFlags::NOFOLLOW
                    | rustix::fs::OFlags::NONBLOCK
                    | rustix::fs::OFlags::CLOEXEC,
                rustix::fs::Mode::empty(),
            )
            .unwrap(),
        );
        let before = fs::stat(&file).unwrap();
        assert_eq!(before.uid, 0);
        assert_eq!(before.gid, 0);
        assert_eq!(before.nlink, 1);
        assert!(before.size <= 128 * 1024 * 1024);
        assert_eq!(fs::hash(&file).unwrap(), expected);
        file.seek(SeekFrom::Start(0)).unwrap();
        let manifest: CompleteManifest = serde_json::from_reader(&file).unwrap();
        let tree = Snapshot::open(&root).unwrap();
        let report = verify(&tree, &manifest).unwrap();
        assert_eq!(fs::stat(&file).unwrap(), before);
        let path_after = fs::identity(
            &rustix::fs::statat(
                &parent,
                name.as_str(),
                rustix::fs::AtFlags::SYMLINK_NOFOLLOW,
            )
            .unwrap(),
        );
        assert_eq!(path_after, before);
        println!("{}", serde_json::to_string(&report).unwrap());
    }
}
