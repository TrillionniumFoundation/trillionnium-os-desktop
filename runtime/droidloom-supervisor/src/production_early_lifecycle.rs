//! The normal Ubuntu production service owns its actual budget, original APK
//! storage, read-only release and Android namespace until orderly retirement.
use super::{
    EarlyBaseAdmission, EarlyBaseRetirement, EarlyBoardResources, EarlyBoundNamespaces, identity,
    invalid,
};
use crate::production_cgroup::PreparedCgroup;
use crate::production_devices::PreparedDevices;
use crate::production_execution::PreparationAdmission;
use crate::production_mounts::{
    PreparedMounts, MountRetirement,
    persistent_data::{EarlyStorageAdmission, PreparedPersistentData, PersistentDataRetirement},
};
use crate::production_devices::DeviceRetirement;
use crate::production_runtime_assets::EarlyQueryRetirement;
use crate::production_selection::ProductionSelection;
use std::{
    fs::File,
    io,
    os::fd::{AsRawFd, FromRawFd},
    path::Path,
    time::Duration,
};

unsafe extern "C" {
    fn droidloom_board_assemble(
        root: i32,
        dev: i32,
        data: i32,
        metadata: i32,
        payload: i32,
        generation: i32,
        frontend: i32,
        query: i32,
        uid: u32,
        gid: u32,
        observer_gid: u32,
    ) -> i32;
    fn droidloom_board_deliver_root(
        pidfd: i32,
        userns: i32,
        mountns: i32,
        childroot: i32,
        root: i32,
    ) -> i32;
}
#[path = "production_early_frontend.rs"]
mod frontend;
pub(crate) use frontend::{QueryObservation, observe_query};

/// Retained only by the original kernel-first MainPID after all prepared
/// resource owners returned their real terminal values. No external builder,
/// Clone, Deserialize or boolean success constructor exists.
pub(crate) struct EarlyPackageRetirement {
    base: EarlyBaseRetirement,
    _images: MountRetirement,
    _data: PersistentDataRetirement,
    _devices: DeviceRetirement,
    query: EarlyQueryRetirement,
    _frontend: frontend::FrontendRetirement,
    selection: [u8; 32],
}
impl EarlyPackageRetirement {
    pub(crate) fn verify_package_retirement(&self, selection: &ProductionSelection) -> io::Result<()> {
        selection.revalidate().map_err(io::Error::other)?;
        if !selection.is_kernel_first() || selection.package_binding() != self.selection {
            return Err(invalid("early package retirement belongs to another original selection"));
        }
        self.base.verify_original_exit()?;
        self.query.verify_selection(selection.base_cohort(), selection.runtime_manifest())
            .map_err(io::Error::other)
    }
}

