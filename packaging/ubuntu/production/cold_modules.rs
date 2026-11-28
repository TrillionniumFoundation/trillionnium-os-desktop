//! Source-owned cold deployment modules published by the normal host stage.
//! These are readonly inputs, not new production maintenance commands.
pub(crate) const FILES: &[(&str, &[u8])] = &[
    (
        "usr/lib/droidloom/production/current/release.py",
        include_bytes!("release.py"),
    ),
    (
        "usr/lib/droidloom/production/current/cold_publish.py",
        include_bytes!("cold_publish.py"),
    ),
    (
        "usr/lib/droidloom/production/current/cold_transaction.py",
        include_bytes!("cold_transaction.py"),
    ),
    (
        "usr/lib/droidloom/production/current/cold_apply.py",
        include_bytes!("cold_apply.py"),
    ),
    (
        "usr/lib/droidloom/production/current/native_bundle.py",
        include_bytes!("native_bundle.py"),
    ),
    (
        "usr/lib/droidloom/production/current/systemd_bundle.py",
        include_bytes!("systemd_bundle.py"),
    ),
    (
        "usr/lib/droidloom/production/current/native_release.py",
        include_bytes!("native_release.py"),
    ),
    (
        "usr/lib/droidloom/production/current/cold_native.py",
        include_bytes!("cold_native.py"),
    ),
];
