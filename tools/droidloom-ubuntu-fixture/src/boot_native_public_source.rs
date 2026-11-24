//! Pinned public inputs imported from a normal native plan, never host secrets.
//! The original plan fixes each source name and byte digest. A relocated name
//! is valid only below one held, protected qualification input directory.
use super::{PUBLIC_CONFIGS, PublicConfigInput, SNAP_NAMES};
use crate::{
    Result,
    boot::NativePlan,
    boot_files::{self, FilePin},
    ensure, fs, paths,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Read,
    path::{Path, PathBuf},
};

const QUALIFICATION: &str = "/var/lib/droidloom-qualification";

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ImportedPublicInputs {
    pub original_native_plan: FilePin,
    pub directory: PathBuf,
}

struct ImportedCustody {
    declaration: ImportedPublicInputs,
    tree: fs::Tree,
    originals: BTreeMap<PathBuf, FilePin>,
    package_sources: BTreeMap<PathBuf, FilePin>,
    fixture_manifest_sha256: String,
}

/// Constructed only by reading the pinned original plan and opening its
/// protected import directory. This grants no runtime or qualification status.
pub struct PublicInputCustody {
    imported: Option<ImportedCustody>,
}

fn import_parent(directory: &Path) -> Result<&Path> {
    let parent = directory.parent().ok_or("missing public import parent")?;
    ensure(
        directory.file_name().is_some_and(|name| name == "inputs")
            && parent.parent() == Some(Path::new(QUALIFICATION)),
        "public input directory must be a fixed inputs child of isolated qualification work",
    )?;
    let name = parent
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or("invalid public import work name")?;
    ensure(
        !name.is_empty()
            && name.len() <= 96
            && name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b)),
        "invalid public import work name",
    )?;
    paths::parts(&fs::absolute_string(directory)?)?;
    Ok(parent)
}

fn same_bytes(first: &FilePin, second: &FilePin) -> bool {
    first.bytes == second.bytes && first.sha256 == second.sha256 && fs::valid_digest(&first.sha256)
}

fn bind_pin(
    originals: &mut BTreeMap<PathBuf, FilePin>,
    directory: &Path,
    original: &FilePin,
    relocated: &FilePin,
) -> Result<()> {
    let name = fs::absolute_string(&original.path)?;
    let parts = paths::parts(&name)?;
    ensure(
        !parts.is_empty()
            && original.bytes <= 1024 * 1024
            && same_bytes(original, relocated)
            && relocated.path == directory.join(parts.join("/")),
        "imported public input differs from its original fixed path or bytes",
    )?;
    ensure(
        originals
            .insert(relocated.path.clone(), original.clone())
            .is_none(),
        "duplicate imported public input",
    )
}

fn bind_configs(
    originals: &mut BTreeMap<PathBuf, FilePin>,
    directory: &Path,
    original: &[PublicConfigInput],
    relocated: &[PublicConfigInput],
    snaps: bool,
) -> Result<()> {
    let expected = if snaps {
        SNAP_NAMES.len()
    } else {
        PUBLIC_CONFIGS.len()
    };
    ensure(
        original.len() == expected && relocated.len() == expected,
        "imported public configuration set differs from its original plan",
    )?;
    let mut selected = BTreeMap::new();
    for input in relocated {
        ensure(
            selected.insert(input.guest_path.as_str(), input).is_none(),
            "duplicate relocated public configuration",
        )?;
    }
    let mut seen = BTreeSet::new();
    for input in original {
        let guest = input.guest_path.as_str();
        ensure(
            input.mode == 0o644
                && input.input.path == Path::new(guest)
                && seen.insert(guest)
                && if snaps {
                    guest.starts_with("/etc/systemd/system/snap-") && guest.ends_with(".mount")
                } else {
                    PUBLIC_CONFIGS.contains(&guest)
                },
            "original plan has an unreviewed public source path",
        )?;
        let copied = selected.get(guest).ok_or("original public input omitted")?;
        ensure(
            copied.mode == input.mode,
            "relocated public input mode differs",
        )?;
        bind_pin(originals, directory, &input.input, &copied.input)?;
    }
    Ok(())
}

