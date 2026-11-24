use super::*;
static ACTUAL_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn observations(actor: EarlyActor) -> (Snapshot, Properties, Properties) {
    let main = 123;
    let command = super::super::super::bus::ExecCommand {
        path: BROKER_EXECUTABLE.into(),
        arguments: vec![BROKER_EXECUTABLE.into(), command(actor).into()],
        flags: Vec::new(),
        started: [100, 10],
        exited: if actor == EarlyActor::Factory {
            [120, 20]
        } else {
            [0, 0]
        },
        pid: if actor == EarlyActor::Factory {
            122
        } else {
            main
        },
        code: if actor == EarlyActor::Factory {
            libc::CLD_EXITED
        } else {
            0
        },
        status: 0,
    };
    let unit = Properties::from([
        ("ActiveState".into(), Value::Text("active".into())),
        ("SubState".into(), Value::Text("running".into())),
        ("Job".into(), Value::Job(0, "/".into())),
        ("InvocationID".into(), Value::Bytes(vec![7; 16])),
        ("StateChangeTimestampMonotonic".into(), Value::U64(10)),
        ("LoadState".into(), Value::Text("loaded".into())),
    ]);
    let service = Properties::from([
        ("MainPID".into(), Value::U32(main)),
        ("ExecMainPID".into(), Value::U32(main)),
        ("ControlPID".into(), Value::U32(0)),
        ("Result".into(), Value::Text("success".into())),
        ("ExecMainCode".into(), Value::I32(0)),
        ("ExecMainStatus".into(), Value::I32(0)),
        ("ExecMainStartTimestampMonotonic".into(), Value::U64(10)),
        ("ExecMainExitTimestampMonotonic".into(), Value::U64(0)),
        ("ExecStartEx".into(), Value::Commands(vec![command.clone()])),
        ("ControlGroup".into(), Value::Text(actor_group(actor))),
        ("ControlGroupId".into(), Value::U64(15)),
        ("NRestarts".into(), Value::U32(0)),
    ]);
    let mut ended_unit = unit.clone();
    ended_unit.insert("ActiveState".into(), Value::Text("inactive".into()));
    ended_unit.insert("SubState".into(), Value::Text("dead".into()));
    ended_unit.insert("StateChangeTimestampMonotonic".into(), Value::U64(40));
    let mut ended_service = service.clone();
    ended_service.insert("MainPID".into(), Value::U32(0));
    ended_service.insert("ExecMainCode".into(), Value::I32(libc::CLD_EXITED));
    ended_service.insert("ExecMainExitTimestampMonotonic".into(), Value::U64(35));
    if actor != EarlyActor::Factory {
        ended_service.insert(
            "ExecStartEx".into(),
            Value::Commands(vec![super::super::super::bus::ExecCommand {
                exited: [135, 35],
                code: libc::CLD_EXITED,
                ..command
            }]),
        );
    }
    (
        Snapshot {
            invocation: Invocation {
                unit: actor.text().into(),
                path: actor.path().into(),
                id: [7; 16],
            },
            unit,
            service,
        },
        ended_unit,
        ended_service,
    )
}

