use super::*;
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixStream;

fn readonly(file: &File) -> File {
    File::open(format!("/proc/self/fd/{}", file.as_raw_fd())).unwrap()
}
fn write_source(root: &std::path::Path, name: &str, data: &[u8]) -> PathBuf {
    let path = root.join(name);
    std::fs::write(&path, data).unwrap();
    path
}

#[test]
fn single_and_split_capture_preserve_complete_original_bytes() {
    let d = tempfile::tempdir().unwrap();
    let base = b"PK\x03\x04unchanged signed base";
    let split = b"PK\x03\x04unchanged signed split";
    let p = write_source(d.path(), "base.apk", base);
    let q = write_source(d.path(), "split.apk", split);
    for paths in [vec![p.clone()], vec![p.clone(), q.clone()]] {
        let (mut file, lengths) = prepare(&paths).unwrap();
        validate(&file, &lengths).unwrap();
        let expected = if paths.len() == 1 {
            base.to_vec()
        } else {
            [base.as_slice(), split.as_slice()].concat()
        };
        let mut observed = Vec::new();
        file.read_to_end(&mut observed).unwrap();
        assert_eq!(observed, expected);
        assert_eq!(
            lengths,
            if paths.len() == 1 {
                vec![base.len() as u64]
            } else {
                vec![base.len() as u64, split.len() as u64]
            }
        );
        assert_eq!(
            std::fs::read_link(format!("/proc/self/fd/{}", file.as_raw_fd())).unwrap(),
            PathBuf::from("/memfd:droidloom-apk-payload (deleted)")
        );
        assert_eq!(file.metadata().unwrap().mode() & 0o111, 0);
        // SAFETY: scalar descriptor property queries.
        assert_eq!(
            unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE,
            libc::O_RDONLY
        );
        assert_eq!(
            unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GET_SEALS) }
                & (REQUIRED_SEALS | F_SEAL_EXEC),
            REQUIRED_SEALS | F_SEAL_EXEC
        );
        assert_ne!(
            unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
    }
    assert_eq!(std::fs::read(p).unwrap(), base);
    assert_eq!(std::fs::read(q).unwrap(), split);
}

#[test]
fn real_scm_rights_preserves_readonly_seals_inode_and_bytes() {
    let input = test_payload(b"PK\x03\x04original");
    let original = observe(&input).unwrap();
    let (sender, receiver) = UnixStream::pair().unwrap();
    super::super::apk::send_file(&sender, b'{', &input).unwrap();
    let (byte, received) = super::super::apk::receive_file(&receiver).unwrap();
    assert_eq!(byte, b'{');
    drop(input);
    let mut received = received.unwrap();
    validate(&received, &[12]).unwrap();
    assert_eq!(observe(&received).unwrap(), original);
    let mut bytes = Vec::new();
    received.read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes, b"PK\x03\x04original");
}

#[test]
fn each_missing_immutable_seal_is_rejected_even_with_correct_bytes() {
    for missing in [
        libc::F_SEAL_SEAL,
        libc::F_SEAL_SHRINK,
        libc::F_SEAL_GROW,
        libc::F_SEAL_WRITE,
    ] {
        let mut writer = create().unwrap();
        writer.write_all(b"PK\x03\x04base").unwrap();
        // SAFETY: owned scalar seal operation; intentionally incomplete.
        assert_eq!(
            unsafe {
                libc::fcntl(
                    writer.as_raw_fd(),
                    libc::F_ADD_SEALS,
                    REQUIRED_SEALS & !missing,
                )
            },
            0
        );
        let file = readonly(&writer);
        assert!(validate(&file, &[8]).is_err(), "missing seal {missing}");
    }
}