fn bind_original(
    original: &NativePlan,
    current: &NativePlan,
    directory: &Path,
) -> Result<BTreeMap<PathBuf, FilePin>> {
    ensure(
        original.schema == "droidloom.ubuntu-native-boot-plan.v1"
            && original.imported_public_inputs.is_none()
            && original.fixture_root.is_absolute()
            && original.fixture_root != Path::new("/")
            && original.work_directory.parent() == Some(Path::new(QUALIFICATION))
            && same_bytes(&original.fixture_manifest, &current.fixture_manifest),
        "imported public inputs require one original native plan bound to this public manifest",
    )?;
    let source = &original.native;
    let selected = &current.native;
    ensure(
        source.public_passwd.path == Path::new("/etc/passwd")
            && source.public_group.path == Path::new("/etc/group"),
        "original account input paths differ",
    )?;
    let mut originals = BTreeMap::new();
    for (original, relocated) in [
        (&source.public_passwd, &selected.public_passwd),
        (&source.public_group, &selected.public_group),
        (&source.alias_receipt, &selected.alias_receipt),
    ] {
        bind_pin(&mut originals, directory, original, relocated)?;
    }
    bind_configs(
        &mut originals,
        directory,
        &source.public_configs,
        &selected.public_configs,
        false,
    )?;
    bind_configs(
        &mut originals,
        directory,
        &source.snap_mounts,
        &selected.snap_mounts,
        true,
    )?;
    Ok(originals)
}

fn relocated_pin(original: &FilePin, directory: &Path, limit: u64) -> Result<FilePin> {
    let name = fs::absolute_string(&original.path)?;
    let parts = paths::parts(&name)?;
    ensure(
        !parts.is_empty() && original.bytes <= limit && fs::valid_digest(&original.sha256),
        "invalid bounded original public package pin",
    )?;
    Ok(FilePin {
        path: directory.join(parts.join("/")),
        bytes: original.bytes,
        sha256: original.sha256.clone(),
    })
}

fn bind_public_packages(
    original: Option<&FilePin>,
    selected: Option<&FilePin>,
    tree: &fs::Tree,
    directory: &Path,
    originals: &mut BTreeMap<PathBuf, FilePin>,
) -> Result<BTreeMap<PathBuf, FilePin>> {
    let (original, selected) = match (original, selected) {
        (None, None) => return Ok(BTreeMap::new()),
        (Some(original), Some(selected)) => (original, selected),
        _ => return Err("public package selection differs from original native plan".into()),
    };
    let copied = relocated_pin(original, directory, 8 * 1024 * 1024)?;
    ensure(
        copied.path == selected.path
            && same_bytes(original, selected)
            && originals
                .insert(selected.path.clone(), original.clone())
                .is_none(),
        "public package declaration must be the unchanged fixed import of the original plan",
    )?;
    let packages: crate::boot_packages::PublicPackages =
        serde_json::from_slice(&read_imported(tree, directory, selected, 8 * 1024 * 1024)?)?;
    ensure(
        packages.schema == "droidloom.ubuntu-public-packages.v1"
            && !packages.packages.is_empty()
            && packages.packages.len() <= 64,
        "unsupported original public package declaration",
    )?;
    let mut sources = BTreeMap::<PathBuf, FilePin>::new();
    let mut add = |pin: &FilePin, limit: u64| -> Result<()> {
        let copied = relocated_pin(pin, directory, limit)?;
        if let Some(previous) = sources.get(&pin.path) {
            ensure(
                previous.path == copied.path && same_bytes(previous, &copied),
                "conflicting original public package pins",
            )?;
        } else {
            sources.insert(pin.path.clone(), copied);
        }
        Ok(())
    };
    add(&packages.dependency_audit, 8 * 1024 * 1024)?;
    for package in &packages.packages {
        add(&package.archive, 128 * 1024 * 1024)?;
        add(&package.provenance, 8 * 1024 * 1024)?;
    }
    Ok(sources)
}

