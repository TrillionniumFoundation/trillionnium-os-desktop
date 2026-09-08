#![forbid(unsafe_code)]

//! Isolated source marker for the explicit D3 development/qualification graph.
//!
//! The persistent service and exact-image fixtures are binary targets gated by
//! the non-default `development` feature. The default product workspace graph
//! therefore does not activate static peer attestation or an AgentPort listener.

pub const DEVELOPMENT_FEATURE_REQUIRED: bool = true;
pub const PRODUCT_AGENT_PORT_ENABLED: bool = false;
pub const EXTERNAL_EFFECT_AUTHORITY: bool = false;
