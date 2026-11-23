//! Compile one portable package payload without activating a local installation.
use crate::{android, assemble, licenses, python, util::*};
use serde_json::{Value, json};
use std::{fs, os::unix::fs::symlink, path::Path, process::Command};

#[path="early_boot_package.rs"]
mod early_boot_package;

fn validate_builder(jobs: usize) -> Result<()> {
    if unsafe { libc::geteuid() } == 0 {
        return fail("package compilation must run as an ordinary build user, without sudo");
    }
    let available = std::thread::available_parallelism()?.get();
    let reserved = std::env::var("DROIDLOOM_COMPILER_CPUS_RESERVED").as_deref() == Ok("1");
    let capacity = if reserved {
        available
    } else {
        available.saturating_sub(2)
    };
    if jobs == 0 || jobs > capacity {
        return fail("package jobs must leave two logical CPUs available");
    }
    Ok(())
}

pub fn stage_container_host(repo: &Path, work: &Path, jobs: usize) -> Result<std::path::PathBuf> {
    validate_builder(jobs)?;
    fs::create_dir_all(work)?;
    let work = work.canonicalize()?;
    let _lock = Lock::acquire(&work.join("container-host-build.lock"))?;
    let target = std::env::var_os("CARGO_TARGET_DIR")
        .map(std::path::PathBuf::from)
        .filter(|p| p.is_absolute())
        .unwrap_or_else(|| work.join("cargo"));
    let mut build = Command::new("cargo");
    build
        .current_dir(repo)
        .env("CARGO_TARGET_DIR", &target)
        .args(["build", "--locked", "--release", "--jobs"])
        .arg(jobs.to_string());
    build.args(["-p", "droidloom-supervisor", "--bins"]);
    run_build(&mut build)?;
    run_build(&mut crate::container_entry_build::command(
        repo, &target, jobs,
    ))?;
    let stage = tempfile::Builder::new()
        .prefix("container-host-stage-")
        .tempdir_in(&work)?;
    production_host_payload(repo, &target.join("release"), stage.path())?;
    Ok(stage.keep())
}

pub fn stage(repo: &Path, work: &Path, destination: &Path, clean: bool, jobs: usize) -> Result<()> {
    validate_builder(jobs)?;
    fs::create_dir_all(work)?;
    let work = work.canonicalize()?;
    if !destination.is_absolute()
        || !destination.starts_with(&work)
        || destination == work
        || destination
            .components()
            .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        return fail("package destination must be a child of its private work directory");
    }
    let _lock = Lock::acquire(&work.join("package-build.lock"))?;
    let source = work.join("aosp-source");
    let out = work.join("android-out");
    let cargo = work.join("cargo");
    if work.join("source-projection.json").exists() {
        android::recover(&work.join("source-projection.json"), &source)?;
    }
    let source_ready = work.join("package-source-ready");
    if source.exists() && !source_ready.exists() {
        normalize_source_cache(&source)?;
        write(
            &source_ready,
            b"Private package source cache initialized.\n",
        )?;
    }
    if clean {
        for path in [&out, &cargo, &work.join("mesa-tools"), &work.join("ccache")] {
            if path.exists() {
                fs::remove_dir_all(path)?;
            }
        }
    }
    let mut host = Command::new("cargo");
    host.current_dir(repo)
        .env("CARGO_TARGET_DIR", &cargo)
        .args(["build", "--locked", "--release", "--jobs"])
        .arg(jobs.to_string());
    for package in assemble::HOST_PACKAGES {
        host.arg("-p").arg(package);
    }
    run_build(&mut host)?;
    run_build(&mut crate::container_entry_build::command(repo, &cargo, jobs))?;
    assemble::prepare_complete_inputs(repo, &work, "x86_64")?;
    python::prepare(repo, &work)?;
    assemble::mesa_tools(&work, jobs)?;
    android::build(repo, &source, &out, &work, "droidloom_x86_64", jobs)?;
    if !source_ready.exists() {
        write(
            &source_ready,
            b"Private package source cache initialized.\n",
        )?;
    }
    let stage = tempfile::Builder::new()
        .prefix("package-stage-")
        .tempdir_in(&work)?;
    assemble::assemble_artifacts(
        repo,
        &work,
        &out.join("target/product/droidloom_x86_64"),
        &cargo.join("release"),
        stage.path(),
    )?;
    package_layout(repo, &cargo.join("release"), stage.path())?;
    crate::coherent_images::verify_portable_package(stage.path())?;
    package_notices(repo, &work, stage.path())?;
    if destination.exists() {
        fs::remove_dir_all(destination)?;
    }
    fs::create_dir_all(
        destination
            .parent()
            .ok_or("package destination has no parent")?,
    )?;
    fs::rename(stage.path(), destination)?;
    println!("Portable package payload: {}", destination.display());
    Ok(())
}