struct ServiceSignals {
    events: File,
    previous: libc::sigset_t,
    stopping: std::cell::Cell<bool>,
}
impl ServiceSignals {
    fn acquire() -> io::Result<Self> {
        let mut mask: libc::sigset_t = unsafe { std::mem::zeroed() };
        let mut old: libc::sigset_t = unsafe { std::mem::zeroed() };
        for result in [
            unsafe { libc::sigemptyset(&mut mask) },
            unsafe { libc::sigaddset(&mut mask, libc::SIGTERM) },
            unsafe { libc::sigaddset(&mut mask, libc::SIGINT) },
        ] {
            if result != 0 {
                return Err(io::Error::last_os_error());
            }
        }
        let rc = unsafe { libc::pthread_sigmask(libc::SIG_BLOCK, &mask, &mut old) };
        if rc != 0 {
            return Err(io::Error::from_raw_os_error(rc));
        }
        let fd = unsafe { libc::signalfd(-1, &mask, libc::SFD_CLOEXEC | libc::SFD_NONBLOCK) };
        if fd < 0 {
            let e = io::Error::last_os_error();
            unsafe {
                libc::pthread_sigmask(libc::SIG_SETMASK, &old, std::ptr::null_mut());
            }
            return Err(e);
        }
        Ok(Self {
            events: unsafe { File::from_raw_fd(fd) },
            previous: old,
            stopping: std::cell::Cell::new(false),
        })
    }
    fn stop_requested(&self) -> io::Result<bool> {
        // Standard TERM/INT signals coalesce. Drain the original signalfd even
        // after a nested query observed stop so a later request cannot remain
        // pending through orderly Android retirement. Bound work under a flood.
        for _ in 0..8 {
            let mut event: libc::signalfd_siginfo = unsafe { std::mem::zeroed() };
            let count = unsafe {
                libc::read(
                    self.events.as_raw_fd(),
                    (&mut event as *mut libc::signalfd_siginfo).cast(),
                    std::mem::size_of_val(&event),
                )
            };
            if count < 0 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return if error.kind() == io::ErrorKind::WouldBlock {
                    Ok(self.stopping.get())
                } else {
                    Err(error)
                };
            }
            if count != std::mem::size_of_val(&event) as isize
                || !matches!(event.ssi_signo as i32, libc::SIGTERM | libc::SIGINT)
            {
                return Err(invalid("incomplete or unexpected owner stop signal"));
            }
            // The same owner remembers the kernel event when a nested query
            // consumes it. Its outer loop still performs orderly Android stop.
            self.stopping.set(true);
        }
        Ok(self.stopping.get())
    }
    fn await_child(
        &self,
        pidfd: &File,
        mut progress: impl FnMut() -> io::Result<bool>,
    ) -> io::Result<()> {
        let mut fds = [
            libc::pollfd {
                fd: pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: self.events.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        loop {
            if self.stop_requested()? {
                return Ok(());
            }
            let progressed = progress();
            if self.stop_requested()? {
                return Ok(());
            }
            if progressed? {
                return Ok(());
            }
            if unsafe { libc::poll(fds.as_mut_ptr(), 2, 100) } < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(e);
            }
            if fds
                .iter()
                .any(|f| f.revents & (libc::POLLNVAL | libc::POLLERR) != 0)
            {
                return Err(invalid("lost Android lifetime monitor"));
            }
            if fds[1].revents & libc::POLLIN != 0 {
                if self.stop_requested()? {
                    return Ok(());
                }
            }
            if fds[0].revents & libc::POLLIN != 0 {
                return Err(invalid("original Android init exited before service stop"));
            }
        }
    }

    fn await_native_stop(&self, deadline: std::time::Instant) -> io::Result<()> {
        loop {
            if self.stop_requested()? {
                return Ok(());
            }
            let remaining = deadline.checked_duration_since(std::time::Instant::now())
                .ok_or_else(|| io::Error::from_raw_os_error(libc::ETIMEDOUT))?;
            let mut event = libc::pollfd { fd: self.events.as_raw_fd(), events: libc::POLLIN, revents: 0 };
            if unsafe { libc::poll(&mut event, 1, remaining.as_millis().min(100) as i32) } < 0 {
                let error = io::Error::last_os_error();
                if error.kind() != io::ErrorKind::Interrupted { return Err(error); }
            }
            if event.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
                return Err(invalid("original package owner lost its native stop monitor"));
            }
        }
    }
}
impl Drop for ServiceSignals {
    fn drop(&mut self) {
        let _ = self.stop_requested();
        // This guard is owned only by the one-shot service entry. After stop,
        // that entry returns directly to process exit. Keep TERM/INT blocked
        // across the final return: an event arriving after the last drain must
        // not turn a completed orderly shutdown into signal termination.
        if !self.stopping.get() {
            unsafe {
                libc::pthread_sigmask(libc::SIG_SETMASK, &self.previous, std::ptr::null_mut());
            }
        }
    }
}
fn wait_ended(fd: &File, timeout: Duration) -> io::Result<bool> {
    let until = std::time::Instant::now() + timeout;
    loop {
        let mut p = libc::pollfd {
            fd: fd.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let ms = until
            .saturating_duration_since(std::time::Instant::now())
            .as_millis()
            .min(i32::MAX as u128) as i32;
        let rc = unsafe { libc::poll(&mut p, 1, ms) };
        if rc < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        if p.revents & (libc::POLLNVAL | libc::POLLERR) != 0 {
            return Err(invalid("original Android pidfd could not be observed"));
        }
        return Ok(rc > 0 && p.revents & libc::POLLIN != 0);
    }
}
#[derive(Debug, PartialEq, Eq)]
enum ChildExit {
    Observed,
    Forced,
}

impl ChildExit {
    fn after_retirement(self, retired: io::Result<()>) -> io::Result<()> {
        match (self, retired) {
            (Self::Observed, result) => result,
            (Self::Forced, Ok(())) => Err(invalid(
                "original Android PID 1 required SIGKILL; its resources were retired",
            )),
            (Self::Forced, Err(e)) => Err(io::Error::other(format!(
                "original Android PID 1 required SIGKILL; resource retirement failed: {e}"
            ))),
        }
    }
}

fn stop_child(fd: &File, term_timeout: Duration) -> io::Result<ChildExit> {
    for (signal, timeout) in [
        (libc::SIGTERM, term_timeout),
        (libc::SIGKILL, Duration::from_secs(10)),
    ] {
        if wait_ended(fd, Duration::ZERO)? {
            return Ok(ChildExit::Observed);
        }
        let signaled = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                fd.as_raw_fd(),
                signal,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        } == 0;
        if !signaled {
            let e = io::Error::last_os_error();
            if e.raw_os_error() != Some(libc::ESRCH) {
                return Err(e);
            }
        }
        if wait_ended(fd, timeout)? {
            return Ok(if signaled && signal == libc::SIGKILL {
                ChildExit::Forced
            } else {
                ChildExit::Observed
            });
        }
    }
    Err(invalid("original Android PID 1 did not exit"))
}

