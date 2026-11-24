use crate::fs::{self, Tree};
use crate::model::*;
use crate::paths;
use crate::{Result, ensure};
use std::collections::{BTreeMap, BTreeSet};

pub fn validate(manifest: &Manifest) -> Result<()> {
    ensure(
        manifest.schema == MANIFEST_SCHEMA && !manifest.guest_qualified,
        "manifest cannot assert guest qualification",
    )?;
    ensure(
        !manifest.unresolved_requirements.is_empty(),
        "material-only manifest cannot remove qualification requirements",
    )?;
    ensure(
        fs::valid_digest(&manifest.selection_sha256) && fs::valid_digest(&manifest.audit_sha256),
        "invalid input identity",
    )?;
    ensure(
        manifest.target_kernel_release.starts_with("6.18."),
        "unexpected target kernel family",
    )?;
    let mut entries = BTreeMap::new();
    for entry in &manifest.entries {
        paths::validate(
            &entry.path,
            &entry.component,
            &manifest.target_kernel_release,
        )?;
        ensure(
            entries.insert(entry.path.clone(), entry).is_none(),
            "duplicate manifest destination",
        )?;
        ensure(
            fs::content_type_matches(&entry.source, &entry.content),
            "manifest inode type differs from content",
        )?;
        if entry.component == Component::AncestorDirectory {
            ensure(
                entry.content == Content::Directory,
                "ancestor is not a directory",
            )?;
        }
        if entry.component == Component::TargetModule {
            ensure(
                manifest.kernel.is_some(),
                "module entry lacks producer identity",
            )?;
        }
        if entry.component == Component::SnapArchive {
            ensure(
                matches!(
                    entry.content,
                    Content::Regular { .. } | Content::Hardlink { .. }
                ),
                "snap archive must be a regular file",
            )?;
        }
        match &entry.content {
            Content::Regular { sha256 } | Content::Hardlink { sha256, .. } => {
                ensure(fs::valid_digest(sha256), "invalid file digest")?
            }
            Content::Symlink { target } => {
                paths::normalize_link(&entry.path, target)?;
            }
            _ => (),
        }
    }
    for entry in &manifest.entries {
        let parent = paths::parent(&entry.path);
        if parent != "/" {
            ensure(
                entries
                    .get(parent)
                    .is_some_and(|e| e.content == Content::Directory),
                "missing or symlink manifest parent",
            )?;
        }
        if let Content::Hardlink { target, sha256 } = &entry.content {
            let original = entries.get(target).ok_or("hardlink target absent")?;
            ensure(
                target < &entry.path
                    && matches!(&original.content, Content::Regular{sha256: s} if s == sha256),
                "hardlink must refer to an earlier primary regular entry",
            )?;
            ensure(
                original.source == entry.source && original.xattrs == entry.xattrs,
                "hardlink identity differs from primary",
            )?;
        }
    }
    if let Some(k) = &manifest.kernel {
        ensure(
            k.complete_installed_tree && k.binding.release == manifest.target_kernel_release,
            "kernel content admission is incomplete",
        )?;
    }
    Ok(())
}

pub fn materialize(
    manifest: &Manifest,
    sha: &str,
    destination: &str,
    owner: u32,
) -> Result<Receipt> {
    validate(manifest)?;
    let source = Tree::open(&manifest.source_root, owner)?;
    let root = fs::stat(&source.root)?;
    ensure(
        root.dev == manifest.source_root_identity.dev
            && root.ino == manifest.source_root_identity.ino
            && root.mode == manifest.source_root_identity.mode
            && root.uid == manifest.source_root_identity.uid,
        "source root identity changed",
    )?;
    // A cheap complete identity preflight precedes the first destination mutation.
    for e in &manifest.entries {
        ensure(
            source.identity(&e.path)? == e.source,
            &format!("source changed after manifest capture: {}", e.path),
        )?;
    }
    if let Some(k) = &manifest.kernel {
        let (id, digest, _) = fs::read_regular(&source, &k.binding.image_path)?;
        ensure(
            id == k.image_identity && digest == k.binding.image_sha256,
            "selected kernel image changed",
        )?;
    }
    let dest = Tree::create(destination, owner)?;
    let mut dirs: Vec<_> = manifest
        .entries
        .iter()
        .filter(|x| x.content == Content::Directory)
        .collect();
    dirs.sort_by_key(|x| (x.path.matches('/').count(), x.path.as_str()));
    for e in &dirs {
        dest.mkdir(&e.path)?;
    }
    for e in &manifest.entries {
        match &e.content {
            Content::Regular { sha256 } => {
                fs::copy_regular(&source, &dest, &e.path, &e.source, sha256, &e.xattrs)?
            }
            Content::Hardlink { target, .. } => {
                ensure(
                    source.identity(&e.path)? == e.source,
                    "source hardlink changed during materialization",
                )?;
                dest.hardlink(&e.path, target)?;
            }
            Content::Symlink { target } => {
                let (id, link) = source.read_link(&e.path)?;
                ensure(
                    id == e.source && link == *target,
                    "source symlink changed during materialization",
                )?;
                dest.symlink(&e.path, target, &e.source)?;
            }
            Content::Directory => (),
        }
    }
    for e in dirs.iter().rev() {
        fs::set_metadata(&dest.dir(&e.path)?, &e.source, &e.xattrs)?;
    }
    rustix::fs::fsync(&dest.root)?;
    fs::assert_root_namespace(destination, &dest)?;
    fs::assert_root_namespace(&manifest.source_root, &source)?;
    verify(manifest, sha, destination, owner)
}

