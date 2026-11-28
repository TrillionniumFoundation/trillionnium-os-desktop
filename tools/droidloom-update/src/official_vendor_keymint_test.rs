//! Execute the real Soong/BoringSSL test before publishing a normal vendor result.
use super::*;
use std::ffi::OsString;
use std::fs::File;
use std::io::Read;
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::os::unix::process::{CommandExt, ExitStatusExt};

pub(super) const TARGET: &str = "droidloom_keymint_software_compat_test";
const SCHEMA: &str = "droidloom-keymint-soong-host-test-v1";
const LIMIT: u64 = 512 * 1024 * 1024;
const LOG_LIMIT: u64 = 8 * 1024 * 1024;
const CASES: &[&str] = &[
    "new_keys_and_provider_report_software",
    "authenticated_legacy_upgrade_preserves_key_and_authorizations_across_restart",
    "software_upgrade_is_idempotent",
    "wrong_root_or_hidden_parameters_are_rejected_before_migration",
    "corrupted_ciphertext_nonce_and_characteristics_are_rejected",
    "foreign_context_secure_deletion_and_mixed_profiles_are_rejected",
    "generic_software_provider_does_not_implicitly_opt_in",
    "tee_provider_never_uses_the_software_migration_hook",
    "migration_preserves_purpose_and_authentication_restrictions",
    "migration_does_not_allow_version_downgrades",
];

fn expected_tests() -> BTreeSet<String> {
    CASES
        .iter()
        .map(|name| format!("compat_tests::{name}"))
        .collect()
}

fn inventory(text: &str) -> Result<BTreeSet<String>> {
    let names: Vec<_> = text
        .lines()
        .filter_map(|line| line.strip_suffix(": test"))
        .collect();
    let actual: BTreeSet<_> = names.iter().map(|name| (*name).to_owned()).collect();
    if names.len() != CASES.len() || actual != expected_tests() {
        return fail("Soong KeyMint test inventory differs from the ten required cases");
    }
    Ok(actual)
}

fn passed_tests(text: &str) -> Result<()> {
    let names: Vec<_> = text
        .lines()
        .filter_map(|line| {
            line.strip_prefix("test ")
                .and_then(|line| line.strip_suffix(" ... ok"))
        })
        .collect();
    let actual: BTreeSet<_> = names.iter().map(|name| (*name).to_owned()).collect();
    let summaries: Vec<_> = text
        .lines()
        .filter(|line| line.starts_with("test result:"))
        .collect();
    if names.len() != CASES.len()
        || actual != expected_tests()
        || summaries.len() != 1
        || !summaries[0].starts_with(
            "test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;",
        )
    {
        return fail("Soong KeyMint execution did not pass all ten unfiltered cases");
    }
    Ok(())
}

fn needed(text: &str) -> Result<BTreeSet<String>> {
    let mut names = BTreeSet::new();
    for line in text.lines().filter(|line| line.contains("(NEEDED)")) {
        let (_, suffix) = line.split_once('[').ok_or("malformed DT_NEEDED")?;
        let (name, _) = suffix.split_once(']').ok_or("malformed DT_NEEDED")?;
        if name.is_empty() || name.contains('/') || !names.insert(name.to_owned()) {
            return fail("invalid or duplicated DT_NEEDED");
        }
    }
    if !names.contains("libcrypto-host.so") {
        return fail("Soong KeyMint test does not link the Android BoringSSL host library");
    }
    Ok(names)
}

fn loaded(text: &str) -> Result<BTreeMap<String, PathBuf>> {
    let mut libraries = BTreeMap::new();
    for line in text.lines().map(str::trim).filter(|line| !line.is_empty()) {
        if let Some((name, tail)) = line.split_once(" => ") {
            let path = tail
                .split_whitespace()
                .next()
                .ok_or("empty ldd library path")?;
            if !Path::new(path).is_absolute()
                || libraries
                    .insert(name.to_owned(), PathBuf::from(path))
                    .is_some()
            {
                return fail("unresolved, duplicated or nonabsolute host runtime library");
            }
        } else if line.starts_with('/') {
            let path = line.split_whitespace().next().ok_or("empty loader path")?;
            if libraries
                .insert("ELF_INTERPRETER".into(), PathBuf::from(path))
                .is_some()
            {
                return fail("duplicated ELF interpreter");
            }
        } else if !line.starts_with("linux-vdso.so.1 (") {
            return fail("unrecognized ldd output");
        }
    }
    Ok(libraries)
}

