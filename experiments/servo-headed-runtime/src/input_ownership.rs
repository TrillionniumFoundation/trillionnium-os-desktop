//! Native input ownership for the fixed physical-pixel qualification viewport.
//! No event may reuse a content coordinate after pointer/focus withdrawal.

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
        }
    }

    pub fn focused(&mut self, focused: bool) -> bool {
        self.window_focused = focused;
        if !focused {
            self.point = None;
            self.content_keyboard = false;
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
        self.point
    }

    pub fn pointer_left(&mut self) {
        self.point = None;
    }
    pub fn point(&self) -> Option<(f32, f32)> {
        if self.live && self.window_focused {
            self.point
        } else {
            None
        }
    }

    /// A physical press selects keyboard ownership; trusted chrome withdraws it.
    pub fn pressed(&mut self) -> bool {
        self.content_keyboard = self.point().is_some();
        self.withdraw_ime_if_needed()
    }

    pub fn keyboard_allowed(&self) -> bool {
        self.live && self.window_focused && self.content_keyboard
    }

    pub fn begin_ime(&mut self) -> bool {
        if !self.keyboard_allowed() || self.ime_open {
            return false;
        }
        self.ime_open = true;
        true
    }

    pub fn ime_allowed(&self) -> bool {
        self.keyboard_allowed() && self.ime_open
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
        self.live = false;
        self.point = None;
        self.content_keyboard = false;
        self.end_ime()
    }

    /// Replacement never inherits old input coordinates, focus or composition.
    pub fn reconstruct(&mut self, generation: u32) -> bool {
        if self.live || generation <= self.generation {
            return false;
        }
        self.generation = generation;
        self.live = true;
        self.point = None;
        self.content_keyboard = false;
        self.ime_open = false;
        true
    }

    pub fn current_callback(&self, generation: u32) -> bool {
        self.live && self.generation == generation
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn owner() -> InputOwnership {
        let mut o = InputOwnership::new(1024, 768, 64);
        o.focused(true);
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
}
