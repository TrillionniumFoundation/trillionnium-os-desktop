//! One fixed working-qualification layout shared by cold publication and live readers.
//! These names and labels are comparisons. Possession of a pathname, label or
//! serialized pin cannot construct a working owner or an accepted capture.
use std::path::{Path, PathBuf};

pub const WORKING_QUALIFICATION_BASE: &str = "/var/lib/droidloom/qualification";
pub const WORKING_CANDIDATE_PREFIX: &str = "working-qualification-";
pub const WORKING_INPUT_DIRECTORY: &str = "inputs";
pub const WORKING_EVIDENCE_DIRECTORY: &str = "runtime-evidence";
pub const WORKING_BOOT_EVIDENCE_DIRECTORY: &str = "boot-evidence";
pub const WORKING_RETURN_EVIDENCE_DIRECTORY: &str = "return";
pub const WORKING_BOOT_EVIDENCE_DIRECTORY_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_boot_evidence_dir_t:s0";
pub const WORKING_RETURN_EVIDENCE_DIRECTORY_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_return_evidence_dir_t:s0";
pub const WORKING_RETURN_EVIDENCE_FILE_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_return_evidence_t:s0";
pub const WORKING_SOURCE_LOCK_LABEL: &[u8] = b"u:object_r:p4_linux_working_source_lock_t:s0";
pub const WORKING_RETURN_LOCK_LABEL: &[u8] = b"u:object_r:p4_linux_working_return_lock_t:s0";
pub const WORKING_ADMITTED_MATERIALS_FILE: &str = "ADMITTED-MATERIALS.json";
/// Exact ordered roles in current_public_materials.documents.
pub const WORKING_APPLICATION_INPUT_FILES: [&str; 4] = [
    "application-selection.json",
    "application-signatures.json",
    "application-import.json",
    "application-input-verification.json",
];
pub const WORKING_GATE_REGISTRY_FILE: &str = "gate-registry.json";
pub const WORKING_PLAN_FILE: &str = "PLAN.json";
pub const WORKING_RUNTIME_PLAN_FILE: &str = "RUNTIME-PLAN.json";
pub const WORKING_CAPTURE_FILE: &str = "CAPTURE.json";
pub const WORKING_MAIN_BINDING_FILE: &str = "MAIN-BINDING.json";
pub const WORKING_NATIVE_BASELINES_DIRECTORY: &str = "native-baselines";
pub const WORKING_NATIVE_INPUTS_DIRECTORY: &str = "native-inputs";
pub const WORKING_NATIVE_CASES_DIRECTORY: &str = "native-cases";
pub const WORKING_NATIVE_CLAIMS_DIRECTORY: &str = "native-claims";

pub const WORKING_PARENT_ROLE: &[u8] = b"u:system_r:p4_linux_working_qualification_t:s0";
pub const WORKING_SUITE_ROLE: &[u8] = b"u:system_r:p4_linux_working_suite_t:s0";
pub const WORKING_RETURN_ROLE: &[u8] = b"u:system_r:p4_linux_working_return_t:s0";
pub const WORKING_LEAF_ROLE: &[u8] = b"u:system_r:p4_linux_working_leaf_t:s0";
pub const WORKING_PARENT_PROFILE: &[u8] = b"droidloom-working-qualification (enforce)";
pub const WORKING_SUITE_PROFILE: &[u8] = b"droidloom-working-suite (enforce)";
pub const WORKING_RETURN_PROFILE: &[u8] = b"droidloom-working-return (enforce)";
pub const WORKING_LEAF_PROFILE: &[u8] = b"droidloom-working-leaf (enforce)";
/// Fixed common ancestor; installed through the normal H2 host label roster.
pub const WORKING_ROOT_DIRECTORY_LABEL: &[u8] = b"u:object_r:p4_linux_working_root_dir_t:s0";
pub const WORKING_CANDIDATE_DIRECTORY_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_candidate_dir_t:s0";
pub const WORKING_INPUT_DIRECTORY_LABEL: &[u8] = b"u:object_r:p4_linux_working_inputs_dir_t:s0";
pub const WORKING_INPUT_FILE_LABEL: &[u8] = b"u:object_r:p4_linux_working_input_t:s0";
pub const WORKING_EVIDENCE_DIRECTORY_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_evidence_dir_t:s0";
pub const WORKING_NATIVE_BASELINES_DIRECTORY_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_baselines_dir_t:s0";
pub const WORKING_NATIVE_INPUTS_DIRECTORY_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_native_inputs_dir_t:s0";
pub const WORKING_NATIVE_CASES_DIRECTORY_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_cases_dir_t:s0";
pub const WORKING_NATIVE_CLAIMS_DIRECTORY_LABEL: &[u8] =
    b"u:object_r:p4_linux_working_claims_dir_t:s0";
pub const WORKING_NATIVE_CLAIM_FILE_LABEL: &[u8] = b"u:object_r:p4_linux_working_claim_t:s0";
pub const WORKING_PLAN_FILE_LABEL: &[u8] = b"u:object_r:p4_linux_working_plan_t:s0";
pub const WORKING_RUNTIME_PLAN_FILE_LABEL: &[u8] = b"u:object_r:p4_linux_working_runtime_plan_t:s0";
pub const WORKING_CAPTURE_FILE_LABEL: &[u8] = b"u:object_r:p4_linux_working_capture_t:s0";
pub const WORKING_MAIN_BINDING_FILE_LABEL: &[u8] = b"u:object_r:p4_linux_working_main_binding_t:s0";
pub const WORKING_APPLICATION_OUTPUT_LABEL: &[u8] = b"u:object_r:p4_linux_working_output_t:s0";