fn crypto_paths(host_lib: &Path, libraries: &BTreeMap<String, PathBuf>) -> Result<()> {
    if libraries.get("libcrypto-host.so") != Some(&host_lib.join("libcrypto-host.so")) {
        return fail("KeyMint test resolved BoringSSL outside this normal Soong output");
    }
    for (name, path) in libraries {
        if name.starts_with("libcrypto") || name.starts_with("libssl") {
            if !matches!(name.as_str(), "libcrypto-host.so" | "libssl-host.so")
                || *path != host_lib.join(name)
            {
                return fail("KeyMint test resolved an external crypto or SSL implementation");
            }
        }
    }
    Ok(())
}

// Empty stderr is valid evidence, unlike nonempty build artifacts.
fn log_ref(path: &Path) -> Result<Value> {
    let before = fs::symlink_metadata(path)?;
    if !before.is_file()
        || before.file_type().is_symlink()
        || before.nlink() != 1
        || before.len() > LOG_LIMIT
    {
        return fail("invalid host test log");
    }
    let digest = hash(path)?;
    if f9(&before)? != f9(&fs::symlink_metadata(path)?)? {
        return fail("host test log changed while hashed");
    }
    Ok(json!({"path":path,"bytes":before.len(),"sha256":digest}))
}

fn execute(
    directory: &Path,
    name: &str,
    program: &Path,
    args: &[OsString],
    commands: &mut Vec<Value>,
) -> Result<String> {
    let stdout_path = directory.join(format!("{name}.stdout"));
    let stderr_path = directory.join(format!("{name}.stderr"));
    let open = |path: &Path| -> Result<File> {
        Ok(fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(path)?)
    };
    let stdout = open(&stdout_path)?;
    let stderr = open(&stderr_path)?;
    let mut command = Command::new(program);
    command
        .args(args)
        .current_dir(directory)
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("LC_ALL", "C")
        .env("TZ", "UTC")
        .env("HOME", directory)
        .env("TMPDIR", directory)
        .stdin(Stdio::null())
        .stdout(stdout.try_clone()?)
        .stderr(stderr.try_clone()?)
        .process_group(0);
    let start = Instant::now();
    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(error) => {
            commands.push(json!({"name":name,"program":program,"args":args,
                "spawn_error":error.to_string(),"success":false,
                "stdout":log_ref(&stdout_path)?,"stderr":log_ref(&stderr_path)?}));
            return Err(error.into());
        }
    };
    let mut violation = None;
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if start.elapsed() > Duration::from_secs(300) {
            violation = Some("deadline exceeded");
        } else if stdout.metadata()?.len() > LOG_LIMIT || stderr.metadata()?.len() > LOG_LIMIT {
            violation = Some("log limit exceeded");
        }
        if violation.is_some() {
            // This process group was created solely for this invocation.
            let stopped = Command::new("/usr/bin/kill")
                .env_clear()
                .args(["-KILL", "--", &format!("-{}", child.id())])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()?;
            if !stopped.success() {
                child.kill()?;
            }
            break child.wait()?;
        }
        std::thread::sleep(Duration::from_millis(25));
    };
    stdout.sync_all()?;
    stderr.sync_all()?;
    let success = status.success() && violation.is_none();
    commands.push(json!({"name":name,"program":program,"args":args,
        "exit_code":status.code(),"signal":status.signal(),"success":success,
        "limit_violation":violation,"elapsed_ms":start.elapsed().as_millis(),
        "environment_inherited":false,
        "stdout":log_ref(&stdout_path)?,"stderr":log_ref(&stderr_path)?}));
    if !success {
        return fail(format!(
            "Soong KeyMint {name} failed; see {}",
            directory.display()
        ));
    }
    Ok(fs::read_to_string(stdout_path)?)
}