#[test]
fn actor_terminal_checks_original_main_and_adopter_as_distinct_processes() {
    for actor in ACTORS {
        let (original, unit, service) = observations(actor);
        validate_actor_terminal(actor, &original, &unit, &service).unwrap();
        let mut removed = service.clone();
        removed.insert("ControlGroup".into(), Value::Text(String::new()));
        validate_actor_terminal(actor, &original, &unit, &removed).unwrap();
        removed.insert("ControlGroupId".into(), Value::U64(0));
        validate_actor_terminal(actor, &original, &unit, &removed).unwrap();
        assert!(
            validate_actor_terminal(actor, &original, &original.unit, &original.service).is_err()
        );
        for (name, value) in [
            ("ExecMainPID", Value::U32(122)),
            ("MainPID", Value::U32(123)),
            ("Result", Value::Text("signal".into())),
            ("ExecMainCode", Value::I32(libc::CLD_KILLED)),
            ("ExecMainStatus", Value::I32(1)),
            ("NRestarts", Value::U32(1)),
            ("ExecMainStartTimestampMonotonic", Value::U64(11)),
            ("ExecMainExitTimestampMonotonic", Value::U64(9)),
            ("ControlGroupId", Value::U64(16)),
        ] {
            let mut changed = service.clone();
            changed.insert(name.into(), value);
            assert!(
                validate_actor_terminal(actor, &original, &unit, &changed).is_err(),
                "{actor:?} {name}"
            );
        }
        for (name, value) in [
            ("InvocationID", Value::Bytes(vec![8; 16])),
            ("ActiveState", Value::Text("failed".into())),
            (
                "Job",
                Value::Job(7, "/org/freedesktop/systemd1/job/7".into()),
            ),
        ] {
            let mut changed = unit.clone();
            changed.insert(name.into(), value);
            assert!(validate_actor_terminal(actor, &original, &changed, &service).is_err());
        }
        for mutation in 0..5 {
            let mut changed = service.clone();
            let Value::Commands(cmd) = changed.get_mut("ExecStartEx").unwrap() else {
                unreachable!()
            };
            match mutation {
                0 => cmd[0].pid += 1,
                1 => cmd[0].started[1] += 1,
                2 => cmd[0].status = 1,
                3 => cmd[0].code = libc::CLD_KILLED,
                _ => cmd[0].exited = [0, 0],
            }
            assert!(validate_actor_terminal(actor, &original, &unit, &changed).is_err());
        }
    }
}

#[test]
fn all_fixed_actor_names_and_stop_order_match_installed_templates() {
    let factory = include_str!("droidloom-instance-factory.service");
    let launcher = include_str!("droidloom-instance-launcher.service");
    let observer = include_str!("droidloom-early-observer.service");
    for (actor, source) in ACTORS.into_iter().zip([factory, launcher, observer]) {
        assert!(source.contains(&format!("ExecStart={BROKER_EXECUTABLE} {}", command(actor))));
        assert!(source.contains("Type=notify\n"));
        assert!(source.contains("NotifyAccess=main\n"));
    }
    assert!(launcher.contains("BindsTo=droidloom-instance-factory.service\n"));
    assert!(launcher.contains("PartOf=droidloom-production.service\n"));
    assert!(observer.contains("BindsTo=droidloom-production.service\n"));
    assert!(!factory.contains("PartOf=droidloom-production.service"));
    assert_eq!(
        ACTORS.map(EarlyActor::text),
        [
            "droidloom-instance-factory.service",
            "droidloom-instance-launcher.service",
            "droidloom-early-observer.service",
        ]
    );
}

#[test]
fn original_pidfd_requires_real_process_death() {
    use std::process::Command;
    let mut child = Command::new("/bin/sleep").arg("0.05").spawn().unwrap();
    let pidfd = actual_pidfd(child.id()).unwrap();
    assert!(!ended(&pidfd).unwrap());
    assert!(child.wait().unwrap().success());
    assert!(ended(&pidfd).unwrap());
    let live = actual_pidfd(std::process::id()).unwrap();
    assert!(!ended(&live).unwrap());
}

