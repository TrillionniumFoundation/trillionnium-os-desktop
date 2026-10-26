//! Explicit administrator-only fresh product entry. No restore fallback.
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
        if action.as_deref() != Some(std::ffi::OsStr::new("initialize"))
            || flag.as_deref() != Some(std::ffi::OsStr::new("--config"))
            || path.is_none()
            || args.next().is_some()
        {
            return Err("expected initialize --config <Root0600-input>; existing/partial deployment is refused".into());
        }
        product_root::initialize(std::path::Path::new(path.as_ref().ok_or("missing config")?))
    }
    #[cfg(not(target_os = "linux"))]
    {
        Err("the original first-product Root entry requires Linux".into())
    }
}
