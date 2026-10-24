//! Verify the original inventory before the SDK opens a native window.
#[cfg(feature = "hepta-native-clipboard-sdk")]
mod sdk;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::io::Read;
use std::path::{Component, Path};
use trill_ui_core::shared_chat::native_presentation::{
    NATIVE_DEPENDENCY_NOTICE_MANIFEST_JSON, NATIVE_RESOURCE_MANIFEST_JSON,
};

#[derive(Deserialize)]
struct Inventory {
    schema: String,
    #[serde(rename = "makepadRevision")]
    makepad_revision: String,
    assets: Vec<Entry>,
    #[serde(rename = "noticeFileSha256")]
    notices: Vec<Entry>,
    #[serde(rename = "liberationSource")]
    liberation_source: Entry,
}

#[derive(Deserialize)]
struct Entry {
    #[serde(alias = "logical", alias = "file")]
    path: String,
    bytes: u64,
    sha256: String,
}

#[derive(Deserialize)]
struct DependencyInventory {
    schema: String,
    #[serde(rename = "upstreamRevision")]
    upstream_revision: String,
    files: Vec<Entry>,
}

pub(super) fn verified_root() -> Result<String, String> {
    let path = std::env::var_os("TRILL_UI_MAKEPAD_RESOURCES")
        .ok_or("TRILL_UI_MAKEPAD_RESOURCES must name the prepared original resource bundle")?;
    let root = Path::new(&path)
        .canonicalize()
        .map_err(|error| format!("Makepad resource directory: {error}"))?;
    if !root.is_dir() {
        return Err("Makepad resources must be a directory".into());
    }
    let inventory: Inventory = serde_json::from_str(NATIVE_RESOURCE_MANIFEST_JSON)
        .map_err(|error| format!("Original Makepad inventory: {error}"))?;
    if inventory.schema != "hepta.native-embedded-assets.v1"
        || inventory.makepad_revision != "337566c8b25d47f7e4fff6a202157b65bf183330"
        || inventory.assets.len() != 29
        || inventory.notices.len() != 15
    {
        return Err(
            "Unsupported original Makepad inventory; rebuild the matching resource bundle".into(),
        );
    }
    for entry in inventory.assets.iter().chain(&inventory.notices) {
        verify(&root, entry)?;
    }
    let source = Entry {
        path: format!("sources/{}", inventory.liberation_source.path),
        ..inventory.liberation_source
    };
    verify(&root, &source)?;
    let dependencies: DependencyInventory =
        serde_json::from_str(NATIVE_DEPENDENCY_NOTICE_MANIFEST_JSON)
            .map_err(|error| format!("Native dependency notices: {error}"))?;
    if dependencies.schema != "hepta.native-dependency-notices.v1"
        || dependencies.upstream_revision != "405d578cdfd8496ee79020d24cfaac8c29a8a48f"
        || dependencies.files.len() != 6
    {
        return Err("Unsupported native dependency notice inventory".into());
    }
    verify(
        &root,
        &Entry {
            path: "NATIVE-DEPENDENCIES.json".into(),
            bytes: NATIVE_DEPENDENCY_NOTICE_MANIFEST_JSON.len() as u64,
            sha256: format!(
                "{:x}",
                Sha256::digest(NATIVE_DEPENDENCY_NOTICE_MANIFEST_JSON.as_bytes())
            ),
        },
    )?;
    for entry in &dependencies.files {
        if !entry.path.starts_with("dependency-notices/accesskit/") {
            return Err("Invalid native dependency notice path".into());
        }
        verify(&root, entry)?;
    }
    #[cfg(feature = "hepta-native-clipboard-sdk")]
    sdk::verify(&root)?;
    root.into_os_string()
        .into_string()
        .map_err(|_| "Makepad resource directory must be UTF-8".into())
}

fn verify(root: &Path, entry: &Entry) -> Result<(), String> {
    if !Path::new(&entry.path)
        .components()
        .all(|part| matches!(part, Component::Normal(_)))
    {
        return Err(format!("Invalid resource path: {}", entry.path));
    }
    let path = root.join(&entry.path);
    let metadata = path
        .symlink_metadata()
        .map_err(|error| format!("Missing original resource {}: {error}", entry.path))?;
    if !metadata.is_file()
        || metadata.len() != entry.bytes
        || !path
            .canonicalize()
            .map_err(|error| error.to_string())?
            .starts_with(root)
    {
        return Err(format!(
            "Original resource type/length mismatch: {}",
            entry.path
        ));
    }
    let mut file = std::fs::File::open(&path).map_err(|error| error.to_string())?;
    let mut hash = Sha256::new();
    let mut buffer = [0; 64 * 1024];
    loop {
        let size = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if size == 0 {
            break;
        }
        hash.update(&buffer[..size]);
    }
    if format!("{:x}", hash.finalize()) != entry.sha256 {
        return Err(format!("Original resource SHA256 mismatch: {}", entry.path));
    }
    Ok(())
}
