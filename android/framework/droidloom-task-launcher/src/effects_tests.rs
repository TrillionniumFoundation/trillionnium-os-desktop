use super::*;
use std::collections::VecDeque;
use std::os::unix::process::ExitStatusExt;
use std::process::ExitStatus;

// These are ordinary, in-memory transport controls. They create no Android
// process/socket or Ready witness and are not application/runtime evidence.
enum Step {
    Android(AndroidCommand, Result<Output, LaunchError>),
    Exchange(ControlRequest, ControlResponse),
    Wait,
}

struct Script {
    request: LaunchRequest,
    deadline: Instant,
    steps: VecDeque<Step>,
    effects: usize,
    waits: usize,
    starts: usize,
    registrations: usize,
    checkpoints: usize,
    revoked_after: Option<usize>,
    expire_after: Option<usize>,
}

impl Script {
    fn new(request: LaunchRequest, deadline: Instant, steps: Vec<Step>) -> Self {
        Self {
            request,
            deadline,
            steps: steps.into(),
            effects: 0,
            waits: 0,
            starts: 0,
            registrations: 0,
            checkpoints: 0,
            revoked_after: None,
            expire_after: None,
        }
    }

    fn effect(&mut self, deadline: Instant) -> Step {
        assert_eq!(
            deadline, self.deadline,
            "an effect reset the shared deadline"
        );
        self.effects += 1;
        let step = self.steps.pop_front().expect("unexpected extra effect");
        if self.expire_after == Some(self.effects) {
            while Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(1));
            }
        }
        step
    }
}

impl LaunchEffects for Script {
    fn revalidate(
        &mut self,
        request: &LaunchRequest,
        deadline: Instant,
    ) -> Result<(), LaunchError> {
        assert_eq!(request, &self.request);
        assert_eq!(deadline, self.deadline);
        self.checkpoints += 1;
        if self.revoked_after.is_some_and(|at| self.effects >= at) {
            return Err(LaunchError::Control("original owner/epoch changed".into()));
        }
        Ok(())
    }

    fn android(
        &mut self,
        command: &AndroidCommand,
        deadline: Instant,
    ) -> Result<Output, LaunchError> {
        if matches!(command, AndroidCommand::Start { .. }) {
            self.starts += 1;
        }
        match self.effect(deadline) {
            Step::Android(expected, output) => {
                assert_eq!(command, &expected);
                output
            }
            _ => panic!("Android effect occurred in the wrong phase"),
        }
    }

    fn exchange(
        &mut self,
        request: &ControlRequest,
        deadline: Instant,
    ) -> Result<ControlResponse, LaunchError> {
        if matches!(request, ControlRequest::RegisterDirect { .. }) {
            self.registrations += 1;
        }
        match self.effect(deadline) {
            Step::Exchange(expected, response) => {
                assert_eq!(request, &expected);
                Ok(response)
            }
            _ => panic!("task-control effect occurred in the wrong phase"),
        }
    }

    fn wait(&mut self, interval: Duration, deadline: Instant) -> Result<(), LaunchError> {
        assert!(!interval.is_zero() && interval <= DISCOVERY_INTERVAL);
        self.waits += 1;
        assert!(matches!(self.effect(deadline), Step::Wait));
        Ok(())
    }
}

fn request() -> LaunchRequest {
    LaunchRequest {
        package: "org.example.notes".into(),
        component: None,
        resolution: None,
        user: 10,
    }
}

fn output(stdout: &str) -> Output {
    Output {
        status: ExitStatus::from_raw(0),
        stdout: stdout.as_bytes().to_vec(),
        stderr: Vec::new(),
    }
}

fn hello() -> Step {
    Step::Exchange(
        ControlRequest::Hello {
            min_major: PROTOCOL_MAJOR,
            max_major: PROTOCOL_MAJOR,
        },
        ControlResponse::ServerHello {
            major: PROTOCOL_MAJOR,
            minor: 0,
        },
    )
}

fn listing(task: u64, package: &str, user: u32, display: u32, activity: &str) -> String {
    format!(
        "RootTask id={task} displayId={display} userId={user}\n  taskId={task}: {package}/.Launcher userId={user} visible=true topActivity=ComponentInfo{{{package}/{activity}}}\n"
    )
}

