//! Explicit D0/qualification-only AgentPort fixture.
//!
//! This binary is available only with the `fixture` Cargo feature. It creates
//! no filesystem or network listener and is absent from the Debian production
//! installation map. Product activation must never substitute this handler for
//! a real BrowserActor.

#![forbid(unsafe_code)]

use hepta_agent_port::D0FixtureHandler;

fn main() {
    if !std::env::args().any(|argument| argument == "--self-check") {
        eprintln!(
            "hepta-agent-port-fixture: qualification fixture accepts only --self-check"
        );
        std::process::exit(64);
    }
    match self_check() {
        Ok(report) => println!("{report}"),
        Err(error) => {
            eprintln!("hepta-agent-port-fixture: {error}");
            std::process::exit(1);
        }
    }
}

fn self_check() -> Result<String, hepta_agent_port::AgentPortError> {
    hepta_agent_port::self_check()?;
    let handler = D0FixtureHandler::default();
    if handler.invocation_count != 0 {
        return Err(hepta_agent_port::AgentPortError::SelfCheckInvariant(
            "fresh fixture handler is not quiescent",
        ));
    }
    Ok(concat!(
        "{\"schema\":\"trillionnium.desktop.agent-port-fixture-self-check.v1\",",
        "\"ok\":true,\"fixture_profile\":true,",
        "\"listener_created\":false,\"product_installable\":false,",
        "\"browser_actor_connected\":false,",
        "\"external_effect_authority\":false}"
    )
    .to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixture_is_explicit_closed_and_non_product() {
        let report = self_check().expect("fixture self-check");
        assert!(report.contains("\"fixture_profile\":true"));
        assert!(report.contains("\"listener_created\":false"));
        assert!(report.contains("\"product_installable\":false"));
        assert!(report.contains("\"external_effect_authority\":false"));
    }
}
