use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs, materialize,
    model::{Component, Content, Manifest},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

/// A separately captured, fully materialized module tree, bound to the normal
/// kernel producer's image/config/module manifest. No live /boot mutation.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KernelMaterial {
    pub image: FilePin,
    pub fixture_manifest: FilePin,
    pub materialized_root: PathBuf,
    pub normal_module_manifest: FilePin,
    pub normal_initrd: FilePin,
}

pub fn install(
    root: &Path,
    work: &Path,
    original_release: &str,
    input: &KernelMaterial,
) -> Result<Value> {
    let manifest: Manifest = serde_json::from_slice(&boot_files::read_pin(
        &input.fixture_manifest,
        128 * 1024 * 1024,
    )?)?;
    materialize::validate(&manifest)?;
    let kernel = manifest
        .kernel
        .as_ref()
        .ok_or("target module fixture lacks kernel producer binding")?;
    let release = &manifest.target_kernel_release;
    ensure(
        release.starts_with("6.18.")
            && release != original_release
            && release
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b)),
        "replacement target release must be a new isolated shared-kernel candidate",
    )?;
    ensure(
        kernel.complete_installed_tree
            && kernel.binding.release == *release
            && kernel.binding.image_sha256 == input.image.sha256
            && kernel.image_identity.size == input.image.bytes
            && kernel.binding.module_manifest_sha256 == input.normal_module_manifest.sha256,
        "new target image/modules are not from one admitted kernel producer",
    )?;
    boot_files::checked_file(&input.normal_module_manifest)?;
    let prefix = format!("/usr/lib/modules/{release}");
    let ancestors = ["/usr", "/usr/lib", "/usr/lib/modules"];
    for e in &manifest.entries {
        ensure(
            match e.component {
                Component::AncestorDirectory => {
                    e.content == Content::Directory
                        && (ancestors.contains(&e.path.as_str())
                            || e.path == prefix
                            || e.path.starts_with(&(prefix.clone() + "/")))
                }
                Component::TargetModule => {
                    e.path == prefix || e.path.starts_with(&(prefix.clone() + "/"))
                }
                _ => false,
            },
            "supplemental module manifest contains unrelated native state",
        )?;
    }
    let source = fs::Tree::open(&fs::absolute_string(&input.materialized_root)?, 0)?;
    materialize::verify(
        &manifest,
        &input.fixture_manifest.sha256,
        &fs::absolute_string(&input.materialized_root)?,
        0,
    )?;
    let target = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    match target.identity(&prefix) {
        Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => (),
        _ => return Err("candidate module tree already exists".into()),
    }
    let old = format!("/usr/lib/modules/{original_release}");
    let original = target.dir(&old)?;
    let id = fs::stat(&original)?;
    ensure(
        id.uid == 0 && id.mode & 0o022 == 0,
        "old fixture module root is not protected",
    )?;
    let retired = work.join("prior-fixture-modules");
    ensure(
        std::fs::symlink_metadata(&retired)
            .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound),
        "old module retirement destination already exists",
    )?;
    std::fs::rename(boot_files::guest_path(root, &old)?, &retired)?;
    let retired_tree = fs::Tree::open(&fs::absolute_string(&retired)?, 0)?;
    let moved = fs::stat(&retired_tree.root)?;
    ensure(
        (moved.dev, moved.ino) == (id.dev, id.ino),
        "scoped fixture module retirement changed identity",
    )?;
    let mut dirs: Vec<_> = manifest
        .entries
        .iter()
        .filter(|e| {
            e.content == Content::Directory
                && (e.path == prefix || e.path.starts_with(&(prefix.clone() + "/")))
        })
        .collect();
    dirs.sort_by_key(|e| (e.path.matches('/').count(), e.path.as_str()));
    for e in &dirs {
        target.mkdir(&e.path)?;
    }
    for e in &manifest.entries {
        match &e.content {
            Content::Regular { sha256 } => {
                let actual = source.identity(&e.path)?;
                fs::copy_regular(&source, &target, &e.path, &actual, sha256, &e.xattrs)?;
            }
            Content::Hardlink {
                target: primary, ..
            } => target.hardlink(&e.path, primary)?,
            Content::Symlink { target: link } => {
                let (actual, value) = source.read_link(&e.path)?;
                ensure(value == *link, "supplemental source alias changed")?;
                target.symlink(&e.path, link, &actual)?;
            }
            Content::Directory => (),
        }
    }
    for e in dirs.iter().rev() {
        fs::set_metadata(&target.dir(&e.path)?, &e.source, &e.xattrs)?;
    }
    let mut count = 0usize;
    for e in &manifest.entries {
        if ancestors.contains(&e.path.as_str()) {
            continue;
        }
        let actual = target.identity(&e.path)?;
        ensure(
            fs::same_metadata(&actual, &e.source),
            "installed target module metadata differs",
        )?;
        match &e.content {
            Content::Regular { sha256 } | Content::Hardlink { sha256, .. } => {
                let (_, actual_hash, attrs) = fs::read_regular(&target, &e.path)?;
                ensure(
                    actual_hash == *sha256 && attrs == e.xattrs,
                    "installed target module content differs",
                )?;
                count += 1;
            }
            Content::Symlink { target: link } => ensure(
                target.read_link(&e.path)?.1 == *link,
                "installed module alias differs",
            )?,
            Content::Directory => (),
        }
    }
    fs::assert_root_namespace(&fs::absolute_string(root)?, &target)?;
    fs::assert_root_namespace(&fs::absolute_string(&input.materialized_root)?, &source)?;
    Ok(
        json!({"target_kernel_release":release,"kernel_image":input.image,"normal_initrd":input.normal_initrd,
        "fixture_manifest":input.fixture_manifest,"normal_module_manifest":input.normal_module_manifest,
        "module_regular_paths_verified":count,"retired_private_fixture_modules":retired,
        "physical_boot_or_modules_modified":false,"guest_qualified":false}),
    )
}
