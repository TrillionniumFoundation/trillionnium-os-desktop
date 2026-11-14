//! User-session Android application catalog, XDG reconciliation and release evidence checks.

#![forbid(unsafe_code)]

use std::env;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

use clap::Parser;
use droidloom_applications::{CatalogPaths, ControlCatalog, reconcile, remove_managed};
use droidloom_supervisor::control::DEFAULT_CONTROL_SOCKET;

const DEFAULT_REFRESH_SECONDS: u64 = 30;

#[cfg(test)]
mod cli_tests {
    use super::*;

    #[test]
    fn release_check_requires_external_pins_and_excludes_catalog_mutation() {
        assert!(Cli::try_parse_from(["apps", "--release-check", "/manifest"]).is_err());
        let args = [
            "apps",
            "--release-check",
            "/manifest",
            "--release-results",
            "/results",
            "--expect-release-sha256",
            "manifest-pin",
            "--expect-main-sha256",
            "main-pin",
            "--expect-app-count",
            "42",
        ];
        assert!(Cli::try_parse_from(args).is_ok());
        let mut conflicting = args.to_vec();
        conflicting.push("--remove-managed");
        assert!(Cli::try_parse_from(conflicting).is_err());
        assert!(Cli::try_parse_from(["apps", "--once"]).is_ok());
    }
    #[test]
    fn runtime_plan_requires_complete_pins_and_excludes_other_actions() {
        assert!(Cli::try_parse_from(["apps", "--runtime-plan", "/plan"]).is_err());
        let args = [
            "apps",
            "--runtime-plan",
            "/plan",
            "--expect-runtime-plan-sha256",
            "plan-pin",
            "--expect-app-count",
            "42",
        ];
        assert!(Cli::try_parse_from(args).is_ok());
        for extra in [
            vec!["--once"],
            vec!["--remove-managed"],
            vec!["--user", "0"],
            vec!["--inspect-package", "org.mozilla.firefox"],
        ] {
            let mut conflicting = args.to_vec();
            conflicting.extend(extra);
            assert!(Cli::try_parse_from(conflicting).is_err());
        }
        assert!(Cli::try_parse_from(["apps", "--expect-app-count", "42"]).is_err());
    }

    #[test]
    fn installed_identity_inspection_allows_only_its_own_socket_and_user() {
        assert!(
            Cli::try_parse_from([
                "apps",
                "--inspect-package",
                "org.mozilla.firefox",
                "--socket",
                "/socket",
                "--user",
                "1"
            ])
            .is_ok()
        );
        assert!(
            Cli::try_parse_from(["apps", "--inspect-package", "org.mozilla.firefox", "--once"])
                .is_err()
        );
        assert!(
            Cli::try_parse_from([
                "apps",
                "--inspect-package",
                "org.mozilla.firefox",
                "--release-results",
                "/results"
            ])
            .is_err()
        );
    }
}

