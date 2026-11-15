//! Offline construction of exactly eight labelled inodes; no host mount.
use crate::contract::{Adapter, BuildPlan, FileRef, IMAGE_PATHS, RC_NAMES};
use crate::io::{self, Deadline, Inputs, Runner};
use crate::{Result, require};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::fs::{self, File};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

#[derive(Debug, Serialize)]
pub(crate) struct Inode {
    pub path: String,
    pub inode: u64,
    pub kind: String,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub links: u64,
    pub bytes: u64,
    pub selinux_hex: String,
    pub content_sha256: Option<String>,
}
#[derive(Serialize)]
pub(crate) struct Inventory {
    pub schema: &'static str,
    pub initial_apex_directory_empty: bool,
    pub initial_linkerconfig_directory_empty: bool,
    pub activated_apexes_observed: bool,
    pub generated_linkerconfig_observed: bool,
    pub inodes: Vec<Inode>,
}
pub(crate) struct BuiltImage {
    pub image: FileRef,
    pub inventory: FileRef,
}
fn quote(path: &Path) -> Result<String> {
    crate::contract::absolute(path)?;
    Ok(format!(
        "\"{}\"",
        path.to_str().ok_or("image tool UTF-8 path")?
    ))
}
fn os(args: &[&str]) -> Vec<OsString> {
    args.iter().map(OsString::from).collect()
}
fn debug(
    runner: &mut Runner<'_>,
    inputs: &Inputs,
    plan: &BuildPlan,
    image: &Path,
    command: &str,
) -> Result<Vec<u8>> {
    let mut args = os(&["-R", command]);
    args.push(image.as_os_str().to_owned());
    Ok(runner.run(inputs, &plan.tools.debugfs, &args)?.0)
}
fn checked_number<T: std::str::FromStr>(line: &str, key: &str) -> Result<T>
where
    T::Err: std::error::Error + 'static,
{
    let words: Vec<_> = line.split_whitespace().collect();
    require(
        words.iter().filter(|&&w| w == key).count() == 1,
        format!("one actual {key} field"),
    )?;
    let position = words
        .iter()
        .position(|&w| w == key)
        .ok_or("missing inode field")?;
    Ok(words
        .get(position + 1)
        .ok_or("missing inode value")?
        .parse()?)
}
fn parse_stat(path: &str, raw: &[u8]) -> Result<Inode> {
    let text = std::str::from_utf8(raw)?;
    let lines: Vec<_> = text.lines().collect();
    let first = lines.first().ok_or("empty actual image inode stat")?;
    let expected = if path.starts_with("/rc/") {
        "regular"
    } else {
        "directory"
    };
    let words: Vec<_> = first.split_whitespace().collect();
    let type_at = words
        .iter()
        .position(|&s| s == "Type:")
        .ok_or("actual inode type")?;
    require(
        words.get(type_at + 1) == Some(&expected),
        "image inode type differs",
    )?;
    let mode_at = words
        .iter()
        .position(|&s| s == "Mode:")
        .ok_or("actual inode mode")?;
    let permissions = u32::from_str_radix(words.get(mode_at + 1).ok_or("mode value")?, 8)?;
    let mode = if expected == "regular" {
        0o100000
    } else {
        0o040000
    } | permissions;
    let ids: Vec<_> = lines.iter().filter(|l| l.starts_with("User:")).collect();
    let link_rows: Vec<_> = lines.iter().filter(|l| l.starts_with("Links:")).collect();
    require(
        ids.len() == 1 && link_rows.len() == 1,
        "one original image ownership/links record",
    )?;
    let inode = Inode {
        path: path.into(),
        inode: checked_number(first, "Inode:")?,
        kind: expected.into(),
        mode,
        uid: checked_number(ids[0], "User:")?,
        gid: checked_number(ids[0], "Group:")?,
        bytes: checked_number(ids[0], "Size:")?,
        links: checked_number(link_rows[0], "Links:")?,
        selinux_hex: String::new(),
        content_sha256: None,
    };
    let required_mode = if expected == "regular" {
        0o100444
    } else {
        0o040555
    };
    let required_links = if path == "/" {
        5
    } else if expected == "directory" {
        2
    } else {
        1
    };
    require(
        inode.mode == required_mode
            && inode.uid == 0
            && inode.gid == 0
            && inode.links == required_links
            && inode.inode > 0,
        "exact new runtime inode metadata",
    )?;
    Ok(inode)
}
fn listing(raw: &[u8]) -> Result<BTreeMap<String, (u64, u32, u32, u32)>> {
    let mut rows = BTreeMap::new();
    for line in std::str::from_utf8(raw)?
        .lines()
        .filter(|s| !s.trim().is_empty())
    {
        let fields: Vec<_> = line.split('/').collect();
        require(
            fields.len() == 8 && fields[0].is_empty() && fields[7].is_empty(),
            "exact debugfs directory listing grammar",
        )?;
        if fields[1] == "0" {
            continue;
        }
        let name = fields[5];
        require(
            !name.is_empty() && !name.contains('/') && !name.contains('\0'),
            "bounded actual image entry",
        )?;
        require(
            rows.insert(
                name.to_owned(),
                (
                    fields[1].parse()?,
                    u32::from_str_radix(fields[2], 8)?,
                    fields[3].parse()?,
                    fields[4].parse()?,
                ),
            )
            .is_none(),
            "duplicate image directory entry",
        )?;
    }
    require(
        rows.contains_key(".") && rows.contains_key(".."),
        "actual image directory dot entries",
    )?;
    Ok(rows)
}

