use super::*;

fn frame(
    ctx: &egui::Context,
    input: &mut NotesInput,
    text: &mut String,
    revision: u64,
    events: Vec<egui::Event>,
) -> Option<(u64, String)> {
    frame_after_poll(ctx, input, text, revision, revision, None, events)
}

fn frame_after_poll(
    ctx: &egui::Context,
    input: &mut NotesInput,
    text: &mut String,
    before_revision: u64,
    after_revision: u64,
    local_ack: Option<(u64, u64)>,
    events: Vec<egui::Event>,
) -> Option<(u64, String)> {
    let mut result = None;
    let mut raw = egui::RawInput {
        focused: true,
        screen_rect: Some(egui::Rect::from_min_size(
            egui::Pos2::ZERO,
            egui::vec2(600.0, 400.0),
        )),
        events,
        ..Default::default()
    };
    input.raw_input_hook(ctx, &mut raw);
    let _ = ctx.run(raw, |ctx| {
        input.begin(ctx, text, before_revision);
        if let Some((from, to)) = local_ack {
            input.accept_local_revision(from, to);
        }
        input.prepare_editor(ctx, text, after_revision);
        egui::CentralPanel::default().show(ctx, |ui| {
            let response = ui.add(egui::TextEdit::multiline(text).id(egui::Id::new(EDITOR_ID)));
            result = input.finish(ctx, text, response.changed(), response.lost_focus());
        });
    });
    result
}

fn setup(text: &mut String) -> (egui::Context, NotesInput) {
    let ctx = egui::Context::default();
    let mut input = NotesInput::default();
    frame(&ctx, &mut input, text, 4, vec![]);
    ctx.memory_mut(|memory| memory.request_focus(egui::Id::new(EDITOR_ID)));
    frame(&ctx, &mut input, text, 4, vec![]);
    let mut state = TextEditState::load(&ctx, egui::Id::new(EDITOR_ID)).unwrap();
    state
        .cursor
        .set_char_range(Some(egui::text::CCursorRange::two(
            egui::text::CCursor::new(0),
            egui::text::CCursor::new(text.chars().count()),
        )));
    state.store(&ctx, egui::Id::new(EDITOR_ID));
    (ctx, input)
}

#[test]
fn actual_egui_preedit_is_visible_but_only_commit_returns_original_revision() {
    let mut text = "old selection".to_owned();
    let (ctx, mut input) = setup(&mut text);
    assert!(frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![
            egui::Event::Ime(egui::ImeEvent::Enabled),
            egui::Event::Ime(egui::ImeEvent::Preedit("nihao".into())),
        ]
    )
    .is_none());
    assert_eq!(text, "nihao");
    assert!(input.composing());
    // A newer worker observation must not become the composition's CAS base.
    assert!(frame(
        &ctx,
        &mut input,
        &mut text,
        5,
        vec![egui::Event::Ime(egui::ImeEvent::Preedit(String::new())),]
    )
    .is_none());
    let edit = frame(
        &ctx,
        &mut input,
        &mut text,
        5,
        vec![
            egui::Event::Ime(egui::ImeEvent::Commit("你好".into())),
            egui::Event::Ime(egui::ImeEvent::Disabled),
        ],
    )
    .unwrap();
    assert_eq!(edit, (4, "你好".into()));
    assert_eq!(text, "你好");
    assert!(!input.composing());
}

#[test]
fn actual_egui_cancel_preserves_committed_selection_and_never_publishes_preedit() {
    let mut text = "保留原文".to_owned();
    let (ctx, mut input) = setup(&mut text);
    let before = TextEditState::load(&ctx, egui::Id::new(EDITOR_ID))
        .unwrap()
        .cursor
        .char_range();
    assert!(frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![
            egui::Event::Ime(egui::ImeEvent::Enabled),
            egui::Event::Ime(egui::ImeEvent::Preedit("temporary".into())),
        ]
    )
    .is_none());
    assert_eq!(text, "temporary");
    assert!(frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![egui::Event::Ime(egui::ImeEvent::Disabled),]
    )
    .is_none());
    assert_eq!(text, "保留原文");
    assert!(!input.composing());
    assert_eq!(
        TextEditState::load(&ctx, egui::Id::new(EDITOR_ID))
            .unwrap()
            .cursor
            .char_range(),
        before
    );
}

#[test]
fn oversize_native_paste_rejects_the_whole_replacement_and_retains_selection() {
    let mut text = "selected text".to_owned();
    let (ctx, mut input) = setup(&mut text);
    let before = TextEditState::load(&ctx, egui::Id::new(EDITOR_ID))
        .unwrap()
        .cursor
        .char_range();
    assert!(frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![egui::Event::Paste("中".repeat(1400)),]
    )
    .is_none());
    assert_eq!(text, "selected text");
    assert!(input.notice().is_some());
    assert_eq!(
        TextEditState::load(&ctx, egui::Id::new(EDITOR_ID))
            .unwrap()
            .cursor
            .char_range(),
        before
    );
    // A following ordinary replacement still works on the original selection.
    assert_eq!(
        frame(
            &ctx,
            &mut input,
            &mut text,
            4,
            vec![egui::Event::Paste("正常".into())]
        ),
        Some((4, "正常".into()))
    );
}

