//! One complete, verified Droidloom build and activation transaction.
mod android;
mod assemble;
mod bundle;
mod dependencies;
mod image_policy;
mod install;
mod licenses;
mod native_bridge;
mod native_engine;
mod package;
mod python;
mod util;
use clap::{Parser, Subcommand};
use std::{fs, path::PathBuf, process::Command};
use util::*;
#[derive(Parser)]
#[command(
    version,
    about = "Build, verify, install and restart all Droidloom components"
)]
struct Args {
    /// Droidloom checkout (remembered automatically after installation).
    #[arg(long, global = true)]
    source: Option<PathBuf>,
    /// Delete this updater's build outputs before compiling.
    #[arg(long)]
    clean: bool,
    #[arg(long, hide = true)]
    bootstrapped: bool,
    /// Build and verify a complete bundle without installing it.
    #[arg(long)]
    build_only: bool,
    /// Maximum parallel jobs, capped at available CPUs minus two.
    #[arg(short = 'j', long)]
    jobs: Option<usize>,
    #[command(subcommand)]
    command: Option<Action>,
}
#[derive(Subcommand)]
enum Action {
    #[command(hide = true)]
    NativeBridgeImage {
        #[arg(long)]
        image: PathBuf,
        #[arg(long)]
        destination: PathBuf,
        #[arg(long)]
        product: PathBuf,
        #[arg(long)]
        source_lock: PathBuf,
    },
    /// Rebuild the ARM64 translator in an already prepared Android workspace.
    NativeBridgeBuild {
        /// Use an existing package build workspace (containing aosp-source).
        #[arg(long)]
        work: Option<PathBuf>,
    /// Also build Teto's ARM64 host regression suite.
        #[arg(long)]
        tests: bool,
    },
    /// Build only NativeBridge targets, deferring missing modules to Ninja errors.
    TargetClosureBuild {
        /// Use an existing package build workspace (containing aosp-source).
        #[arg(long)]
        work: Option<PathBuf>,
        /// Also build ARM64 host regressions; this does not run those tests.
        #[arg(long)]
        tests: bool,
    },
    /// Build only the Android ARM64 translation engine; does not install it.
    NativeEngineBuild {
        /// Existing package workspace containing aosp-source.
        #[arg(long)]
        work: PathBuf,
        /// Absolute output directory; defaults to WORK/android-native-engine-out.
        /// Use a new directory to exclude objects from an older cache policy.
        #[arg(long)]
        out: Option<PathBuf>,
        /// Also build the real x86_64 ARM64-guest host tests and their data.
        /// This does not execute those tests.
        #[arg(long)]
        tests: bool,
    },
    /// Build the complete AIDL audio APEX with strict dependency validation.
    /// Does not install artifacts or start services.
    AudioApexBuild {
        /// Existing package build workspace (containing aosp-source).
        #[arg(long)]
        work: PathBuf,
    },
    /// Build the original final vendor policy on the fixed Audio source profile.
    /// Does not build an APEX, install a policy or load SELinux policy.
    VendorPolicyBuild {
        #[arg(long)]
        work: PathBuf,
    },
    /// Build native vendor SELinux policy, contexts, version, VINTF declarations and checkvintf.
    VendorPolicyBundleBuild {
        #[arg(long)]
        work: PathBuf,
    },
    /// Build the original IntentResolver module with its official caller-package security patch.
    /// Does not install the APK or qualify production signing.
    #[command(name = "intentresolver-security-build")]
    IntentResolverSecurityBuild {
        #[arg(long)]
        work: PathBuf,
    },
    /// Build swcodec and the original AAC regression with the complete official security fix.
    /// Does not install the APEX or qualify runtime and signing.
    #[command(name = "aac-security-build")]
    AacSecurityBuild {
        #[arg(long)]
        work: PathBuf,
    },
    /// Restore an interrupted source projection under the normal two workspace locks.
    /// Does not compile, install, bootstrap dependencies, or start services.
    RecoverSource {
        #[arg(long)]
        work: PathBuf,
    },
    /// Build the native AMD allocator candidate without installing anything.
    MinigbmBuild {
        #[arg(long)]
        work: PathBuf,
    },
    #[command(hide = true)]
    PruneDesktopImage {
        #[arg(long)]
        image: PathBuf,
        #[arg(long)]
        destination: PathBuf,
        #[arg(long)]
        vendor_properties: PathBuf,
    },
    /// Compile and stage a portable pacman payload; does not install or start services.
    PackageStage {
        #[arg(long)]
        work: PathBuf,
        #[arg(long)]
        destination: PathBuf,
        #[arg(long)]
        clean: bool,
        #[arg(long)]
        jobs: usize,
    },
    /// Show the complete build plan without changing anything.
    Plan,
    /// Verify an already built bundle.
    Verify { payload: PathBuf },
    /// Privileged activation worker; normally invoked automatically through polkit.
    #[command(hide = true)]
    Apply {
        payload: PathBuf,
        #[arg(long)]
        uid: u32,
    },
    #[command(hide = true)]
    Recover {
        #[arg(long)]
        uid: u32,
    },
}
fn repository(explicit: Option<PathBuf>) -> Result<PathBuf> {
    let path = if let Some(p) = explicit {
        p
    } else {
        let current = std::env::current_dir()?;
        if let Some(p) = current
            .ancestors()
            .find(|p| p.join("tools/droidloom-update/Cargo.toml").exists())
        {
            p.to_owned()
        } else {
            let config: serde_json::Value = serde_json::from_slice(
                &fs::read("/usr/lib/droidloom/active/etc/droidloom/update.json")
                    .map_err(|_| "run the initial update inside the Droidloom checkout")?,
            )?;
            PathBuf::from(
                config["source"]
                    .as_str()
                    .ok_or("invalid updater configuration")?,
            )
        }
    }
    .canonicalize()?;
    if !path.join("tools/droidloom-update/Cargo.toml").is_file() {
        return fail("not a Droidloom checkout");
    }
    Ok(path)
}
fn selected_build_out(command: Option<&Action>, work: &std::path::Path) -> Result<PathBuf> {
    if matches!(command, Some(Action::VendorPolicyBuild { .. } | Action::VendorPolicyBundleBuild { .. } | Action::IntentResolverSecurityBuild { .. } | Action::AacSecurityBuild { .. })) {
        let out = work.join(match command {
            Some(Action::VendorPolicyBundleBuild { .. }) => "android-user-vendor-policy-bundle-out",
            Some(Action::IntentResolverSecurityBuild { .. }) => "android-user-intentresolver-security-out",
            Some(Action::AacSecurityBuild { .. }) => "android-user-aac-security-out",
            _ => "android-user-vendor-policy-out",
        });
        if !work.is_absolute() {
            return fail("vendor policy workspace must be absolute");
        }
        for path in out.ancestors() {
            match fs::symlink_metadata(path) {
                Ok(meta) if !meta.is_dir() || meta.file_type().is_symlink() =>
                    return fail("vendor policy output and parents must be real directories"),
                Ok(_) => {},
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {},
                Err(error) => return Err(error.into()),
            }
        }
        return Ok(out);
    }
    if let Some(Action::NativeEngineBuild { out: Some(out), .. }) = command {
        let source = work.join("aosp-source");
        if !out.is_absolute()
            || out.components().any(|part| matches!(part,
                std::path::Component::ParentDir | std::path::Component::CurDir))
            || out.starts_with(&source) || source.starts_with(out)
        {
            return fail("native-engine --out must be absolute and separate from the prepared source tree");
        }
        // Do not let an output alias redirect receipt cleanup or compilation
        // into a source tree. Missing final directories are allowed.
        for part in out.ancestors() {
            match fs::symlink_metadata(part) {
                Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() =>
                    return fail("native-engine --out and its existing parents must be real directories"),
                Ok(_) => {},
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {},
                Err(error) => return Err(error.into()),
            }
        }
        return Ok(out.clone());
    }
    Ok(work.join(match command {
        Some(Action::TargetClosureBuild { .. }) => "android-target-closure-out",
        Some(Action::AudioApexBuild { .. }) => "android-audio-closure-out",
        Some(Action::NativeEngineBuild { .. }) => "android-native-engine-out",
        Some(Action::MinigbmBuild { .. }) => "android-minigbm-out",
        _ => "android-out",
    }))
}

