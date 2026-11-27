//! User-session Android application catalog, XDG reconciliation and release evidence checks.

#![forbid(unsafe_code)]

use std::env;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

use clap::Parser;
use droidloom_applications::{CatalogPaths, ControlCatalog, reconcile, remove_managed};
use droidloom_supervisor::control::{ControlRequest, DEFAULT_CONTROL_SOCKET, request};

const DEFAULT_REFRESH_SECONDS: u64 = 30;

#[cfg(test)]
mod cli_tests {
    use super::*;

    #[test]
    fn working_parent_has_one_source_owned_entry_without_caller_plan_arguments() {
        let args = ["apps", "--owned-working-qualification"];
        assert!(Cli::try_parse_from(args).is_ok());
        assert!(Cli::try_parse_from(["apps", "--owned-working-qualification", "a"]).is_err());
        assert!(Cli::try_parse_from(["apps", "--owned-physical-plan-sha256", "a"]).is_err());
        for extra in [
            vec![
                "--physical-application-plan",
                "/other",
                "--expect-physical-plan-sha256",
                "sha",
            ],
            vec!["--socket", "/other"],
            vec!["--user", "1"],
            vec!["--once"],
            vec!["--remove-managed"],
            vec!["--expect-app-count", "39"],
            vec![
                "--owned-leaf-profile",
                "gallery",
                "--owned-leaf-plan-sha256",
                "sha",
            ],
            vec![
                "--runtime-plan",
                "/other",
                "--expect-runtime-plan-sha256",
                "sha",
                "--expect-app-count",
                "39",
            ],
            vec!["--release-check", "/other"],
        ] {
            let mut combined = args.to_vec();
            combined.extend(extra);
            assert!(Cli::try_parse_from(combined).is_err());
        }
    }

    #[test]
    fn physical_case_execution_uses_only_its_complete_source_owned_plan() {
        assert!(Cli::try_parse_from(["apps", "--physical-application-plan", "/plan"]).is_err());
        assert!(Cli::try_parse_from(["apps", "--expect-physical-plan-sha256", "sha"]).is_err());
        let args = [
            "apps",
            "--physical-application-plan",
            "/plan",
            "--expect-physical-plan-sha256",
            "sha",
        ];
        assert!(Cli::try_parse_from(args).is_ok());
        for extra in [
            vec!["--expect-app-count", "38"],
            vec!["--socket", "/other"],
            vec!["--user", "1"],
            vec!["--once"],
            vec!["--remove-managed"],
            vec![
                "--runtime-plan",
                "/other",
                "--expect-runtime-plan-sha256",
                "sha",
                "--expect-app-count",
                "39",
            ],
            vec!["--release-check", "/manifest"],
        ] {
            let mut combined = args.to_vec();
            combined.extend(extra);
            assert!(Cli::try_parse_from(combined).is_err());
        }
    }

    #[test]
    fn preparation_requires_external_intent_and_count_and_cannot_execute_other_actions() {
        assert!(Cli::try_parse_from(["apps", "--prepare-runtime-plan", "/intent"]).is_err());
        assert!(Cli::try_parse_from(["apps", "--expect-preparation-sha256", "pin"]).is_err());
        let args = [
            "apps",
            "--prepare-runtime-plan",
            "/intent",
            "--expect-preparation-sha256",
            "pin",
            "--expect-app-count",
            "39",
        ];
        assert!(Cli::try_parse_from(args).is_ok());
        let mut socket = args.to_vec();
        socket.extend(["--socket", "/socket"]);
        assert!(Cli::try_parse_from(socket).is_ok());
        for extra in [
            vec!["--once"],
            vec!["--user", "0"],
            vec!["--refresh-seconds", "30"],
            vec!["--remove-managed"],
            vec!["--inspect-package", "org.mozilla.firefox"],
            vec!["--inspect-contacts-fixture"],
            vec![
                "--runtime-plan",
                "/plan",
                "--expect-runtime-plan-sha256",
                "pin",
            ],
            vec![
                "--owned-leaf-profile",
                "gallery",
                "--owned-leaf-plan-sha256",
                "pin",
            ],
            vec![
                "--adopt-native-leaf-release",
                "/adoption",
                "--expect-native-adoption-sha256",
                "pin",
            ],
        ] {
            let mut combined = args.to_vec();
            combined.extend(extra);
            assert!(Cli::try_parse_from(combined).is_err());
        }
    }

