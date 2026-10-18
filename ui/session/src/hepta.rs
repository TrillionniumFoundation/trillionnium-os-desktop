//! The host Session owns the optional Agentd observation connection.
//! Socket I/O runs on one background worker. Shell receives bounded metadata
//! through its existing private Session IPC, never an Agentd endpoint or RPC.

use hepta_os_observer::{EndpointConfig, Observation, ObserverClient};
use std::ffi::OsString;
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, Sender, TryRecvError};
use std::time::{Duration, Instant};
use trill_ui_core::hepta::{
    bounded_hepta_text, HeptaCapabilityObservation, HeptaConnectionState, HeptaEventObservation,
    HeptaHealthObservation, HeptaProjection, HeptaRuntimeObservation, MAX_HEPTA_CAPABILITIES,
    MAX_HEPTA_EVENTS,
};
use trill_ui_core::unix_ms;

pub const SOCKET_ENV: &str = "TRILL_HEPTA_AGENTD_SOCKET";
pub const AGENT_ENV: &str = "TRILL_HEPTA_AGENT_ID";
pub const GENERATION_ENV: &str = "TRILL_HEPTA_SPAWN_GENERATION";
pub const PEER_UID_ENV: &str = "TRILL_HEPTA_PEER_UID";
const POLL_INTERVAL: Duration = Duration::from_secs(1);
// A facade poll has a five-second total deadline. A lost/panicked worker must
// not keep an older successful observation looking current indefinitely.
const UPDATE_DEADLINE: Duration = Duration::from_secs(7);

struct EndpointSettings {
    socket: PathBuf,
    agent_id: String,
    generation: u64,
    peer_uid: u32,
}

impl EndpointSettings {
    fn read(get: impl Fn(&str) -> Option<OsString>) -> Result<Option<Self>, &'static str> {
        let values = [SOCKET_ENV, AGENT_ENV, GENERATION_ENV, PEER_UID_ENV].map(get);
        if values.iter().all(Option::is_none) {
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
        Ok(Some(Self {
            socket: PathBuf::from(socket),
            agent_id,
            generation,
            peer_uid,
        }))
    }
}

struct Update {
    projection: HeptaProjection,
    reported_at: Instant,
}

pub struct HeptaMonitor {
    latest: HeptaProjection,
    updates: Option<Receiver<Update>>,
    last_update: Instant,
    stop: Option<Sender<()>>,
}

impl Default for HeptaMonitor {
    fn default() -> Self {
        Self {
            latest: HeptaProjection::not_configured(),
            updates: None,
            last_update: Instant::now(),
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
        let (sender, updates) = mpsc::sync_channel(1);
        let (stop, stopping) = mpsc::channel();
        let spawned = std::thread::Builder::new()
            .name("hepta-read-only-observer".into())
            .spawn(move || {
                let mut projection = HeptaProjection::connecting();
                let mut client = match ObserverClient::new(config) {
                    Ok(client) => client,
                    Err(error) => {
                        projection.last_attempt_unix_ms = Some(unix_ms());
                        projection.mark_unavailable(error.code());
                        let _ = sender.try_send(Update {
                            projection,
                            reported_at: Instant::now(),
                        });
                        return;
                    }
                };
                let mut cursor = 0;
                loop {
                    if !matches!(stopping.try_recv(), Err(TryRecvError::Empty)) {
                        break;
                    }
                    match client.poll(cursor, MAX_HEPTA_EVENTS as u16) {
                        Ok(observation) => {
                            cursor = observation.next_cursor;
                            projection = project_observation(observation, &projection, unix_ms());
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
                        }
                    }
                    // Bounded one-slot delivery. A stalled consumer cannot
                    // accumulate an event journal or stall the Agentd worker.
                    let _ = sender.try_send(Update {
                        projection: projection.clone(),
                        reported_at: Instant::now(),
                    });
                    match stopping.recv_timeout(POLL_INTERVAL) {
                        Err(mpsc::RecvTimeoutError::Timeout) => {}
                        _ => break,
                    }
                }
            });
        if spawned.is_err() {
            return Self::unavailable("observer_worker_unavailable");
        }
        Self {
            latest: HeptaProjection::connecting(),
            updates: Some(updates),
            last_update: Instant::now(),
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
                    self.last_update = update.reported_at;
                }
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => {
                    if self.latest.error_code.is_none() {
                        self.latest.mark_unavailable("observer_worker_stopped");
                    }
                    break;
                }
            }
        }
        if self.last_update.elapsed() > UPDATE_DEADLINE
            && matches!(
                self.latest.connection,
                HeptaConnectionState::Observed | HeptaConnectionState::Connecting
            )
        {
            self.latest.mark_unavailable("observer_update_timeout");
        }
    }

    pub fn snapshot(&self) -> HeptaProjection {
        self.latest.clone()
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
    HeptaProjection {
        connection: HeptaConnectionState::Observed,
        last_attempt_unix_ms: Some(sampled_unix_ms),
        error_code: None,
        last_observation: Some(last_observation),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_os_observer::{Capability, EventObservation, HealthObservation};

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
        let view = project_observation(observation(20, 17, 16, false), &view, 20);
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
}
