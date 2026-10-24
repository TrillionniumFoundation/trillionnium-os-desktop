use super::*;

fn frame(
    ctx: &egui::Context,
    input: &mut NotesInput,
    text: &mut String,
    revision: u64,
    events: Vec<egui::Event>,
) -> Option<(u64, String)> {
    let mut result = None;
    let raw = egui::RawInput {
        focused: true,
        screen_rect: Some(egui::Rect::from_min_size(
            egui::Pos2::ZERO,
            egui::vec2(600.0, 400.0),
        )),
        events,
        ..Default::default()
    };
    let _ = ctx.run(raw, |ctx| {
        input.begin(ctx, text, revision);
        egui::CentralPanel::default().show(ctx, |ui| {
            let response = ui.add(egui::TextEdit::multiline(text).id(egui::Id::new(EDITOR_ID)));
            result = input.finish(ctx, text, response.changed());
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