// Run explicitly as initial root on a host with systemd GetUnitByPIDFD. This
// tests the exact private bus parser, MAINPIDFD adoption, real stop
// JobRemoved signals, PIDFD death and cgroup removal. It is not MAC admission.
#[test]
#[ignore = "requires root and temporary fixed systemd test units"]
fn actual_early_actor_stop_jobs_pin_adopted_main_and_all_original_generations() {
    run_actual_retirement(true);
}
#[test]
#[ignore = "requires root and temporary fixed systemd test units"]
fn actual_collected_actor_uses_original_exit_proof_without_another_stop_job() {
    run_actual_retirement(false);
}
fn run_actual_retirement(keep_dependencies_loaded: bool) {
    use std::os::unix::net::UnixStream;
    use std::process::Command;
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let _serial = ACTUAL_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let actors = [
        EarlyActor::TestFactory,
        EarlyActor::TestLauncher,
        EarlyActor::TestObserver,
    ];
    struct Cleanup;
    impl Drop for Cleanup {
        fn drop(&mut self) {
            let _ = Command::new("/usr/bin/systemctl")
                .args([
                    "stop",
                    "droidloom-ff1d-test-package-observer.service",
                    "droidloom-ff1d-test-package-launcher.service",
                    "droidloom-ff1d-test-package-factory.service",
                ])
                .status();
        }
    }
    for actor in actors {
        let state = Command::new("/usr/bin/systemctl")
            .args(["show", actor.text(), "-p", "LoadState", "--value"])
            .output()
            .unwrap();
        assert_eq!(
            String::from_utf8_lossy(&state.stdout).trim(),
            "not-found",
            "fixed test unit exists"
        );
    }
    let _cleanup = Cleanup;
    for actor in actors.into_iter().rev() {
        let factory = actor.production() == EarlyActor::Factory;
        let observer = actor.production() == EarlyActor::Observer;
        let mut args = vec![
            format!("--unit={}", actor.text()),
            "--service-type=notify".into(),
            "--property=NotifyAccess=main".into(),
            "--property=Restart=no".into(),
            format!(
                "--property=KillMode={}",
                if observer { "control-group" } else { "process" }
            ),
            format!(
                "--property=SendSIGKILL={}",
                if observer { "yes" } else { "no" }
            ),
            "--property=NoNewPrivileges=yes".into(),
            "--property=PrivateMounts=no".into(),
            format!(
                "--property=TimeoutStopSec={}s",
                if factory {
                    210
                } else if observer {
                    15
                } else {
                    30
                }
            ),
            "--property=TimeoutStartSec=20s".into(),
            "--property=RuntimeMaxSec=120s".into(),
            format!("--property=UMask={}", if factory { "0022" } else { "0077" }),
            "--property=MemoryMax=128M".into(),
            "--property=TasksMax=16".into(),
        ];
        if !observer {
            args.extend([
                "--property=User=root".into(),
                "--property=Group=root".into(),
            ]);
        }
        if factory && keep_dependencies_loaded {
            // Keep an inactive dependent loaded until the persistent factory
            // exits, like a normal active target's Wants references. This is
            // test setup, not a RefUnit/start grant to the production helper.
            args.push("--property=Wants=droidloom-ff1d-test-package-observer.service droidloom-ff1d-test-package-launcher.service".into());
        }
        if actor.production() == EarlyActor::Launcher {
            args.push("--property=WorkingDirectory=/".into());
        }
        args.extend([
            "/usr/bin/python3".into(),
            "-c".into(),
            TEST_PROGRAM.into(),
            if factory { "factory" } else { "ordinary" }.into(),
        ]);
        let result = Command::new("/usr/bin/systemd-run")
            .args(args)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "start {actor:?}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
    }
    let socket = UnixStream::connect("/run/systemd/private").unwrap();
    let file = File::from(std::os::fd::OwnedFd::from(socket));
    let deadline = Instant::now() + Duration::from_secs(30);
    let bus = PrivateBus::from_authenticated_socket(&file, deadline).unwrap();
    let [a, b, c] = actors;
    let originals = EarlyActors {
        original: [
            ActorLifetime::capture(&bus, a, deadline).unwrap(),
            ActorLifetime::capture(&bus, b, deadline).unwrap(),
            ActorLifetime::capture(&bus, c, deadline).unwrap(),
        ],
        begun: Cell::new(false),
        completed: RefCell::new(Vec::new()),
    };
    originals.revalidate_before_commit(&bus, deadline).unwrap();
    let factory = &originals.original[0].original.service;
    assert_ne!(commands(factory).unwrap().pid, main_pid(factory).unwrap());
    // Simulate a dependency having already retired the observer. The original
    // PIDFD, invocation and actual cgroup events remain mandatory.
    assert!(
        Command::new("/usr/bin/systemctl")
            .args(["stop", c.text()])
            .status()
            .unwrap()
            .success()
    );
    if keep_dependencies_loaded {
        let stopped = ActorLifetime::read(&bus, c, deadline).unwrap();
        for name in [
            "MainPID",
            "ExecMainPID",
            "ExecMainCode",
            "ExecMainStatus",
            "ControlGroup",
            "ControlGroupId",
            "ExecStartEx",
        ] {
            println!(
                "original observer after dependency stop: {name}={:?}",
                stopped.service.get(name)
            );
        }
    } else {
        while bus.actor_is_loaded(c, deadline).unwrap() {
            before(deadline).unwrap();
            std::thread::sleep(Duration::from_millis(10));
        }
        let original = &originals.original[2];
        kernel_normal_exit(&original.pidfd, original.node.ino, deadline).unwrap();
        assert!(matches!(retained_cgroup_events(&original.events),
            Err(error) if error.raw_os_error()==Some(libc::ENODEV)));
        assert!(
            matches!(open_absolute(&group_path(c),libc::O_PATH|libc::O_DIRECTORY),
            Err(CgroupError::Io(error)) if error.kind()==io::ErrorKind::NotFound)
        );
        original.revalidate_retired(&bus, deadline).unwrap();
        println!(
            "observer collected before stop phase: exact_NoSuchUnit=true; original_PIDFD_exit0=true; original_cgroup_ENODEV=true"
        );
    }
    originals
        .stop(&bus, deadline, &|| before(deadline))
        .unwrap();
    originals.revalidate_retired(&bus, deadline).unwrap();
    assert!(
        originals
            .stop(&bus, deadline, &|| before(deadline))
            .is_err()
    );
    let completed = originals.completed.borrow();
    assert!(
        matches!(&completed[0],ActorCompletion::AlreadyRetired(proof) if proof.verifies(&originals.original[2]).unwrap())
    );
    assert_eq!(
        completed
            .iter()
            .filter(|p| matches!(p, ActorCompletion::StopJob(_)))
            .count(),
        2
    );
    assert_eq!(
        completed
            .iter()
            .filter(|p| matches!(p, ActorCompletion::AlreadyRetired(_)))
            .count(),
        1
    );
    if !keep_dependencies_loaded {
        assert!(!bus.actor_is_loaded(c, deadline).unwrap());
    }
    for original in &originals.original {
        println!(
            "original {:?}: invocation={:?}; pidfd_dead={}; cgroup_inode={}; retirement_revalidated=true",
            original.actor,
            original.original.invocation.id,
            ended(&original.pidfd).unwrap(),
            original.node.ino
        );
    }
    println!(
        "actual_completed_stop_jobs=2; independently_retired_originals=1; fabricated_stop_jobs=0"
    );
}

