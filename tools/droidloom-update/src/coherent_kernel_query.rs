//! Fixed original query inputs for the shared-kernel first-stage release.
//! Publication creates private material only; root ownership and original role
//! labels are required again by the production import and descriptor admission.
use super::*;
use std::os::unix::fs::PermissionsExt;

#[path = "../../../runtime/droidloom-supervisor/src/production_query_input_profile.rs"]
mod fixed;
#[path = "query_input_metadata.rs"]
mod metadata;
use metadata::{original_stat, original_xattrs};

fn require(value: bool, message: &str) -> Result<()> {
    if value { Ok(()) } else { fail(message) }
}

pub(super) struct Prepared {
    pub(super) declaration: Value,
    files: Vec<(fixed::FixedQueryInput, FileRef)>,
    installation: Value,
}

fn capture(reader: &FileRef, system: &FileRef, work: &Path, name: &str, request: &str, limit: u64) -> Result<FileRef> {
    let path = work.join(name);
    let file = OpenOptions::new().write(true).create_new(true).mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(&path)?;
    checked_tool(reader, Command::new(&reader.path).args(["-R", request])
        .arg(&system.path).current_dir(work).stdout(Stdio::from(file)))?;
    pin(&path, limit)
}

pub(super) fn prepare(work: &Path, system: &FileRef, reader: &FileRef) -> Result<Prepared> {
    require(system.bytes == fixed::SYSTEM_BYTES && system.sha256 == fixed::SYSTEM_SHA256,
        "kernel-first query roles require the complete original CP3A system")?;
    let mut files = Vec::with_capacity(4);
    let mut sources = Vec::with_capacity(4);
    let mut observations = Vec::with_capacity(4);
    for role in fixed::INPUTS {
        let body = capture(reader, system, work, role.output_name,
            &format!("cat {}", role.source_path), role.bytes)?;
        require(body.bytes == role.bytes && body.sha256 == role.sha256,
            "whole original kernel-first query body differs from its fixed CP3A role")?;
        let stat = capture(reader, system, work, &format!("{}-stat", role.output_name),
            &format!("stat {}", role.source_path), 8192)?;
        let inode = original_stat(role, &bound_body(&stat, 8192)?)?;
        let attrs = capture(reader, system, work, &format!("{}-xattrs", role.output_name),
            &format!("ea_list {}", role.source_path), 8192)?;
        let label_name = format!("{}-label", role.output_name);
        checked_tool(reader, Command::new(&reader.path)
            .args(["-R", &format!("ea_get -f {label_name} {} security.selinux", role.source_path)])
            .arg(&system.path).current_dir(work))?;
        let label = pin(&work.join(label_name), 256)?;
        original_xattrs(role, &bound_body(&attrs, 8192)?, &bound_body(&label, 256)?)?;
        sources.push(json!({"original":{"file":role.output_name,"bytes":body.bytes,"sha256":body.sha256},
            "source_path":role.source_path,"interpreter":role.interpreter}));
        observations.push(json!({"source_path":role.source_path,"source_inode":inode,
            "source_mode":role.original_mode,"source_uid":0,"source_gid":role.original_gid,
            "file":role.output_name,"bytes":body.bytes,"sha256":body.sha256,
            "required_installed_mode":role.installed_mode(),"required_installed_uid":0,"required_installed_gid":0,
            "required_original_label":std::str::from_utf8(role.original_label)?,
            "required_original_label_preserved":true,"required_security_capability_absent":true,
            "installed_label_observed":false}));
        files.push((role, body));
    }
    recheck(system, MAX_IMAGE)?;
    recheck(reader, 256 * 1024 * 1024)?;
    let [cmd,toybox,app_process64,content_jar]: [Value;4] = sources.try_into()
        .map_err(|_| "fixed kernel-first query input count changed")?;
    let declaration = json!({"scope":"fixed_application_query_v1","source_system_sha256":fixed::SYSTEM_SHA256,
        "cmd":cmd,"toybox":toybox,"contacts":{"scope":"fixed_contacts_content_query_v1",
        "app_process64":app_process64,"content_jar":content_jar}});
    let installation = json!({"schema":"droidloom-fixed-cp3a-query-inputs-v1",
        "input_scope":fixed::INPUT_SCOPE,"source_system_sha256":fixed::SYSTEM_SHA256,
        "source_system_bytes":fixed::SYSTEM_BYTES,"sources":observations,"input_count":4,
        "private_query_projection_observed":false,"original_query_executions":0,
        "application_admission":false,"runtime_qualified":false});
    Ok(Prepared { declaration, files, installation })
}

