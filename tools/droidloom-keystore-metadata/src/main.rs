//! Inspect or prepare a new, isolated Keystore metadata experiment.
use clap::{Parser, Subcommand};
use droidloom_keystore_metadata::{Request, run};
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    about = "Audit a cold Keystore copy, or prepare a NEW clone for runtime qualification. No in-place database writer."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
    /// Report schema and unqualified metadata candidates; discard the private working copy.
    Audit {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        workspace: PathBuf,
    },
    /// Prepare a new private directory; requires externally reviewed snapshot/backend evidence.
    PrepareClone {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        workspace: PathBuf,
        #[arg(long)]
        evidence: PathBuf,
    },
}
fn main() {
    let (input, workspace, evidence) = match Cli::parse().command {
        Command::Audit { input, workspace } => (input, workspace, None),
        Command::PrepareClone {
            input,
            workspace,
            evidence,
        } => (input, workspace, Some(evidence)),
    };
    match run(&Request {
        input,
        workspace,
        evidence,
    }) {
        Ok(report) => println!(
            "{}",
            serde_json::to_string_pretty(&report).expect("report JSON")
        ),
        Err(code) => {
            // Error codes are fixed strings. Never print database values, SQL errors, or key IDs.
            eprintln!("{}", serde_json::json!({"status":"refused","reason":code}));
            std::process::exit(1);
        }
    }
}
