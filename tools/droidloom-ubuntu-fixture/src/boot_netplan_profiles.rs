//! Read-only verification of the seven existing Pocket4 Netplan profiles.
//! Private bytes remain in memory; reports contain identities and hashes only.
//! This is configuration admission, never service execution or runtime acceptance.
use crate::complete_snapshot::Snapshot;
use crate::model::Identity;
use crate::{Result, ensure, fs};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::fs::File;
use std::io::Read;
use std::path::Path;

const SOURCE: &str = include_str!(
    "../../../android/framework/droidloom-readiness/board-policy/native-netplan-private-source.json"
);
const NORMAL: &str = include_str!(
    "../../../android/framework/droidloom-readiness/board-policy/native-netplan-source.json"
);
const PROFILE_NAMES: [&str; 7] = [
    "50-cloud-init.yaml",
    "90-NM-3c797701-51cb-45c5-a632-00f213232095.yaml",
    "90-NM-899dbbd2-d128-4d5b-8001-5d3cad80b503.yaml",
    "90-NM-c61cd9fc-00ef-49aa-8ed2-7bfd641c7097.yaml",
    "90-NM-d732669d-d34a-4baa-b97e-bd2563bdd648.yaml",
    "90-NM-e80414a4-1077-49d3-953e-aaccddb3bf21.yaml",
    "90-NM-f84d0c1a-dcde-4634-bf39-13ace1617de3.yaml",
];

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
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Closure {
    schema: String,
    normal_source_contract_sha256: String,
    selection: String,
    profiles: Vec<Input>,
    public_inputs: Vec<Input>,
    public_account_paths: Vec<String>,
    account_lookup: String,
    normal_unit_argv: Vec<String>,
    normal_service_umask: u32,
    source_documents: Vec<Value>,
    observation: Value,
    private_contents_included: bool,
    runtime_qualified: bool,
    policy_enforcement_qualified: bool,
}

fn contract() -> Result<Closure> {
    let c: Closure = serde_json::from_str(SOURCE)?;
    ensure(
        c.schema == "droidloom.native-netplan-private-source.v1"
            && c.normal_source_contract_sha256 == fs::digest(NORMAL.as_bytes())
            && c.selection == "pocket4-existing-seven-NetworkManager-profiles"
            && c.profiles.len() == 7
            && c.public_inputs.len() == 3
            && c.public_account_paths == ["/etc/passwd", "/etc/group"]
            && c.account_lookup == "unique-root-uid0-gid0-and-files-first"
            && c.normal_unit_argv == ["/usr/libexec/netplan/configure"]
            && c.normal_service_umask == 0o022
            && c.source_documents.len() == 5
            && c.observation["schema"] == "droidloom.netplan-private-profile-public-observation.v2"
            && !c.private_contents_included
            && !c.runtime_qualified
            && !c.policy_enforcement_qualified,
        "Netplan private-source contract has another scope",
    )?;
    let expected = PROFILE_NAMES
        .iter()
        .map(|n| format!("/etc/netplan/{n}"))
        .collect::<BTreeSet<_>>();
    ensure(
        c.profiles
            .iter()
            .map(|r| r.path.clone())
            .collect::<BTreeSet<_>>()
            == expected,
        "Netplan profile set differs from the fixed existing selection",
    )?;
    for row in c.profiles.iter().chain(&c.public_inputs) {
        crate::paths::parts(&row.path)?;
        ensure(
            row.uid == 0
                && row.gid == 0
                && row.nlink == 1
                && matches!(row.mode, 0o600 | 0o644)
                && row.bytes > 0
                && row.bytes <= 1024 * 1024
                && fs::valid_digest(&row.sha256),
            "Netplan input pin is incomplete",
        )?;
    }
    ensure(
        c.profiles.iter().all(|r| r.mode == 0o600)
            && c.public_inputs
                .iter()
                .map(|r| r.path.as_str())
                .collect::<BTreeSet<_>>()
                == BTreeSet::from([
                    "/usr/lib/netplan/00-network-manager-all.yaml",
                    "/usr/lib/netplan/PLACEHOLDER",
                    "/etc/nsswitch.conf",
                ]),
        "Netplan public/private input boundary differs",
    )?;
    Ok(c)
}