/// Run in the actual droidloom-production.service MainPID after initramfs
/// created the original Android process. Success means the service stopped
/// and its released original resources were positively retired.
pub fn complete_early_resources() -> io::Result<()> {
    let signals = ServiceSignals::acquire()?;
    let board = EarlyBoardResources::acquire()?;
    let bound = EarlyBoundNamespaces::acquire(&board)?;
    let private = board
        .selection()
        .retain_for_retirement()
        .map_err(io::Error::other)?;
    let prep = PreparationAdmission::acquire(private).map_err(io::Error::other)?;
    let owner = prep.owner();
    let group =
        PreparedCgroup::prepare(bound.admit_host()?, owner.clone()).map_err(io::Error::other)?;
    let base = match EarlyBaseAdmission::new(&bound, group.admission()) {
        Ok(value) => value,
        Err(cause) => {
            group.retire_early_unstarted().map_err(io::Error::other)?;
            return Err(cause);
        }
    };
    if let Err(cause) = group.place_early_payload(&base, &owner) {
        if group.attempted_original(&board).map_err(io::Error::other)? {
            let stopped = stop_child(board.pidfd(), Duration::from_secs(15))?;
            let retired = group.retire_early_empty(&board).map_err(io::Error::other);
            if let Err(e) = stopped.after_retirement(retired) {
                return Err(io::Error::other(format!("{cause}; retirement: {e}")));
            }
        } else {
            group.retire_early_unstarted().map_err(io::Error::other)?;
        }
        return Err(io::Error::other(cause));
    }
    // Retain the listener outside the work closure so accepted package streams
    // can borrow it through resource teardown. A bind failure enters the same
    // original-PIDFD/cgroup cleanup below; it must not add a new early return.
    let control = crate::control::EarlyApplicationControl::bind(&owner);
    let mut transaction = None;
    let mut images: Option<PreparedMounts> = None;
    let mut data: Option<PreparedPersistentData> = None;
    let mut devices: Option<PreparedDevices> = None;
    let mut original_root: Option<File> = None;
    let mut query_resources = None;
    let mut frontend_retirement = None;
    let mut root_delivery_attempted = false;
    let work = (|| -> io::Result<()> {
        let control = control.as_ref().map_err(|error| io::Error::other(error.to_string()))?;
        let cg_ns = board.root_cgroup_namespace()?;
        group
            .finish_early_placement(&base, &cg_ns)
            .map_err(io::Error::other)?;
        let storage =
            EarlyStorageAdmission::acquire(&base, &group, &owner).map_err(io::Error::other)?;
        let payload = group
            .early_payload(&base, &owner)
            .map_err(io::Error::other)?;
        let outer_root = base.observe_init_metadata()?.root;
        let generation =
            super::super::open_root_trusted_directory(Path::new("/run/droidloom-early"))
                .map_err(io::Error::other)?;
        let system = images.insert(PreparedMounts::prepare_early(&base).map_err(io::Error::other)?);
        let root = original_root.insert(File::from(
            system
                .early_root_for_transfer(&base)
                .map_err(io::Error::other)?
                .try_clone_to_owned()?,
        ));
        let private_dev =
            devices.insert(PreparedDevices::prepare_early(&base).map_err(io::Error::other)?);
        let dev = File::from(
            private_dev
                .early_descriptor_for_transfer(&base)
                .map_err(io::Error::other)?
                .try_clone_to_owned()?,
        );
        let mutable =
            data.insert(PreparedPersistentData::prepare_early(&storage).map_err(io::Error::other)?);
        let [userdata, metadata] = mutable
            .early_descriptors_for_transfer(&storage)
            .map_err(io::Error::other)?;
        let (u, g) = base.identity_lease().broker_ranges();
        let obs = g
            .start
            .checked_add(9999)
            .ok_or_else(|| invalid("observer gid overflow"))?;
        let frontend = frontend::Frontend::prepare(&board, &owner, root)?;
        let query = query_resources.insert(
            crate::production_runtime_assets::EarlyQueryResources::prepare(&base)
                .map_err(io::Error::other)?,
        );
        owner.objects().map_err(io::Error::other)?;
        if unsafe {
            droidloom_board_assemble(
                root.as_raw_fd(),
                dev.as_raw_fd(),
                userdata.as_raw_fd(),
                metadata.as_raw_fd(),
                payload.as_raw_fd(),
                generation.as_raw_fd(),
                frontend.projection()?.as_raw_fd(),
                query.mount(&base).map_err(io::Error::other)?.as_raw_fd(),
                u.start,
                g.start,
                obs,
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        mutable
            .revalidate_early_lifetime(&storage)
            .map_err(io::Error::other)?;
        if identity(&outer_root)? != identity(&base.observe_init_metadata()?.root)? {
            return Err(invalid(
                "original Android process changed root before delivery",
            ));
        }
        board.revalidate()?;
        root_delivery_attempted = true;
        if unsafe {
            droidloom_board_deliver_root(
                board.pidfd().as_raw_fd(),
                board.user_namespace().as_raw_fd(),
                board.mount_namespace().as_raw_fd(),
                outer_root.as_raw_fd(),
                root.as_raw_fd(),
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        mutable
            .revalidate_early_lifetime(&storage)
            .map_err(io::Error::other)?;
        let stop = super::orderly::StopRequest::acquire(&board, obs, &userdata, &metadata)?;
        drop(userdata);
        drop(metadata);
        board.release_prepared_root()?;
        let frontend = std::cell::RefCell::new(frontend);
        let progress = || {
            if signals.stop_requested()? {
                return Err(io::Error::new(
                    io::ErrorKind::Interrupted,
                    "original service stop requested",
                ));
            }
            frontend.borrow_mut().progress()
        };
        let waiting = signals.await_child(board.pidfd(), || {
            progress()?;
            if let Some(mut request) = control
                .poll(
                    board.host_pid() as u32,
                    board.selection().spec().host_uid,
                    || {
                        super::EarlyApplicationAuthority::acquire(
                            &base, &group, &owner, root, query, &progress,
                        )
                    },
                )
                .map_err(io::Error::other)?
            {
                request.revalidate()?;
                board.selection().revalidate().map_err(io::Error::other)?;
                if request.selection().package_binding() != board.selection().package_binding() {
                    return Err(invalid("package transaction differs from the original early owner"));
                }
                request.fence_before_retirement()?;
                transaction = Some(request);
                return Ok(true);
            }
            Ok(false)
        });
        let presentation_retired = frontend.borrow_mut().retire_with_proof();
        frontend_retirement = Some(presentation_retired?);
        waiting?;
        stop.deliver(&board)?;
        if !wait_ended(board.pidfd(), Duration::from_secs(75))? {
            return Err(invalid(
                "Android did not finish its requested orderly shutdown",
            ));
        }
        stop.check_mounts(&board, false)
    })();
    // The original pidfd retains exclusive custody even if an earlier stage
    // failed after moving a mount. Never release by a numeric process lookup.
    let cleanup = stop_child(board.pidfd(), Duration::from_secs(15)).and_then(|exit| {
        let mut complete = None;
        let retired = (|| -> io::Result<()> {
            if let Some(root) = original_root {
                let retired =
                    EarlyBaseRetirement::finish(&board, &group, &root, root_delivery_attempted)?;
                drop(root);
                let query_result = query_resources
                    .map(|v| v.retire_after_early_tree(&retired))
                    .transpose()
                    .map_err(io::Error::other);
                let dev_result = devices
                    .map(|v| v.retire_after_early_tree(&retired))
                    .transpose()
                    .map_err(io::Error::other);
                let data_result = data
                    .map(|v| v.retire_after_early_tree(&retired))
                    .transpose()
                    .map_err(io::Error::other);
                let image_result = images
                    .map(|v| v.retire_after_early_tree(&retired))
                    .transpose()
                    .map_err(io::Error::other);
                let query = query_result?;
                let devices = dev_result?;
                let data = data_result?;
                let images = image_result?;
                if work.is_ok() && root_delivery_attempted {
                    if let (Some(query), Some(devices), Some(data), Some(images), Some(frontend)) =
                        (query, devices, data, images, frontend_retirement)
                    {
                        complete = Some(EarlyPackageRetirement {
                            base: retired, _images: images, _data: data, _devices: devices,
                            query, _frontend: frontend, selection: board.selection().package_binding(),
                        });
                    }
                }
            } else {
                group.retire_early_empty(&board).map_err(io::Error::other)?;
                if let Some(images) = images {
                    images.retire_untransferred().map_err(io::Error::other)?;
                }
            }
            Ok(())
        })();
        exit.after_retirement(retired)?;
        Ok(complete)
    });
    let completed = match (work, cleanup) {
        (Err(operation), Err(cleanup)) => {
            Err(io::Error::other(format!("{operation}; cleanup: {cleanup}")))
        }
        (Err(e), _) | (_, Err(e)) => Err(e),
        (Ok(()), Ok(retired)) => Ok(retired),
    };
    let result = (|| {
        let retired = completed?;
        if let Some(request) = transaction.as_mut() {
            let retired = retired.as_ref().ok_or_else(|| invalid("complete original early resource retirement is absent"))?;
            request.complete_early(retired)?;
            // Keep this exact daemon, listener and opaque evidence alive until
            // the helper stops its native unit. A lost reply or helper cannot
            // be replaced with a new transaction or a serialized receipt.
            signals.await_native_stop(request.deadline())?;
        }
        Ok(())
    })();
    drop(transaction);
    let listener_retired = control.and_then(|control| control.retire()).map_err(io::Error::other);
    result.and(listener_retired)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn package_request_returns_to_orderly_shutdown_before_native_stop() {
        std::thread::spawn(|| {
            let signals = ServiceSignals::acquire().unwrap();
            let mut child = std::process::Command::new("/bin/sleep").arg("20").spawn().unwrap();
            let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
            assert!(raw >= 0);
            let held = unsafe { File::from_raw_fd(raw as i32) };
            signals.await_child(&held, || Ok(true)).unwrap();
            assert!(!signals.stop_requested().unwrap());
            assert!(!wait_ended(&held, Duration::ZERO).unwrap());
            assert!(signals.await_native_stop(std::time::Instant::now()).is_err());
            assert_eq!(unsafe { libc::pthread_kill(libc::pthread_self(), libc::SIGTERM) }, 0);
            signals.await_native_stop(std::time::Instant::now() + Duration::from_secs(1)).unwrap();
            child.kill().unwrap();
            child.wait().unwrap();
        }).join().unwrap();
    }
    #[test]
    fn nested_query_stop_observation_is_retained_for_orderly_outer_loop() {
        std::thread::spawn(|| {
            let signals = ServiceSignals::acquire().unwrap();
            assert!(!signals.stop_requested().unwrap());
            let mut child = std::process::Command::new("/bin/sleep")
                .arg("20")
                .spawn()
                .unwrap();
            let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
            assert!(raw >= 0);
            let held = unsafe { File::from_raw_fd(raw as i32) };
            assert_eq!(
                unsafe { libc::pthread_kill(libc::pthread_self(), libc::SIGTERM) },
                0
            );
            // A nested application wait observes this original thread's event.
            assert!(signals.stop_requested().unwrap());
            assert!(signals.stop_requested().unwrap());
            signals
                .await_child(&held, || {
                    panic!("must not begin another application after stop")
                })
                .unwrap();
            child.kill().unwrap();
            child.wait().unwrap();
        })
        .join()
        .unwrap();
    }
    #[test]
    fn stop_arriving_inside_progress_returns_to_orderly_lifecycle() {
        std::thread::spawn(|| {
            let signals = ServiceSignals::acquire().unwrap();
            let mut child = std::process::Command::new("/bin/sleep")
                .arg("20")
                .spawn()
                .unwrap();
            let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
            assert!(raw >= 0);
            let held = unsafe { File::from_raw_fd(raw as i32) };
            let mut entered = false;
            signals
                .await_child(&held, || {
                    entered = true;
                    assert_eq!(
                        unsafe { libc::pthread_kill(libc::pthread_self(), libc::SIGTERM) },
                        0
                    );
                    assert!(signals.stop_requested().unwrap());
                    Err(io::Error::new(
                        io::ErrorKind::Interrupted,
                        "query cancelled",
                    ))
                })
                .unwrap();
            assert!(entered);
            child.kill().unwrap();
            child.wait().unwrap();
        })
        .join()
        .unwrap();
    }
    #[test]
    fn repeated_owner_stop_events_are_drained_and_final_return_keeps_them_blocked() {
        std::thread::spawn(|| {
            let signals = ServiceSignals::acquire().unwrap();
            assert_eq!(
                unsafe { libc::pthread_kill(libc::pthread_self(), libc::SIGTERM) },
                0
            );
            assert!(signals.stop_requested().unwrap());
            for signal in [libc::SIGTERM, libc::SIGINT] {
                assert_eq!(
                    unsafe { libc::pthread_kill(libc::pthread_self(), signal) },
                    0
                );
            }
            assert!(signals.stop_requested().unwrap());
            let mut pending: libc::sigset_t = unsafe { std::mem::zeroed() };
            assert_eq!(unsafe { libc::sigpending(&mut pending) }, 0);
            for signal in [libc::SIGTERM, libc::SIGINT] {
                assert_eq!(unsafe { libc::sigismember(&pending, signal) }, 0);
                assert_eq!(
                    unsafe { libc::pthread_kill(libc::pthread_self(), signal) },
                    0
                );
            }
            // A second request during retirement is consumed by the same owner.
            drop(signals);
            assert_eq!(unsafe { libc::sigpending(&mut pending) }, 0);
            let mut current: libc::sigset_t = unsafe { std::mem::zeroed() };
            assert_eq!(
                unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, std::ptr::null(), &mut current) },
                0
            );
            for signal in [libc::SIGTERM, libc::SIGINT] {
                assert_eq!(unsafe { libc::sigismember(&pending, signal) }, 0);
                assert_eq!(unsafe { libc::sigismember(&current, signal) }, 1);
            }
        })
        .join()
        .unwrap();
    }
    #[test]
    fn unused_owner_signal_guard_restores_original_thread_mask() {
        std::thread::spawn(|| {
            let mut before: libc::sigset_t = unsafe { std::mem::zeroed() };
            assert_eq!(
                unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, std::ptr::null(), &mut before) },
                0
            );
            drop(ServiceSignals::acquire().unwrap());
            let mut after: libc::sigset_t = unsafe { std::mem::zeroed() };
            assert_eq!(
                unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, std::ptr::null(), &mut after) },
                0
            );
            for signal in [libc::SIGTERM, libc::SIGINT] {
                assert_eq!(unsafe { libc::sigismember(&before, signal) }, unsafe {
                    libc::sigismember(&after, signal)
                });
            }
        })
        .join()
        .unwrap();
    }
    #[test]
    fn original_process_receives_stop_and_pidfd_confirms_exit() {
        let mut child = std::process::Command::new("/bin/sleep")
            .arg("25")
            .spawn()
            .unwrap();
        let pid = child.id();
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        assert!(fd >= 0);
        let fd = unsafe { File::from_raw_fd(fd as i32) };
        assert!(!wait_ended(&fd, Duration::ZERO).unwrap());
        assert_eq!(
            stop_child(&fd, Duration::from_secs(3)).unwrap(),
            ChildExit::Observed
        );
        assert!(wait_ended(&fd, Duration::ZERO).unwrap());
        child.wait().unwrap();
    }
    #[test]
    fn unresponsive_original_is_reaped_and_cannot_report_a_clean_stop() {
        use std::io::BufRead;
        use std::os::unix::process::ExitStatusExt;
        use std::process::{Command, Stdio};

        let mut child = Command::new("/bin/sh")
            .args(["-c", "trap '' TERM; echo ready; exec /bin/sleep 25"])
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        let mut ready = String::new();
        std::io::BufReader::new(child.stdout.take().unwrap())
            .read_line(&mut ready)
            .unwrap();
        assert_eq!(ready.trim(), "ready");
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
        assert!(raw >= 0);
        let fd = unsafe { File::from_raw_fd(raw as i32) };
        let exit = stop_child(&fd, Duration::from_millis(20)).unwrap();
        assert_eq!(exit, ChildExit::Forced);
        assert_eq!(child.wait().unwrap().signal(), Some(libc::SIGKILL));
        assert!(
            exit.after_retirement(Ok(()))
                .unwrap_err()
                .to_string()
                .contains("SIGKILL")
        );
        let failure = ChildExit::Forced
            .after_retirement(Err(invalid("test detach failed")))
            .unwrap_err();
        assert!(
            failure.to_string().contains("SIGKILL")
                && failure.to_string().contains("test detach failed")
        );
    }
}