fn candidate_id(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
}
/// Construct a comparison path only; live admission still authenticates the boot.
pub fn working_candidate_directory(candidate: &str) -> Option<PathBuf> {
    candidate_id(candidate).then(|| {
        Path::new(WORKING_QUALIFICATION_BASE).join(format!("{WORKING_CANDIDATE_PREFIX}{candidate}"))
    })
}
pub(crate) fn fixed_plan_path(path: &Path) -> bool {
    let Some(candidate) = path.parent().and_then(Path::parent) else {
        return false;
    };
    let Some(id) = candidate
        .file_name()
        .and_then(|v| v.to_str())
        .and_then(|v| v.strip_prefix(WORKING_CANDIDATE_PREFIX))
    else {
        return false;
    };
    working_candidate_directory(id).is_some_and(|root| {
        path.as_os_str()
            == root
                .join(WORKING_EVIDENCE_DIRECTORY)
                .join(WORKING_PLAN_FILE)
                .as_os_str()
    })
}
pub(crate) fn preparation_directory_label(name: &str) -> Option<&'static [u8]> {
    match name {
        WORKING_NATIVE_BASELINES_DIRECTORY => Some(WORKING_NATIVE_BASELINES_DIRECTORY_LABEL),
        WORKING_NATIVE_INPUTS_DIRECTORY => Some(WORKING_NATIVE_INPUTS_DIRECTORY_LABEL),
        WORKING_NATIVE_CASES_DIRECTORY => Some(WORKING_NATIVE_CASES_DIRECTORY_LABEL),
        _ => None,
    }
}
pub(crate) fn parent_output_label(name: &str) -> Option<&'static [u8]> {
    match name {
        WORKING_CAPTURE_FILE => Some(WORKING_CAPTURE_FILE_LABEL),
        WORKING_MAIN_BINDING_FILE => Some(WORKING_MAIN_BINDING_FILE_LABEL),
        "applications.stdout" | "applications.stderr" => Some(WORKING_APPLICATION_OUTPUT_LABEL),
        _ => None,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn physical_working_layout_rejects_aliases_and_cold_private_roots() {
        let root = working_candidate_directory(&"a".repeat(64)).unwrap();
        let plan = root
            .join(WORKING_EVIDENCE_DIRECTORY)
            .join(WORKING_PLAN_FILE);
        assert!(fixed_plan_path(&plan));
        for path in [
            PathBuf::from("/PLAN.json"),
            root.join(WORKING_PLAN_FILE),
            root.join("boot-evidence/PLAN.json"),
            PathBuf::from("/var/lib/droidloom-qualification")
                .join(format!("working-qualification-{}", "a".repeat(64)))
                .join("runtime-evidence/PLAN.json"),
            PathBuf::from(format!(
                "{}/runtime-evidence/../runtime-evidence/PLAN.json",
                root.display()
            )),
        ] {
            assert!(!fixed_plan_path(&path), "{}", path.display());
        }
        for id in [
            "",
            "../caller",
            &"A".repeat(64),
            &"a".repeat(63),
            &"a".repeat(65),
        ] {
            assert!(working_candidate_directory(id).is_none());
        }
    }
    #[test]
    fn physical_working_layout_separates_parent_evidence_and_leaf_writable_trees() {
        let mut labels = std::collections::BTreeSet::new();
        for label in [
            WORKING_EVIDENCE_DIRECTORY_LABEL,
            WORKING_NATIVE_BASELINES_DIRECTORY_LABEL,
            WORKING_NATIVE_INPUTS_DIRECTORY_LABEL,
            WORKING_NATIVE_CASES_DIRECTORY_LABEL,
            WORKING_NATIVE_CLAIMS_DIRECTORY_LABEL,
        ] {
            assert!(labels.insert(label));
        }
        for name in [
            WORKING_NATIVE_BASELINES_DIRECTORY,
            WORKING_NATIVE_INPUTS_DIRECTORY,
            WORKING_NATIVE_CASES_DIRECTORY,
        ] {
            assert_ne!(
                preparation_directory_label(name).unwrap(),
                WORKING_EVIDENCE_DIRECTORY_LABEL
            );
        }
        for name in [
            WORKING_EVIDENCE_DIRECTORY,
            WORKING_NATIVE_CLAIMS_DIRECTORY,
            WORKING_CAPTURE_FILE,
            "../native-cases",
        ] {
            assert!(preparation_directory_label(name).is_none());
        }
        for name in [
            WORKING_PLAN_FILE,
            WORKING_RUNTIME_PLAN_FILE,
            "native-cases/result.json",
            "../CAPTURE.json",
        ] {
            assert!(parent_output_label(name).is_none());
        }
        assert_ne!(
            parent_output_label(WORKING_CAPTURE_FILE),
            parent_output_label("applications.stdout")
        );
    }
}
