//! Explicit administrator-only fresh or exact existing-state recovery entry.
#[cfg(target_os = "linux")]
#[path = "../product_root/mod.rs"]
mod product_root;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(target_os = "linux")]
    {
        let mut args = std::env::args_os().skip(1);
        let action = args.next();
        if action.as_deref() == Some(std::ffi::OsStr::new("admin")) {
            return product_root::administer(args);
        }
        let flag = args.next();
        let path = args.next();
        if flag.as_deref() != Some(std::ffi::OsStr::new("--config")) || path.is_none() {
            return Err("expected initialize --config <Notes-Root0600-input>, initialize-desktop --config <joint-v2-Root0600-input>, recover --config <same-Notes-input> (--operation-id <original-id> | --latest-original-notes), or recover-desktop --config <same-joint-input> --previous-generation <n> (--latest-original-desktop | --notes-operation-id <id> --calculator-operation-id <id>)".into());
        }
        let path = std::path::Path::new(path.as_ref().ok_or("missing config")?);
        match action.as_deref().and_then(std::ffi::OsStr::to_str) {
            Some("initialize") if args.next().is_none() => product_root::initialize(path),
            Some("initialize-desktop") if args.next().is_none() => {
                product_root::initialize_desktop(path)
            }
            Some("recover") => {
                let selection = product_root::RecoverySelection::from_arguments(args)?;
                product_root::recover(path, selection)
            }
            Some("recover-desktop") => {
                let (generation, selection) =
                    product_root::RecoverySelection::from_desktop_arguments(args)?;
                product_root::recover_desktop(path, generation, selection)
            }
            _ => Err("unknown or repeated original Root action".into()),
        }
    }
    #[cfg(not(target_os = "linux"))]
    {
        Err("the original first-product Root entry requires Linux".into())
    }
}
