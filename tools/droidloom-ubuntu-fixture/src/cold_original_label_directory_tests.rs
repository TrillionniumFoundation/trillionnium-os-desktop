use super::*;
use std::os::{
    fd::AsRawFd,
    unix::fs::{PermissionsExt, symlink},
};

fn fixture() -> (tempfile::TempDir, Records) {
    let root = tempfile::Builder::new()
        .prefix(".p4-label-directory-")
        .tempdir_in(std::env::current_dir().unwrap())
        .unwrap();
    let parent = root.path().join("parent");
    std::fs::create_dir(&parent).unwrap();
    let path = parent.join("records");
    std::fs::create_dir(&path).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
    let records = Records::open(&path).unwrap();
    (root, records)
}

#[test]
fn kernel_resolution_keeps_the_original_private_directory_and_held_inode() {
    let (_root, records) = fixture();
    let prior = fs::Tree::open(
        &fs::absolute_string(&records.path).unwrap(),
        records.identity.uid,
    )
    .unwrap();
    assert_eq!(
        fs::stat(&prior.root).unwrap(),
        fs::stat(&records.held).unwrap()
    );
    for _ in 0..100 {
        records.revalidate().unwrap();
    }
    assert_eq!(
        fs::stat(&prior.root).unwrap(),
        fs::stat(&records.held).unwrap()
    );
}

#[test]
fn intermediate_symlink_to_the_same_held_inode_is_rejected() {
    let (root, records) = fixture();
    let parent = root.path().join("parent");
    let moved = root.path().join("moved");
    std::fs::rename(&parent, &moved).unwrap();
    symlink(&moved, &parent).unwrap();
    assert_eq!(
        fs::stat(&records.held).unwrap(),
        fs::identity(
            &rustix::fs::statat(
                rustix::fs::CWD,
                moved.join("records"),
                AtFlags::SYMLINK_NOFOLLOW,
            )
            .unwrap()
        ),
    );
    assert!(records.revalidate().is_err());
    assert!(
        fs::Tree::open(
            &fs::absolute_string(&records.path).unwrap(),
            records.identity.uid,
        )
        .is_err()
    );
}

#[test]
fn final_symlink_and_same_mode_replacement_directory_are_rejected() {
    let (_root, records) = fixture();
    let saved = records.path.with_file_name("saved");
    std::fs::rename(&records.path, &saved).unwrap();
    symlink(&saved, &records.path).unwrap();
    assert!(records.revalidate().is_err());
    std::fs::remove_file(&records.path).unwrap();
    std::fs::create_dir(&records.path).unwrap();
    std::fs::set_permissions(&records.path, std::fs::Permissions::from_mode(0o700)).unwrap();
    assert!(records.revalidate().is_err());
}

#[test]
fn original_path_grammar_magic_link_and_mode_checks_remain_in_force() {
    let (root, mut records) = fixture();
    let original = records.path.clone();
    for path in [
        PathBuf::from("relative/records"),
        root.path().join("parent/../parent/records"),
        PathBuf::from(format!("/proc/self/fd/{}", records.held.as_raw_fd())),
    ] {
        records.path = path;
        assert!(records.revalidate().is_err());
    }
    records.path = original;
    records.revalidate().unwrap();
    std::fs::set_permissions(&records.path, std::fs::Permissions::from_mode(0o750)).unwrap();
    assert!(records.revalidate().is_err());
    std::fs::set_permissions(&records.path, std::fs::Permissions::from_mode(0o700)).unwrap();
    records.revalidate().unwrap();
}
