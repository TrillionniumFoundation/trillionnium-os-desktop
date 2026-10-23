//! egui adapter for the shared input policy. Call `begin_frame` before editors
//! consume input, then use `activated` for controls that request an effect.
#[path = "activation_policy.rs"]
mod policy;

use eframe::egui;
use policy::{ActivationPolicy, ActivationSource, ConfirmKey, FramePermission, InputEvent};

#[derive(Default)]
pub struct ActivationGuard {
    policy: ActivationPolicy,
    permission: FramePermission,
    last_frame: Option<u64>,
}

impl ActivationGuard {
    pub fn begin_frame(&mut self, ctx: &egui::Context) {
        // A layout can request another egui pass. That pass has no raw events;
        // preserve the first pass's IME fence instead of treating it as idle.
        let frame = ctx
            .cumulative_pass_nr()
            .saturating_sub(ctx.output(|output| output.num_completed_passes as u64));
        if self.last_frame == Some(frame) {
            return;
        }
        self.last_frame = Some(frame);
        self.permission = ctx.input(|input| {
            self.policy.begin_frame(
                input.focused,
                input.events.iter().filter_map(|event| match event {
                    egui::Event::Ime(egui::ImeEvent::Preedit(text)) => Some(InputEvent::Preedit {
                        empty: text.is_empty(),
                    }),
                    egui::Event::Ime(egui::ImeEvent::Commit(_)) => Some(InputEvent::Commit),
                    egui::Event::Ime(egui::ImeEvent::Disabled) => Some(InputEvent::ImeDisabled),
                    egui::Event::Key {
                        key,
                        pressed,
                        repeat,
                        modifiers,
                        ..
                    } if matches!(key, egui::Key::Enter | egui::Key::Space) => {
                        Some(InputEvent::ConfirmKey {
                            key: if *key == egui::Key::Enter {
                                ConfirmKey::Enter
                            } else {
                                ConfirmKey::Space
                            },
                            pressed: *pressed,
                            repeat: *repeat,
                            modified: !modifiers.is_none(),
                        })
                    }
                    egui::Event::Key {
                        key: egui::Key::Tab,
                        pressed: true,
                        repeat: false,
                        ..
                    }
                    | egui::Event::PointerButton {
                        button: egui::PointerButton::Primary,
                        pressed: true,
                        ..
                    } => Some(InputEvent::ExplicitNavigation),
                    _ => None,
                }),
            )
        });
    }

    pub fn composing(&self) -> bool {
        self.policy.composing()
    }

    // This shared adapter is also compiled by app-window, whose editors do not
    // yet use the optional original-Hepta composer transaction.
    #[allow(dead_code)]
    pub fn ime_confirmation_fenced(&self) -> bool {
        self.permission.ime_confirmation_fenced()
    }

