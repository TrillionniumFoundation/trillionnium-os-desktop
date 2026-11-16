fn main() {
    let a = std::env::args().collect::<Vec<_>>();
    let result = if a.len() == 4 && a[1] == "--inspect-original-platform-policy" {
        droidloom_first_init_policy_sources::inspect_original_platform_sources(
            std::path::Path::new(&a[2]),
            std::path::Path::new(&a[3]),
        )
    } else if a.len() == 3 && a[1] == "--guest-selinux-requirements" {
        droidloom_first_init_policy_sources::selected_private_guest_selinux_requirements(
            std::path::Path::new(&a[2]),
        )
    } else {
        Err("usage: --inspect-original-platform-policy EXACT_PUBLIC_SOURCE_COPY_ROOT NEW_OUTPUT | --guest-selinux-requirements ACTUAL_PUBLIC_CONFIG_ROOT".into())
    };
    match result {
        Ok(v) => println!("{}", serde_json::to_string_pretty(&v).unwrap()),
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1)
        }
    }
}
