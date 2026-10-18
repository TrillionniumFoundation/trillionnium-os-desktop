//! The host Session owns the optional Agentd observation connection.
//! Socket I/O runs on one background worker. Shell receives bounded metadata
//! through its existing private Session IPC, never an Agentd endpoint or RPC.

use hepta_os_observer::{EndpointConfig, Observation, ObserverClient, RunObservation};
use std::ffi::OsString;
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, Sender, TryRecvError};
use std::time::{Duration, Instant};
use trill_ui_core::hepta::{
    bounded_hepta_text, HeptaCapabilityObservation, HeptaConnectionState, HeptaEventObservation,
    HeptaHealthObservation, HeptaProjection, HeptaRunConnectionState, HeptaRunObservation,
    HeptaRunProjection, HeptaRuntimeObservation, MAX_HEPTA_CAPABILITIES, MAX_HEPTA_EVENTS,
};
use trill_ui_core::observation::{self, FreshnessFailure};
use trill_ui_core::unix_ms;

pub const SOCKET_ENV: &str = "TRILL_HEPTA_AGENTD_SOCKET";
pub const AGENT_ENV: &str = "TRILL_HEPTA_AGENT_ID";
pub const GENERATION_ENV: &str = "TRILL_HEPTA_SPAWN_GENERATION";
pub const PEER_UID_ENV: &str = "TRILL_HEPTA_PEER_UID";
pub const RUN_ID_ENV: &str = "TRILL_HEPTA_RUN_ID";
const POLL_INTERVAL: Duration = Duration::from_secs(1);
// A facade poll has a five-second total deadline. A lost/panicked worker must
// not keep an older successful observation looking current indefinitely.
const UPDATE_DEADLINE: Duration = Duration::from_secs(7);

struct EndpointSettings {
    socket: PathBuf,
    agent_id: String,
    generation: u64,
    peer_uid: u32,
    run_id: Option<String>,
}

impl EndpointSettings {
    fn read(get: impl Fn(&str) -> Option<OsString>) -> Result<Option<Self>, &'static str> {
        let values = [SOCKET_ENV, AGENT_ENV, GENERATION_ENV, PEER_UID_ENV].map(&get);
        let run_id = get(RUN_ID_ENV);
        if values.iter().all(Option::is_none) && run_id.is_none() {
            return Ok(None);
        }
        let [Some(socket), Some(agent), Some(generation), Some(peer_uid)] = values else {
            return Err("observer_config_incomplete");
        };
        let agent_id = agent.into_string().map_err(|_| "observer_config_invalid")?;
        let generation = generation
            .into_string()
            .map_err(|_| "observer_config_invalid")?
            .parse()
            .map_err(|_| "observer_config_invalid")?;
        let peer_uid = peer_uid
            .into_string()
            .map_err(|_| "observer_config_invalid")?
            .parse()
            .map_err(|_| "observer_config_invalid")?;
        let run_id = run_id
            .map(|value| {
                let value = value.into_string().map_err(|_| "observer_run_id_invalid")?;
                // Same identity grammar as the fixed facade's run_status.
                // Validate before any worker or socket I/O; never trim, map
                // a HostTask number, synthesize or truncate this identity.
                if value.is_empty()
                    || value.len() > 128
                    || !value.bytes().all(|byte| {
                        byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-')
                    })
                {
                    return Err("observer_run_id_invalid");
                }
                Ok(value)
            })
            .transpose()?;
        Ok(Some(Self {
            socket: PathBuf::from(socket),
            agent_id,
            generation,
            peer_uid,
            run_id,
        }))
    }
}

struct Update {
    projection: HeptaProjection,
    runtime_reported_at: Instant,
    run_sampled_at: Instant,
}

pub struct HeptaMonitor {
    latest: HeptaProjection,
    updates: Option<Receiver<Update>>,
    last_update: Instant,
    last_run_sample: Instant,
    stop: Option<Sender<()>>,
}

impl Default for HeptaMonitor {
    fn default() -> Self {
        Self {
            latest: HeptaProjection::not_configured(),
            updates: None,
            last_update: Instant::now(),
            last_run_sample: Instant::now(),
            stop: None,
        }
    }
}

