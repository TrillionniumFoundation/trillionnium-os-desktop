from pathlib import Path

path = Path("runtime/servo/hepta_workspace_runtime.rs")
text = path.read_text()


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match, found {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


replace_once(
    '    "%3Cbody%20tabindex=0%3E%3Cdiv%20id=target%3ED0A-02%20Servo%20content%3C/div%3E",\n',
    '    "%3Cbody%3E%3Cdiv%20id=target%3ED0A-02%20Servo%20content%3C/div%3E",\n'
    '    "%3Cinput%20id=field%20autofocus%20aria-label=ime-test%3E",\n',
)
replace_once(
    '    "document.body.focus();%3C/script%3E"\n',
    '    "document.getElementById(\'field\').focus();%3C/script%3E"\n',
)
replace_once(
    '''            InputEvent::Keyboard(KeyboardEvent::from_state_and_key(
                KeyState::Up,
                Key::Character("h".into()),
            )),
            InputEvent::Ime(ImeEvent::Composition(CompositionEvent {
                state: CompositionState::Start,
                data: String::new(),
            })),
            InputEvent::Ime(ImeEvent::Composition(CompositionEvent {
                state: CompositionState::Update,
                data: "hepta".to_owned(),
            })),
            InputEvent::Ime(ImeEvent::Composition(CompositionEvent {
                state: CompositionState::End,
                data: "hepta".to_owned(),
            })),
        ];
''',
    '''            InputEvent::Keyboard(KeyboardEvent::from_state_and_key(
                KeyState::Up,
                Key::Character("h".into()),
            )),
        ];
''',
)
replace_once(
    '''        self.input_events_sent.set(15);
        self.ime_composition_events_sent.set(3);
        self.ime_path_exercised.set(true);
    }

    fn request_page_input_evidence(self: &Rc<Self>) {
''',
    '''        self.input_events_sent.set(12);
    }

    fn send_composition_ime(self: &Rc<Self>) {
        if self.ime_composition_events_sent.get() != 0 {
            return;
        }
        let Some(webview) = self.webview.borrow().as_ref().cloned() else {
            return;
        };
        let _ = fs::write(self.output.join("ime-composition.started"), b"started\\n");
        let events = [
            CompositionEvent {
                state: CompositionState::Start,
                data: String::new(),
            },
            CompositionEvent {
                state: CompositionState::Update,
                data: "hepta".to_owned(),
            },
            CompositionEvent {
                state: CompositionState::End,
                data: "hepta".to_owned(),
            },
        ];
        for event in events {
            webview.notify_input_event(InputEvent::Ime(ImeEvent::Composition(event)));
        }
        self.ime_composition_events_sent.set(3);
        self.input_events_sent.set(15);
        self.ime_path_exercised.set(true);
        let _ = fs::write(
            self.output.join("ime-composition.completed"),
            b"completed\\n",
        );
        let _ = self.proxy.send_event(AppEvent::Wake);
    }

    fn request_page_input_evidence(self: &Rc<Self>) {
''',
)
replace_once(
    '''        if self.page_input_verified.get()
            && self.popup_requests_denied.get() >= 1
            && self.generation.get() == 1
        {
            self.begin_recovery();
        }
''',
    '''        if self.page_input_verified.get()
            && self.popup_requests_denied.get() >= 1
            && self.generation.get() == 1
            && self.ime_composition_events_sent.get() == 0
        {
            self.send_composition_ime();
            return;
        }
        if self.page_input_verified.get()
            && self.popup_requests_denied.get() >= 1
            && self.generation.get() == 1
            && self.ime_composition_events_sent.get() == 3
        {
            self.begin_recovery();
        }
''',
)
path.write_text(text)
