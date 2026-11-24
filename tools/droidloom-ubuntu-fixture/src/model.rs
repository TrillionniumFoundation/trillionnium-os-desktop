use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const SELECTION_SCHEMA: &str = "droidloom.ubuntu-public-selection.v1";
pub const MANIFEST_SCHEMA: &str = "droidloom.ubuntu-public-fixture-manifest.v1";
pub const RECEIPT_SCHEMA: &str = "droidloom.ubuntu-public-fixture-receipt.v1";

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Component {
    AncestorDirectory,
    Native,
    PublicConfig,
    GeneratedPublicCache,
    TargetModule,
    SnapArchive,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SelectedPath {
    pub path: String,
    pub component: Component,
    pub origin: String,
    #[serde(default)]
    pub expected_sha256: Option<String>,
    #[serde(default)]
    pub expected_size: Option<u64>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KernelBinding {
    pub release: String,
    pub image_path: String,
    pub image_sha256: String,
    pub config_path: String,
    pub config_sha256: String,
    pub module_manifest_path: String,
    pub module_manifest_sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub schema: String,
    pub source_root: String,
    pub audit_sha256: String,
    pub target_kernel_release: String,
    #[serde(default)]
    pub kernel: Option<KernelBinding>,
    pub entries: Vec<SelectedPath>,
    #[serde(default)]
    pub unresolved_requirements: Vec<String>,
}

/// Source identity is checked before and after every regular-file read.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Identity {
    pub dev: u64,
    pub ino: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub nlink: u64,
    pub size: u64,
    pub mtime_sec: i64,
    pub mtime_nsec: i64,
    pub ctime_sec: i64,
    pub ctime_nsec: i64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Content {
    Directory,
    Regular { sha256: String },
    Symlink { target: String },
    Hardlink { target: String, sha256: String },
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Entry {
    pub path: String,
    pub component: Component,
    pub origin: String,
    pub source: Identity,
    pub content: Content,
    /// Public privilege metadata only. SELinux labels belong to later policy admission.
    pub xattrs: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KernelResult {
    pub binding: KernelBinding,
    pub source_module_count: usize,
    pub source_index_count: usize,
    pub complete_installed_tree: bool,
    pub omitted_build_links: Vec<String>,
    pub image_identity: Identity,
    pub config_identity: Identity,
    /// This tool checks content identity; independent signature receipts remain distinct.
    pub signature_verification_performed: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: String,
    pub selection_sha256: String,
    pub audit_sha256: String,
    pub source_root: String,
    pub source_root_identity: Identity,
    pub target_kernel_release: String,
    pub kernel: Option<KernelResult>,
    pub entries: Vec<Entry>,
    pub unresolved_requirements: Vec<String>,
    pub unresolved_public_links: Vec<String>,
    pub guest_qualified: bool,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub schema: String,
    pub manifest_sha256: String,
    pub destination: String,
    pub destination_identity: Identity,
    pub entries_verified: usize,
    pub regular_paths_verified: usize,
    pub unique_regular_bytes: u64,
    pub target_kernel_release: String,
    pub kernel_modules_content_verified: bool,
    pub materialization_complete: bool,
    pub guest_qualified: bool,
    pub unresolved_requirements: Vec<String>,
    pub unresolved_public_links: Vec<String>,
}
