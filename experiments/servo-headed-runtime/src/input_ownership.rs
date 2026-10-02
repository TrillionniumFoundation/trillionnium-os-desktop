//! Native input ownership for the fixed physical-pixel qualification viewport.
//! No event may reuse a content coordinate after pointer/focus withdrawal.

use std::collections::VecDeque;
use std::time::{Duration, Instant};

const MAX_HELD_BUTTONS: usize = 16;
pub const MAX_NATIVE_EVENTS: usize = 64;
pub const MAX_NATIVE_PAYLOAD_BYTES: usize = 16 * 1024;
pub const MAX_NATIVE_EVENT_BYTES: usize = 4 * 1024;
pub const NATIVE_EPISODE_BUDGET: Duration = Duration::from_secs(5);

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
    OrderedInputRefused,
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
            Self::OrderedInputRefused => "ordered_input_refused",
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
        let point = self.point()?;
        self.route_button_at(generation, button, action, point)
    }

    pub fn route_button_at(
        &mut self,
        generation: u32,
        button: Button,
        action: ButtonAction,
        point: (f32, f32),
    ) -> Option<(f32, f32)> {
        if !self.current_callback(generation)
            || !self.window_focused
            || !point.0.is_finite()
            || !point.1.is_finite()
            || point.0 < 0.0
            || point.1 < 0.0
            || point.0 as f64 >= self.width
            || point.1 as f64 >= self.height - self.chrome_height
        {
            return None;
        }
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

    pub fn refuse_ordered_input(&mut self) {
        self.withdraw_held(WithdrawalReason::OrderedInputRefused);
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

/// OS-side projection only. Enqueueing never modifies Servo's held/IME ledger.
#[derive(Debug)]
pub struct PhysicalIngress {
    width: f64,
    height: f64,
    chrome: f64,
    pub epoch: u64,
    focused: bool,
    point: Option<(f32, f32)>,
    keyboard: bool,
    ime_enabled: bool,
    ime_open: bool,
    held: Vec<Button>,
}
impl PhysicalIngress {
    pub fn new(width: u32, height: u32, chrome: u32) -> Self {
        Self {
            width: width.into(),
            height: height.into(),
            chrome: chrome.into(),
            epoch: 0,
            focused: false,
            point: None,
            keyboard: false,
            ime_enabled: false,
            ime_open: false,
            held: Vec::new(),
        }
    }
    pub fn barrier(&mut self) {
        self.epoch = self
            .epoch
            .checked_add(1)
            .expect("native ownership epoch exhausted");
        self.point = None;
        self.keyboard = false;
        self.held.clear();
        self.ime_open = false;
        self.ime_enabled = false;
    }
    pub fn focused(&mut self, focused: bool) {
        if self.focused != focused {
            self.barrier();
        }
        self.focused = focused;
    }
    pub fn focused_now(&self) -> bool {
        self.focused
    }
    pub fn pointer(&mut self, x: f64, y: f64) -> Option<(f32, f32)> {
        if self.focused
            && x.is_finite()
            && y.is_finite()
            && x >= 0.0
            && x < self.width
            && y >= self.chrome
            && y < self.height
        {
            self.point = Some((x as f32, (y - self.chrome) as f32));
        } else {
            self.barrier();
        }
        self.point
    }
    pub fn point(&self) -> Option<(f32, f32)> {
        self.point
    }
    pub fn keyboard_allowed(&self) -> bool {
        self.focused && self.keyboard
    }
    pub fn button(
        &mut self,
        button: Button,
        action: ButtonAction,
    ) -> Result<Option<(f32, f32)>, LaneError> {
        let Some(point) = self.point else {
            self.keyboard = false;
            return Ok(None);
        };
        match action {
            ButtonAction::Down => {
                if self.held.contains(&button) {
                    return Err(LaneError::PhysicalSequence);
                }
                if self.held.len() == MAX_HELD_BUTTONS {
                    return Err(LaneError::Capacity);
                }
                self.held.push(button);
                self.keyboard = true;
            }
            ButtonAction::Up => {
                let Some(index) = self.held.iter().position(|value| *value == button) else {
                    return Err(LaneError::PhysicalSequence);
                };
                self.held.remove(index);
            }
        }
        Ok(Some(point))
    }
    pub fn ime_enabled(&mut self, enabled: bool) -> bool {
        self.ime_enabled = enabled;
        if !enabled {
            return std::mem::replace(&mut self.ime_open, false);
        }
        false
    }
    pub fn composition(&mut self, committing: bool) -> Option<bool> {
        if !self.keyboard_allowed() || !self.ime_enabled {
            return None;
        }
        let start = !self.ime_open;
        self.ime_open = !committing;
        Some(start)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NativeOwner {
    pub generation: u32,
    pub view: String,
    pub epoch: u64,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LaneError {
    Capacity,
    Payload,
    Expired,
    StaleOwner,
    DispatchFailed,
    UnknownSubmission,
    PhysicalSequence,
    OwnershipWithdrawn,
    Closed,
}
impl LaneError {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Capacity => "capacity",
            Self::Payload => "payload",
            Self::Expired => "expired",
            Self::StaleOwner => "stale_owner",
            Self::DispatchFailed => "dispatch_failed",
            Self::UnknownSubmission => "unknown_submission",
            Self::PhysicalSequence => "physical_sequence",
            Self::OwnershipWithdrawn => "ownership_withdrawn",
            Self::Closed => "closed",
        }
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum NativeKind {
    Move,
    Down(Button),
    Up(Button),
    Wheel,
    Key,
    Ime,
    LocalIme,
    SyntheticIme,
}
impl NativeKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Move => "move",
            Self::Down(_) => "down",
            Self::Up(_) => "up",
            Self::Wheel => "wheel",
            Self::Key => "key",
            Self::Ime => "ime",
            Self::LocalIme => "local_ime",
            Self::SyntheticIme => "synthetic_ime",
        }
    }
}
#[derive(Clone, Debug)]
pub struct NativeTicket {
    pub sequence: u64,
    pub owner: NativeOwner,
    pub kind: NativeKind,
    pub point: Option<(f32, f32)>,
    bytes: usize,
}
pub struct NativeSubmission<E> {
    pub ticket: NativeTicket,
    pub payload: E,
}
enum NativeFlight<I> {
    Submitting(NativeTicket),
    InFlight(NativeTicket, I),
}
pub enum NativeAck {
    Accepted(NativeTicket),
    Ignored,
}
/// One absolute deadline per nonempty episode; no ACK/admission can renew it.
/// The Submitting reservation remains owned while caller enters Servo without
/// holding a RefCell borrow. A callback before ID binding is unknown, not success.
pub struct OrderedNativeInput<I, E> {
    queue: VecDeque<NativeSubmission<E>>,
    flight: Option<NativeFlight<I>>,
    bytes: usize,
    next: u64,
    deadline: Option<Instant>,
    error: Option<LaneError>,
}
impl<I: Copy + Eq, E> OrderedNativeInput<I, E> {
    pub fn new() -> Self {
        Self {
            queue: VecDeque::new(),
            flight: None,
            bytes: 0,
            next: 1,
            deadline: None,
            error: None,
        }
    }
    pub fn idle(&self) -> bool {
        self.queue.is_empty() && self.flight.is_none() && self.error.is_none()
    }
    pub fn deadline(&self) -> Option<Instant> {
        self.deadline
    }
    pub fn check(&mut self, now: Instant) -> Result<(), LaneError> {
        if let Some(error) = self.error {
            return Err(error);
        }
        if self.deadline.is_some_and(|stop| now >= stop) {
            return self.close(LaneError::Expired);
        }
        Ok(())
    }
    pub fn close<T>(&mut self, error: LaneError) -> Result<T, LaneError> {
        self.error.get_or_insert(error);
        self.queue.clear();
        self.bytes = 0;
        Err(self.error.unwrap())
    }
    pub fn enqueue(
        &mut self,
        now: Instant,
        owner: NativeOwner,
        events: Vec<(NativeKind, Option<(f32, f32)>, usize, E)>,
    ) -> Result<Vec<NativeTicket>, LaneError> {
        self.check(now)?;
        if events.is_empty() || events.len() > 3 {
            return self.close(LaneError::Payload);
        }
        if owner.generation == 0 || owner.view.is_empty() || owner.view.len() > 128 {
            return self.close(LaneError::StaleOwner);
        }
        if let Some(first) = self
            .queue
            .front()
            .map(|event| &event.ticket.owner)
            .or_else(|| {
                self.flight.as_ref().map(|flight| match flight {
                    NativeFlight::Submitting(ticket) | NativeFlight::InFlight(ticket, _) => {
                        &ticket.owner
                    }
                })
            })
        {
            if first != &owner {
                return self.close(LaneError::StaleOwner);
            }
        }
        if events.iter().any(|(kind, point, _, _)| {
            point.is_some_and(|(x, y)| !x.is_finite() || !y.is_finite() || x < 0.0 || y < 0.0)
                || (matches!(
                    kind,
                    NativeKind::Move | NativeKind::Down(_) | NativeKind::Up(_) | NativeKind::Wheel
                ) && point.is_none())
        }) {
            return self.close(LaneError::Payload);
        }
        let total = events
            .iter()
            .try_fold(0usize, |sum, (_, _, bytes, _)| {
                if *bytes > MAX_NATIVE_EVENT_BYTES {
                    None
                } else {
                    sum.checked_add(*bytes)
                }
            })
            .ok_or(LaneError::Payload);
        let total = match total {
            Ok(value) => value,
            Err(error) => return self.close(error),
        };
        if self.queue.len() + usize::from(self.flight.is_some()) + events.len() > MAX_NATIVE_EVENTS
        {
            return self.close(LaneError::Capacity);
        }
        if self
            .bytes
            .checked_add(total)
            .is_none_or(|bytes| bytes > MAX_NATIVE_PAYLOAD_BYTES)
        {
            return self.close(LaneError::Payload);
        }
        if self.next.checked_add(events.len() as u64).is_none() {
            return self.close(LaneError::Capacity);
        }
        if self.deadline.is_none() {
            let Some(deadline) = now.checked_add(NATIVE_EPISODE_BUDGET) else {
                return self.close(LaneError::Expired);
            };
            self.deadline = Some(deadline);
        }
        self.bytes += total;
        let mut tickets = Vec::with_capacity(events.len());
        for (kind, point, bytes, payload) in events {
            let ticket = NativeTicket {
                sequence: self.next,
                owner: owner.clone(),
                kind,
                point,
                bytes,
            };
            self.next += 1;
            tickets.push(ticket.clone());
            self.queue.push_back(NativeSubmission { ticket, payload });
        }
        Ok(tickets)
    }
    pub fn begin(
        &mut self,
        now: Instant,
        owner: &NativeOwner,
    ) -> Result<Option<NativeSubmission<E>>, LaneError> {
        self.check(now)?;
        if self.flight.is_some() {
            return Ok(None);
        }
        let Some(event) = self.queue.pop_front() else {
            self.deadline = None;
            return Ok(None);
        };
        if &event.ticket.owner != owner {
            return self.close(LaneError::StaleOwner);
        }
        self.flight = Some(NativeFlight::Submitting(event.ticket.clone()));
        Ok(Some(event))
    }
    pub fn bind(
        &mut self,
        now: Instant,
        owner: &NativeOwner,
        ticket: &NativeTicket,
        id: I,
    ) -> Result<(), LaneError> {
        self.check(now)?;
        let valid = matches!(&self.flight, Some(NativeFlight::Submitting(reserved)) if reserved.sequence == ticket.sequence && &reserved.owner == owner && reserved.owner == ticket.owner);
        if !valid {
            return self.close(LaneError::UnknownSubmission);
        }
        self.flight = Some(NativeFlight::InFlight(ticket.clone(), id));
        Ok(())
    }
    pub fn local(
        &mut self,
        now: Instant,
        owner: &NativeOwner,
        ticket: &NativeTicket,
    ) -> Result<(), LaneError> {
        self.check(now)?;
        let valid = matches!(&self.flight, Some(NativeFlight::Submitting(reserved)) if reserved.sequence == ticket.sequence && &reserved.owner == owner && reserved.owner == ticket.owner && ticket.kind == NativeKind::LocalIme);
        if !valid {
            return self.close(LaneError::UnknownSubmission);
        }
        self.finish(ticket.bytes);
        Ok(())
    }
    pub fn acknowledge(
        &mut self,
        now: Instant,
        owner: &NativeOwner,
        id: I,
        accepted: bool,
    ) -> Result<NativeAck, LaneError> {
        self.check(now)?;
        if matches!(self.flight, Some(NativeFlight::Submitting(_))) {
            return self.close(LaneError::UnknownSubmission);
        }
        let Some(NativeFlight::InFlight(ticket, expected)) = &self.flight else {
            return Ok(NativeAck::Ignored);
        };
        if expected != &id || &ticket.owner != owner {
            return Ok(NativeAck::Ignored);
        }
        if !accepted {
            return self.close(LaneError::DispatchFailed);
        }
        let ticket = ticket.clone();
        self.finish(ticket.bytes);
        Ok(NativeAck::Accepted(ticket))
    }
    fn finish(&mut self, bytes: usize) {
        self.flight = None;
        self.bytes -= bytes;
        if self.queue.is_empty() {
            self.deadline = None;
        }
    }
    pub fn unsent_tickets(&self) -> Vec<NativeTicket> {
        self.queue
            .iter()
            .map(|event| event.ticket.clone())
            .collect()
    }
    pub fn withdraw(&mut self) -> Result<(), LaneError> {
        self.queue.clear();
        if self.flight.is_some() {
            return self.close(LaneError::OwnershipWithdrawn);
        }
        self.bytes = 0;
        self.deadline = None;
        Ok(())
    }
}

#[cfg(test)]
mod ordered_tests {
    use super::*;
    type Lane = OrderedNativeInput<u64, usize>;
    fn owner() -> NativeOwner {
        NativeOwner {
            generation: 1,
            view: "real-owned-view".into(),
            epoch: 1,
        }
    }
    fn add(
        lane: &mut Lane,
        now: Instant,
        kind: NativeKind,
        point: Option<(f32, f32)>,
        payload: usize,
    ) {
        lane.enqueue(now, owner(), vec![(kind, point, 32, payload)])
            .unwrap();
    }
    fn accepted(lane: &mut Lane, now: Instant, ticket: &NativeTicket, id: u64) {
        lane.bind(now, &owner(), ticket, id).unwrap();
        assert!(matches!(
            lane.acknowledge(now, &owner(), id, true),
            Ok(NativeAck::Accepted(_))
        ));
    }
    #[test]
    fn original_three_fast_pairs_are_retained_before_the_first_release_ack() {
        let start = Instant::now();
        let mut lane = Lane::new();
        let mut ingress = PhysicalIngress::new(800, 600, 32);
        ingress.focused(true);
        let points = [(200.0, 132.0), (400.0, 164.0), (200.0, 132.0)];
        for (pair, point) in points.into_iter().enumerate() {
            ingress.pointer(point.0, point.1);
            for (offset, action) in [ButtonAction::Down, ButtonAction::Up]
                .into_iter()
                .enumerate()
            {
                let point = ingress.button(Button::Primary, action).unwrap().unwrap();
                let kind = if action == ButtonAction::Down {
                    NativeKind::Down(Button::Primary)
                } else {
                    NativeKind::Up(Button::Primary)
                };
                add(&mut lane, start, kind, Some(point), pair * 2 + offset);
            }
        }
        let mut renderer = InputOwnership::new(800, 600, 32);
        renderer.focused(true);
        let mut down = 0;
        for expected in 0..6 {
            let submitted = lane.begin(start, &owner()).unwrap().unwrap();
            assert_eq!(submitted.payload, expected);
            assert!(lane.begin(start, &owner()).unwrap().is_none());
            let action = if expected % 2 == 0 {
                down += 1;
                ButtonAction::Down
            } else {
                ButtonAction::Up
            };
            let point = submitted.ticket.point.unwrap();
            assert_eq!(
                renderer.route_button_at(1, Button::Primary, action, point),
                Some(point)
            );
            // Renderer receives each physical Up's point, then its actual ID ACK,
            // before any next Down; physical ingress already received all six.
            accepted(&mut lane, start, &submitted.ticket, 100 + expected as u64);
            if action == ButtonAction::Up {
                assert!(renderer.acknowledge_release(1, Button::Primary, ReleaseOutcome::Accepted));
            }
        }
        assert_eq!(down, 3);
        assert!(lane.idle());
        assert!(renderer.recovery_required().is_none());
    }
    #[test]
    fn every_kind_shares_fifo_and_freezes_each_arrival_point() {
        let now = Instant::now();
        let mut lane = Lane::new();
        let events = [
            NativeKind::Move,
            NativeKind::Down(Button::Primary),
            NativeKind::Key,
            NativeKind::Wheel,
            NativeKind::Ime,
            NativeKind::Up(Button::Primary),
        ];
        for (index, kind) in events.into_iter().enumerate() {
            add(&mut lane, now, kind, Some((index as f32, 10.0)), index);
        }
        for (index, kind) in events.into_iter().enumerate() {
            let item = lane.begin(now, &owner()).unwrap().unwrap();
            assert_eq!(item.payload, index);
            assert_eq!(item.ticket.kind, kind);
            assert_eq!(item.ticket.point, Some((index as f32, 10.0)));
            accepted(&mut lane, now, &item.ticket, index as u64);
        }
        assert!(lane.idle());
    }
    #[test]
    fn ime_expansion_is_atomic_at_admission_and_cannot_interleave() {
        let now = Instant::now();
        let mut lane = Lane::new();
        lane.enqueue(
            now,
            owner(),
            vec![
                (NativeKind::Ime, None, 32, 1),
                (NativeKind::Ime, None, 40, 2),
            ],
        )
        .unwrap();
        add(&mut lane, now, NativeKind::Key, None, 3);
        for expected in 1..=3 {
            let item = lane.begin(now, &owner()).unwrap().unwrap();
            assert_eq!(item.payload, expected);
            accepted(&mut lane, now, &item.ticket, expected as u64);
        }
    }
    #[test]
    fn local_ime_control_is_ordered_without_fabricating_an_engine_ack() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(&mut lane, now, NativeKind::LocalIme, None, 1);
        add(&mut lane, now, NativeKind::Ime, None, 2);
        let local = lane.begin(now, &owner()).unwrap().unwrap();
        assert!(lane.begin(now, &owner()).unwrap().is_none());
        lane.local(now, &owner(), &local.ticket).unwrap();
        let ime = lane.begin(now, &owner()).unwrap().unwrap();
        assert_eq!(ime.payload, 2);
        assert!(matches!(
            lane.local(now, &owner(), &ime.ticket),
            Err(LaneError::UnknownSubmission)
        ));
    }
    #[test]
    fn enqueue_and_ack_never_renew_busy_episode_deadline() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(&mut lane, now, NativeKind::Key, None, 1);
        let stop = lane.deadline().unwrap();
        let item = lane.begin(now, &owner()).unwrap().unwrap();
        add(
            &mut lane,
            now + Duration::from_secs(3),
            NativeKind::Key,
            None,
            2,
        );
        accepted(&mut lane, now + Duration::from_secs(4), &item.ticket, 7);
        assert_eq!(lane.deadline(), Some(stop));
        assert!(matches!(
            lane.begin(stop, &owner()),
            Err(LaneError::Expired)
        ));
        assert!(!lane.idle());
        assert!(matches!(
            lane.enqueue(stop, owner(), vec![(NativeKind::Key, None, 1, 3)]),
            Err(LaneError::Expired)
        ));
    }
    #[test]
    fn missing_ack_expires_and_cannot_replay() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(
            &mut lane,
            now,
            NativeKind::Down(Button::Primary),
            Some((1.0, 1.0)),
            1,
        );
        let item = lane.begin(now, &owner()).unwrap().unwrap();
        lane.bind(now, &owner(), &item.ticket, 9).unwrap();
        assert_eq!(
            lane.check(now + NATIVE_EPISODE_BUDGET),
            Err(LaneError::Expired)
        );
        assert!(matches!(
            lane.acknowledge(now + NATIVE_EPISODE_BUDGET, &owner(), 9, true),
            Err(LaneError::Expired)
        ));
    }
    #[test]
    fn zero_empty_or_oversized_owner_is_refused_before_admission() {
        let now = Instant::now();
        for invalid in [
            NativeOwner {
                generation: 0,
                ..owner()
            },
            NativeOwner {
                view: String::new(),
                ..owner()
            },
            NativeOwner {
                view: "x".repeat(129),
                ..owner()
            },
        ] {
            let mut lane = Lane::new();
            assert!(matches!(
                lane.enqueue(now, invalid, vec![(NativeKind::Key, None, 1, 1)]),
                Err(LaneError::StaleOwner)
            ));
            assert!(!lane.idle());
        }
    }
    #[test]
    fn physical_ime_enable_and_two_event_expansion_do_not_grant_renderer_ownership() {
        let mut physical = PhysicalIngress::new(800, 600, 32);
        physical.focused(true);
        physical.ime_enabled(true);
        assert_eq!(physical.composition(false), None);
        physical.pointer(10.0, 42.0);
        physical
            .button(Button::Primary, ButtonAction::Down)
            .unwrap();
        assert_eq!(physical.composition(false), Some(true));
        assert_eq!(physical.composition(false), Some(false));
        assert_eq!(physical.composition(true), Some(false));
        assert_eq!(physical.composition(true), Some(true));
        physical.barrier();
        assert_eq!(physical.composition(false), None);
        assert!(!physical.keyboard_allowed());
        let mut renderer = InputOwnership::new(800, 600, 32);
        renderer.focused(true);
        renderer.enable_ime();
        assert!(!renderer.begin_ime());
        assert!(renderer.take_withdrawal().is_none());
    }
    #[test]
    fn count_capacity_includes_inflight_and_refuses_without_partial_admission() {
        let now = Instant::now();
        let mut lane = Lane::new();
        for value in 0..MAX_NATIVE_EVENTS {
            add(&mut lane, now, NativeKind::Key, None, value);
        }
        let item = lane.begin(now, &owner()).unwrap().unwrap();
        lane.bind(now, &owner(), &item.ticket, 1).unwrap();
        assert!(matches!(
            lane.enqueue(now, owner(), vec![(NativeKind::Key, None, 1, 99)]),
            Err(LaneError::Capacity)
        ));
        assert!(matches!(
            lane.acknowledge(now, &owner(), 1, true),
            Err(LaneError::Capacity)
        ));
    }
    #[test]
    fn individual_and_total_payload_budgets_are_both_closed() {
        let now = Instant::now();
        let mut lane = Lane::new();
        assert!(matches!(
            lane.enqueue(
                now,
                owner(),
                vec![(NativeKind::Ime, None, MAX_NATIVE_EVENT_BYTES + 1, 0)]
            ),
            Err(LaneError::Payload)
        ));
        let mut lane = Lane::new();
        for value in 0..4 {
            lane.enqueue(
                now,
                owner(),
                vec![(NativeKind::Ime, None, MAX_NATIVE_EVENT_BYTES, value)],
            )
            .unwrap();
        }
        assert!(matches!(
            lane.enqueue(now, owner(), vec![(NativeKind::Key, None, 1, 0)]),
            Err(LaneError::Payload)
        ));
    }
    #[test]
    fn malformed_points_and_missing_button_point_fail_closed() {
        let now = Instant::now();
        for (kind, point) in [
            (NativeKind::Move, Some((f32::NAN, 1.0))),
            (NativeKind::Down(Button::Primary), None),
            (NativeKind::Wheel, Some((-1.0, 0.0))),
        ] {
            let mut lane = Lane::new();
            assert!(matches!(
                lane.enqueue(now, owner(), vec![(kind, point, 1, 1)]),
                Err(LaneError::Payload)
            ));
        }
    }
    #[test]
    fn callbacks_require_exact_id_view_generation_and_epoch() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(&mut lane, now, NativeKind::Key, None, 1);
        let item = lane.begin(now, &owner()).unwrap().unwrap();
        lane.bind(now, &owner(), &item.ticket, 4).unwrap();
        for changed in [
            NativeOwner {
                generation: 2,
                ..owner()
            },
            NativeOwner {
                view: "other-view".into(),
                ..owner()
            },
            NativeOwner {
                epoch: 2,
                ..owner()
            },
        ] {
            assert!(matches!(
                lane.acknowledge(now, &changed, 4, true),
                Ok(NativeAck::Ignored)
            ));
        }
        assert!(matches!(
            lane.acknowledge(now, &owner(), 8, true),
            Ok(NativeAck::Ignored)
        ));
        assert!(lane.begin(now, &owner()).unwrap().is_none());
        assert!(matches!(
            lane.acknowledge(now, &owner(), 4, true),
            Ok(NativeAck::Accepted(_))
        ));
        assert!(matches!(
            lane.acknowledge(now, &owner(), 4, true),
            Ok(NativeAck::Ignored)
        ));
    }
    #[test]
    fn dispatch_failed_never_advances_queued_release() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(
            &mut lane,
            now,
            NativeKind::Down(Button::Primary),
            Some((1.0, 1.0)),
            1,
        );
        add(
            &mut lane,
            now,
            NativeKind::Up(Button::Primary),
            Some((2.0, 2.0)),
            2,
        );
        let item = lane.begin(now, &owner()).unwrap().unwrap();
        lane.bind(now, &owner(), &item.ticket, 4).unwrap();
        assert!(matches!(
            lane.acknowledge(now, &owner(), 4, false),
            Err(LaneError::DispatchFailed)
        ));
        assert!(matches!(
            lane.begin(now, &owner()),
            Err(LaneError::DispatchFailed)
        ));
    }
    #[test]
    fn callback_during_submitting_is_unknown_and_never_reentrant_drain() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(&mut lane, now, NativeKind::Move, Some((1.0, 1.0)), 1);
        let item = lane.begin(now, &owner()).unwrap().unwrap();
        assert!(lane.begin(now, &owner()).unwrap().is_none());
        assert!(matches!(
            lane.acknowledge(now, &owner(), 7, true),
            Err(LaneError::UnknownSubmission)
        ));
        assert_eq!(
            lane.bind(now, &owner(), &item.ticket, 7),
            Err(LaneError::UnknownSubmission)
        );
    }
    #[test]
    fn changed_owner_after_notify_cannot_bind_submission() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(&mut lane, now, NativeKind::Key, None, 1);
        let item = lane.begin(now, &owner()).unwrap().unwrap();
        let changed = NativeOwner {
            epoch: 2,
            ..owner()
        };
        assert_eq!(
            lane.bind(now, &changed, &item.ticket, 7),
            Err(LaneError::UnknownSubmission)
        );
    }
    #[test]
    fn queued_only_press_withdraws_without_claiming_engine_held() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(
            &mut lane,
            now,
            NativeKind::Down(Button::Primary),
            Some((1.0, 1.0)),
            1,
        );
        let mut renderer = InputOwnership::new(800, 600, 32);
        renderer.focused(true);
        renderer.pointer(1.0, 33.0);
        renderer.pointer_left();
        lane.withdraw().unwrap();
        assert!(lane.idle());
        assert!(renderer.take_withdrawal().is_none());
        let changed = NativeOwner {
            epoch: 2,
            ..owner()
        };
        lane.enqueue(
            now,
            changed.clone(),
            vec![(NativeKind::Move, Some((2.0, 2.0)), 1, 2)],
        )
        .unwrap();
        assert_eq!(lane.begin(now, &changed).unwrap().unwrap().payload, 2);
    }
    #[test]
    fn actual_down_or_pending_up_preserves_original_held_withdrawal() {
        for action in [ButtonAction::Down, ButtonAction::Up] {
            let now = Instant::now();
            let mut lane = Lane::new();
            let mut renderer = InputOwnership::new(800, 600, 32);
            renderer.focused(true);
            renderer
                .route_button_at(1, Button::Primary, ButtonAction::Down, (1.0, 1.0))
                .unwrap();
            if action == ButtonAction::Up {
                renderer
                    .route_button_at(1, Button::Primary, ButtonAction::Up, (2.0, 2.0))
                    .unwrap();
            }
            add(&mut lane, now, NativeKind::Key, None, 1);
            let _ = lane.begin(now, &owner()).unwrap();
            renderer.focused(false);
            assert_eq!(lane.withdraw(), Err(LaneError::OwnershipWithdrawn));
            let withdrawal = renderer.take_withdrawal().unwrap();
            assert_eq!(withdrawal.reason, WithdrawalReason::WindowFocusLost);
            assert_eq!(withdrawal.held_buttons, 1);
            assert!(!renderer.reconstruct(2));
        }
    }
    #[test]
    fn unresolved_nonbutton_withdrawal_is_closed_without_fake_held_count() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(&mut lane, now, NativeKind::Move, Some((1.0, 1.0)), 1);
        let item = lane.begin(now, &owner()).unwrap().unwrap();
        lane.bind(now, &owner(), &item.ticket, 7).unwrap();
        let stop = lane.deadline();
        assert_eq!(lane.withdraw(), Err(LaneError::OwnershipWithdrawn));
        assert_eq!(lane.deadline(), stop);
        assert!(matches!(
            lane.acknowledge(now, &owner(), 7, true),
            Err(LaneError::OwnershipWithdrawn)
        ));
    }
    #[test]
    fn unsent_crash_queue_is_not_replayed_into_new_generation() {
        let now = Instant::now();
        let mut lane = Lane::new();
        add(&mut lane, now, NativeKind::Key, None, 1);
        lane.withdraw().unwrap();
        let new = NativeOwner {
            generation: 2,
            epoch: 2,
            ..owner()
        };
        assert!(lane.begin(now, &new).unwrap().is_none());
        lane.enqueue(now, new.clone(), vec![(NativeKind::Key, None, 1, 2)])
            .unwrap();
        assert_eq!(lane.begin(now, &new).unwrap().unwrap().payload, 2);
    }
    #[test]
    fn physical_up_freezes_its_own_point_and_projection_does_not_change_renderer() {
        let mut physical = PhysicalIngress::new(800, 600, 32);
        physical.focused(true);
        physical.pointer(10.0, 42.0);
        assert_eq!(
            physical
                .button(Button::Primary, ButtonAction::Down)
                .unwrap(),
            Some((10.0, 10.0))
        );
        physical.pointer(20.0, 52.0);
        assert_eq!(
            physical.button(Button::Primary, ButtonAction::Up).unwrap(),
            Some((20.0, 20.0))
        );
        let mut renderer = InputOwnership::new(800, 600, 32);
        renderer.focused(true);
        renderer.pointer_left();
        assert!(renderer.take_withdrawal().is_none());
        let epoch = physical.epoch;
        physical.pointer(1.0, 1.0);
        assert!(physical.epoch > epoch);
        assert!(!physical.keyboard_allowed());
        assert_eq!(
            physical.button(Button::Primary, ButtonAction::Up).unwrap(),
            None
        );
    }
}

