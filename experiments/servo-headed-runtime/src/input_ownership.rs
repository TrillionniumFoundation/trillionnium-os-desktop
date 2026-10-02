//! Native input ownership for the fixed physical-pixel qualification viewport.
//! No event may reuse a content coordinate after pointer/focus withdrawal.

const MAX_HELD_BUTTONS: usize = 16;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Button {
    Primary,
    Secondary,
    Auxiliary,
    Back,
    Forward,
    Other(u16),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ButtonAction {
    Down,
    Up,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReleaseOutcome {
    Accepted,
    DispatchFailed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WithdrawalReason {
    ContentBoundary,
    WindowLeave,
    WindowFocusLost,
    ContentCrash,
    ButtonCapacity,
    ReleaseDispatchFailed,
}

impl WithdrawalReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::ContentBoundary => "content_boundary",
            Self::WindowLeave => "window_leave",
            Self::WindowFocusLost => "window_focus_lost",
            Self::ContentCrash => "content_crash",
            Self::ButtonCapacity => "held_button_capacity",
            Self::ReleaseDispatchFailed => "release_dispatch_failed",
        }
    }
}

/// Withdrawal of an admitted gesture requires a fresh Servo owner. At the pin
/// there is no mouse-cancel API, and dropping a WebView does not reset Servo's
/// global pressed-button mask. No Up or automatic replacement is authorized.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RecoveryRequired {
    pub generation: u32,
    pub reason: WithdrawalReason,
    pub held_buttons: usize,
}

#[derive(Debug)]
pub struct InputOwnership {
    width: f64,
    height: f64,
    chrome_height: f64,
    generation: u32,
    live: bool,
    window_focused: bool,
    content_keyboard: bool,
    point: Option<(f32, f32)>,
    ime_open: bool,
    ime_enabled: bool,
    held_buttons: Vec<Button>,
    pending_releases: Vec<Button>,
    recovery_required: Option<RecoveryRequired>,
    pending_withdrawal: Option<RecoveryRequired>,
}

impl InputOwnership {
    pub fn new(width: u32, height: u32, chrome_height: u32) -> Self {
        assert!(width > 0 && chrome_height > 0 && chrome_height < height);
        Self {
            width: width.into(),
            height: height.into(),
            chrome_height: chrome_height.into(),
            generation: 1,
            live: true,
            window_focused: false,
            content_keyboard: false,
            point: None,
            ime_open: false,
            ime_enabled: false,
            held_buttons: Vec::new(),
            pending_releases: Vec::new(),
            recovery_required: None,
            pending_withdrawal: None,
        }
    }

    pub fn focused(&mut self, focused: bool) -> bool {
        self.window_focused = focused;
        if !focused {
            self.point = None;
            self.content_keyboard = false;
            self.withdraw_held(WithdrawalReason::WindowFocusLost);
        }
        self.withdraw_ime_if_needed()
    }

    pub fn pointer(&mut self, x: f64, y: f64) -> Option<(f32, f32)> {
        self.point = if self.live
            && self.window_focused
            && x.is_finite()
            && y.is_finite()
            && x >= 0.0
            && x < self.width
            && y >= self.chrome_height
            && y < self.height
        {
            Some((x as f32, (y - self.chrome_height) as f32))
        } else {
            None
        };
        if self.point.is_none() {
            self.withdraw_held(WithdrawalReason::ContentBoundary);
        }
        self.point
    }

    pub fn pointer_left(&mut self) {
        self.point = None;
        self.withdraw_held(WithdrawalReason::WindowLeave);
    }
    pub fn point(&self) -> Option<(f32, f32)> {
        if self.live && self.window_focused {
            self.point
        } else {
            None
        }
    }

    pub fn window_focused(&self) -> bool {
        self.live && self.window_focused
    }

    pub fn button_ready(&self, generation: u32, button: Button) -> bool {
        self.current_callback(generation)
            && self.point().is_some()
            && !self.held_buttons.contains(&button)
            && !self.pending_releases.contains(&button)
    }

    /// A physical press selects keyboard ownership; trusted chrome withdraws it.
    pub fn pressed(&mut self) -> bool {
        self.content_keyboard = self.point().is_some();
        self.withdraw_ime_if_needed()
    }

