// Copyright 2026 Droidloom contributors
// SPDX-License-Identifier: Apache-2.0
//! Bounded observations of actual registration writes and queued PSI events.
//! These records carry no authority and do not relax any pressure/effect gate.
use super::*;

pub const MAX_AUDIT_EVENTS: usize = 64;
pub(crate) const PRESSURE_AUDIT_SIZE: usize = 2560;
const REG_START: usize = 256;
const REG_WIDTH: usize = 128;
const EVENT_START: usize = REG_START + 2 * REG_WIDTH;
const EVENT_WIDTH: usize = 32;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RegistrationRecord {
    pub level: u32,
    pub trigger_length: u32,
    pub window_us: u64,
    pub stall_us: u64,
    pub pressure_device: u64,
    pub pressure_inode: u64,
    pub write_started_ns: u64,
    pub write_completed_ns: u64,
    pub bytes_written: u64,
    pub trigger: [u8; 64],
}
impl Default for RegistrationRecord {
    fn default() -> Self {
        Self { level: 0, trigger_length: 0, window_us: 0, stall_us: 0, pressure_device: 0,
            pressure_inode: 0, write_started_ns: 0, write_completed_ns: 0,
            bytes_written: 0, trigger: [0; 64] }
    }
}
impl RegistrationRecord {
    pub(crate) fn completed(config: PressureConfig, file: FileId, trigger: &[u8],
        written: usize, start: u64, completed: u64) -> Result<Self> {
        if trigger.is_empty() || trigger.len() > 64 || written != trigger.len() {
            return Err(Error::Reject("pressure registration audit length"));
        }
        let mut result = Self { level: level_number(config.level), trigger_length: trigger.len() as u32,
            window_us: config.window_us, stall_us: config.stall_us,
            pressure_device: file.device, pressure_inode: file.inode,
            write_started_ns: start, write_completed_ns: completed, bytes_written: written as u64,
            ..Self::default() };
        result.trigger[..trigger.len()].copy_from_slice(trigger);
        result.validate(file.device, completed)?;
        Ok(result)
    }
    pub fn config(&self) -> Result<PressureConfig> {
        Ok(PressureConfig { level: match self.level {
            1 => PressureLevel::Medium, 2 => PressureLevel::Critical,
            _ => return Err(Error::Reject("pressure audit level")),
        }, window_us: self.window_us, stall_us: self.stall_us })
    }
    pub fn trigger_text(&self) -> Result<&str> {
        let len = self.trigger_length as usize;
        if len == 0 || len > self.trigger.len() { return Err(Error::Reject("pressure audit raw trigger bound")); }
        std::str::from_utf8(&self.trigger[..len]).map_err(|_| Error::Reject("pressure audit trigger is not UTF-8"))
    }
    fn validate(&self, scope_device: u64, end: u64) -> Result<()> {
        let trigger = self.trigger_text()?;
        let canonical = self.config()?.exact_trigger()?;
        if trigger != canonical || self.trigger[self.trigger_length as usize..].iter().any(|byte| *byte != 0) ||
            self.bytes_written != self.trigger_length as u64 || self.pressure_device != scope_device ||
            self.pressure_inode == 0 || self.write_started_ns == 0 ||
            self.write_completed_ns < self.write_started_ns || self.write_completed_ns > end {
            return Err(Error::Reject("actual pressure registration audit differs from exact write"));
        }
        Ok(())
    }
}
pub(crate) fn level_number(level: PressureLevel) -> u32 {
    match level { PressureLevel::Medium => 1, PressureLevel::Critical => 2 }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct QueuedEventRecord {
    pub level: u32,
    pub sequence: u64,
    pub observed_ns: u64,
    pub send_completed_ns: u64,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct EventAuditTrail {
    pub records: [QueuedEventRecord; MAX_AUDIT_EVENTS],
    pub count: u32,
    pub overflow: bool,
}
impl Default for EventAuditTrail {
    fn default() -> Self { Self { records: [QueuedEventRecord::default(); MAX_AUDIT_EVENTS], count: 0, overflow: false } }
}
impl EventAuditTrail {
    pub(crate) fn append(&mut self, record: QueuedEventRecord) {
        if (self.count as usize) < self.records.len() {
            self.records[self.count as usize] = record;
            self.count += 1;
        } else {
            self.overflow = true;
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct RegistrationAudit {
    pub lease_generation: [u8; 32],
    pub records: [RegistrationRecord; 2],
    pub count: u32,
}

/// A joined-worker observation record, separate from the retirement status.
/// Incomplete/faulted records may describe a failure but cannot qualify a run.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PressureAudit {
    pub nonce: [u8; 32],
    pub authority_generation: [u8; 32],
    pub cgroup: FileId,
    pub budget: [u8; 32],
    pub granted: bool,
    pub faulted: bool,
    pub incomplete: bool,
    pub registrations: RegistrationAudit,
    pub observations: u64,
    pub packets_queued: u64,
    pub stop_reason: u32,
    pub events: EventAuditTrail,
    pub retired_monotonic_ns: u64,
}
impl PressureAudit {
    pub(crate) fn from_retirement(status: &BootstrapStatus, receipt: &RetirementReceipt, now: u64) -> Self {
        let registrations = receipt.registration_audit().unwrap_or_default();
        let diagnostics = receipt.diagnostics();
        let (observations, packets_queued, stop_reason, events) = diagnostics
            .map(|d| (d.observations, d.packets_queued, d.stop_reason, d.events))
            .unwrap_or((0, 0, 0, EventAuditTrail::default()));
        Self { nonce: status.nonce, authority_generation: status.generation, cgroup: status.cgroup,
            budget: status.budget, granted: status.granted, faulted: status.faulted,
            incomplete: status.faulted || events.overflow || observations != packets_queued || packets_queued != events.count as u64,
            registrations, observations, packets_queued, stop_reason, events, retired_monotonic_ns: now }
    }
    pub fn validate(&self) -> Result<()> {
        if self.nonce == [0; 32] || self.authority_generation == [0; 32] || self.cgroup.device == 0 ||
            self.cgroup.inode == 0 || !super::enrollment::valid_budget(&self.budget) ||
            self.retired_monotonic_ns == 0 || self.registrations.count > 2 ||
            self.events.count as usize > MAX_AUDIT_EVENTS || self.observations < self.packets_queued ||
            self.packets_queued < self.events.count as u64 || self.stop_reason > 6 ||
            ((self.events.overflow || self.faulted || self.observations != self.packets_queued ||
                self.packets_queued != self.events.count as u64) && !self.incomplete) {
            return Err(Error::Reject("pressure retirement audit bounds/state"));
        }
        let count = self.registrations.count as usize;
        if (self.granted && count == 0) || (count == 0 && self.registrations.lease_generation != [0; 32]) ||
            (count != 0 && self.registrations.lease_generation == [0; 32]) ||
            (count == 0 && (self.observations != 0 || self.packets_queued != 0 || self.events.count != 0)) ||
            (count == 2 && (self.registrations.records[0].level == self.registrations.records[1].level ||
                self.registrations.records[0].pressure_device != self.registrations.records[1].pressure_device ||
                self.registrations.records[0].pressure_inode != self.registrations.records[1].pressure_inode)) {
            return Err(Error::Reject("pressure audit registration generation/count"));
        }
        for registration in &self.registrations.records[..count] {
            registration.validate(self.cgroup.device, self.retired_monotonic_ns)?;
        }
        if self.registrations.records[count..].iter().any(|r| *r != RegistrationRecord::default()) ||
            self.events.records[self.events.count as usize..].iter().any(|r| *r != QueuedEventRecord::default()) {
            return Err(Error::Reject("pressure audit unused record is not zero"));
        }
        let mut sequence = [0u64; 2];
        let mut observed = [0u64; 2];
        for event in &self.events.records[..self.events.count as usize] {
            let registration = self.registrations.records[..count].iter().find(|r| r.level == event.level)
                .ok_or(Error::Reject("pressure event audit has no registered level"))?;
            let index = (event.level - 1) as usize;
            if event.sequence != sequence[index] + 1 || event.observed_ns < registration.write_completed_ns ||
                event.observed_ns < observed[index] || event.send_completed_ns < event.observed_ns ||
                event.send_completed_ns > self.retired_monotonic_ns ||
                event.send_completed_ns - event.observed_ns >= registration.window_us * 1000 {
                return Err(Error::Reject("pressure event audit sequence/time differs"));
            }
            sequence[index] = event.sequence; observed[index] = event.observed_ns;
        }
        Ok(())
    }
    pub fn require_minimal_root_defaults(&self) -> Result<()> {
        self.validate()?;
        if self.incomplete || self.faulted || !self.granted || self.registrations.count != 2 || self.stop_reason != 1 {
            return Err(Error::Reject("pressure qualification requires complete joined active lease"));
        }
        for (level, stall) in [(1, 70_000), (2, 700_000)] {
            let row = self.registrations.records.iter().find(|r| r.level == level)
                .ok_or(Error::Reject("missing original native PSI level"))?;
            if row.window_us != 1_000_000 || row.stall_us != stall {
                return Err(Error::Reject("original native pressure defaults changed"));
            }
        }
        Ok(())
    }
    pub(crate) fn encode(&self) -> Result<[u8; PRESSURE_AUDIT_SIZE]> {
        self.validate()?;
        let mut wire = [0; PRESSURE_AUDIT_SIZE]; wire[..8].copy_from_slice(b"P4AUD01!");
        put(&mut wire, 8, 1, 4);
        let flags = u64::from(self.granted) | u64::from(self.faulted) << 1 |
            u64::from(self.incomplete) << 2 | u64::from(self.events.overflow) << 3;
        put(&mut wire, 12, flags, 4); wire[16..48].copy_from_slice(&self.nonce);
        wire[48..80].copy_from_slice(&self.authority_generation);
        wire[80..112].copy_from_slice(&self.registrations.lease_generation);
        put(&mut wire, 112, self.cgroup.device, 8); put(&mut wire, 120, self.cgroup.inode, 8);
        wire[128..160].copy_from_slice(&self.budget); put(&mut wire, 160, self.registrations.count as u64, 4);
        put(&mut wire, 164, self.events.count as u64, 4); put(&mut wire, 168, self.observations, 8);
        put(&mut wire, 176, self.packets_queued, 8); put(&mut wire, 184, self.stop_reason as u64, 4);
        put(&mut wire, 192, self.retired_monotonic_ns, 8);
        for (index, row) in self.registrations.records.iter().enumerate() {
            let at = REG_START + index * REG_WIDTH;
            put(&mut wire, at, row.level as u64, 4); put(&mut wire, at + 4, row.trigger_length as u64, 4);
            for (offset, value) in [(8, row.window_us), (16, row.stall_us), (24, row.pressure_device),
                (32, row.pressure_inode), (40, row.write_started_ns), (48, row.write_completed_ns), (56, row.bytes_written)] {
                put(&mut wire, at + offset, value, 8);
            }
            wire[at + 64..at + 128].copy_from_slice(&row.trigger);
        }
        for (index, event) in self.events.records.iter().enumerate() {
            let at = EVENT_START + index * EVENT_WIDTH;
            put(&mut wire, at, event.level as u64, 4); put(&mut wire, at + 8, event.sequence, 8);
            put(&mut wire, at + 16, event.observed_ns, 8); put(&mut wire, at + 24, event.send_completed_ns, 8);
        }
        Ok(wire)
    }
    pub(crate) fn decode(wire: &[u8]) -> Result<Self> {
        if wire.len() != PRESSURE_AUDIT_SIZE || &wire[..8] != b"P4AUD01!" || get(wire, 8, 4) != 1 ||
            get(wire, 12, 4) > 15 || wire[188..192].iter().chain(&wire[200..256]).any(|b| *b != 0) {
            return Err(Error::Reject("pressure audit framing/reserved fields"));
        }
        let flags = get(wire, 12, 4);
        let mut nonce = [0; 32]; nonce.copy_from_slice(&wire[16..48]);
        let mut authority_generation = [0; 32]; authority_generation.copy_from_slice(&wire[48..80]);
        let mut registrations = RegistrationAudit::default();
        registrations.lease_generation.copy_from_slice(&wire[80..112]);
        registrations.count = get(wire, 160, 4) as u32;
        for (index, row) in registrations.records.iter_mut().enumerate() {
            let at = REG_START + index * REG_WIDTH;
            *row = RegistrationRecord { level: get(wire, at, 4) as u32, trigger_length: get(wire, at + 4, 4) as u32,
                window_us: get(wire, at + 8, 8), stall_us: get(wire, at + 16, 8),
                pressure_device: get(wire, at + 24, 8), pressure_inode: get(wire, at + 32, 8),
                write_started_ns: get(wire, at + 40, 8), write_completed_ns: get(wire, at + 48, 8),
                bytes_written: get(wire, at + 56, 8), ..RegistrationRecord::default() };
            row.trigger.copy_from_slice(&wire[at + 64..at + 128]);
        }
        let mut events = EventAuditTrail { count: get(wire, 164, 4) as u32, overflow: flags & 8 != 0,
            ..EventAuditTrail::default() };
        for (index, event) in events.records.iter_mut().enumerate() {
            let at = EVENT_START + index * EVENT_WIDTH;
            if get(wire, at + 4, 4) != 0 { return Err(Error::Reject("pressure event reserved field")); }
            *event = QueuedEventRecord { level: get(wire, at, 4) as u32, sequence: get(wire, at + 8, 8),
                observed_ns: get(wire, at + 16, 8), send_completed_ns: get(wire, at + 24, 8) };
        }
        let mut budget = [0; 32]; budget.copy_from_slice(&wire[128..160]);
        let result = Self { nonce, authority_generation, cgroup: FileId { device: get(wire, 112, 8), inode: get(wire, 120, 8) },
            budget, granted: flags & 1 != 0, faulted: flags & 2 != 0, incomplete: flags & 4 != 0, registrations,
            observations: get(wire, 168, 8), packets_queued: get(wire, 176, 8), stop_reason: get(wire, 184, 4) as u32,
            events, retired_monotonic_ns: get(wire, 192, 8) };
        result.validate()?; Ok(result)
    }
    pub fn to_json(&self) -> Result<String> {
        self.validate()?;
        let hex = |bytes: &[u8]| -> String { bytes.iter().map(|byte| format!("{byte:02x}")).collect() };
        let mut registration_rows = Vec::new();
        for row in &self.registrations.records[..self.registrations.count as usize] {
            registration_rows.push(format!("{{\"level\":{},\"trigger\":\"{}\",\"window_us\":{},\"stall_us\":{},\"pressure_device\":{},\"pressure_inode\":{},\"write_started_ns\":{},\"write_completed_ns\":{},\"bytes_written\":{}}}",
                row.level, row.trigger_text()?, row.window_us, row.stall_us, row.pressure_device, row.pressure_inode,
                row.write_started_ns, row.write_completed_ns, row.bytes_written));
        }
        let events = self.events.records[..self.events.count as usize].iter().map(|row|
            format!("{{\"level\":{},\"sequence\":{},\"observed_ns\":{},\"send_completed_ns\":{}}}",
                row.level, row.sequence, row.observed_ns, row.send_completed_ns)).collect::<Vec<_>>();
        Ok(format!("{{\"schema\":1,\"source\":\"actual-registration-write-and-POLLPRI-send-after-joined-retirement\",\"nonce\":\"{}\",\"authority_generation\":\"{}\",\"lease_generation\":\"{}\",\"cgroup_device\":{},\"cgroup_inode\":{},\"budget_hex\":\"{}\",\"granted\":{},\"faulted\":{},\"incomplete\":{},\"overflow\":{},\"observations\":{},\"packets_queued\":{},\"stop_reason\":{},\"retired_monotonic_ns\":{},\"registrations\":[{}],\"events\":[{}]}}",
            hex(&self.nonce), hex(&self.authority_generation), hex(&self.registrations.lease_generation),
            self.cgroup.device, self.cgroup.inode, hex(&self.budget), self.granted, self.faulted, self.incomplete,
            self.events.overflow, self.observations, self.packets_queued, self.stop_reason, self.retired_monotonic_ns,
            registration_rows.join(","), events.join(",")))
    }
}

fn get(wire: &[u8], at: usize, width: usize) -> u64 {
    let mut value = [0; 8]; value[..width].copy_from_slice(&wire[at..at + width]); u64::from_le_bytes(value)
}
fn put(wire: &mut [u8], at: usize, value: u64, width: usize) {
    wire[at..at + width].copy_from_slice(&value.to_le_bytes()[..width]);
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> PressureAudit {
        let mut registrations = RegistrationAudit { lease_generation: [3; 32], count: 2, ..RegistrationAudit::default() };
        for (index, (level, stall)) in [(PressureLevel::Medium, 70_000), (PressureLevel::Critical, 700_000)].into_iter().enumerate() {
            let config = PressureConfig { level, window_us: 1_000_000, stall_us: stall };
            let trigger = config.exact_trigger().unwrap();
            registrations.records[index] = RegistrationRecord::completed(config, FileId { device: 30, inode: 44 },
                trigger.as_bytes(), trigger.len(), 100, 200).unwrap();
        }
        let mut budget = [0; 32]; budget[..8].copy_from_slice(&(512u64 * 1024 * 1024).to_le_bytes());
        budget[8..16].copy_from_slice(&(384u64 * 1024 * 1024).to_le_bytes());
        budget[28..32].copy_from_slice(&1u32.to_le_bytes());
        let mut events = EventAuditTrail::default();
        events.append(QueuedEventRecord { level: 2, sequence: 1, observed_ns: 1000, send_completed_ns: 1100 });
        PressureAudit { nonce: [1; 32], authority_generation: [2; 32], cgroup: FileId { device: 30, inode: 40 },
            budget, granted: true, faulted: false, incomplete: false, registrations,
            observations: 1, packets_queued: 1, stop_reason: 1, events, retired_monotonic_ns: 2000 }
    }
    #[test]
    fn actual_trigger_audit_codec_and_bounds() {
        let audit = fixture(); audit.require_minimal_root_defaults().unwrap();
        let wire = audit.encode().unwrap(); assert_eq!(PressureAudit::decode(&wire).unwrap(), audit);
        assert!(audit.to_json().unwrap().contains("full 700000 1000000"));
        let mut changed = wire; changed[REG_START + REG_WIDTH + 64 + 5] = b'1';
        assert!(PressureAudit::decode(&changed).is_err());
        let mut changed = wire; changed[188] = 1; assert!(PressureAudit::decode(&changed).is_err());
        let mut changed = wire; put(&mut changed, 164, 65, 4); assert!(PressureAudit::decode(&changed).is_err());
        let mut changed = wire; put(&mut changed, EVENT_START + 8, 2, 8); assert!(PressureAudit::decode(&changed).is_err());
        let mut changed = wire; put(&mut changed, EVENT_START + 24, 1000 + 1_000_000_000, 8);
        assert!(PressureAudit::decode(&changed).is_err());
    }
    #[test]
    fn incomplete_or_lowered_threshold_audit_cannot_qualify() {
        let mut audit = fixture(); audit.events.overflow = true; audit.incomplete = true;
        assert!(audit.validate().is_ok()); assert!(audit.require_minimal_root_defaults().is_err());
        let mut audit = fixture();
        let config = PressureConfig { level: PressureLevel::Critical, window_us: 1_000_000, stall_us: 70_000 };
        let trigger = config.exact_trigger().unwrap();
        audit.registrations.records[1] = RegistrationRecord::completed(config, FileId { device: 30, inode: 44 },
            trigger.as_bytes(), trigger.len(), 100, 200).unwrap();
        assert!(audit.validate().is_ok()); assert!(audit.require_minimal_root_defaults().is_err());
        let mut audit = fixture(); audit.packets_queued = 2; audit.observations = 2;
        assert!(audit.validate().is_err());
        let mut audit = fixture(); audit.observations = 2;
        assert!(audit.validate().is_err());
        audit.incomplete = true; assert!(audit.validate().is_ok());
        assert!(audit.require_minimal_root_defaults().is_err());
        let mut audit = fixture(); audit.registrations.records[1].pressure_inode += 1;
        assert!(audit.validate().is_err());
    }
}
