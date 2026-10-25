//! Verify the compiled original-SDK patch contract independently of fonts.
use super::Entry;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::io::Read;
use std::path::{Component, Path};
#[cfg(not(feature = "hepta-native-preedit-sdk"))]
use trill_ui_core::shared_chat::native_presentation::NATIVE_SDK_NOTICE_MANIFEST_JSON;
#[cfg(feature = "hepta-native-preedit-sdk")]
const NATIVE_SDK_NOTICE_MANIFEST_JSON: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../support/ui/preedit-sdk/NATIVE-SDK-PATCH.json"
));
#[cfg(feature = "hepta-native-preedit-sdk")]
const SDK_PATCH: &str = "native-preedit-callbacks.patch";
#[cfg(feature = "hepta-native-preedit-sdk")]
const SDK_UI_FEATURE: &str = "native-presentation";
#[cfg(not(feature = "hepta-native-preedit-sdk"))]
const SDK_PATCH: &str = "native-clipboard-read.patch";
#[cfg(not(feature = "hepta-native-preedit-sdk"))]
const SDK_UI_FEATURE: &str = "native-clipboard-sdk";

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Inventory {
    schema: String,
    upstream_repository: String,
    upstream_revision: String,
    patched_tree: String,
    source_manifest_sha256: String,
    files: Vec<Entry>,
}

#[derive(Deserialize)]
struct Profile {
    schema: String,
    #[serde(default)]
    sdk_profile: Option<String>,
    #[serde(default)]
    upstream_tree: Option<String>,
    native_ui_feature: String,
    upstream_repository: String,
    upstream_commit: String,
    patched_tree: String,
    manifest_sha256: String,
    source_tree_verified: bool,
    all_sdk_packages_same_tree: bool,
    dependency_edges_verified: bool,
    effects_authority: bool,
    resolved_packages: Vec<Package>,
}

#[derive(Deserialize)]
struct Package {
    name: String,
    version: String,
    manifest: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Bundle {
    makepad_source: String,
    sdk_source_profile_sha256: String,
    sdk_notice_inventory_sha256: String,
    sdk_notices: usize,
}

fn read(root: &Path, name: &str, limit: u64) -> Result<Vec<u8>, String> {
    let path = root.join(name);
    let metadata = path.symlink_metadata().map_err(|error| error.to_string())?;
    if !metadata.is_file() || metadata.len() > limit {
        return Err(format!("Invalid SDK evidence file: {name}"));
    }
    let mut bytes = Vec::new();
    std::fs::File::open(path)
        .map_err(|error| error.to_string())?
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    if bytes.len() as u64 > limit {
        return Err("SDK evidence exceeds its bound".into());
    }
    Ok(bytes)
}

pub(super) fn verify(root: &Path) -> Result<(), String> {
    let inventory: Inventory =
        serde_json::from_str(NATIVE_SDK_NOTICE_MANIFEST_JSON).map_err(|error| error.to_string())?;
    let expected_files: BTreeSet<_> = [
        "LICENSE-MIT",
        "MANIFEST.json",
        SDK_PATCH,
        "sdk-num-traits-path.patch",
        "README.md",
    ]
    .into_iter()
    .map(|name| format!("dependency-notices/makepad/{name}"))
    .collect();
    if inventory.schema != "hepta.native-sdk-notices.v1"
        || inventory.upstream_revision != "337566c8b25d47f7e4fff6a202157b65bf183330"
        || inventory.files.len() != 5
        || inventory
            .files
            .iter()
            .map(|entry| entry.path.clone())
            .collect::<BTreeSet<_>>()
            != expected_files
    {
        return Err("Unsupported compiled SDK source contract".into());
    }
    let expected_digest = format!(
        "{:x}",
        Sha256::digest(NATIVE_SDK_NOTICE_MANIFEST_JSON.as_bytes())
    );
    super::verify(
        root,
        &Entry {
            path: "NATIVE-SDK-PATCH.json".into(),
            bytes: NATIVE_SDK_NOTICE_MANIFEST_JSON.len() as u64,
            sha256: expected_digest.clone(),
        },
    )?;
    for entry in &inventory.files {
        super::verify(root, entry)?;
    }
    let bundle: Bundle = serde_json::from_slice(&read(root, "bundle.json", 128 * 1024)?)
        .map_err(|error| error.to_string())?;
    let profile_bytes = read(root, "NATIVE-SDK-SOURCE.json", 1024 * 1024)?;
    if bundle.makepad_source
        != format!(
            "prepared+{}#{}",
            inventory.upstream_repository, inventory.patched_tree
        )
        || bundle.sdk_notice_inventory_sha256 != expected_digest
        || bundle.sdk_notices != 5
        || bundle.sdk_source_profile_sha256 != format!("{:x}", Sha256::digest(&profile_bytes))
    {
        return Err("SDK source evidence differs from its compiled contract".into());
    }
    let profile: Profile =
        serde_json::from_slice(&profile_bytes).map_err(|error| error.to_string())?;
    if profile.schema != "hepta.verified-original-sdk-source.v1"
        || profile.native_ui_feature != SDK_UI_FEATURE
        || profile.upstream_repository != inventory.upstream_repository
        || profile.upstream_commit != inventory.upstream_revision
        || profile.patched_tree != inventory.patched_tree
        || profile.manifest_sha256 != inventory.source_manifest_sha256
        || !profile.source_tree_verified
        || !profile.all_sdk_packages_same_tree
        || !profile.dependency_edges_verified
        || profile.effects_authority
        || !(5..=256).contains(&profile.resolved_packages.len())
    {
        return Err("SDK source was not verified against the original prepared tree".into());
    }
    if cfg!(feature = "hepta-native-preedit-sdk")
        && (profile.sdk_profile.as_deref() != Some("preedit-callbacks")
            || profile.upstream_tree.as_deref() != Some("c6e18be7754f9634492ec5251bac3e8b4f7e09b7"))
    {
        return Err("Preedit source profile differs from its compiled contract".into());
    }
    if !cfg!(feature = "hepta-native-preedit-sdk")
        && profile
            .sdk_profile
            .as_deref()
            .is_some_and(|name| name != "clipboard")
    {
        return Err("Clipboard source profile differs from its compiled contract".into());
    }
    let mut identities = BTreeSet::new();
    for package in &profile.resolved_packages {
        if package.name.is_empty()
            || package.name.len() > 100
            || package.version.is_empty()
            || package.version.len() > 100
            || !package.manifest.ends_with("/Cargo.toml")
            || package.manifest.contains(['\\', '\0'])
            || !Path::new(&package.manifest)
                .components()
                .all(|part| matches!(part, Component::Normal(_)))
            || !identities.insert((&package.name, &package.version))
        {
            return Err("Invalid SDK package identity or source path".into());
        }
    }
    for (name, manifest) in [
        ("makepad-widgets", "widgets/Cargo.toml"),
        ("makepad-draw", "draw/Cargo.toml"),
        ("makepad-platform", "platform/Cargo.toml"),
        ("makepad-script", "platform/script/Cargo.toml"),
    ] {
        if !profile
            .resolved_packages
            .iter()
            .any(|package| package.name == name && package.manifest == manifest)
        {
            return Err(format!("Original SDK package missing: {name}"));
        }
    }
    if !profile
        .resolved_packages
        .iter()
        .any(|package| package.name == "unicode-segmentation")
    {
        return Err("Original SDK grapheme package missing".into());
    }
    Ok(())
}
