use trillionnium_ui_contracts::{
    AppWindow, CompositorState, DesktopBoundary, FocusController, FocusOwner, Notification,
    NotificationCenter, NotificationId, ShellState, Task, TaskState, WindowState,
};

#[test]
fn task_cards_require_observed_lifecycle_and_show_real_failures() {
    let mut task = Task::new(7);
    assert!(!task.observe(TaskState::Completed, "assistant said done"));
    assert_eq!(task.state, TaskState::Pending);

    assert!(task.observe(TaskState::Running, "process spawned; pid=123"));
    assert!(task.observe(TaskState::Failed, "waitpid: exit code 17"));
    assert_eq!(task.state, TaskState::Failed);
    assert!(task.state.is_terminal());
    assert_eq!(task.observed_detail, "waitpid: exit code 17");
    assert!(!task.observe(TaskState::Completed, "later text claimed success"));
}

#[test]
fn cancellation_is_a_request_until_the_process_exit_is_observed() {
    let mut task = Task::new(9);
    assert!(task.observe(TaskState::Running, "pid=900"));
    assert!(task.observe(TaskState::CancelRequested, "SIGKILL sent"));
    assert!(!task.state.is_terminal());
    assert!(task.observe(TaskState::Cancelled, "waitpid: SIGKILL"));
    assert!(task.state.is_terminal());
}

#[test]
fn chinese_ime_commit_is_focused_and_not_duplicated() {
    let mut focus = FocusController::default();
    focus.focus(FocusOwner::ShellComposer);
    assert!(focus.update_preedit("ni"));
    assert!(focus.commit("你"));
    assert_eq!(focus.shell_text(), "你");
    assert_eq!(focus.preedit(), "");

    // Switching focus cancels an uncommitted candidate rather than leaking it
    // into the Notes app.  A repeated redraw cannot duplicate "你".
    assert!(focus.update_preedit("hao"));
    focus.focus(FocusOwner::App(42));
    assert_eq!(focus.preedit(), "");
    assert_eq!(focus.shell_text(), "你");
    assert_eq!(focus.app_text(42), "");
    assert!(focus.update_preedit("shi"));
    assert!(focus.commit("是"));
    assert_eq!(focus.app_text(42), "是");

    focus.focus(FocusOwner::None);
    assert!(!focus.commit("丢弃"));
    assert_eq!(focus.app_text(42), "是");
}

#[test]
fn notifications_are_event_idempotent_and_bounded() {
    let mut notices = NotificationCenter::new(2);
    assert!(notices.push(Notification {
        id: NotificationId(1),
        task_id: Some(3),
        message: "RUNNING".into(),
    }));
    assert!(!notices.push(Notification {
        id: NotificationId(1),
        task_id: Some(3),
        message: "RUNNING (snapshot replay)".into(),
    }));
    assert!(notices.push(Notification {
        id: NotificationId(2),
        task_id: Some(3),
        message: "FAILED: exit code 17".into(),
    }));
    assert!(notices.push(Notification {
        id: NotificationId(3),
        task_id: None,
        message: "session offline".into(),
    }));
    let messages: Vec<_> = notices
        .items()
        .map(|notice| notice.message.as_str())
        .collect();
    assert_eq!(messages, ["FAILED: exit code 17", "session offline"]);

    // Evicted events no longer consume dedupe memory forever; a later event
    // with the same id is accepted as a fresh bounded notification.
    assert!(notices.push(Notification {
        id: NotificationId(1),
        task_id: Some(3),
        message: "RUNNING again".into(),
    }));
    assert_eq!(notices.items().count(), 2);
}

#[test]
fn shell_restart_does_not_terminate_independent_app_windows() {
    let mut desktop = DesktopBoundary::default();
    assert!(desktop.launch_app(11, 1));
    assert!(desktop.launch_app(12, 2));
    let before = desktop.apps.clone();
    let compositor_generation = desktop.compositor_generation;

    desktop.crash_shell();
    assert_eq!(desktop.shell, ShellState::Crashed);
    desktop.restart_shell();
    assert_eq!(desktop.shell, ShellState::Running);
    assert!(desktop.shell_generation > 1);
    assert_eq!(desktop.compositor_generation, compositor_generation);
    assert_eq!(desktop.apps, before);
}

#[test]
fn compositor_crash_and_gpu_reset_disconnect_without_fake_reattach() {
    let mut desktop = DesktopBoundary::default();
    assert!(desktop.launch_app(21, 4));
    assert!(desktop.launch_app(22, 4));
    let old_generation = desktop.compositor_generation;

    desktop.crash_compositor();
    assert_eq!(desktop.compositor, CompositorState::Crashed);
    assert!(desktop
        .apps
        .values()
        .all(|app| app.state == WindowState::Disconnected));
    assert!(!desktop.reconnect_app(21));

    desktop.restart_compositor();
    assert_eq!(desktop.compositor, CompositorState::Running);
    assert!(desktop.compositor_generation > old_generation);
    assert!(desktop
        .apps
        .values()
        .all(|app| app.state == WindowState::Disconnected));
    assert!(desktop.reconnect_app(21));
    assert_eq!(
        desktop.apps[&21].state,
        WindowState::Attached {
            compositor_generation: desktop.compositor_generation
        }
    );
    assert_eq!(desktop.apps[&22].state, WindowState::Disconnected);

    desktop.gpu_reset();
    assert_eq!(desktop.compositor, CompositorState::GpuReset);
    assert!(desktop
        .apps
        .values()
        .all(|app| { matches!(app.state, WindowState::Disconnected) }));
    desktop.recover_gpu();
    assert_eq!(desktop.compositor, CompositorState::Running);
    assert!(desktop
        .apps
        .values()
        .all(|app| { matches!(app.state, WindowState::Disconnected) }));
}

#[test]
fn app_exit_is_distinct_from_window_disconnect_and_cannot_reopen_closed_app() {
    let mut desktop = DesktopBoundary::default();
    assert!(desktop.launch_app(31, 3));
    assert!(desktop.close_app(31));
    assert_eq!(desktop.apps[&31].state, WindowState::Closed);
    assert!(!desktop.reconnect_app(31));
    assert!(!desktop.close_app(31));
}

#[test]
fn app_window_contract_keeps_workspace_identity_across_reconnect() {
    let window = AppWindow {
        id: 5,
        workspace: 7,
        state: WindowState::Attached {
            compositor_generation: 2,
        },
    };
    assert_eq!(window.id, 5);
    assert_eq!(window.workspace, 7);
    assert_eq!(
        window.state,
        WindowState::Attached {
            compositor_generation: 2
        }
    );
}