struct Held {
    path: String,
    file: File,
    before: Identity,
    sha256: String,
}
fn read_held(tree: &Snapshot, path: &str, owner: u32, mode: u32) -> Result<(Held, Vec<u8>)> {
    let mut file = tree.file(path)?;
    let before = fs::stat(&file)?;
    ensure(
        before.uid == owner
            && before.gid == owner
            && before.mode & 0o7777 == mode
            && before.nlink == 1
            && before.size <= 1024 * 1024
            && tree.identity(path)? == before,
        "Netplan input is not a fixed protected regular inode",
    )?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(1024 * 1024 + 1)
        .read_to_end(&mut bytes)?;
    ensure(
        bytes.len() as u64 == before.size
            && fs::stat(&file)? == before
            && tree.identity(path)? == before,
        "Netplan input changed during the complete read",
    )?;
    Ok((
        Held {
            path: path.to_owned(),
            file,
            before,
            sha256: fs::digest(&bytes),
        },
        bytes,
    ))
}
fn pin(tree: &Snapshot, row: &Input) -> Result<(Held, Vec<u8>)> {
    let (held, bytes) = read_held(tree, &row.path, row.uid, row.mode)?;
    ensure(
        held.before.gid == row.gid
            && held.before.size == row.bytes
            && held.before.nlink == row.nlink
            && held.sha256 == row.sha256,
        "Netplan input bytes or declared identity differ",
    )?;
    Ok((held, bytes))
}
fn still_held(tree: &Snapshot, held: &[Held]) -> Result<()> {
    let mut inodes = BTreeSet::new();
    for row in held {
        ensure(
            fs::stat(&row.file)? == row.before
                && tree.identity(&row.path)? == row.before
                && inodes.insert((row.before.dev, row.before.ino)),
            "Netplan input was replaced, changed, or aliased",
        )?;
    }
    Ok(())
}
fn root_account(bytes: &[u8], group: bool) -> Result<()> {
    let text = std::str::from_utf8(bytes)?;
    let fields = text
        .lines()
        .filter(|line| line.starts_with("root:"))
        .map(|line| line.split(':').collect::<Vec<_>>())
        .collect::<Vec<_>>();
    ensure(
        fields.len() == 1
            && if group {
                fields[0].len() == 4 && fields[0][2] == "0"
            } else {
                fields[0].len() == 7 && fields[0][2] == "0" && fields[0][3] == "0"
            },
        "Netplan fixed root account lookup differs",
    )
}
fn files_first(bytes: &[u8]) -> Result<()> {
    let text = std::str::from_utf8(bytes)?;
    for key in ["passwd", "group"] {
        let values = text
            .lines()
            .filter_map(|line| {
                let line = line.split('#').next()?.trim();
                let (name, value) = line.split_once(':')?;
                (name.trim() == key).then_some(value.trim())
            })
            .collect::<Vec<_>>();
        ensure(
            values.len() == 1,
            "Netplan NSS source is missing or duplicated",
        )?;
        let tokens = values[0].split_whitespace().collect::<Vec<_>>();
        ensure(
            tokens.first() == Some(&"files")
                && tokens.get(1).is_none_or(|token| !token.starts_with('[')),
            "Netplan root lookup is not an unmodified files-first lookup",
        )?;
    }
    Ok(())
}