fn normalize_source_cache(source: &Path) -> Result<()> {
    // Seeding reuses Git objects, not prior developer modifications. Only the
    // package workflow's private copy is changed; the seed checkout is untouched.
    eprintln!("Restoring pinned worktrees in the private package source cache.");
    let manifest: Value =
        serde_json::from_slice(&fs::read(source.join(".droidloom-source-manifest.json"))?)?;
    for project in manifest["plan"]["projects"]
        .as_array()
        .ok_or("source manifest has no projects")?
    {
        let path = source
            .join(
                project["path"]
                    .as_str()
                    .ok_or("source project has no path")?,
            )
            .canonicalize()?;
        if !path.starts_with(source) {
            return fail("source project escapes the private package cache");
        }
        run(Command::new("git")
            .arg("-C")
            .arg(&path)
            .args(["reset", "--hard", "HEAD"]))?;
        run(Command::new("git")
            .arg("-C")
            .arg(&path)
            .args(["clean", "-fd"]))?;
    }
    Ok(())
}

fn package_layout(repo: &Path, host: &Path, stage: &Path) -> Result<()> {
    let runtime = stage.join("runtime");
    let image = stage.join("image");
    fs::create_dir_all(image.join("usr/lib/droidloom"))?;
    fs::rename(
        stage.join("usr/lib/droidloom/runtime"),
        image.join("usr/lib/droidloom/runtime"),
    )?;
    fs::rename(
        stage.join("usr/lib/droidloom/storage"),
        image.join("usr/lib/droidloom/storage"),
    )?;
    fs::rename(
        stage.join("var/lib/droidloom/images"),
        image.join("usr/lib/droidloom/images"),
    )?;
    symlink("runtime", image.join("usr/lib/droidloom/current"))?;
    fs::remove_dir_all(stage.join("var"))?;
    fs::create_dir_all(&runtime)?;
    fs::rename(stage.join("usr"), runtime.join("usr"))?;
    // A package installation is maintained through pacman. The source updater remains
    // available in the checkout but is not installed as a second system-file owner.
    fs::remove_file(runtime.join("usr/bin/droidloom-update"))?;
    copy(
        &host.join("droidloom-package-helper"),
        &runtime.join("usr/lib/droidloom/droidloom-package-helper"),
    )?;
    mode(
        &runtime.join("usr/lib/droidloom/droidloom-package-helper"),
        0o755,
    )?;
    production_host_payload(repo, host, &runtime)?;
    let mut template: Value = serde_json::from_slice(&fs::read(
        repo.join("packaging/cell-spec-x86_64-u1000.json"),
    )?)?;
    portable_template(&mut template);
    write(
        &runtime.join("usr/share/droidloom/cell-template.json"),
        serde_json::to_vec_pretty(&template)?,
    )?;
    copy(
        &repo.join("packaging/arch/version.json"),
        &runtime.join("usr/share/droidloom/package.json"),
    )?;
    for (from, to) in [
        (
            "droidloom.service",
            "usr/lib/systemd/user/droidloom.service",
        ),
        (
            "org.droidloom.setup.policy",
            "usr/share/polkit-1/actions/org.droidloom.setup.policy",
        ),
        (
            "60-droidloom-upgrade.hook",
            "usr/share/libalpm/hooks/60-droidloom-upgrade.hook",
        ),
        (
            "60-droidloom-remove.hook",
            "usr/share/libalpm/hooks/60-droidloom-remove.hook",
        ),
        (
            "90-droidloom-installed.hook",
            "usr/share/libalpm/hooks/90-droidloom-installed.hook",
        ),
        ("README.md", "usr/share/doc/droidloom/README.md"),
    ] {
        copy(&repo.join("packaging/arch").join(from), &runtime.join(to))?;
    }
    Ok(())
}

