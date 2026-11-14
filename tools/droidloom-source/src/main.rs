//! Command-line entry point for exact-commit sparse AOSP materialization.

#![forbid(unsafe_code)]

use std::path::PathBuf;

use clap::{Parser, Subcommand, ValueEnum};
use droidloom_source::{load_lock, SparseSourceLock, MaterializationPlan, MaterializedManifest, SourceError};
use std::path::Path;

#[derive(Debug, Parser)]
#[command(name = "droidloom-source", version, about)]
struct Cli {
    /// Select the independent bounded source contract; the default stays Audio541.
    #[arg(long, global = true, value_enum, default_value_t = Profile::Audio)]
    profile: Profile,
    #[command(subcommand)]
    command: Command,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum Profile {
    Audio,
    NativePair,
    ProductionFull,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Validate the bounded sparse lock without touching the network.
    VerifyLock {
        /// Sparse source lock to verify.
        #[arg(long, default_value = "android/manifest/m2-sparse-source-lock.json")]
        lock: PathBuf,
    },
    /// Print the exact immutable project plan without fetching it.
    Plan {
        /// Sparse source lock to inspect.
        #[arg(long, default_value = "android/manifest/m2-sparse-source-lock.json")]
        lock: PathBuf,
    },
    /// Fetch exact commits into a new atomically published source directory.
    Materialize {
        /// Sparse source lock to materialize.
        #[arg(long, default_value = "android/manifest/m2-sparse-source-lock.json")]
        lock: PathBuf,
        /// New output directory. Existing paths are refused.
        #[arg(long)]
        output: PathBuf,
    },
    /// Add newly locked projects to an existing verified materialization.
    Reconcile {
        /// Sparse source lock to reconcile against.
        #[arg(long, default_value = "android/manifest/m2-sparse-source-lock.json")]
        lock: PathBuf,
        /// Existing droidloom-source output directory.
        #[arg(long)]
        output: PathBuf,
    },
    /// Verify an existing materialization without fetching or modifying it.
    VerifyMaterialized {
        /// Sparse source lock the materialization must exactly match.
        #[arg(long, default_value = "android/manifest/m2-sparse-source-lock.json")]
        lock: PathBuf,
        /// Existing droidloom-source output directory.
        #[arg(long)]
        output: PathBuf,
    },
}

fn main() {
    if let Err(error) = run() {
        eprintln!("droidloom-source: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    let build_plan: fn(&SparseSourceLock) -> Result<MaterializationPlan, SourceError> = match cli.profile {
        Profile::Audio => droidloom_source::build_plan,
        Profile::NativePair => droidloom_source::native_pair::build_plan,
        Profile::ProductionFull => droidloom_source::production_full::build_plan,
    };
    type SourceOperation = fn(&Path, &SparseSourceLock, &Path) -> Result<MaterializedManifest, SourceError>;
    let (materialize, reconcile, verify_materialized): (SourceOperation, SourceOperation, SourceOperation) = match cli.profile {
        Profile::Audio => (droidloom_source::materialize, droidloom_source::reconcile, droidloom_source::verify_materialized),
        Profile::NativePair => (droidloom_source::native_pair::materialize, droidloom_source::native_pair::reconcile, droidloom_source::native_pair::verify_materialized),
        Profile::ProductionFull => (droidloom_source::production_full::materialize, droidloom_source::production_full::reconcile, droidloom_source::production_full::verify_materialized),
    };
    match cli.command {
        Command::VerifyLock { lock } => {
            let lock = load_lock(&lock)?;
            let plan = build_plan(&lock)?;
            println!(
                "verified {} exact AOSP projects and {} root links at superproject {}",
                plan.projects.len(),
                plan.links.len(),
                plan.superproject_commit
            );
        }
        Command::Plan { lock } => {
            let lock = load_lock(&lock)?;
            println!("{}", serde_json::to_string_pretty(&build_plan(&lock)?)?);
        }
        Command::Materialize { lock, output } => {
            let source_lock = load_lock(&lock)?;
            let manifest = materialize(&lock, &source_lock, &output)?;
            println!(
                "materialized {} exact AOSP projects at {}",
                manifest.plan.projects.len(),
                output.display()
            );
        }
        Command::Reconcile { lock, output } => {
            let source_lock = load_lock(&lock)?;
            let manifest = reconcile(&lock, &source_lock, &output)?;
            println!(
                "reconciled {} exact AOSP projects at {}",
                manifest.plan.projects.len(),
                output.display()
            );
        }
        Command::VerifyMaterialized { lock, output } => {
            let source_lock = load_lock(&lock)?;
            let manifest = verify_materialized(&lock, &source_lock, &output)?;
            println!(
                "verified {} exact AOSP projects at {}",
                manifest.plan.projects.len(),
                output.display()
            );
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_cli_keeps_audio_default_and_requires_named_native_profile() {
        let audio = Cli::try_parse_from(["droidloom-source", "verify-lock"]).unwrap();
        assert!(matches!(audio.profile, Profile::Audio));
        for argv in [
            ["droidloom-source", "--profile", "native-pair", "verify-lock"],
            ["droidloom-source", "verify-lock", "--profile", "native-pair"],
        ] {
            let native = Cli::try_parse_from(argv).unwrap();
            assert!(matches!(native.profile, Profile::NativePair));
        }
        let full = Cli::try_parse_from(["droidloom-source", "--profile", "production-full", "verify-lock"]).unwrap();
        assert!(matches!(full.profile, Profile::ProductionFull));
        for value in ["native", "unbounded", "656", "539", ""] {
            assert!(Cli::try_parse_from(["droidloom-source", "--profile", value, "verify-lock"]).is_err());
        }
    }
}