struct HeldDirectory {
    path: String,
    file: File,
    before: Identity,
    names: Vec<String>,
}
fn hold_directory(tree: &Snapshot, path: &str, names: &[String]) -> Result<HeldDirectory> {
    let file = tree.directory(path)?;
    let before = fs::stat(&file)?;
    ensure(
        before.uid == 0
            && before.gid == 0
            && before.mode & 0o7777 == 0o755
            && before.nlink == 2
            && tree.identity(path)? == before
            && tree.names(path)? == names
            && fs::stat(&file)? == before,
        "Netplan directory contains another profile, state, or inode class",
    )?;
    Ok(HeldDirectory {
        path: path.to_owned(),
        file,
        before,
        names: names.to_vec(),
    })
}
fn verify_at(tree: &Snapshot, run_tree: &Snapshot, c: &Closure) -> Result<Value> {
    let profiles = PROFILE_NAMES
        .iter()
        .map(|n| n.to_string())
        .collect::<Vec<_>>();
    let public = vec![
        "00-network-manager-all.yaml".to_string(),
        "PLACEHOLDER".to_string(),
    ];
    let dirs = vec![
        hold_directory(tree, "/etc/netplan", &profiles)?,
        hold_directory(tree, "/usr/lib/netplan", &public)?,
    ];
    let mut runtime_dir = None;
    let run_absent = match run_tree.raw_stat("/netplan") {
        Ok(_) => {
            runtime_dir = Some(hold_directory(run_tree, "/netplan", &[])?);
            false
        }
        Err(error) => {
            let missing = error
                .downcast_ref::<rustix::io::Errno>()
                .is_some_and(|e| *e == rustix::io::Errno::NOENT);
            ensure(
                missing,
                "Netplan runtime input directory cannot be inspected",
            )?;
            true
        }
    };
    let mut held = Vec::new();
    for row in c.profiles.iter().chain(&c.public_inputs) {
        let (value, bytes) = pin(tree, row)?;
        if row.path == "/etc/nsswitch.conf" {
            files_first(&bytes)?;
        }
        held.push(value);
    }
    for path in &c.public_account_paths {
        let (value, bytes) = read_held(tree, path, 0, 0o644)?;
        root_account(&bytes, path == "/etc/group")?;
        held.push(value);
    }
    still_held(tree, &held)?;
    for dir in &dirs {
        ensure(
            fs::stat(&dir.file)? == dir.before
                && tree.identity(&dir.path)? == dir.before
                && tree.names(&dir.path)? == dir.names,
            "Netplan input directory changed while files were held",
        )?;
    }
    if let Some(dir) = runtime_dir {
        ensure(
            fs::stat(&dir.file)? == dir.before
                && run_tree.identity(&dir.path)? == dir.before
                && run_tree.names(&dir.path)? == dir.names,
            "Netplan runtime input directory changed",
        )?;
    }
    if run_absent {
        let err = run_tree
            .raw_stat("/netplan")
            .err()
            .ok_or("Netplan runtime inputs appeared")?;
        ensure(
            err.downcast_ref::<rustix::io::Errno>()
                .is_some_and(|e| *e == rustix::io::Errno::NOENT),
            "Netplan runtime input absence changed",
        )?;
    }
    still_held(tree, &held)?;
    Ok(json!({
        "schema":"droidloom.netplan-profile-input-verification.v1",
        "source_contract_sha256":fs::digest(SOURCE.as_bytes()),
        "selection":c.selection,
        "profiles_verified":c.profiles.len(),
        "held_inputs":held.iter().map(|r| json!({
            "path":r.path,"identity":r.before,"sha256":r.sha256
        })).collect::<Vec<_>>(),
        "exact_directory_sets_verified":true,
        "runtime_input_directory_absent":run_absent,
        "local_root_account_lookup_verified":true,
        "full_bytes_hashed":true,
        "held_and_named_identities_rechecked":true,
        "private_contents_included":false,
        "normal_elf_admission_performed":false,
        "policy_enforcement_qualified":false,
        "runtime_started":false,
        "runtime_qualified":false
    }))
}