    pub fn activated(&self, response: &egui::Response) -> bool {
        if !response.enabled() || !response.clicked() {
            return false;
        }
        let source = if response.clicked_by(egui::PointerButton::Primary) {
            ActivationSource::Pointer
        } else if self.permission.confirmation_key_seen() {
            ActivationSource::Keyboard
        } else {
            // egui's remaining semantic click source is its accessibility
            // integration. No raw Enter/Space is synthesized here.
            ActivationSource::Accessibility
        };
        self.permission.allows(source)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn raw(events: Vec<egui::Event>) -> egui::RawInput {
        egui::RawInput {
            focused: true,
            screen_rect: Some(egui::Rect::from_min_size(
                egui::Pos2::ZERO,
                egui::vec2(800.0, 600.0),
            )),
            events,
            ..Default::default()
        }
    }

    fn key(key: egui::Key, pressed: bool) -> egui::Event {
        egui::Event::Key {
            key,
            physical_key: None,
            pressed,
            repeat: false,
            modifiers: egui::Modifiers::default(),
        }
    }

    fn button_frame(
        ctx: &egui::Context,
        guard: &mut ActivationGuard,
        events: Vec<egui::Event>,
    ) -> (egui::Id, egui::Rect, bool, bool) {
        let mut result = None;
        let _ = ctx.run(raw(events), |ctx| {
            guard.begin_frame(ctx);
            egui::CentralPanel::default().show(ctx, |ui| {
                let response = ui.button("Explicit effect");
                result = Some((
                    response.id,
                    response.rect,
                    response.clicked(),
                    guard.activated(&response),
                ));
            });
        });
        result.unwrap()
    }

    #[test]
    fn real_focused_button_is_accessible_by_enter_and_space() {
        for confirm in [egui::Key::Enter, egui::Key::Space] {
            let ctx = egui::Context::default();
            let mut guard = ActivationGuard::default();
            let (id, _, _, _) = button_frame(&ctx, &mut guard, vec![]);
            ctx.memory_mut(|memory| memory.request_focus(id));
            let (_, _, clicked, allowed) = button_frame(&ctx, &mut guard, vec![key(confirm, true)]);
            assert!(clicked && allowed);
        }
    }

    #[test]
    fn real_button_rejects_ime_confirmation_then_accepts_a_fresh_press() {
        for confirm in [egui::Key::Enter, egui::Key::Space] {
            let ctx = egui::Context::default();
            let mut guard = ActivationGuard::default();
            let (id, _, _, _) = button_frame(&ctx, &mut guard, vec![]);
            ctx.memory_mut(|memory| memory.request_focus(id));
            button_frame(
                &ctx,
                &mut guard,
                vec![egui::Event::Ime(egui::ImeEvent::Preedit("nihao".into()))],
            );
            button_frame(
                &ctx,
                &mut guard,
                vec![
                    egui::Event::Ime(egui::ImeEvent::Commit("你好".into())),
                    egui::Event::Ime(egui::ImeEvent::Disabled),
                ],
            );
            let (_, _, clicked, allowed) = button_frame(&ctx, &mut guard, vec![key(confirm, true)]);
            assert!(clicked, "exercise egui's actual synthetic keyboard click");
            assert!(
                !allowed,
                "a delayed candidate key is not explicit activation"
            );
            button_frame(&ctx, &mut guard, vec![key(confirm, false)]);
            let (_, _, clicked, allowed) = button_frame(&ctx, &mut guard, vec![key(confirm, true)]);
            assert!(
                clicked && allowed,
                "fresh deliberate keyboard action is restored"
            );
        }
    }

    #[test]
    fn real_button_rejects_repeat_without_requiring_a_pointer() {
        let ctx = egui::Context::default();
        let mut guard = ActivationGuard::default();
        let (id, _, _, _) = button_frame(&ctx, &mut guard, vec![]);
        ctx.memory_mut(|memory| memory.request_focus(id));
        assert!(button_frame(&ctx, &mut guard, vec![key(egui::Key::Enter, true)]).3);
        let (_, _, clicked, allowed) =
            button_frame(&ctx, &mut guard, vec![key(egui::Key::Enter, true)]);
        assert!(clicked, "egui synthesizes repeated focused button clicks");
        assert!(!allowed, "held Enter must not dispatch an effect twice");
    }

    #[test]
    fn explicit_pointer_cannot_bypass_active_preedit() {
        let ctx = egui::Context::default();
        let mut guard = ActivationGuard::default();
        let (_, rect, _, _) = button_frame(&ctx, &mut guard, vec![]);
        let pos = rect.center();
        let pointer = |pressed| egui::Event::PointerButton {
            pos,
            button: egui::PointerButton::Primary,
            pressed,
            modifiers: egui::Modifiers::default(),
        };
        button_frame(
            &ctx,
            &mut guard,
            vec![
                egui::Event::Ime(egui::ImeEvent::Preedit("nihao".into())),
                egui::Event::PointerMoved(pos),
                pointer(true),
            ],
        );
        let (_, _, clicked, allowed) = button_frame(&ctx, &mut guard, vec![pointer(false)]);
        assert!(clicked, "exercise a real primary-button click");
        assert!(!allowed, "pointer is not an escape from active composition");
        button_frame(
            &ctx,
            &mut guard,
            vec![egui::Event::Ime(egui::ImeEvent::Commit("你好".into()))],
        );
        button_frame(&ctx, &mut guard, vec![pointer(true)]);
        assert!(button_frame(&ctx, &mut guard, vec![pointer(false)]).3);
    }

    #[test]
    fn repeated_layout_pass_preserves_the_commit_fence() {
        let ctx = egui::Context::default();
        let mut guard = ActivationGuard::default();
        ctx.options_mut(|options| options.max_passes = 2.try_into().unwrap());
        let mut passes = 0;
        let _ = ctx.run(
            raw(vec![egui::Event::Ime(egui::ImeEvent::Commit(
                "你好".into(),
            ))]),
            |ctx| {
                guard.begin_frame(ctx);
                // Also exercise repeated callers within one pass.
                guard.begin_frame(ctx);
                assert!(!guard.permission.allows(ActivationSource::Pointer));
                assert!(!guard.permission.allows(ActivationSource::Accessibility));
                if passes == 0 {
                    ctx.request_discard("activation guard regression");
                }
                passes += 1;
            },
        );
        assert_eq!(passes, 2);
    }
}
