//! New multi-target private startup. This does not change the Notes-only wire
//! or turn a reservation into an authority grant or application-effect receipt.
use crate::calculator::{lower_hex, CalculatorTargetIdentity};
use crate::notes::NotesTargetIdentity;
use serde::{Deserialize, Serialize};

pub const MAX_DESKTOP_BOOTSTRAP_BYTES: usize = 1024;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DesktopProfile {
    NotesCalculatorV1,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DesktopReservationAction {
    DesktopTargetsReserved,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DesktopStartupReservation {
    pub schema_version: u16,
    pub action: DesktopReservationAction,
    pub profile: DesktopProfile,
    pub notes: NotesTargetIdentity,
    pub calculator: CalculatorTargetIdentity,
    pub nonce: String,
}

impl DesktopStartupReservation {
    pub fn new(
        notes: NotesTargetIdentity,
        calculator: CalculatorTargetIdentity,
        nonce: String,
    ) -> Result<Self, &'static str> {
        let value = Self {
            schema_version: 1,
            action: DesktopReservationAction::DesktopTargetsReserved,
            profile: DesktopProfile::NotesCalculatorV1,
            notes,
            calculator,
            nonce,
        };
        validate(
            value.schema_version,
            &value.notes,
            &value.calculator,
            &value.nonce,
        )?;
        Ok(value)
    }
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let value: Self = parse(raw)?;
        validate(
            value.schema_version,
            &value.notes,
            &value.calculator,
            &value.nonce,
        )?;
        Ok(value)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DesktopActivationAction {
    ActivateDesktopBootstrap,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DesktopStartupActivation {
    pub schema_version: u16,
    pub action: DesktopActivationAction,
    pub profile: DesktopProfile,
    pub notes: NotesTargetIdentity,
    pub calculator: CalculatorTargetIdentity,
    pub nonce: String,
}

impl DesktopStartupActivation {
    pub fn from_reservation(reservation: &DesktopStartupReservation) -> Self {
        Self {
            schema_version: 1,
            action: DesktopActivationAction::ActivateDesktopBootstrap,
            profile: reservation.profile,
            notes: reservation.notes.clone(),
            calculator: reservation.calculator.clone(),
            nonce: reservation.nonce.clone(),
        }
    }
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let value: Self = parse(raw)?;
        validate(
            value.schema_version,
            &value.notes,
            &value.calculator,
            &value.nonce,
        )?;
        Ok(value)
    }
    pub fn matches(&self, reservation: &DesktopStartupReservation) -> bool {
        self.schema_version == 1
            && reservation.schema_version == 1
            && self.profile == reservation.profile
            && self.notes == reservation.notes
            && self.calculator == reservation.calculator
            && self.nonce == reservation.nonce
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorOfferAction {
    OfferCalculatorTarget,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorBootstrapOffer {
    pub schema_version: u16,
    pub action: CalculatorOfferAction,
    pub target: CalculatorTargetIdentity,
    pub destination_id: String,
}

impl CalculatorBootstrapOffer {
    pub fn new(target: CalculatorTargetIdentity) -> Result<Self, &'static str> {
        target
            .validate()
            .map_err(|_| "Calculator bootstrap target")?;
        Ok(Self {
            schema_version: 1,
            action: CalculatorOfferAction::OfferCalculatorTarget,
            destination_id: target.destination_id(),
            target,
        })
    }
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let value: Self = parse(raw)?;
        value
            .target
            .validate()
            .map_err(|_| "Calculator bootstrap target")?;
        if value.schema_version != 1 || value.destination_id != value.target.destination_id() {
            return Err("Calculator bootstrap binding");
        }
        Ok(value)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorAckAction {
    CalculatorTargetAck,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorBootstrapStatus {
    Attached,
    Rejected,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorBootstrapAck {
    pub schema_version: u16,
    pub action: CalculatorAckAction,
    pub target: CalculatorTargetIdentity,
    pub destination_id: String,
    pub status: CalculatorBootstrapStatus,
}
impl CalculatorBootstrapAck {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let value: Self = parse(raw)?;
        value
            .target
            .validate()
            .map_err(|_| "Calculator ACK target")?;
        if value.schema_version != 1 || value.destination_id != value.target.destination_id() {
            return Err("Calculator ACK binding");
        }
        Ok(value)
    }
    pub fn matches(&self, offer: &CalculatorBootstrapOffer) -> bool {
        self.schema_version == 1
            && offer.schema_version == 1
            && self.target == offer.target
            && self.destination_id == offer.destination_id
    }
}

fn validate(
    version: u16,
    notes: &NotesTargetIdentity,
    calculator: &CalculatorTargetIdentity,
    nonce: &str,
) -> Result<(), &'static str> {
    notes.validate().map_err(|_| "Desktop Notes target")?;
    calculator
        .validate()
        .map_err(|_| "Desktop Calculator target")?;
    if version != 1
        || notes.task_id != 1
        || calculator.task_id != 2
        || notes.session_instance != calculator.session_instance
        || notes.incarnation == calculator.incarnation
        || !lower_hex(nonce, 32)
        || nonce.bytes().all(|b| b == b'0')
    {
        return Err("Desktop reservation target or nonce mismatch");
    }
    Ok(())
}
fn parse<T: for<'de> Deserialize<'de>>(raw: &[u8]) -> Result<T, &'static str> {
    if raw.is_empty() || raw.len() > MAX_DESKTOP_BOOTSTRAP_BYTES {
        return Err("Desktop bootstrap frame bound");
    }
    serde_json::from_slice(raw).map_err(|_| "Desktop bootstrap schema")
}

#[cfg(test)]
#[path = "desktop_startup_tests.rs"]
mod tests;