    #[test]
    fn owned_unit_entry_requires_both_fixed_profile_and_content_pin_without_other_actions() {
        assert!(Cli::try_parse_from(["apps", "--owned-leaf-profile", "gallery"]).is_err());
        assert!(Cli::try_parse_from(["apps", "--owned-leaf-plan-sha256", "pin"]).is_err());
        let args = [
            "apps",
            "--owned-leaf-profile",
            "gallery",
            "--owned-leaf-plan-sha256",
            "pin",
        ];
        assert!(Cli::try_parse_from(args).is_ok());
        for extra in [
            vec!["--once"],
            vec!["--socket", "/other"],
            vec!["--expect-app-count", "1"],
            vec!["--inspect-package", "com.android.gallery3d"],
            vec!["--remove-managed"],
        ] {
            let mut changed = args.to_vec();
            changed.extend(extra);
            assert!(Cli::try_parse_from(changed).is_err());
        }
        assert!(
            Cli::try_parse_from([
                "apps",
                "--owned-leaf-profile",
                "arbitrary",
                "--owned-leaf-plan-sha256",
                "pin"
            ])
            .is_err()
        );
    }

    #[test]
    fn native_adoption_requires_an_explicit_intent_pin_and_excludes_runtime_actions() {
        assert!(Cli::try_parse_from(["apps", "--adopt-native-leaf-release", "/intent"]).is_err());
        let args = [
            "apps",
            "--adopt-native-leaf-release",
            "/intent",
            "--expect-native-adoption-sha256",
            "pin",
        ];
        assert!(Cli::try_parse_from(args).is_ok());
        for extra in [
            vec!["--once"],
            vec!["--socket", "/other"],
            vec!["--inspect-contacts-fixture"],
            vec!["--user", "0"],
            vec!["--remove-managed"],
        ] {
            let mut combined = args.to_vec();
            combined.extend(extra);
            assert!(Cli::try_parse_from(combined).is_err());
        }
    }

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
    fn contacts_fixture_inspection_excludes_mutation_other_operations_and_user_override() {
        assert!(
            Cli::try_parse_from(["apps", "--inspect-contacts-fixture", "--socket", "/socket"])
                .is_ok()
        );
        for extra in [
            vec!["--once"],
            vec!["--remove-managed"],
            vec!["--user", "0"],
            vec!["--inspect-package", "com.android.contacts"],
            vec!["--release-results", "/results"],
            vec!["--refresh-seconds", "30"],
        ] {
            let mut args = vec!["apps", "--inspect-contacts-fixture"];
            args.extend(extra);
            assert!(Cli::try_parse_from(args).is_err());
        }
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
#[command(group(clap::ArgGroup::new("release_action").args(["release_check", "runtime_plan", "prepare_runtime_plan", "verify_material_identity"])))]
struct Cli {
    /// Prepare and capture the normal working qualification as its actual fixed parent.
    #[arg(long, conflicts_with_all = ["physical_application_plan", "expect_physical_plan_sha256",
        "verify_material_identity", "prepare_material_admission", "owned_leaf_profile",
        "adopt_native_leaf_release", "release_check", "runtime_plan", "prepare_runtime_plan",
        "inspect_package", "inspect_contacts_fixture", "remove_managed", "socket", "user",
        "once", "refresh_seconds", "expect_app_count"])]
    owned_working_qualification: bool,
    /// Execute the source-owned complete physical case roster on the current working copy.
    #[arg(long, requires = "expect_physical_plan_sha256",
        conflicts_with_all = ["verify_material_identity","prepare_material_admission",
            "owned_leaf_profile","adopt_native_leaf_release","release_check","runtime_plan",
            "prepare_runtime_plan","inspect_package","inspect_contacts_fixture",
            "remove_managed","socket","user","once","refresh_seconds","expect_app_count"])]
    physical_application_plan: Option<PathBuf>,
    /// Whole input-plan pin; it cannot change the compiled package/case/gate roster.
    #[arg(long, requires = "physical_application_plan")]
    expect_physical_plan_sha256: Option<String>,
    /// Verify live installed material identity only; never execute routes in the plan.
    #[arg(long, requires_all = ["expect_identity_plan_sha256", "expect_app_count"],
        conflicts_with_all = ["owned_leaf_profile", "adopt_native_leaf_release", "release_check",
        "runtime_plan", "prepare_runtime_plan", "prepare_material_admission", "inspect_package",
        "inspect_contacts_fixture", "remove_managed", "user", "once", "refresh_seconds"])]
    verify_material_identity: Option<PathBuf>,
    /// Exact complete runtime plan used only for its identity inputs.
    #[arg(long, requires = "verify_material_identity")]
    expect_identity_plan_sha256: Option<String>,
    /// Prepare a normal material admission row for source review; never admits or runs Android.
    #[arg(long, requires = "expect_material_admission_sha256",
        conflicts_with_all = ["owned_leaf_profile", "adopt_native_leaf_release", "release_check",
        "runtime_plan", "prepare_runtime_plan", "inspect_package", "inspect_contacts_fixture",
        "remove_managed", "socket", "user", "once", "refresh_seconds", "expect_app_count"])]
    prepare_material_admission: Option<PathBuf>,
    /// Exact candidate input pin; this cannot extend the source-owned admission table.
    #[arg(long, requires = "prepare_material_admission")]
    expect_material_admission_sha256: Option<String>,
    /// Run one content-addressed root plan in its exact installed owned unit.
    #[arg(long, value_parser = ["calendar-reminder", "gallery", "settings-pages"], requires = "owned_leaf_plan_sha256",
        conflicts_with_all = ["adopt_native_leaf_release", "release_check", "runtime_plan", "inspect_package", "inspect_contacts_fixture", "remove_managed", "socket", "user", "once", "refresh_seconds", "expect_app_count"])]
    owned_leaf_profile: Option<String>,
    /// Exact root request and instance identity; no arbitrary path is accepted.
    #[arg(long, requires = "owned_leaf_profile")]
    owned_leaf_plan_sha256: Option<String>,
    /// Explicit root-only adoption of the pinned final CI/source pairing.
    /// Changes only its CURRENT release reference; never installs or runs Android.
    #[arg(long, requires = "expect_native_adoption_sha256", conflicts_with_all = ["release_check", "runtime_plan", "inspect_package", "inspect_contacts_fixture", "remove_managed", "socket", "user", "once", "refresh_seconds"])]
    adopt_native_leaf_release: Option<PathBuf>,
    /// Independent SHA-256 of the root-owned adoption intent.
    #[arg(long, requires = "adopt_native_leaf_release")]
    expect_native_adoption_sha256: Option<String>,
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
    /// Observe the fixed Contacts fixture's empty provider baseline in the current Ready tree.
    /// This reads only; it does not qualify UI creation, edit, search, delete, or account topology.
    #[arg(long, conflicts_with_all = ["inspect_package", "runtime_plan", "release_check", "remove_managed", "once", "refresh_seconds", "user"])]
    inspect_contacts_fixture: bool,
    /// Execute explicit per-app runtime routing; unsupported and pending gates remain incomplete.
    #[arg(long, requires_all = ["expect_runtime_plan_sha256", "expect_app_count"], conflicts_with_all = ["inspect_package", "release_check", "remove_managed", "once", "refresh_seconds", "user"])]
    runtime_plan: Option<PathBuf>,
    /// Independently reviewed complete runtime plan hash.
    #[arg(long, requires = "runtime_plan")]
    expect_runtime_plan_sha256: Option<String>,
    /// Bind reviewed source materials to live PM/launcher observations without launching apps.
    #[arg(long, value_name = "INTENT", requires_all = ["expect_preparation_sha256", "expect_app_count"],
        conflicts_with_all = ["owned_leaf_profile", "adopt_native_leaf_release", "inspect_package", "inspect_contacts_fixture", "remove_managed", "once", "refresh_seconds", "user"])]
    prepare_runtime_plan: Option<PathBuf>,
    /// Independently reviewed intent pin, including all source/Main/cell/gate bindings.
    #[arg(long, requires = "prepare_runtime_plan")]
    expect_preparation_sha256: Option<String>,
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
    droidloom_supervisor::control::physical_qualification_channel::admit_working_entry(
        &std::env::args_os().skip(1).collect::<Vec<_>>(),
    )?;
    let cli = Cli::parse();
    if cli.owned_working_qualification {
        let owner=droidloom_supervisor::control::physical_qualification_channel::WorkingQualificationOwner::acquire()?;
        droidloom_applications::prepare_owned_physical_plan(&owner)?;
        let captured = owner.capture()?;
        captured.guard()?;
        let receipt = captured.write_receipt()?;
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "schema":"droidloom.physical-application-parent-completed.v1",
                "receipt":receipt, "actual_capture":captured.observation()?,
                "parent_unit_retirement_pending":true, "production_ready":false,
            }))?
        );
        captured.guard()?;
        return Ok(());
    }
    if let Some(path) = &cli.physical_application_plan {
        let outcome = droidloom_applications::runtime_plan::run_physical_files(
            path,
            cli.expect_physical_plan_sha256
                .as_deref()
                .ok_or("physical input pin missing")?,
        )?;
        return match outcome.into_complete() {
            Ok(mut complete) => {
                complete.write_owned_completion()?;
                Ok(())
            }
            Err(partial) => {
                println!("{}", serde_json::to_string_pretty(partial.summary())?);
                Err(
                    "complete physical application qualification retains pending or failed gates"
                        .into(),
                )
            }
        };
    }
    if let Some(path) = &cli.prepare_material_admission {
        let candidate = droidloom_applications::runtime_plan::prepare_identity_material_admission(
            path,
            cli.expect_material_admission_sha256
                .as_deref()
                .ok_or("missing normal material admission candidate pin")?,
        )?;
        println!("{}", serde_json::to_string_pretty(&candidate)?);
        return Ok(());
    }
    if let Some(path) = &cli.verify_material_identity {
        let report = droidloom_applications::runtime_plan::verify_material_identity_files(
            &cli.socket,
            path,
            cli.expect_identity_plan_sha256
                .as_deref()
                .ok_or("missing complete identity plan pin")?,
            cli.expect_app_count
                .ok_or("missing complete selected count")?,
        )?;
        println!("{}", serde_json::to_string_pretty(&report)?);
        return Err("complete identity, business and activation acceptance remain incomplete; inspect every selected row".into());
    }
    if let Some(profile) = &cli.owned_leaf_profile {
        droidloom_applications::runtime_plan::run_owned_leaf_plan(
            profile,
            cli.owned_leaf_plan_sha256
                .as_deref()
                .ok_or("missing owned root plan pin")?,
        )?;
        return Err("application acceptance remains incomplete".into());
    }
    if let Some(path) = &cli.adopt_native_leaf_release {
        let result = droidloom_applications::runtime_plan::adopt_native_leaf_release(
            path,
            cli.expect_native_adoption_sha256
                .as_deref()
                .ok_or("missing explicit native adoption intent pin")?,
        )?;
        println!("{}", serde_json::to_string_pretty(&result)?);
        return Ok(());
    }
    if let Some(path) = &cli.prepare_runtime_plan {
        let report = droidloom_applications::runtime_plan::prepare_files(
            &cli.socket,
            path,
            cli.expect_preparation_sha256
                .as_deref()
                .ok_or("missing preparation intent pin")?,
            cli.expect_app_count
                .ok_or("missing complete selected count")?,
        )?;
        println!("{}", serde_json::to_string_pretty(&report)?);
        return if report.bindings_complete {
            Ok(())
        } else {
            Err("runtime plan preparation retains blocked bindings; inspect every selected application in the JSON report".into())
        };
    }
    if cli.inspect_contacts_fixture {
        let contacts = droidloom_applications::runtime_plan::inspect_package(
            &cli.socket,
            "com.android.contacts",
            0,
        )?;
        let provider = droidloom_applications::runtime_plan::inspect_package(
            &cli.socket,
            "com.android.providers.contacts",
            0,
        )?;
        let response = request(
            &cli.socket,
            &ControlRequest::InspectContactsFixture { contacts, provider },
        )?;
        if !response.ok {
            return Err(response.message.into());
        }
        let observed: serde_json::Value = serde_json::from_str(
            response
                .diagnostics
                .as_deref()
                .ok_or("Contacts baseline response omitted the actual observation")?,
        )?;
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "operation": "inspect_owned_contacts_fixture_baseline",
                "observation": observed,
                "production_ready": false, "runtime_qualified": false,
                "whole_application_qualified": false, "app_launches": 0,
                "contact_mutations": 0
            }))?
        );
        return Ok(());
    }
    if let Some(package) = &cli.inspect_package {
        let (observed, image_custody) =
            droidloom_applications::runtime_plan::inspect_package_with_custody(
                &cli.socket,
                package,
                cli.user,
            )?;
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "operation": "inspect_installed_application", "observation": observed,
                "image_custody": image_custody, "data_continuity_qualified": false,
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

#[cfg(test)]
mod identity_admission_cli_tests {
    use super::*;
    #[test]
    fn preparation_requires_its_pin_and_never_combines_with_runtime_operations() {
        assert!(Cli::try_parse_from(["apps", "--prepare-material-admission", "/input"]).is_err());
        let hash = "a".repeat(64);
        assert!(
            Cli::try_parse_from([
                "apps",
                "--prepare-material-admission",
                "/input",
                "--expect-material-admission-sha256",
                &hash
            ])
            .is_ok()
        );
        assert!(
            Cli::try_parse_from([
                "apps",
                "--prepare-material-admission",
                "/input",
                "--expect-material-admission-sha256",
                &hash,
                "--inspect-package",
                "org.example.app"
            ])
            .is_err()
        );
        assert!(
            Cli::try_parse_from([
                "apps",
                "--prepare-material-admission",
                "/input",
                "--expect-material-admission-sha256",
                &hash,
                "--remove-managed"
            ])
            .is_err()
        );
    }
}