#[test]
fn writable_alias_is_never_admitted_and_kernel_denies_all_body_changes() {
    let mut writer = create().unwrap();
    writer.write_all(b"PK\x03\x04base").unwrap();
    let alias = writer.try_clone().unwrap();
    let file = seal(writer).unwrap();
    validate(&file, &[8]).unwrap();
    assert!(validate(&alias, &[8]).is_err());
    assert_eq!(
        alias.write_at(b"x", 4).unwrap_err().raw_os_error(),
        Some(libc::EPERM)
    );
    assert_eq!(
        alias.set_len(9).unwrap_err().raw_os_error(),
        Some(libc::EPERM)
    );
    assert_eq!(
        alias.set_len(7).unwrap_err().raw_os_error(),
        Some(libc::EPERM)
    );
    assert!(
        alias
            .set_permissions(std::fs::Permissions::from_mode(0o700))
            .is_err()
    );
    // A still-live O_RDWR alias also cannot introduce a writable shared map.
    // SAFETY: no pointer is dereferenced; failure is required.
    let mapped = unsafe {
        libc::mmap(
            std::ptr::null_mut(),
            4096,
            libc::PROT_READ | libc::PROT_WRITE,
            libc::MAP_SHARED,
            alias.as_raw_fd(),
            0,
        )
    };
    assert_eq!(mapped, libc::MAP_FAILED);
    assert_eq!(
        hash(&file, 0, 8, Instant::now() + Duration::from_secs(1)).unwrap(),
        <[u8; 32]>::from(Sha256::digest(b"PK\x03\x04base"))
    );
}

#[test]
fn ordinary_unlinked_temporary_file_and_nonfiles_are_not_payloads() {
    let mut ordinary = tempfile::tempfile().unwrap();
    ordinary.write_all(b"PK\x03\x04base").unwrap();
    assert!(validate(&readonly(&ordinary), &[8]).is_err());
    assert!(validate(&File::open("/dev/null").unwrap(), &[8]).is_err());
    let file = test_payload(b"PK\x03\x04base");
    let path = format!("/proc/self/fd/{}", file.as_raw_fd());
    let path_only = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_PATH)
        .open(path)
        .unwrap();
    assert!(validate(&path_only, &[8]).is_err());
}

#[test]
fn noexec_flag_cannot_be_replaced_with_only_chmod_and_four_seals() {
    // SAFETY: the source literal and Linux scalar flags are valid.
    let fd =
        unsafe { libc::memfd_create(NAME.as_ptr(), libc::MFD_ALLOW_SEALING | libc::MFD_CLOEXEC) };
    assert!(fd >= 0);
    // SAFETY: owns the new successful descriptor.
    let mut writer = unsafe { File::from_raw_fd(fd) };
    writer.write_all(b"PK\x03\x04base").unwrap();
    writer
        .set_permissions(std::fs::Permissions::from_mode(0o600))
        .unwrap();
    assert_eq!(
        unsafe { libc::fcntl(writer.as_raw_fd(), libc::F_ADD_SEALS, REQUIRED_SEALS) },
        0
    );
    assert!(validate(&readonly(&writer), &[8]).is_err());
}

#[test]
fn exact_bounded_segments_reject_truncation_trailing_bytes_and_non_zip() {
    let file = test_payload(b"PK\x03\x04basePK\x03\x04split");
    validate(&file, &[8, 9]).unwrap();
    for lengths in [
        vec![],
        vec![8],
        vec![8, 8],
        vec![8, 10],
        vec![3, 14],
        vec![u64::MAX],
        vec![4; 33],
    ] {
        assert!(validate(&file, &lengths).is_err(), "{lengths:?}");
    }
    assert!(validate(&test_payload(b"PK\x03\x04baseNOT-split"), &[8, 9]).is_err());
    let writer = create().unwrap();
    writer.set_len(MAX_BYTES + 1).unwrap(); // Sparse; does not allocate 2 GiB.
    assert!(validate(&seal(writer).unwrap(), &[MAX_BYTES + 1]).is_err());
}