#[test]
fn kernel_exit_mask_status_and_cgroup_are_all_mandatory() {
    let value = NativePidfdInfo {
        mask: 12,
        cgroupid: 7,
        exit_code: 0,
        ..NativePidfdInfo::default()
    };
    validate_pidfd_exit(&value, 7).unwrap();
    for mask in [0, 4, 8] {
        assert!(
            validate_pidfd_exit(
                &NativePidfdInfo {
                    mask,
                    cgroupid: 7,
                    ..NativePidfdInfo::default()
                },
                7
            )
            .is_err()
        );
    }
    for exit_code in [1 << 8, libc::SIGTERM, libc::SIGKILL, 0x7f, -1] {
        assert!(
            validate_pidfd_exit(
                &NativePidfdInfo {
                    mask: 12,
                    cgroupid: 7,
                    exit_code,
                    ..NativePidfdInfo::default()
                },
                7
            )
            .is_err()
        );
    }
    assert!(validate_pidfd_exit(&value, 8).is_err());
}

#[test]
fn actual_owned_abnormal_exits_cannot_become_normal_retirement() {
    use std::process::Command;
    for code in [3, 9] {
        let mut child = if code == 3 {
            Command::new("/bin/sh")
                .args(["-c", "sleep 0.05; exit 3"])
                .spawn()
                .unwrap()
        } else {
            Command::new("/bin/sleep").arg("30").spawn().unwrap()
        };
        let pidfd = actual_pidfd(child.id()).unwrap();
        let group = pidfd_info(&pidfd).unwrap().cgroupid;
        if code == 9 {
            assert_eq!(
                unsafe {
                    libc::syscall(
                        libc::SYS_pidfd_send_signal,
                        pidfd.as_raw_fd(),
                        libc::SIGKILL,
                        std::ptr::null::<libc::siginfo_t>(),
                        0,
                    )
                },
                0
            );
        }
        assert!(!child.wait().unwrap().success());
        assert!(
            kernel_normal_exit(&pidfd, group, Instant::now() + Duration::from_secs(1)).is_err()
        );
    }
}

