//! Optional trusted-parent startup barrier. Reservation carries only actual
//! Session identity/nonce, never descriptors, authority or an attachment ACK.

use serde::{Deserialize, Serialize};
use crate::notes::NotesTargetIdentity;
use crate::notes_bootstrap::{NotesBootstrapOffer, NOTES_BOOTSTRAP_MAX_BYTES};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesReservationAction { NotesTargetReserved }

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesStartupReservation {
    pub schema_version: u16,
    pub action: NotesReservationAction,
    pub target: NotesTargetIdentity,
    pub destination_id: String,
    pub nonce: String,
}

impl NotesStartupReservation {
    pub fn new(target: NotesTargetIdentity, nonce: String) -> Result<Self, &'static str> {
        let offer = NotesBootstrapOffer::new(target)?;
        let value = Self { schema_version: 1, action: NotesReservationAction::NotesTargetReserved,
            target: offer.target, destination_id: offer.destination_id, nonce };
        validate(value.schema_version, &value.target, &value.destination_id, &value.nonce)?;
        Ok(value)
    }

    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        frame(raw)?;
        let value: Self = serde_json::from_slice(raw).map_err(|_| "Notes reservation schema")?;
        validate(value.schema_version, &value.target, &value.destination_id, &value.nonce)?;
        Ok(value)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NotesActivationAction { ActivateNotesBootstrap }

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NotesStartupActivation {
    pub schema_version: u16,
    pub action: NotesActivationAction,
    pub target: NotesTargetIdentity,
    pub destination_id: String,
    pub nonce: String,
}

impl NotesStartupActivation {
    pub fn from_reservation(value: &NotesStartupReservation) -> Self {
        Self { schema_version: 1, action: NotesActivationAction::ActivateNotesBootstrap,
            target: value.target.clone(), destination_id: value.destination_id.clone(), nonce: value.nonce.clone() }
    }

    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        frame(raw)?;
        let value: Self = serde_json::from_slice(raw).map_err(|_| "Notes activation schema")?;
        validate(value.schema_version, &value.target, &value.destination_id, &value.nonce)?;
        Ok(value)
    }

    pub fn matches(&self, reservation: &NotesStartupReservation) -> bool {
        self.target == reservation.target && self.destination_id == reservation.destination_id
            && self.nonce == reservation.nonce
    }
}

fn validate(version: u16, target: &NotesTargetIdentity, destination: &str, nonce: &str) -> Result<(), &'static str> {
    let offer = NotesBootstrapOffer::new(target.clone())?;
    if version != 1 || offer.destination_id != destination || nonce.len() != 32
        || !nonce.bytes().all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
        || !nonce.bytes().any(|byte| byte != b'0')
    { return Err("Notes reservation/activation identity or nonce"); }
    Ok(())
}

fn frame(raw: &[u8]) -> Result<(), &'static str> {
    if raw.is_empty() || raw.len() > NOTES_BOOTSTRAP_MAX_BYTES { Err("Notes startup frame bound") } else { Ok(()) }
}
