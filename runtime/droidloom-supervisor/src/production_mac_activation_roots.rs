//! Same loaded-policy epoch decisions for the two original directory labels
//! on the three fixed activation roots.
//! These checks do not load or alter policy. The mount provider separately
//! creates and verifies fresh detached tmpfs inodes before changing labels.

use super::*;

const TMPFS: &str = "u:object_r:tmpfs:s0";
const ROOTS: [&str; 2] = [
    "u:object_r:apex_mnt_dir:s0",
    "u:object_r:linkerconfig_file:s0",
];

pub(super) fn required(root: &File, sequence: &mut Option<u32>) -> Result<()> {
    access(
        root,
        BROKER,
        TMPFS,
        "filesystem",
        &["mount", "getattr"],
        true,
        sequence,
    )?;
    access(
        root,
        BROKER,
        TMPFS,
        "dir",
        &["getattr", "search", "read", "open", "relabelfrom"],
        true,
        sequence,
    )?;
    for label in ROOTS {
        access(
            root,
            BROKER,
            label,
            "dir",
            &["getattr", "search", "read", "open", "relabelto"],
            true,
            sequence,
        )?;
        access(
            root,
            label,
            TMPFS,
            "filesystem",
            &["associate"],
            true,
            sequence,
        )?;
        // A root directory permission must not become permission to change
        // original executable/data inodes bearing either existing label.
        access(
            root,
            BROKER,
            label,
            "file",
            &[
                "write",
                "append",
                "create",
                "setattr",
                "relabelfrom",
                "relabelto",
                "execute",
                "entrypoint",
            ],
            false,
            sequence,
        )?;
        access(
            root,
            BROKER,
            label,
            "dir",
            &["relabelfrom"],
            false,
            sequence,
        )?;
        access(
            root,
            HOST,
            label,
            "dir",
            &[
                "write",
                "add_name",
                "remove_name",
                "create",
                "setattr",
                "relabelfrom",
                "relabelto",
                "mounton",
            ],
            false,
            sequence,
        )?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn activation_root_policy_delta_is_limited_to_two_original_directory_labels() {
        let delta = include_str!("../policy/activation-roots.cil");
        let rules: Vec<_> = delta.lines().filter(|line| line.starts_with('(')).collect();
        assert_eq!(rules.len(), 4);
        for label in ["apex_mnt_dir", "linkerconfig_file"] {
            assert!(rules.contains(&format!("(allow droidloom_broker {label} (dir (getattr search read open relabelto)))").as_str()));
            assert!(
                rules.contains(&format!("(allow {label} tmpfs (filesystem (associate)))").as_str())
            );
        }
        for forbidden in [
            "(file (",
            "droidloom_host",
            "unlabeled",
            "setenforce",
            "load_policy",
            "(capability",
            "relabelfrom",
            "write",
            "mounton",
            "typeattribute",
        ] {
            assert!(rules.iter().all(|line| !line.contains(forbidden)));
        }
    }
}