#[test]
#[ignore = "requires root and a temporary fixed systemd test unit"]
fn actual_failed_actor_cannot_use_a_done_stop_job_as_retirement() {
    use std::os::unix::net::UnixStream;
    use std::process::Command;
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let _serial = ACTUAL_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let actor = EarlyActor::TestObserver;
    let state = Command::new("/usr/bin/systemctl")
        .args(["show", actor.text(), "-p", "LoadState", "--value"])
        .output()
        .unwrap();
    assert_eq!(String::from_utf8_lossy(&state.stdout).trim(), "not-found");
    struct Cleanup;
    impl Drop for Cleanup {
        fn drop(&mut self) {
            let _ = Command::new("/usr/bin/systemctl")
                .args(["stop", "droidloom-ff1d-test-package-observer.service"])
                .status();
            let _ = Command::new("/usr/bin/systemctl")
                .args([
                    "reset-failed",
                    "droidloom-ff1d-test-package-observer.service",
                ])
                .status();
        }
    }
    let _cleanup = Cleanup;
    let result = Command::new("/usr/bin/systemd-run")
        .args([
            "--unit=droidloom-ff1d-test-package-observer.service",
            "--service-type=notify",
            "--property=NotifyAccess=main",
            "--property=Restart=no",
            "--property=KillMode=control-group",
            "--property=SendSIGKILL=yes",
            "--property=NoNewPrivileges=yes",
            "--property=PrivateMounts=no",
            "--property=TimeoutStopSec=15s",
            "--property=TimeoutStartSec=20s",
            "--property=RuntimeMaxSec=120s",
            "--property=UMask=0077",
            "--property=MemoryMax=128M",
            "--property=TasksMax=16",
            "--setenv=DROIDLOOM_TEST_STOP_STATUS=42",
            "/usr/bin/python3",
            "-c",
            TEST_PROGRAM,
            "ordinary",
        ])
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let file = File::from(std::os::fd::OwnedFd::from(
        UnixStream::connect("/run/systemd/private").unwrap(),
    ));
    let deadline = Instant::now() + Duration::from_secs(30);
    let bus = PrivateBus::from_authenticated_socket(&file, deadline).unwrap();
    let original = ActorLifetime::capture(&bus, actor, deadline).unwrap();
    let jobs = bus.package_jobs(deadline).unwrap();
    let job = jobs.stop(actor, deadline, &|| before(deadline)).unwrap();
    assert!(job.verifies(actor));
    assert!(original.revalidate_retired(&bus, deadline).is_err());
    let info = pidfd_info(&original.pidfd).unwrap();
    assert!(info.mask & 8 != 0 && info.exit_code == 42 << 8);
    println!(
        "actual failed original actor: stop_job=done; PIDFD EXIT mask={}; raw_exit={}; retirement_refused=true",
        info.mask, info.exit_code
    );
}
