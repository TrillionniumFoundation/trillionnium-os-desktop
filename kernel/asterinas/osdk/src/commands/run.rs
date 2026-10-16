// SPDX-License-Identifier: MPL-2.0

use std::process::exit;

use vsc::VscLaunchConfig;

use super::{
    build::create_base_and_cached_build,
    util::{DEFAULT_TARGET_RELPATH, is_tdx_enabled},
};
use crate::{
    config::{Config, scheme::ActionChoice},
    error::Errno,
    error_msg,
    util::{get_kernel_crate, get_target_directory},
    warn_msg,
};

pub fn execute_run_command(config: &Config, gdb_server_args: Option<&str>) {
    let cargo_target_directory = get_target_directory();
    let osdk_output_directory = cargo_target_directory.join(DEFAULT_TARGET_RELPATH);

    let target_info = get_kernel_crate();

    let mut config = config.clone();

    let _vsc_launch_file = if let Some(gdb_server_str) = gdb_server_args {
        adapt_for_gdb_server(&mut config, gdb_server_str)
    } else {
        None
    };

    let default_bundle_directory = osdk_output_directory.join(&target_info.name);
    let bundle = create_base_and_cached_build(
        target_info,
        default_bundle_directory,
        &osdk_output_directory,
        &cargo_target_directory,
        &config,
        ActionChoice::Run,
        &[],
    );

    bundle.run(&config, ActionChoice::Run);
}

fn adapt_for_gdb_server(config: &mut Config, gdb_server_str: &str) -> Option<VscLaunchConfig> {
    let gdb_server_args = GdbServerArgs::from_str(gdb_server_str);

    // Add GDB server arguments to QEMU.
    let qemu_gdb_args = {
        let gdb_stub_addr = gdb_server_args.host_addr.as_str();
        match gdb::stub_type_of(gdb_stub_addr) {
            gdb::StubAddrType::Unix => {
                format!(
                    " -chardev socket,path={},server=on,wait=off,id=gdb0 -gdb chardev:gdb0",
                    gdb_stub_addr
                )
            }
            gdb::StubAddrType::Tcp => {
                format!(
                    " -gdb tcp:{}",
                    gdb::tcp_addr_util::format_tcp_addr(gdb_stub_addr)
                )
            }
        }
    };
    config.run.qemu.args += &qemu_gdb_args;

    if gdb_server_args.wait_client {
        config.run.qemu.args += " -S";
    }

    if is_tdx_enabled() {
        let target = "-object tdx-guest,";
        if let Some(pos) = config.run.qemu.args.find(target) {
            let insert_pos = pos + target.len();
            config.run.qemu.args.insert_str(insert_pos, "debug=on,");
        } else {
            warn_msg!(
                "TDX is enabled, but the TDX guest object is not found in the QEMU arguments"
            );
        }
    }

    // Ensure debug info added when debugging in the release profile.
    if config.run.build.profile.contains("release") {
        config
            .run
            .build
            .override_configs
            .push(format!("profile.{}.debug=true", config.run.build.profile));
    }

    gdb_server_args.vsc_launch_file.then(|| {
        vsc::check_gdb_config(&gdb_server_args);
        vsc::VscLaunchConfig::new(config, &gdb_server_args.host_addr)
    })
}

struct GdbServerArgs {
    host_addr: String,
    wait_client: bool,
    vsc_launch_file: bool,
}

impl GdbServerArgs {
    fn from_str(args: &str) -> Self {
        let mut host_addr = ".osdk-gdb-socket".to_string();
        let mut wait_client = false;
        let mut vsc_launch_file = false;

        for arg in args.split(",") {
            let kv = arg.split('=').collect::<Vec<_>>();
            match kv.as_slice() {
                ["addr", addr] => host_addr = addr.to_string(),
                ["wait-client"] => wait_client = true,
                ["vscode"] => vsc_launch_file = true,
                _ => {
                    error_msg!("Invalid GDB server argument: {}", arg);
                    exit(Errno::Cli as _);
                }
            }
        }

        GdbServerArgs {
            host_addr,
            wait_client,
            vsc_launch_file,
        }
    }
}

mod gdb {
    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    pub enum StubAddrType {
        Unix, // Unix Domain Socket
        Tcp,  // IP_ADDR:PORT
    }
    pub fn stub_type_of(stub: &str) -> StubAddrType {
        if stub.split(':').next_back().unwrap().parse::<u16>().is_ok() {
            return StubAddrType::Tcp;
        }
        StubAddrType::Unix
    }

    pub mod tcp_addr_util {
        use crate::{error::Errno, error_msg};
        use std::process::exit;

        fn strip_tcp_prefix(addr: &str) -> &str {
            addr.strip_prefix("tcp:").unwrap_or(addr)
        }