impl HeptaMonitor {
    pub fn from_env() -> Self {
        let settings = match EndpointSettings::read(|name| std::env::var_os(name)) {
            Ok(None) => return Self::default(),
            Ok(Some(settings)) => settings,
            Err(code) => return Self::unavailable(code),
        };
        // This validates explicit owner configuration. It makes no connection.
        let config = match EndpointConfig::new(
            settings.socket,
            settings.agent_id,
            settings.generation,
            settings.peer_uid,
        ) {
            Ok(config) => config,
            Err(error) => return Self::unavailable(error.code()),
        };
        let initial = HeptaProjection {
            run: settings
                .run_id
                .map(|run_id| Box::new(HeptaRunProjection::connecting(run_id))),
            ..HeptaProjection::connecting()
        };
        let worker_initial = initial.clone();
        let started_at = Instant::now();
        // A bounded pair lets the worker publish health before a potentially
        // slow run read, without waiting for the Session event loop.
        let (sender, updates) = mpsc::sync_channel(2);
        let (stop, stopping) = mpsc::channel();
        let spawned = std::thread::Builder::new()
            .name("hepta-read-only-observer".into())
            .spawn(move || {
                let mut projection = worker_initial;
                let mut run_sampled_at = started_at;
                let mut client = match ObserverClient::new(config) {
                    Ok(client) => client,
                    Err(error) => {
                        projection.last_attempt_unix_ms = Some(unix_ms());
                        projection.mark_unavailable(error.code());
                        let _ = sender.try_send(Update {
                            projection,
                            runtime_reported_at: Instant::now(),
                            run_sampled_at,
                        });
                        return;
                    }
                };
                let mut cursor = 0;
                loop {
                    if !matches!(stopping.try_recv(), Err(TryRecvError::Empty)) {
                        break;
                    }
                    let healthy = match client.poll(cursor, MAX_HEPTA_EVENTS as u16) {
                        Ok(observation) => {
                            cursor = observation.next_cursor;
                            projection = project_observation(observation, &projection, unix_ms());
                            true
                        }
                        Err(error) => {
                            // A read cursor can be resynchronized. This is NOT
                            // a retry or replay of an objective/effect request.
                            if error.code() == "event_cursor_ahead" {
                                cursor = 0;
                                if let Some(last) = &mut projection.last_observation {
                                    last.history_gap = true;
                                    last.events_omitted_from_view = last
                                        .events_omitted_from_view
                                        .saturating_add(last.events.len() as u64);
                                    last.events.clear();
                                }
                            }
                            projection.last_attempt_unix_ms = Some(unix_ms());
                            projection.mark_unavailable(error.code());
                            false
                        }
                    };
                    let runtime_reported_at = Instant::now();
                    let _ = sender.try_send(Update {
                        projection: projection.clone(),
                        runtime_reported_at,
                        run_sampled_at,
                    });
                    if !matches!(stopping.try_recv(), Err(TryRecvError::Empty)) {
                        break;
                    }
                    if healthy {
                        if let Some(run) = &mut projection.run {
                            // This independently bounded health -> run_status
                            // -> health read never submits or reconciles an
                            // objective. A null result is only missing current
                            // in-memory metadata, not durable non-admission.
                            // Bound the sample age from the beginning of the
                            // whole read: the closing health check can itself
                            // be slow after the run payload was already read.
                            let read_started_at = Instant::now();
                            let sampled_unix_ms = unix_ms();
                            let result = client.run_status(&run.run_id);
                            let completed_unix_ms = unix_ms();
                            match result {
                                Ok(observation) => project_run_status(
                                    run,
                                    observation,
                                    sampled_unix_ms,
                                    completed_unix_ms,
                                ),
                                Err(error) => {
                                    run.last_attempt_unix_ms = Some(completed_unix_ms);
                                    run.mark_unavailable(error.code());
                                }
                            }
                            if run.connection == HeptaRunConnectionState::Observed {
                                run_sampled_at = read_started_at;
                            }
                            let _ = sender.try_send(Update {
                                projection: projection.clone(),
                                // Neither a slow nor successful run read may
                                // renew the separately sampled runtime health.
                                runtime_reported_at,
                                run_sampled_at,
                            });
                        }
                    }
                    match stopping.recv_timeout(POLL_INTERVAL) {
                        Err(mpsc::RecvTimeoutError::Timeout) => {}
                        _ => break,
                    }
                }
            });
        if spawned.is_err() {
            let mut monitor = Self {
                latest: initial,
                updates: None,
                last_update: started_at,
                last_run_sample: started_at,
                stop: None,
            };
            monitor
                .latest
                .mark_unavailable("observer_worker_unavailable");
            return monitor;
        }
        Self {
            latest: initial,
            updates: Some(updates),
            last_update: started_at,
            last_run_sample: started_at,
            stop: Some(stop),
        }
    }