fn read_imported(tree: &fs::Tree, directory: &Path, pin: &FilePin, limit: u64) -> Result<Vec<u8>> {
    ensure(
        pin.bytes <= limit && fs::valid_digest(&pin.sha256),
        "invalid bounded imported public pin",
    )?;
    let relative = pin
        .path
        .strip_prefix(directory)
        .map_err(|_| "public input escaped its held import directory")?;
    let guest = format!(
        "/{}",
        relative.to_str().ok_or("non-UTF8 public import path")?
    );
    ensure(
        !paths::parts(&guest)?.is_empty(),
        "public input cannot name its root",
    )?;
    let directory_name = fs::absolute_string(directory)?;
    fs::assert_root_namespace(&directory_name, tree)?;
    ensure(
        fs::stat(&tree.root)?.mode & 0o7777 == 0o700,
        "public input directory is no longer private",
    )?;
    let mut input = tree.file(&guest)?;
    let before = fs::stat(&input)?;
    ensure(
        before.size == pin.bytes && before.nlink == 1,
        "imported public input size or link count differs",
    )?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut input)
        .take(limit + 1)
        .read_to_end(&mut bytes)?;
    ensure(
        bytes.len() as u64 == pin.bytes
            && fs::digest(&bytes) == pin.sha256
            && fs::stat(&input)? == before
            && tree.identity(&guest)? == before,
        "imported public input changed or its digest differs",
    )?;
    fs::assert_root_namespace(&directory_name, tree)?;
    Ok(bytes)
}

impl PublicInputCustody {
    pub fn acquire(plan: &NativePlan) -> Result<Self> {
        let Some(declaration) = &plan.imported_public_inputs else {
            return Ok(Self { imported: None });
        };
        let parent = import_parent(&declaration.directory)?;
        ensure(
            !declaration.directory.starts_with(&plan.work_directory)
                && !plan.work_directory.starts_with(&declaration.directory)
                && !declaration.directory.starts_with(&plan.fixture_root)
                && !plan.fixture_root.starts_with(&declaration.directory),
            "public inputs must be independent of native work and the materialized root",
        )?;
        fs::Tree::open(QUALIFICATION, 0)?;
        let parent_tree = fs::Tree::open(&fs::absolute_string(parent)?, 0)?;
        ensure(
            fs::stat(&parent_tree.root)?.mode & 0o7777 == 0o700,
            "public import work is not private",
        )?;
        let tree = fs::Tree::open(&fs::absolute_string(&declaration.directory)?, 0)?;
        let bytes = read_imported(
            &tree,
            &declaration.directory,
            &declaration.original_native_plan,
            1024 * 1024,
        )?;
        let original: NativePlan = serde_json::from_slice(&bytes)?;
        let mut originals = bind_original(&original, plan, &declaration.directory)?;
        let package_sources = bind_public_packages(
            original.public_packages.as_ref(),
            plan.public_packages.as_ref(),
            &tree,
            &declaration.directory,
            &mut originals,
        )?;
        Ok(Self {
            imported: Some(ImportedCustody {
                declaration: declaration.clone(),
                tree,
                originals,
                package_sources,
                fixture_manifest_sha256: plan.fixture_manifest.sha256.clone(),
            }),
        })
    }

    pub fn original_pin<'a>(&'a self, pin: &'a FilePin) -> Result<&'a FilePin> {
        match &self.imported {
            None => Ok(pin),
            Some(imported) => {
                let original = imported
                    .originals
                    .get(&pin.path)
                    .ok_or("public input absent from original pinned native plan")?;
                ensure(
                    same_bytes(original, pin),
                    "public input pin changed after binding",
                )?;
                Ok(original)
            }
        }
    }

    pub fn original_config(&self, input: &PublicConfigInput) -> Result<PublicConfigInput> {
        Ok(PublicConfigInput {
            input: self.original_pin(&input.input)?.clone(),
            guest_path: input.guest_path.clone(),
            mode: input.mode,
        })
    }

    pub fn read_pin(&self, pin: &FilePin, limit: u64) -> Result<Vec<u8>> {
        self.original_pin(pin)?;
        match &self.imported {
            None => boot_files::read_pin(pin, limit),
            Some(imported) => {
                read_imported(&imported.tree, &imported.declaration.directory, pin, limit)
            }
        }
    }

    fn package_pin<'a>(&'a self, pin: &'a FilePin) -> Result<&'a FilePin> {
        match &self.imported {
            None => Ok(pin),
            Some(imported) => {
                let copied = imported
                    .package_sources
                    .get(&pin.path)
                    .ok_or("package input absent from unchanged original declaration")?;
                ensure(
                    same_bytes(copied, pin),
                    "original public package pin differs",
                )?;
                Ok(copied)
            }
        }
    }