fn prefix(request: &LaunchRequest) -> Vec<Step> {
    vec![
        hello(),
        Step::Android(
            AndroidCommand::ListTasks,
            Ok(output(&listing(
                8,
                &request.package,
                request.user,
                0,
                ".Main",
            ))),
        ),
        Step::Android(
            AndroidCommand::ResolvePermissionDialog { user: request.user },
            Ok(output("No activity found\n")),
        ),
        Step::Android(
            AndroidCommand::Start {
                request: request.clone(),
            },
            Ok(output(
                "Status: ok\nActivity: org.example.notes/.Main\nComplete\n",
            )),
        ),
        Step::Android(
            AndroidCommand::ResolveAlias {
                request: request.clone(),
            },
            Ok(output(
                "ActivityInfo:\n name=org.example.notes.Launcher packageName=org.example.notes targetActivity=org.example.notes.Main\nApplicationInfo:\n name=Unrelated\n",
            )),
        ),
    ]
}

fn bound() -> ControlResponse {
    ControlResponse::Bound {
        request_id: 1,
        object: 17,
        task: 9,
        display: 23,
        android_display: 0,
    }
}

fn success_steps(request: &LaunchRequest, response: ControlResponse) -> Vec<Step> {
    let mut steps = prefix(request);
    // The old task also matches the completed activity. Only task 9 was newly
    // observed, and its launcher alias is verified through PackageManager.
    let tasks = format!(
        "{}{}",
        listing(8, &request.package, request.user, 0, ".Main"),
        listing(9, &request.package, request.user, 0, ".Launcher")
    );
    steps.push(Step::Android(AndroidCommand::ListTasks, Ok(output(&tasks))));
    steps.push(Step::Exchange(
        ControlRequest::RegisterDirect {
            request_id: 1,
            package: request.package.clone(),
            task: 9,
            android_display: 0,
        },
        response,
    ));
    steps
}

#[test]
fn prepared_launch_uses_alias_and_binds_only_new_owned_task() {
    let request = request();
    let deadline = Instant::now() + Duration::from_secs(10);
    let mut script = Script::new(request.clone(), deadline, success_steps(&request, bound()));
    assert_eq!(
        launch_prepared(&mut script, &request, deadline).unwrap(),
        TaskBinding {
            object: 17,
            composer_display: 23,
            android_display: 0,
            task: 9,
        }
    );
    assert!(script.steps.is_empty());
    assert_eq!(
        (script.starts, script.registrations, script.waits),
        (1, 1, 0)
    );
    assert_eq!(script.checkpoints, script.effects * 2 + 1);
}

#[test]
fn prepared_launch_rejects_ambiguous_or_wrong_owner_tasks_before_registration() {
    let request = request();
    let deadline = Instant::now() + Duration::from_secs(10);
    let ambiguous = format!(
        "{}{}",
        listing(9, &request.package, request.user, 0, ".Main"),
        listing(10, &request.package, request.user, 0, ".Main")
    );
    let mut steps = prefix(&request);
    steps.push(Step::Android(
        AndroidCommand::ListTasks,
        Ok(output(&ambiguous)),
    ));
    let mut script = Script::new(request.clone(), deadline, steps);
    assert!(matches!(
        launch_prepared(&mut script, &request, deadline),
        Err(LaunchError::Discovery(_))
    ));
    assert_eq!(script.registrations, 0);
    assert!(script.steps.is_empty());

    let foreign = format!(
        "{}{}{}",
        listing(9, &request.package, 0, 0, ".Main"),
        listing(10, &request.package, request.user, 1, ".Main"),
        listing(11, "org.example.notes.other", request.user, 0, ".Main")
    );
    let mut steps = prefix(&request);
    for attempt in 0..ACTIVITY_DISCOVERY_ATTEMPTS {
        steps.push(Step::Android(
            AndroidCommand::ListTasks,
            Ok(output(&foreign)),
        ));
        if attempt + 1 < ACTIVITY_DISCOVERY_ATTEMPTS {
            steps.push(Step::Wait);
        }
    }
    let mut script = Script::new(request.clone(), deadline, steps);
    assert!(matches!(
        launch_prepared(&mut script, &request, deadline),
        Err(LaunchError::Discovery(_))
    ));
    assert_eq!(script.registrations, 0);
    assert_eq!(script.waits, ACTIVITY_DISCOVERY_ATTEMPTS - 1);
    assert!(script.steps.is_empty());
}

