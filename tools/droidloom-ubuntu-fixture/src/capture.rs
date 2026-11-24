use crate::fs::{self, Tree};
use crate::model::*;
use crate::paths;
use crate::{Result, ensure};
use rustix::fs::FileType;
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
struct ModuleSource {
    schema: String,
    release: String,
    count: usize,
    rows: Vec<ModuleRow>,
    indexes: Vec<ModuleRow>,
}
#[derive(Deserialize)]
struct ModuleRow {
    relative: String,
    sha256: String,
    bytes: u64,
}

fn insert(map: &mut BTreeMap<String, SelectedPath>, item: SelectedPath) -> Result<()> {
    if let Some(old) = map.get(&item.path) {
        ensure(
            old.component == item.component
                && old.expected_sha256 == item.expected_sha256
                && old.expected_size == item.expected_size,
            "conflicting duplicate selection",
        )?;
    } else {
        map.insert(item.path.clone(), item);
    }
    Ok(())
}

fn module_tree(
    tree: &Tree,
    path: &str,
    regular: &mut BTreeSet<String>,
    omitted: &mut Vec<String>,
) -> Result<()> {
    for name in tree.list(path)? {
        let child = format!("{path}/{name}");
        let s = tree.identity(&child)?;
        match FileType::from_raw_mode(s.mode) {
            FileType::Directory => module_tree(tree, &child, regular, omitted)?,
            FileType::RegularFile => {
                regular.insert(child);
            }
            FileType::Symlink
                if ["build", "source"].contains(&name.as_str()) && !path.contains("/kernel/") =>
            {
                // Only names and inode metadata: never follow build trees or signing keys.
                omitted.push(child);
            }
            _ => return Err(format!("unexpected module-tree inode: {child}").into()),
        }
    }
    Ok(())
}

fn admit_kernel(
    selection: &Selection,
    tree: &Tree,
    selected: &mut BTreeMap<String, SelectedPath>,
) -> Result<Option<KernelResult>> {
    let Some(binding) = &selection.kernel else {
        return Ok(None);
    };
    ensure(
        binding.release == selection.target_kernel_release,
        "kernel release differs from selection",
    )?;
    ensure(
        binding.image_path == format!("/boot/vmlinuz-{}", binding.release),
        "kernel image must be the exact selected native boot image",
    )?;
    let prefix = format!("/usr/lib/modules/{}", binding.release);
    ensure(
        binding.config_path == format!("{prefix}/config-{}", binding.release),
        "kernel config path differs from selected module release",
    )?;
    let proof: ModuleSource = fs::read_json(
        &binding.module_manifest_path,
        &binding.module_manifest_sha256,
    )?;
    ensure(
        proof.schema == "p4-normal-kernel-installed-module-manifest-v1"
            && proof.release == binding.release,
        "module producer identity mismatch",
    )?;
    ensure(
        proof.count == proof.rows.len() && proof.count > 0,
        "module roster count mismatch",
    )?;
    let (image_id, image_sha, _) = fs::read_regular(tree, &binding.image_path)?;
    ensure(
        image_sha == binding.image_sha256,
        "selected kernel image hash mismatch",
    )?;
    let (config_id, config_sha, _) = fs::read_regular(tree, &binding.config_path)?;
    ensure(
        config_sha == binding.config_sha256,
        "selected kernel config hash mismatch",
    )?;
    let mut expected = BTreeSet::new();
    for row in proof.rows.iter().chain(proof.indexes.iter()) {
        let path = format!("{prefix}/{}", row.relative);
        paths::validate(&path, &Component::TargetModule, &binding.release)?;
        ensure(
            fs::valid_digest(&row.sha256) && expected.insert(path.clone()),
            "invalid or duplicate module/index binding",
        )?;
        insert(
            selected,
            SelectedPath {
                path,
                component: Component::TargetModule,
                origin: format!("module-producer-sha256:{}", binding.module_manifest_sha256),
                expected_sha256: Some(row.sha256.clone()),
                expected_size: Some(row.bytes),
            },
        )?;
    }
    ensure(
        expected.insert(binding.config_path.clone()),
        "producer unexpectedly duplicates config binding",
    )?;
    insert(
        selected,
        SelectedPath {
            path: binding.config_path.clone(),
            component: Component::TargetModule,
            origin: "selected-kernel-config".into(),
            expected_sha256: Some(binding.config_sha256.clone()),
            expected_size: Some(config_id.size),
        },
    )?;
    let mut actual = BTreeSet::new();
    let mut omitted = Vec::new();
    module_tree(tree, &prefix, &mut actual, &mut omitted)?;
    ensure(
        actual == expected,
        &format!(
            "installed module tree differs from producer roster: extra={}, missing={}",
            actual.difference(&expected).count(),
            expected.difference(&actual).count()
        ),
    )?;
    Ok(Some(KernelResult {
        binding: binding.clone(),
        source_module_count: proof.rows.len(),
        source_index_count: proof.indexes.len(),
        complete_installed_tree: true,
        omitted_build_links: omitted,
        image_identity: image_id,
        config_identity: config_id,
        signature_verification_performed: false,
    }))
}

