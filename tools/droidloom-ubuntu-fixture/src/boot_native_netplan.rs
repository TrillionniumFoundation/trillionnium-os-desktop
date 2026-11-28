//! Read-only admission of the exact public no-netdefs Netplan configuration.
//! Runs before initializing a fresh complete root. This never executes configure.
use crate::complete_native::{CompleteManifest, normalize_package};
use crate::complete_snapshot::Snapshot;
use crate::model::Identity;
use crate::{Result, ensure, fs};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;

const SOURCE: &str = include_str!(
    "../../../android/framework/droidloom-readiness/board-policy/native-netplan-source.json"
);
const YAML: &str = "/usr/lib/netplan/00-network-manager-all.yaml";
const UNIT: &str = "/usr/lib/systemd/system/netplan-configure.service";
const ENTRY: &str = "/usr/libexec/netplan/configure";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Closure {
    schema: String,
    packages: BTreeMap<String, String>,
    aliases: Vec<Value>,
    files: Vec<Input>,
    directories: Vec<Directory>,
    command_links: Vec<Link>,
    elf_paths: Vec<String>,
    needed_edges: Vec<Value>,
    shared_library_paths: Vec<String>,
    unit_argv: Vec<String>,
    selected_configuration: String,
    output_path: String,
    output_sha256: String,
    file_packages: BTreeMap<String, String>,
    source_documents: Vec<Value>,
    runtime_qualified: bool,
    other_yaml_profiles_qualified: bool,
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
    category: String,
    source_type: String,
    target_type: String,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Directory {
    path: String,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    names: Vec<String>,
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
    nlink: u64,
}

fn validate(c: &Closure) -> Result<()> {
    ensure(
        c.schema == "droidloom.native-netplan-source-closure.v1"
            && !c.runtime_qualified
            && !c.other_yaml_profiles_qualified
            && c.unit_argv == [ENTRY]
            && c.selected_configuration == "global-NetworkManager-without-netdefs"
            && c.output_path == "/run/NetworkManager/conf.d/10-globally-managed-devices.conf"
            && c.output_sha256 == fs::digest(b"")
            && c.elf_paths.len() == 18
            && c.shared_library_paths.len() == 9
            && c.files.len() == 26
            && c.packages.len() == 19
            && c.command_links.len() == 15
            && !c.needed_edges.is_empty()
            && !c.source_documents.is_empty(),
        "netplan admission is not the compiled public configuration branch",
    )?;
    ensure(
        c.aliases
            == vec![
                json!({"source":"p4_linux_native_bin_t","target":"p4_linux_netplan_exec_t","class":"file"}),
                json!({"source":"p4_linux_runtime_lib_t","target":"p4_linux_netplan_library_t","class":"file"}),
                json!({"source":"p4_linux_runtime_lib_t","target":"p4_linux_netplan_yaml_t","class":"file"}),
                json!({"source":"p4_linux_rootdir_t","target":"p4_linux_netplan_input_dir_t","class":"dir"}),
                json!({"source":"p4_linux_network_manager_run_t","target":"p4_linux_netplan_output_t","class":"file"}),
            ],
        "netplan alias source or class differs",
    )?;
    ensure(
        c.packages
            .get("netplan-generator:amd64")
            .map(String::as_str)
            == Some("1.2-1ubuntu5.1")
            && c.packages.get("libnetplan1:amd64").map(String::as_str) == Some("1.2-1ubuntu5.1")
            && c.packages.get("libsystemd0:amd64").map(String::as_str)
                == Some("259.9-0ubuntu0.1+p4gentmp2"),
        "netplan normal package family differs",
    )?;
    let paths = c
        .files
        .iter()
        .map(|r| r.path.as_str())
        .collect::<BTreeSet<_>>();
    let elves = c
        .elf_paths
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let shared = c
        .shared_library_paths
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    ensure(
        paths.len() == c.files.len() && elves.len() == 18 && shared.len() == 9,
        "duplicate netplan dependency inode",
    )?;
    ensure(
        elves.is_subset(&paths)
            && shared.is_subset(&paths)
            && paths
                == elves
                    .union(&shared)
                    .copied()
                    .chain([YAML, UNIT, "/etc/ld.so.cache"])
                    .collect(),
        "netplan dependency file set is incomplete or contains an extra input",
    )?;
    ensure(
        c.file_packages
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == paths
                .iter()
                .copied()
                .filter(|p| *p != "/etc/ld.so.cache")
                .collect()
            && c.file_packages.values().collect::<BTreeSet<_>>() == c.packages.keys().collect(),
        "netplan package ownership map differs",
    )?;
    for row in &c.files {
        crate::paths::parts(&row.path)?;
        ensure(
            row.uid == 0
                && row.gid == 0
                && row.nlink == 1
                && matches!(row.mode, 0o600 | 0o644 | 0o755)
                && row.bytes > 0
                && row.bytes <= 16 * 1024 * 1024
                && fs::valid_digest(&row.sha256)
                && row.source_type.starts_with("p4_linux_")
                && row.target_type.starts_with("p4_linux_"),
            "netplan normal inode metadata differs",
        )?;
        let expected = match row.path.as_str() {
            ENTRY => ("entry", "p4_linux_native_bin_t", "p4_linux_netplan_exec_t"),
            YAML => {
                ensure(
                    row.bytes == 49
                        && row.mode == 0o600
                        && row.sha256
                            == "d0fa4fd1b88a52f9b8eae641c7c84b7843197155c08df46c0057a4ea23094411",
                    "netplan public YAML differs",
                )?;
                (
                    "config",
                    "p4_linux_runtime_lib_t",
                    "p4_linux_netplan_yaml_t",
                )
            }
            UNIT => {
                ensure(
                    row.bytes == 879
                        && row.sha256
                            == "6893fca2c14d53951c73f396f7528b0b1baa9f570ca9cf099dc1c71df1aa2724",
                    "netplan unit or command arguments differ",
                )?;
                ("unit", "p4_linux_unit_file_t", "p4_linux_unit_file_t")
            }
            "/etc/ld.so.cache" => (
                "cache",
                "p4_linux_console_ld_cache_native_config_t",
                "p4_linux_console_ld_cache_native_config_t",
            ),
            "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2" => (
                "loader",
                "p4_linux_elf_interpreter_t",
                "p4_linux_elf_interpreter_t",
            ),
            path if shared.contains(path) => (
                if elves.contains(path) {
                    "library"
                } else {
                    "shared_label_member"
                },
                "p4_linux_console_library_runtime_lib_t",
                "p4_linux_console_library_runtime_lib_t",
            ),
            path if path.starts_with("/usr/lib/x86_64-linux-gnu/") && elves.contains(path) => (
                "library",
                "p4_linux_runtime_lib_t",
                "p4_linux_netplan_library_t",
            ),
            _ => return Err("unselected netplan dependency path".into()),
        };
        ensure(
            (
                row.category.as_str(),
                row.source_type.as_str(),
                row.target_type.as_str(),
            ) == expected,
            "netplan inode category or label differs",
        )?;
    }
    let directories = [
        (
            "/usr/lib/netplan",
            vec!["00-network-manager-all.yaml", "PLACEHOLDER"],
        ),
        ("/etc/netplan", vec![]),
        ("/run/netplan", vec![]),
    ];
    ensure(
        c.directories.len() == directories.len(),
        "netplan input-directory count differs",
    )?;
    for (row, (path, names)) in c.directories.iter().zip(directories) {
        ensure(
            row.path == path
                && row.names == names
                && row.mode == 0o755
                && row.uid == 0
                && row.gid == 0
                && row.nlink == 2
                && row.source_type == "p4_linux_rootdir_t"
                && row.target_type == "p4_linux_netplan_input_dir_t",
            "netplan input directory selects another configuration profile",
        )?;
    }
    let mut links = BTreeSet::new();
    for row in &c.command_links {
        crate::paths::parts(&row.path)?;
        ensure(
            links.insert(&row.path)
                && row.uid == 0
                && row.gid == 0
                && row.nlink == 1
                && !row.target.starts_with('/')
                && !row.target.is_empty()
                && !row.target.contains(['\0', '\n', '\r']),
            "netplan loader link is unbounded or duplicated",
        )?;
    }
    Ok(())
}

fn verify_files(tree: &Snapshot, rows: &[Input]) -> Result<Value> {
    let mut held = Vec::new();
    let mut inodes = BTreeSet::new();
    for row in rows {
        let file = tree.file(&row.path)?;
        let before = fs::stat(&file)?;
        ensure(
            before.size == row.bytes
                && before.mode & 0o7777 == row.mode
                && before.uid == row.uid
                && before.gid == row.gid
                && before.nlink == row.nlink
                && before.nlink == 1
                && tree.identity(&row.path)? == before
                && inodes.insert((before.dev, before.ino)),
            "netplan package inode identity differs",
        )?;
        ensure(
            fs::hash(&file)? == row.sha256,
            "netplan package payload bytes differ",
        )?;
        held.push((row, file, before));
    }
    for (row, file, before) in &held {
        ensure(
            fs::stat(file)? == *before && tree.identity(&row.path)? == *before,
            "netplan package inode changed while held",
        )?;
    }
    Ok(
        json!({"verified_inodes":held.len(),"full_hashes_verified":true,
        "held_and_named_identities_rechecked":true,"unlisted_hardlinks_rejected":true}),
    )
}

fn hold_directories(tree: &Snapshot, rows: &[Directory]) -> Result<Vec<(String, File, Identity)>> {
    let mut held = Vec::new();
    for row in rows {
        let dir = tree.directory(&row.path)?;
        let before = fs::stat(&dir)?;
        ensure(
            before.mode & 0o7777 == row.mode
                && before.uid == row.uid
                && before.gid == row.gid
                && before.nlink == row.nlink
                && tree.names(&row.path)? == row.names
                && tree.identity(&row.path)? == before
                && fs::stat(&dir)? == before,
            "netplan input directory changed or contains unselected YAML/state",
        )?;
        held.push((row.path.clone(), dir, before));
    }
    Ok(held)
}

pub(super) fn verify(tree: &Snapshot, manifest: &CompleteManifest) -> Result<Value> {
    let c: Closure = serde_json::from_str(SOURCE)?;
    validate(&c)?;
    for (key, version) in &c.packages {
        let rows = manifest
            .packages
            .iter()
            .filter(|p| normalize_package(&p.package, &p.architecture).is_ok_and(|n| n == *key))
            .collect::<Vec<_>>();
        ensure(
            rows.len() == 1 && rows[0].version == *version && rows[0].status == "ii ",
            "netplan normally installed package roster differs",
        )?;
    }
    let directories = hold_directories(tree, &c.directories)?;
    let verified = verify_files(tree, &c.files)?;
    let mut links = Vec::new();
    for row in &c.command_links {
        let (id, target) = tree.link(&row.path)?;
        ensure(
            id.uid == row.uid && id.gid == row.gid && id.nlink == 1 && target == row.target,
            "netplan normal loader link differs",
        )?;
        links.push((row, id));
    }
    for (row, before) in links {
        let (id, target) = tree.link(&row.path)?;
        ensure(
            id == before && target == row.target,
            "netplan loader link changed",
        )?;
    }
    for ((path, dir, before), row) in directories.iter().zip(&c.directories) {
        ensure(
            fs::stat(dir)? == *before
                && tree.identity(path)? == *before
                && tree.names(path)? == row.names,
            "netplan directory changed during admission",
        )?;
    }
    Ok(
        json!({"schema":"droidloom.normal-netplan-source-admission.v1",
        "source_contract_sha256":fs::digest(SOURCE.as_bytes()),"packages":c.packages,
        "input_verification":verified,"normal_unit_argv":c.unit_argv,
        "elf_dependency_count":c.elf_paths.len(),"shared_label_member_count":c.shared_library_paths.len(),
        "selected_configuration":c.selected_configuration,"other_yaml_profiles_qualified":false,
        "package_bytes_replaced":false,"runtime_started":false,"runtime_qualified":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn fixed_contract_rejects_other_unit_yaml_or_execution_class() {
        let mut c: Closure = serde_json::from_str(SOURCE).unwrap();
        validate(&c).unwrap();
        c.unit_argv.push("--root-dir".into());
        assert!(validate(&c).is_err());
        let mut c: Closure = serde_json::from_str(SOURCE).unwrap();
        c.files.iter_mut().find(|r| r.path == YAML).unwrap().sha256 = fs::digest(b"changed");
        assert!(validate(&c).is_err());
        let mut c: Closure = serde_json::from_str(SOURCE).unwrap();
        c.files
            .iter_mut()
            .find(|r| r.path == ENTRY)
            .unwrap()
            .target_type = "p4_linux_native_bin_t".into();
        assert!(validate(&c).is_err());
    }

    #[test]
    fn changed_bytes_links_and_symlink_substitution_are_rejected() {
        let area = tempfile::tempdir().unwrap();
        let path = area.path().join("input");
        std::fs::write(&path, b"selected").unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        let tree = Snapshot::test_open(area.path()).unwrap();
        let id = tree.identity("/input").unwrap();
        let row = Input {
            path: "/input".into(),
            bytes: 8,
            sha256: fs::digest(b"selected"),
            mode: 0o600,
            uid: id.uid,
            gid: id.gid,
            nlink: 1,
            category: "config".into(),
            source_type: String::new(),
            target_type: String::new(),
        };
        assert!(verify_files(&tree, &[row.clone()]).is_ok());
        std::fs::hard_link(&path, area.path().join("alias")).unwrap();
        assert!(verify_files(&tree, &[row.clone()]).is_err());
        std::fs::remove_file(area.path().join("alias")).unwrap();
        std::fs::write(&path, b"modified").unwrap();
        assert!(verify_files(&tree, &[row.clone()]).is_err());
        std::fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink("elsewhere", &path).unwrap();
        assert!(verify_files(&tree, &[row]).is_err());
    }

    #[test]
    fn another_yaml_profile_and_replaced_input_directory_are_rejected() {
        let area = tempfile::tempdir().unwrap();
        std::fs::create_dir(area.path().join("netplan")).unwrap();
        std::fs::set_permissions(
            area.path().join("netplan"),
            std::fs::Permissions::from_mode(0o755),
        )
        .unwrap();
        let tree = Snapshot::test_open(area.path()).unwrap();
        let id = tree.identity("/netplan").unwrap();
        let row = Directory {
            path: "/netplan".into(),
            mode: 0o755,
            uid: id.uid,
            gid: id.gid,
            nlink: id.nlink,
            names: vec![],
            source_type: String::new(),
            target_type: String::new(),
        };
        assert!(hold_directories(&tree, &[row.clone()]).is_ok());
        std::fs::write(area.path().join("netplan/other.yaml"), b"network: {}").unwrap();
        assert!(hold_directories(&tree, &[row.clone()]).is_err());
        std::fs::remove_file(area.path().join("netplan/other.yaml")).unwrap();
        std::fs::remove_dir(area.path().join("netplan")).unwrap();
        std::os::unix::fs::symlink("elsewhere", area.path().join("netplan")).unwrap();
        assert!(hold_directories(&tree, &[row]).is_err());
    }

    #[test]
    #[ignore = "requires root access and explicit complete source/manifest pins"]
    fn admitted_normal_source_readback() {
        use std::io::{Seek, SeekFrom};
        assert_eq!(rustix::process::geteuid().as_raw(), 0);
        let root =
            std::path::PathBuf::from(std::env::var("DROIDLOOM_NETPLAN_SOURCE_ROOT").unwrap());
        let path = std::env::var("DROIDLOOM_NETPLAN_SOURCE_MANIFEST").unwrap();
        let expected = std::env::var("DROIDLOOM_NETPLAN_SOURCE_SHA256").unwrap();
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
        assert_eq!(report["input_verification"]["verified_inodes"], 26);
        assert_eq!(report["runtime_qualified"], false);
        println!("{}", serde_json::to_string(&report).unwrap());
    }
}