    /// Only a current-generation, content-owned Down can authorize a matching
    /// Up. Release coordinates must be current, never a saved old press point.
    pub fn route_button(
        &mut self,
        generation: u32,
        button: Button,
        action: ButtonAction,
    ) -> Option<(f32, f32)> {
        if !self.current_callback(generation) {
            return None;
        }
        let point = self.point()?;
        match action {
            ButtonAction::Down => {
                if self.held_buttons.contains(&button) || self.pending_releases.contains(&button) {
                    return None;
                }
                if self.held_buttons.len() + self.pending_releases.len() == MAX_HELD_BUTTONS {
                    self.withdraw_held(WithdrawalReason::ButtonCapacity);
                    return None;
                }
                self.held_buttons.push(button);
            }
            ButtonAction::Up => {
                let index = self.held_buttons.iter().position(|held| *held == button)?;
                self.held_buttons.remove(index);
                self.pending_releases.push(button);
            }
        }
        Some(point)
    }

    /// The native dispatcher binds this outcome to the real InputEventId of its
    /// matching physical Up. Sending an Up is not itself delivery confirmation.
    pub fn acknowledge_release(
        &mut self,
        generation: u32,
        button: Button,
        outcome: ReleaseOutcome,
    ) -> bool {
        if !self.current_callback(generation) {
            return false;
        }
        let Some(index) = self
            .pending_releases
            .iter()
            .position(|pending| *pending == button)
        else {
            return false;
        };
        if outcome == ReleaseOutcome::DispatchFailed {
            self.withdraw_held(WithdrawalReason::ReleaseDispatchFailed);
        } else {
            self.pending_releases.remove(index);
        }
        true
    }

    fn withdraw_held(&mut self, reason: WithdrawalReason) {
        let unsettled = self.held_buttons.len() + self.pending_releases.len();
        if unsettled == 0 || self.recovery_required.is_some() {
            return;
        }
        let outcome = RecoveryRequired {
            generation: self.generation,
            reason,
            held_buttons: unsettled,
        };
        // Latch before retiring the renderer; every input path and callback is
        // already closed even when hide/drop completion is asynchronous.
        self.live = false;
        self.point = None;
        self.content_keyboard = false;
        self.ime_enabled = false;
        self.held_buttons.clear();
        self.pending_releases.clear();
        self.recovery_required = Some(outcome);
        self.pending_withdrawal = Some(outcome);
    }

    pub fn take_withdrawal(&mut self) -> Option<RecoveryRequired> {
        self.pending_withdrawal.take()
    }

    pub fn recovery_required(&self) -> Option<RecoveryRequired> {
        self.recovery_required
    }

    pub fn keyboard_allowed(&self) -> bool {
        self.live && self.window_focused && self.content_keyboard
    }

    pub fn begin_ime(&mut self) -> bool {
        if !self.keyboard_allowed() || !self.ime_enabled || self.ime_open {
            return false;
        }
        self.ime_open = true;
        true
    }

    pub fn ime_allowed(&self) -> bool {
        self.keyboard_allowed() && self.ime_enabled && self.ime_open
    }
    pub fn enable_ime(&mut self) {
        self.ime_enabled = self.live;
    }
    pub fn disable_ime(&mut self) -> bool {
        self.ime_enabled = false;
        self.end_ime()
    }
    pub fn ime_context_allowed(&self) -> bool {
        self.keyboard_allowed() && self.ime_enabled
    }
    pub fn end_ime(&mut self) -> bool {
        std::mem::replace(&mut self.ime_open, false)
    }

    fn withdraw_ime_if_needed(&mut self) -> bool {
        if !self.keyboard_allowed() {
            self.end_ime()
        } else {
            false
        }
    }

    pub fn crashed(&mut self) -> bool {
        self.withdraw_held(WithdrawalReason::ContentCrash);
        self.live = false;
        self.point = None;
        self.content_keyboard = false;
        self.ime_enabled = false;
        self.end_ime()
    }

