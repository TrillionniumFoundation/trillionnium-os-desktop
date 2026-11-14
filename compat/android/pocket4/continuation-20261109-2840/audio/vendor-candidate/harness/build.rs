use std::{env, fs, path::PathBuf};
fn main() {
    let harness = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let source = harness.parent().unwrap().join("source/tools/droidloom-update/src");
    for name in ["audio_vendor_candidate.rs", "audio_vendor_candidate/tests.rs", "audio_vendor_zip.rs"] {
        let original = source.join(name);
        let compiled = harness.join("src").join(name);
        assert_eq!(fs::read(&original).unwrap(), fs::read(&compiled).unwrap(), "CI fixture differs from exact updater source: {name}");
        println!("cargo:rerun-if-changed={}", original.display());
        println!("cargo:rerun-if-changed={}", compiled.display());
    }
}
