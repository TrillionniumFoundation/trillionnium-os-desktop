//! One independent client window per app process. No embedded webview or Node.
use eframe::egui::{self, RichText};
use std::io::Write;
use trill_ui_core::{AppKind, Workspace};

struct ClientWindow {
    kind: AppKind,
    workspace: Workspace,
    task_id: u64,
    notes: String,
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
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading(self.kind.name());
            ui.label(format!("Workspace: {} · host task #{}", self.workspace.name(), self.task_id));
            ui.small("This is a separate native Rust app process/window, not a secure workspace container.");
            ui.separator();
            match self.kind {
                AppKind::Notes => {
                    ui.label("Notes / 笔记 · try composing Chinese with your host IME");
                    let editor = ui.add(
                        egui::TextEdit::multiline(&mut self.notes)
                            .id(egui::Id::new("notes-editor"))
                            .desired_rows(17)
                            .desired_width(f32::INFINITY)
                            .hint_text("中文输入、候选词、焦点测试……"),
                    );
                    ui.small(if editor.has_focus() {
                        "Keyboard focus: NOTES editor (IME target)"
                    } else {
                        "Keyboard focus: inactive; click Notes editor to compose"
                    });
                    ui.small("Local unsaved memory only. Closing this app discards notes.");
                }
                AppKind::Calculator => {
                    ui.horizontal(|ui| {
                        ui.label("A");
                        ui.text_edit_singleline(&mut self.left);
                        ui.label("B");
                        ui.text_edit_singleline(&mut self.right);
                    });
                    ui.horizontal(|ui| {
                        for (label, op) in [("+", '+'), ("−", '-'), ("×", '*'), ("÷", '/')] {
                            if ui.button(label).clicked() {
                                self.calculate(op);
                            }
                        }
                    });
                    ui.label(RichText::new(&self.result).size(20.0));
                    ui.separator();
                    ui.label("Keyboard and IME focus probe / 输入法焦点");
                    let ime_probe = ui.add(
                        egui::TextEdit::singleline(&mut self.focused_input)
                            .id(egui::Id::new("calculator-ime-focus")),
                    );
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
        // Signal only AFTER the first UI layout has completed successfully,
        // not on process spawn or before building the widget tree.
        // This still does not attest that a compositor presented the frame.
        if !self.first_frame_emitted {
            self.first_frame_emitted = true;
            // The session owns this child's stdout pipe. Ignore BrokenPipe:
            // session failure MUST NOT crash an independently running app.
            let _ = std::io::stdout().write_all(b"TRILL_UI_FIRST_FRAME_V1\n");
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

    fn terminal_line(&mut self, line: impl Into<String>) {
        if self.terminal_output.len() >= Self::MAX_TERMINAL_LINES {
            self.terminal_output.remove(0);
        }
        self.terminal_output.push(line.into());
    }

    fn restricted_terminal(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        // Only a nonempty preedit blocks Run; idle IME Enabled remains usable.
        ui.input(|input| {
            for event in &input.events {
                match event {
                    egui::Event::Ime(egui::ImeEvent::Preedit(text)) => {
                        self.terminal_preedit_active = !text.is_empty();
                    }
                    egui::Event::Ime(egui::ImeEvent::Commit(_))
                    | egui::Event::Ime(egui::ImeEvent::Disabled) => {
                        self.terminal_preedit_active = false;
                    }
                    _ => {}
                }
            }
        });
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
        ui.horizontal(|ui| {
            ui.add(
                egui::TextEdit::singleline(&mut self.terminal_input)
                    .id(egui::Id::new("restricted-terminal-input"))
                    .desired_width(f32::INFINITY)
                    .hint_text("help / status / echo <text> / clear / exit"),
            );
            // Enter is used by Chinese IME to confirm a candidate. Losing
            // TextEdit focus on Enter must NEVER execute an uncommitted command.
            // Explicit button activation is the only command commit path.
            if ui
                .add_enabled(!self.terminal_preedit_active, egui::Button::new("Run"))
                .clicked()
                && !self.terminal_close_requested
            {
                self.run_restricted_command();
            }
            if ui.button("Clear output").clicked() {
                self.terminal_output.clear();
            }
        });
        ui.small("IME: Enter confirms a candidate, not a command. Click Run to execute.");
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

fn parse_kind(value: &str) -> Result<AppKind, String> {
    match value {
        "notes" => Ok(AppKind::Notes),
        "calculator" => Ok(AppKind::Calculator),
        "terminal" => Ok(AppKind::Terminal),
        _ => Err(format!("unsupported app kind: {value}")),
    }
}

fn parse_arguments() -> Result<(AppKind, Workspace, u64), String> {
    let mut kind = None;
    let mut workspace = None;
    let mut task_id = None;
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
            _ => return Err(format!("unknown argument: {flag}")),
        }
    }
    Ok((
        kind.ok_or("missing kind")?,
        workspace.ok_or("missing workspace")?,
        task_id.ok_or("missing task id")?,
    ))
}

fn install_host_cjk_font(ctx: &egui::Context) {
    for path in [
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ] {
        if let Ok(bytes) = std::fs::read(path) {
            let mut fonts = egui::FontDefinitions::default();
            fonts
                .font_data
                .insert("host-cjk".into(), egui::FontData::from_owned(bytes).into());
            if let Some(family) = fonts.families.get_mut(&egui::FontFamily::Proportional) {
                family.insert(0, "host-cjk".into());
            }
            ctx.set_fonts(fonts);
            return;
        }
    }
    eprintln!("CJK font unavailable: Chinese glyph rendering requires host font installation");
}

fn main() -> eframe::Result {
    let (kind, workspace, task_id) = parse_arguments().unwrap_or_else(|error| {
        eprintln!("trill-app-window: {error}");
        std::process::exit(2);
    });
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([740.0, 560.0]),
        ..Default::default()
    };
    eframe::run_native(
        kind.name(),
        options,
        Box::new(move |cc| {
            install_host_cjk_font(&cc.egui_ctx);
            Ok(Box::new(ClientWindow {
                kind,
                workspace,
                task_id,
                notes: String::new(),
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
            kind: AppKind::Calculator,
            workspace: Workspace::Personal,
            task_id: 1,
            notes: String::new(),
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
            kind: AppKind::Terminal,
            workspace: Workspace::Build,
            task_id: 9,
            notes: String::new(),
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
            kind: AppKind::Terminal,
            workspace: Workspace::Build,
            task_id: 17,
            notes: String::new(),
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
        assert!(state.terminal_output.last().is_some_and(|line| {
            line.contains("active IME composition")
        }));
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
    fn restricted_terminal_refuses_forged_log_lines_and_bidi_controls() {
        let mut state = ClientWindow {
            kind: AppKind::Terminal,
            workspace: Workspace::Build,
            task_id: 12,
            notes: String::new(),
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
            kind: AppKind::Terminal,
            workspace: Workspace::Build,
            task_id: 10,
            notes: String::new(),
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
            kind: AppKind::Terminal,
            workspace: Workspace::Personal,
            task_id: 11,
            notes: String::new(),
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
