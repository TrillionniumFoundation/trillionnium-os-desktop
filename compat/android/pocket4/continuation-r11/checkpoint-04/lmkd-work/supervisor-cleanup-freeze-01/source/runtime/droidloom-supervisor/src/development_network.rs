//! Bounded network plumbing for the executable development cell.
//!
//! Linux remains the network implementation. This module only creates a veth
//! pair, assigns the host gateway, and installs narrowly named nftables rules
//! for outbound forwarding/NAT. Android owns `eth0` and its normal networking
//! services inside the private namespace.

use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Stdio;

use crate::CellSpec;
use crate::development::DevelopmentError;

const HOST_IPV4_CIDR: &str = "10.177.0.1/30";
const CELL_IPV4_CIDR: &str = "10.177.0.2/32";
const IPV4_FORWARD_PATH: &str = "/proc/sys/net/ipv4/ip_forward";
const IPV4_FORWARD_STATE_FILE: &str = "host-ipv4-forward.before";

#[derive(Clone, Debug, Eq, PartialEq)]
struct NetworkNames {
    namespace: String,
    host_interface: String,
    temporary_cell_interface: String,
    filter_table: String,
    nat_table: String,
}

impl NetworkNames {
    fn for_spec(spec: &CellSpec) -> Self {
        let uid = spec.host_uid;
        Self {
            namespace: format!("droidloom-u{uid}"),
            host_interface: format!("dlh{uid}"),
            temporary_cell_interface: format!("dlc{uid}"),
            filter_table: format!("droidloom_u{uid}"),
            nat_table: format!("droidloom_u{uid}_nat"),
        }
    }
}

/// Live host-owned networking objects for one development cell.
pub(crate) struct DevelopmentNetwork {
    names: NetworkNames,
    runtime_dir: PathBuf,
    resources: Vec<NetworkResource>,
    previous_ipv4_forward: Option<String>,
    forwarding_restored: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum NetworkResource {
    Namespace,
    HostInterface,
    FilterTable,
    NatTable,
    UfwForwardRule,
}

impl DevelopmentNetwork {
    /// Create the private namespace and its single outbound kernel path.
    pub(crate) fn create(spec: &CellSpec) -> Result<Self, DevelopmentError> {
        let mut network = Self {
            names: NetworkNames::for_spec(spec),
            runtime_dir: spec.runtime_dir.clone(),
            resources: Vec::new(),
            previous_ipv4_forward: None,
            forwarding_restored: false,
        };

        if let Err(error) = network.setup() {
            if let Err(cleanup_error) = network.teardown() {
                eprintln!(
                    "droidloom-supervisor: network setup failed: {error}; cleanup also failed: {cleanup_error}"
                );
            }
            return Err(error);
        }
        Ok(network)
    }

    pub(crate) fn namespace(&self) -> &str {
        &self.names.namespace
    }

    fn setup(&mut self) -> Result<(), DevelopmentError> {
        self.setup_links()?;
        self.enable_forwarding()?;
        self.setup_filter()?;
        self.setup_nat()?;
        self.setup_ufw_forwarding()
    }

    fn setup_ufw_forwarding(&mut self) -> Result<(), DevelopmentError> {
        // A separate nftables accept verdict cannot override UFW's later drop.
        // Add only our exact outbound source/interface rule to its user chain.
        // It is transient and never modifies UFW's persistent configuration.
        if ufw_chain_exists()? {
            run("iptables", ufw_rule_arguments("-I", &self.names))?;
            self.resources.push(NetworkResource::UfwForwardRule);
        }
        Ok(())
    }

