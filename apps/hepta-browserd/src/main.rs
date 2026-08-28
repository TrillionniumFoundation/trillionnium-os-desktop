#![forbid(unsafe_code)]

use std::process::ExitCode;

use hepta_browserd::{ACTIVE_PLAN_REVISION, IMPLEMENTATION_STAGE, run_self_check};

fn main() -> ExitCode {
    let mut arguments = std::env::args();
    let program = arguments
        .next()
        .unwrap_or_else(|| "hepta-browserd".to_string());
    match arguments.next().as_deref() {
        Some("--self-check") => match run_self_check() {
            Ok(report) => {
                println!("{}", report.to_json());
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("hepta-browserd self-check failed: {error}");
                ExitCode::FAILURE
            }
        },
        Some("--print-build-info") => {
            println!(
                "hepta-browserd {} plan={} stage={}",
                env!("CARGO_PKG_VERSION"),
                ACTIVE_PLAN_REVISION,
                IMPLEMENTATION_STAGE
            );
            ExitCode::SUCCESS
        }
        Some("--help") | None => {
            println!(
                "Usage: {program} [--self-check|--print-build-info|--help]\n\n\
                 D0 scaffold only: no Servo runtime, UDS listener, or external network authority is started."
            );
            ExitCode::SUCCESS
        }
        Some(argument) => {
            eprintln!("unknown argument: {argument}");
            ExitCode::from(2)
        }
    }
}
