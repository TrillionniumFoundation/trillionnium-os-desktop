//! One independent client window per app process. No embedded webview or Node.
#[path = "../../activation.rs"]
mod activation;
#[path = "../../host_fonts.rs"]
mod host_fonts;
mod notes_input;
mod notes_organ;
use eframe::egui::{self, RichText};
use std::io::Write;
use trill_ui_core::{AppKind, Workspace};

struct ClientWindow {
    activation: activation::ActivationGuard,
    kind: AppKind,
    workspace: Workspace,
    task_id: u64,
    notes: String,
    notes_input: notes_input::NotesInput,
    notes_organ: Option<notes_organ::NotesAppChannel>,
    notes_browser: bool,
    left: String,
    right: String,
    result: String,
    focused_input: String,
    terminal_input: String,
    terminal_output: Vec<String>,
    terminal_close_requested: bool,
    terminal_preedit_active: bool,
    first_frame_emitted: bool,
}

impl eframe::App for ClientWindow {
    fn raw_input_hook(&mut self, ctx: &egui::Context, raw: &mut egui::RawInput) {
        if self.notes_organ.is_some() {
            self.notes_input.raw_input_hook(ctx, raw);
        }
    }

    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        if self
            .notes_organ
            .as_ref()
            .is_some_and(|organ| organ.close_if_session_ended(ctx))
        {
            // Original Session ended: do not run input/edit/close-cancel paths.
            return;
        }
        self.notes_input.begin_activation(ctx, &mut self.activation);
        self.terminal_preedit_active = self.activation.composing();
        let mut notes_updated = false;
        if let Some(organ) = &mut self.notes_organ {
            let preserve = self
                .notes_input
                .begin(ctx, &mut self.notes, organ.revision());
            let updated = organ.poll();
            if let Some((from, to)) = organ.accepted_local_revision() {
                self.notes_input.accept_local_revision(from, to);
            }
            if !preserve && (updated || self.notes_input.cancelled()) {
                self.notes = organ.text().to_owned();
                notes_updated = true;
            }
        }
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading(self.kind.name());
            ui.label(format!("Workspace: {} · host task #{}", self.workspace.name(), self.task_id));
            ui.small("This is a separate native Rust app process/window, not a secure workspace container.");
            ui.small(host_fonts::status_label(ctx));
            ui.separator();
            match self.kind {
                AppKind::Notes => {
                    let label = ui.horizontal(|ui| {
                        let label = ui.label("Notes / 笔记 · try composing Chinese with your host IME");
                        if let Some(organ) = &mut self.notes_organ {
                            if organ.has_document_storage()
                                && self.activation.activated(&ui.button("打开已保存笔记"))
                            {
                                self.notes_browser = true;
                                organ.refresh_saved_documents();
                            }
                        }
                        label
                    }).inner;
                    if let Some(organ) = &self.notes_organ {
                        self.notes_input.prepare_editor(ctx, &self.notes, organ.revision());
                    }
                    let editor = ui.add_enabled(
                        !self.notes_organ.as_ref().is_some_and(|organ| organ.restore_pending()),
                        egui::TextEdit::multiline(&mut self.notes)
                            .id(egui::Id::new(notes_input::EDITOR_ID))
                            .desired_rows(17)
                            .desired_width(f32::INFINITY)
                            .hint_text("中文输入、候选词、焦点测试……"),
                    ).labelled_by(label.id);
                    if let Some(organ) = &mut self.notes_organ {
                        if let Some((revision, text)) = self.notes_input.finish(ctx, &mut self.notes, editor.changed(), editor.lost_focus()) {
                            if !organ.local_edit_at(revision, text) {
                                self.notes = organ.text().to_owned();
                            }
                        }
                        if self.notes_input.cancelled() { self.notes = organ.text().to_owned(); }
                        if organ.has_conflict() {
                            ui.horizontal(|ui| {
                                let ready = !self.notes_input.composing();
                                if self.activation.activated(&ui.add_enabled(ready, egui::Button::new("确认保留我的编辑"))) {
                                    organ.keep_local_after_conflict();
                                }
                                if self.activation.activated(&ui.add_enabled(ready, egui::Button::new("放弃未保存编辑，加载已保存内容"))) {
                                    organ.discard_local_after_conflict();
                                    self.notes = organ.text().to_owned();
                                }
                            });
                        }
                        if self.notes_input.composing() { ui.small("输入法组词中；确认后的文字才会保存。"); }
                        if let Some(notice) = self.notes_input.notice() { ui.small(notice); }
                        ui.small(format!("Document revision: {} · private Notes destination", organ.revision()));
                        ui.small("External edits require the original Hepta owner. This document is limited to 4096 UTF-8 bytes.");
                        ui.small(organ.storage_status());
                    }
                    ui.small(if editor.has_focus() {
                        "Keyboard focus: NOTES editor (IME target)"
                    } else {
                        "Keyboard focus: inactive; click Notes editor to compose"
                    });
                    if self.notes_organ.is_none() {
                        ui.small("Local unsaved memory only. Closing this app discards notes.");
                    }
                }
                AppKind::Calculator => {
                    ui.horizontal(|ui| {
                        let a = ui.label("A");
                        ui.text_edit_singleline(&mut self.left).labelled_by(a.id);
                        let b = ui.label("B");
                        ui.text_edit_singleline(&mut self.right).labelled_by(b.id);
                    });
                    ui.horizontal(|ui| {
                        for (label, op) in [("+", '+'), ("−", '-'), ("×", '*'), ("÷", '/')] {
                            if self.activation.activated(&ui.button(label)) {
                                self.calculate(op);
                            }
                        }
                    });
                    ui.label(RichText::new(&self.result).size(20.0));
                    ui.separator();
                    let label = ui.label("Keyboard and IME focus probe / 输入法焦点");
                    let ime_probe = ui.add(
                        egui::TextEdit::singleline(&mut self.focused_input)
                            .id(egui::Id::new("calculator-ime-focus")),
                    ).labelled_by(label.id);
                    ui.small(if ime_probe.has_focus() {
                        "Keyboard focus: calculator IME probe"
                    } else {
                        "Keyboard focus: calculator IME probe inactive"
                    });
                    ui.small("Click between numeric and Chinese text controls to test focus.");
                }
                AppKind::Terminal => self.restricted_terminal(ui, ctx),
            }
        });
        self.show_saved_notes(ctx);
        if let Some(organ) = &mut self.notes_organ {
            if organ.close_requested() {
                egui::Window::new("关闭笔记")
                    .collapsible(false)
                    .resizable(false)
                    .show(ctx, |ui| {
                        match organ.close_state() {
                            notes_organ::NotesCloseState::Saving => {
                                ui.label("正在保存最后的编辑，保存完成后将关闭窗口。");
                                if self.activation.activated(&ui.button("停止等待并关闭")) {
                                    organ.discard_and_close();
                                }
                                ui.small("停止等待时，最后的修改可能尚未保存。");
                            }
                            notes_organ::NotesCloseState::Unsaved => {
                                ui.label("当前编辑尚未确认保存。继续编辑可保留窗口中的内容。");
                                if self
                                    .activation
                                    .activated(&ui.button("关闭并舍弃未保存编辑"))
                                {
                                    organ.discard_and_close();
                                }
                            }
                            notes_organ::NotesCloseState::Ready => {}
                        }
                        if self.activation.activated(&ui.button("继续编辑")) {
                            organ.keep_open();
                        }
                    });
            }
            // This follows TextEdit so a final edit and close in one frame
            // cannot bypass the worker's durable-save acknowledgement.
            organ.input_queue_changed(self.notes_input.queued_input());
            organ.handle_close(ctx);
        }
        // Signal only AFTER the first UI layout has completed successfully,
        // not on process spawn or before building the widget tree.
        // This still does not attest that a compositor presented the frame.
        if !self.first_frame_emitted {
            self.first_frame_emitted = true;
            // The session owns this child's stdout pipe. Ignore BrokenPipe:
            // session failure MUST NOT crash an independently running app.
            let _ = std::io::stdout().write_all(b"TRILL_UI_FIRST_FRAME_V1\n");
        }
        if notes_updated {
            if let Some(organ) = &self.notes_organ {
                // Independent layout witness after the widget tree consumed
                // this document. It is still not compositor pixel evidence.
                let marker = format!(
                    "TRILL_NOTES_LAYOUT_V1:{}:{}\n",
                    organ.revision(),
                    trill_ui_core::notes::sha256_hex(self.notes.as_bytes())
                );
                let _ = std::io::stdout().write_all(marker.as_bytes());
            }
        }
    }
}

