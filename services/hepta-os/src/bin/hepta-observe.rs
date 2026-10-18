//! Diagnostic launcher for one explicit, trusted, local read-only endpoint.

use hepta_os_observer::{EndpointConfig, ObserverClient, ObserverError};
use std::path::PathBuf;

fn main() {
    if let Err(error) = run() {
        eprintln!("hepta-observe: {}", error.code());
        std::process::exit(1);
    }
}

fn run() -> Result<(), ObserverError> {
    let arguments: Vec<_> = std::env::args().skip(1).collect();
    if arguments.len() == 1 && matches!(arguments[0].as_str(), "--help" | "-h") {
        println!(
            "hepta-observe <absolute-socket> <agent-uuid> <spawn-generation> <peer-uid> [run-id]\n\
             Reads pinned Agentd v2 health/capabilities/lifecycle events or one known run.\n\
             Linux host only. Endpoint identity must come from a trusted launcher.\n\
             No objective submission, signing, cancellation, or device effects."
        );
        return Ok(());
    }
    if !matches!(arguments.len(), 4 | 5) {
        return Err(ObserverError::InvalidRequest);
    }
    let endpoint = EndpointConfig::new(
        PathBuf::from(&arguments[0]),
        arguments[1].clone(),
        arguments[2]
            .parse()
            .map_err(|_| ObserverError::InvalidEndpoint)?,
        arguments[3]
            .parse()
            .map_err(|_| ObserverError::InvalidEndpoint)?,
    )?;
    let mut client = ObserverClient::new(endpoint)?;
    let projection = if let Some(run_id) = arguments.get(4) {
        serde_json::to_string_pretty(&client.run_status(run_id)?)
    } else {
        serde_json::to_string_pretty(&client.poll(0, 16)?)
    }
    .map_err(|_| ObserverError::ProtocolMismatch)?;
    println!("{projection}");
    Ok(())
}