fn actual_paths(tree: &Tree, directory: Option<&str>, out: &mut BTreeSet<String>) -> Result<()> {
    // Root listing has the same descriptor-based semantics as other directories.
    let fd = match directory {
        Some(p) => tree.dir(p)?,
        None => tree.root.try_clone()?,
    };
    let mut dir = rustix::fs::Dir::read_from(&fd)?;
    let mut names = Vec::new();
    for e in &mut dir {
        let e = e?;
        let n = e.file_name().to_str()?;
        if n != "." && n != ".." {
            names.push(n.to_owned());
        }
    }
    for n in names {
        let p = format!("{}/{n}", directory.unwrap_or(""));
        ensure(out.insert(p.clone()), "duplicate directory listing entry")?;
        if rustix::fs::FileType::from_raw_mode(tree.identity(&p)?.mode)
            == rustix::fs::FileType::Directory
        {
            actual_paths(tree, Some(&p), out)?;
        }
    }
    Ok(())
}

pub fn verify(manifest: &Manifest, sha: &str, destination: &str, owner: u32) -> Result<Receipt> {
    validate(manifest)?;
    ensure(fs::valid_digest(sha), "invalid manifest digest")?;
    let tree = Tree::open(destination, owner)?;
    ensure(
        fs::stat(&tree.root)?.mode & 0o777 == 0o700,
        "fixture root must remain private",
    )?;
    let mut actual = BTreeSet::new();
    actual_paths(&tree, None, &mut actual)?;
    let expected: BTreeSet<_> = manifest.entries.iter().map(|e| e.path.clone()).collect();
    ensure(
        actual == expected,
        "fixture contains missing or unexpected paths",
    )?;
    let mut bytes = 0u64;
    let mut regular = 0usize;
    for e in &manifest.entries {
        let id = tree.identity(&e.path)?;
        ensure(
            fs::same_metadata(&id, &e.source),
            &format!("destination mode/type/ownership differs: {}", e.path),
        )?;
        match &e.content {
            Content::Directory => ensure(
                fs::xattrs(&tree.dir(&e.path)?)? == e.xattrs,
                "directory ACL differs",
            )?,
            Content::Symlink { target } => ensure(
                tree.read_link(&e.path)?.1 == *target,
                "symlink readback differs",
            )?,
            Content::Regular { sha256 } | Content::Hardlink { sha256, .. } => {
                let (id, hash, attrs) = fs::read_regular(&tree, &e.path)?;
                ensure(
                    id.size == e.source.size && hash == *sha256 && attrs == e.xattrs,
                    &format!(
                        "full destination content/privilege readback differs: {}",
                        e.path
                    ),
                )?;
                regular += 1;
                if let Content::Hardlink { target, .. } = &e.content {
                    let t = tree.identity(target)?;
                    ensure(
                        id.dev == t.dev && id.ino == t.ino,
                        "hardlink topology was not preserved",
                    )?;
                } else {
                    bytes += id.size;
                }
            }
        }
    }
    fs::assert_root_namespace(destination, &tree)?;
    Ok(Receipt {
        schema: RECEIPT_SCHEMA.into(),
        manifest_sha256: sha.into(),
        destination: destination.into(),
        destination_identity: fs::stat(&tree.root)?,
        entries_verified: manifest.entries.len(),
        regular_paths_verified: regular,
        unique_regular_bytes: bytes,
        target_kernel_release: manifest.target_kernel_release.clone(),
        kernel_modules_content_verified: manifest
            .kernel
            .as_ref()
            .is_some_and(|k| k.complete_installed_tree),
        materialization_complete: true,
        guest_qualified: false,
        unresolved_requirements: manifest.unresolved_requirements.clone(),
        unresolved_public_links: manifest.unresolved_public_links.clone(),
    })
}
