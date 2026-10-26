//! Actual original Core Start/Resume before the bounded Root/Session episode.
use super::{Result, config::Inputs, fs, geometry::Product, process::ChildOwner};
use codex_app_server_client::{
    RemoteAppServerClient, RemoteAppServerConnectArgs, RemoteAppServerEndpoint,
};
use codex_hepta_agentd::{
    NotesThreadSeedOptions, NotesThreadSeedReceipt, seed_original_notes_thread,
};
use codex_utils_absolute_path::AbsolutePathBuf;
use serde::Deserialize;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Preferences {
    schema: String,
    locale: String,
    model: String,
    model_provider: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PromptRegistry {
    schema: String,
    developer_instructions: String,
}

pub(super) async fn create(inputs: &Inputs, fresh: &Product) -> Result<NotesThreadSeedReceipt> {
    let home = fresh.record.layout.home_root();
    let preferences: Preferences = fs::read_root_document(&inputs.sources.preferences)?;
    let prompts: PromptRegistry = fs::read_root_document(&inputs.sources.prompt_registry)?;
    if preferences.schema != "trill.original-notes-preferences.v1"
        || preferences.locale != inputs.locale
        || preferences.model != "qwen38-flash-next-uc"
        || preferences.model_provider != "hepta_local"
        || prompts.schema != "trill.original-notes-prompts.v1"
        || prompts.developer_instructions.is_empty()
        || prompts.developer_instructions.len() > 512
        || prompts.developer_instructions.contains('\0')
        || fs::digest(&inputs.sources.runtime_body)? != fs::digest(&inputs.programs.agentd)?
    {
        return Err(
            "actual preferences, prompt or runtime input differs from the finite product profile"
                .into(),
        );
    }
    // This is public, fixed product configuration in a genuinely new Core
    // home. It neither reads nor copies existing provider credentials.
    fs::write_new(&home.join("config.toml"), b"model = \"qwen38-flash-next-uc\"\nmodel_provider = \"hepta_local\"\n[model_providers.hepta_local]\nname = \"Hepta local Responses\"\nbase_url = \"http://127.0.0.1:18083/v1\"\nwire_api = \"responses\"\nrequires_openai_auth = false\n")?;
    let path = fresh.prefix.join("seed.sock");
    if std::fs::symlink_metadata(&path).is_ok() {
        return Err("seed socket already exists".into());
    }
    let program = fs::root_file(&inputs.programs.app_server, true)?;
    let stdout = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(fresh.admin.join("seed.stdout"))?;
    let stderr = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(fresh.admin.join("seed.stderr"))?;
    let mut command = Command::new(format!("/proc/self/fd/{}", program.as_raw_fd()));
    command
        .args([
            "--listen",
            &format!("unix://{}", path.display()),
            "--strict-config",
        ])
        .current_dir(fresh.record.manifest.workspace.as_path())
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("LANG", "C.UTF-8")
        .env("CODEX_HOME", home)
        .env("CODEX_SQLITE_HOME", home)
        .env("HOME", home)
        .stdin(Stdio::null())
        .stdout(stdout)
        .stderr(stderr);
    let mut owner = ChildOwner::spawn(&mut command)?;
    let end = Instant::now() + Duration::from_secs(20);
    let client = loop {
        super::process::alive(&owner.pidfd)?;
        let connected = tokio::time::timeout(
            Duration::from_millis(250),
            RemoteAppServerClient::connect(RemoteAppServerConnectArgs {
                endpoint: RemoteAppServerEndpoint::UnixSocket {
                    socket_path: AbsolutePathBuf::from_absolute_path(&path)?,
                },
                client_name: "trill-original-root-thread-seed".into(),
                client_version: env!("CARGO_PKG_VERSION").into(),
                experimental_api: true,
                mcp_server_openai_form_elicitation: false,
                opt_out_notification_methods: Vec::new(),
                channel_capacity: 32,
            }),
        )
        .await;
        match connected {
            Ok(Ok(client)) => break client,
            Ok(Err(_)) | Err(_) if Instant::now() < end => {
                tokio::time::sleep(Duration::from_millis(25)).await;
            }
            Ok(Err(error)) => return Err(error.into()),
            Err(_) => return Err("original AppServer seed connection timed out".into()),
        }
    };
    let receipt = seed_original_notes_thread(
        &client,
        home,
        NotesThreadSeedOptions {
            model: Some(preferences.model.clone()),
            model_provider: Some(preferences.model_provider.clone()),
            cwd: Some(fresh.record.manifest.workspace.as_path().to_path_buf()),
            developer_instructions: Some(prompts.developer_instructions),
        },
    )
    .await?;
    if receipt.model != preferences.model || receipt.model_provider != preferences.model_provider {
        return Err("actual Start result differs from the explicit product model/provider".into());
    }
    client.shutdown().await?;
    owner.terminate()?;
    cleanup_seed_aliases(home, &inputs.programs.app_server)?;
    if let Ok(meta) = std::fs::symlink_metadata(&path) {
        use std::os::unix::fs::FileTypeExt;
        if !meta.file_type().is_socket() || meta.uid() != 0 {
            return Err("seed socket changed".into());
        }
        std::fs::remove_file(&path)?;
    }
    fs::json_new(&fresh.admin.join("original-thread-seed.json"), &receipt)?;
    Ok(receipt)
}

fn cleanup_seed_aliases(home: &Path, program: &Path) -> Result<()> {
    let root = home.join("tmp/arg0");
    if !root.exists() {
        return Ok(());
    }
    fs::root_directory(&root)?;
    let entries = std::fs::read_dir(&root)?.collect::<std::io::Result<Vec<_>>>()?;
    if entries.len() > 1 {
        return Err("unexpected extra seed arg0 directories".into());
    }
    for entry in entries {
        let path = entry.path();
        fs::root_directory(&path)?;
        if !entry
            .file_name()
            .to_str()
            .is_some_and(|s| s.starts_with("codex-arg0"))
        {
            return Err("unknown seed alias directory".into());
        }
        let aliases = std::fs::read_dir(&path)?.collect::<std::io::Result<Vec<_>>>()?;
        if aliases.len() > 8 {
            return Err("seed alias bound exceeded".into());
        }
        for alias in &aliases {
            let p = alias.path();
            let m = std::fs::symlink_metadata(&p)?;
            if m.uid() != 0
                || (m.file_type().is_symlink() && std::fs::read_link(&p)? != program)
                || (!m.file_type().is_symlink() && (!m.is_file() || m.nlink() != 1))
            {
                return Err("seed alias custody changed".into());
            }
        }
        for alias in aliases {
            std::fs::remove_file(alias.path())?;
        }
        std::fs::remove_dir(&path)?;
    }
    std::fs::File::open(root)?.sync_all()?;
    Ok(())
}