#[test]
fn source_rewrites_cannot_change_the_published_original_payload() {
    let d = tempfile::tempdir().unwrap();
    let path = write_source(d.path(), "base.apk", b"PK\x03\x04base");
    let (file, lengths) = prepare(&[path.clone()]).unwrap();
    std::fs::write(path, b"PK\x03\x04evil").unwrap();
    validate(&file, &lengths).unwrap();
    let mut bytes = [0_u8; 8];
    file.read_exact_at(&mut bytes, 0).unwrap();
    assert_eq!(&bytes, b"PK\x03\x04base");
}

#[test]
fn original_input_count_and_zip_contract_remain_required() {
    assert!(prepare(&[]).is_err());
    let d = tempfile::tempdir().unwrap();
    let path = write_source(d.path(), "not.apk", b"not an APK");
    assert!(prepare(&[path.clone()]).is_err());
    assert!(prepare(&vec![path; 33]).is_err());
    assert!(prepare(&[PathBuf::from("/dev/null")]).is_err());
    assert!(before(Instant::now() - Duration::from_secs(1)).is_err());
}

#[test]
fn production_context_requires_actual_joint_policy_object_not_a_claim() {
    let file = test_payload(b"PK\x03\x04base");
    // Do not assume this ordinary host loaded the board's final policy.
    let n = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            std::ptr::null_mut(),
            0,
        )
    };
    if n < 0 {
        assert!(validate_production_context(&file).is_err());
    } else {
        let mut context = vec![0_u8; n as usize];
        assert_eq!(
            unsafe {
                libc::fgetxattr(
                    file.as_raw_fd(),
                    c"security.selinux".as_ptr(),
                    context.as_mut_ptr().cast(),
                    context.len(),
                )
            },
            n
        );
        let actual = context.strip_suffix(&[0]).unwrap_or(&context);
        assert_eq!(
            validate_production_context(&file).is_ok(),
            actual == PAYLOAD_CONTEXT
        );
    }
}

#[test]
fn identical_sealed_bytes_with_a_different_kernel_name_are_rejected() {
    // SAFETY: fixed alternative literal is a deliberate negative test.
    let fd = unsafe {
        libc::memfd_create(
            c"not-droidloom-apk-payload".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING | MFD_NOEXEC_SEAL,
        )
    };
    assert!(fd >= 0);
    // SAFETY: owns the newly returned successful descriptor.
    let mut writer = unsafe { File::from_raw_fd(fd) };
    writer.write_all(b"PK\x03\x04base").unwrap();
    let input = seal(writer).unwrap();
    assert!(validate(&input, &[8]).is_err());
}

#[test]
fn working_pinned_capture_uses_held_descriptors_and_rejects_wrong_bytes_or_renewed_time() {
    let d=tempfile::tempdir().unwrap();
    let original=b"PK\x03\x04original";
    let path=write_source(d.path(),"held.apk",original);
    let held=File::open(&path).unwrap();
    let expected=(original.len() as u64,<[u8;32]>::from(Sha256::digest(original)));
    std::fs::rename(&path,d.path().join("old.apk")).unwrap();
    std::fs::write(&path,b"PK\x03\x04replaced").unwrap();
    let (mut actual,lengths)=prepare_pinned_until(&[&held],&[expected],
        Instant::now()+Duration::from_secs(2)).unwrap();
    let mut bytes=Vec::new();actual.read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes,original);
    assert_eq!(lengths,[original.len() as u64]);
    assert!(prepare_pinned_until(&[&held],&[(expected.0,[0;32])],
        Instant::now()+Duration::from_secs(2)).is_err());
    assert!(prepare_pinned_until(&[&held],&[(expected.0+1,expected.1)],
        Instant::now()+Duration::from_secs(2)).is_err());
    assert!(prepare_pinned_until(&[&held],&[expected],Instant::now()).is_err());
    assert!(prepare_pinned_until(&[&held],&[],Instant::now()+Duration::from_secs(2)).is_err());
    assert_eq!(PREPARE_LIMIT.as_secs(),
        super::super::physical_qualification_channel::budget::APPLICATION_INSTALL_PAYLOAD_SECONDS);
}