fn tool(path: &str) -> Result<Artifact> {
    let path = Path::new(path).canonicalize()?;
    let file = artifact(&path, 64 * 1024 * 1024)?;
    if file.f9[3] != 0 || file.f9[2] & 0o022 != 0 || file.f9[2] & 0o111 == 0 {
        return fail("host test inspection tool must be root-owned and non-writable");
    }
    Ok(file)
}

fn qualify(
    repo: &Path,
    vendor_out: &Path,
    directory: &Path,
    commands: &mut Vec<Value>,
) -> Result<Value> {
    let input = artifact(
        &vendor_out.join("droidloom-production-full654-inputs.json"),
        64 * 1024 * 1024,
    )?;
    let normal = artifact(
        &vendor_out.join("droidloom-production-full654-vendor-normal-result.json"),
        64 * 1024 * 1024,
    )?;
    let normal_value: Value = serde_json::from_slice(&fs::read(&normal.path)?)?;
    if normal_value["schema"] != "droidloom-production-full654-vendor-normal-result-v1"
        || normal_value["normal_command_returned_success"] != true
        || normal_value["source_projection_restored"] != true
        || normal_value["inputs"]["sha256"].as_str() != Some(&input.sha256)
        || !normal_value["requested_targets"]
            .as_array()
            .is_some_and(|targets| targets.iter().any(|v| v == TARGET))
    {
        return fail("host test was not requested by the successful normal vendor producer");
    }
    let binary = artifact(
        &vendor_out
            .join("host/linux-x86/nativetest64")
            .join(TARGET)
            .join(TARGET),
        LIMIT,
    )?;
    let mut header = [0u8; 20];
    File::open(&binary.path)?.read_exact(&mut header)?;
    if &header[..6] != b"\x7fELF\x02\x01"
        || !matches!(u16::from_le_bytes([header[16], header[17]]), 2 | 3)
        || u16::from_le_bytes([header[18], header[19]]) != 62
        || binary.f9[2] & 0o111 == 0
    {
        return fail("Soong KeyMint test is not an executable x86_64 ELF");
    }
    let test_source = artifact(
        &repo.join("android/keymint-software-compat/compat_tests.rs"),
        1024 * 1024,
    )?;
    let source_recipe = artifact(
        &repo.join("android/keymint-software-compat/SOURCE.json"),
        1024 * 1024,
    )?;
    let readelf = tool("/usr/bin/readelf")?;
    let ldd = tool("/usr/bin/ldd")?;
    let dynamic = execute(
        directory,
        "dynamic",
        &readelf.path,
        &[
            "--wide".into(),
            "--dynamic".into(),
            binary.path.as_os_str().into(),
        ],
        commands,
    )?;
    let needed = needed(&dynamic)?;
    let loader_output = execute(
        directory,
        "loader",
        &ldd.path,
        &[binary.path.as_os_str().into()],
        commands,
    )?;
    let paths: BTreeMap<_, _> = loaded(&loader_output)?
        .into_iter()
        .map(|(name, path)| Ok((name, path.canonicalize()?)))
        .collect::<Result<_>>()?;
    if needed.iter().any(|name| !paths.contains_key(name)) {
        return fail("a DT_NEEDED library is absent from the actual host loader result");
    }
    // unique_host_soname in pinned BoringSSL installs these -host SONAMEs.
    let host_lib = vendor_out.join("host/linux-x86/lib64");
    if host_lib.canonicalize()? != host_lib {
        return fail("normal host library directory contains an alias");
    }
    crypto_paths(&host_lib, &paths)?;
    let libraries: BTreeMap<_, _> = paths
        .into_iter()
        .map(|(name, path)| Ok((name, artifact(&path, LIMIT)?)))
        .collect::<Result<_>>()?;
    let listing = execute(
        directory,
        "list",
        &binary.path,
        &["--list".into()],
        commands,
    )?;
    let tests = inventory(&listing)?;
    let output = execute(
        directory,
        "tests",
        &binary.path,
        &[
            "--test-threads=1".into(),
            "--format=pretty".into(),
            "--color=never".into(),
        ],
        commands,
    )?;
    passed_tests(&output)?;
    for file in [
        &input,
        &normal,
        &binary,
        &test_source,
        &source_recipe,
        &readelf,
        &ldd,
    ] {
        file.check()?;
    }
    for file in libraries.values() {
        file.check()?;
    }
    Ok(json!({"schema":SCHEMA,"target":TARGET,"passed":true,
        "test_count":tests.len(),"tests":tests,"run_exit_code":0,"list_exit_code":0,
        "boringssl_same_build":true,"binary":binary,"dt_needed":needed,
        "runtime_libraries":libraries,"readelf":readelf,"ldd":ldd,
        "normal_vendor_inputs":input,"normal_vendor_result":normal,
        "test_source":test_source,"source_recipe":source_recipe,
        "runtime_qualified":false,"production_ready":false}))
}