    /// Replacement never inherits old input coordinates, focus or composition.
    pub fn reconstruct(&mut self, generation: u32) -> bool {
        if self.live || self.recovery_required.is_some() || generation <= self.generation {
            return false;
        }
        self.generation = generation;
        self.live = true;
        self.point = None;
        self.content_keyboard = false;
        self.ime_open = false;
        self.ime_enabled = false;
        true
    }

    pub fn current_callback(&self, generation: u32) -> bool {
        self.live && self.generation == generation
    }
}

/// Qualification-only sequencing of the original three native content pairs.
/// Event identifiers are the actual values returned by Servo, never counters
/// supplied by the stimulus process. This does not queue real user input.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CheckpointPhase {
    PreludeReady,
    ChromeReady,
    Ready,
    DownAccepted,
    UpAccepted,
}

impl CheckpointPhase {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::PreludeReady => "prelude_ready",
            Self::ChromeReady => "chrome_ready",
            Self::Ready => "ready",
            Self::DownAccepted => "down_accepted",
            Self::UpAccepted => "up_accepted",
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct InputCheckpoint<I> {
    pub sequence: usize,
    pub phase: CheckpointPhase,
    pub point: Option<(u32, u32)>,
    pub pointer_event: Option<I>,
    pub down_event: Option<I>,
    pub up_event: Option<I>,
    pub completed_pairs: usize,
}

pub struct QualificationInput<I> {
    prelude_event: Option<I>,
    prelude_accepted: bool,
    chrome_seen: bool,
    completed_pairs: usize,
    pointer_event: Option<I>,
    pointer_accepted: bool,
    down_event: Option<I>,
    down_accepted: bool,
    up_event: Option<I>,
}

impl<I: Copy + Eq> QualificationInput<I> {
    const POINTS: [(u32, u32); 3] = [(200, 68), (400, 100), (200, 68)];

    pub fn new() -> Self {
        Self {
            prelude_event: None,
            prelude_accepted: false,
            chrome_seen: false,
            completed_pairs: 0,
            pointer_event: None,
            pointer_accepted: false,
            down_event: None,
            down_accepted: false,
            up_event: None,
        }
    }

    pub fn observe_chrome(&mut self, generation: u32, focused: bool) -> Option<InputCheckpoint<I>> {
        if generation != 1
            || !focused
            || !self.prelude_accepted
            || self.chrome_seen
            || self.completed_pairs != 0
        {
            return None;
        }
        self.chrome_seen = true;
        Some(InputCheckpoint {
            sequence: 0,
            phase: CheckpointPhase::ChromeReady,
            point: None,
            pointer_event: None,
            down_event: None,
            up_event: None,
            completed_pairs: 0,
        })
    }

    fn point_matches(&self, generation: u32, point: Option<(f32, f32)>) -> bool {
        generation == 1
            && Self::POINTS
                .get(self.completed_pairs)
                .is_some_and(|&(x, y)| point == Some((x as f32, y as f32)))
    }

    pub fn observe_pointer(&mut self, generation: u32, point: (f32, f32), event: I) {
        if !self.chrome_seen {
            if generation == 1 && point == (200.0, 68.0) && !self.prelude_accepted {
                self.prelude_event = Some(event);
            }
            return;
        }
        if self.down_event.is_some() || self.up_event.is_some() {
            return;
        }
        self.pointer_event = self.point_matches(generation, Some(point)).then_some(event);
        self.pointer_accepted = false;
    }

    pub fn allows_down(&self, generation: u32, point: Option<(f32, f32)>) -> bool {
        self.point_matches(generation, point)
            && self.chrome_seen
            && self.pointer_accepted
            && self.down_event.is_none()
            && self.up_event.is_none()
    }

    pub fn allows_up(&self, generation: u32, point: Option<(f32, f32)>) -> bool {
        self.point_matches(generation, point) && self.down_accepted && self.up_event.is_none()
    }

    pub fn submit_down(&mut self, event: I) -> Result<(), &'static str> {
        if !self.pointer_accepted
            || self.down_event.is_some()
            || self.up_event.is_some()
            || self.pointer_event == Some(event)
        {
            return Err("qualification Down submission has no fresh ready pointer");
        }
        self.down_event = Some(event);
        Ok(())
    }