    fn unavailable(code: &str) -> Self {
        let mut monitor = Self::default();
        monitor.latest.mark_unavailable(code);
        monitor
    }

    /// Never waits for Agentd, even while it is stalled or disconnected.
    pub fn refresh(&mut self) {
        let Some(updates) = &self.updates else {
            return;
        };
        loop {
            match updates.try_recv() {
                Ok(update) => {
                    self.latest = update.projection;
                    self.last_update = update.runtime_reported_at;
                    self.last_run_sample = update.run_sampled_at;
                }
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => {
                    if self.latest.error_code.is_none() {
                        self.latest.mark_unavailable("observer_worker_stopped");
                    } else if let Some(run) = &mut self.latest.run {
                        if matches!(
                            run.connection,
                            HeptaRunConnectionState::Observed | HeptaRunConnectionState::Connecting
                        ) {
                            run.mark_unavailable("observer_worker_stopped");
                        }
                    }
                    break;
                }
            }
        }
        self.expire_at(Instant::now(), unix_ms());
    }

    fn expire_at(&mut self, now: Instant, now_unix_ms: u64) {
        if now
            .checked_duration_since(self.last_update)
            .is_none_or(|age| age > UPDATE_DEADLINE)
            && matches!(
                self.latest.connection,
                HeptaConnectionState::Observed | HeptaConnectionState::Connecting
            )
        {
            self.latest
                .mark_runtime_unavailable("observer_update_timeout");
        }
        if let Some(run) = &mut self.latest.run {
            let age = now.checked_duration_since(self.last_run_sample);
            if run.connection == HeptaRunConnectionState::Connecting
                && age.is_none_or(|age| age > UPDATE_DEADLINE)
            {
                run.mark_unavailable("run_observer_update_timeout");
            }
            if run.connection == HeptaRunConnectionState::Observed {
                if let Some(failure) = observation::freshness_failure(
                    run.last_observation
                        .as_ref()
                        .map(|sample| sample.sampled_unix_ms),
                    age,
                    now_unix_ms,
                ) {
                    run.mark_unavailable(match failure {
                        FreshnessFailure::SampleMissing => "run_observation_missing",
                        FreshnessFailure::ReceiptTimeInvalid => "run_observer_time_invalid",
                        FreshnessFailure::ReceiptExpired => "run_observer_update_timeout",
                        FreshnessFailure::SampleTimeInvalid => "run_observation_time_invalid",
                        FreshnessFailure::SampleExpired => "run_observation_expired",
                    });
                }
            }
        }
    }

    pub fn snapshot(&self) -> HeptaProjection {
        self.snapshot_at(Instant::now())
    }