/// Guard the *visible* terminal log. A TextEdit is not a security boundary:
/// pasted text or future input adapters may contain embedded newlines,
/// terminal control codes or bidi overrides that forge process-status lines.
/// Preserve normal CJK text and punctuation.
fn command_is_safe_for_log(command: &str) -> bool {
    !command.chars().any(|character| {
        character.is_control()
            || matches!(
                character as u32,
                0x200E..=0x200F | 0x2028..=0x202E | 0x2066..=0x2069
            )
    })
}

impl ClientWindow {
    const MAX_TERMINAL_LINES: usize = 256;

    fn show_saved_notes(&mut self, ctx: &egui::Context) {
        if !self.notes_browser {
            return;
        }
        let Some(organ) = &mut self.notes_organ else {
            return;
        };
        let mut open = true;
        let mut selected = None;
        egui::Window::new("打开已保存笔记")
            .id(egui::Id::new("notes-saved-documents"))
            .open(&mut open)
            .default_width(540.0)
            .show(ctx, |ui| {
                ui.label("选择之前保存的笔记，在当前空白窗口打开副本。原笔记保持不变。");
                if !organ.can_restore_saved() {
                    ui.label("当前窗口已编辑或暂不可用。请在桌面新建笔记窗口后打开副本。");
                }
                if self.activation.activated(
                    &ui.add_enabled(!organ.saved_list_pending(), egui::Button::new("刷新列表")),
                ) {
                    organ.refresh_saved_documents();
                }
                if organ.saved_list_pending() {
                    ui.label("正在读取已保存笔记……");
                }
                if let Some(message) = organ.saved_list_error() {
                    ui.colored_label(egui::Color32::YELLOW, message);
                }
                let listing = organ.saved_documents();
                if listing.unavailable > 0 {
                    ui.small(format!(
                        "{} 份笔记正在使用或无法读取；关闭旧窗口后可刷新。",
                        listing.unavailable
                    ));
                }
                if listing.truncated {
                    ui.small("列表达到上限；较早的笔记可能未列出。");
                }
                if listing.documents.is_empty() && !organ.saved_list_pending() {
                    ui.label("暂无可打开的已保存笔记。");
                }
                egui::ScrollArea::vertical()
                    .max_height(320.0)
                    .show(ui, |ui| {
                        for document in &listing.documents {
                            ui.push_id(document.target.destination_id(), |ui| {
                                ui.horizontal(|ui| {
                                    if self.activation.activated(&ui.add_enabled(
                                        organ.can_restore_saved(),
                                        egui::Button::new("打开副本"),
                                    )) {
                                        selected = Some(document.clone());
                                    }
                                    ui.vertical(|ui| {
                                        ui.label(if document.preview.is_empty() {
                                            "空白笔记"
                                        } else {
                                            &document.preview
                                        });
                                        ui.small(saved_notes_age(document.saved_unix_ms));
                                    });
                                });
                            });
                            ui.separator();
                        }
                    });
            });
        if let Some(document) = selected {
            if organ.restore_saved_document(document) {
                open = false;
            }
        }
        self.notes_browser = open;
    }