#[test]
fn prepared_launch_keeps_one_deadline_and_only_retries_the_fixed_display_race() {
    let request = request();
    for (message, attempts) in [
        (
            "Permission Denial: starting activity with launchDisplayId=0",
            ACTIVITY_DISCOVERY_ATTEMPTS,
        ),
        (
            "Permission Denial: starting activity with launchDisplayId=1",
            1,
        ),
        ("Error: Activity not found", 1),
    ] {
        let deadline = Instant::now() + Duration::from_secs(10);
        let mut steps = prefix(&request);
        steps.truncate(3);
        for attempt in 0..attempts {
            steps.push(Step::Android(
                AndroidCommand::Start {
                    request: request.clone(),
                },
                Ok(Output {
                    status: ExitStatus::from_raw(1 << 8),
                    stdout: Vec::new(),
                    stderr: message.as_bytes().to_vec(),
                }),
            ));
            if attempt + 1 < attempts {
                steps.push(Step::Wait);
            }
        }
        let mut script = Script::new(request.clone(), deadline, steps);
        assert!(matches!(
            launch_prepared(&mut script, &request, deadline),
            Err(LaunchError::Activity(_))
        ));
        assert_eq!(
            (script.starts, script.waits, script.registrations),
            (attempts, attempts - 1, 0)
        );
        assert!(script.steps.is_empty());
    }
}

#[test]
fn prepared_launch_fences_revocation_and_preserves_retirement_errors() {
    let request = request();
    for at in [1, 4, 7] {
        let deadline = Instant::now() + Duration::from_secs(10);
        let mut script = Script::new(request.clone(), deadline, success_steps(&request, bound()));
        script.revoked_after = Some(at);
        assert!(matches!(
            launch_prepared(&mut script, &request, deadline),
            Err(LaunchError::Control(_))
        ));
        assert_eq!(script.effects, at);
        assert_eq!(script.registrations, usize::from(at == 7));
    }
    let deadline = Instant::now() + Duration::from_secs(10);
    let steps = vec![
        hello(),
        Step::Android(
            AndroidCommand::ListTasks,
            Err(LaunchError::Io(std::io::Error::other(
                "unproven original command retirement",
            ))),
        ),
    ];
    let mut script = Script::new(request.clone(), deadline, steps);
    script.revoked_after = Some(2);
    let error = launch_prepared(&mut script, &request, deadline).unwrap_err();
    assert!(matches!(&error, LaunchError::Io(_)));
    assert!(
        error
            .to_string()
            .contains("unproven original command retirement")
    );
    assert_eq!(
        (script.effects, script.checkpoints, script.registrations),
        (2, 4, 0)
    );
}

#[test]
fn prepared_launch_rejects_unmatched_or_malformed_bridge_replies() {
    let request = request();
    for response in [
        ControlResponse::Bound {
            request_id: 2,
            object: 17,
            task: 9,
            display: 23,
            android_display: 0,
        },
        ControlResponse::Bound {
            request_id: 1,
            object: 17,
            task: 10,
            display: 23,
            android_display: 0,
        },
        ControlResponse::Bound {
            request_id: 1,
            object: 17,
            task: 9,
            display: 23,
            android_display: 1,
        },
        ControlResponse::Bound {
            request_id: 1,
            object: 0,
            task: 9,
            display: 23,
            android_display: 0,
        },
        ControlResponse::Bound {
            request_id: 1,
            object: 17,
            task: 9,
            display: 0,
            android_display: 0,
        },
        ControlResponse::ServerHello {
            major: PROTOCOL_MAJOR,
            minor: 0,
        },
    ] {
        let deadline = Instant::now() + Duration::from_secs(10);
        let mut script = Script::new(request.clone(), deadline, success_steps(&request, response));
        assert!(launch_prepared(&mut script, &request, deadline).is_err());
        assert_eq!(script.registrations, 1);
        assert!(script.steps.is_empty());
    }
    let deadline = Instant::now() + Duration::from_secs(10);
    let mut script = Script::new(
        request.clone(),
        deadline,
        vec![Step::Exchange(
            ControlRequest::Hello {
                min_major: PROTOCOL_MAJOR,
                max_major: PROTOCOL_MAJOR,
            },
            ControlResponse::ServerHello {
                major: PROTOCOL_MAJOR + 1,
                minor: 0,
            },
        )],
    );
    assert!(matches!(
        launch_prepared(&mut script, &request, deadline),
        Err(LaunchError::Control(_))
    ));
    assert_eq!((script.effects, script.starts), (1, 0));
}