#[test]
fn empty_commit_cannot_publish_leftover_preedit() {
    let mut text = "original".to_owned();
    let (ctx, mut input) = setup(&mut text);
    frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![
            egui::Event::Ime(egui::ImeEvent::Enabled),
            egui::Event::Ime(egui::ImeEvent::Preedit("uncommitted".into())),
        ],
    );
    assert!(frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![egui::Event::Ime(egui::ImeEvent::Commit(String::new())),]
    )
    .is_none());
    assert_eq!(text, "original");
}

#[test]
fn one_native_batch_commits_then_defers_new_preedit_without_saving_it() {
    let mut text = "original".to_owned();
    let (ctx, mut input) = setup(&mut text);
    assert_eq!(
        frame(
            &ctx,
            &mut input,
            &mut text,
            4,
            vec![
                egui::Event::Ime(egui::ImeEvent::Enabled),
                egui::Event::Ime(egui::ImeEvent::Preedit("ni".into())),
                egui::Event::Ime(egui::ImeEvent::Commit("你".into())),
                egui::Event::Ime(egui::ImeEvent::Preedit("hao".into())),
            ]
        ),
        Some((4, "你".into()))
    );
    assert_eq!(text, "你");
    // The original worker acknowledged exactly that local edit. A following
    // composition can advance to that accepted revision, never an external one.
    assert!(frame_after_poll(&ctx, &mut input, &mut text, 4, 5, Some((4, 5)), vec![]).is_none());
    assert_eq!(text, "你hao");
    assert!(input.composing());
    assert_eq!(
        frame(
            &ctx,
            &mut input,
            &mut text,
            5,
            vec![
                egui::Event::Ime(egui::ImeEvent::Commit("好".into())),
                egui::Event::Ime(egui::ImeEvent::Disabled),
            ]
        ),
        Some((5, "你好".into()))
    );
}

#[test]
fn one_native_batch_preedit_then_disabled_never_replays_cancelled_text() {
    let mut text = "保留原文".to_owned();
    let (ctx, mut input) = setup(&mut text);
    let selection = TextEditState::load(&ctx, egui::Id::new(EDITOR_ID))
        .unwrap()
        .cursor
        .char_range();
    assert!(frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![
            egui::Event::Ime(egui::ImeEvent::Enabled),
            egui::Event::Ime(egui::ImeEvent::Preedit("temporary".into())),
            egui::Event::Ime(egui::ImeEvent::Disabled),
        ]
    )
    .is_none());
    assert_eq!(text, "保留原文");
    assert_eq!(
        TextEditState::load(&ctx, egui::Id::new(EDITOR_ID))
            .unwrap()
            .cursor
            .char_range(),
        selection
    );
    assert!(input.cancelled());
    assert!(!input.composing());
    // A later accepted transaction still reaches the real native editor.
    assert_eq!(
        frame(
            &ctx,
            &mut input,
            &mut text,
            4,
            vec![egui::Event::Paste("确认后的文字".into())]
        ),
        Some((4, "确认后的文字".into()))
    );
}

#[test]
fn ordinary_input_uses_revision_after_the_workers_own_acknowledgement() {
    let mut text = "saved local text".to_owned();
    let (ctx, mut input) = setup(&mut text);
    assert_eq!(
        frame_after_poll(
            &ctx,
            &mut input,
            &mut text,
            4,
            5,
            Some((4, 5)),
            vec![egui::Event::Text("next local edit".into())]
        ),
        Some((5, "next local edit".into()))
    );
}

#[test]
fn cancelled_second_composition_keeps_the_earlier_same_batch_commit() {
    let mut text = "original".to_owned();
    let (ctx, mut input) = setup(&mut text);
    assert_eq!(
        frame(
            &ctx,
            &mut input,
            &mut text,
            4,
            vec![
                egui::Event::Ime(egui::ImeEvent::Enabled),
                egui::Event::Ime(egui::ImeEvent::Preedit("first".into())),
                egui::Event::Ime(egui::ImeEvent::Commit("已确认".into())),
                egui::Event::Ime(egui::ImeEvent::Preedit("never committed".into())),
                egui::Event::Ime(egui::ImeEvent::Disabled),
            ]
        ),
        Some((4, "已确认".into()))
    );
    assert!(frame_after_poll(&ctx, &mut input, &mut text, 4, 5, Some((4, 5)), vec![]).is_none());
    assert_eq!(text, "已确认");
    assert!(!input.composing());
}

