//! Original Composer event history for one explicitly armed qualification window.
//! No package lookup, serialized task number, socket closure or frame counter
//! can manufacture a fresh task or successful Android task retirement.
use crate::production::window::{self, Action, Observation, Phase};
use std::collections::BTreeMap;
use std::io;

#[derive(Clone)]
struct Birth {
    serial: u64,
    package: String,
    task: Option<u64>,
    frames: u64,
}
#[derive(Clone)]
struct Lease {
    token: [u8; 16],
    package: String,
    after: u64,
    bound: Option<(u64, u64, u64)>,
    close_requested: bool,
    destroyed: bool,
    frames: u64,
    input: u64,
    capture_enabled: bool,
}
#[derive(Default)]
pub(crate) struct Tracker {
    serial: u64,
    births: BTreeMap<u64, Birth>,
    lease: Option<Lease>,
}
#[derive(Clone, Copy, Default)]
pub(crate) struct Surface {
    pub(crate) mapped: bool,
    pub(crate) focused: bool,
    pub(crate) size: [u32; 2],
}
impl Tracker {
    pub(crate) fn created(&mut self, object: u64, package: &str) -> io::Result<()> {
        window::require(
            object > 0 && !self.births.contains_key(&object) && self.births.len() < 1024,
            "duplicate or unbounded original window creation",
        )?;
        self.serial = self
            .serial
            .checked_add(1)
            .ok_or_else(|| window::invalid("creation serial exhausted"))?;
        self.births.insert(
            object,
            Birth {
                serial: self.serial,
                package: package.into(),
                task: None,
                frames: 0,
            },
        );
        Ok(())
    }
    pub(crate) fn bound(&mut self, object: u64, task: u64) -> io::Result<()> {
        let b = self
            .births
            .get_mut(&object)
            .ok_or_else(|| window::invalid("BindTask lacks original CreateTask"))?;
        window::require(
            task > 0 && b.task.is_none_or(|old| old == task),
            "original task binding changed",
        )?;
        b.task = Some(task);
        Ok(())
    }
    pub(crate) fn presented(&mut self, object: u64) -> io::Result<()> {
        let b = self
            .births
            .get_mut(&object)
            .ok_or_else(|| window::invalid("frame lacks original CreateTask"))?;
        b.frames = b
            .frames
            .checked_add(1)
            .ok_or_else(|| window::invalid("frame serial exhausted"))?;
        if let Some(l) = self.lease.as_mut().filter(|l| {
            l.bound
                .is_some_and(|(o, _, s)| o == object && s == b.serial)
        }) {
            l.frames = b.frames;
        }
        Ok(())
    }
    pub(crate) fn destroyed(&mut self, object: u64) -> io::Result<()> {
        let b = self
            .births
            .remove(&object)
            .ok_or_else(|| window::invalid("DestroyTask lacks original CreateTask"))?;
        if let Some(l) = self.lease.as_mut().filter(|l| {
            l.bound
                .is_some_and(|(o, _, s)| o == object && s == b.serial)
        }) {
            l.destroyed = true;
            l.frames = b.frames;
            l.capture_enabled = false;
        }
        Ok(())
    }
    pub(crate) fn arm(
        &mut self,
        token: [u8; 16],
        package: &str,
        previous_surface_retired: bool,
    ) -> io::Result<()> {
        window::valid_token(token)?;
        window::valid_package(package)?;
        window::require(
            self.lease
                .as_ref()
                .is_none_or(|l| l.destroyed && previous_surface_retired),
            "previous original window has no complete DestroyTask/surface retirement",
        )?;
        window::require(
            self.lease.as_ref().is_none_or(|l| l.token != token),
            "window lease token reused",
        )?;
        self.lease = Some(Lease {
            token,
            package: package.into(),
            after: self.serial,
            bound: None,
            close_requested: false,
            destroyed: false,
            frames: 0,
            input: 0,
            capture_enabled: true,
        });
        Ok(())
    }
    pub(crate) fn bind(&mut self, token: [u8; 16], object: u64, task: u64) -> io::Result<bool> {
        let l = self
            .lease
            .as_mut()
            .ok_or_else(|| window::invalid("no original armed window"))?;
        window::require(
            l.token == token && !l.destroyed && !l.close_requested,
            "stale original window lease",
        )?;
        if let Some((o, t, s)) = l.bound {
            window::require(
                o == object && t == task && self.births.get(&o).is_some_and(|b| b.serial == s),
                "bound original window was replaced",
            )?;
            return Ok(true);
        }
        let Some(b) = self.births.get(&object) else {
            return Ok(false);
        };
        window::require(
            b.serial > l.after && b.package == l.package,
            "launch resolved to a pre-existing or different package window",
        )?;
        if b.task.is_none() {
            return Ok(false);
        }
        window::require(
            b.task == Some(task),
            "actual Composer BindTask differs from launcher",
        )?;
        l.bound = Some((object, task, b.serial));
        l.frames = b.frames;
        Ok(true)
    }
    pub(crate) fn object(&self, token: [u8; 16]) -> io::Result<Option<u64>> {
        let l = self
            .lease
            .as_ref()
            .ok_or_else(|| window::invalid("no original window lease"))?;
        window::require(l.token == token, "window lease is from another launch")?;
        if let Some((o, t, s)) = l.bound {
            if !l.destroyed {
                window::require(
                    self.births.get(&o).is_some_and(|b| {
                        b.serial == s && b.task == Some(t) && b.package == l.package
                    }),
                    "held original window identity changed",
                )?;
            }
            Ok(Some(o))
        } else {
            Ok(None)
        }
    }
    pub(crate) fn capture_candidate(&self, object: u64) -> bool {
        self.lease.as_ref().is_some_and(|l| {
            l.capture_enabled
                && !l.destroyed
                && !l.close_requested
                && self.births.get(&object).is_some_and(|b| {
                    b.serial > l.after
                        && b.package == l.package
                        && l.bound.is_none_or(|(o, _, s)| o == object && s == b.serial)
                })
        })
    }
    pub(crate) fn current_object(&self) -> Option<u64> {
        self.lease.as_ref().and_then(|l| l.bound.map(|b| b.0))
    }
    pub(crate) fn observation(&self, token: [u8; 16], surface: Surface) -> io::Result<Observation> {
        self.object(token)?;
        let l = self.lease.as_ref().unwrap();
        let phase = if l.destroyed {
            Phase::Destroyed
        } else if l.close_requested {
            Phase::CloseRequested
        } else if l.bound.is_some() {
            Phase::Bound
        } else {
            Phase::Armed
        };
        // A DestroyTask is not sufficient to claim native surface retirement.
        // Report it only after the actual native surface has been removed.
        let destroy_observed = l.destroyed && !surface.mapped;
        let phase = if l.destroyed && !destroy_observed {
            Phase::CloseRequested
        } else {
            phase
        };
        let o = Observation {
            lease: l.token,
            package: l.package.clone(),
            phase,
            object: l.bound.map(|v| v.0),
            android_task: l.bound.map(|v| v.1),
            creation_serial: l.bound.map(|v| v.2),
            mapped: surface.mapped,
            focused: surface.focused,
            size: surface.size,
            submitted_frames: l.frames,
            capture_enabled: l.capture_enabled,
            last_input_serial: l.input,
            close_requested: l.close_requested || (l.destroyed && !destroy_observed),
            destroy_observed,
        };
        o.validate()?;
        Ok(o)
    }
    pub(crate) fn admit_action(
        &self,
        token: [u8; 16],
        action: &Action,
        surface: Surface,
    ) -> io::Result<Option<u64>> {
        action.validate()?;
        let object = self.object(token)?;
        let l = self.lease.as_ref().unwrap();
        if matches!(action, Action::Observe) {
            return Ok(object);
        }
        if matches!(action, Action::Capture | Action::StopCapture) {
            window::require(
                object.is_some() && !l.destroyed && !l.close_requested && surface.mapped,
                "capture requires the original live mapped window",
            )?;
            if matches!(action, Action::Capture) {
                window::require(
                    l.capture_enabled,
                    "capture was explicitly stopped for this lease",
                )?;
            }
            return Ok(object);
        }
        window::require(object.is_some(), "window is not bound to a fresh launch")?;
        if matches!(action, Action::Close) {
            // Idempotent observation of an earlier close; never send it twice.
            return if l.close_requested || l.destroyed {
                Ok(None)
            } else {
                Ok(object)
            };
        }
        window::require(
            !l.destroyed && !l.close_requested && surface.mapped && surface.focused,
            "input requires the original live focused mapped window",
        )?;
        if let Action::Tap { x, y } = action {
            window::require(
                *x < surface.size[0] && *y < surface.size[1],
                "tap exceeds the actual window extent",
            )?;
        }
        Ok(object)
    }
    pub(crate) fn close_sent(&mut self, token: [u8; 16]) -> io::Result<()> {
        self.object(token)?;
        let l = self.lease.as_mut().unwrap();
        window::require(
            !l.destroyed && !l.close_requested,
            "duplicate original close send",
        )?;
        l.close_requested = true;
        l.capture_enabled = false;
        Ok(())
    }
    pub(crate) fn stop_capture(&mut self, token: [u8; 16]) -> io::Result<()> {
        self.object(token)?;
        self.lease.as_mut().unwrap().capture_enabled = false;
        Ok(())
    }
    pub(crate) fn input_sent(&mut self, token: [u8; 16], serial: u64) -> io::Result<()> {
        self.object(token)?;
        let l = self.lease.as_mut().unwrap();
        window::require(
            serial > l.input && !l.destroyed && !l.close_requested,
            "input serial did not advance",
        )?;
        l.input = serial;
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    const A: [u8; 16] = [1; 16];
    const B: [u8; 16] = [2; 16];
    fn surface() -> Surface {
        Surface {
            mapped: true,
            focused: true,
            size: [100, 200],
        }
    }
    fn live() -> Tracker {
        let mut t = Tracker::default();
        t.arm(A, "org.example.app", true).unwrap();
        t.created(4, "org.example.app").unwrap();
        t.bound(4, 9).unwrap();
        assert!(t.bind(A, 4, 9).unwrap());
        t
    }
    #[test]
    fn owned_window_rejects_preexisting_task_even_if_package_and_numbers_match() {
        let mut t = Tracker::default();
        t.created(4, "org.example.app").unwrap();
        t.bound(4, 9).unwrap();
        t.arm(A, "org.example.app", true).unwrap();
        assert!(t.bind(A, 4, 9).is_err());
    }
    #[test]
    fn owned_window_requires_both_real_create_and_bind_events() {
        let mut t = Tracker::default();
        t.arm(A, "org.example.app", true).unwrap();
        assert!(!t.bind(A, 4, 9).unwrap());
        t.created(4, "org.example.app").unwrap();
        assert!(!t.bind(A, 4, 9).unwrap());
        assert!(t.bound(99, 9).is_err());
        t.bound(4, 8).unwrap();
        assert!(t.bind(A, 4, 9).is_err());
    }
    #[test]
    fn owned_window_close_request_is_never_task_retirement() {
        let mut t = live();
        assert_eq!(
            t.admit_action(A, &Action::Close, surface()).unwrap(),
            Some(4)
        );
        t.close_sent(A).unwrap();
        let o = t.observation(A, surface()).unwrap();
        assert_eq!(o.phase, Phase::CloseRequested);
        assert!(!o.destroy_observed);
        assert_eq!(t.admit_action(A, &Action::Close, surface()).unwrap(), None);
        assert!(t.arm(B, "org.example.app", true).is_err());
        t.destroyed(4).unwrap();
        assert!(!t.observation(A, surface()).unwrap().destroy_observed);
        assert!(t.arm(B, "org.example.app", false).is_err());
        assert!(
            t.observation(A, Surface::default())
                .unwrap()
                .destroy_observed
        );
        t.arm(B, "org.example.app", true).unwrap();
    }
    #[test]
    fn owned_window_rejects_foreign_tokens_and_reused_numeric_identity() {
        let mut t = live();
        assert!(t.object(B).is_err());
        t.destroyed(4).unwrap();
        t.created(4, "org.example.other").unwrap();
        t.bound(4, 9).unwrap();
        assert_eq!(
            t.admit_action(A, &Action::Close, Surface::default())
                .unwrap(),
            None
        );
        assert!(
            t.admit_action(A, &Action::Tap { x: 1, y: 1 }, surface())
                .is_err()
        );
    }
    #[test]
    fn owned_window_input_requires_focus_and_actual_bounds() {
        let t = live();
        let mut s = surface();
        s.focused = false;
        assert!(t.admit_action(A, &Action::Back, s).is_err());
        assert!(
            t.admit_action(A, &Action::Tap { x: 100, y: 0 }, surface())
                .is_err()
        );
        assert_eq!(
            t.admit_action(A, &Action::Tap { x: 99, y: 199 }, surface())
                .unwrap(),
            Some(4)
        );
    }
    #[test]
    fn owned_window_can_stop_capture_without_losing_normal_lifecycle_authority() {
        let mut t = live();
        assert!(t.capture_candidate(4));
        t.stop_capture(A).unwrap();
        assert!(!t.capture_candidate(4));
        assert!(!t.observation(A, surface()).unwrap().capture_enabled);
        assert!(t.admit_action(A, &Action::Capture, surface()).is_err());
        assert_eq!(
            t.admit_action(A, &Action::Back, surface()).unwrap(),
            Some(4)
        );
        assert_eq!(
            t.admit_action(A, &Action::Close, surface()).unwrap(),
            Some(4)
        );
        assert!(!t.observation(A, surface()).unwrap().destroy_observed);
    }
    #[test]
    fn owned_window_bind_is_idempotent_only_for_original_birth() {
        let mut t = live();
        assert!(t.bind(A, 4, 9).unwrap());
        assert!(t.bind(A, 4, 10).is_err());
        assert!(t.created(4, "org.example.app").is_err());
        t.input_sent(A, 12).unwrap();
        assert!(t.input_sent(A, 12).is_err());
        t.presented(4).unwrap();
        assert_eq!(t.observation(A, surface()).unwrap().submitted_frames, 1);
    }
}