pub(crate) fn verify_inputs_report(root: &Path) -> Result<Value> {
    let c = contract()?;
    let tree = if root == Path::new("/") {
        Snapshot {
            root: fs::Tree::open("/", 0)?.root,
        }
    } else {
        Snapshot::open(root)?
    };
    let before = fs::stat(&tree.root)?;
    // /run is a separate, explicitly selected filesystem on the original host.
    // NO_XDEV remains enforced underneath each of the two held roots.
    let run_path = root.join("run");
    let run_tree = Snapshot {
        root: fs::Tree::open(&fs::absolute_string(&run_path)?, 0)?.root,
    };
    let run_before = fs::stat(&run_tree.root)?;
    let mut result = verify_at(&tree, &run_tree, &c)?;
    let reopened = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    ensure(
        fs::stat(&tree.root)? == before && fs::stat(&reopened.root)? == before,
        "Netplan verification root changed",
    )?;
    let run_reopened = fs::Tree::open(&fs::absolute_string(&run_path)?, 0)?;
    ensure(
        fs::stat(&run_tree.root)? == run_before && fs::stat(&run_reopened.root)? == run_before,
        "Netplan runtime input root changed",
    )?;
    result["runtime_root_identity"] = json!(run_before);
    result["root"] = json!(root);
    result["root_identity"] = json!(before);
    Ok(result)
}
pub(crate) fn run(root: &Path) -> Result<()> {
    println!("{}", serde_json::to_string(&verify_inputs_report(root)?)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn contract_keeps_exact_profiles_and_no_runtime_acceptance() {
        let c = contract().unwrap();
        assert_eq!(c.profiles.len(), 7);
        assert!(!c.runtime_qualified && !c.policy_enforcement_qualified);
    }
    #[test]
    fn root_lookup_rejects_remote_first_and_ambiguous_accounts() {
        assert!(files_first(b"passwd: files systemd sss\ngroup: files systemd sss\n").is_ok());
        for bad in [
            &b"passwd: sss files\ngroup: files\n"[..],
            &b"passwd: files [SUCCESS=continue] sss\ngroup: files\n"[..],
            &b"passwd: files\npasswd: files\ngroup: files\n"[..],
        ] {
            assert!(files_first(bad).is_err());
        }
        assert!(root_account(b"root:x:0:0:root:/root:/bin/bash\n", false).is_ok());
        assert!(root_account(b"root:x:0:\n", true).is_ok());
        assert!(root_account(b"root:x:1:0:root:/root:/bin/bash\n", false).is_err());
        assert!(root_account(b"root:x:0:\nroot:x:0:\n", true).is_err());
    }
    #[test]
    fn private_inputs_reject_changed_bytes_hardlinks_and_symlinks() {
        let area = tempfile::tempdir().unwrap();
        let path = area.path().join("selected");
        std::fs::write(&path, b"private input").unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        let tree = Snapshot::test_open(area.path()).unwrap();
        let id = tree.identity("/selected").unwrap();
        let row = Input {
            path: "/selected".into(),
            bytes: 13,
            sha256: fs::digest(b"private input"),
            mode: 0o600,
            uid: id.uid,
            gid: id.gid,
            nlink: 1,
        };
        assert!(pin(&tree, &row).is_ok());
        std::fs::hard_link(&path, area.path().join("alias")).unwrap();
        assert!(pin(&tree, &row).is_err());
        std::fs::remove_file(area.path().join("alias")).unwrap();
        std::fs::write(&path, b"changed input").unwrap();
        assert!(pin(&tree, &row).is_err());
        std::fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink("elsewhere", &path).unwrap();
        assert!(pin(&tree, &row).is_err());
    }
    #[test]
    fn held_input_rejects_same_path_replacement_before_report() {
        let area = tempfile::tempdir().unwrap();
        let path = area.path().join("selected");
        std::fs::write(&path, b"private input").unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        let tree = Snapshot::test_open(area.path()).unwrap();
        let id = tree.identity("/selected").unwrap();
        let (held, _) = read_held(&tree, "/selected", id.uid, 0o600).unwrap();
        std::fs::rename(&path, area.path().join("previous")).unwrap();
        std::fs::write(&path, b"private input").unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        assert!(still_held(&tree, &[held]).is_err());
    }
}