    fn setup_links(&mut self) -> Result<(), DevelopmentError> {
        run("ip", ["netns", "add", &self.names.namespace])?;
        self.resources.push(NetworkResource::Namespace);

        run(
            "ip",
            [
                "link",
                "add",
                &self.names.host_interface,
                "type",
                "veth",
                "peer",
                "name",
                &self.names.temporary_cell_interface,
            ],
        )?;
        self.resources.push(NetworkResource::HostInterface);
        run(
            "ip",
            [
                "link",
                "set",
                &self.names.temporary_cell_interface,
                "netns",
                &self.names.namespace,
            ],
        )?;
        run(
            "ip",
            [
                "address",
                "add",
                HOST_IPV4_CIDR,
                "dev",
                &self.names.host_interface,
            ],
        )?;
        run("ip", ["link", "set", &self.names.host_interface, "up"])?;
        run_in_namespace(&self.names.namespace, ["link", "set", "lo", "up"])?;
        run_in_namespace(
            &self.names.namespace,
            [
                "link",
                "set",
                &self.names.temporary_cell_interface,
                "name",
                "eth0",
            ],
        )?;
        run_in_namespace(&self.names.namespace, ["link", "set", "eth0", "up"])?;
        Ok(())
    }

    fn enable_forwarding(&mut self) -> Result<(), DevelopmentError> {
        let forwarding = fs::read_to_string(IPV4_FORWARD_PATH)
            .map_err(|source| io_error("read host IPv4 forwarding state", source))?;
        fs::write(self.forwarding_state_path(), forwarding.as_bytes())
            .map_err(|source| io_error("record host IPv4 forwarding state", source))?;
        self.previous_ipv4_forward = Some(forwarding.clone());
        if forwarding.trim() != "1" {
            fs::write(IPV4_FORWARD_PATH, "1\n")
                .map_err(|source| io_error("enable host IPv4 forwarding", source))?;
        }
        Ok(())
    }

    fn setup_filter(&mut self) -> Result<(), DevelopmentError> {
        run("nft", ["add", "table", "inet", &self.names.filter_table])?;
        self.resources.push(NetworkResource::FilterTable);
        self.setup_input_filter()?;
        self.setup_forward_filter()
    }

    fn setup_input_filter(&self) -> Result<(), DevelopmentError> {
        run(
            "nft",
            [
                "add",
                "chain",
                "inet",
                &self.names.filter_table,
                "input",
                "{",
                "type",
                "filter",
                "hook",
                "input",
                "priority",
                "filter",
                ";",
                "policy",
                "accept",
                ";",
                "}",
            ],
        )?;
        run(
            "nft",
            [
                "add",
                "rule",
                "inet",
                &self.names.filter_table,
                "input",
                "iifname",
                &self.names.host_interface,
                "drop",
            ],
        )
    }

    fn setup_forward_filter(&self) -> Result<(), DevelopmentError> {
        run(
            "nft",
            [
                "add",
                "chain",
                "inet",
                &self.names.filter_table,
                "forward",
                "{",
                "type",
                "filter",
                "hook",
                "forward",
                "priority",
                "filter",
                ";",
                "policy",
                "accept",
                ";",
                "}",
            ],
        )?;
        run(
            "nft",
            [
                "add",
                "rule",
                "inet",
                &self.names.filter_table,
                "forward",
                "iifname",
                &self.names.host_interface,
                "ip",
                "saddr",
                "!=",
                CELL_IPV4_CIDR,
                "drop",
            ],
        )?;
        run(
            "nft",
            [
                "add",
                "rule",
                "inet",
                &self.names.filter_table,
                "forward",
                "iifname",
                &self.names.host_interface,
                "ip",
                "saddr",
                CELL_IPV4_CIDR,
                "accept",
            ],
        )?;
        run(
            "nft",
            [
                "add",
                "rule",
                "inet",
                &self.names.filter_table,
                "forward",
                "oifname",
                &self.names.host_interface,
                "ip",
                "daddr",
                CELL_IPV4_CIDR,
                "ct",
                "state",
                "established,related",
                "accept",
            ],
        )?;
        run(
            "nft",
            [
                "add",
                "rule",
                "inet",
                &self.names.filter_table,
                "forward",
                "oifname",
                &self.names.host_interface,
                "drop",
            ],
        )
    }