    /// Read an original declaration's name through its unique fixed import.
    /// Provenance continues to compare the original name in the unchanged JSON.
    pub fn read_package_pin(&self, original: &FilePin, limit: u64) -> Result<Vec<u8>> {
        let actual = self.package_pin(original)?;
        match &self.imported {
            None => boot_files::read_pin(actual, limit),
            Some(imported) => read_imported(
                &imported.tree,
                &imported.declaration.directory,
                actual,
                limit,
            ),
        }
    }

    pub fn copy_package(&self, original: &FilePin, destination: &Path) -> Result<FilePin> {
        let actual = self.package_pin(original)?.clone();
        match &self.imported {
            None => boot_files::copy_pin(&actual, destination, 0o400)?,
            Some(_) => {
                let bytes = self.read_package_pin(original, 128 * 1024 * 1024)?;
                boot_files::write_new(destination, &bytes, 0o400)?;
            }
        }
        Ok(actual)
    }

    pub fn evidence(&self) -> Value {
        match &self.imported {
            None => json!({"mode":"local_fixed_paths"}),
            Some(imported) => json!({
                "mode":"imported_original_public_inputs",
                "original_native_plan":imported.declaration.original_native_plan,
                "directory":imported.declaration.directory,
                "fixture_manifest_sha256":imported.fixture_manifest_sha256,
                "bound_public_inputs":imported.originals.len(),
                "bound_package_inputs":imported.package_sources.len(),
                "runtime_authority_issued":false,
                "guest_qualified":false
            }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::NativeInputs;
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn pin(path: &str) -> FilePin {
        FilePin {
            path: path.into(),
            bytes: 6,
            sha256: fs::digest(b"public"),
        }
    }

    fn original_plan() -> NativePlan {
        let config = |path: &str| PublicConfigInput {
            input: pin(path),
            guest_path: path.into(),
            mode: 0o644,
        };
        NativePlan {
            schema: "droidloom.ubuntu-native-boot-plan.v1".into(),
            work_directory: format!("{QUALIFICATION}/source-native").into(),
            fixture_manifest: pin("/public/MANIFEST.json"),
            fixture_root: "/public/root".into(),
            public_packages: None,
            imported_public_inputs: None,
            native: NativeInputs {
                public_passwd: pin("/etc/passwd"),
                public_group: pin("/etc/group"),
                alias_receipt: pin("/public/ALIASES.json"),
                public_configs: PUBLIC_CONFIGS.iter().map(|path| config(path)).collect(),
                snap_mounts: SNAP_NAMES
                    .iter()
                    .map(|name| {
                        config(&format!(
                            "/etc/systemd/system/snap-{}-1.mount",
                            name.replace('-', "\\x2d")
                        ))
                    })
                    .collect(),
                hostname: "isolated".into(),
                username: "alex".into(),
                uid: 1000,
                gid: 1000,
                root_filesystem_uuid: "f752fbea-fb44-4b0a-a7d2-7732637087dc".into(),
                network_connection_uuid: "ba1985c9-1d8c-412a-b5f7-a44ee523d928".into(),
                generate_fixture_ssh: false,
            },
        }
    }

    fn relocated(original: &NativePlan, directory: &Path) -> Result<NativePlan> {
        let mut current: NativePlan = serde_json::from_value(serde_json::to_value(original)?)?;
        for pin in [
            &mut current.native.public_passwd,
            &mut current.native.public_group,
            &mut current.native.alias_receipt,
        ] {
            pin.path = directory.join(pin.path.strip_prefix("/")?);
        }
        for input in current
            .native
            .public_configs
            .iter_mut()
            .chain(current.native.snap_mounts.iter_mut())
        {
            input.input.path = directory.join(input.input.path.strip_prefix("/")?);
        }
        current.fixture_manifest.path = "/imported/MANIFEST.json".into();
        Ok(current)
    }

    #[test]
    fn imported_plan_binds_all_public_pins_to_same_manifest_and_fixed_names() -> Result<()> {
        let directory = Path::new("/var/lib/droidloom-qualification/import-test/inputs");
        let original = original_plan();
        let mut current = relocated(&original, directory)?;
        assert_eq!(bind_original(&original, &current, directory)?.len(), 19);
        current.fixture_manifest.sha256 = fs::digest(b"another manifest");
        assert!(bind_original(&original, &current, directory).is_err());
        let mut current = relocated(&original, directory)?;
        current.native.public_passwd.sha256 = fs::digest(b"changed account");
        assert!(bind_original(&original, &current, directory).is_err());
        let mut current = relocated(&original, directory)?;
        current.native.snap_mounts[0].input.path = "/etc/systemd/system/elsewhere.mount".into();
        assert!(bind_original(&original, &current, directory).is_err());
        let mut current = relocated(&original, directory)?;
        current.native.public_configs[0].guest_path = "/etc/shadow".into();
        assert!(bind_original(&original, &current, directory).is_err());
        Ok(())
    }

    #[test]
    fn imported_plan_rejects_chains_duplicates_private_sources_and_path_escape() -> Result<()> {
        let directory = Path::new("/var/lib/droidloom-qualification/import-test/inputs");
        let mut original = original_plan();
        let current = relocated(&original, directory)?;
        original.imported_public_inputs = Some(ImportedPublicInputs {
            original_native_plan: pin("/another/plan.json"),
            directory: directory.into(),
        });
        assert!(bind_original(&original, &current, directory).is_err());
        let mut original = original_plan();
        original.native.public_passwd.path = "/etc/shadow".into();
        assert!(bind_original(&original, &current, directory).is_err());
        let mut original = original_plan();
        original.native.public_configs[1] = original.native.public_configs[0].clone();
        assert!(bind_original(&original, &current, directory).is_err());
        let mut original = original_plan();
        original.native.alias_receipt.path = "/public/../secret.json".into();
        assert!(bind_original(&original, &current, directory).is_err());
        for bad in [
            "/",
            "/etc/inputs",
            "/var/lib/droidloom-qualification/inputs",
            "/var/lib/droidloom-qualification/a/../inputs",
            "/var/lib/droidloom-qualification/a/root",
        ] {
            assert!(import_parent(Path::new(bad)).is_err());
        }
        Ok(())
    }

    #[test]
    fn imported_reads_hold_original_directory_and_reject_replacement_alias_and_changes()
    -> Result<()> {
        let temp = tempfile::tempdir()?;
        let directory = temp.path().join("inputs");
        std::fs::create_dir(&directory)?;
        std::fs::set_permissions(&directory, std::fs::Permissions::from_mode(0o700))?;
        let path = directory.join("public");
        std::fs::write(&path, b"public")?;
        let pin = boot_files::pin_file(&path)?;
        let tree = fs::Tree::open(
            &fs::absolute_string(&directory)?,
            rustix::process::geteuid().as_raw(),
        )?;
        assert_eq!(read_imported(&tree, &directory, &pin, 1024)?, b"public");
        std::fs::write(&path, b"change")?;
        assert!(read_imported(&tree, &directory, &pin, 1024).is_err());
        std::fs::remove_file(&path)?;
        let external = temp.path().join("external");
        std::fs::write(&external, b"public")?;
        std::os::unix::fs::symlink(&external, &path)?;
        assert!(read_imported(&tree, &directory, &pin, 1024).is_err());
        std::fs::remove_file(&path)?;
        std::fs::write(&path, b"public")?;
        std::fs::hard_link(&path, temp.path().join("other-link"))?;
        assert!(read_imported(&tree, &directory, &pin, 1024).is_err());
        std::fs::remove_file(temp.path().join("other-link"))?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o666))?;
        assert!(read_imported(&tree, &directory, &pin, 1024).is_err());
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644))?;
        std::fs::rename(&directory, temp.path().join("old-inputs"))?;
        std::fs::create_dir(&directory)?;
        std::fs::set_permissions(&directory, std::fs::Permissions::from_mode(0o700))?;
        std::fs::write(directory.join("public"), b"public")?;
        assert!(read_imported(&tree, &directory, &pin, 1024).is_err());
        Ok(())
    }

    #[test]
    fn imported_reads_reject_outside_path_and_digest_before_using_content() -> Result<()> {
        let directory = tempfile::tempdir()?;
        std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o700))?;
        let tree = fs::Tree::open(
            &fs::absolute_string(directory.path())?,
            rustix::process::geteuid().as_raw(),
        )?;
        assert!(read_imported(&tree, directory.path(), &pin("/etc/passwd"), 1024).is_err());
        let mut invalid = pin("/etc/shadow");
        invalid.sha256 = "caller assertion".into();
        assert!(read_imported(&tree, directory.path(), &invalid, 1024).is_err());
        Ok(())
    }
    #[test]
    fn imported_packages_preserve_original_declaration_and_copy_only_its_pins() -> Result<()> {
        let temp = tempfile::tempdir()?;
        let directory = temp.path().join("inputs");
        std::fs::create_dir(&directory)?;
        std::fs::set_permissions(&directory, std::fs::Permissions::from_mode(0o700))?;
        std::fs::create_dir(directory.join("intake"))?;
        let make = |name: &str, bytes: &[u8]| -> Result<FilePin> {
            let path = directory.join("intake").join(name);
            std::fs::write(&path, bytes)?;
            Ok(FilePin {
                path: PathBuf::from("/intake").join(name),
                bytes: bytes.len() as u64,
                sha256: fs::digest(bytes),
            })
        };
        let archive = make("package.deb", b"public archive")?;
        let provenance_bytes = serde_json::to_vec(&json!({
            "host_install":false, "files":[{
                "package":"example","version":"1","bytes":archive.bytes,
                "sha256":archive.sha256,"path":archive.path,
            }],
        }))?;
        let provenance = make("INTAKE.json", &provenance_bytes)?;
        let audit = make("DEPENDENCIES.json", b"{}")?;
        let declaration = crate::boot_packages::PublicPackages {
            schema: "droidloom.ubuntu-public-packages.v1".into(),
            packages: vec![crate::boot_packages::PackageInput {
                package: "example".into(),
                version: "1".into(),
                architecture: "amd64".into(),
                archive: archive.clone(),
                provenance: provenance.clone(),
            }],
            retained_originals: vec![],
            dependency_audit: audit,
        };
        let declared_bytes = serde_json::to_vec(&declaration)?;
        let original_manifest = make("PUBLIC-PACKAGES.json", &declared_bytes)?;
        let copied_manifest = relocated_pin(&original_manifest, &directory, 8 * 1024 * 1024)?;
        let tree = fs::Tree::open(
            &fs::absolute_string(&directory)?,
            rustix::process::geteuid().as_raw(),
        )?;
        let mut originals = BTreeMap::new();
        let package_sources = bind_public_packages(
            Some(&original_manifest),
            Some(&copied_manifest),
            &tree,
            &directory,
            &mut originals,
        )?;
        let custody = PublicInputCustody {
            imported: Some(ImportedCustody {
                declaration: ImportedPublicInputs {
                    original_native_plan: pin("/unused/original-plan.json"),
                    directory: directory.clone(),
                },
                tree,
                originals,
                package_sources,
                fixture_manifest_sha256: fs::digest(b"manifest"),
            }),
        };
        assert_eq!(
            custody.read_pin(&copied_manifest, 8 * 1024 * 1024)?,
            declared_bytes
        );
        assert_eq!(
            custody.read_package_pin(&provenance, 8 * 1024 * 1024)?,
            provenance_bytes
        );
        let actual = custody.copy_package(&archive, &temp.path().join("copied.deb"))?;
        assert_eq!(actual.path, directory.join("intake/package.deb"));
        assert_eq!(
            std::fs::read(temp.path().join("copied.deb"))?,
            b"public archive"
        );
        assert!(custody.read_package_pin(&pin("/etc/shadow"), 1024).is_err());
        let mut changed = archive.clone();
        changed.sha256 = fs::digest(b"caller replacement");
        assert!(
            custody
                .copy_package(&changed, &temp.path().join("rejected.deb"))
                .is_err()
        );
        let imported = custody.imported.as_ref().unwrap();
        let mut changed_manifest = copied_manifest.clone();
        changed_manifest.sha256 = fs::digest(b"edited declaration");
        assert!(
            bind_public_packages(
                Some(&original_manifest),
                Some(&changed_manifest),
                &imported.tree,
                &directory,
                &mut BTreeMap::new(),
            )
            .is_err()
        );
        std::fs::write(&copied_manifest.path, b"replacement declaration")?;
        assert!(
            bind_public_packages(
                Some(&original_manifest),
                Some(&copied_manifest),
                &imported.tree,
                &directory,
                &mut BTreeMap::new(),
            )
            .is_err()
        );
        Ok(())
    }
}