/// Actual dispatch-side key/composition possibility. Physical ingress and local
/// IME enable/disable cannot clear it. Only a bound actual release/end ACK can.
pub struct AuxiliaryOwnership<I> {
    keys: Vec<String>,
    composition_possible: bool,
    key_release: Option<(I, String)>,
    composition_end: Option<I>,
}
impl<I: Copy + Eq> AuxiliaryOwnership<I> {
    pub fn new() -> Self {
        Self {
            keys: Vec::new(),
            composition_possible: false,
            key_release: None,
            composition_end: None,
        }
    }
    pub fn unsettled(&self) -> bool {
        !self.keys.is_empty() || self.composition_possible
    }
    pub fn reserve_key(&mut self, key: &str, down: bool) -> Result<Option<String>, LaneError> {
        if key.is_empty() || key.len() > 128 {
            return Err(LaneError::Payload);
        }
        if down {
            if !self.keys.iter().any(|held| held == key) {
                if self.keys.len() == MAX_NATIVE_EVENTS {
                    return Err(LaneError::Capacity);
                }
                self.keys.push(key.into());
            }
            Ok(None) // A physical key-repeat retains the same possible hold.
        } else if self.keys.iter().any(|held| held == key) {
            Ok(Some(key.into()))
        } else {
            Err(LaneError::PhysicalSequence)
        }
    }
    pub fn reserve_composition(&mut self, start: bool, end: bool) -> Result<(), LaneError> {
        if start && end {
            return Err(LaneError::Payload);
        }
        if !start && !self.composition_possible {
            return Err(LaneError::PhysicalSequence);
        }
        if start {
            if self.composition_possible {
                return Err(LaneError::PhysicalSequence);
            }
            self.composition_possible = true;
        }
        if end && !self.composition_possible {
            return Err(LaneError::PhysicalSequence);
        }
        Ok(())
    }
    pub fn bind_completion(
        &mut self,
        id: I,
        key: Option<String>,
        composition_end: bool,
    ) -> Result<(), LaneError> {
        if self.key_release.is_some() || self.composition_end.is_some() {
            return Err(LaneError::UnknownSubmission);
        }
        if let Some(key) = key {
            if !self.keys.contains(&key) {
                return Err(LaneError::PhysicalSequence);
            }
            self.key_release = Some((id, key));
        }
        if composition_end {
            if !self.composition_possible {
                return Err(LaneError::PhysicalSequence);
            }
            self.composition_end = Some(id);
        }
        Ok(())
    }
    pub fn accepted(&mut self, id: I) -> Result<bool, LaneError> {
        // Check both before removing either. A callback not accepted by the
        // current ordered lane must never call this method.
        if self
            .key_release
            .as_ref()
            .is_some_and(|(expected, _)| *expected != id)
            || self.composition_end.is_some_and(|expected| expected != id)
        {
            return Err(LaneError::UnknownSubmission);
        }
        if let Some((_, key)) = self.key_release.take() {
            let index = self
                .keys
                .iter()
                .position(|held| held == &key)
                .ok_or(LaneError::PhysicalSequence)?;
            self.keys.remove(index);
        }
        let ended = self.composition_end.take().is_some();
        if ended {
            self.composition_possible = false;
        }
        Ok(ended)
    }
}