fn production_host_payload(repo: &Path, host: &Path, runtime: &Path) -> Result<()> {
    // The fixed production executable paths are ordinary package files. Keep
    // them in the same build as the desktop protocol peers; the unit templates
    // remain data until a separately qualified installation selects the cell.
    for binary in [
        "droidloom-supervisor",
        "droidloomctl",
        "droidloomd",
        "droidloom-host-mac",
        "droidloom-container-entry",
    ] {
        let source = host.join(binary);
        if !fs::symlink_metadata(&source)?.is_file() {
            return fail("production package binaries must be regular build outputs");
        }
        let target = runtime
            .join("usr/lib/droidloom/production/current")
            .join(binary);
        copy(&source, &target)?;
        mode(&target, 0o755)?;
    }
    for unit in [
        "droidloom-production.service",
        "droidloom-manager-label.service",
        "droidloom-container-services.target",
        "droidloom-container-entry.service",
        "droidloom-container-guest.socket",
        "droidloom-early-observer.service",
    ] {
        let source = repo.join("runtime/droidloom-supervisor/src").join(unit);
        if !fs::symlink_metadata(&source)?.is_file() {
            return fail("production unit templates must be regular source files");
        }
        let target = runtime.join("usr/share/droidloom/production").join(unit);
        copy(&source, &target)?;
        mode(&target, 0o644)?;
    }
    early_boot_package::stage(runtime)
}

fn portable_template(template: &mut Value) {
    template["image_dir"] = json!("/usr/lib/droidloom/images");
    template["vendor_image"] = json!("/usr/lib/droidloom/images/images/vendor.raw.img");
    for key in [
        "host_uid",
        "render_node",
        "data_dir",
        "runtime_dir",
        "denial_socket",
    ] {
        template.as_object_mut().unwrap().remove(key);
    }
    template["shared_storage_directories"] = json!([]);
}

