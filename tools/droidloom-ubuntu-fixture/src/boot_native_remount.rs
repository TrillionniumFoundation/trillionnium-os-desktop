//! Admit the exact normal remount unit and its two executable package inodes.
//! This is a read-only check of a newly materialized complete native root.
use crate::complete_native::{CompleteManifest, normalize_package};
use crate::complete_snapshot::Snapshot;
use crate::{Result, ensure, fs};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!(
    "../../../android/framework/droidloom-readiness/board-policy/native-remount-source.json"
);
const SYSTEMD: &str = "259.9-0ubuntu0.1+p4gentmp2";
const MOUNT: &str = "2.41.3-3ubuntu2.2";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Closure {
    schema: String,
    packages: BTreeMap<String, String>,
    aliases: Vec<Value>,
    files: Vec<Input>,
    command_links: Vec<Link>,
    source_documents: Vec<Value>,
    runtime_qualified: bool,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    path: String,
    bytes: u64,
    sha256: String,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    source_type: String,
    target_type: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Link {
    path: String,
    target: String,
    uid: u32,
    gid: u32,
}

fn validate(c: &Closure) -> Result<()> {
    ensure(
        c.schema == "droidloom.native-remount-source-closure.v1"
            && !c.runtime_qualified
            && c.packages
                == BTreeMap::from([
                    ("systemd:amd64".into(), SYSTEMD.into()),
                    ("mount:amd64".into(), MOUNT.into()),
                ])
            && c.aliases
                == vec![
                    json!({"source":"p4_linux_runtime_lib_t","target":"p4_linux_remount_exec_t","class":"file"}),
                    json!({"source":"p4_linux_native_bin_t","target":"p4_linux_remount_mount_exec_t","class":"file"}),
                    json!({"source":"p4_linux_native_config_t","target":"p4_linux_remount_fstab_native_config_t","class":"file"}),
                    json!({"source":"device","target":"p4_linux_root_uuid_link_t","class":"lnk_file"}),
                    json!({"source":"device","target":"p4_linux_root_block_t","class":"blk_file"}),
                ]
            && !c.source_documents.is_empty(),
        "remount source contract is not the compiled normal package selection",
    )?;
    let expected = BTreeMap::from([
        (
            "/usr/lib/systemd/systemd-remount-fs",
            (0o755, "p4_linux_runtime_lib_t", "p4_linux_remount_exec_t"),
        ),
        (
            "/usr/bin/mount",
            (
                0o4755,
                "p4_linux_native_bin_t",
                "p4_linux_remount_mount_exec_t",
            ),
        ),
        (
            "/usr/lib/systemd/system/systemd-remount-fs.service",
            (0o644, "p4_linux_unit_file_t", "p4_linux_unit_file_t"),
        ),
    ]);
    ensure(
        c.files.len() == expected.len(),
        "unexpected remount inode count",
    )?;
    let mut seen = BTreeSet::new();
    for row in &c.files {
        let selected = expected
            .get(row.path.as_str())
            .ok_or("unselected remount input")?;
        ensure(
            seen.insert(&row.path)
                && row.uid == 0
                && row.gid == 0
                && row.nlink == 1
                && (row.mode, row.source_type.as_str(), row.target_type.as_str()) == *selected
                && row.bytes > 0
                && row.bytes <= 16 * 1024 * 1024
                && fs::valid_digest(&row.sha256),
            "remount inode contract changed ownership, link count, mode or role",
        )?;
    }
    ensure(
        c.command_links.len() == 1
            && c.command_links[0].path == "/etc/mtab"
            && c.command_links[0].target == "../proc/self/mounts"
            && c.command_links[0].uid == 0
            && c.command_links[0].gid == 0,
        "remount mount-table link is not the original distribution alias",
    )
}

fn verify_files(tree: &Snapshot, rows: &[Input]) -> Result<Value> {
    let mut held = Vec::new();
    let mut identities = BTreeSet::new();
    let mut paths = BTreeSet::new();
    for row in rows {
        crate::paths::parts(&row.path)?;
        ensure(paths.insert(&row.path), "duplicate remount source path")?;
        let file = tree.file(&row.path)?;
        let before = fs::stat(&file)?;
        ensure(
            before.size == row.bytes
                && before.mode & 0o7777 == row.mode
                && before.uid == row.uid
                && before.gid == row.gid
                && before.nlink == 1
                && row.nlink == 1
                && tree.identity(&row.path)? == before
                && identities.insert((before.dev, before.ino)),
            "normal remount inode identity differs",
        )?;
        ensure(
            fs::hash(&file)? == row.sha256,
            "normal remount package bytes differ",
        )?;
        held.push((row, file, before));
    }
    for (row, file, before) in &held {
        ensure(
            fs::stat(file)? == *before && tree.identity(&row.path)? == *before,
            "normal remount source changed while held",
        )?;
    }
    Ok(
        json!({"verified_inodes":held.len(),"full_hashes_verified":true,
              "held_and_named_identities_rechecked":true,"unlisted_hardlinks_rejected":true}),
    )
}

pub(super) fn verify(tree: &Snapshot, manifest: &CompleteManifest) -> Result<Value> {
    let c: Closure = serde_json::from_str(SOURCE)?;
    validate(&c)?;
    for (key, version) in &c.packages {
        let selected = manifest
            .packages
            .iter()
            .filter(|p| {
                normalize_package(&p.package, &p.architecture).is_ok_and(|actual| actual == *key)
            })
            .collect::<Vec<_>>();
        ensure(
            selected.len() == 1 && selected[0].version == *version && selected[0].status == "ii ",
            "normal remount package roster differs",
        )?;
    }
    let result = verify_files(tree, &c.files)?;
    let mut links = Vec::new();
    for link in &c.command_links {
        let (identity, target) = tree.link(&link.path)?;
        ensure(
            identity.uid == link.uid
                && identity.gid == link.gid
                && identity.nlink == 1
                && target == link.target,
            "normal remount mount-table alias differs",
        )?;
        links.push((link, identity));
    }
    for (link, before) in links {
        let (identity, target) = tree.link(&link.path)?;
        ensure(
            identity == before && target == link.target,
            "remount mount-table alias changed",
        )?;
    }
    Ok(
        json!({"schema":"droidloom.normal-remount-source-admission.v1",
              "source_contract_sha256":fs::digest(SOURCE.as_bytes()),
              "packages":c.packages,"input_verification":result,
              "package_bytes_replaced":false,"runtime_started":false,"runtime_qualified":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::File;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn fixed_contract_cannot_substitute_another_executable_or_clear_suid() {
        let mut c: Closure = serde_json::from_str(SOURCE).unwrap();
        validate(&c).unwrap();
        let row = c
            .files
            .iter_mut()
            .find(|r| r.path == "/usr/bin/mount")
            .unwrap();
        row.mode = 0o755;
        assert!(validate(&c).is_err());
        let mut c: Closure = serde_json::from_str(SOURCE).unwrap();
        c.files[0].path = "/usr/bin/umount".into();
        assert!(validate(&c).is_err());
    }

    #[test]
    fn changed_bytes_extra_links_and_path_replacement_are_rejected() {
        let area = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(area.path().join("usr/bin")).unwrap();
        let path = area.path().join("usr/bin/mount");
        std::fs::write(&path, b"selected").unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).unwrap();
        let tree = Snapshot::test_open(area.path()).unwrap();
        let id = tree.identity("/usr/bin/mount").unwrap();
        let row = Input {
            path: "/usr/bin/mount".into(),
            bytes: 8,
            sha256: fs::digest(b"selected"),
            mode: 0o755,
            uid: id.uid,
            gid: id.gid,
            nlink: 1,
            source_type: String::new(),
            target_type: String::new(),
        };
        assert!(verify_files(&tree, &[row.clone()]).is_ok());
        std::fs::hard_link(&path, area.path().join("usr/bin/extra")).unwrap();
        assert!(verify_files(&tree, &[row.clone()]).is_err());
        std::fs::remove_file(area.path().join("usr/bin/extra")).unwrap();
        std::fs::write(&path, b"replaced").unwrap();
        assert!(verify_files(&tree, &[row.clone()]).is_err());
        std::fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink("elsewhere", &path).unwrap();
        assert!(verify_files(&tree, &[row]).is_err());
    }


    #[test]
    fn root_fstab_and_device_custody_reject_ambiguous_or_changed_inputs() {
        use std::process::Command;
        let area = tempfile::tempdir().unwrap();
        let source = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../runtime/droidloom-early-boot");
        let program = area.path().join("root-custody.c");
        let executable = area.path().join("root-custody");
        std::fs::write(&program, r##"
#include "linux_run_label.c"
#include <assert.h>
#include <stdlib.h>

static void parse_case(const char *text, bool accepted) {
    char data[ROOT_FSTAB_LIMIT + 1], uuid[37];
    size_t n = strlen(text);
    memcpy(data, text, n);
    int result = root_fstab_uuid(data, n, uuid);
    assert((result == 0) == accepted);
    if (accepted) assert(!strcmp(uuid, "01c27223-3933-481e-9836-7bd0ef1be8c9"));
}
int main(int argc, char **argv) {
    assert(argc == 2);
    parse_case("# root\nUUID=01c27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1\n", true);
    parse_case("/dev/disk/by-uuid/01c27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1\n/swap.img none swap sw 0 0\n", true);
    parse_case("UUID=01c27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1\nUUID=01c27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1\n", false);
    parse_case("UUID=01c27223-3933-481e-9836-7bd0ef1be8c9 / xfs defaults 0 1\n", false);
    parse_case("UUID=01c27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1", false);
    parse_case("UUID=01c27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1 extra\n", false);
    parse_case("UUID=01C27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1\n", false);
    parse_case("UUID=../01c27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1\n", false);
    parse_case("/dev/vda / ext4 defaults 0 1\n", false);
    parse_case("/dev/disk/by-uuid/01c27223-3933-481e-9836-7bd0ef1be8c9/child / ext4 defaults 0 1\n", false);
    parse_case("UUID=01c27223-3933-481e-9836-7bd0ef1be8c9 /boot ext4 defaults 0 1\n", false);
    char embedded[] = "UUID=01c27223-3933-481e-9836-7bd0ef1be8c9 / ext4 defaults 0 1\0\n";
    char uuid[37];
    assert(root_fstab_uuid(embedded, sizeof(embedded) - 1, uuid) < 0);
    dev_t root = makedev(259, 2), dev = makedev(0, 20);
    struct stat block = { .st_mode = S_IFBLK | 0600, .st_uid = 0,
        .st_gid = 0, .st_rdev = root, .st_dev = dev, .st_nlink = 1 };
    assert(root_block_metadata(&block, root, dev));
    block.st_gid = 6; block.st_mode = S_IFBLK | 0660;
    assert(root_block_metadata(&block, root, dev));
    struct stat good = block;
    block.st_gid = 7; assert(!root_block_metadata(&block, root, dev)); block = good;
    block.st_mode |= 0006; assert(!root_block_metadata(&block, root, dev)); block = good;
    block.st_uid = 1000; assert(!root_block_metadata(&block, root, dev)); block = good;
    block.st_rdev = makedev(259, 3); assert(!root_block_metadata(&block, root, dev)); block = good;
    block.st_mode = S_IFCHR | 0660; assert(!root_block_metadata(&block, root, dev)); block = good;
    block.st_nlink = 2; assert(!root_block_metadata(&block, root, dev)); block = good;
    block.st_size = 1; assert(!root_block_metadata(&block, root, dev));
    struct root_device_hold held = {0};
    for (size_t i = 0; i < ROOT_HOLDS; i++) held.fd[i] = -1;
    held.fd[ROOT_ETC] = open(argv[1], O_PATH | O_DIRECTORY | O_CLOEXEC);
    assert(held.fd[ROOT_ETC] >= 0);
    int file = openat(held.fd[ROOT_ETC], "fstab", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
    assert(file >= 0 && write(file, "selected\n", 9) == 9);
    assert(root_capture(&held, ROOT_FSTAB, file) == 0);
    assert(root_stable_inode(&held, ROOT_FSTAB, -1) == 0);
    assert(linkat(held.fd[ROOT_ETC], "fstab", held.fd[ROOT_ETC], "alias", 0) == 0);
    assert(root_stable_inode(&held, ROOT_FSTAB, -1) < 0);
    assert(unlinkat(held.fd[ROOT_ETC], "alias", 0) == 0);
    assert(fstat(file, &held.identity[ROOT_FSTAB]) == 0);
    assert(renameat(held.fd[ROOT_ETC], "fstab", held.fd[ROOT_ETC], "old-fstab") == 0);
    int substitute = openat(held.fd[ROOT_ETC], "fstab", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
    assert(substitute >= 0 && write(substitute, "selected\n", 9) == 9);
    assert(root_stable_inode(&held, ROOT_FSTAB, -1) < 0);
    close(substitute); close(file);
    assert(unlinkat(held.fd[ROOT_ETC], "fstab", 0) == 0);
    assert(symlinkat("../../vda", held.fd[ROOT_ETC], "node") == 0);
    held.fd[ROOT_LINK] = vt_open_path(held.fd[ROOT_ETC], "node", false);
    assert(held.fd[ROOT_LINK] >= 0);
    char text[70];
    assert(root_read_link(&held, text) == 0 && !strcmp(text, "../../vda"));
    close(held.fd[ROOT_LINK]);
    assert(unlinkat(held.fd[ROOT_ETC], "node", 0) == 0);
    assert(symlinkat("../../escape/device", held.fd[ROOT_ETC], "node") == 0);
    held.fd[ROOT_LINK] = vt_open_path(held.fd[ROOT_ETC], "node", false);
    assert(held.fd[ROOT_LINK] >= 0 && root_read_link(&held, text) < 0);
    close(held.fd[ROOT_LINK]); close(held.fd[ROOT_ETC]);
    puts("root-custody: 12 fstab, 9 block metadata, 3 held-inode, 2 link checks passed");
    return 0;
}
"##).unwrap();
        let built = Command::new("cc")
            .args(["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                   "-ffunction-sections", "-fdata-sections"])
            .arg("-I").arg(&source)
            .arg(&program).args(["-Wl,--gc-sections", "-o"]).arg(&executable)
            .output().unwrap();
        assert!(built.status.success(), "{}", String::from_utf8_lossy(&built.stderr));
        let ran = Command::new(executable).arg(area.path()).output().unwrap();
        assert!(ran.status.success(), "stdout={} stderr={}",
            String::from_utf8_lossy(&ran.stdout), String::from_utf8_lossy(&ran.stderr));
        assert_eq!(String::from_utf8_lossy(&ran.stdout).trim(),
            "root-custody: 12 fstab, 9 block metadata, 3 held-inode, 2 link checks passed");
    }

    /// Read the committed contract against a complete, normally captured root.
    #[test]
    #[ignore = "requires root access and explicit complete source/manifest pins"]
    fn admitted_normal_source_readback() {
        use std::io::{Seek, SeekFrom};
        assert_eq!(rustix::process::geteuid().as_raw(), 0);
        let root =
            std::path::PathBuf::from(std::env::var("DROIDLOOM_REMOUNT_SOURCE_ROOT").unwrap());
        let path = std::env::var("DROIDLOOM_REMOUNT_SOURCE_MANIFEST").unwrap();
        let expected = std::env::var("DROIDLOOM_REMOUNT_SOURCE_SHA256").unwrap();
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
        assert_eq!((before.uid, before.gid, before.nlink), (0, 0, 1));
        assert!(before.size <= 128 * 1024 * 1024);
        assert_eq!(fs::hash(&file).unwrap(), expected);
        file.seek(SeekFrom::Start(0)).unwrap();
        let manifest: CompleteManifest = serde_json::from_reader(&file).unwrap();
        let tree = Snapshot::open(&root).unwrap();
        let report = verify(&tree, &manifest).unwrap();
        assert_eq!(fs::stat(&file).unwrap(), before);
        assert_eq!(
            fs::identity(
                &rustix::fs::statat(
                    &parent,
                    name.as_str(),
                    rustix::fs::AtFlags::SYMLINK_NOFOLLOW
                )
                .unwrap()
            ),
            before
        );
        println!("{}", serde_json::to_string(&report).unwrap());
    }
}