#[cfg(test)]
mod auxiliary_tests {
    use super::*;
    #[test]
    fn physical_release_admission_and_local_disable_do_not_settle_actual_holds() {
        let mut owner = AuxiliaryOwnership::<u64>::new();
        assert_eq!(owner.reserve_key("KeyK", true), Ok(None));
        let key = owner.reserve_key("KeyK", false).unwrap();
        assert!(owner.unsettled());
        owner.bind_completion(4, key, false).unwrap();
        assert_eq!(owner.accepted(5), Err(LaneError::UnknownSubmission));
        assert!(owner.unsettled());
        owner.accepted(4).unwrap();
        assert!(!owner.unsettled());
        owner.reserve_composition(true, false).unwrap();
        let mut renderer = InputOwnership::new(800, 600, 32);
        renderer.disable_ime();
        assert!(owner.unsettled());
        owner.reserve_composition(false, true).unwrap();
        owner.bind_completion(6, None, true).unwrap();
        assert_eq!(owner.accepted(7), Err(LaneError::UnknownSubmission));
        assert!(owner.unsettled());
        assert!(owner.accepted(6).unwrap());
        assert!(!owner.unsettled());
    }
    #[test]
    fn barrier_after_acked_down_or_start_requires_fresh_owner_even_when_queue_idle() {
        let now = Instant::now();
        for composition in [false, true] {
            let mut lane = OrderedNativeInput::<u64, ()>::new();
            let current = NativeOwner {
                generation: 1,
                view: "owned".into(),
                epoch: 1,
            };
            let mut auxiliary = AuxiliaryOwnership::<u64>::new();
            if composition {
                auxiliary.reserve_composition(true, false).unwrap();
            } else {
                auxiliary.reserve_key("KeyK", true).unwrap();
            }
            lane.enqueue(now, current.clone(), vec![(NativeKind::Key, None, 8, ())])
                .unwrap();
            let submitted = lane.begin(now, &current).unwrap().unwrap();
            lane.bind(now, &current, &submitted.ticket, 1).unwrap();
            assert!(matches!(
                lane.acknowledge(now, &current, 1, true),
                Ok(NativeAck::Accepted(_))
            ));
            auxiliary.accepted(1).unwrap();
            assert!(lane.idle());
            assert!(auxiliary.unsettled());
            lane.withdraw().unwrap();
            let result: Result<(), LaneError> = lane.close(LaneError::OwnershipWithdrawn);
            assert_eq!(result, Err(LaneError::OwnershipWithdrawn));
            assert!(matches!(
                lane.begin(now, &current),
                Err(LaneError::OwnershipWithdrawn)
            ));
        }
    }
    #[test]
    fn key_repeat_or_wrong_up_never_mints_another_release_authority() {
        let mut owner = AuxiliaryOwnership::<u64>::new();
        owner.reserve_key("KeyK", true).unwrap();
        owner.reserve_key("KeyK", true).unwrap();
        assert_eq!(
            owner.reserve_key("KeyX", false),
            Err(LaneError::PhysicalSequence)
        );
        let key = owner.reserve_key("KeyK", false).unwrap();
        owner.bind_completion(1, key, false).unwrap();
        assert_eq!(
            owner.bind_completion(2, Some("KeyK".into()), false),
            Err(LaneError::UnknownSubmission)
        );
        owner.accepted(1).unwrap();
        assert!(!owner.unsettled());
        assert_eq!(
            owner.reserve_key("KeyK", false),
            Err(LaneError::PhysicalSequence)
        );
    }
    #[test]
    fn bounded_key_ledger_rejects_capacity_and_oversized_identity_without_forgetting_holds() {
        let mut owner = AuxiliaryOwnership::<u64>::new();
        for key in 0..MAX_NATIVE_EVENTS {
            owner.reserve_key(&format!("Physical{key}"), true).unwrap();
        }
        assert_eq!(owner.reserve_key("extra", true), Err(LaneError::Capacity));
        assert_eq!(
            owner.reserve_key(&"x".repeat(129), true),
            Err(LaneError::Payload)
        );
        assert!(owner.unsettled());
    }
    #[test]
    fn unknown_or_duplicate_composition_transition_cannot_clear_possible_effect() {
        let mut owner = AuxiliaryOwnership::<u64>::new();
        assert_eq!(
            owner.reserve_composition(false, false),
            Err(LaneError::PhysicalSequence)
        );
        assert_eq!(
            owner.reserve_composition(true, true),
            Err(LaneError::Payload)
        );
        assert_eq!(
            owner.reserve_composition(false, true),
            Err(LaneError::PhysicalSequence)
        );
        owner.reserve_composition(true, false).unwrap();
        assert_eq!(
            owner.reserve_composition(true, false),
            Err(LaneError::PhysicalSequence)
        );
        owner.bind_completion(1, None, true).unwrap();
        owner.accepted(1).unwrap();
        assert!(!owner.accepted(1).unwrap());
        assert!(!owner.unsettled());
    }
}
