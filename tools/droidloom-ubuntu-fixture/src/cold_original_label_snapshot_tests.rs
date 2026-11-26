use super::*;
use rustix::fs::{Mode, OFlags};

fn fixture() -> (tempfile::TempDir, File) {
    let area = tempfile::Builder::new()
        .prefix(".p4-snapshot-custody-")
        .tempdir_in(std::env::current_dir().unwrap())
        .unwrap();
    let path = area.path().join("target");
    std::fs::write(&path, b"held public target").unwrap();
    let held = File::from(
        rustix::fs::open(
            &path,
            OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .unwrap(),
    );
    (area, held)
}

#[test]
fn complete_snapshot_keeps_empty_binary_and_large_attribute_values() {
    let (_area, file) = fixture();
    let mut wanted = attributes(&file).unwrap();
    for (name, value) in [
        ("user.droidloom.empty", Vec::new()),
        ("user.droidloom.binary", vec![0, 255, 128, 1, 0]),
        ("user.droidloom.long", vec![0x67; 2048]),
    ] {
        set(&file, name, Some(&value)).unwrap();
        wanted.insert(name.into(), value);
    }
    let before = snapshot(&file).unwrap();
    assert_eq!(before.attributes, wanted);
    assert_eq!(snapshot(&file).unwrap(), before);
}

#[test]
fn reused_alias_reads_actual_new_values_without_caching() {
    let (_area, file) = fixture();
    let name = "user.droidloom.mutable";
    set(&file, name, Some(b"before")).unwrap();
    let alias = DescriptorAlias::new(&file).unwrap();
    let mut first = vec![0; get(&alias, name, &mut []).unwrap()];
    get(&alias, name, &mut first).unwrap();
    assert_eq!(first, b"before");
    set(&file, name, Some(b"after-with-another-length")).unwrap();
    let mut second = vec![0; get(&alias, name, &mut []).unwrap()];
    get(&alias, name, &mut second).unwrap();
    assert_eq!(second, b"after-with-another-length");
    assert_eq!(attributes(&file).unwrap()[name], second);
    let count = list(&alias, &mut []).unwrap();
    let mut names = vec![0; count];
    assert_eq!(list(&alias, &mut names).unwrap(), count);
    assert!(
        names
            .split(|byte| *byte == 0)
            .any(|row| row == name.as_bytes())
    );
}

#[test]
fn every_reused_read_rejects_a_different_held_namespace() {
    let (_area, file) = fixture();
    let mut alias = DescriptorAlias::new(&file).unwrap();
    list(&alias, &mut []).unwrap();
    // A real namespace descriptor with a different identity replaces one
    // held member; no namespace or host state is changed by this test.
    let other = File::open("/proc/self/ns/net").unwrap();
    assert_ne!(fs::stat(&other).unwrap(), alias.custody.namespaces[0].2);
    alias.custody.namespaces[0].1 = other;
    assert!(list(&alias, &mut []).is_err());
    assert!(get(&alias, "user.droidloom.any", &mut []).is_err());
}

#[test]
fn every_reused_read_rejects_a_different_proc_target_or_process() {
    let (area, file) = fixture();
    let other_path = area.path().join("other");
    std::fs::write(&other_path, b"other public target").unwrap();
    let other = File::open(&other_path).unwrap();
    let mut alias = DescriptorAlias::new(&file).unwrap();
    list(&alias, &mut []).unwrap();
    alias.name = other.as_raw_fd().to_string();
    assert!(list(&alias, &mut []).is_err());
    assert!(get(&alias, "user.droidloom.any", &mut []).is_err());
    let mut alias = DescriptorAlias::new(&file).unwrap();
    alias.custody.pid = alias.custody.pid.checked_add(1).unwrap();
    assert!(list(&alias, &mut []).is_err());
    assert!(get(&alias, "user.droidloom.any", &mut []).is_err());
}

#[test]
fn fixed_proc_name_metadata_matches_a_fresh_opened_descriptor() {
    for path in [
        "/proc/self",
        "/proc/self/fd",
        "/proc/self/ns/mnt",
        "/proc/self/ns/pid",
        "/proc/self/ns/user",
    ] {
        let named_before = fs::identity(
            &rustix::fs::statat(rustix::fs::CWD, path, rustix::fs::AtFlags::empty()).unwrap(),
        );
        let opened = File::open(path).unwrap();
        let named_after = fs::identity(
            &rustix::fs::statat(rustix::fs::CWD, path, rustix::fs::AtFlags::empty()).unwrap(),
        );
        assert_eq!(named_before, fs::stat(&opened).unwrap(), "{path}");
        assert_eq!(named_after, named_before, "{path}");
    }
}