impl Prepared {
    pub(super) fn publish(&self, root: &Path, runtime: &str) -> Result<Value> {
        require(runtime.len() == 64 && runtime.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "kernel-first query destination must be a manifest digest")?;
        let parent = root.join("var/lib/droidloom/runtime-cohorts");
        resources::prepare_output_directory(&parent)?;
        let temporary = tempfile::Builder::new().prefix("kernel-query-stage-").tempdir_in(&parent)?;
        let stage = temporary.path();
        for (role, body) in &self.files {
            let destination = stage.join("images").join(role.output_name);
            copy_bound(body, &destination)?;
            fs::set_permissions(&destination, fs::Permissions::from_mode(role.installed_mode()))?;
            File::open(&destination)?.sync_all()?;
            let actual = pin(&destination, role.bytes)?;
            require(actual.sha256 == body.sha256 && actual.bytes == body.bytes,
                "staged kernel-first query body changed")?;
        }
        save_new(&stage.join("QUERY-INSTALL-REQUIREMENTS.json"), &self.installation)?;
        File::open(stage.join("images"))?.sync_all()?;
        File::open(stage)?.sync_all()?;
        let directory = parent.join(runtime);
        match official_base::rename_new(stage, &directory) {
            Ok(()) => { let _published_path = temporary.keep(); }
            Err(error) if directory.symlink_metadata().is_ok() => {
                // A previous normal binding of this exact digest may be reused,
                // but every original role is re-read below before success.
                ordinary_absolute(&directory, true)?;
                let _ = error;
            }
            Err(error) => return Err(error),
        }
        for (role, body) in &self.files {
            recheck(body, role.bytes)?;
            let actual = pin(&directory.join("images").join(role.output_name), role.bytes)?;
            require(actual.bytes == role.bytes && actual.sha256 == role.sha256
                && actual.identity[2] & 0o7777 == u64::from(role.installed_mode()),
                "published kernel-first query body or mode changed")?;
        }
        let (requirements, actual) = read_json(&directory.join("QUERY-INSTALL-REQUIREMENTS.json"))?;
        require(actual == self.installation, "published query installation requirements changed")?;
        File::open(&parent)?.sync_all()?;
        Ok(json!({"images_directory":directory.strip_prefix(root)?,
            "installation_requirements":requirements.path.strip_prefix(root)?,
            "installation_requirements_sha256":requirements.sha256,"input_count":4,
            "installed_original_labels_observed":false,"application_admission":false}))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore = "requires DROIDLOOM_TEST_CP3A_SYSTEM pointing at the complete original CP3A image"]
    fn actual_kernel_query_reads_original_labels_and_rejects_changed_publication() {
        let path = std::env::var_os("DROIDLOOM_TEST_CP3A_SYSTEM").expect("explicit original CP3A image");
        let system = pin(Path::new(&path), MAX_IMAGE).unwrap();
        let temp = tempfile::tempdir().unwrap();
        let _scope = resources::Scope::writing(temp.path(), 4 * 1024 * 1024).unwrap();
        let work = temp.path().join("extracted");
        fs::create_dir(&work).unwrap();
        let reader = reader_tool("debugfs").unwrap();
        let prepared = prepare(&work, &system, &reader).unwrap();
        let runtime = "a".repeat(64);
        prepared.publish(temp.path(), &runtime).unwrap();
        prepared.publish(temp.path(), &runtime).unwrap();
        let member = temp.path().join("var/lib/droidloom/runtime-cohorts").join(&runtime)
            .join("images/cmd-original");
        fs::set_permissions(&member, fs::Permissions::from_mode(0o755)).unwrap();
        let mut bytes = fs::read(&member).unwrap();
        bytes[32] ^= 1;
        fs::write(&member, bytes).unwrap();
        assert!(prepared.publish(temp.path(), &runtime).is_err());
    }
}