    fn terminal_line(&mut self, line: impl Into<String>) {
        if self.terminal_output.len() >= Self::MAX_TERMINAL_LINES {
            self.terminal_output.remove(0);
        }
        self.terminal_output.push(line.into());
    }

    fn restricted_terminal(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        // Idempotent for the app update and direct widget regression tests.
        // Read the lifecycle before TextEdit can consume the raw IME events.
        self.activation.begin_frame(ctx);
        self.terminal_preedit_active = self.activation.composing();
        ui.label("Restricted task terminal / 受限任务终端");
        ui.small("This is an explicit Rust app process. It does not invoke /bin/sh, pipes, redirects, or arbitrary host commands.");
        ui.small("Allowlist: help, status, version, echo <text>, clear, exit");
        ui.separator();
        egui::ScrollArea::vertical()
            .id_salt("restricted-terminal-output")
            .max_height(310.0)
            .stick_to_bottom(true)
            .show(ui, |ui| {
                for line in &self.terminal_output {
                    ui.monospace(line);
                }
            });
        ui.separator();
        let label = ui.label("Command / 命令");
        ui.horizontal(|ui| {
            ui.add(
                egui::TextEdit::singleline(&mut self.terminal_input)
                    .id(egui::Id::new("restricted-terminal-input"))
                    .desired_width(f32::INFINITY)
                    .hint_text("help / status / echo <text> / clear / exit"),
            )
            .labelled_by(label.id);
            // A deliberate focused Enter/Space is accessible activation. The
            // shared guard fences preedit, Commit and trailing candidate keys.
            if self
                .activation
                .activated(&ui.add_enabled(!self.terminal_preedit_active, egui::Button::new("Run")))
                && !self.terminal_close_requested
            {
                self.run_restricted_command();
            }
            if self.activation.activated(&ui.button("Clear output")) {
                self.terminal_output.clear();
            }
        });
        ui.small("IME: Enter confirms a candidate. To execute, click Run or Tab to Run and press Enter/Space after composition ends.");
        if self.terminal_preedit_active {
            ui.colored_label(
                egui::Color32::YELLOW,
                "IME composition active: Run disabled until candidate commit.",
            );
        }
        if self.terminal_close_requested {
            ui.colored_label(
                egui::Color32::LIGHT_GREEN,
                "Exit requested; waiting for the host session to observe process exit.",
            );
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
    }

    /// Execute only fixed, local UI commands. This is intentionally not a
    /// shell parser: no token expansion, command lookup, filesystem access,
    /// networking, or child process creation occurs here.
    fn run_restricted_command(&mut self) {
        const MAX_COMMAND_BYTES: usize = 512;
        const MAX_ECHO_BYTES: usize = 256;
        if self.terminal_preedit_active {
            self.terminal_line("refused: active IME composition; text remains in the editor");
            return;
        }
        let command = std::mem::take(&mut self.terminal_input);
        let command = command.trim();
        if command.is_empty() {
            return;
        }
        // Reject BEFORE echoing command bytes to the visible history: a
        // megabyte-long paste must not become an unbounded rendered log line.
        if command.len() > MAX_COMMAND_BYTES {
            self.terminal_line(
                "refused: command exceeds 512 bytes; no host operation was attempted",
            );
            return;
        }
        if !command_is_safe_for_log(command) {
            self.terminal_line(
                "refused: control or bidi formatting character; no host operation was attempted",
            );
            return;
        }
        self.terminal_line(format!("$ {command}"));
        match command {
            "help" => self
                .terminal_line("allowlist: help | status | version | echo <text> | clear | exit"),
            "status" => self.terminal_line(format!(
                "running restricted terminal task #{} in {}",
                self.task_id,
                self.workspace.name()
            )),
            "version" => self.terminal_line("trill restricted terminal v1 (host UI prototype)"),
            "clear" => self.terminal_output.clear(),
            "exit" => {
                self.terminal_line("exit requested; app process will close");
                self.terminal_close_requested = true;
            }
            value if value.strip_prefix("echo ").is_some() => {
                let text = value.strip_prefix("echo ").unwrap().trim();
                if text.len() > MAX_ECHO_BYTES {
                    self.terminal_line(
                        "refused: echo text exceeds 256 bytes; no host operation was attempted",
                    );
                } else {
                    self.terminal_line(text);
                }
            }
            _ => self.terminal_line(
                "refused: command is not allowlisted; no host operation was attempted",
            ),
        }
    }

    fn calculate(&mut self, operation: char) {
        let (Ok(a), Ok(b)) = (
            self.left.trim().parse::<f64>(),
            self.right.trim().parse::<f64>(),
        ) else {
            self.result = "Invalid number (input remains unchanged)".into();
            return;
        };
        let value = match operation {
            '+' => Some(a + b),
            '-' => Some(a - b),
            '*' => Some(a * b),
            '/' if b != 0.0 => Some(a / b),
            _ => None,
        };
        self.result = match value {
            Some(n) if n.is_finite() => format!("{n}"),
            Some(_) => "Overflow / nonfinite result".into(),
            None => "Division by zero".into(),
        };
    }
}

fn saved_notes_age(saved_unix_ms: u64) -> String {
    let elapsed = trill_ui_core::unix_ms().saturating_sub(saved_unix_ms) / 1000;
    match elapsed {
        0..=59 => "刚刚保存".to_owned(),
        60..=3599 => format!("{} 分钟前保存", elapsed / 60),
        3600..=86399 => format!("{} 小时前保存", elapsed / 3600),
        _ => format!("{} 天前保存", elapsed / 86400),
    }
}

fn parse_kind(value: &str) -> Result<AppKind, String> {
    match value {
        "notes" => Ok(AppKind::Notes),
        "calculator" => Ok(AppKind::Calculator),
        "terminal" => Ok(AppKind::Terminal),
        _ => Err(format!("unsupported app kind: {value}")),
    }
}

fn parse_arguments() -> Result<
    (
        AppKind,
        Workspace,
        u64,
        Option<trill_ui_core::notes::NotesTargetIdentity>,
    ),
    String,
> {
    let mut kind = None;
    let mut workspace = None;
    let mut task_id = None;
    let mut notes_session = None;
    let mut notes_incarnation = None;
    let mut args = std::env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args.next().ok_or_else(|| format!("{flag} missing value"))?;
        match flag.as_str() {
            "--kind" => kind = Some(parse_kind(&value)?),
            "--workspace" => {
                workspace = Some(match value.as_str() {
                    "personal" => Workspace::Personal,
                    "research" => Workspace::Research,
                    "build" => Workspace::Build,
                    _ => return Err(format!("unknown workspace: {value}")),
                })
            }
            "--task-id" => task_id = Some(value.parse::<u64>().map_err(|_| "invalid task id")?),
            "--notes-session" if notes_session.is_none() => notes_session = Some(value),
            "--notes-incarnation" if notes_incarnation.is_none() => notes_incarnation = Some(value),
            _ => return Err(format!("unknown argument: {flag}")),
        }
    }
    let kind = kind.ok_or("missing kind")?;
    let workspace = workspace.ok_or("missing workspace")?;
    let task_id = task_id.ok_or("missing task id")?;
    let notes = match (notes_session, notes_incarnation) {
        (None, None) => None,
        (Some(session_instance), Some(incarnation)) if kind == AppKind::Notes => {
            let identity = trill_ui_core::notes::NotesTargetIdentity {
                session_instance,
                task_id,
                incarnation,
            };
            identity.validate().map_err(|_| "invalid Notes target")?;
            Some(identity)
        }
        _ => {
            return Err(
                "Notes destination requires both identity fields and Notes app kind".into(),
            );
        }
    };
    Ok((kind, workspace, task_id, notes))
}

