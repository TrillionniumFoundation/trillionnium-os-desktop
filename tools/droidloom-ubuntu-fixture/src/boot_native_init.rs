//! Bind the original Ubuntu manager before changing a fresh root and in ext4.
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
// The standalone fixture compiles the same source contract without a second pin.
#[path = "../../../runtime/droidloom-contracts/src/native_init.rs"]
mod native_init;
use native_init::NativeInit;
use serde_json::{Value, json};
use std::path::Path;

fn verify_selected(root: &Path, owner: u32, selected: &NativeInit) -> Result<Value> {
    selected.validate()?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, owner)?;
    let (identity, sha256, _) = fs::read_regular(&tree, &selected.path)?;
    ensure(
        identity.mode == 0o100755
            && identity.uid == owner
            && identity.gid == owner
            && identity.nlink == 1
            && identity.size == selected.size
            && sha256 == selected.sha256,
        "native Ubuntu systemd differs from the one committed board-init ELF/package pin",
    )?;
    Ok(json!({"schema":"droidloom.native-init-source-verified.v1",
        "selected":selected,"root":root,"identity":identity,"sha256":sha256,
        "guest_qualified":false}))
}

/// Called before the boot directory, kernel, or host release is written.
pub(super) fn verify(root: &Path) -> Result<Value> {
    verify_selected(root, 0, &native_init::selected()?)
}

