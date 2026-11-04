
#[cfg(test)]
pub(crate) fn owned_cleanup_test_spec(directory: &Path) -> CellSpec {
    CellSpec {
        host_uid: 1001,
        subordinate_uids: crate::IdRange {
            start: 100_000,
            count: 100_000,
        },
        subordinate_gids: crate::IdRange {
            start: 200_000,
            count: 100_000,
        },
        image_dir: directory.join("images"),
        gapps_dir: None,
        vendor_image: directory.join("vendor.img"),
        android_init: None,
        android_file_overrides: Vec::new(),
        android_runtime_directories: Vec::new(),
        shared_storage_directories: Vec::new(),
        data_dir: directory.join("data"),
        runtime_dir: directory.join("runtime"),
        render_node: directory.join("unused-render-node"),
        graphics_backend: crate::GraphicsBackend::default(),
        denial_socket: directory.join("unused-denial.sock"),
    }
}


#[cfg(test)]
mod cleanup_regression_control {
    use super::*;
    #[test]
    fn repeated_owned_cleanup_must_not_report_success() {
        let directory = tempfile::tempdir().unwrap();
        let spec = owned_cleanup_test_spec(directory.path());
        fs::create_dir(&spec.runtime_dir).unwrap();
        fs::create_dir(spec.runtime_dir.join("android-cmdline")).unwrap();
        let mut child = std::process::Command::new("/bin/true").spawn().unwrap();
        assert!(child.wait().unwrap().success());
        let mut cell = DevelopmentCell {spec, child, network: None, cleaned: false};
        assert!(cell.try_wait().is_err(), "the first real cleanup must fail");
        assert!(cell.try_wait().is_err(), "cleanup failure became false success on the second poll");
    }
}
