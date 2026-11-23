//! Closed input and output schemas. Content provenance is distinct from admission.
pub(crate) use crate::apex_inputs::ApexInput;
use crate::{Result, require};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Component, Path, PathBuf};

pub(crate) const MAX_PLAN: u64 = 1024 * 1024;
pub(crate) const MAX_CAPTURE: u64 = 4 * 1024 * 1024;
pub(crate) const MAX_CONFIG: u64 = 1024 * 1024;
pub(crate) const MAX_INPUT: u64 = 16 * 1024 * 1024 * 1024;
pub(crate) const IMAGE_BYTES_MIN: u64 = 32 * 1024 * 1024;
pub(crate) const IMAGE_BYTES_MAX: u64 = 256 * 1024 * 1024;
pub(crate) const IMAGE_PATHS: [&str; 8] = [
    "/",
    "/apex",
    "/linkerconfig",
    "/rc",
    "/rc/bootconfig",
    "/rc/cgroups.json",
    "/rc/init.rc",
    "/rc/task_profiles.json",
];
pub(crate) const RC_NAMES: [&str; 4] = [
    "bootconfig",
    "cgroups.json",
    "init.rc",
    "task_profiles.json",
];
pub(crate) const NATIVE_IMAGE_PATHS: [&str; 12] = [
    "/",
    "/apex",
    "/lib64",
    "/lib64/libprocessgroup.so",
    "/lib64/libprocessgroup_setup.so",
    "/linkerconfig",
    "/rc",
    "/rc/bootconfig",
    "/rc/cgroup-v2-policy.json",
    "/rc/cgroups.json",
    "/rc/init.rc",
    "/rc/task_profiles.json",
];
pub(crate) fn image_file(path: &str) -> Option<&str> {
    path.strip_prefix("/rc/").or_else(|| match path {
        "/lib64/libprocessgroup.so" => Some("libprocessgroup.so"),
        "/lib64/libprocessgroup_setup.so" => Some("libprocessgroup_setup.so"),
        _ => None,
    })
}
pub(crate) const ORIGINAL_RC: [(&str, &str); 3] = [
    ("cgroups.json", "/system/etc/cgroups.json"),
    ("init.rc", "/system/etc/init/hw/init.rc"),
    ("task_profiles.json", "/system/etc/task_profiles.json"),
];

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct FileRef {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
    // dev, ino, mode, uid, gid, nlink, bytes, mtime_ns, ctime_ns.
    // All JSON integers remain exact u64; no floating-point transport.
    pub f9: [u64; 9],
}
impl FileRef {
    pub fn validate(&self, maximum: u64) -> Result<()> {
        absolute(&self.path)?;
        require(
            self.bytes > 0
                && self.bytes <= maximum
                && digest(&self.sha256)
                && self.f9[2] & 0o170000 == 0o100000
                && self.f9[2] & 0o7022 == 0
                && self.f9[5] == 1
                && self.f9[6] == self.bytes,
            format!(
                "bounded immutable regular file reference: {}",
                self.path.display()
            ),
        )
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ImageDeclaration {
    pub file: String,
    pub bytes: u64,
    pub sha256: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct BaseDeclaration {
    pub schema: u32,
    pub scope: String,
    pub layout: String,
    pub system: ImageDeclaration,
    pub vendor: ImageDeclaration,
    #[serde(default)]
    pub system_ext_lib64: Option<droidloom_contracts::system_ext::Declaration>,
}
impl BaseDeclaration {
    pub fn validate(&self, plan: &BuildPlan) -> Result<()> {
        require(
            droidloom_contracts::system_ext::accepts(self.schema, &self.scope, self.system_ext_lib64.as_ref(), &self.system.sha256, &self.vendor.sha256)
                && self.layout == "gsi_system_as_root",
            "supported actual base declaration",
        )?;
        for (decl, file, name) in [
            (&self.system, &plan.system, "system.img"),
            (&self.vendor, &plan.vendor, "vendor.img"),
        ] {
            require(
                decl.file == name
                    && decl.bytes == file.bytes
                    && decl.sha256 == file.sha256
                    && decl.bytes >= 4096
                    && decl.bytes % 512 == 0,
                "base declaration and whole input images differ",
            )?;
        }
        match (&self.system_ext_lib64, &plan.system_ext_lib64) {
            (Some(decl),Some(file)) => require(file.path.file_name().and_then(|n|n.to_str())==Some(droidloom_contracts::system_ext::FILE)
                && file.bytes==decl.bytes && file.sha256==decl.sha256,"runtime plan differs from selected native bridge library image")?,
            (None,None) => (),
            _ => return Err("runtime plan and selected base have different extension roles".into()),
        }
        Ok(())
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Tools {
    pub mke2fs: FileRef,
    pub debugfs: FileRef,
    pub e2fsck: FileRef,
}
impl Tools {
    pub fn validate(&self) -> Result<()> {
        for (r, path) in [
            (&self.mke2fs, "/usr/sbin/mke2fs"),
            (&self.debugfs, "/usr/sbin/debugfs"),
            (&self.e2fsck, "/usr/sbin/e2fsck"),
        ] {
            r.validate(32 * 1024 * 1024)?;
            require(
                r.path == Path::new(path) && r.f9[3] == 0 && r.f9[4] == 0 && r.f9[2] & 0o111 != 0,
                "only fixed root-owned filesystem tool roles",
            )?;
        }
        Ok(())
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct BuildPlan {
    pub schema: String,
    pub base: FileRef,
    pub system: FileRef,
    pub vendor: FileRef,
    #[serde(default)]
    pub system_ext_lib64: Option<FileRef>,
    pub capture: FileRef,
    pub adapter: FileRef,
    pub tools: Tools,
    pub image_bytes: u64,
    pub epoch_seconds: u32,
    pub deadline_seconds: u64,
}
impl BuildPlan {
    pub fn validate(&self) -> Result<()> {
        require(
            self.schema == "droidloom-runtime-build-plan-v1",
            "closed build-plan schema",
        )?;
        for (r, maximum) in [
            (&self.base, MAX_PLAN),
            (&self.system, MAX_INPUT),
            (&self.vendor, MAX_INPUT),
            (&self.capture, MAX_CAPTURE),
            (&self.adapter, MAX_PLAN),
        ] {
            r.validate(maximum)?;
        }
        if let Some(extension)=&self.system_ext_lib64 { extension.validate(MAX_INPUT)?; }
        self.tools.validate()?;
        require(
            (IMAGE_BYTES_MIN..=IMAGE_BYTES_MAX).contains(&self.image_bytes)
                && self.image_bytes % 4096 == 0
                && (60..=1800).contains(&self.deadline_seconds)
                && self.epoch_seconds >= 1_230_768_000,
            "finite image, time and epoch bounds",
        )?;
        require(
            self.system.path != self.vendor.path && self.system.sha256 != self.vendor.sha256,
            "distinct actual system/vendor images",
        )?;
        Ok(())
    }
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct TextChange {
    pub before: String,
    pub after: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct AdaptedFile {
    pub content: FileRef,
    pub source_path: Option<String>,
    pub changes: Vec<TextChange>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ExecutionSelection {
    pub scope: String,
}
impl ExecutionSelection {
    pub fn validate_system(&self, system: &FileRef) -> Result<()> {
        require(
            self.scope == "android_cp3a_scoped_capabilities_v1"
                && system.bytes == 2_294_853_632
                && system.sha256
                    == "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4",
            "explicit execution profile requires the exact original CP3A system",
        )
    }
    pub fn validate_init(&self, init: &FileRef) -> Result<()> {
        require(
            self.scope == "android_cp3a_scoped_capabilities_v1"
                && init.bytes == 2_934_488
                && init.sha256
                    == "9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537",
            "explicit execution profile requires the exact original CP3A init",
        )
    }
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Adapter {
    pub schema: String,
    pub base_cohort_sha256: String,
    pub source_system_sha256: String,
    pub original_capture_sha256: String,
    // The actual review/source record is retained and hashed, never replaced
    // by a caller-supplied "reviewed", "activated" or "ready" boolean.
    pub provenance: FileRef,
    pub bootconfig_provenance: FileRef,
    pub files: BTreeMap<String, AdaptedFile>,
    pub selinux_contexts: BTreeMap<String, String>,
    #[serde(default)]
    pub native_v2: Option<crate::native::NativeInput>,
    #[serde(default)]
    pub execution: Option<ExecutionSelection>,
    #[serde(default)]
    pub activation: Option<crate::activation::ActivationInput>,
    #[serde(default)]
    pub query: Option<crate::query::QueryInput>,
}
impl Adapter {
    pub fn validate(&self, plan: &BuildPlan) -> Result<()> {
        require(
            ((self.schema == "droidloom-runtime-preinit-adapter-v1" && self.native_v2.is_none())
                || (self.schema == "droidloom-runtime-preinit-adapter-v2"
                    && self.native_v2.is_some()))
                && self.base_cohort_sha256 == plan.base.sha256
                && self.source_system_sha256 == plan.system.sha256
                && self.original_capture_sha256 == plan.capture.sha256,
            "adapter must bind this actual base, system and capture",
        )?;
        self.provenance.validate(MAX_PLAN)?;
        self.bootconfig_provenance.validate(MAX_PLAN)?;
        if let Some(execution) = &self.execution {
            require(
                self.native_v2.is_some(),
                "execution selection requires the native v2 adapter",
            )?;
            execution.validate_system(&plan.system)?;
        }
        if let Some(activation) = &self.activation {
            require(
                self.execution.is_some(),
                "fixed activation inputs require the explicit CP3A execution selection",
            )?;
            activation.validate()?;
        }
        if let Some(query) = &self.query {
            require(
                self.execution.is_some(),
                "fixed query inputs require the explicit CP3A execution selection",
            )?;
            query.validate(&plan.system)?;
        }
        require(
            self.files.keys().map(String::as_str).eq(RC_NAMES),
            "exact four adapter files",
        )?;
        require(
            self.selinux_contexts
                .keys()
                .map(String::as_str)
                .eq(self.image_paths().iter().copied()),
            "explicit labels for the exact declared image inodes",
        )?;
        for (path, context) in &self.selinux_contexts {
            require(
                label(context),
                format!("bounded exact object context at {path}"),
            )?;
        }
        for (name, file) in &self.files {
            file.content.validate(MAX_CONFIG)?;
            require(
                file.changes.len() <= 128,
                "bounded explicit source transformations",
            )?;
            if name == "bootconfig" {
                require(
                    file.source_path.is_none() && file.changes.is_empty(),
                    "bootconfig is an explicit provenance-bound input, not an invented image path",
                )?;
            } else {
                let source = ORIGINAL_RC
                    .iter()
                    .find(|(n, _)| n == name)
                    .ok_or("unknown adapter role")?
                    .1;
                require(
                    file.source_path.as_deref() == Some(source),
                    "adapter source is the fixed original Android file",
                )?;
            }
        }
        Ok(())
    }
    pub fn image_paths(&self) -> &'static [&'static str] {
        if self.native_v2.is_some() {
            &NATIVE_IMAGE_PATHS
        } else {
            &IMAGE_PATHS
        }
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct RuntimeDeclaration {
    pub schema: u32,
    pub scope: &'static str,
    pub base_cohort_sha256: String,
    pub source_system: ImageDeclaration,
    pub runtime_image: ImageDeclaration,
    pub init: ImageDeclaration,
    pub init_source_path: &'static str,
    pub init_interpreter: Option<String>,
    pub original_rc_inventory_sha256: String,
    pub reviewed_adapter_sha256: String,
    pub runtime_tree_inventory_sha256: String,
    pub apexes: Vec<ApexInput>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub native_v2: Option<crate::native::NativeDeclaration>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub execution: Option<ExecutionSelection>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub activation: Option<crate::activation::ActivationDeclaration>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub query: Option<crate::query::QueryDeclaration>,
    // Actual input declarations never assert execution or application permission.
}

pub(crate) fn digest(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
pub(crate) fn absolute(path: &Path) -> Result<()> {
    require(
        path.is_absolute()
            && path
                .components()
                .all(|c| matches!(c, Component::RootDir | Component::Normal(_))),
        "absolute normalized input path",
    )?;
    let s = path.to_str().ok_or("UTF-8 input path required")?;
    require(
        s.len() <= 4096
            && !s
                .bytes()
                .any(|c| c < 32 || c == 127 || c == b'"' || c == b'\\'),
        "path cannot carry filesystem-tool command syntax",
    )
}
pub(crate) fn label(s: &str) -> bool {
    s.strip_prefix("u:object_r:")
        .and_then(|v| v.strip_suffix(":s0"))
        .is_some_and(|v| {
            !v.is_empty()
                && v.len() <= 96
                && v.bytes()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_')
        })
}
pub(crate) fn safe_module_name(name: &str) -> bool {
    (3..=128).contains(&name.len())
        && !name.starts_with('.')
        && !name.ends_with('.')
        && !name.contains("..")
        && name.contains('.')
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
}
pub(crate) fn apply_changes(original: &[u8], changes: &[TextChange]) -> Result<Vec<u8>> {
    let mut text = std::str::from_utf8(original)?.to_owned();
    require(!text.contains('\0'), "original configuration contains NUL")?;
    for change in changes {
        require(
            !change.before.is_empty()
                && !change.before.contains('\0')
                && !change.after.contains('\0')
                && text.match_indices(&change.before).count() == 1,
            "each explicit adapter preimage must match exactly once",
        )?;
        text = text.replacen(&change.before, &change.after, 1);
        require(
            text.len() as u64 <= MAX_CONFIG,
            "adapted configuration size",
        )?;
    }
    require(
        !text.trim().is_empty(),
        "empty adapter configuration is not a runtime input",
    )?;
    Ok(text.into_bytes())
}
pub(crate) fn validate_apexes(apexes: &[ApexInput]) -> Result<()> {
    require(
        (1..=128).contains(&apexes.len()),
        "nonempty bounded actual APEX inventory",
    )?;
    let mut seen = BTreeSet::new();
    let mut previous: Option<&str> = None;
    for a in apexes {
        require(
            safe_module_name(&a.name)
                && a.version > 0
                && previous.is_none_or(|p| p < a.name.as_str())
                && seen.insert(a.container_file.as_str())
                && [format!("{}.apex", a.name), format!("{}.capex", a.name)]
                    .contains(&a.container_file),
            "sorted unique actual APEX identities",
        )?;
        for (n, hash) in [
            (a.container_bytes, &a.container_sha256),
            (a.original_apex_bytes, &a.original_apex_sha256),
            (a.payload_bytes, &a.payload_sha256),
        ] {
            require(
                (4096..=MAX_INPUT).contains(&n) && digest(hash),
                "bounded APEX lineage",
            )?;
        }
        if a.container_file.ends_with(".apex") {
            require(
                a.container_bytes == a.original_apex_bytes
                    && a.container_sha256 == a.original_apex_sha256,
                "uncompressed original APEX identity",
            )?;
        }
        previous = Some(&a.name);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn explicit_execution_selection_rejects_other_images_and_unknown_authority_fields() {
        let profile = ExecutionSelection {
            scope: "android_cp3a_scoped_capabilities_v1".into(),
        };
        let mut system = FileRef {
            path: "/ordinary-schema-fixture/system.img".into(),
            bytes: 2_294_853_632,
            sha256: "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4".into(),
            f9: [0; 9],
        };
        let mut init = FileRef {
            path: "/ordinary-schema-fixture/init".into(),
            bytes: 2_934_488,
            sha256: "9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537".into(),
            f9: [0; 9],
        };
        // This exercises only declarative selection. The invalid fixture F9
        // cannot pass FileRef validation, byte rechecks, or runtime preparation.
        assert!(system.validate(MAX_INPUT).is_err());
        assert!(init.validate(MAX_INPUT).is_err());
        profile.validate_system(&system).unwrap();
        profile.validate_init(&init).unwrap();
        for scope in ["", "android_cp2a_scoped_capabilities_v1", "host_sys_admin"] {
            let wrong = ExecutionSelection {
                scope: scope.into(),
            };
            assert!(wrong.validate_system(&system).is_err());
            assert!(wrong.validate_init(&init).is_err());
        }
        for field in ["capabilities", "mask", "qualified", "host_sys_admin"] {
            let mut value = serde_json::to_value(&profile).unwrap();
            value[field] = serde_json::json!(true);
            assert!(serde_json::from_value::<ExecutionSelection>(value).is_err());
        }
        system.bytes += 512;
        assert!(profile.validate_system(&system).is_err());
        system.bytes -= 512;
        system.sha256 = "0".repeat(64);
        assert!(profile.validate_system(&system).is_err());
        init.bytes += 1;
        assert!(profile.validate_init(&init).is_err());
        init.bytes -= 1;
        init.sha256 = "0".repeat(64);
        assert!(profile.validate_init(&init).is_err());
    }

    #[test]
    fn changed_source_is_rejected_before_any_image_operation() {
        let changes = [TextChange {
            before: "import /old.rc".into(),
            after: "import /new.rc".into(),
        }];
        assert_eq!(
            apply_changes(b"import /old.rc\n", &changes).unwrap(),
            b"import /new.rc\n"
        );
        assert!(apply_changes(b"import /different.rc\n", &changes).is_err());
        assert!(apply_changes(b"import /old.rc\nimport /old.rc\n", &changes).is_err());
        assert!(apply_changes(b"a\0b", &[]).is_err());
        assert!(apply_changes(b"\n", &[]).is_err());
    }
    #[test]
    fn paths_and_labels_cannot_inject_tool_commands_or_escape() {
        for path in ["/a/../b", "/a\nmkdir /x", "/a\\b", "/a\"b", "relative"] {
            assert!(absolute(Path::new(path)).is_err(), "{path}");
        }
        assert!(absolute(Path::new("/data/fixed input")).is_ok());
        assert!(label("u:object_r:system_file:s0"));
        for value in [
            "u:r:init:s0",
            "u:object_r:system_file:s0\0",
            "u:object_r:x:s0:c1",
            "unlabeled",
        ] {
            assert!(!label(value));
        }
    }
    #[test]
    fn empty_duplicate_or_reordered_apex_claims_fail() {
        let one = ApexInput {
            name: "com.android.runtime".into(),
            version: 1,
            container_file: "com.android.runtime.apex".into(),
            container_bytes: 4096,
            container_sha256: "1".repeat(64),
            original_apex_bytes: 4096,
            original_apex_sha256: "1".repeat(64),
            payload_bytes: 4096,
            payload_sha256: "2".repeat(64),
        };
        assert!(validate_apexes(&[one.clone()]).is_ok());
        assert!(validate_apexes(&[]).is_err());
        assert!(validate_apexes(&[one.clone(), one.clone()]).is_err());
        let mut wrong = one;
        wrong.original_apex_sha256 = "3".repeat(64);
        assert!(validate_apexes(&[wrong]).is_err());
    }
}