/// Read the exact manager back from the image produced by the normal fixture.
pub(super) fn verify_image(
    root: &Path,
    work: &Path,
    image: &FilePin,
    metadata: &Value,
    label: &FilePin,
) -> Result<Value> {
    let selected = native_init::selected()?;
    let source = verify_selected(root, 0, &selected)?;
    // Reuse the original ext4 inode and ea_get evidence, not the metadata of
    // the debugfs export. The normal image builder has already compared these
    // fields with the source root; this additionally fixes the one ELF role.
    ensure(
        metadata["all_matched"] == true,
        "original inode readback incomplete",
    )?;
    let matches = metadata["inodes"]
        .as_array()
        .ok_or("missing original inode rows")?
        .iter()
        .filter(|row| row["path"] == selected.path)
        .collect::<Vec<_>>();
    ensure(
        matches.len() == 1,
        "native init original inode absent or repeated",
    )?;
    let inode = matches[0];
    ensure(
        inode["type"] == "regular"
            && inode["mode"] == 0o755
            && inode["uid"] == 0
            && inode["gid"] == 0
            && inode["nlink"] == 1
            && inode["size"] == selected.size,
        "native init original ext4 inode metadata differs",
    )?;
    let label_bytes = boot_files::read_pin(label, 256)?;
    ensure(
        label_bytes == b"u:object_r:init_exec_t:s0"
            || label_bytes == b"u:object_r:init_exec_t:s0\0",
        "native init original ext4 SELinux label differs",
    )?;
    let directory = work.join("native-init-image-readback");
    boot_files::private_dir(&directory)?;
    let extracted = directory.join("systemd");
    let safe = |p: &Path| {
        p.to_str().is_some_and(|s| {
            s.bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"/._-".contains(&b))
        })
    };
    ensure(
        safe(&extracted) && safe(&image.path),
        "native init image path is unsafe",
    )?;
    boot_files::run_logged(
        &directory,
        "systemd",
        "/usr/sbin/debugfs",
        &[
            "-R".into(),
            format!("dump -p {} {}", selected.path, extracted.display()),
            fs::absolute_string(&image.path)?,
        ],
        30,
    )?;
    let actual = boot_files::pin_file(&extracted)?;
    ensure(
        actual.bytes == selected.size && actual.sha256 == selected.sha256,
        "root image Ubuntu systemd differs from the committed board-init ELF",
    )?;
    let after = verify_selected(root, 0, &selected)?;
    ensure(
        source == after,
        "source Ubuntu systemd changed during image readback",
    )?;
    Ok(
        json!({"schema":"droidloom.native-init-image-verified.v1","selected":selected,
        "source":source,"extracted":actual,"image":image,
        "original_inode":inode,"inode_readback_command":metadata["command"],
        "original_inode_label":{"actual_readback":label,"label_hex":hex::encode(label_bytes)},
        "guest_qualified":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn source_gate_rejects_changed_body_mode_and_symlink() -> Result<()> {
        let root = tempfile::tempdir()?;
        let path = root.path().join("usr/lib/systemd/systemd");
        std::fs::create_dir_all(path.parent().unwrap())?;
        let bytes = b"bounded native-init verifier fixture";
        std::fs::write(&path, bytes)?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755))?;
        let mut selected = native_init::selected()?;
        selected.size = bytes.len() as u64;
        selected.sha256 = fs::digest(bytes);
        let owner = rustix::process::geteuid().as_raw();
        assert!(verify_selected(root.path(), owner, &selected).is_ok());
        std::fs::write(&path, b"changed native-init verifier fixture")?;
        assert!(verify_selected(root.path(), owner, &selected).is_err());
        std::fs::write(&path, bytes)?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o775))?;
        assert!(verify_selected(root.path(), owner, &selected).is_err());
        std::fs::remove_file(&path)?;
        std::os::unix::fs::symlink("/usr/lib/systemd/systemd", &path)?;
        assert!(verify_selected(root.path(), owner, &selected).is_err());
        Ok(())
    }

    fn actual_image_probe(root: &Path, work: &Path, disk: &Path) -> Result<Value> {
        boot_files::private_dir(work)?;
        let selected = native_init::selected()?;
        let metadata =
            crate::boot_runtime::readback_metadata(root, work, disk, &[selected.path.clone()])?;
        let label = work.join("systemd-selinux-label");
        boot_files::run_logged(
            work,
            "inode-label",
            "/usr/sbin/debugfs",
            &[
                "-R".into(),
                format!(
                    "ea_get -f {} {} security.selinux",
                    label.display(),
                    selected.path
                ),
                fs::absolute_string(disk)?,
            ],
            30,
        )?;
        verify_image(
            root,
            work,
            &boot_files::pin_file(disk)?,
            &metadata,
            &boot_files::pin_file(&label)?,
        )
    }

    #[test]
    #[ignore = "requires the explicitly selected public complete-native root; never starts it"]
    fn actual_normal_native_systemd_and_ext4_readback() -> Result<()> {
        ensure(
            rustix::process::geteuid().as_raw() == 0,
            "actual fixture regression requires root",
        )?;
        let root = std::path::PathBuf::from(std::env::var("DROIDLOOM_NATIVE_INIT_TEST_ROOT")?);
        let output = std::path::PathBuf::from(std::env::var("DROIDLOOM_NATIVE_INIT_TEST_OUTPUT")?);
        boot_files::private_dir(&output)?;
        let source = verify(&root)?;
        let selected = native_init::selected()?;
        let copy_root = output.join("copy-root");
        boot_files::private_dir(&copy_root)?;
        std::fs::create_dir_all(copy_root.join("usr/lib/systemd"))?;
        let original = boot_files::pin_file(&root.join(selected.path.trim_start_matches('/')))?;
        let leaf = copy_root.join(selected.path.trim_start_matches('/'));
        boot_files::copy_pin(&original, &leaf, 0o755)?;
        let copy_before = verify(&copy_root)?;
        let mut negatives = Vec::new();
        let mut wrong = selected.clone();
        wrong.sha256 = "0".repeat(64);
        negatives.push(("wrong_digest", verify_selected(&root, 0, &wrong).is_err()));
        wrong = selected.clone();
        wrong.size += 1;
        negatives.push(("wrong_size", verify_selected(&root, 0, &wrong).is_err()));
        std::fs::set_permissions(&leaf, std::fs::Permissions::from_mode(0o775))?;
        negatives.push(("writable_copy", verify(&copy_root).is_err()));
        std::fs::set_permissions(&leaf, std::fs::Permissions::from_mode(0o755))?;
        let alias = copy_root.join("alias");
        std::fs::hard_link(&leaf, &alias)?;
        negatives.push(("multiply_linked_copy", verify(&copy_root).is_err()));
        std::fs::remove_file(alias)?;
        std::fs::remove_file(&leaf)?;
        std::os::unix::fs::symlink(&original.path, &leaf)?;
        negatives.push(("symlink_copy", verify(&copy_root).is_err()));
        std::fs::remove_file(&leaf)?;
        boot_files::copy_pin(&original, &leaf, 0o755)?;
        ensure(
            negatives.iter().all(|(_, rejected)| *rejected),
            "negative native-init gate accepted",
        )?;
        let disk = output.join("native-init.ext4");
        let f = boot_files::new_file(&disk, 0o600)?;
        f.set_len(16 * 1024 * 1024)?;
        f.sync_all()?;
        boot_files::run_logged(
            &output,
            "mke2fs",
            "/usr/sbin/mke2fs",
            &[
                "-q".into(),
                "-F".into(),
                "-t".into(),
                "ext4".into(),
                "-d".into(),
                fs::absolute_string(&copy_root)?,
                fs::absolute_string(&disk)?,
            ],
            30,
        )?;
        boot_files::run_logged(
            &output,
            "label-private-image",
            "/usr/sbin/debugfs",
            &[
                "-w".into(),
                "-R".into(),
                format!(
                    "ea_set {} security.selinux u:object_r:init_exec_t:s0",
                    selected.path
                ),
                fs::absolute_string(&disk)?,
            ],
            30,
        )?;
        let image = actual_image_probe(&copy_root, &output.join("positive-image"), &disk)?;
        let mut image_negatives = Vec::new();
        for (name, field, wrong, restore) in [
            ("inode_mode", "mode", "0100775", "0100755"),
            ("inode_uid", "uid", "1", "0"),
            ("inode_gid", "gid", "1", "0"),
            ("inode_nlink", "links_count", "2", "1"),
        ] {
            boot_files::run_logged(
                &output,
                &format!("mutate-{name}"),
                "/usr/sbin/debugfs",
                &[
                    "-w".into(),
                    "-R".into(),
                    format!("set_inode_field {} {field} {wrong}", selected.path),
                    fs::absolute_string(&disk)?,
                ],
                30,
            )?;
            image_negatives.push((
                name,
                actual_image_probe(&copy_root, &output.join(format!("reject-{name}")), &disk)
                    .is_err(),
            ));
            boot_files::run_logged(
                &output,
                &format!("restore-{name}"),
                "/usr/sbin/debugfs",
                &[
                    "-w".into(),
                    "-R".into(),
                    format!("set_inode_field {} {field} {restore}", selected.path),
                    fs::absolute_string(&disk)?,
                ],
                30,
            )?;
        }
        boot_files::run_logged(
            &output,
            "mutate-inode-label",
            "/usr/sbin/debugfs",
            &[
                "-w".into(),
                "-R".into(),
                format!(
                    "ea_set {} security.selinux u:object_r:rootfs:s0",
                    selected.path
                ),
                fs::absolute_string(&disk)?,
            ],
            30,
        )?;
        image_negatives.push((
            "inode_label",
            actual_image_probe(&copy_root, &output.join("reject-inode-label"), &disk).is_err(),
        ));
        ensure(
            image_negatives.iter().all(|(_, rejected)| *rejected),
            "invalid original ext4 inode was accepted",
        )?;
        ensure(source == verify(&root)?, "actual source root changed")?;
        fs::write_json(
            &fs::absolute_string(&output.join("RESULT.json"))?,
            &json!({
                "schema":"droidloom.native-init-actual-regression.v1","source":source,
                "initial_copy":copy_before,"negative_cases":negatives,"image":image,
                "original_inode_negative_cases":image_negatives,
                "actual_source_unchanged":true,"vm_started":false,"guest_qualified":false
            }),
            0,
        )?;
        Ok(())
    }
}