#[test]
fn prepared_launch_checks_deadline_after_effect_and_bounds_outputs() {
    let request = request();
    for deadline in [
        Instant::now() - Duration::from_millis(1),
        Instant::now() + LAUNCH_LIMIT + Duration::from_secs(1),
    ] {
        let mut script = Script::new(request.clone(), deadline, Vec::new());
        assert!(matches!(
            launch_prepared(&mut script, &request, deadline),
            Err(LaunchError::Deadline)
        ));
        assert_eq!(script.effects, 0);
    }
    let deadline = Instant::now() + Duration::from_secs(1);
    let mut script = Script::new(
        request.clone(),
        deadline,
        vec![
            hello(),
            Step::Android(AndroidCommand::ListTasks, Ok(output(""))),
        ],
    );
    script.expire_after = Some(2);
    assert!(matches!(
        launch_prepared(&mut script, &request, deadline),
        Err(LaunchError::Deadline)
    ));
    assert_eq!(
        (script.effects, script.starts, script.registrations),
        (2, 0, 0)
    );

    for stdout in [vec![b'x'; COMMAND_OUTPUT_LIMIT + 1], vec![0xff]] {
        let deadline = Instant::now() + Duration::from_secs(10);
        let mut script = Script::new(
            request.clone(),
            deadline,
            vec![
                hello(),
                Step::Android(
                    AndroidCommand::ListTasks,
                    Ok(Output {
                        status: ExitStatus::from_raw(0),
                        stdout,
                        stderr: Vec::new(),
                    }),
                ),
            ],
        );
        assert!(matches!(
            launch_prepared(&mut script, &request, deadline),
            Err(LaunchError::Activity(_))
        ));
        assert_eq!(
            (script.effects, script.starts, script.registrations),
            (2, 0, 0)
        );
    }
}

#[test]
fn prepared_commands_keep_literal_scope_and_invalid_inputs_have_no_effects() {
    let mut request = request();
    let args = AndroidCommand::Start {
        request: request.clone(),
    }
    .arguments()
    .unwrap();
    assert_eq!(
        args,
        [
            "activity",
            "start-activity",
            "-W",
            "--display",
            "0",
            "--windowingMode",
            "5",
            "--user",
            "10",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            "-p",
            "org.example.notes"
        ]
    );
    request.component = Some("org.example.notes/.Main".into());
    request.resolution = Some((1024, 768));
    assert_eq!(
        AndroidCommand::Start {
            request: request.clone()
        }
        .arguments()
        .unwrap(),
        [
            "activity",
            "start-activity",
            "-W",
            "--display",
            "0",
            "--windowingMode",
            "5",
            "--user",
            "10",
            "-S",
            "--droidloom-resolution",
            "1024x768",
            "-n",
            "org.example.notes/.Main"
        ]
    );
    assert_eq!(
        AndroidCommand::ResolveAlias {
            request: request.clone()
        }
        .arguments()
        .unwrap(),
        [
            "package",
            "resolve-activity",
            "--user",
            "10",
            "-n",
            "org.example.notes/.Main"
        ]
    );
    for invalid in [
        LaunchRequest {
            component: Some("org.other/.Main".into()),
            ..request.clone()
        },
        LaunchRequest {
            resolution: Some((0, 768)),
            ..request.clone()
        },
        LaunchRequest {
            user: u32::MAX,
            ..request.clone()
        },
        LaunchRequest {
            package: "x".repeat(256),
            component: None,
            ..request.clone()
        },
        LaunchRequest {
            component: Some(format!(
                "org.example.notes/{}",
                "X".repeat(MAX_RECORD_BYTES)
            )),
            ..request.clone()
        },
    ] {
        let deadline = Instant::now() + Duration::from_secs(10);
        let mut script = Script::new(invalid.clone(), deadline, Vec::new());
        assert!(launch_prepared(&mut script, &invalid, deadline).is_err());
        assert_eq!(script.effects, 0);
    }
}