    fn snapshot_at(&self, now: Instant) -> HeptaProjection {
        let mut projection = self.latest.clone();
        if let Some(run) = &mut projection.run {
            // Keep immutable observation history separate from its advancing
            // age. This includes time spent in the bounded worker queue and
            // remains meaningful if the wall clock rolls back before Shell
            // receives its first snapshot of this sample.
            run.sample_age_at_snapshot_ms = run.last_observation.as_ref().and_then(|_| {
                now.checked_duration_since(self.last_run_sample).map(|age| {
                    // Rounding down could admit a sample past the deadline.
                    u64::try_from(age.as_nanos().div_ceil(1_000_000)).unwrap_or(u64::MAX)
                })
            });
            if run.last_observation.is_some() && run.connection == HeptaRunConnectionState::Observed
            {
                match run.sample_age_at_snapshot_ms {
                    None => run.mark_unavailable("run_observer_time_invalid"),
                    Some(age_ms) if u128::from(age_ms) > UPDATE_DEADLINE.as_millis() => {
                        run.mark_unavailable("run_observer_update_timeout");
                    }
                    _ => {}
                }
            }
        }
        projection
    }
}

impl Drop for HeptaMonitor {
    fn drop(&mut self) {
        if let Some(stop) = &self.stop {
            let _ = stop.send(());
        }
        // No join on the Session event loop. In-flight socket work has the
        // facade's fixed total deadline, then observes the stop channel.
    }
}

fn project_observation(
    observation: Observation,
    previous: &HeptaProjection,
    sampled_unix_ms: u64,
) -> HeptaProjection {
    let old = previous.last_observation.as_ref();
    let identity_changed = old.is_some_and(|old| {
        // The facade validates the full configured agent identity. Never
        // compare its truncated display string as an authority identifier.
        // Current generation advances during promotion/draining of the same
        // spawned process; those lifecycle transitions do not replace it.
        old.spawn_generation != observation.spawn_generation
            || old.health.process_id != observation.health.process_id
    });
    let mut events = old
        .filter(|_| !identity_changed)
        .map(|old| old.events.clone())
        .unwrap_or_default();
    let mut omitted = old.map_or(0, |old| old.events_omitted_from_view);
    if identity_changed {
        omitted = omitted.saturating_add(old.map_or(0, |old| old.events.len()) as u64);
    }
    for event in observation.events.into_iter().take(MAX_HEPTA_EVENTS) {
        if events.iter().any(|old| old.cursor == event.cursor) {
            continue;
        }
        events.push(HeptaEventObservation {
            cursor: event.cursor,
            kind: bounded_hepta_text(&event.kind),
            generation: event.generation,
            lifecycle: event.lifecycle.as_deref().map(bounded_hepta_text),
        });
        if events.len() > MAX_HEPTA_EVENTS {
            events.remove(0);
            omitted = omitted.saturating_add(1);
        }
    }
    let capabilities_truncated = observation.capabilities.len() > MAX_HEPTA_CAPABILITIES;
    let last_observation = HeptaRuntimeObservation {
        sampled_unix_ms,
        agent_id: bounded_hepta_text(&observation.agent_id),
        spawn_generation: observation.spawn_generation,
        current_generation: observation.current_generation,
        health: HeptaHealthObservation {
            ready: observation.health.ready,
            promotion_ready: observation.health.promotion_ready,
            fenced: observation.health.fenced,
            lifecycle: bounded_hepta_text(&observation.health.lifecycle),
            process_id: observation.health.process_id,
        },
        capabilities: observation
            .capabilities
            .into_iter()
            .take(MAX_HEPTA_CAPABILITIES)
            .map(|capability| HeptaCapabilityObservation {
                id: bounded_hepta_text(&capability.id),
                major: capability.major,
                minor: capability.minor,
            })
            .collect(),
        capabilities_truncated,
        events,
        events_omitted_from_view: omitted,
        next_cursor: observation.next_cursor,
        latest_cursor: observation.latest_cursor,
        history_gap: observation.history_gap
            || identity_changed
            || old.is_some_and(|old| old.history_gap),
        source_changed: identity_changed || old.is_some_and(|old| old.source_changed),
    };
    let mut run = previous.run.clone();
    if identity_changed {
        if let Some(run) = &mut run {
            run.mark_unavailable("observer_source_changed");
        }
    }
    HeptaProjection {
        connection: HeptaConnectionState::Observed,
        last_attempt_unix_ms: Some(sampled_unix_ms),
        error_code: None,
        last_observation: Some(last_observation),
        run,
    }
}