#[derive(Debug, Parser)]
#[command(name = "droidloom-applications", version, about)]
#[command(group(clap::ArgGroup::new("release_action").args(["release_check", "runtime_plan"])))]
struct Cli {
    /// Check complete declared release evidence without contacting Android or changing the catalog.
    #[arg(long, value_name = "MANIFEST", requires_all = ["release_results", "expect_release_sha256", "expect_main_sha256", "expect_app_count"],
        conflicts_with_all = ["runtime_plan", "inspect_package", "remove_managed", "socket", "user", "once", "refresh_seconds"])]
    release_check: Option<PathBuf>,
    /// Results for every selected application and gate.
    #[arg(long, value_name = "RESULTS", requires = "release_check")]
    release_results: Option<PathBuf>,
    /// Independently frozen manifest SHA-256; prevents a reduced application selection.
    #[arg(long, requires = "release_check")]
    expect_release_sha256: Option<String>,
    /// Independently established current Main qualification receipt SHA-256.
    #[arg(long, requires = "release_check")]
    expect_main_sha256: Option<String>,
    /// Complete selected application count, including blocked and unsupported applications.
    #[arg(long, requires = "release_action")]
    expect_app_count: Option<usize>,
    /// Query actual PM identity and APK bytes; never launches or installs an app.
    #[arg(long, conflicts_with_all = ["runtime_plan", "release_check", "remove_managed", "once", "refresh_seconds"])]
    inspect_package: Option<String>,
    /// Execute explicit per-app runtime routing; unsupported and pending gates remain incomplete.
    #[arg(long, requires_all = ["expect_runtime_plan_sha256", "expect_app_count"], conflicts_with_all = ["inspect_package", "release_check", "remove_managed", "once", "refresh_seconds", "user"])]
    runtime_plan: Option<PathBuf>,
    /// Independently reviewed complete runtime plan hash.
    #[arg(long, requires = "runtime_plan")]
    expect_runtime_plan_sha256: Option<String>,
    /// Remove only entries recorded in Droidloom's catalog; Android need not be running.
    #[arg(long)]
    remove_managed: bool,
    /// Droidloom lifecycle socket.
    #[arg(long, default_value = DEFAULT_CONTROL_SOCKET)]
    socket: PathBuf,
    /// Android user whose launchable activities are exported.
    #[arg(long, default_value_t = 0)]
    user: u32,
    /// Reconcile once and exit instead of watching for package changes.
    #[arg(long)]
    once: bool,
    /// Package-catalog polling interval. Android is queried only once per interval.
    #[arg(long, default_value_t = DEFAULT_REFRESH_SECONDS, value_parser = clap::value_parser!(u64).range(5..))]
    refresh_seconds: u64,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("droidloom-applications: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    if let Some(package) = &cli.inspect_package {
        let observed =
            droidloom_applications::runtime_plan::inspect_package(&cli.socket, package, cli.user)?;
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "operation": "inspect_installed_application", "observation": observed,
                "production_ready": false, "runtime_qualified": false, "app_launches": 0
            }))?
        );
        return Ok(());
    }
    if let Some(path) = &cli.runtime_plan {
        let report = droidloom_applications::runtime_plan::run_files(
            &cli.socket,
            path,
            cli.expect_runtime_plan_sha256
                .as_deref()
                .ok_or("missing runtime plan pin")?,
            cli.expect_app_count
                .ok_or("missing complete selected count")?,
        )?;
        println!("{}", serde_json::to_string_pretty(&report)?);
        return Err("application acceptance remains incomplete; retain blocked, unsupported and pending gates".into());
    }
    if let Some(manifest) = cli.release_check {
        let report = droidloom_applications::release::check_release_files(
            &manifest,
            &cli.release_results.ok_or("missing release results")?,
            &cli.expect_release_sha256
                .ok_or("missing release manifest pin")?,
            &cli.expect_main_sha256.ok_or("missing current Main pin")?,
            cli.expect_app_count
                .ok_or("missing selected application count")?,
        )?;
        println!("{}", serde_json::to_string_pretty(&report)?);
        return if report.evidence_complete {
            Ok(())
        } else {
            Err("declared release evidence is incomplete; inspect the JSON report".into())
        };
    }
    droidloom_cpu_placement::initialize(droidloom_cpu_placement::Role::Background);
    let paths = CatalogPaths::from_environment(
        env::var_os("XDG_DATA_HOME"),
        env::var_os("XDG_STATE_HOME"),
        env::var_os("HOME"),
    )?;
    if cli.remove_managed {
        let count = remove_managed(&paths)?;
        println!("Removed {count} Droidloom launcher/icon entries; Android data retained.");
        return Ok(());
    }
    let mut catalog = ControlCatalog::new(cli.socket, cli.user);

    loop {
        match reconcile(&paths, &mut catalog) {
            Ok(summary) => {
                if summary.changed() {
                    eprintln!(
                        "droidloom-applications: {} launchers, {} icons updated, {} stale entries removed",
                        summary.applications, summary.icons_updated, summary.entries_removed
                    );
                }
            }
            Err(error) if !cli.once => {
                // Droidloom is boot-managed independently of this user helper.
                // A temporary Android restart must not erase the last good XDG
                // catalog or turn the helper into a service failure loop.
                eprintln!("droidloom-applications: catalog refresh deferred: {error}");
            }
            Err(error) => return Err(error.into()),
        }
        if cli.once {
            return Ok(());
        }
        thread::sleep(Duration::from_secs(cli.refresh_seconds));
    }
}