pub(crate) fn build(
    root: &Path,
    plan: &BuildPlan,
    adapter: &Adapter,
    contents: &BTreeMap<String, Vec<u8>>,
    inputs: &Inputs,
    runner: &mut Runner<'_>,
    deadline: &Deadline,
) -> Result<BuiltImage> {
    deadline.check()?;
    let work = root.join("image-work");
    io::create_directory(&work)?;
    let image = root.join("runtime.img");
    let file = io::create_file(&image, 0o600)?;
    file.set_len(plan.image_bytes)?;
    file.sync_all()?;
    let uuid = format!(
        "{}-{}-{}-{}-{}",
        &plan.adapter.sha256[..8],
        &plan.adapter.sha256[8..12],
        &plan.adapter.sha256[12..16],
        &plan.adapter.sha256[16..20],
        &plan.adapter.sha256[20..32]
    );
    let mut args = os(&[
        "-q",
        "-F",
        "-t",
        "ext4",
        "-b",
        "4096",
        "-I",
        "256",
        "-N",
        "128",
        "-m",
        "0",
        "-O",
        "none,extent,ext_attr,filetype,sparse_super",
        "-E",
        "lazy_itable_init=0,root_owner=0:0",
        "-U",
        &uuid,
    ]);
    args.push(image.as_os_str().to_owned());
    runner.run(inputs, &plan.tools.mke2fs, &args)?;
    let mut script =
        String::from("rmdir /lost+found\nmkdir /apex\nmkdir /linkerconfig\nmkdir /rc\n");
    for name in RC_NAMES {
        let bytes = contents
            .get(name)
            .ok_or("exact prepared configuration body")?;
        let source = work.join(name);
        io::write_new(&source, bytes, 0o400, deadline)?;
        script.push_str(&format!("write {} /rc/{name}\n", quote(&source)?));
    }
    for (index, path) in IMAGE_PATHS.iter().enumerate() {
        let mode = if path.starts_with("/rc/") {
            0o100444
        } else {
            0o040555
        };
        for (field, value) in [
            ("uid", "0".into()),
            ("gid", "0".into()),
            ("mode", format!("0{mode:o}")),
            ("atime", plan.epoch_seconds.to_string()),
            ("mtime", plan.epoch_seconds.to_string()),
            ("ctime", plan.epoch_seconds.to_string()),
            ("crtime", plan.epoch_seconds.to_string()),
            ("atime_extra", "0".into()),
            ("mtime_extra", "0".into()),
            ("ctime_extra", "0".into()),
            ("crtime_extra", "0".into()),
        ] {
            script.push_str(&format!("set_inode_field {path} {field} {value}\n"));
        }
        let label_path = work.join(format!("label-{index:02}.bin"));
        let mut label = adapter
            .selinux_contexts
            .get(*path)
            .ok_or("missing exact new-inode context")?
            .as_bytes()
            .to_vec();
        label.push(0);
        io::write_new(&label_path, &label, 0o400, deadline)?;
        script.push_str(&format!(
            "ea_set -f {} {path} security.selinux\n",
            quote(&label_path)?
        ));
    }
    let commands = work.join("populate.debugfs");
    io::write_new(&commands, script.as_bytes(), 0o400, deadline)?;
    runner.run(
        inputs,
        &plan.tools.debugfs,
        &[
            "-w".into(),
            "-f".into(),
            commands.into_os_string(),
            image.as_os_str().to_owned(),
        ],
    )?;
    let (out, err) = runner.run(
        inputs,
        &plan.tools.e2fsck,
        &["-f".into(), "-n".into(), image.as_os_str().to_owned()],
    )?;
    let fsck = [out.as_slice(), err.as_slice()].concat();
    let fsck = String::from_utf8(fsck)?;
    require(
        !fsck.contains("Fix?")
            && !fsck.contains("UNEXPECTED INCONSISTENCY")
            && !fsck.contains("WARNING!!!"),
        "runtime filesystem must require no repair",
    )?;
    let mut actual = Vec::new();
    let mut unique_inodes = BTreeSet::new();
    for (index, path) in IMAGE_PATHS.iter().enumerate() {
        deadline.check()?;
        let mut inode = parse_stat(
            path,
            &debug(runner, inputs, plan, &image, &format!("stat {path}"))?,
        )?;
        require(
            unique_inodes.insert(inode.inode),
            "new image has aliased inodes",
        )?;
        let attributes = debug(runner, inputs, plan, &image, &format!("ea_list {path}"))?;
        let attr_lines: Vec<_> = std::str::from_utf8(&attributes)?
            .lines()
            .filter(|s| !s.trim().is_empty())
            .collect();
        require(
            attr_lines.len() == 2
                && attr_lines[0] == "Extended attributes:"
                && attr_lines[1].trim_start().starts_with("security.selinux ("),
            "the only new image xattr is its explicit SELinux context",
        )?;
        let label_path = work.join(format!("readback-label-{index:02}.bin"));
        debug(
            runner,
            inputs,
            plan,
            &image,
            &format!("ea_get -f {} {path} security.selinux", quote(&label_path)?),
        )?;
        let label = fs::read(&label_path)?;
        let mut expected = adapter.selinux_contexts[*path].as_bytes().to_vec();
        expected.push(0);
        require(
            label == expected,
            "full actual security.selinux bytes differ",
        )?;
        inode.selinux_hex = hex::encode(&label);
        if let Some(name) = path.strip_prefix("/rc/") {
            let body = debug(runner, inputs, plan, &image, &format!("cat {path}"))?;
            require(
                contents.get(name) == Some(&body) && inode.bytes == body.len() as u64,
                "actual image configuration body differs",
            )?;
            inode.content_sha256 = Some(io::hash(&body));
        } else {
            let rows = listing(&debug(
                runner,
                inputs,
                plan,
                &image,
                &format!("ls -l -p {path}"),
            )?)?;
            let expected: BTreeSet<&str> = match *path {
                "/" => [".", "..", "apex", "linkerconfig", "rc"].into(),
                "/rc" => [
                    ".",
                    "..",
                    "bootconfig",
                    "cgroups.json",
                    "init.rc",
                    "task_profiles.json",
                ]
                .into(),
                _ => [".", ".."].into(),
            };
            require(
                rows.keys().map(String::as_str).collect::<BTreeSet<_>>() == expected,
                "exact runtime image directory inventory",
            )?;
            require(rows["."].0 == inode.inode, "image directory self inode")?;
            for (name, (_, mode, uid, gid)) in rows {
                let expected_mode = if *path == "/rc" && name != "." && name != ".." {
                    0o100444
                } else {
                    0o040555
                };
                require(
                    mode == expected_mode && uid == 0 && gid == 0,
                    "actual image listing metadata",
                )?;
            }
        }
        actual.push(inode);
    }
    let inventory = Inventory {
        schema: "droidloom-runtime-image-tree-v1",
        initial_apex_directory_empty: true,
        initial_linkerconfig_directory_empty: true,
        activated_apexes_observed: false,
        generated_linkerconfig_observed: false,
        inodes: actual,
    };
    let inventory_ref = io::json_new(
        &root.join("runtime-tree-inventory.json"),
        &inventory,
        deadline,
    )?;
    file.set_permissions(fs::Permissions::from_mode(0o400))?;
    file.sync_all()?;
    let image_ref = io::actual_ref(&image, deadline)?;
    require(
        image_ref.bytes == plan.image_bytes,
        "fixed final runtime image size",
    )?;
    let mut magic = [0_u8; 2];
    use std::os::unix::fs::FileExt;
    file.read_exact_at(&mut magic, 1080)?;
    require(magic == [0x53, 0xef], "actual completed ext4 superblock")?;
    deadline.check()?;
    Ok(BuiltImage {
        image: image_ref,
        inventory: inventory_ref,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn inode_parser_rejects_wrong_mode_owner_links_and_type() {
        let good = b"Inode: 12 Type: regular Mode: 0444 Flags: 0x80000\nUser: 0 Group: 0 Project: 0 Size: 4\nLinks: 1 Blockcount: 8\n";
        assert_eq!(parse_stat("/rc/init.rc", good).unwrap().mode, 0o100444);
        for (a, b) in [
            ("0444", "0644"),
            ("User: 0", "User: 1000"),
            ("Links: 1", "Links: 2"),
            ("regular", "symlink"),
        ] {
            assert!(
                parse_stat(
                    "/rc/init.rc",
                    String::from_utf8(good.to_vec())
                        .unwrap()
                        .replace(a, b)
                        .as_bytes()
                )
                .is_err()
            );
        }
    }
    #[test]
    fn listing_parser_rejects_duplicate_or_unbounded_grammar() {
        let good = b"/2/040555/0/0/.//\n/2/040555/0/0/..//\n/12/040555/0/0/rc//\n";
        assert_eq!(listing(good).unwrap().len(), 3);
        assert!(listing(&[good.as_slice(), b"/13/040555/0/0/rc//\n"].concat()).is_err());
        assert!(listing(b"unexpected tool diagnostic\n").is_err());
    }
    #[test]
    fn actual_offline_image_has_exact_bodies_labels_and_eight_inodes() {
        // This fixture exercises the image builder only. It constructs no
        // RuntimeDeclaration, ProductionSelection or admission capability.
        let work = tempfile::Builder::new()
            .prefix("runtime-image-ordinary-")
            .tempdir()
            .unwrap()
            .keep();
        println!("RUNTIME_IMAGE_FIXTURE_ROOT:{}", work.display());
        let d = Deadline::new(120);
        let source = work.as_path().join("synthetic-input");
        io::write_new(&source, b"synthetic ordinary input\n", 0o400, &d).unwrap();
        let reference = io::actual_ref(&source, &d).unwrap();
        let tools = crate::contract::Tools {
            mke2fs: io::actual_ref(Path::new("/usr/sbin/mke2fs"), &d).unwrap(),
            debugfs: io::actual_ref(Path::new("/usr/sbin/debugfs"), &d).unwrap(),
            e2fsck: io::actual_ref(Path::new("/usr/sbin/e2fsck"), &d).unwrap(),
        };
        tools.validate().unwrap();
        let mut inputs = Inputs::new();
        for tool in [&tools.mke2fs, &tools.debugfs, &tools.e2fsck] {
            inputs.add(tool, &d).unwrap();
        }
        let plan = BuildPlan {
            schema: "droidloom-runtime-build-plan-v1".into(),
            base: reference.clone(),
            system: reference.clone(),
            vendor: reference.clone(),
            capture: reference.clone(),
            adapter: reference.clone(),
            tools,
            image_bytes: crate::contract::IMAGE_BYTES_MIN,
            epoch_seconds: 1_230_768_000,
            deadline_seconds: 120,
        };
        let adapter = Adapter {
            schema: "droidloom-runtime-preinit-adapter-v1".into(),
            base_cohort_sha256: reference.sha256.clone(),
            source_system_sha256: reference.sha256.clone(),
            original_capture_sha256: reference.sha256.clone(),
            provenance: reference.clone(),
            bootconfig_provenance: reference,
            files: BTreeMap::new(),
            selinux_contexts: IMAGE_PATHS
                .into_iter()
                .map(|p| (p.into(), "u:object_r:system_file:s0".into()))
                .collect(),
        };
        let contents = [
            (
                "bootconfig".into(),
                b"androidboot.hardware = \"ordinary-fixture\"\n".to_vec(),
            ),
            ("cgroups.json".into(), b"{\"Cgroups\":[]}\n".to_vec()),
            (
                "init.rc".into(),
                b"# ordinary image-byte fixture; never executed\n".to_vec(),
            ),
            ("task_profiles.json".into(), b"{\"Profiles\":[]}\n".to_vec()),
        ]
        .into();
        let logs = work.as_path().join("commands");
        io::create_directory(&logs).unwrap();
        let mut runner = Runner {
            root: &logs,
            deadline: &d,
            epoch: plan.epoch_seconds,
            commands: Vec::new(),
        };
        let built = build(
            work.as_path(),
            &plan,
            &adapter,
            &contents,
            &inputs,
            &mut runner,
            &d,
        )
        .unwrap();
        println!(
            "RUNTIME_IMAGE_WITNESS:{}",
            serde_json::json!({"image":built.image,"inventory":built.inventory,"commands":runner.commands.len()})
        );
        assert_eq!(built.image.bytes, crate::contract::IMAGE_BYTES_MIN);
        let inventory: serde_json::Value =
            serde_json::from_slice(&fs::read(&built.inventory.path).unwrap()).unwrap();
        assert_eq!(inventory["inodes"].as_array().unwrap().len(), 8);
        assert_eq!(inventory["activated_apexes_observed"], false);
        assert_eq!(inventory["generated_linkerconfig_observed"], false);
        assert!(
            runner
                .commands
                .iter()
                .all(|c| c.returncode == Some(0) && c.reaped)
        );
        inputs.revalidate_all(&d).unwrap();
    }
}