fn project_run_status(
    run: &mut HeptaRunProjection,
    observation: Option<RunObservation>,
    sampled_unix_ms: u64,
    completed_unix_ms: u64,
) {
    run.last_attempt_unix_ms = Some(completed_unix_ms);
    let Some(observation) = observation else {
        run.mark_projection_missing();
        return;
    };
    let Some(observation_sequence) = run
        .last_observation
        .as_ref()
        .map_or(0, |sample| sample.observation_sequence)
        .checked_add(1)
    else {
        run.mark_unavailable("run_observation_sequence_exhausted");
        return;
    };
    run.last_observation = Some(HeptaRunObservation {
        sampled_unix_ms,
        observation_sequence,
        run_id: observation.run_id,
        revision: observation.revision,
        phase: observation.phase,
        authority_epoch: observation.authority_epoch,
        generation: observation.generation,
        terminal_observed: observation.terminal_observed,
        idempotent: observation.idempotent,
    });
    run.connection = HeptaRunConnectionState::Observed;
    run.error_code = None;
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_os_observer::{Capability, EventObservation, HealthObservation};

    fn owner_run(run_id: &str) -> RunObservation {
        RunObservation {
            run_id: run_id.into(),
            revision: 4,
            phase: "indeterminate".into(),
            authority_epoch: 9,
            generation: 6,
            terminal_observed: false,
            idempotent: false,
        }
    }

    fn observed_run(sampled_unix_ms: u64) -> HeptaRunProjection {
        let mut run = HeptaRunProjection::connecting("known:run-1".into());
        project_run_status(
            &mut run,
            Some(owner_run("known:run-1")),
            sampled_unix_ms,
            sampled_unix_ms,
        );
        run
    }

    fn observation(pid: u32, start: u64, count: u64, gap: bool) -> Observation {
        Observation {
            agent_id: "00000000-0000-4000-8000-000000000001".into(),
            spawn_generation: 1,
            current_generation: 2,
            health: HealthObservation {
                ready: true,
                promotion_ready: true,
                fenced: false,
                lifecycle: "running".into(),
                process_id: pid,
            },
            capabilities: (0..32)
                .map(|_| Capability {
                    id: "\\".repeat(1000),
                    major: u16::MAX,
                    minor: u16::MAX,
                })
                .collect(),
            events: (start..start + count)
                .map(|cursor| EventObservation {
                    cursor,
                    kind: "\\".repeat(1000),
                    generation: Some(1),
                    lifecycle: Some("\\".repeat(1000)),
                })
                .collect(),
            next_cursor: start + count - 1,
            latest_cursor: start + count - 1,
            history_gap: gap,
        }
    }

    #[test]
    fn lifecycle_advancement_retains_the_same_source_event_window() {
        let mut starting = observation(20, 1, 1, false);
        starting.current_generation = starting.spawn_generation;
        starting.health.lifecycle = "starting".into();
        starting.health.ready = false;
        let view = project_observation(starting, &HeptaProjection::default(), 10);

        let running = observation(20, 2, 1, false);
        let view = project_observation(running, &view, 20);
        let current = view.last_observation.as_ref().unwrap();
        assert_eq!(current.current_generation, 2);
        assert!(!current.source_changed);
        assert!(!current.history_gap);
        assert_eq!(current.events.len(), 2);

        let mut draining = observation(20, 3, 1, false);
        draining.current_generation = draining.spawn_generation + 2;
        draining.health.lifecycle = "draining".into();
        draining.health.ready = false;
        let view = project_observation(draining, &view, 30);
        let current = view.last_observation.as_ref().unwrap();
        assert_eq!(current.current_generation, 3);
        assert!(!current.source_changed);
        assert!(!current.history_gap);
        assert_eq!(current.events.len(), 3);
        assert_eq!(current.events_omitted_from_view, 0);

        let mut replacement = observation(20, 1, 1, false);
        replacement.spawn_generation = 4;
        replacement.current_generation = 5;
        let view = project_observation(replacement, &view, 40);
        let current = view.last_observation.as_ref().unwrap();
        assert!(current.source_changed);
        assert!(current.history_gap);
        assert_eq!(current.events.len(), 1);
        assert_eq!(current.events_omitted_from_view, 3);
    }

    #[test]
    fn bounded_metadata_preserves_stale_evidence_and_sticky_gaps() {
        let mut view = project_observation(
            observation(20, 1, 16, true),
            &HeptaProjection::default(),
            10,
        );
        let first = view.last_observation.clone().unwrap();
        assert_eq!(first.events.len(), MAX_HEPTA_EVENTS);
        assert_eq!(first.capabilities.len(), MAX_HEPTA_CAPABILITIES);
        assert!(first.capabilities_truncated);
        assert!(first.events.iter().all(|event| event.kind.len() <= 96));
        view.mark_unavailable("timeout");
        assert_eq!(view.connection, HeptaConnectionState::Stale);
        assert_eq!(view.last_observation.as_ref(), Some(&first));
        let mut view = project_observation(observation(20, 17, 16, false), &view, 20);
        let exact_id = "r".repeat(128);
        let mut run = HeptaRunProjection::connecting(exact_id.clone());
        project_run_status(&mut run, Some(owner_run(&exact_id)), u64::MAX, u64::MAX);
        view.run = Some(Box::new(run));
        let current = view.last_observation.as_ref().unwrap();
        assert!(current.history_gap);
        assert_eq!(current.events[0].cursor, 17);
        assert_eq!(current.events_omitted_from_view, 16);
        // Exercise the existing full snapshot frame gate, including the
        // projected strings' worst-case JSON escaping, not just Vec lengths.
        let response = trill_ui_core::Response::Snapshot {
            tasks: (0..trill_ui_core::MAX_TRACKED_TASKS)
                .map(|id| {
                    let mut task = trill_ui_core::TaskRecord::new(
                        id as u64,
                        trill_ui_core::Workspace::Build,
                        trill_ui_core::AppKind::Calculator,
                    );
                    task.detail =
                        "Host child running; effect and surface presentation unverified".repeat(2);
                    task
                })
                .collect(),
            resources: super::super::host_resources(
                trill_ui_core::HostWaylandObservation::default(),
            ),
            session_instance: "f".repeat(32),
            hepta: view.clone(),
        };
        let mut bytes = Vec::new();
        trill_ui_core::write_frame(&mut bytes, &response).unwrap();
        assert!(bytes.len() <= trill_ui_core::MAX_FRAME);
        let restarted = project_observation(observation(30, 1, 1, false), &view, 30);
        let restarted = restarted.last_observation.unwrap();
        assert!(restarted.source_changed);
        assert!(restarted.history_gap);
        assert_eq!(restarted.events.len(), 1);
        assert_eq!(restarted.events[0].cursor, 1);
    }

    #[test]
    fn partial_endpoint_configuration_cannot_select_an_implicit_peer() {
        assert!(EndpointSettings::read(|_| None).unwrap().is_none());
        assert!(matches!(
            EndpointSettings::read(|name| (name == SOCKET_ENV).then(|| "/tmp/a.sock".into())),
            Err("observer_config_incomplete")
        ));
        assert!(matches!(
            EndpointSettings::read(|name| Some(match name {
                SOCKET_ENV => "/tmp/a.sock".into(),
                AGENT_ENV => "a".into(),
                GENERATION_ENV => "not-a-generation".into(),
                _ => "0".into(),
            })),
            Err("observer_config_invalid")
        ));
    }

    #[test]
    fn a_lost_worker_cannot_keep_connecting_or_observed_status() {
        let (sender, updates) = mpsc::sync_channel(1);
        drop(sender);
        let mut monitor = HeptaMonitor {
            latest: HeptaProjection::connecting(),
            updates: Some(updates),
            last_update: Instant::now(),
            last_run_sample: Instant::now(),
            stop: None,
        };
        monitor.refresh();
        assert_eq!(
            monitor.snapshot().connection,
            HeptaConnectionState::Unavailable
        );
        assert_eq!(
            monitor.snapshot().error_code.as_deref(),
            Some("observer_worker_stopped")
        );
    }

    #[test]
    fn a_known_run_requires_all_endpoint_values_and_an_exact_valid_identity() {
        use std::os::unix::ffi::OsStringExt;
        assert!(matches!(
            EndpointSettings::read(|name| (name == RUN_ID_ENV).then(|| "known:run".into())),
            Err("observer_config_incomplete")
        ));
        let settings = |run_id: Option<OsString>| {
            EndpointSettings::read(|name| match name {
                SOCKET_ENV => Some("/tmp/known-owner.sock".into()),
                AGENT_ENV => Some("11111111-1111-4111-8111-111111111111".into()),
                GENERATION_ENV => Some("7".into()),
                PEER_UID_ENV => Some("0".into()),
                RUN_ID_ENV => run_id.clone(),
                _ => None,
            })
        };
        assert!(settings(None).unwrap().unwrap().run_id.is_none());
        let exact = format!("R._:-{}", "a".repeat(123));
        assert_eq!(
            settings(Some(exact.clone().into()))
                .unwrap()
                .unwrap()
                .run_id,
            Some(exact)
        );
        for invalid in [
            OsString::new(),
            "r".repeat(129).into(),
            " run".into(),
            "run\n".into(),
            "run/path".into(),
            "任务".into(),
            OsString::from_vec(vec![0xff]),
        ] {
            assert!(matches!(
                settings(Some(invalid)),
                Err("observer_run_id_invalid")
            ));
        }
    }

    #[test]
    fn null_and_old_owner_failure_keep_the_last_typed_run_without_inventing_an_outcome() {
        let mut run = HeptaRunProjection::connecting("known:run-1".into());
        project_run_status(&mut run, None, 1, 1);
        assert_eq!(run.connection, HeptaRunConnectionState::ProjectionMissing);
        assert!(run.last_observation.is_none());
        project_run_status(&mut run, Some(owner_run("known:run-1")), 2, 2);
        let observed = run.last_observation.clone().unwrap();
        assert_eq!(observed.generation, 6);
        assert_eq!(observed.phase, "indeterminate");
        assert!(!observed.terminal_observed);
        project_run_status(&mut run, None, 3, 3);
        assert_eq!(run.connection, HeptaRunConnectionState::ProjectionMissing);
        assert_eq!(run.last_observation.as_ref(), Some(&observed));
        assert!(run.observation_gap);
        run.mark_unavailable("generation_fenced");
        assert_eq!(run.connection, HeptaRunConnectionState::Stale);
        assert_eq!(run.last_observation.as_ref(), Some(&observed));
        project_run_status(&mut run, Some(owner_run("known:run-1")), 4, 4);
        assert_eq!(run.last_observation.unwrap().observation_sequence, 2);
        assert!(run.observation_gap);
    }

    #[test]
    fn run_and_health_deliveries_never_renew_each_others_monotonic_sample_age() {
        for expired_run in [false, true] {
            let now = Instant::now();
            let sampled_unix_ms = unix_ms();
            let old = now - Duration::from_millis(7_001);
            let mut projection = project_observation(
                observation(20, 1, 1, false),
                &HeptaProjection::default(),
                sampled_unix_ms,
            );
            projection.run = Some(Box::new(observed_run(sampled_unix_ms)));
            let (sender, updates) = mpsc::sync_channel(2);
            sender
                .send(Update {
                    projection,
                    runtime_reported_at: if expired_run { now } else { old },
                    run_sampled_at: if expired_run { old } else { now },
                })
                .unwrap();
            let mut monitor = HeptaMonitor {
                latest: HeptaProjection::default(),
                updates: Some(updates),
                last_update: now,
                last_run_sample: now,
                stop: None,
            };
            monitor.refresh();
            let view = monitor.snapshot();
            assert_eq!(
                view.last_observation.unwrap().sampled_unix_ms,
                sampled_unix_ms
            );
            assert_eq!(
                view.connection,
                if expired_run {
                    HeptaConnectionState::Observed
                } else {
                    HeptaConnectionState::Stale
                }
            );
            let run = view.run.unwrap();
            assert_eq!(
                run.connection,
                if expired_run {
                    HeptaRunConnectionState::Stale
                } else {
                    HeptaRunConnectionState::Observed
                }
            );
            assert_eq!(
                run.last_observation.unwrap().sampled_unix_ms,
                sampled_unix_ms
            );
        }
    }

    #[test]
    fn run_clock_rollback_and_exact_seven_second_boundary_fail_closed_without_erasing_history() {
        for (mono_ms, wall_ms, expected) in [
            (7_000, 17_000, HeptaRunConnectionState::Observed),
            (7_001, 10_000, HeptaRunConnectionState::Stale),
            (0, 17_001, HeptaRunConnectionState::Stale),
            (0, 9_999, HeptaRunConnectionState::Stale),
        ] {
            let now = Instant::now();
            let mut monitor = HeptaMonitor {
                latest: HeptaProjection {
                    run: Some(Box::new(observed_run(10_000))),
                    ..HeptaProjection::default()
                },
                last_run_sample: now - Duration::from_millis(mono_ms),
                updates: None,
                last_update: now,
                stop: None,
            };
            let history = monitor
                .latest
                .run
                .as_ref()
                .unwrap()
                .last_observation
                .clone();
            monitor.expire_at(now, wall_ms);
            // Both checks use the same controlled instant: a real snapshot
            // taken later would correctly cross the exact 7,000 ms boundary.
            let run = monitor.snapshot_at(now).run.unwrap();
            assert_eq!(run.connection, expected);
            assert_eq!(run.last_observation, history);
        }
    }

    #[test]
    fn run_snapshot_reports_rounded_monotonic_age_without_rewriting_sample_history() {
        let sampled_at = Instant::now();
        let mut monitor = HeptaMonitor {
            latest: HeptaProjection {
                run: Some(Box::new(observed_run(10_000))),
                ..HeptaProjection::default()
            },
            updates: None,
            last_update: sampled_at,
            last_run_sample: sampled_at,
            stop: None,
        };
        let original = monitor.latest.run.as_ref().unwrap().clone();
        for (elapsed_ns, age_ms) in [
            (0, 0),
            (1, 1),
            (999_999, 1),
            (1_000_000, 1),
            (7_000_000_000, 7_000),
            (7_000_000_001, 7_001),
        ] {
            let view = monitor
                .snapshot_at(sampled_at + Duration::from_nanos(elapsed_ns))
                .run
                .unwrap();
            assert_eq!(view.sample_age_at_snapshot_ms, Some(age_ms));
            assert_eq!(
                view.connection,
                if age_ms > 7_000 {
                    HeptaRunConnectionState::Stale
                } else {
                    HeptaRunConnectionState::Observed
                }
            );
            assert_eq!(view.last_observation, original.last_observation);
            assert_eq!(view.last_attempt_unix_ms, original.last_attempt_unix_ms);
        }
        assert_eq!(monitor.latest.run.as_ref(), Some(&original));
        let invalid = monitor
            .snapshot_at(sampled_at - Duration::from_nanos(1))
            .run
            .unwrap();
        assert_eq!(invalid.connection, HeptaRunConnectionState::Stale);
        assert_eq!(
            invalid.error_code.as_deref(),
            Some("run_observer_time_invalid")
        );
        assert!(invalid.sample_age_at_snapshot_ms.is_none());
        assert_eq!(invalid.last_observation, original.last_observation);

        // A null response with no history has no sample age to invent.
        let mut missing = HeptaRunProjection::connecting("known:missing".into());
        missing.mark_projection_missing();
        monitor.latest.run = Some(Box::new(missing));
        let view = monitor.snapshot_at(sampled_at + Duration::from_secs(8));
        let run = view.run.as_ref().unwrap();
        assert_eq!(run.connection, HeptaRunConnectionState::ProjectionMissing);
        assert!(run.sample_age_at_snapshot_ms.is_none());
        assert!(!run.observation_gap);
        assert!(serde_json::to_value(run)
            .unwrap()
            .get("sample_age_at_snapshot_ms")
            .is_none());
    }
}