#[test]
fn first_oversized_raw_batch_is_refused_without_losing_committed_text() {
    let mut text = "last committed text".to_owned();
    let (ctx, mut input) = setup(&mut text);
    let events = (0..MAX_QUEUED_EVENTS + 1)
        .map(|_| egui::Event::Ime(egui::ImeEvent::Commit("中".into())))
        .collect();
    assert!(frame(&ctx, &mut input, &mut text, 4, events).is_none());
    assert_eq!(text, "last committed text");
    assert!(input.notice().unwrap().contains("未接收"));
    assert!(input.raw_frames.is_empty());
}

#[test]
fn split_raw_frames_keep_each_fragments_focus_and_modifier_state() {
    let ctx = egui::Context::default();
    let _ = ctx.run(egui::RawInput::default(), |_| {});
    let mut input = NotesInput::default();
    let mut raw = egui::RawInput {
        focused: false,
        modifiers: egui::Modifiers::default(),
        events: vec![
            egui::Event::Key {
                key: egui::Key::A,
                physical_key: None,
                pressed: true,
                repeat: false,
                modifiers: egui::Modifiers::CTRL,
            },
            egui::Event::Ime(egui::ImeEvent::Commit("你".into())),
            egui::Event::Ime(egui::ImeEvent::Preedit("hao".into())),
            egui::Event::Key {
                key: egui::Key::A,
                physical_key: None,
                pressed: false,
                repeat: false,
                modifiers: egui::Modifiers::default(),
            },
            egui::Event::WindowFocused(false),
        ],
        ..Default::default()
    };
    input.raw_input_hook(&ctx, &mut raw);
    assert!(raw.focused);
    assert!(raw.modifiers.ctrl);
    assert_eq!(raw.events.len(), 2);
    let deferred = input.raw_frames.front().unwrap();
    assert!(!deferred.focused);
    assert!(!deferred.modifiers.ctrl);
    assert_eq!(deferred.events.len(), 3);
}

#[test]
fn repeated_update_in_one_egui_frame_cannot_publish_the_transaction_twice() {
    let mut text = "original".to_owned();
    let (ctx, mut input) = setup(&mut text);
    let mut raw = egui::RawInput {
        focused: true,
        events: vec![egui::Event::Paste("once".into())],
        ..Default::default()
    };
    input.raw_input_hook(&ctx, &mut raw);
    let mut result = None;
    let _ = ctx.run(raw, |ctx| {
        input.begin(ctx, &mut text, 4);
        input.prepare_editor(ctx, &text, 4);
        egui::CentralPanel::default().show(ctx, |ui| {
            let response =
                ui.add(egui::TextEdit::multiline(&mut text).id(egui::Id::new(EDITOR_ID)));
            result = input.finish(ctx, &mut text, response.changed(), response.lost_focus());
            input.begin(ctx, &mut text, 4);
            input.prepare_editor(ctx, &text, 4);
            assert!(input.finish(ctx, &mut text, true, false).is_none());
        });
    });
    assert_eq!(result, Some((4, "once".into())));
}

#[test]
fn pointer_caret_move_before_commit_never_publishes_the_old_preedit() {
    let mut text = "original".to_owned();
    let (ctx, mut input) = setup(&mut text);
    assert!(frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![
            egui::Event::Ime(egui::ImeEvent::Enabled),
            egui::Event::Ime(egui::ImeEvent::Preedit("temporary".into()))
        ],
    )
    .is_none());
    assert_eq!(text, "temporary");
    // Obtain the real widget's bounds, then deliver actual pointer input. No
    // private egui IME anchor or fabricated TextEdit state is changed here.
    let mut rectangle = egui::Rect::NOTHING;
    let mut raw = egui::RawInput {
        focused: true,
        ..Default::default()
    };
    input.raw_input_hook(&ctx, &mut raw);
    let _ = ctx.run(raw, |ctx| {
        input.begin(ctx, &mut text, 4);
        input.prepare_editor(ctx, &text, 4);
        egui::CentralPanel::default().show(ctx, |ui| {
            let response =
                ui.add(egui::TextEdit::multiline(&mut text).id(egui::Id::new(EDITOR_ID)));
            rectangle = response.rect;
            assert!(input
                .finish(ctx, &mut text, response.changed(), response.lost_focus())
                .is_none());
        });
    });
    let position = rectangle.left_top() + egui::vec2(32.0, 8.0);
    let edit = frame(
        &ctx,
        &mut input,
        &mut text,
        4,
        vec![
            egui::Event::PointerMoved(position),
            egui::Event::PointerButton {
                pos: position,
                button: egui::PointerButton::Primary,
                pressed: true,
                modifiers: egui::Modifiers::default(),
            },
            egui::Event::PointerButton {
                pos: position,
                button: egui::PointerButton::Primary,
                pressed: false,
                modifiers: egui::Modifiers::default(),
            },
            egui::Event::Ime(egui::ImeEvent::Commit("确认".into())),
        ],
    );
    assert_ne!(
        edit,
        Some((4, "temporary".into())),
        "a rejected native Commit must never turn its residual prediction into a saved local edit"
    );
}