fn main() -> eframe::Result {
    let (kind, workspace, task_id, notes_target) = parse_arguments().unwrap_or_else(|error| {
        eprintln!("trill-app-window: {error}");
        std::process::exit(2);
    });
    let notes_lifetime = notes_target
        .as_ref()
        .map(trill_ui_core::notes_lifetime::SessionLifetime::from_environment)
        .transpose()
        .unwrap_or_else(|error| {
            eprintln!("trill-app-window: {error}");
            std::process::exit(2);
        })
        .flatten();
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([740.0, 560.0]),
        ..Default::default()
    };
    eframe::run_native(
        kind.name(),
        options,
        Box::new(move |cc| {
            host_fonts::install(&cc.egui_ctx);
            let notes_organ = notes_target
                .map(|target| {
                    notes_organ::NotesAppChannel::from_inherited_stdin(
                        cc.egui_ctx.clone(),
                        target,
                        notes_lifetime,
                    )
                })
                .transpose()?;
            Ok(Box::new(ClientWindow {
                activation: activation::ActivationGuard::default(),
                kind,
                workspace,
                task_id,
                notes: String::new(),
                notes_input: notes_input::NotesInput::default(),
                notes_organ,
                notes_browser: false,
                left: String::new(),
                right: String::new(),
                result: String::new(),
                focused_input: String::new(),
                terminal_input: String::new(),
                terminal_output: vec![
                    "restricted terminal ready (no shell or arbitrary host commands)".into(),
                    "allowlist: help | status | version | echo <text> | clear | exit".into(),
                ],
                terminal_close_requested: false,
                terminal_preedit_active: false,
                first_frame_emitted: false,
            }))
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn division_by_zero_never_claims_a_numeric_result() {
        let mut state = ClientWindow {
            activation: activation::ActivationGuard::default(),
            kind: AppKind::Calculator,
            workspace: Workspace::Personal,
            task_id: 1,
            notes: String::new(),
            notes_input: notes_input::NotesInput::default(),
            notes_organ: None,
            notes_browser: false,
            left: "4".into(),
            right: "0".into(),
            result: String::new(),
            focused_input: String::new(),
            terminal_input: String::new(),
            terminal_output: Vec::new(),
            terminal_close_requested: false,
            terminal_preedit_active: false,
            first_frame_emitted: false,
        };
        state.calculate('/');
        assert_eq!(state.result, "Division by zero");
        state.right = "2".into();
        state.calculate('/');
        assert_eq!(state.result, "2");
    }

    #[test]
    fn restricted_terminal_rejects_shell_syntax_and_runs_only_allowlist() {
        let mut state = ClientWindow {
            activation: activation::ActivationGuard::default(),
            kind: AppKind::Terminal,
            workspace: Workspace::Build,
            task_id: 9,
            notes: String::new(),
            notes_input: notes_input::NotesInput::default(),
            notes_organ: None,
            notes_browser: false,
            left: String::new(),
            right: String::new(),
            result: String::new(),
            focused_input: String::new(),
            terminal_input: String::new(),
            terminal_output: Vec::new(),
            terminal_close_requested: false,
            terminal_preedit_active: false,
            first_frame_emitted: false,
        };
        state.terminal_input = "sh -c id".into();
        state.run_restricted_command();
        assert!(state
            .terminal_output
            .last()
            .unwrap()
            .contains("not allowlisted"));
        state.terminal_input = "echo 中文".into();
        state.run_restricted_command();
        assert_eq!(state.terminal_output.last().unwrap(), "中文");
        state.terminal_input = "exit".into();
        state.run_restricted_command();
        assert!(state.terminal_close_requested);
    }

    /// A synthetic egui backend event test, not proof that a live host IME
    /// renders Chinese candidate windows under Weston or Asterinas.
    #[test]
    fn ime_candidate_enter_never_implicitly_runs_a_terminal_command() {
        fn frame(ctx: &egui::Context, state: &mut ClientWindow, events: Vec<egui::Event>) {
            let input = egui::RawInput {
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(900.0, 600.0),
                )),
                events,
                ..Default::default()
            };
            let _ = ctx.run(input, |ctx| {
                egui::CentralPanel::default().show(ctx, |ui| {
                    state.restricted_terminal(ui, ctx);
                });
            });
        }

        let ctx = egui::Context::default();
        let mut state = ClientWindow {
            activation: activation::ActivationGuard::default(),
            kind: AppKind::Terminal,
            workspace: Workspace::Build,
            task_id: 17,
            notes: String::new(),
            notes_input: notes_input::NotesInput::default(),
            notes_organ: None,
            notes_browser: false,
            left: String::new(),
            right: String::new(),
            result: String::new(),
            focused_input: String::new(),
            terminal_input: "echo ".into(),
            terminal_output: Vec::new(),
            terminal_close_requested: false,
            terminal_preedit_active: false,
            first_frame_emitted: false,
        };

        frame(&ctx, &mut state, vec![]);
        ctx.memory_mut(|memory| {
            memory.request_focus(egui::Id::new("restricted-terminal-input"));
        });
        frame(
            &ctx,
            &mut state,
            vec![
                egui::Event::Ime(egui::ImeEvent::Enabled),
                egui::Event::Ime(egui::ImeEvent::Preedit("nihao".into())),
            ],
        );
        assert!(
            state.terminal_output.is_empty(),
            "an uncommitted Chinese candidate must never run a command"
        );
        assert!(state.terminal_preedit_active);
        let before = state.terminal_input.clone();
        state.run_restricted_command();
        assert_eq!(state.terminal_input, before);
        assert!(state
            .terminal_output
            .last()
            .is_some_and(|line| { line.contains("active IME composition") }));
        state.terminal_output.clear();
        frame(
            &ctx,
            &mut state,
            vec![
                egui::Event::Ime(egui::ImeEvent::Commit("你好".into())),
                egui::Event::Ime(egui::ImeEvent::Disabled),
            ],
        );
        assert!(state.terminal_input.contains("你好"));
        assert!(!state.terminal_preedit_active);
        // Even an extra Enter key delivered AFTER IME commit must not become
        // a restricted terminal Run click or execute the completed command.
        frame(
            &ctx,
            &mut state,
            vec![egui::Event::Key {
                key: egui::Key::Enter,
                physical_key: None,
                pressed: true,
                repeat: false,
                modifiers: egui::Modifiers::default(),
            }],
        );
        assert!(
            state.terminal_output.is_empty(),
            "IME candidate confirmation via Enter is not an explicit Run click"
        );
        assert!(!state.terminal_close_requested);
    }

    #[test]
    fn focused_run_button_accepts_deliberate_keyboard_activation() {
        let ctx = egui::Context::default();
        let mut activation = activation::ActivationGuard::default();
        let make_input = |events| egui::RawInput {
            focused: true,
            screen_rect: Some(egui::Rect::from_min_size(
                egui::Pos2::ZERO,
                egui::vec2(900.0, 600.0),
            )),
            events,
            ..Default::default()
        };
        let mut run_button = None;
        let _ = ctx.run(make_input(vec![]), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                run_button = Some(ui.button("Run").id);
            });
        });
        ctx.memory_mut(|memory| {
            memory.request_focus(run_button.expect("run button exists"));
        });
        let mut activated = false;
        let mut focused = false;
        let _ = ctx.run(
            make_input(vec![egui::Event::Key {
                key: egui::Key::Enter,
                physical_key: None,
                pressed: true,
                repeat: false,
                modifiers: egui::Modifiers::default(),
            }]),
            |ctx| {
                activation.begin_frame(ctx);
                egui::CentralPanel::default().show(ctx, |ui| {
                    let response = ui.button("Run");
                    focused = response.has_focus();
                    activated = activation.activated(&response);
                });
            },
        );
        assert!(
            focused,
            "test must exercise an actual keyboard-focused button"
        );
        assert!(
            activated,
            "deliberate Enter without an IME lifecycle must activate the focused Run button"
        );
    }

    #[test]
    fn restricted_terminal_refuses_forged_log_lines_and_bidi_controls() {
        let mut state = ClientWindow {
            activation: activation::ActivationGuard::default(),
            kind: AppKind::Terminal,
            workspace: Workspace::Build,
            task_id: 12,
            notes: String::new(),
            notes_input: notes_input::NotesInput::default(),
            notes_organ: None,
            notes_browser: false,
            left: String::new(),
            right: String::new(),
            result: String::new(),
            focused_input: String::new(),
            terminal_input: String::new(),
            terminal_output: Vec::new(),
            terminal_close_requested: false,
            terminal_preedit_active: false,
            first_frame_emitted: false,
        };

        for hostile in [
            "echo 你好\nHOST PROCESS COMPLETED",
            "echo 你好\rFAKE TASK SUCCESS",
            "echo 你好\u{001b}[2J",
            "echo 你好\u{202e}dessap",
            "echo 你好\u{2066}success\u{2069}",
            "echo 你好\u{2028}FAKE TERMINAL",
        ] {
            state.terminal_input = hostile.to_owned();
            state.run_restricted_command();
            assert_eq!(state.terminal_output.len(), 1);
            assert!(state.terminal_output[0].contains("refused"));
            assert!(!state.terminal_output[0].contains("HOST PROCESS"));
            assert!(!state.terminal_close_requested);
            state.terminal_output.clear();
        }

        state.terminal_input = "echo 中文输入、候选词 📝".into();
        state.run_restricted_command();
        assert_eq!(
            state.terminal_output.last().map(String::as_str),
            Some("中文输入、候选词 📝")
        );
        assert!(!state.terminal_close_requested);
    }

    #[test]
    fn restricted_terminal_bounds_input_and_clear_is_local_only() {
        let mut state = ClientWindow {
            activation: activation::ActivationGuard::default(),
            kind: AppKind::Terminal,
            workspace: Workspace::Build,
            task_id: 10,
            notes: String::new(),
            notes_input: notes_input::NotesInput::default(),
            notes_organ: None,
            notes_browser: false,
            left: String::new(),
            right: String::new(),
            result: String::new(),
            focused_input: String::new(),
            // 100 CJK characters are over the 256-byte echo cap but stay
            // below the 512-byte command-input budget.
            terminal_input: "echo ".to_owned() + &"界".repeat(100),
            terminal_output: Vec::new(),
            terminal_close_requested: false,
            terminal_preedit_active: false,
            first_frame_emitted: false,
        };
        let before = state.terminal_input.clone();
        state.run_restricted_command();
        assert!(
            state
                .terminal_output
                .last()
                .is_some_and(|line| line.contains("exceeds 256 bytes")),
            "oversized echo must be refused before any host effect"
        );
        assert_ne!(
            state.terminal_input, before,
            "accepted commands are consumed"
        );
        assert!(!state.terminal_close_requested);

        state.terminal_input = "status".into();
        state.run_restricted_command();
        assert!(state
            .terminal_output
            .last()
            .is_some_and(|line| line.contains("running restricted terminal task #10")));
        state.terminal_input = "clear".into();
        state.run_restricted_command();
        assert!(state.terminal_output.is_empty());
        assert!(!state.terminal_close_requested);
    }

    #[test]
    fn restricted_terminal_refuses_commands_over_wire_budget() {
        let mut state = ClientWindow {
            activation: activation::ActivationGuard::default(),
            kind: AppKind::Terminal,
            workspace: Workspace::Personal,
            task_id: 11,
            notes: String::new(),
            notes_input: notes_input::NotesInput::default(),
            notes_organ: None,
            notes_browser: false,
            left: String::new(),
            right: String::new(),
            result: String::new(),
            focused_input: String::new(),
            terminal_input: "x".repeat(513),
            terminal_output: Vec::new(),
            terminal_close_requested: false,
            terminal_preedit_active: false,
            first_frame_emitted: false,
        };
        state.run_restricted_command();
        assert!(state
            .terminal_output
            .last()
            .is_some_and(|line| line.contains("exceeds 512 bytes")));
        assert!(!state.terminal_close_requested);
        assert_eq!(state.terminal_output.len(), 1);
        assert!(state.terminal_output[0].len() < 160);
        assert!(!state.terminal_output[0].contains("x".repeat(64).as_str()));

        // A hostile or accidental large paste stays bounded in the UI log.
        state.terminal_output.clear();
        state.terminal_input = "中文".repeat(200_000);
        state.run_restricted_command();
        assert_eq!(state.terminal_output.len(), 1);
        assert!(state.terminal_output[0].len() < 160);
        assert!(state.terminal_output[0].contains("exceeds 512 bytes"));
        assert!(!state.terminal_close_requested);
    }

    #[test]
    fn parse_arguments_accepts_terminal_kind() {
        // Parsing only validates the fixed app registry; no process is spawned.
        assert_eq!(parse_kind("terminal").unwrap(), AppKind::Terminal);
        assert!(parse_kind("sh -c id").is_err());
    }
}
