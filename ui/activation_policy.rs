//! Renderer-independent policy for explicit, accessible UI effects.
//!
//! IME confirmation is not an activation. Keep that distinction across frames:
//! backends can deliver Commit, the confirming key, and its release separately.
//! This policy does not authorize effects; Session and Hepta still own admission.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConfirmKey {
    Enter,
    Space,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InputEvent {
    Preedit {
        empty: bool,
    },
    Commit,
    ImeDisabled,
    ConfirmKey {
        key: ConfirmKey,
        pressed: bool,
        repeat: bool,
        modified: bool,
    },
    /// A fresh Tab or primary-pointer press after composition is explicit
    /// navigation. It also recovers when an IME swallowed the confirming key-up.
    ExplicitNavigation,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ActivationSource {
    Pointer,
    Keyboard,
    /// A semantic action supplied by the renderer's accessibility integration.
    Accessibility,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct FramePermission {
    effects: bool,
    keyboard: bool,
    confirmation_key_seen: bool,
    ime_confirmation_fenced: bool,
}

impl FramePermission {
    pub fn allows(self, source: ActivationSource) -> bool {
        self.effects
            && match source {
                ActivationSource::Keyboard => self.keyboard,
                ActivationSource::Pointer | ActivationSource::Accessibility => true,
            }
    }

    pub fn confirmation_key_seen(self) -> bool {
        self.confirmation_key_seen
    }

    /// Keep the whole confirming frame fenced even when its key-up clears the
    /// pending state before a renderer processes that frame's editor events.
    pub fn ime_confirmation_fenced(self) -> bool {
        self.ime_confirmation_fenced
    }
}

#[derive(Debug, Default)]
pub struct ActivationPolicy {
    composing: bool,
    wait_for_confirmation_release: bool,
    enter_down: bool,
    space_down: bool,
}

impl ActivationPolicy {
    pub fn composing(&self) -> bool {
        self.composing
    }

    /// A renderer must not reinterpret a delayed IME confirmation as editor
    /// Return while waiting for its release or fresh explicit navigation.
    pub fn ime_confirmation_pending(&self) -> bool {
        self.composing || self.wait_for_confirmation_release
    }

    pub fn begin_frame(
        &mut self,
        focused: bool,
        events: impl IntoIterator<Item = InputEvent>,
    ) -> FramePermission {
        let ime_confirmation_pending_at_start = self.ime_confirmation_pending();
        let mut blocks_effects = self.composing || !focused;
        let mut blocks_keyboard = false;
        let mut fresh_keyboard_activation = false;
        let mut confirmation_key_seen = false;

        if !focused {
            // Losing focus cancels our preedit lifecycle, but must not arm a
            // delayed candidate key after the window regains focus.
            self.wait_for_confirmation_release |=
                self.composing || self.enter_down || self.space_down;
            self.composing = false;
            self.enter_down = false;
            self.space_down = false;
        }

        for event in events {
            match event {
                InputEvent::Preedit { empty } => {
                    if self.composing || !empty {
                        blocks_effects = true;
                        self.wait_for_confirmation_release = true;
                    }
                    self.composing = !empty && focused;
                }
                InputEvent::Commit => {
                    blocks_effects = true;
                    self.composing = false;
                    self.wait_for_confirmation_release = true;
                }
                InputEvent::ImeDisabled => {
                    if self.composing {
                        blocks_effects = true;
                        self.composing = false;
                        self.wait_for_confirmation_release = true;
                    }
                }
                InputEvent::ConfirmKey {
                    key,
                    pressed,
                    repeat,
                    modified,
                } => {
                    let was_down = match key {
                        ConfirmKey::Enter => self.enter_down,
                        ConfirmKey::Space => self.space_down,
                    };
                    if pressed {
                        confirmation_key_seen = true;
                        blocks_keyboard |= self.composing
                            || self.wait_for_confirmation_release
                            || was_down
                            || repeat
                            || modified;
                        fresh_keyboard_activation |= !was_down && !repeat && !modified;
                    }
                    match key {
                        ConfirmKey::Enter => self.enter_down = pressed,
                        ConfirmKey::Space => self.space_down = pressed,
                    }
                    if !pressed && !self.composing && !self.enter_down && !self.space_down {
                        self.wait_for_confirmation_release = false;
                    }
                }
                InputEvent::ExplicitNavigation => {
                    if !blocks_effects && !self.enter_down && !self.space_down {
                        self.wait_for_confirmation_release = false;
                    }
                }
            }
        }

        FramePermission {
            effects: !blocks_effects && !self.composing,
            keyboard: fresh_keyboard_activation && !blocks_keyboard,
            confirmation_key_seen,
            ime_confirmation_fenced: ime_confirmation_pending_at_start
                || blocks_effects
                || self.wait_for_confirmation_release,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key(key: ConfirmKey, pressed: bool) -> InputEvent {
        InputEvent::ConfirmKey {
            key,
            pressed,
            repeat: false,
            modified: false,
        }
    }

    #[test]
    fn deliberate_enter_and_space_activate_without_a_pointer() {
        for confirm in [ConfirmKey::Enter, ConfirmKey::Space] {
            let mut policy = ActivationPolicy::default();
            let frame = policy.begin_frame(true, [key(confirm, true)]);
            assert!(frame.allows(ActivationSource::Keyboard));
            assert!(frame.confirmation_key_seen());
            assert!(!frame.ime_confirmation_fenced());
        }
    }

    #[test]
    fn active_composition_blocks_every_effect_source() {
        let mut policy = ActivationPolicy::default();
        for events in [vec![InputEvent::Preedit { empty: false }], vec![]] {
            let frame = policy.begin_frame(true, events);
            assert!(policy.composing());
            assert!(frame.ime_confirmation_fenced());
            for source in [
                ActivationSource::Keyboard,
                ActivationSource::Pointer,
                ActivationSource::Accessibility,
            ] {
                assert!(!frame.allows(source));
            }
        }
    }

    #[test]
    fn commit_then_trailing_confirmation_is_blocked_until_release() {
        for confirm in [ConfirmKey::Enter, ConfirmKey::Space] {
            let mut policy = ActivationPolicy::default();
            policy.begin_frame(true, [InputEvent::Preedit { empty: false }]);
            let commit = policy.begin_frame(true, [InputEvent::Commit, InputEvent::ImeDisabled]);
            assert!(!policy.composing());
            assert!(policy.ime_confirmation_pending());
            assert!(commit.ime_confirmation_fenced());
            assert!(!commit.allows(ActivationSource::Pointer));
            assert!(!commit.allows(ActivationSource::Accessibility));
            policy.begin_frame(true, []);
            assert!(policy.ime_confirmation_pending());
            assert!(!policy
                .begin_frame(true, [key(confirm, true)])
                .allows(ActivationSource::Keyboard));
            policy.begin_frame(true, [key(confirm, false)]);
            assert!(!policy.ime_confirmation_pending());
            assert!(policy
                .begin_frame(true, [key(confirm, true)])
                .allows(ActivationSource::Keyboard));
        }
    }

    #[test]
    fn same_frame_commit_and_key_are_blocked_in_either_order() {
        for events in [
            vec![InputEvent::Commit, key(ConfirmKey::Enter, true)],
            vec![key(ConfirmKey::Enter, true), InputEvent::Commit],
        ] {
            let mut policy = ActivationPolicy::default();
            assert!(!policy
                .begin_frame(true, events)
                .allows(ActivationSource::Keyboard));
        }
    }

    #[test]
    fn press_then_release_does_not_unblock_the_same_candidate_frame() {
        let mut policy = ActivationPolicy::default();
        policy.begin_frame(true, [InputEvent::Commit]);
        let confirmation = policy.begin_frame(
            true,
            [key(ConfirmKey::Enter, true), key(ConfirmKey::Enter, false)],
        );
        assert!(!confirmation.allows(ActivationSource::Keyboard));
        assert!(!policy.ime_confirmation_pending());
        assert!(confirmation.ime_confirmation_fenced());
        let fresh = policy.begin_frame(true, [key(ConfirmKey::Enter, true)]);
        assert!(fresh.allows(ActivationSource::Keyboard));
        assert!(!fresh.ime_confirmation_fenced());
    }

    #[test]
    fn empty_preedit_and_disabled_cannot_drop_the_confirmation_fence() {
        for end in [InputEvent::Preedit { empty: true }, InputEvent::ImeDisabled] {
            let mut policy = ActivationPolicy::default();
            policy.begin_frame(true, [InputEvent::Preedit { empty: false }]);
            assert!(!policy
                .begin_frame(true, [end])
                .allows(ActivationSource::Pointer));
            assert!(!policy.composing());
            assert!(!policy
                .begin_frame(true, [key(ConfirmKey::Space, true)])
                .allows(ActivationSource::Keyboard));
        }
    }

    #[test]
    fn explicit_navigation_recovers_when_backend_swallows_key_release() {
        let mut policy = ActivationPolicy::default();
        policy.begin_frame(true, [InputEvent::Commit]);
        let navigation = policy.begin_frame(true, [InputEvent::ExplicitNavigation]);
        assert!(navigation.ime_confirmation_fenced());
        let fresh = policy.begin_frame(true, [key(ConfirmKey::Enter, true)]);
        assert!(fresh.allows(ActivationSource::Keyboard));
        assert!(!fresh.ime_confirmation_fenced());
    }

    #[test]
    fn navigation_during_composition_does_not_bypass_the_fence() {
        let mut policy = ActivationPolicy::default();
        policy.begin_frame(true, [InputEvent::Preedit { empty: false }]);
        policy.begin_frame(true, [InputEvent::ExplicitNavigation]);
        policy.begin_frame(true, [InputEvent::Commit]);
        assert!(!policy
            .begin_frame(true, [key(ConfirmKey::Enter, true)])
            .allows(ActivationSource::Keyboard));
    }

    #[test]
    fn explicit_pointer_and_accessibility_actions_work_after_commit_frame() {
        let mut policy = ActivationPolicy::default();
        policy.begin_frame(true, [InputEvent::Commit]);
        let fresh_frame = policy.begin_frame(true, []);
        assert!(fresh_frame.allows(ActivationSource::Pointer));
        assert!(fresh_frame.allows(ActivationSource::Accessibility));
        assert!(!fresh_frame.allows(ActivationSource::Keyboard));
    }

    #[test]
    fn repeated_or_modified_keypresses_do_not_repeat_effects() {
        for (repeat, modified) in [(true, false), (false, true), (true, true)] {
            let mut policy = ActivationPolicy::default();
            assert!(!policy
                .begin_frame(
                    true,
                    [InputEvent::ConfirmKey {
                        key: ConfirmKey::Enter,
                        pressed: true,
                        repeat,
                        modified,
                    }],
                )
                .allows(ActivationSource::Keyboard));
        }
    }

    #[test]
    fn held_key_without_backend_repeat_flag_is_blocked_until_release() {
        for confirm in [ConfirmKey::Enter, ConfirmKey::Space] {
            let mut policy = ActivationPolicy::default();
            assert!(policy
                .begin_frame(true, [key(confirm, true)])
                .allows(ActivationSource::Keyboard));
            policy.begin_frame(true, []);
            assert!(!policy
                .begin_frame(true, [key(confirm, true)])
                .allows(ActivationSource::Keyboard));
            policy.begin_frame(true, [key(confirm, false)]);
            assert!(policy
                .begin_frame(true, [key(confirm, true)])
                .allows(ActivationSource::Keyboard));
        }
    }

    #[test]
    fn focus_loss_cancels_preedit_but_keeps_delayed_key_fenced() {
        let mut policy = ActivationPolicy::default();
        policy.begin_frame(true, [InputEvent::Preedit { empty: false }]);
        assert!(!policy
            .begin_frame(false, [])
            .allows(ActivationSource::Accessibility));
        assert!(!policy.composing());
        assert!(!policy
            .begin_frame(true, [key(ConfirmKey::Enter, true)])
            .allows(ActivationSource::Keyboard));
        policy.begin_frame(true, [key(ConfirmKey::Enter, false)]);
        assert!(policy
            .begin_frame(true, [key(ConfirmKey::Enter, true)])
            .allows(ActivationSource::Keyboard));
    }

    #[test]
    fn one_release_does_not_unfence_another_held_confirmation_key() {
        let mut policy = ActivationPolicy::default();
        policy.begin_frame(true, [InputEvent::Commit]);
        policy.begin_frame(
            true,
            [key(ConfirmKey::Enter, true), key(ConfirmKey::Space, true)],
        );
        policy.begin_frame(true, [key(ConfirmKey::Enter, false)]);
        assert!(!policy
            .begin_frame(true, [key(ConfirmKey::Enter, true)])
            .allows(ActivationSource::Keyboard));
    }
}
