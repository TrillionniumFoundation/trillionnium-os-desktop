//! Build-size feasibility only. This is not the Agentd daemon or a G2 verdict.
use codex_hepta_agentd::AgentdHos2Device;
use std::fs::OpenOptions;

fn main() -> Result<(), String> {
    // AT_HEPTA_BOOT=240 is supplied by the original sealed Asterinas loader.
    // No argument, environment variable or caller-supplied bootstrap is accepted.
    // SAFETY: getauxval reads this process's kernel-created auxiliary vector.
    let address = unsafe { libc::getauxval(240) } as usize;
    if address == 0 || address % 4096 != 0
        || address.checked_add(192).is_none_or(|end| end > (1usize << 47)) {
        return Err("no bounded kernel HOS2 bootstrap page".to_string());
    }
    // SAFETY: in this x86_64 sealed-loader ABI, a nonzero AT_HEPTA_BOOT points
    // to a mapped read-only 4096-byte discovery page retained for the image.
    // The constructor validates the complete 192-byte protocol and QueryAbi.
    let bootstrap = unsafe { std::slice::from_raw_parts(address as *const u8, 192) };
    let file = OpenOptions::new().read(true).write(true).open("/dev/hepta-control")
        .map_err(|error| format!("open original HOS2 device: {error}"))?;
    let device = AgentdHos2Device::from_bootstrap(file, bootstrap)?;
    let usage = device.read_usage(1)?;
    println!("ORIGINAL_AGENTD_DEVICE_READ revision={} sample_ns={} cpu_ns={} cap_ns={} durable=false",
        usage.revision, usage.sample_boottime_ns, usage.cumulative_cpu_ns, usage.active_cap_ns);
    Ok(())
}
