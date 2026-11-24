//! Finite qualification operations inside the already authenticated presenter.
use super::*;
use std::sync::Arc;
pub(super) struct NativeWindow {
    pub(super) object: TaskObjectId,
    pub(super) surface: wl_surface::WlSurface,
    pub(super) toplevel: wayland_protocols::xdg::shell::client::xdg_toplevel::XdgToplevel,
    pub(super) retired: bool,
}
#[derive(Clone)]
pub(super) struct SavedFrame {
    pub(super) frame: Arc<owned_window_capture::CapturedFrame>,
    pub(super) input: u64,
}
pub(super) struct Snapshot {
    original: production::window::CaptureMeta,
    saved: SavedFrame,
}
impl App {
    fn owned_surface(&self, object: Option<u64>) -> owned_window::Surface {
        let Some(object) = object.map(TaskObjectId) else {
            return owned_window::Surface::default();
        };
        let held = self.owned_native.as_ref().filter(|h| h.object == object);
        if held.is_some_and(|h| h.retired) {
            return owned_window::Surface::default();
        }
        let task = self.tasks.get(&object);
        if let Some(held) = held {
            if task.and_then(|t| t.window.as_ref()).is_none_or(|w| {
                w.wl_surface() != &held.surface || w.xdg_toplevel() != &held.toplevel
            }) {
                // Losing a lookup is not positive native-window retirement.
                return owned_window::Surface {
                    mapped: true,
                    focused: false,
                    size: [0, 0],
                };
            }
        }
        task.map_or(owned_window::Surface::default(), |task| {
            let (w, h) = task.logical_size.unwrap_or((0, 0));
            owned_window::Surface {
                mapped: task.window.is_some(),
                focused: task.window.is_some() && task.focused && self.focused == Some(object),
                size: [w, h],
            }
        })
    }
    fn revalidate_original_native(&self, object: TaskObjectId) -> Result<(), PresenterError> {
        let held = self
            .owned_native
            .as_ref()
            .filter(|h| h.object == object && !h.retired)
            .ok_or(PresenterError::Configuration(
                "original native window handle is absent or retired",
            ))?;
        let actual = self
            .tasks
            .get(&object)
            .and_then(|t| t.window.as_ref())
            .ok_or(PresenterError::Configuration(
                "original native window lookup disappeared",
            ))?;
        if actual.wl_surface() != &held.surface || actual.xdg_toplevel() != &held.toplevel {
            return Err(PresenterError::Configuration(
                "original native surface or toplevel was replaced",
            ));
        }
        Ok(())
    }
    fn input_idle(&self) -> Result<(), PresenterError> {
        if self.clipboard.blocked()
            || !self.clipboard_inputs.is_empty()
            || self.pointer_contact.is_some()
            || !self.touch_contacts.is_empty()
        {
            return Err(PresenterError::Configuration(
                "physical or clipboard input is already active",
            ));
        }
        Ok(())
    }
    fn owned_command(
        &mut self,
        command: &production::window::Command,
    ) -> Result<production::window::Observation, PresenterError> {
        use production::window::{Action, Command};
        let token = command.lease();
        match command {
            Command::Arm { lease, package } => {
                let previous = self.owned_surface(self.owned_windows.current_object());
                self.owned_windows.arm(*lease, package, !previous.mapped)?;
                self.owned_native = None;
                self.window_frames.clear();
                self.window_capture_errors.clear();
                self.window_snapshot = None;
            }
            Command::Bind {
                lease,
                object,
                task,
            } => {
                if self.owned_windows.bind(*lease, *object, *task)? {
                    let object = TaskObjectId(*object);
                    let window = self
                        .tasks
                        .get(&object)
                        .and_then(|t| t.window.as_ref())
                        .ok_or(PresenterError::Configuration(
                            "fresh original native window is absent",
                        ))?;
                    if let Some(held) = &self.owned_native {
                        if held.object != object
                            || held.retired
                            || &held.surface != window.wl_surface()
                            || &held.toplevel != window.xdg_toplevel()
                        {
                            return Err(PresenterError::Configuration(
                                "original native surface or toplevel changed",
                            ));
                        }
                    } else {
                        self.owned_native = Some(NativeWindow {
                            object,
                            surface: window.wl_surface().clone(),
                            toplevel: window.xdg_toplevel().clone(),
                            retired: false,
                        });
                    }
                }
            }
            Command::CaptureChunk { lease, capture, .. } => {
                let object = self.owned_windows.object(*lease)?;
                self.owned_windows.admit_action(
                    *lease,
                    &Action::Capture,
                    self.owned_surface(object),
                )?;
                self.revalidate_original_native(TaskObjectId(
                    object.ok_or(PresenterError::Configuration("unbound original capture"))?,
                ))?;
                let snapshot = self
                    .window_snapshot
                    .as_ref()
                    .ok_or(PresenterError::Configuration("original capture is absent"))?;
                if snapshot.original.capture != *capture
                    || Some(snapshot.original.object) != object
                    || self
                        .tasks
                        .get(&TaskObjectId(snapshot.original.object))
                        .and_then(|t| t.layers.as_ref())
                        .is_some_and(|s| s.active())
                {
                    return Err(PresenterError::Configuration(
                        "capture belongs to a different frame or active layer path",
                    ));
                }
            }
            Command::Action { lease, action } => {
                let object = self.owned_windows.object(*lease)?;
                let surface = self.owned_surface(object);
                let target = self.owned_windows.admit_action(*lease, action, surface)?;
                if let Some(object) = target.map(TaskObjectId) {
                    let retired_observation = matches!(action, Action::Observe)
                        && self
                            .owned_native
                            .as_ref()
                            .is_some_and(|h| h.object == object && h.retired);
                    if !retired_observation {
                        self.revalidate_original_native(object)?;
                    }
                    match action {
                        Action::Observe => {}
                        Action::Capture => {
                            self.freeze_owned_capture(object)?;
                        }
                        Action::StopCapture => {
                            self.owned_windows.stop_capture(*lease)?;
                            self.window_frames.clear();
                            self.window_capture_errors.clear();
                            self.window_snapshot = None;
                        }
                        Action::Close => {
                            self.endpoint
                                .as_ref()
                                .ok_or(PresenterError::Configuration("original endpoint absent"))?
                                .send_close(object)?;
                            self.owned_windows.close_sent(*lease)?;
                            self.tasks
                                .get_mut(&object)
                                .ok_or(PresenterError::UnknownTask(object))?
                                .unmap_requested = true;
                        }
                        Action::Tap { x, y } => {
                            self.input_idle()?;
                            for (action, pressure) in [
                                (droidloom_denial_protocol::TouchAction::Down, 65535),
                                (droidloom_denial_protocol::TouchAction::Up, 0),
                            ] {
                                self.send_input(
                                    object,
                                    InputEvent::Touch {
                                        action,
                                        pointer_id: 0,
                                        x_fixed: (*x as i32) << 16,
                                        y_fixed: (*y as i32) << 16,
                                        pressure,
                                    },
                                )?;
                                self.owned_windows
                                    .input_sent(*lease, self.next_input_serial)?;
                            }
                        }
                        Action::Key { keycode } => {
                            self.input_idle()?;
                            for action in [
                                droidloom_denial_protocol::KeyAction::Down,
                                droidloom_denial_protocol::KeyAction::Up,
                            ] {
                                self.send_input(
                                    object,
                                    InputEvent::Key {
                                        action,
                                        keycode: *keycode,
                                        repeat: 0,
                                    },
                                )?;
                                self.owned_windows
                                    .input_sent(*lease, self.next_input_serial)?;
                            }
                        }
                        Action::Back => {
                            self.input_idle()?;
                            self.send_input(
                                object,
                                InputEvent::Navigation {
                                    action: droidloom_denial_protocol::NavigationAction::Back,
                                },
                            )?;
                            self.owned_windows
                                .input_sent(*lease, self.next_input_serial)?;
                        }
                    }
                }
            }
        }
        let object = self.owned_windows.object(token)?;
        Ok(self
            .owned_windows
            .observation(token, self.owned_surface(object))?)
    }
    fn freeze_owned_capture(&mut self, object: TaskObjectId) -> Result<(), PresenterError> {
        self.revalidate_original_native(object)?;
        if self
            .tasks
            .get(&object)
            .and_then(|t| t.layers.as_ref())
            .is_some_and(|s| s.active())
        {
            return Err(PresenterError::Configuration(
                "active layer stream needs its own complete original composition",
            ));
        }
        if let Some(error) = self.window_capture_errors.get(&object.0) {
            return Err(std::io::Error::other(error.clone()).into());
        }
        let saved =
            self.window_frames
                .get(&object.0)
                .cloned()
                .ok_or(PresenterError::Configuration(
                    "no actual original composed frame has been captured",
                ))?;
        let f = &saved.frame;
        let original = production::window::CaptureMeta {
            capture: production::window::fresh_token()?,
            object: f.object,
            frame: f.frame,
            buffer: f.buffer,
            width: f.width,
            height: f.height,
            captured_monotonic_ns: f.captured_monotonic_ns,
            host_last_input_serial: saved.input,
            total_png_bytes: f.png.len() as u64,
        };
        self.window_snapshot = Some(Snapshot { original, saved });
        Ok(())
    }
    fn owned_capture_part(
        &self,
        command: &production::window::Command,
    ) -> Result<Option<production::window::CapturePart>, PresenterError> {
        use production::window::{Action, CapturePart, Command};
        let offset = match command {
            Command::Action {
                action: Action::Capture,
                ..
            } => 0,
            Command::CaptureChunk { offset, .. } => *offset,
            _ => return Ok(None),
        };
        let s = self
            .window_snapshot
            .as_ref()
            .ok_or(PresenterError::Configuration(
                "original capture snapshot missing",
            ))?;
        Ok(Some(CapturePart::from_bytes(
            s.original.clone(),
            &s.saved.frame.png,
            offset,
        )?))
    }
    pub(super) fn pump_owned_window(&mut self) -> Result<(), PresenterError> {
        let Some(registration) = self.production.as_ref().cloned() else {
            return Ok(());
        };
        if let Some((reply, until)) = &self.window_reply {
            if std::time::Instant::now() >= *until {
                return Err(PresenterError::Configuration(
                    "original window reply deadline expired",
                ));
            }
            match registration.window_reply(reply) {
                Ok(()) => self.window_reply = None,
                Err(e)
                    if matches!(
                        e.kind(),
                        std::io::ErrorKind::WouldBlock | std::io::ErrorKind::Interrupted
                    ) =>
                {
                    return Ok(());
                }
                Err(e) => return Err(e.into()),
            }
        }
        let Some(request) = registration.window_request()? else {
            return Ok(());
        };
        let result = self
            .owned_command(&request.command)
            .and_then(|observation| {
                self.owned_capture_part(&request.command)
                    .map(|capture| (observation, capture))
            });
        let (observation, error, capture) = match result {
            Ok((value, capture)) => (Some(value), None, capture),
            Err(e) => (None, Some(e.to_string().chars().take(400).collect()), None),
        };
        self.window_reply = Some((
            production::window::Reply {
                nonce: request.nonce,
                serial: request.serial,
                observation,
                error,
                capture,
            },
            std::time::Instant::now() + Duration::from_secs(5),
        ));
        Ok(())
    }
}
