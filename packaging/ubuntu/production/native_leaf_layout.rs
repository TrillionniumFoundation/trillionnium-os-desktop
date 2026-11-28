//! Fixed initial layout for the normal native-leaf publisher.
//! These markers create no CURRENT, release, plan, lease or runtime qualification.
pub const MODE: u32 = 0o444;
pub const BODY: &[u8] = b"pocket4-native-application-leaf-layout-v1\n";
pub const FILES: [(&str, &[u8]); 3] = [
    ("etc/droidloom/native-application-leaves/catalogs/.layout", BODY),
    ("etc/droidloom/native-application-leaves/current-preimages/.layout", BODY),
    ("etc/droidloom/native-application-leaves/releases/.layout", BODY),
];