fn recover_source_workspace(work: &std::path::Path) -> Result<()> {
    let work = work.canonicalize()?;
    let source = work.join("aosp-source");
    let meta = fs::symlink_metadata(&source)?;
    if !meta.is_dir() || meta.file_type().is_symlink() {
        return fail("recover-source requires a real prepared aosp-source directory");
    }
    let _lock = Lock::acquire(&work.join("package-build.lock"))?;
    let _source_lock = Lock::acquire(&work.join("aosp-source-update.lock"))?;
    let journal = work.join("source-projection.json");
    if journal.exists() { android::recover(&journal, &source)?; }
    Ok(())
}

fn execute(args: Args) -> Result<()> {
    if matches!(&args.command, Some(Action::VendorPolicyBuild { .. } | Action::VendorPolicyBundleBuild { .. } | Action::IntentResolverSecurityBuild { .. } | Action::AacSecurityBuild { .. }))
        && (args.clean || args.build_only || args.bootstrapped) {
        return fail("fixed vendor policy does not accept cleanup, bundle or bootstrap options");
    }
    match &args.command {
        Some(Action::RecoverSource { work }) => {
            if args.clean || args.build_only || args.jobs.is_some() {
                return fail("recover-source does not accept build or cleanup options");
            }
            if unsafe { libc::getuid() } == 0 {
                return fail("run source recovery as the desktop user");
            }
            return recover_source_workspace(work);
        }
        Some(Action::NativeBridgeImage {
            image,
            destination,
            product,
            source_lock,
        }) => {
            return native_bridge::derive_image(image, destination, product, source_lock);
        }
        Some(Action::PruneDesktopImage {
            image,
            destination,
            vendor_properties,
        }) => {
            return image_policy::prune(image, destination, vendor_properties);
        }
        Some(Action::PackageStage {
            work,
            destination,
            clean,
            jobs,
        }) => {
            return package::stage(
                &repository(args.source.clone())?,
                work,
                destination,
                *clean,
                *jobs,
            );
        }
        Some(Action::Recover { uid }) => return install::recover(*uid),
        Some(Action::Apply { payload, uid }) => {
            return install::apply(&payload.canonicalize()?, *uid);
        }
        Some(Action::Verify { payload }) => {
            let m = bundle::verify(payload)?;
            println!(
                "Verified {} bundle, input ABI {}, source {}",
                m.architecture, m.input_abi, m.source_identity
            );
            return Ok(());
        }
        _ => {}
    }
    if args.command.is_none()
        && !args.build_only
        && std::path::Path::new("/usr/share/droidloom/package.json").exists()
    {
        return fail(
            "Droidloom is managed by pacman. Build packages with cargo run --locked -j 1 -p droidloom-package -- build, then install the printed package pair with sudo pacman -U. Sudo is needed to replace package-owned system files and update pacman's database.",
        );
    }
    let repo = repository(args.source)?;
    let arch = std::env::consts::ARCH;
    if arch != "x86_64" {
        return fail("the source builder currently requires an x86_64 Linux build host");
    }
    let product = "droidloom_x86_64";
    let package_work = match &args.command {
        Some(Action::NativeBridgeBuild {
            work: Some(work), ..
        })
        | Some(Action::TargetClosureBuild {
            work: Some(work), ..
        })
        | Some(Action::AudioApexBuild { work })
        | Some(Action::VendorPolicyBuild { work })
        | Some(Action::VendorPolicyBundleBuild { work })
        | Some(Action::IntentResolverSecurityBuild { work })
        | Some(Action::AacSecurityBuild { work })
        | Some(Action::NativeEngineBuild { work, .. })
        | Some(Action::MinigbmBuild { work }) => Some(work.canonicalize()?),
        _ => None,
    };
    let work = package_work
        .clone()
        .unwrap_or_else(|| repo.join(".work/update"));
    let source = if package_work.is_some() {
        work.join("aosp-source")
    } else {
        repo.join(".work/aosp-m2-source")
    };
    let out = selected_build_out(args.command.as_ref(), &work)?;
    let cargo = work.join("cargo");
    if matches!(args.command, Some(Action::Plan)) {
        println!(
            "Source: {}\nCache: {}\nAndroid product: {product}\nHost: supervisor, ctl, daemon, Wayland, applications, doctor, updater\nAndroid: {}\nPinned inputs: system, system_ext, product, Mesa\nActivation: verify -> stage -> stop Droidloom -> switch complete release -> start -> check Android catalog\nFailure: restore previous release\nBoot autostart: disabled",
            repo.display(),
            work.display(),
            android::TARGETS.join(", ")
        );
        return Ok(());
    }
    let uid = unsafe { libc::getuid() };
    if uid == 0 {
        return fail(
            "run as the desktop user; administrator authentication is requested only for installation",
        );
    }
    let capacity = std::thread::available_parallelism()
        .map(|n| n.get().saturating_sub(2).max(1))
        .unwrap_or(1);
    let jobs = args.jobs.unwrap_or(capacity).min(capacity);
    if jobs == 0 {
        return fail("jobs must be positive");
    }
    let _lock = Lock::acquire(&work.join(if package_work.is_some() {
        "package-build.lock"
    } else {
        "update.lock"
    }))?;
    let _source_lock = Lock::acquire(&if package_work.is_some() {
        work.join("aosp-source-update.lock")
    } else {
        repo.join(".work/aosp-source-update.lock")
    })?;
    // A prepared package workspace runs inside the rootless builder, which
    // supplies build tools and does not run host systemd or install services.
    if package_work.is_none() {
        dependencies::ensure()?;
    }
    if work.join("source-projection.json").exists() {
        android::recover(&work.join("source-projection.json"), &source)?;
    }
    if let Some(Action::TargetClosureBuild { tests, .. }) = args.command {
        eprintln!("Building only the NativeBridge target closure; full-product validation and runtime tests remain separate.");
        return android::build_native_bridge_target_closure(
            &repo, &source, &out, &work, product, jobs, tests,
        );
    }
    if matches!(args.command, Some(Action::VendorPolicyBundleBuild { .. })) {
        eprintln!("Building native vendor policy, contexts, versions and VINTF declarations; compatibility qualification follows the actual artifacts.");
        return android::build_vendor_policy_bundle_on_audio_source(&repo,&source,&out,&work,product,jobs);
    }
    if matches!(args.command, Some(Action::IntentResolverSecurityBuild { .. })) {
        return android::build_intentresolver_security_on_audio_source(
            &repo, &source, &out, &work, product, jobs,
        );
    }
    if matches!(args.command, Some(Action::AacSecurityBuild { .. })) {
        return android::build_aac_security_on_audio_source(
            &repo, &source, &out, &work, product, jobs,
        );
    }
    if matches!(args.command, Some(Action::VendorPolicyBuild { .. })) {
        eprintln!("Building the original final vendor_sepolicy.cil with the exact Audio source profile; APEX, selected-cohort policy compatibility and runtime remain separate.");
        return android::build_vendor_policy_on_audio_source(
            &repo, &source, &out, &work, product, jobs,
        );
    }
    if matches!(args.command, Some(Action::AudioApexBuild { .. })) {
        eprintln!("Building the AIDL audio APEX target closure with PCM bridge patches; runtime audio verification remains separate.");
        return android::build_audio_apex_target_closure(
            &repo, &source, &out, &work, product, jobs,
        );
    }
    if let Some(Action::NativeEngineBuild { tests, .. }) = args.command {
        eprintln!("Building only the Android translation engine and optional host-test artifacts; installation and runtime qualification remain separate.");
        return android::build_native_engine_target_closure(
            &repo, &source, &out, &work, product, jobs, tests,
        );
    }
    if matches!(args.command, Some(Action::MinigbmBuild { .. })) {
        return android::build_minigbm_target_closure(
            &repo, &source, &out, &work, product, jobs,
        );
    }
    if let Some(Action::NativeBridgeBuild { tests, .. }) = args.command {
        return android::build_targets(
            &repo,
            &source,
            &out,
            &work,
            product,
            jobs,
            if tests {
                &["droidloom-native-bridge", "berberis_arm64_host_tests"]
            } else {
                &["droidloom-native-bridge"]
            },
        );
    }
    if args.clean {
        for path in [&out, &cargo, &work.join("mesa-tools"), &work.join("ccache")] {
            if path.exists() {
                fs::remove_dir_all(path)?;
            }
        }
    }
    let identity = bundle::source_identity(&repo)?;
    eprintln!("Building complete Droidloom release from {identity}");
    eprintln!("Compiler budget: {jobs} parallel jobs; two logical CPUs reserved");
    let mut host_build = Command::new("cargo");
    host_build
        .current_dir(&repo)
        .env("CARGO_TARGET_DIR", &cargo)
        .args(["build", "--locked", "--release"])
        .arg(format!("-j{jobs}"));
    for package in assemble::HOST_PACKAGES {
        host_build.arg("-p").arg(package);
    }
    run_build(&mut host_build)?;
    let fresh = cargo.join("release/droidloom-update");
    if !args.bootstrapped {
        // The updater is part of the build too. Use its new orchestration in this update.
        // Release locks before exec so the replacement can acquire them normally.
        drop(_source_lock);
        drop(_lock);
        use std::os::unix::process::CommandExt;
        let mut command = Command::new(fresh);
        command
            .arg("--bootstrapped")
            .arg("--source")
            .arg(&repo)
            .arg("--jobs")
            .arg(jobs.to_string());
        if args.build_only {
            command.arg("--build-only");
        }
        // --clean was already applied; repeating it would cause an endless bootstrap.
        return Err(command.exec().into());
    }
    if !args.build_only && std::path::Path::new("/usr/lib/droidloom/transaction.json").exists() {
        run(Command::new("pkexec")
            .arg(&fresh)
            .arg("recover")
            .arg("--uid")
            .arg(uid.to_string()))?;
    }
    let base = assemble::prepare_inputs(&repo, &work, arch)?;
    python::prepare(&repo, &work)?;
    assemble::mesa_tools(&work, jobs)?;
    android::build(&repo, &source, &out, &work, product, jobs)?;
    let staging = tempfile::Builder::new()
        .prefix("bundle-")
        .tempdir_in(&work)?;
    assemble::assemble(
        &repo,
        &work,
        &base,
        &out.join("target/product").join(product),
        &cargo.join("release"),
        staging.path(),
        uid,
    )?;
    let id = bundle::seal(staging.path(), identity)?;
    bundle::verify(staging.path())?;
    let payload = work.join(format!("release-{id}"));
    if payload.exists() {
        bundle::verify(&payload)?;
    } else {
        fs::rename(staging.path(), &payload)?;
    }
    println!("Verified bundle: {}", payload.display());
    if !args.build_only {
        run(Command::new("pkexec")
            .arg(payload.join("usr/bin/droidloom-update"))
            .arg("apply")
            .arg(&payload)
            .arg("--uid")
            .arg(uid.to_string()))?;
    }
    Ok(())
}
fn main() {
    if let Err(error) = execute(Args::parse()) {
        eprintln!("Droidloom update failed: {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn vendor_policy_bundle_cli_is_fixed_without_source_target_or_variant_overrides() {
        let valid=["droidloom-update","vendor-policy-bundle-build","--work","/not-executed"];
        let args=Args::try_parse_from(valid).unwrap();assert!(matches!(args.command,Some(Action::VendorPolicyBundleBuild{..})));
        assert_eq!(selected_build_out(args.command.as_ref(),std::path::Path::new("/not-executed")).unwrap(),PathBuf::from("/not-executed/android-user-vendor-policy-bundle-out"));
        assert!(Args::try_parse_from(["droidloom-update","vendor-policy-bundle-build"]).is_err());
        for extra in [&["vendorimage"][..],&["selinux_policy_vendor"][..],&["--out","/another"][..],&["--variant","userdebug"][..],&["--source-lock","/another"][..]] {let mut argv=valid.to_vec();argv.extend_from_slice(extra);assert!(Args::try_parse_from(argv).is_err());}
        for option in ["--clean","--build-only","--bootstrapped"] {let args=Args::try_parse_from(["droidloom-update",option,"vendor-policy-bundle-build","--work","/not-executed"]).unwrap();assert!(execute(args).unwrap_err().to_string().contains("does not accept cleanup"));}
    }

    #[test]
    fn vendor_policy_bundle_output_rejects_directory_and_ancestor_aliases() {
        use std::os::unix::fs::symlink;
        let d=tempfile::tempdir().unwrap();let work=d.path().join("work");fs::create_dir(&work).unwrap();
        let args=Args::try_parse_from(["droidloom-update","vendor-policy-bundle-build","--work",work.to_str().unwrap()]).unwrap();
        let output=work.join("android-user-vendor-policy-bundle-out");symlink(&work,&output).unwrap();assert!(selected_build_out(args.command.as_ref(),&work).is_err());fs::remove_file(output).unwrap();
        let alias=d.path().join("alias");symlink(&work,&alias).unwrap();assert!(selected_build_out(args.command.as_ref(),&alias).is_err());
        assert!(selected_build_out(args.command.as_ref(),std::path::Path::new("relative-work")).is_err());
    }

    use super::*;

    #[test]
    fn intentresolver_security_cli_rejects_widening_and_output_aliases() {
        let d=tempfile::tempdir().unwrap();let work=d.path();
        let valid=["droidloom-update","intentresolver-security-build","--work",work.to_str().unwrap()];
        let args=Args::try_parse_from(valid).unwrap();
        assert!(matches!(args.command,Some(Action::IntentResolverSecurityBuild { .. })));
        assert_eq!(selected_build_out(args.command.as_ref(),work).unwrap(),work.join("android-user-intentresolver-security-out"));
        for extra in [&["services"][..], &["--out","/another"][..], &["--variant","eng"][..], &["--source-lock","/other"][..]] {
            let mut argv=valid.to_vec();argv.extend_from_slice(extra);assert!(Args::try_parse_from(argv).is_err());
        }
        for option in ["--clean","--build-only","--bootstrapped"] {
            let args=Args::try_parse_from(["droidloom-update",option,"intentresolver-security-build","--work",work.to_str().unwrap()]).unwrap();
            assert!(execute(args).unwrap_err().to_string().contains("does not accept cleanup"));
        }
        std::os::unix::fs::symlink(work,work.join("android-user-intentresolver-security-out")).unwrap();
        assert!(selected_build_out(args.command.as_ref(),work).is_err());
    }

    #[test]
    fn aac_security_cli_rejects_widening_and_output_aliases() {
        let d = tempfile::tempdir().unwrap();
        let work = d.path();
        let valid = ["droidloom-update", "aac-security-build", "--work", work.to_str().unwrap()];
        let args = Args::try_parse_from(valid).unwrap();
        assert!(matches!(args.command, Some(Action::AacSecurityBuild { .. })));
        let out = work.join("android-user-aac-security-out");
        assert_eq!(selected_build_out(args.command.as_ref(), work).unwrap(), out);
        for extra in [&["services"][..], &["--out", "/another"][..], &["--variant", "eng"][..], &["--source-lock", "/other"][..]] {
            let mut argv = valid.to_vec();
            argv.extend_from_slice(extra);
            assert!(Args::try_parse_from(argv).is_err());
        }
        for option in ["--clean", "--build-only", "--bootstrapped"] {
            let args = Args::try_parse_from(["droidloom-update", option, "aac-security-build", "--work", work.to_str().unwrap()]).unwrap();
            assert!(execute(args).unwrap_err().to_string().contains("does not accept cleanup"));
        }
        std::os::unix::fs::symlink(work, out).unwrap();
        assert!(selected_build_out(args.command.as_ref(), work).is_err());
    }

    #[test]
    fn vendor_policy_cli_is_fixed_and_has_no_cleanup_or_target_override() {
        let valid = ["droidloom-update", "vendor-policy-build", "--work", "/not-executed"];
        let args = Args::try_parse_from(valid).unwrap();
        assert!(matches!(args.command, Some(Action::VendorPolicyBuild { .. })));
        assert_eq!(selected_build_out(args.command.as_ref(), std::path::Path::new("/not-executed")).unwrap(),
            PathBuf::from("/not-executed/android-user-vendor-policy-out"));
        assert!(Args::try_parse_from(["droidloom-update", "vendor-policy-build"]).is_err());
        for extra in [&["services"][..], &["vendor_sepolicy.cil"][..], &["--out", "/another-out"][..],
                      &["--variant", "userdebug"][..], &["--source-lock", "/another-lock"][..]] {
            let mut argv = valid.to_vec(); argv.extend_from_slice(extra);
            assert!(Args::try_parse_from(argv).is_err());
        }
        for option in ["--clean", "--build-only", "--bootstrapped"] {
            let argv = ["droidloom-update", option, "vendor-policy-build", "--work", "/not-executed"];
            let args = Args::try_parse_from(argv).unwrap();
            assert!(execute(args).unwrap_err().to_string().contains("does not accept cleanup"));
        }
    }

    #[cfg(unix)]
    #[test]
    fn vendor_policy_output_rejects_aliases_and_uses_existing_two_lock_recovery() {
        let d = tempfile::tempdir().unwrap(); let work = d.path();
        let args = Args::try_parse_from(["droidloom-update", "vendor-policy-build", "--work", work.to_str().unwrap()]).unwrap();
        let output = work.join("android-user-vendor-policy-out");
        std::os::unix::fs::symlink(work, &output).unwrap();
        assert!(selected_build_out(args.command.as_ref(), work).is_err()); fs::remove_file(&output).unwrap();
        let source = work.join("aosp-source"); fs::create_dir(&source).unwrap();
        let input = source.join("original"); fs::write(&input, b"original").unwrap();
        use std::os::unix::fs::PermissionsExt;
        let original_metadata=fs::metadata(&input).unwrap();fs::write(&input,b"projected").unwrap();
        let journal = work.join("source-projection.json");
        let raw = serde_json::to_vec(&serde_json::json!({"schema_version":2,"originals":[{"path":input,"bytes":b"original".to_vec(),"modified":original_metadata.modified().unwrap(),"permissions_mode":original_metadata.permissions().mode()}]})).unwrap();
        fs::write(&journal, &raw).unwrap();
        for name in ["package-build.lock", "aosp-source-update.lock"] {
            let held = Lock::acquire(&work.join(name)).unwrap();
            assert!(recover_source_workspace(work).is_err());
            assert_eq!(fs::read(&input).unwrap(), b"projected"); assert_eq!(fs::read(&journal).unwrap(), raw);
            drop(held);
        }
        recover_source_workspace(work).unwrap();
        assert_eq!(fs::read(&input).unwrap(), b"original"); assert!(!journal.exists()); assert!(!output.exists());
    }


    #[test]
    fn source_recovery_cli_is_explicit_and_has_no_build_path() {
        assert!(Args::try_parse_from(["droidloom-update", "recover-source"]).is_err());
        assert!(Args::try_parse_from(["droidloom-update", "recover-source", "--work", "/not-executed", "services"]).is_err());
        let args = Args::try_parse_from(["droidloom-update", "recover-source", "--work", "/not-executed"]).unwrap();
        assert!(matches!(args.command, Some(Action::RecoverSource { .. })));
        let args = Args::try_parse_from(["droidloom-update", "--clean", "recover-source", "--work", "/not-executed"]).unwrap();
        assert!(execute(args).unwrap_err().to_string().contains("does not accept build"));
    }

    #[test]
    fn source_recovery_requires_both_normal_locks_and_only_restores_journal() {
        let d = tempfile::tempdir().unwrap(); let work = d.path(); let source = work.join("aosp-source");
        fs::create_dir(&source).unwrap(); let input = source.join("original");
        fs::write(&input, b"original").unwrap();
        use std::os::unix::fs::PermissionsExt;
        let original_metadata=fs::metadata(&input).unwrap();fs::write(&input,b"projected").unwrap();let journal = work.join("source-projection.json");
        let raw = serde_json::to_vec(&serde_json::json!({"schema_version":2,"originals":[{"path":input,"bytes":b"original".to_vec(),"modified":original_metadata.modified().unwrap(),"permissions_mode":original_metadata.permissions().mode()}]})).unwrap();
        fs::write(&journal, &raw).unwrap();
        for name in ["package-build.lock", "aosp-source-update.lock"] {
            let held = Lock::acquire(&work.join(name)).unwrap();
            assert!(recover_source_workspace(work).is_err());
            assert_eq!(fs::read(&input).unwrap(), b"projected");
            assert_eq!(fs::read(&journal).unwrap(), raw); drop(held);
        }
        recover_source_workspace(work).unwrap(); assert_eq!(fs::read(&input).unwrap(), b"original");
        assert!(!journal.exists()); recover_source_workspace(work).unwrap();
        let mut entries: Vec<_> = fs::read_dir(work).unwrap().map(|x| x.unwrap().file_name()).collect(); entries.sort();
        assert_eq!(entries, ["aosp-source", "aosp-source-update.lock", "package-build.lock"].map(std::ffi::OsString::from));
    }


    #[test]
    fn native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets() {
        assert!(Args::try_parse_from(["droidloom-update", "native-engine-build"]).is_err());
        assert!(Args::try_parse_from(["droidloom-update", "native-engine-build",
            "--work", "/not-executed", "services"]).is_err());
        let args = Args::try_parse_from(["droidloom-update", "-j", "2", "native-engine-build",
            "--work", "/not-executed", "--tests"]).unwrap();
        assert!(matches!(args.command, Some(Action::NativeEngineBuild { tests: true, .. })));
    }

    #[test]
    fn native_engine_output_selector_keeps_default_or_exact_explicit_directory() {
        let work = std::path::Path::new("/prepared");
        let parse = |extra: &[&str]| {
            let mut argv = vec!["droidloom-update", "native-engine-build", "--work", "/prepared", "--tests"];
            argv.extend_from_slice(extra);
            Args::try_parse_from(argv).unwrap()
        };
        let args = parse(&[]);
        assert_eq!(selected_build_out(args.command.as_ref(), work).unwrap(),
            work.join("android-native-engine-out"));
        let args = parse(&["--out", "/prepared/android-native-engine-out-r9"]);
        assert_eq!(selected_build_out(args.command.as_ref(), work).unwrap(),
            PathBuf::from("/prepared/android-native-engine-out-r9"));
        for path in ["relative-out", "/prepared", "/prepared/aosp-source", "/prepared/aosp-source/out", "/prepared/new/../old"] {
            let args = parse(&["--out", path]);
            assert!(selected_build_out(args.command.as_ref(), work).is_err(), "{path}");
        }
        let temp = tempfile::tempdir().unwrap();
        let alias = temp.path().join("alias");
        std::os::unix::fs::symlink(temp.path(), &alias).unwrap();
        let args = parse(&["--out", alias.join("new-out").to_str().unwrap()]);
        assert!(selected_build_out(args.command.as_ref(), work).is_err());
    }
}