    pub fn submit_up(&mut self, event: I) -> Result<(), &'static str> {
        if !self.down_accepted
            || self.up_event.is_some()
            || self.down_event == Some(event)
            || self.pointer_event == Some(event)
        {
            return Err("qualification Up submission has no matched accepted Down");
        }
        self.up_event = Some(event);
        Ok(())
    }

    pub fn acknowledge(
        &mut self,
        generation: u32,
        point: Option<(f32, f32)>,
        focused: bool,
        event: I,
        accepted: bool,
    ) -> Result<Option<InputCheckpoint<I>>, &'static str> {
        if !self.prelude_accepted && self.prelude_event == Some(event) {
            if generation != 1 || point != Some((200.0, 68.0)) || !focused || !accepted {
                return Err(
                    "qualification prelude pointer failed or lost its current native owner",
                );
            }
            self.prelude_accepted = true;
            return Ok(Some(InputCheckpoint {
                sequence: 0,
                phase: CheckpointPhase::PreludeReady,
                point: Some((200, 68)),
                pointer_event: Some(event),
                down_event: None,
                up_event: None,
                completed_pairs: 0,
            }));
        }
        let phase = if self.pointer_event == Some(event) && !self.pointer_accepted {
            CheckpointPhase::Ready
        } else if self.down_event == Some(event) && !self.down_accepted {
            CheckpointPhase::DownAccepted
        } else if self.up_event == Some(event) {
            CheckpointPhase::UpAccepted
        } else {
            return Ok(None);
        };
        if !focused || !self.point_matches(generation, point) || !accepted {
            return Err("qualification input callback failed or lost its current native owner");
        }
        match phase {
            CheckpointPhase::Ready => self.pointer_accepted = true,
            CheckpointPhase::DownAccepted => self.down_accepted = true,
            CheckpointPhase::UpAccepted => {}
            CheckpointPhase::ChromeReady | CheckpointPhase::PreludeReady => unreachable!(),
        }
        let checkpoint = InputCheckpoint {
            sequence: self.completed_pairs + 1,
            phase,
            point: Self::POINTS.get(self.completed_pairs).copied(),
            pointer_event: self.pointer_event,
            down_event: self.down_event,
            up_event: self.up_event,
            completed_pairs: self.completed_pairs
                + usize::from(phase == CheckpointPhase::UpAccepted),
        };
        if phase == CheckpointPhase::UpAccepted {
            self.completed_pairs += 1;
            self.pointer_event = None;
            self.pointer_accepted = false;
            self.down_event = None;
            self.down_accepted = false;
            self.up_event = None;
        }
        Ok(Some(checkpoint))
    }

    pub fn complete(&self) -> bool {
        self.completed_pairs == Self::POINTS.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn owner() -> InputOwnership {
        let mut o = InputOwnership::new(1024, 768, 64);
        o.focused(true);
        o.enable_ime();
        o
    }
    #[test]
    fn chrome_click_cannot_reuse_prior_content_point() {
        let mut o = owner();
        assert_eq!(o.pointer(200.0, 132.0), Some((200.0, 68.0)));
        o.pressed();
        assert!(o.keyboard_allowed());
        assert_eq!(o.pointer(10.0, 10.0), None);
        o.pressed();
        assert_eq!(o.point(), None);
        assert!(!o.keyboard_allowed());
    }
    #[test]
    fn viewport_edges_and_nonfinite_points_fail_closed() {
        for (x, y) in [
            (-1.0, 100.0),
            (1024.0, 100.0),
            (1.0, 768.0),
            (f64::NAN, 100.0),
            (1.0, f64::INFINITY),
        ] {
            assert_eq!(owner().pointer(x, y), None);
        }
        assert_eq!(owner().pointer(0.0, 64.0), Some((0.0, 0.0)));
    }
    #[test]
    fn pointer_leave_drops_buttons_and_wheel() {
        let mut o = owner();
        o.pointer(10.0, 100.0);
        o.pointer_left();
        assert_eq!(o.point(), None);
    }
    #[test]
    fn unfocused_window_never_forwards_input() {
        let mut o = owner();
        o.pointer(10.0, 100.0);
        o.pressed();
        o.begin_ime();
        assert!(o.focused(false));
        assert_eq!(o.pointer(10.0, 100.0), None);
        assert!(!o.keyboard_allowed());
        assert!(!o.ime_allowed());
        o.focused(true);
        assert!(!o.keyboard_allowed());
    }
    #[test]
    fn native_ime_requires_current_content_focus_and_open_composition() {
        let mut o = owner();
        assert!(!o.begin_ime());
        o.pointer(10.0, 100.0);
        o.pressed();
        assert!(o.begin_ime());
        assert!(!o.begin_ime());
        assert!(o.ime_allowed());
        assert!(o.end_ime());
        assert!(!o.end_ime());
        assert!(!o.ime_allowed());
    }
    #[test]
    fn crash_and_replacement_reject_stale_callback_and_input() {
        let mut o = owner();
        o.pointer(10.0, 100.0);
        o.pressed();
        o.begin_ime();
        assert!(o.crashed());
        assert!(!o.current_callback(1));
        assert!(!o.reconstruct(1));
        assert!(!o.reconstruct(0));
        assert!(o.reconstruct(2));
        assert!(!o.current_callback(1));
        assert!(o.current_callback(2));
        assert_eq!(o.point(), None);
        assert!(!o.keyboard_allowed());
        assert!(!o.ime_allowed());
        assert!(!o.reconstruct(3));
    }

    #[test]
    fn one_native_context_supports_multiple_compositions() {
        let mut o = owner();
        o.pointer(10.0, 100.0);
        o.pressed();
        for _ in 0..2 {
            assert!(o.begin_ime());
            assert!(o.ime_allowed());
            assert!(o.end_ime());
        }
        assert!(o.ime_context_allowed());
        o.disable_ime();
        assert!(!o.begin_ime());
    }

    #[test]
    fn enabled_context_before_physical_press_does_not_grant_keyboard() {
        let mut o = owner();
        assert!(!o.keyboard_allowed());
        assert!(!o.begin_ime());
        o.pointer(10.0, 100.0);
        o.pressed();
        assert!(o.begin_ime());
        o.pointer(10.0, 10.0);
        assert!(o.pressed());
        assert!(!o.ime_allowed());
        o.pointer(10.0, 100.0);
        o.pressed();
        assert!(o.begin_ime());
    }

    fn held() -> InputOwnership {
        let mut o = owner();
        o.pointer(20.0, 100.0);
        o.pressed();
        assert_eq!(
            o.route_button(1, Button::Primary, ButtonAction::Down),
            Some((20.0, 36.0))
        );
        o
    }

    #[test]
    fn matched_down_and_up_preserve_normal_current_content_gesture() {
        let mut o = held();
        o.pointer(30.0, 110.0);
        assert_eq!(
            o.route_button(1, Button::Primary, ButtonAction::Up),
            Some((30.0, 46.0))
        );
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Up), None);
        assert!(o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
        o.pointer_left();
        assert_eq!(o.recovery_required(), None);
        assert!(o.current_callback(1));
    }

    #[test]
    fn orphan_and_wrong_button_releases_do_not_authorize_an_event() {
        let mut o = owner();
        o.pointer(20.0, 100.0);
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Up), None);
        o.route_button(1, Button::Primary, ButtonAction::Down)
            .unwrap();
        assert_eq!(o.route_button(1, Button::Secondary, ButtonAction::Up), None);
        o.pointer_left();
        assert_eq!(o.recovery_required().unwrap().held_buttons, 1);
    }

    #[test]
    fn duplicate_down_cannot_create_a_second_release_authority() {
        let mut o = held();
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Down), None);
        assert!(
            o.route_button(1, Button::Primary, ButtonAction::Up)
                .is_some()
        );
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Up), None);
        assert!(o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
        assert_eq!(o.recovery_required(), None);
    }

    #[test]
    fn held_content_leave_latches_all_input_and_requires_new_servo_owner() {
        let mut o = held();
        assert!(o.begin_ime());
        assert_eq!(o.pointer(10.0, 10.0), None);
        let expected = RecoveryRequired {
            generation: 1,
            reason: WithdrawalReason::ContentBoundary,
            held_buttons: 1,
        };
        assert_eq!(o.take_withdrawal(), Some(expected));
        assert_eq!(o.take_withdrawal(), None);
        assert_eq!(o.recovery_required(), Some(expected));
        assert_eq!(o.pointer(20.0, 100.0), None);
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Up), None);
        assert!(!o.keyboard_allowed());
        assert!(!o.ime_allowed());
        assert!(!o.begin_ime());
        assert!(!o.current_callback(1));
        assert!(!o.reconstruct(2));
        o.focused(true);
        o.enable_ime();
        o.pressed();
        assert!(!o.keyboard_allowed());
        assert!(!o.reconstruct(3));
    }

    #[test]
    fn native_window_leave_with_hold_is_a_typed_retirement_once() {
        let mut o = held();
        o.pointer_left();
        let expected = RecoveryRequired {
            generation: 1,
            reason: WithdrawalReason::WindowLeave,
            held_buttons: 1,
        };
        assert_eq!(o.take_withdrawal(), Some(expected));
        o.pointer_left();
        o.crashed();
        assert_eq!(o.take_withdrawal(), None);
        assert_eq!(o.recovery_required(), Some(expected));
    }

    #[test]
    fn focus_loss_with_hold_dismisses_composition_and_never_reopens_input() {
        let mut o = held();
        assert!(o.begin_ime());
        assert!(o.focused(false));
        let outcome = o.take_withdrawal().unwrap();
        assert_eq!(outcome.reason, WithdrawalReason::WindowFocusLost);
        assert_eq!(outcome.generation, 1);
        assert!(!o.ime_allowed());
        o.focused(true);
        assert_eq!(o.pointer(20.0, 100.0), None);
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Up), None);
        assert!(!o.current_callback(1));
    }

    #[test]
    fn held_crash_cannot_use_normal_same_servo_fixture_reconstruction() {
        let mut o = held();
        assert!(o.begin_ime());
        assert!(o.crashed());
        assert_eq!(
            o.take_withdrawal().unwrap().reason,
            WithdrawalReason::ContentCrash
        );
        assert!(!o.reconstruct(2));
        assert_eq!(o.route_button(2, Button::Primary, ButtonAction::Up), None);
        assert!(!o.current_callback(2));
    }

    #[test]
    fn several_buttons_withdraw_only_remaining_admitted_holds() {
        let mut o = held();
        o.route_button(1, Button::Secondary, ButtonAction::Down)
            .unwrap();
        o.route_button(1, Button::Primary, ButtonAction::Up)
            .unwrap();
        assert!(o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
        o.pointer_left();
        assert_eq!(o.take_withdrawal().unwrap().held_buttons, 1);
        assert_eq!(o.route_button(1, Button::Secondary, ButtonAction::Up), None);
    }

    #[test]
    fn bounded_held_button_capacity_retires_without_forwarding_extra_down() {
        let mut o = owner();
        o.pointer(20.0, 100.0);
        for value in 0..MAX_HELD_BUTTONS as u16 {
            o.route_button(1, Button::Other(value + 100), ButtonAction::Down)
                .unwrap();
        }
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Down), None);
        let outcome = o.take_withdrawal().unwrap();
        assert_eq!(outcome.reason, WithdrawalReason::ButtonCapacity);
        assert_eq!(outcome.held_buttons, MAX_HELD_BUTTONS);
        assert!(!o.current_callback(1));
    }

    #[test]
    fn stale_generation_down_or_up_cannot_touch_current_binding() {
        let mut o = owner();
        o.pointer(20.0, 100.0);
        assert_eq!(o.route_button(0, Button::Primary, ButtonAction::Down), None);
        o.route_button(1, Button::Primary, ButtonAction::Down)
            .unwrap();
        assert_eq!(o.route_button(0, Button::Primary, ButtonAction::Up), None);
        o.route_button(1, Button::Primary, ButtonAction::Up)
            .unwrap();
        assert!(o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
        o.crashed();
        assert!(o.reconstruct(2));
        o.pointer(20.0, 100.0);
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Up), None);
        assert_eq!(o.route_button(2, Button::Primary, ButtonAction::Up), None);
        assert_eq!(o.recovery_required(), None);
    }

    #[test]
    fn physical_up_waits_for_its_matching_callback_before_withdrawal_is_safe() {
        let mut o = held();
        o.route_button(1, Button::Primary, ButtonAction::Up)
            .unwrap();
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Down), None);
        o.pointer_left();
        assert_eq!(o.take_withdrawal().unwrap().held_buttons, 1);
        assert!(!o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
        assert!(!o.reconstruct(2));
    }

    #[test]
    fn failed_up_dispatch_cannot_forget_pressed_engine_state() {
        let mut o = held();
        o.route_button(1, Button::Primary, ButtonAction::Up)
            .unwrap();
        assert!(o.acknowledge_release(1, Button::Primary, ReleaseOutcome::DispatchFailed));
        assert_eq!(
            o.take_withdrawal().unwrap().reason,
            WithdrawalReason::ReleaseDispatchFailed
        );
        assert!(!o.current_callback(1));
        assert_eq!(o.route_button(1, Button::Primary, ButtonAction::Down), None);
    }

    #[test]
    fn stale_or_wrong_release_callback_cannot_clear_a_current_pending_up() {
        let mut o = held();
        o.route_button(1, Button::Primary, ButtonAction::Up)
            .unwrap();
        assert!(!o.acknowledge_release(0, Button::Primary, ReleaseOutcome::Accepted));
        assert!(!o.acknowledge_release(1, Button::Secondary, ReleaseOutcome::Accepted));
        assert!(o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
        assert!(!o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
        o.pointer_left();
        assert_eq!(o.recovery_required(), None);
    }

    #[test]
    fn exactly_three_ungated_native_pairs_can_lose_one_pair_before_release_ack() {
        let mut o = owner();
        let mut forwarded = 0;
        let mut downs = 0;
        for (index, (x, y)) in [(200.0, 132.0), (400.0, 164.0), (200.0, 132.0)]
            .into_iter()
            .enumerate()
        {
            o.pointer(x, y);
            o.pressed();
            if o.route_button(1, Button::Primary, ButtonAction::Down)
                .is_some()
            {
                forwarded += 1;
                downs += 1;
            }
            if o.route_button(1, Button::Primary, ButtonAction::Up)
                .is_some()
            {
                forwarded += 1;
            }
            if index >= 1 {
                assert!(o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
            }
        }
        assert_eq!((forwarded, downs), (4, 2));
        assert!(o.current_callback(1));
        assert_eq!(o.recovery_required(), None);
    }

    fn qualification() -> QualificationInput<u32> {
        let mut gate = QualificationInput::new();
        gate.observe_pointer(1, (200.0, 68.0), 100);
        assert_eq!(
            gate.acknowledge(1, Some((200.0, 68.0)), true, 100, true)
                .unwrap()
                .unwrap()
                .phase,
            CheckpointPhase::PreludeReady
        );
        assert!(gate.observe_chrome(1, true).is_some());
        gate
    }

    #[test]
    fn three_checkpoint_pairs_require_their_actual_pointer_down_and_up_callbacks() {
        let mut gate = qualification();
        let mut o = owner();
        let mut forwarded = 0;
        for (index, (x, y)) in [(200.0, 132.0), (400.0, 164.0), (200.0, 132.0)]
            .into_iter()
            .enumerate()
        {
            let event = 10 + index as u32 * 3;
            let point = o.pointer(x, y);
            gate.observe_pointer(1, point.unwrap(), event);
            assert!(!gate.allows_down(1, point));
            assert!(o.button_ready(1, Button::Primary));
            let ready = gate
                .acknowledge(1, point, true, event, true)
                .unwrap()
                .unwrap();
            assert_eq!(ready.phase, CheckpointPhase::Ready);
            assert!(gate.allows_down(1, point));
            o.pressed();
            assert!(
                o.route_button(1, Button::Primary, ButtonAction::Down)
                    .is_some()
            );
            forwarded += 1;
            gate.submit_down(event + 1).unwrap();
            assert!(!gate.allows_up(1, point));
            let down = gate
                .acknowledge(1, point, true, event + 1, true)
                .unwrap()
                .unwrap();
            assert_eq!(down.phase, CheckpointPhase::DownAccepted);
            assert!(gate.allows_up(1, point));
            assert!(
                o.route_button(1, Button::Primary, ButtonAction::Up)
                    .is_some()
            );
            forwarded += 1;
            gate.submit_up(event + 2).unwrap();
            assert!(!o.button_ready(1, Button::Primary));
            assert!(!gate.allows_down(1, point));
            assert!(o.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
            let up = gate
                .acknowledge(1, point, true, event + 2, true)
                .unwrap()
                .unwrap();
            assert_eq!(up.phase, CheckpointPhase::UpAccepted);
            assert_eq!(up.completed_pairs, index + 1);
            assert_eq!(up.pointer_event, ready.pointer_event);
            assert_eq!(up.down_event, down.down_event);
            assert!(o.button_ready(1, Button::Primary));
            assert_eq!(gate.complete(), index == 2);
        }
        assert_eq!(forwarded, 6);
        assert_eq!(o.recovery_required(), None);
    }

    #[test]
    fn prelude_and_chrome_require_current_native_focus_and_real_pointer_callback() {
        let mut gate = QualificationInput::new();
        assert!(gate.observe_chrome(1, true).is_none());
        gate.observe_pointer(1, (200.0, 68.0), 1);
        assert!(
            gate.acknowledge(1, Some((200.0, 68.0)), false, 1, true)
                .is_err()
        );
        assert!(
            gate.acknowledge(2, Some((200.0, 68.0)), true, 1, true)
                .is_err()
        );
        assert!(
            gate.acknowledge(1, Some((200.0, 68.0)), true, 1, false)
                .is_err()
        );
        assert!(gate.observe_chrome(1, true).is_none());
        assert!(
            gate.acknowledge(1, Some((200.0, 68.0)), true, 1, true)
                .unwrap()
                .is_some()
        );
        assert!(gate.observe_chrome(2, true).is_none());
        assert!(gate.observe_chrome(1, false).is_none());
        assert!(gate.observe_chrome(1, true).is_some());
        assert!(gate.observe_chrome(1, true).is_none());
        assert!(!gate.complete());
    }

    #[test]
    fn mismatched_duplicate_stale_or_failed_input_callbacks_never_complete_a_pair() {
        for phase in 0..3 {
            let mut gate = qualification();
            let point = Some((200.0, 68.0));
            gate.observe_pointer(1, point.unwrap(), 1);
            if phase > 0 {
                gate.acknowledge(1, point, true, 1, true).unwrap();
                gate.submit_down(2).unwrap();
            }
            if phase > 1 {
                gate.acknowledge(1, point, true, 2, true).unwrap();
                gate.submit_up(3).unwrap();
            }
            let event = phase + 1;
            assert!(
                gate.acknowledge(1, point, true, 99, true)
                    .unwrap()
                    .is_none()
            );
            assert!(gate.acknowledge(2, point, true, event, true).is_err());
            assert!(
                gate.acknowledge(1, Some((1.0, 1.0)), true, event, true)
                    .is_err()
            );
            assert!(gate.acknowledge(1, point, false, event, true).is_err());
            assert!(gate.acknowledge(1, point, true, event, false).is_err());
            assert!(!gate.complete());
            assert!(
                gate.acknowledge(1, point, true, event, true)
                    .unwrap()
                    .is_some()
            );
            assert!(
                gate.acknowledge(1, point, true, event, true)
                    .unwrap()
                    .is_none()
            );
            assert!(!gate.complete());
        }
    }

    #[test]
    fn unacknowledged_or_reused_input_submission_cannot_advance_checkpoint() {
        let mut gate = qualification();
        assert!(gate.submit_down(2).is_err());
        assert!(gate.submit_up(3).is_err());
        gate.observe_pointer(1, (200.0, 68.0), 1);
        gate.acknowledge(1, Some((200.0, 68.0)), true, 1, true)
            .unwrap();
        assert!(gate.submit_down(1).is_err());
        gate.submit_down(2).unwrap();
        assert!(gate.submit_down(4).is_err());
        assert!(gate.submit_up(3).is_err());
        gate.acknowledge(1, Some((200.0, 68.0)), true, 2, true)
            .unwrap();
        assert!(gate.submit_up(2).is_err());
        assert!(gate.submit_up(1).is_err());
        gate.submit_up(3).unwrap();
        assert!(gate.submit_up(4).is_err());
        assert!(!gate.complete());
    }
}