pub fn capture(selection: Selection, selection_sha: &str, owner: u32) -> Result<Manifest> {
    ensure(
        selection.schema == SELECTION_SCHEMA,
        "selection schema mismatch",
    )?;
    ensure(
        fs::valid_digest(selection_sha) && fs::valid_digest(&selection.audit_sha256),
        "selection/audit digest is invalid",
    )?;
    let release = &selection.target_kernel_release;
    ensure(
        release.starts_with("6.18.")
            && release
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b".-_".contains(&b)),
        "target must explicitly select the 6.18 kernel family",
    )?;
    let source = Tree::open(&selection.source_root, owner)?;
    let root_identity = fs::stat(&source.root)?;
    let mut selected = BTreeMap::new();
    for item in &selection.entries {
        paths::validate(&item.path, &item.component, release)?;
        ensure(
            !item.origin.trim().is_empty(),
            "selected input lacks provenance",
        )?;
        if matches!(
            item.component,
            Component::PublicConfig | Component::GeneratedPublicCache | Component::SnapArchive
        ) {
            ensure(
                item.expected_sha256
                    .as_deref()
                    .is_some_and(fs::valid_digest),
                "reviewed configuration/cache/snap input requires its exact digest",
            )?;
        }
        if let Some(sha) = &item.expected_sha256 {
            ensure(fs::valid_digest(sha), "invalid selected digest")?;
        }
        ensure(
            item.component != Component::TargetModule,
            "module files must come from separate producer admission",
        )?;
        insert(&mut selected, item.clone())?;
    }
    let kernel = admit_kernel(&selection, &source, &mut selected)?;
    let all_paths: Vec<_> = selected.keys().cloned().collect();
    for p in all_paths {
        let mut parent = paths::parent(&p);
        while parent != "/" {
            selected
                .entry(parent.to_owned())
                .or_insert_with(|| SelectedPath {
                    path: parent.to_owned(),
                    component: Component::AncestorDirectory,
                    origin: "public-input-ancestor-directory".into(),
                    expected_sha256: None,
                    expected_size: None,
                });
            parent = paths::parent(parent);
        }
    }
    let mut entries = Vec::new();
    let mut hardlinks: BTreeMap<(u64, u64), (String, Identity, String, BTreeMap<String, String>)> =
        BTreeMap::new();
    for item in selected.values() {
        paths::validate(&item.path, &item.component, release)?;
        let before = source.identity(&item.path)?;
        let (content, attrs, content_sha) = match FileType::from_raw_mode(before.mode) {
            FileType::Directory => {
                let fd = source.dir(&item.path)?;
                ensure(fs::stat(&fd)? == before, "directory identity changed")?;
                (Content::Directory, fs::xattrs(&fd)?, None)
            }
            FileType::RegularFile => {
                ensure(
                    item.component != Component::AncestorDirectory,
                    "ancestor entry is not a directory",
                )?;
                if let Some((target, identity, sha, attrs)) =
                    hardlinks.get(&(before.dev, before.ino))
                {
                    let fd = source.file(&item.path)?;
                    ensure(
                        fs::stat(&fd)? == *identity
                            && before == *identity
                            && fs::xattrs(&fd)? == *attrs,
                        "hardlinked source changed",
                    )?;
                    (
                        Content::Hardlink {
                            target: target.clone(),
                            sha256: sha.clone(),
                        },
                        attrs.clone(),
                        Some(sha.clone()),
                    )
                } else {
                    let (id, sha, attrs) = fs::read_regular(&source, &item.path)?;
                    ensure(id == before, "source changed before hash")?;
                    hardlinks.insert(
                        (id.dev, id.ino),
                        (item.path.clone(), id, sha.clone(), attrs.clone()),
                    );
                    (
                        Content::Regular {
                            sha256: sha.clone(),
                        },
                        attrs,
                        Some(sha),
                    )
                }
            }
            FileType::Symlink => {
                ensure(
                    !matches!(
                        item.component,
                        Component::AncestorDirectory
                            | Component::SnapArchive
                            | Component::TargetModule
                    ),
                    "component cannot be a symlink",
                )?;
                let (id, target) = source.read_link(&item.path)?;
                ensure(id == before, "symlink changed before read")?;
                paths::normalize_link(&item.path, &target)?;
                let sha = fs::digest(target.as_bytes());
                (Content::Symlink { target }, BTreeMap::new(), Some(sha))
            }
            _ => return Err(format!("special input is forbidden: {}", item.path).into()),
        };
        if let Some(expected) = &item.expected_sha256 {
            ensure(
                content_sha.as_ref() == Some(expected),
                &format!("reviewed input hash mismatch: {}", item.path),
            )?;
        }
        if let Some(expected) = item.expected_size {
            ensure(before.size == expected, "reviewed input size mismatch")?;
        }
        ensure(
            source.identity(&item.path)? == before,
            "source changed during capture",
        )?;
        entries.push(Entry {
            path: item.path.clone(),
            component: item.component.clone(),
            origin: item.origin.clone(),
            source: before,
            content,
            xattrs: attrs,
        });
    }
    let names: BTreeSet<_> = entries.iter().map(|x| x.path.clone()).collect();
    let mut unresolved_public_links = Vec::new();
    for entry in &entries {
        if let Content::Symlink { target } = &entry.content {
            let absolute = paths::normalize_link(&entry.path, target)?;
            if !names.contains(&absolute) {
                unresolved_public_links.push(format!("{} -> {}", entry.path, absolute));
            }
        }
    }
    let mut unmet = selection.unresolved_requirements;
    unmet.extend([
        "Fresh fixture accounts, shadow/gshadow and service UID/GID mapping via distribution tools",
        "Fresh machine-id, hostname, hosts, fstab and DNS/network configuration",
        "Fresh SSH host keys and an explicitly authorized fixture login identity",
        "Distribution cache generation, sysusers, tmpfiles and synthetic API mounts",
        "Joined SELinux labels, service/user roles, PAM login contexts and enforcing qualification",
        "Native AppArmor and Snap profile generation for the selected 6.18 feature ABI",
        "Fresh Snap state and independently verified public assertion import",
        "Actual GDM/Wayland/DBus/NetworkManager/SSH/audio service and login qualification",
        "Actual selected-kernel DRM/input/network/audio/Bluetooth device qualification",
    ].map(str::to_owned));
    if kernel.is_none() {
        unmet.push(
            "Selected target-kernel image/config/complete module provenance is missing".into(),
        );
    }
    unmet.sort();
    unmet.dedup();
    fs::assert_root_namespace(&selection.source_root, &source)?;
    Ok(Manifest {
        schema: MANIFEST_SCHEMA.into(),
        selection_sha256: selection_sha.into(),
        audit_sha256: selection.audit_sha256,
        source_root: selection.source_root,
        source_root_identity: root_identity,
        target_kernel_release: selection.target_kernel_release,
        kernel,
        entries,
        unresolved_requirements: unmet,
        unresolved_public_links,
        guest_qualified: false,
    })
}
