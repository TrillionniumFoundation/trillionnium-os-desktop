use super::*;

#[test]
fn host_column_is_distinct_from_inside_ids() {
    let map = parse_map(b"0 400000 1000\n1000 700000 2\n").unwrap();
    assert_eq!(map[0].host_start, 400000);
    assert_eq!(map[1].inside_start, 1000);
    assert!(overlaps(
        map[1].host_start,
        map[1].count,
        IdRange {
            start: 700001,
            count: 1
        }
    ));
    assert!(!overlaps(
        map[1].inside_start,
        map[1].count,
        IdRange {
            start: 700001,
            count: 1
        }
    ));
}

#[test]
fn range_boundaries_exclude_minus_one() {
    assert!(checked_range(u32::MAX - 1, 1).is_ok());
    assert!(checked_range(u32::MAX, 1).is_err());
    assert!(checked_range(0, 0).is_err());
    assert!(!overlaps(
        100,
        20,
        IdRange {
            start: 120,
            count: 1
        }
    ));
    assert!(overlaps(
        100,
        20,
        IdRange {
            start: 119,
            count: 1
        }
    ));
}

#[test]
fn initial_map_is_valid_only_as_explicit_host_evidence() {
    assert_eq!(
        parse_map(b"0 0 4294967295\n").unwrap(),
        vec![MapExtent {
            inside_start: 0,
            host_start: 0,
            count: u32::MAX
        }]
    );
    assert!(parse_map(b"0 0 4294967296\n").is_err());
}

#[test]
fn empty_partial_maps_cannot_certify_free_ids() {
    for raw in [b"".as_slice(), b"\n", b"0 200000\n", b"0 200000 0\n"] {
        assert!(parse_map(raw).is_err());
    }
}

#[test]
fn both_inside_and_host_extent_overlap_are_rejected() {
    assert!(parse_map(b"0 200000 10\n9 400000 10\n").is_err());
    assert!(parse_map(b"0 200000 10\n20 200009 10\n").is_err());
    assert!(parse_map(b"0 200000 10\n20 200010 10\n").is_ok());
}

#[test]
fn map_numeric_and_resource_bounds_are_fail_closed() {
    assert!(parse_map(b"-1 0 1\n").is_err());
    assert!(parse_map(b"0 1x 1\n").is_err());
    assert!(parse_map(&vec![b' '; MAX_MAP_BYTES + 1]).is_err());
    let mut raw = String::new();
    for i in 0..=MAX_EXTENTS {
        raw.push_str(&format!("{} {} 1\n", i, i + 1000));
    }
    assert!(parse_map(raw.as_bytes()).is_err());
}

#[test]
fn proc_stat_identity_handles_parentheses_and_rejects_changed_start() {
    let mut rest = vec!["0"; 20];
    rest[0] = "S";
    rest[1] = "11";
    rest[19] = "12345";
    let raw = format!("22 (collector ) name) {}", rest.join(" "));
    let first = parse_stat(raw.as_bytes()).unwrap();
    assert_eq!(first.pid, 22);
    assert_eq!(first.ppid, 11);
    assert_eq!(first.starttime, 12345);
    let mut second = first.clone();
    second.starttime += 1;
    assert!(!same_task(&first, &second));
    second = first.clone();
    second.state = b'Z';
    assert!(!same_task(&first, &second));
}

#[test]
fn namespace_uapi_layout_is_exact() {
    assert_eq!(mem::size_of::<NamespaceRequest>(), 32);
    assert_eq!(mem::size_of::<CloneArguments>(), 88);
    assert_eq!(mem::size_of::<NamespaceFileHandle>(), 24);
    assert_eq!(mem::offset_of!(NamespaceFileHandle, namespace_id), 8);
}

#[test]
fn deadline_rejection_cannot_create_a_guard() {
    let result = audit_existing_user_namespaces(
        IdRange {
            start: 200000,
            count: 100000,
        },
        IdRange {
            start: 200000,
            count: 100000,
        },
        Instant::now(),
    );
    assert!(matches!(result, Err(AuditError::Unknown(_))));
}

#[test]
fn calling_thread_signal_mask_is_restored_exactly() {
    let before = current_signal_mask().unwrap();
    let mut blocked = BlockedSignals::new().unwrap();
    assert_eq!(current_signal_mask().unwrap(), BLOCKABLE_SIGNALS);
    blocked.restore().unwrap();
    assert_eq!(current_signal_mask().unwrap(), before);
}

#[test]
fn auto_reap_signal_policy_is_refused_without_a_collector() {
    const CHILD: &str = "DROIDLOOM_USERNS_AUTOREAP_CONTROL";
    if std::env::var_os(CHILD).is_none() {
        let path = module_path!().split_once("::").unwrap().1;
        let name = format!("{path}::auto_reap_signal_policy_is_refused_without_a_collector");
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", &name, "--test-threads=1"])
            .env(CHILD, "1")
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout).unwrap();
        assert!(stdout.contains("running 1 test") && stdout.contains("1 passed"));
        return;
    }
    let mut disposition: libc::sigaction = unsafe { mem::zeroed() };
    disposition.sa_sigaction = libc::SIG_IGN;
    disposition.sa_flags = libc::SA_NOCLDWAIT;
    unsafe {
        libc::sigemptyset(&mut disposition.sa_mask);
    }
    assert_eq!(
        unsafe { libc::sigaction(libc::SIGCHLD, &disposition, std::ptr::null_mut()) },
        0
    );
    assert_eq!(
        require_sigchld_policy().unwrap_err().code,
        "sigchld_reaper_policy_not_qualified"
    );
}
