#![forbid(unsafe_code)]

mod boot;
mod boot_apparmor_candidate;
mod boot_candidate;
mod boot_child;
mod boot_collect;
mod boot_complete;
mod boot_files;
mod boot_gdm_candidate;
mod boot_gdm_proof;
mod boot_host;
mod boot_kernel;
mod boot_native;
mod boot_native_candidates;
mod boot_owned_evidence;
mod boot_packages;
mod boot_public_apks;
mod boot_qemu;
mod boot_query;
mod boot_query_image;
mod boot_release;
mod boot_runtime;
mod boot_systemd_candidate;
mod boot_vm;
mod capture;
mod complete_native;
mod complete_snapshot;
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
    about = "Capture, initialize, and boot a private real Ubuntu qualification root. Runtime and application acceptance remain independent."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    VerifyNativeCandidates {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    VerifyOwnedGuest {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    VerifySystemdCandidate {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    CollectBoot {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    VerifyBootMaterials {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    VerifyHostImport {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    Boot {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    PrepareBoot {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    PrepareNative {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    PrepareCompleteNative {
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        config_sha256: String,
    },
    CaptureCompleteNative {
        #[arg(long)]
        source_receipt: PathBuf,
        #[arg(long)]
        source_receipt_sha256: String,
        #[arg(long)]
        target_kernel_release: String,
        #[arg(long)]
        output: PathBuf,
    },
    MaterializeCompleteNative {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        manifest_sha256: String,
        #[arg(long)]
        destination: PathBuf,
        #[arg(long)]
        receipt: PathBuf,
    },
    VerifyCompleteNative {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        manifest_sha256: String,
        #[arg(long)]
        destination: PathBuf,
        #[arg(long)]
        receipt: PathBuf,
    },
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
        Command::VerifyNativeCandidates {
            config,
            config_sha256,
        } => boot_native_candidates::run(&config, &config_sha256)?,
        Command::VerifyOwnedGuest {
            config,
            config_sha256,
        } => boot_owned_evidence::run(&config, &config_sha256)?,
        Command::VerifySystemdCandidate {
            config,
            config_sha256,
        } => boot_systemd_candidate::run(&config, &config_sha256)?,
        Command::CollectBoot {
            config,
            config_sha256,
        } => boot_collect::run(&config, &config_sha256)?,
        Command::VerifyBootMaterials {
            config,
            config_sha256,
        } => boot::verify_boot_materials(&config, &config_sha256)?,
        Command::VerifyHostImport {
            config,
            config_sha256,
        } => boot::verify_host_import(&config, &config_sha256)?,
        Command::Boot {
            config,
            config_sha256,
        } => boot_vm::run(&config, &config_sha256)?,
        Command::PrepareBoot {
            config,
            config_sha256,
        } => boot::prepare_boot(&config, &config_sha256)?,
        Command::PrepareNative {
            config,
            config_sha256,
        } => boot::prepare_native(&config, &config_sha256)?,
        Command::PrepareCompleteNative {
            config,
            config_sha256,
        } => {
            boot_complete::prepare(&config, &config_sha256)?;
        }
        Command::CaptureCompleteNative {
            source_receipt,
            source_receipt_sha256,
            target_kernel_release,
            output,
        } => {
            let result = complete_native::capture(
                &source_receipt,
                &source_receipt_sha256,
                &target_kernel_release,
            )?;
            let source_stage = complete_native::validate(&result)?.stage;
            let sha = fs::write_json(&fs::absolute_string(&output)?, &result, 0)?;
            println!(
                "{}",
                serde_json::json!({"manifest_sha256":sha,
                "entries":result.entries.len()+result.static_devices.len(),
                "complete_package_database":true,"source_stage":source_stage,"guest_qualified":false})
            );
        }
        Command::MaterializeCompleteNative {
            manifest,
            manifest_sha256,
            destination,
            receipt,
        } => {
            let input: complete_native::CompleteManifest =
                fs::read_json(&fs::absolute_string(&manifest)?, &manifest_sha256)?;
            let result = complete_native::materialize(&input, &manifest_sha256, &destination)?;
            let sha = fs::write_json(&fs::absolute_string(&receipt)?, &result, 0)?;
            println!(
                "{}",
                serde_json::json!({"receipt_sha256":sha,"materialization_complete":true,"guest_qualified":false})
            );
        }
        Command::VerifyCompleteNative {
            manifest,
            manifest_sha256,
            destination,
            receipt,
        } => {
            let input: complete_native::CompleteManifest =
                fs::read_json(&fs::absolute_string(&manifest)?, &manifest_sha256)?;
            let result = complete_native::verify(&input, &manifest_sha256, &destination)?;
            let sha = fs::write_json(&fs::absolute_string(&receipt)?, &result, 0)?;
            println!(
                "{}",
                serde_json::json!({"receipt_sha256":sha,"materialization_complete":true,"guest_qualified":false})
            );
        }
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
