#![forbid(unsafe_code)]

mod capture;
mod fs;
mod materialize;
mod model;
mod paths;
#[cfg(test)]
mod tests;

use clap::{Parser, Subcommand};
use model::{Manifest, Selection};
use std::path::PathBuf;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
fn ensure(ok: bool, message: &str) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(message.to_owned().into())
    }
}

#[derive(Parser)]
#[command(
    about = "Materialize a private real Ubuntu qualification root from reviewed public native files. Never boots or qualifies a guest."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    Capture {
        #[arg(long)]
        selection: PathBuf,
        #[arg(long)]
        selection_sha256: String,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        module_output: Option<PathBuf>,
    },
    Materialize {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        manifest_sha256: String,
        #[arg(long)]
        destination: PathBuf,
        #[arg(long)]
        receipt: PathBuf,
    },
    Verify {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        manifest_sha256: String,
        #[arg(long)]
        destination: PathBuf,
        #[arg(long)]
        receipt: PathBuf,
    },
}

fn run() -> Result<()> {
    let cli = Cli::parse();
    // Only the internal synthetic tests accept their temporary tree owner's UID.
    ensure(
        rustix::process::geteuid().as_raw() == 0,
        "real source capture/copy requires existing root rights; no privilege helper is installed",
    )?;
    match cli.command {
        Command::Capture {
            selection,
            selection_sha256,
            output,
            module_output,
        } => {
            let input: Selection =
                fs::read_json(&fs::absolute_string(&selection)?, &selection_sha256)?;
            ensure(
                input.kernel.is_none() || module_output.is_some(),
                "target-kernel admission requires a separate module-output manifest",
            )?;
            let result = capture::capture(input, &selection_sha256, 0)?;
            let module_hash = if let Some(path) = module_output {
                let entries: Vec<_> = result
                    .entries
                    .iter()
                    .filter(|e| e.component == model::Component::TargetModule)
                    .collect();
                Some(fs::write_json(
                    &fs::absolute_string(&path)?,
                    &serde_json::json!({
                        "schema":"droidloom.ubuntu-target-module-content.v1", "selection_sha256":selection_sha256,
                        "kernel":result.kernel, "entries":entries, "guest_qualified":false
                    }),
                    0,
                )?)
            } else {
                None
            };
            let sha = fs::write_json(&fs::absolute_string(&output)?, &result, 0)?;
            println!(
                "{}",
                serde_json::json!({"manifest_sha256":sha,"entries":result.entries.len(),"module_manifest_sha256":module_hash,"guest_qualified":false})
            );
        }
        Command::Materialize {
            manifest,
            manifest_sha256,
            destination,
            receipt,
        } => {
            let input: Manifest =
                fs::read_json(&fs::absolute_string(&manifest)?, &manifest_sha256)?;
            let result = materialize::materialize(
                &input,
                &manifest_sha256,
                &fs::absolute_string(&destination)?,
                0,
            )?;
            let sha = fs::write_json(&fs::absolute_string(&receipt)?, &result, 0)?;
            println!(
                "{}",
                serde_json::json!({"receipt_sha256":sha,"entries_verified":result.entries_verified,"unique_regular_bytes":result.unique_regular_bytes,"materialization_complete":true,"guest_qualified":false})
            );
        }
        Command::Verify {
            manifest,
            manifest_sha256,
            destination,
            receipt,
        } => {
            let input: Manifest =
                fs::read_json(&fs::absolute_string(&manifest)?, &manifest_sha256)?;
            let result = materialize::verify(
                &input,
                &manifest_sha256,
                &fs::absolute_string(&destination)?,
                0,
            )?;
            let sha = fs::write_json(&fs::absolute_string(&receipt)?, &result, 0)?;
            println!(
                "{}",
                serde_json::json!({"receipt_sha256":sha,"entries_verified":result.entries_verified,"materialization_complete":true,"guest_qualified":false})
            );
        }
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("fixture materialization refused: {error}");
        std::process::exit(1);
    }
}