        fn parse_tcp_addr(addr: &str) -> (&str, u16) {
            let addr = strip_tcp_prefix(addr);
            if !addr.contains(':') {
                error_msg!("Ambiguous GDB server address, use '[IP]:PORT' format");
                exit(Errno::ParseMetadata as _);
            }
            let mut iter = addr.split(':');
            let host = iter.next().unwrap();
            let port = iter.next().unwrap().parse().unwrap();
            (host, port)
        }

        pub fn format_tcp_addr(tcp_addr: &str) -> String {
            let (host, port) = parse_tcp_addr(tcp_addr);
            format!("{}:{}", host, port)
        }
    }
}

mod vsc {
    use crate::{
        arch::Arch,
        commands::util::{bin_file_name, profile_name_adapter},
        config::Config,
        util::{get_cargo_metadata, get_target_directory},
    };
    use serde_json::{Value, from_str};
    use std::{
        fs::{read_to_string, write as write_file},
        path::{Path, PathBuf},
    };

    use super::{GdbServerArgs, gdb};

    const VSC_DIR: &str = ".vscode";

    #[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
    struct Existence {
        vsc_dir: bool,
        launch_file: bool,
    }

    fn workspace_root() -> String {
        get_cargo_metadata(None::<&str>, None::<&[&str]>).unwrap()["workspace_root"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    #[derive(Debug, Default)]
    pub struct VscLaunchConfig {
        existence: Existence,
        backup_launch_path: Option<String>,
    }
    impl VscLaunchConfig {
        pub fn new(config: &Config, addr: &str) -> Self {
            let workspace = workspace_root();
            let workspace = Path::new(&workspace);
            let launch_file_path = workspace.join(VSC_DIR).join("launch.json");
            let existence = Existence {
                vsc_dir: workspace.join(VSC_DIR).exists(),
                launch_file: launch_file_path.exists(),
            };

            let backup_launch_path = existence.launch_file.then(|| {
                let backup_launch_path = launch_file_path.with_extension("bak");
                std::fs::copy(&launch_file_path, &backup_launch_path).unwrap();
                backup_launch_path.to_string_lossy().to_string()
            });

            if !existence.vsc_dir {
                std::fs::create_dir(workspace.join(VSC_DIR)).unwrap();
            }
            let symbol_file = kernel_symbol_file(
                &get_target_directory(),
                config.target_arch,
                &config.run.build.profile,
                &bin_file_name(),
            );
            generate_vsc_launch_file(
                workspace,
                profile_name_adapter(&config.run.build.profile),
                addr,
                &symbol_file,
            )
            .unwrap();

            VscLaunchConfig {
                existence,
                backup_launch_path,
            }
        }
    }

    impl Drop for VscLaunchConfig {
        fn drop(&mut self) {
            // remove generated files
            if !self.existence.vsc_dir {
                std::fs::remove_dir_all(Path::new(&workspace_root()).join(VSC_DIR)).unwrap();
                return;
            }
            if !self.existence.launch_file {
                std::fs::remove_file(
                    Path::new(&workspace_root())
                        .join(VSC_DIR)
                        .join("launch.json"),
                )
                .unwrap();
                return;
            }
            // restore backup launch file
            if let Some(backup_launch_path) = &self.backup_launch_path {
                std::fs::copy(
                    backup_launch_path,
                    Path::new(&workspace_root())
                        .join(VSC_DIR)
                        .join("launch.json"),
                )
                .unwrap();
                std::fs::remove_file(backup_launch_path).unwrap();
            }
        }
    }

    /// Exit if the QEMU GDB server configuration is not valid
    pub fn check_gdb_config(args: &GdbServerArgs) {
        use crate::{error::Errno, error_msg};
        use std::process::exit;

        // check GDB server address
        let gdb_stub_addr = args.host_addr.as_str();
        if gdb_stub_addr.is_empty() {
            error_msg!("GDB server address is required to generate a VSCode launch file");
            exit(Errno::ParseMetadata as _);
        }
        if gdb::stub_type_of(gdb_stub_addr) != gdb::StubAddrType::Tcp {
            error_msg!(
                "Non-TCP GDB server address is not supported under '--gdb-server vscode' currently"
            );
            exit(Errno::ParseMetadata as _);
        }
    }

    fn generate_vsc_launch_file(
        workspace: impl AsRef<Path>,
        profile: &str,
        addr: &str,
        symbol_file: &Path,
    ) -> Result<(), std::io::Error> {
        let contents = render_launch_config(profile, addr, symbol_file)?;

        let original_items: Option<Value> = {
            let launch_file_path = workspace.as_ref().join(VSC_DIR).join("launch.json");
            let src_path = if launch_file_path.exists() {
                launch_file_path
            } else {
                launch_file_path.with_extension("bak")
            };
            src_path
                .exists()
                .then(|| from_str(&read_to_string(&src_path).unwrap()).unwrap())
        };

        let contents = if let Some(mut original_items) = original_items {
            let items: Value = from_str(&contents)?;
            for item in items["configurations"].as_array().unwrap() {
                if original_items["configurations"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .any(|x| x["name"].as_str() == item["name"].as_str())
                {
                    println!("[{}/launch.json]{} already exists", VSC_DIR, item["name"]);
                    // no override for configurations with the same name
                    continue;
                }
                original_items["configurations"]
                    .as_array_mut()
                    .unwrap()
                    .push(item.clone());
            }
            serde_json::to_string_pretty(&original_items).unwrap()
        } else {
            contents
        };

        let launch_file_path = workspace.as_ref().join(VSC_DIR).join("launch.json");
        write_file(launch_file_path, contents)
    }

    fn kernel_symbol_file(
        target_directory: &Path,
        arch: Arch,
        profile: &str,
        binary_name: &str,
    ) -> PathBuf {
        // Use Cargo's original ELF rather than the boot bundle: direct boot may
        // rename and reformat the latter for the VMM's multiboot loader.
        target_directory
            .join(arch.triple())
            .join(profile_name_adapter(profile))
            .join(binary_name)
    }

    fn render_launch_config(
        profile: &str,
        addr: &str,
        symbol_file: &Path,
    ) -> Result<String, serde_json::Error> {
        let symbol_file = symbol_file.to_string_lossy();
        let target_command = format!(
            "target create {}",
            shlex::Quoter::new().quote(&symbol_file).unwrap()
        );
        Ok(include_str!("launch.json.template")
            .replace("#PROFILE#", profile)
            .replace(
                "#TARGET_CREATE_COMMAND#",
                &serde_json::to_string(&target_command)?,
            )
            .replace(
                "#ADDR_PORT#",
                gdb::tcp_addr_util::format_tcp_addr(addr).trim_start_matches(':'),
            ))
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use crate::config::scheme::BootMethod;

        #[test]
        fn symbol_file_uses_cargo_elf_for_direct_and_grub_boot() {
            let workspace = tempfile::tempdir().unwrap();
            let target = workspace.path().join("target");
            let symbols = target.join("x86_64-unknown-none/debug/myos-osdk-bin");
            std::fs::create_dir_all(symbols.parent().unwrap()).unwrap();
            std::fs::write(&symbols, b"original debug ELF fixture").unwrap();

            for method in [
                BootMethod::VmmDirect,
                BootMethod::GrubRescueIso,
                BootMethod::GrubQcow2,
            ] {
                let bundle = target.join("osdk/myos");
                std::fs::create_dir_all(&bundle).unwrap();
                let boot_file = bundle.join(if method == BootMethod::VmmDirect {
                    "myos-osdk-bin.elf"
                } else {
                    "myos-osdk-bin"
                });
                std::fs::write(&boot_file, b"boot artifact fixture").unwrap();

                let selected = kernel_symbol_file(&target, Arch::X86_64, "dev", "myos-osdk-bin");
                assert_eq!(selected, symbols);
                assert!(selected.is_file());
                assert_ne!(selected, boot_file);
                let launch: Value =
                    from_str(&render_launch_config("debug", ":1234", &selected).unwrap()).unwrap();
                let command = launch["configurations"][0]["targetCreateCommands"][0]
                    .as_str()
                    .unwrap();
                assert_eq!(shlex::split(command).unwrap()[2], symbols.to_str().unwrap());
                std::fs::remove_file(boot_file).unwrap();
            }
        }

        #[test]
        fn symbol_file_respects_custom_target_arch_and_profile() {
            assert_eq!(
                kernel_symbol_file(
                    Path::new("/custom/shared-target"),
                    Arch::Aarch64,
                    "release-lto",
                    "myos-osdk-bin",
                ),
                Path::new(
                    "/custom/shared-target/aarch64-unknown-none-softfloat/release-lto/myos-osdk-bin"
                )
            );
        }

        #[test]
        fn launch_command_preserves_symbol_path_with_spaces_and_quotes() {
            let symbols = Path::new("/custom target/a \"quoted\" kernel/myos-osdk-bin");
            let launch: Value =
                from_str(&render_launch_config("debug", ":1234", symbols).unwrap()).unwrap();
            let configuration = &launch["configurations"][0];
            assert_eq!(
                shlex::split(configuration["targetCreateCommands"][0].as_str().unwrap()).unwrap(),
                ["target", "create", symbols.to_str().unwrap()]
            );
            assert_eq!(configuration["processCreateCommands"][0], "gdb-remote 1234");
        }
    }
}
