//! Explicit administrator-only fresh or exact existing-state recovery entry.
#[cfg(target_os = "linux")]
#[path = "../product_root/mod.rs"]
mod product_root;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(target_os = "linux")]
    {
        let mut args = std::env::args_os().skip(1);
        let action = args.next();
        let flag = args.next();
        let path = args.next();
        if flag.as_deref() != Some(std::ffi::OsStr::new("--config")) || path.is_none() {
            return Err("expected initialize --config <Root0600-input> or recover --config <same-input> --operation-id <original-id>".into());
        }
        let path = std::path::Path::new(path.as_ref().ok_or("missing config")?);
        match action.as_deref().and_then(std::ffi::OsStr::to_str) {
            Some("initialize") if args.next().is_none() => product_root::initialize(path),
            Some("recover") => {
                if args.next().as_deref() != Some(std::ffi::OsStr::new("--operation-id")) {
                    return Err("recovery requires an explicit original operation selector".into());
                }
                let operation = args.next().ok_or("missing original operation selector")?;
                if args.next().is_some() {
                    return Err("unexpected recovery argument".into());
                }
                product_root::recover(
                    path,
                    operation
                        .to_str()
                        .ok_or("operation selector must be UTF-8")?,
                )
            }
            _ => Err("unknown or repeated original Root action".into()),
        }
    }
    #[cfg(not(target_os = "linux"))]
    {
        Err("the original first-product Root entry requires Linux".into())
    }
}