pub(super) fn run(repo: &Path, vendor_out: &Path, out: &Path) -> Result<Value> {
    let directory = out.join("keymint-soong-host-test");
    fs::DirBuilder::new().mode(0o700).create(&directory)?;
    let mut commands = Vec::new();
    let result = qualify(repo, vendor_out, &directory, &mut commands);
    let mut receipt = match &result {
        Ok(value) => value.clone(),
        Err(error) => json!({"schema":SCHEMA,"target":TARGET,"passed":false,
            "error":error.to_string(),"runtime_qualified":false,"production_ready":false}),
    };
    receipt["commands"] = json!(commands);
    let result_path = directory.join("RESULT.json");
    write(&result_path, serde_json::to_vec_pretty(&receipt)?)?;
    result?;
    receipt["result_file"] = serde_json::to_value(artifact(&result_path, 1024 * 1024)?)?;
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_empty_filtered_ignored_or_missing_cases() {
        let list = expected_tests()
            .iter()
            .map(|n| format!("{n}: test\n"))
            .collect::<String>();
        assert_eq!(inventory(&list).unwrap(), expected_tests());
        assert!(inventory("0 tests, 0 benchmarks\n").is_err());
        assert!(inventory(&(list.clone() + "unknown: test\n")).is_err());
        let output = expected_tests()
            .iter()
            .map(|n| format!("test {n} ... ok\n"))
            .collect::<String>()
            + "test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s\n";
        passed_tests(&output).unwrap();
        assert!(passed_tests(&output.replace("10 passed", "9 passed")).is_err());
        assert!(passed_tests(&output.replace("0 filtered out", "1 filtered out")).is_err());
        assert!(passed_tests(&output.replacen(" ... ok", " ... ignored", 1)).is_err());
    }

    #[test]
    fn rejects_missing_or_external_crypto_resolution() {
        let directory = Path::new("/normal/vendor/host/linux-x86/lib64");
        let mut libraries = BTreeMap::from([(
            "libcrypto-host.so".into(),
            directory.join("libcrypto-host.so"),
        )]);
        crypto_paths(directory, &libraries).unwrap();
        libraries.insert(
            "libcrypto-host.so".into(),
            "/usr/lib/libcrypto-host.so".into(),
        );
        assert!(crypto_paths(directory, &libraries).is_err());
        libraries.insert(
            "libcrypto-host.so".into(),
            directory.join("libcrypto-host.so"),
        );
        libraries.insert("libcrypto.so.3".into(), "/usr/lib/libcrypto.so.3".into());
        assert!(crypto_paths(directory, &libraries).is_err());
        assert!(loaded("libcrypto-host.so => not found\n").is_err());
        assert!(needed("0 (NEEDED) Shared library: [libcrypto.so.3]\n").is_err());
        assert!(needed("0 (NEEDED) Shared library: [libcrypto-host.so]\n").is_ok());
    }

    #[test]
    fn real_nonzero_command_leaves_exit_and_empty_log_evidence() {
        let directory = tempfile::tempdir().unwrap();
        let mut commands = Vec::new();
        assert!(
            execute(
                directory.path(),
                "false",
                Path::new("/usr/bin/false"),
                &[],
                &mut commands
            )
            .is_err()
        );
        assert_eq!(commands.len(), 1);
        assert_eq!(commands[0]["exit_code"], 1);
        assert_eq!(commands[0]["success"], false);
        assert_eq!(commands[0]["stderr"]["bytes"], 0);
        assert!(directory.path().join("false.stderr").is_file());
    }
}