    fn setup_nat(&mut self) -> Result<(), DevelopmentError> {
        run("nft", ["add", "table", "ip", &self.names.nat_table])?;
        self.resources.push(NetworkResource::NatTable);
        run(
            "nft",
            [
                "add",
                "chain",
                "ip",
                &self.names.nat_table,
                "postrouting",
                "{",
                "type",
                "nat",
                "hook",
                "postrouting",
                "priority",
                "srcnat",
                ";",
                "policy",
                "accept",
                ";",
                "}",
            ],
        )?;
        run(
            "nft",
            [
                "add",
                "rule",
                "ip",
                &self.names.nat_table,
                "postrouting",
                "ip",
                "saddr",
                CELL_IPV4_CIDR,
                "masquerade",
            ],
        )
    }

    /// Remove every object created by this instance in reverse ownership order.
    pub(crate) fn teardown(&mut self) -> Result<(), DevelopmentError> {
        self.teardown_with(
            remove_resource,
            |previous| {
                fs::write(IPV4_FORWARD_PATH, previous)
                    .map_err(|source| io_error("restore host IPv4 forwarding", source))
            },
            |path| remove_file_if_present(path, "remove host IPv4 forwarding state"),
        )
    }

    // The effect boundary is replaceable by owned-file controls in unit tests;
    // production and tests use this same ownership/retirement algorithm.
    fn teardown_with(
        &mut self,
        mut remove: impl FnMut(NetworkResource, &NetworkNames) -> Result<(), DevelopmentError>,
        mut restore_forwarding: impl FnMut(&str) -> Result<(), DevelopmentError>,
        mut remove_record: impl FnMut(&Path) -> Result<(), DevelopmentError>,
    ) -> Result<(), DevelopmentError> {
        while let Some(resource) = self.resources.last().copied() {
            remove(resource, &self.names)?;
            self.resources.pop();
        }
        if let Some(previous) = self.previous_ipv4_forward.as_deref() {
            if !self.forwarding_restored {
                if previous.trim() != "1" {
                    restore_forwarding(previous)?;
                }
                self.forwarding_restored = true;
            }
            // A record-removal failure must not replay a successful global
            // sysctl write on a later retry by this same owner.
            remove_record(&self.forwarding_state_path())?;
            self.previous_ipv4_forward = None;
            self.forwarding_restored = false;
        }
        Ok(())
    }