fn package_notices(repo: &Path, work: &Path, stage: &Path) -> Result<()> {
    let runtime_notices = stage.join("runtime/usr/share/licenses/droidloom-runtime");
    licenses::project(repo, &runtime_notices)?;
    licenses::rust(repo, &runtime_notices.join("rust"))?;
    let notices = stage.join("image/usr/share/licenses/droidloom-image");
    licenses::project(repo, &notices)?;
    copy(
        &work.join("android-out/target/product/droidloom_x86_64/system/etc/NOTICE.xml.gz"),
        &notices.join("Android-NOTICE.xml.gz"),
    )?;
    copy(
        &work.join("mesa-source/docs/license.rst"),
        &notices.join("Mesa-license.rst"),
    )?;
    let mesa_licenses = work.join("mesa-source/licenses");
    for path in files(&mesa_licenses)? {
        copy(
            &path,
            &notices
                .join("mesa")
                .join(path.strip_prefix(&mesa_licenses)?),
        )?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    #[test]
    fn production_unit_commands_resolve_to_complete_staged_host_payload() {
        let directory = tempfile::tempdir().unwrap();
        let repo = directory.path().join("source");
        let host = directory.path().join("release");
        let runtime = directory.path().join("runtime");
        let templates = repo.join("runtime/droidloom-supervisor/src");
        fs::create_dir_all(&templates).unwrap();
        fs::create_dir(&host).unwrap();
        for (name, body) in [
            ("droidloom-early-observer.service",include_str!("../../../runtime/droidloom-supervisor/src/droidloom-early-observer.service")),
            (
                "droidloom-container-guest.socket",
                include_str!("../../../runtime/droidloom-supervisor/src/droidloom-container-guest.socket"),
            ),
            (
                "droidloom-container-entry.service",
                include_str!("../../../runtime/droidloom-supervisor/src/droidloom-container-entry.service"),
            ),
            (
                "droidloom-container-services.target",
                include_str!("../../../runtime/droidloom-supervisor/src/droidloom-container-services.target"),
            ),
            (
                "droidloom-production.service",
                include_str!(
                    "../../../runtime/droidloom-supervisor/src/droidloom-production.service"
                ),
            ),
            (
                "droidloom-manager-label.service",
                include_str!(
                    "../../../runtime/droidloom-supervisor/src/droidloom-manager-label.service"
                ),
            ),
        ] {
            fs::write(templates.join(name), body).unwrap();
        }
        for binary in ["droidloom-supervisor", "droidloomctl", "droidloomd"] {
            fs::write(host.join(binary), format!("package-copy fixture: {binary}")).unwrap();
        }
        // A three-binary legacy build must not produce a complete new payload.
        assert!(production_host_payload(&repo, &host, &runtime).is_err());
        fs::write(
            host.join("droidloom-host-mac"),
            b"package-copy fixture: host-mac",
        )
        .unwrap();
        assert!(production_host_payload(&repo, &host, &runtime).is_err());
        fs::write(host.join("droidloom-container-entry"), b"package-copy fixture: container-entry").unwrap();
        production_host_payload(&repo, &host, &runtime).unwrap();
        for unit in fs::read_dir(runtime.join("usr/share/droidloom/production")).unwrap() {
            let unit = unit.unwrap().path();
            let body = fs::read_to_string(&unit).unwrap();
            assert_eq!(
                body,
                fs::read_to_string(templates.join(unit.file_name().unwrap())).unwrap()
            );
            assert_eq!(
                fs::metadata(&unit).unwrap().permissions().mode() & 0o777,
                0o644
            );
            if unit.extension().is_some_and(|ext| ext == "socket") {
                assert!(body.lines().any(|line| line == "Service=droidloom-container-entry.service"));
                assert!(body.lines().any(|line| line == "DirectoryMode=0700"));
                continue;
            }
            if unit.extension().is_some_and(|ext| ext == "target") {
                assert!(body.lines().any(|line| line == "BindsTo=droidloom-container-entry.service"));
                assert!(body.lines().any(|line| line == "After=droidloom-container-entry.service"));
                assert!(body.lines().any(|line| line == "PropagatesStopTo=droidloom-container-entry.service"));
                continue;
            }
            let command = body
                .lines()
                .find_map(|line| line.strip_prefix("ExecStart="))
                .unwrap();
            let executable = command.split_whitespace().next().unwrap();
            let target = runtime.join(executable.strip_prefix('/').unwrap());
            let original = host.join(target.file_name().unwrap());
            let metadata = fs::symlink_metadata(&target).unwrap();
            assert!(metadata.is_file());
            assert_eq!(metadata.permissions().mode() & 0o777, 0o755);
            assert_eq!(metadata.nlink(), 1);
            assert_ne!(metadata.ino(), fs::metadata(&original).unwrap().ino());
            assert_eq!(fs::read(&target).unwrap(), fs::read(original).unwrap());
        }
        // Staging the public files cannot install a unit or select a cell.
        assert!(!runtime.join("etc").exists());
        assert!(
            !runtime
                .join("usr/lib/systemd/system/droidloom-production.service")
                .exists()
        );
    }

    #[test]
    fn portable_recipe_has_no_builder_identity_or_local_storage() {
        let mut template: Value = serde_json::from_str(include_str!(
            "../../../packaging/cell-spec-x86_64-u1000.json"
        ))
        .unwrap();
        portable_template(&mut template);
        for key in [
            "host_uid",
            "render_node",
            "data_dir",
            "runtime_dir",
            "denial_socket",
        ] {
            assert!(template.get(key).is_none());
        }
        assert_eq!(template["image_dir"], "/usr/lib/droidloom/images");
        assert_eq!(template["shared_storage_directories"], json!([]));
        assert!(
            !template["android_file_overrides"]
                .as_array()
                .unwrap()
                .is_empty()
        );
    }
}