    /// Remove exact, deterministically named objects left by an interrupted
    /// daemon. This never enumerates or deletes unrelated host networking.
    pub(crate) fn recover(spec: &CellSpec) -> Result<(), DevelopmentError> {
        let names = NetworkNames::for_spec(spec);
        let mut first_error = None;

        record_error(&mut first_error, remove_ufw_rule(&names));
        if nft_table_exists("ip", &names.nat_table)? {
            record_error(
                &mut first_error,
                run("nft", ["delete", "table", "ip", &names.nat_table]),
            );
        }
        if nft_table_exists("inet", &names.filter_table)? {
            record_error(
                &mut first_error,
                run("nft", ["delete", "table", "inet", &names.filter_table]),
            );
        }
        if link_exists(&names.host_interface)? {
            record_error(
                &mut first_error,
                run("ip", ["link", "delete", &names.host_interface]),
            );
        }
        if namespace_exists(&names.namespace)? {
            record_error(
                &mut first_error,
                run("ip", ["netns", "delete", &names.namespace]),
            );
        }
        // Failed object retirement must retain the forwarding recovery record.
        first_error.map_or(Ok(()), Err)?;

        let forwarding_state = spec.runtime_dir.join(IPV4_FORWARD_STATE_FILE);
        match fs::read_to_string(&forwarding_state) {
            Ok(previous) => {
                fs::write(IPV4_FORWARD_PATH, previous).map_err(|source| {
                    io_error("restore stale host IPv4 forwarding state", source)
                })?;
                remove_file_if_present(
                    &forwarding_state,
                    "remove stale host IPv4 forwarding state",
                )?;
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(source) => {
                return Err(io_error("read stale host IPv4 forwarding state", source));
            }
        }

        Ok(())
    }

    fn forwarding_state_path(&self) -> PathBuf {
        // `runtime_dir` has already been created mode 0700 before networking
        // starts, so this recovery record is not exposed to the Android cell.
        self.runtime_dir.join(IPV4_FORWARD_STATE_FILE)
    }
}

fn remove_resource(
    resource: NetworkResource,
    names: &NetworkNames,
) -> Result<(), DevelopmentError> {
    match resource {
        NetworkResource::UfwForwardRule => remove_ufw_rule(names),
        NetworkResource::Namespace => run("ip", ["netns", "delete", &names.namespace]),
        NetworkResource::HostInterface => run("ip", ["link", "delete", &names.host_interface]),
        NetworkResource::FilterTable => {
            run("nft", ["delete", "table", "inet", &names.filter_table])
        }
        NetworkResource::NatTable => run("nft", ["delete", "table", "ip", &names.nat_table]),
    }
}

fn ufw_rule_arguments<'a>(operation: &'a str, names: &'a NetworkNames) -> [&'a str; 13] {
    [
        "-w",
        operation,
        "ufw-user-forward",
        "-i",
        &names.host_interface,
        "-s",
        CELL_IPV4_CIDR,
        "-m",
        "comment",
        "--comment",
        &names.namespace,
        "-j",
        "ACCEPT",
    ]
}

fn ufw_chain_exists() -> Result<bool, DevelopmentError> {
    match droidloom_cpu_placement::command("iptables")
        .args(["-w", "-S", "ufw-user-forward"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
    {
        Ok(status) => Ok(status.success()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(io_error("inspect UFW forwarding chain", error)),
    }
}

fn remove_ufw_rule(names: &NetworkNames) -> Result<(), DevelopmentError> {
    if ufw_chain_exists()? && command_succeeds("iptables", ufw_rule_arguments("-C", names))? {
        run("iptables", ufw_rule_arguments("-D", names))?;
    }
    Ok(())
}

fn command_succeeds<const N: usize>(
    program: &str,
    args: [&str; N],
) -> Result<bool, DevelopmentError> {
    droidloom_cpu_placement::command(program)
        .args(args)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .map_err(|source| io_error(&format!("execute {program}"), source))
}

fn namespace_exists(namespace: &str) -> Result<bool, DevelopmentError> {
    let output = droidloom_cpu_placement::command("ip")
        .args(["netns", "list"])
        .output()
        .map_err(|source| io_error("execute ip", source))?;
    if !output.status.success() {
        return Err(DevelopmentError::Command {
            program: "ip".into(),
            status: output.status,
        });
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter_map(|line| line.split_whitespace().next())
        .any(|name| name == namespace))
}

fn link_exists(interface: &str) -> Result<bool, DevelopmentError> {
    command_succeeds("ip", ["link", "show", "dev", interface])
}

fn nft_table_exists(family: &str, table: &str) -> Result<bool, DevelopmentError> {
    command_succeeds("nft", ["list", "table", family, table])
}

fn remove_file_if_present(path: &Path, context: &str) -> Result<(), DevelopmentError> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(source) => Err(io_error(context, source)),
    }
}

fn run_in_namespace<const N: usize>(
    namespace: &str,
    ip_arguments: [&str; N],
) -> Result<(), DevelopmentError> {
    let mut arguments = vec![
        OsString::from("netns"),
        OsString::from("exec"),
        OsString::from(namespace),
        OsString::from("ip"),
    ];
    arguments.extend(ip_arguments.into_iter().map(OsString::from));
    run_os("ip", arguments)
}

fn run<const N: usize>(program: &str, args: [&str; N]) -> Result<(), DevelopmentError> {
    run_os(program, args.into_iter().map(OsString::from))
}

fn run_os<I>(program: &str, args: I) -> Result<(), DevelopmentError>
where
    I: IntoIterator<Item = OsString>,
{
    let status = droidloom_cpu_placement::command(program)
        .args(args)
        .status()
        .map_err(|source| io_error(&format!("execute {program}"), source))?;
    if status.success() {
        Ok(())
    } else {
        Err(DevelopmentError::Command {
            program: program.into(),
            status,
        })
    }
}

fn record_error(slot: &mut Option<DevelopmentError>, result: Result<(), DevelopmentError>) {
    if let Err(error) = result
        && slot.is_none()
    {
        *slot = Some(error);
    }
}

fn io_error(context: &str, source: std::io::Error) -> DevelopmentError {
    DevelopmentError::Io {
        context: context.into(),
        source,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::IdRange;
    use std::path::PathBuf;

    fn spec(host_uid: u32) -> CellSpec {
        CellSpec {
            host_uid,
            subordinate_uids: IdRange {
                start: 100_000,
                count: 100_000,
            },
            subordinate_gids: IdRange {
                start: 200_000,
                count: 100_000,
            },
            image_dir: PathBuf::from("/images"),
            gapps_dir: None,
            vendor_image: PathBuf::from("/images/vendor.img"),
            android_init: None,
            android_file_overrides: Vec::new(),
            android_runtime_directories: Vec::new(),
            shared_storage_directories: Vec::new(),
            data_dir: PathBuf::from("/data"),
            runtime_dir: PathBuf::from("/run/droidloom/cells/test"),
            render_node: PathBuf::from("/dev/dri/renderD128"),
            graphics_backend: crate::GraphicsBackend::default(),
            denial_socket: PathBuf::from("/run/user/1001/denial.sock"),
        }
    }

    #[test]
    fn network_objects_are_stable_and_interface_names_fit_linux() {
        let names = NetworkNames::for_spec(&spec(1001));
        assert_eq!(names.namespace, "droidloom-u1001");
        assert_eq!(names.host_interface, "dlh1001");
        assert_eq!(names.temporary_cell_interface, "dlc1001");
        assert!(names.host_interface.len() < libc::IF_NAMESIZE);
        assert!(names.temporary_cell_interface.len() < libc::IF_NAMESIZE);
    }

    #[test]
    fn cell_and_gateway_use_the_same_bounded_subnet() {
        assert_eq!(HOST_IPV4_CIDR, "10.177.0.1/30");
        assert_eq!(CELL_IPV4_CIDR, "10.177.0.2/32");
    }

    fn cleanup_owner(directory: &Path, resources: Vec<NetworkResource>) -> DevelopmentNetwork {
        DevelopmentNetwork {
            names: NetworkNames::for_spec(&spec(1001)),
            runtime_dir: directory.to_owned(),
            resources,
            previous_ipv4_forward: Some("0\n".into()),
            forwarding_restored: false,
        }
    }

    #[test]
    fn failed_network_effect_retains_itself_and_lower_ownership_steps() {
        let directory = tempfile::tempdir().unwrap();
        let blocker = directory.path().join("owned-delete-target");
        fs::create_dir(&blocker).unwrap();
        let mut network = cleanup_owner(
            directory.path(),
            vec![
                NetworkResource::Namespace,
                NetworkResource::HostInterface,
                NetworkResource::FilterTable,
                NetworkResource::NatTable,
            ],
        );
        fs::write(network.forwarding_state_path(), "0\n").unwrap();
        let mut observed = Vec::new();
        for _ in 0..2 {
            let result = network.teardown_with(
                |resource, names| {
                    assert_eq!(names.namespace, "droidloom-u1001");
                    observed.push(resource);
                    if resource == NetworkResource::HostInterface {
                        fs::remove_file(&blocker)
                            .map_err(|source| io_error("owned test resource removal", source))?;
                    }
                    Ok(())
                },
                |_| panic!("must not restore forwarding below an unretired resource"),
                |_| panic!("must retain recovery record below an unretired resource"),
            );
            assert!(result.is_err());
            assert_eq!(
                network.resources,
                vec![NetworkResource::Namespace, NetworkResource::HostInterface]
            );
            assert_eq!(
                fs::read_to_string(network.forwarding_state_path()).unwrap(),
                "0\n"
            );
        }
        assert_eq!(
            observed,
            vec![
                NetworkResource::NatTable,
                NetworkResource::FilterTable,
                NetworkResource::HostInterface,
                NetworkResource::HostInterface
            ]
        );
        fs::remove_dir(&blocker).unwrap();
        fs::write(&blocker, "owned target").unwrap();
        let owned_forwarding = directory.path().join("owned-forwarding-value");
        network
            .teardown_with(
                |resource, _| {
                    observed.push(resource);
                    if resource == NetworkResource::HostInterface {
                        fs::remove_file(&blocker)
                            .map_err(|source| io_error("owned resource removal", source))?;
                    }
                    Ok(())
                },
                |previous| {
                    fs::write(&owned_forwarding, previous)
                        .map_err(|source| io_error("owned forwarding restore", source))
                },
                |path| remove_file_if_present(path, "owned record removal"),
            )
            .unwrap();
        assert!(network.resources.is_empty());
        assert!(network.previous_ipv4_forward.is_none());
        assert_eq!(fs::read_to_string(&owned_forwarding).unwrap(), "0\n");
        assert!(!network.forwarding_state_path().exists());
    }

    #[test]
    fn failed_forwarding_restore_keeps_the_original_recovery_record() {
        let directory = tempfile::tempdir().unwrap();
        let mut network = cleanup_owner(directory.path(), Vec::new());
        fs::write(network.forwarding_state_path(), "0\n").unwrap();
        let owned_forwarding = directory.path().join("owned-forwarding-value");
        fs::create_dir(&owned_forwarding).unwrap();
        for _ in 0..2 {
            assert!(
                network
                    .teardown_with(
                        |_, _| panic!("no network objects in this control"),
                        |previous| fs::write(&owned_forwarding, previous)
                            .map_err(|source| io_error("owned forwarding restore", source)),
                        |_| panic!("failed restore must not remove its recovery record"),
                    )
                    .is_err()
            );
            assert_eq!(network.previous_ipv4_forward.as_deref(), Some("0\n"));
            assert!(!network.forwarding_restored);
            assert_eq!(
                fs::read_to_string(network.forwarding_state_path()).unwrap(),
                "0\n"
            );
        }
        fs::remove_dir(&owned_forwarding).unwrap();
        network
            .teardown_with(
                |_, _| panic!("no network objects in this control"),
                |previous| {
                    fs::write(&owned_forwarding, previous)
                        .map_err(|source| io_error("owned forwarding restore", source))
                },
                |path| remove_file_if_present(path, "owned record removal"),
            )
            .unwrap();
        assert!(network.previous_ipv4_forward.is_none());
    }

    #[test]
    fn failed_record_removal_does_not_replay_a_successful_forwarding_restore() {
        let directory = tempfile::tempdir().unwrap();
        let mut network = cleanup_owner(directory.path(), Vec::new());
        fs::create_dir(network.forwarding_state_path()).unwrap();
        let owned_forwarding = directory.path().join("owned-forwarding-value");
        let mut restores = 0;
        for _ in 0..2 {
            assert!(
                network
                    .teardown_with(
                        |_, _| panic!("no network objects in this control"),
                        |previous| {
                            restores += 1;
                            fs::write(&owned_forwarding, previous)
                                .map_err(|source| io_error("owned forwarding restore", source))
                        },
                        |path| remove_file_if_present(path, "owned record removal"),
                    )
                    .is_err()
            );
            assert_eq!(restores, 1);
            assert!(network.forwarding_restored);
            assert!(network.previous_ipv4_forward.is_some());
            fs::write(&owned_forwarding, "changed by another owner\n").unwrap();
        }
        fs::remove_dir(network.forwarding_state_path()).unwrap();
        fs::write(network.forwarding_state_path(), "0\n").unwrap();
        network
            .teardown_with(
                |_, _| panic!("no network objects in this control"),
                |_| panic!("must not replay a completed forwarding restore"),
                |path| remove_file_if_present(path, "owned record removal"),
            )
            .unwrap();
        assert!(network.previous_ipv4_forward.is_none());
        assert!(!network.forwarding_restored);
        assert!(!network.forwarding_state_path().exists());
        assert_eq!(
            fs::read_to_string(&owned_forwarding).unwrap(),
            "changed by another owner\n"
        );
    }
}
