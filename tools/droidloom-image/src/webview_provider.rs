//! Admission of one reviewed, unchanged Google WebView APK.
//!
//! The compiled profile binds the complete APK to a retained SDK 37 signature,
//! manifest, and normal presigned-import preflight. This separate public input
//! is not one of the 29 official GSI vendor link references. Exact input bytes
//! establish neither latest-version status nor preload or runtime qualification.

use crate::official_gsi::{hash_file, identity, open_absolute, require_original};
use crate::{PrepareError, io_error};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard};
use std::time::{Duration, Instant};

type Result<T> = std::result::Result<T, PrepareError>;
const PROFILE_BODY: &[u8] = include_bytes!("../../../android/manifest/webview-provider.json");
/// SHA256 of the complete compiled review profile, including the SDK result pin.
pub const PROFILE_SHA256: &str = "3aa15b10d91819ce249707cc9521706195723bb3384a7d9eaea983143ba1bebb";
/// Exact size of the single, complete reviewed APK.
pub const APK_BYTES: u64 = 365_700_497;
/// SHA256 of the unchanged upstream signed APK.
pub const APK_SHA256: &str = "66b5e41ab63a92aad6426c6c85037534e153370d373fa2a9cccfc4d16147892e";
/// Only provider package accepted by this profile.
pub const PACKAGE_NAME: &str = "com.google.android.webview";
/// Reviewed version; a newer .93 release is known.
pub const VERSION_NAME: &str = "158.0.8127.92";
/// Version code observed by the normal SDK 37 tools.
pub const VERSION_CODE: u64 = 812_709_208;
/// SHA256 of the APK application's DER signing certificate, not its source stamp.
pub const SIGNER_CERTIFICATE_SHA256: &str =
    "6faf3c4140407473400934d117815a21af1cfefc5c0bee61c858bc3d72ba6fe5";

const SDK_RESULT_SHA256: &str = "da7b5ef803409ca2aecd15088fbe5bbedb864a083379230abb23682e0009434f";
const LIMIT: Duration = Duration::from_secs(180);
const READ_BUFFER: usize = 64 * 1024;

fn rejected(message: impl Into<String>) -> PrepareError {
    PrepareError::Verification(message.into())
}

fn reviewed_profile() -> Result<Value> {
    if hex::encode(Sha256::digest(PROFILE_BODY)) != PROFILE_SHA256 {
        return Err(rejected(
            "compiled WebView profile changed without its review pin",
        ));
    }
    let profile: Value = serde_json::from_slice(PROFILE_BODY)
        .map_err(|error| rejected(format!("invalid compiled WebView profile: {error}")))?;
    if profile["schema"] != "droidloom-reviewed-webview-provider-v1"
        || profile["package_name"] != PACKAGE_NAME
        || profile["version_name"] != VERSION_NAME
        || profile["version_code"] != VERSION_CODE
        || profile["apk"] != json!({"bytes": APK_BYTES, "sha256": APK_SHA256})
        || profile["signer_certificate"]
            != json!({"encoding":"DER","bytes":959,"sha256":SIGNER_CERTIFICATE_SHA256})
        || profile["android_manifest"]
            != json!({
                "min_sdk":32, "target_sdk":36, "compile_sdk":37,
                "abis":["x86","x86_64"], "base_apk_count":1,
                "split_names":[], "uses_split":[], "uses_static_library":[],
                "optional_uses_libraries":[
                    "android.test.base", "androidx.window.extensions", "android.ext.adservices"
                ]
            })
        || profile["sdk37_preflight"]["schema"] != "p4.public-webview-sdk37-preflight.v1"
        || profile["sdk37_preflight"]["bytes"] != 19_133
        || profile["sdk37_preflight"]["sha256"] != SDK_RESULT_SHA256
        || profile["known_newer_version"] != "158.0.8127.93"
        || profile["provenance"]["upstream_apk_modified"] != false
        || profile["provenance"]["official_vendor_reference_member"] != false
        || profile["provenance"]["source_revision_equivalence_claimed"] != false
        || [
            "latest_qualified",
            "normal_preload_qualified",
            "runtime_qualified",
            "business_qualified",
            "production_ready",
        ]
        .iter()
        .any(|key| profile[*key] != false)
    {
        return Err(rejected(
            "compiled WebView profile changes the reviewed input-only scope",
        ));
    }
    Ok(profile)
}

#[derive(Debug)]
struct HeldInput {
    // One mutex also serializes the shared seek offset for concurrent &self calls.
    file: Mutex<File>,
    path: PathBuf,
    f9: [u64; 9],
    bytes: u64,
    sha256: String,
}

impl HeldInput {
    fn open(path: &Path, bytes: u64, sha256: &str) -> Result<Self> {
        if path.to_str().is_none()
            || bytes == 0
            || bytes > APK_BYTES
            || sha256.len() != 64
            || !sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(rejected("invalid bounded WebView file pin"));
        }
        let mut file = open_absolute(path, false)?;
        let metadata = file
            .metadata()
            .map_err(|error| io_error("stat held WebView APK", error))?;
        if !metadata.is_file() || metadata.nlink() != 1 || metadata.len() != bytes {
            return Err(rejected(
                "WebView APK must be its exact single-link regular file",
            ));
        }
        let f9 = identity(&metadata)?;
        require_original(&file, path, &f9)?;
        let actual = hash_file(&mut file, bytes, Instant::now() + LIMIT)?;
        require_original(&file, path, &f9)?;
        if actual != sha256 {
            return Err(rejected(
                "WebView APK SHA256 differs from the reviewed input",
            ));
        }
        Ok(Self {
            file: Mutex::new(file),
            path: path.to_owned(),
            f9,
            bytes,
            sha256: sha256.into(),
        })
    }

    fn lock(&self) -> Result<MutexGuard<'_, File>> {
        self.file
            .lock()
            .map_err(|_| rejected("WebView input reader lost its held-file custody"))
    }

    fn verify_locked(&self, file: &mut File, deadline: Instant) -> Result<()> {
        require_original(file, &self.path, &self.f9)?;
        let actual = hash_file(file, self.bytes, deadline)?;
        require_original(file, &self.path, &self.f9)?;
        if actual != self.sha256 {
            return Err(rejected("held WebView APK bytes changed"));
        }
        Ok(())
    }

    fn verify(&self) -> Result<()> {
        let mut file = self.lock()?;
        self.verify_locked(&mut file, Instant::now() + LIMIT)
    }

    fn bytes_for_projection(&self) -> Result<Vec<u8>> {
        let mut file = self.lock()?;
        let deadline = Instant::now() + LIMIT;
        self.verify_locked(&mut file, deadline)?;
        file.seek(SeekFrom::Start(0))
            .map_err(|error| io_error("seek reviewed WebView APK", error))?;
        let capacity = usize::try_from(self.bytes)
            .map_err(|_| rejected("WebView projection does not fit this address space"))?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(capacity)
            .map_err(|error| rejected(format!("reserve bounded WebView projection: {error}")))?;
        let mut buffer = [0u8; READ_BUFFER];
        let mut digest = Sha256::new();
        loop {
            if Instant::now() >= deadline {
                return Err(rejected(
                    "WebView projection exceeded its bounded read deadline",
                ));
            }
            let count = file
                .read(&mut buffer)
                .map_err(|error| io_error("read held WebView APK for projection", error))?;
            if count == 0 {
                break;
            }
            if bytes
                .len()
                .checked_add(count)
                .is_none_or(|total| total > capacity)
            {
                return Err(rejected("WebView APK grew during projection"));
            }
            digest.update(&buffer[..count]);
            bytes.extend_from_slice(&buffer[..count]);
        }
        require_original(&file, &self.path, &self.f9)?;
        if bytes.len() != capacity || hex::encode(digest.finalize()) != self.sha256 {
            return Err(rejected(
                "WebView projection differs from the complete reviewed APK",
            ));
        }
        // Check the held input again after the entire copy; only then expose bytes.
        self.verify_locked(&mut file, deadline)?;
        Ok(bytes)
    }
}

/// A complete reviewed APK retained by its original open descriptor and full F9.
/// Fields are private; a caller cannot supply a success flag or an alternate pin.
#[derive(Debug)]
pub struct VerifiedWebView {
    input: HeldInput,
    profile: Value,
}

/// Verify the exact compiled profile and hold its single-link, unaliased APK.
pub fn verify_webview_provider(path: &Path) -> Result<VerifiedWebView> {
    let profile = reviewed_profile()?;
    let input = HeldInput::open(path, APK_BYTES, APK_SHA256)?;
    Ok(VerifiedWebView { input, profile })
}

impl VerifiedWebView {
    /// Reopen the original name and rehash the held descriptor with full F9 bookends.
    pub fn verify_unchanged(&self) -> Result<()> {
        self.input.verify()
    }

    /// Return the unchanged upstream bytes after bounded copying and both full hashes.
    pub fn bytes_for_projection(&self) -> Result<Vec<u8>> {
        self.input.bytes_for_projection()
    }

    /// Fresh input identity and the pinned historical SDK evidence, without runtime claims.
    pub fn receipt(&self) -> Result<Value> {
        let mut file = self.input.lock()?;
        self.input
            .verify_locked(&mut file, Instant::now() + LIMIT)?;
        let receipt = json!({
            "schema":"droidloom.verified-webview-provider.v1",
            "profile_sha256":PROFILE_SHA256,
            "reviewed_profile":self.profile,
            "apk":{
                "path":self.input.path, "bytes":APK_BYTES, "sha256":APK_SHA256,
                "f9":self.input.f9
            },
            "package_name":PACKAGE_NAME,
            "version_name":VERSION_NAME,
            "version_code":VERSION_CODE,
            "signer_certificate_sha256":SIGNER_CERTIFICATE_SHA256,
            "sdk37_preflight":self.profile["sdk37_preflight"],
            "upstream_apk_modified":false,
            "official_vendor_reference_member":false,
            "known_newer_version":"158.0.8127.93",
            "latest_qualified":false,
            "normal_preload_qualified":false,
            "runtime_qualified":false,
            "business_qualified":false,
            "production_ready":false
        });
        require_original(&file, &self.input.path, &self.input.f9)?;
        Ok(receipt)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::ffi::OsStringExt;
    use std::os::unix::fs::symlink;

    fn fixture() -> (tempfile::TempDir, PathBuf, Vec<u8>, String) {
        let directory = tempfile::tempdir().expect("fixture directory");
        let path = directory.path().join("provider.apk");
        let bytes = b"tiny held APK identity fixture\n".to_vec();
        fs::write(&path, &bytes).expect("fixture bytes");
        let sha256 = hex::encode(Sha256::digest(&bytes));
        (directory, path, bytes, sha256)
    }

    #[test]
    fn reviewed_profile_binds_sdk_evidence_without_latest_or_runtime_claims() {
        let profile = reviewed_profile().expect("reviewed compiled profile");
        assert_eq!(profile["sdk37_preflight"]["sha256"], SDK_RESULT_SHA256);
        assert_eq!(profile["android_manifest"]["min_sdk"], 32);
        assert_eq!(profile["latest_qualified"], false);
        assert_eq!(profile["runtime_qualified"], false);
        assert_eq!(profile["production_ready"], false);
        let (_directory, path, bytes, sha256) = fixture();
        let held = HeldInput::open(&path, bytes.len() as u64, &sha256).expect("tiny held input");
        assert_eq!(held.bytes_for_projection().expect("exact copy"), bytes);
        held.verify().expect("input remains original");
        // The production factory never accepts the small test pin.
        assert!(verify_webview_provider(&path).is_err());
    }

    #[test]
    fn same_length_mutation_of_the_held_inode_is_rejected() {
        let (_directory, path, bytes, sha256) = fixture();
        let held = HeldInput::open(&path, bytes.len() as u64, &sha256).unwrap();
        let mut changed = bytes;
        changed[0] ^= 1;
        fs::write(&path, changed).unwrap();
        assert!(held.verify().is_err());
        assert!(held.bytes_for_projection().is_err());
    }

    #[test]
    fn same_bytes_replacement_is_not_the_held_input() {
        let (directory, path, bytes, sha256) = fixture();
        let held = HeldInput::open(&path, bytes.len() as u64, &sha256).unwrap();
        let replacement = directory.path().join("replacement.apk");
        fs::write(&replacement, &bytes).unwrap();
        fs::rename(replacement, &path).unwrap();
        assert!(held.verify().is_err());
        assert!(held.bytes_for_projection().is_err());
    }

    #[test]
    fn original_or_new_hardlink_is_rejected() {
        let (directory, path, bytes, sha256) = fixture();
        let alias = directory.path().join("hardlink.apk");
        fs::hard_link(&path, &alias).unwrap();
        assert!(HeldInput::open(&path, bytes.len() as u64, &sha256).is_err());
        fs::remove_file(&alias).unwrap();
        let held = HeldInput::open(&path, bytes.len() as u64, &sha256).unwrap();
        fs::hard_link(&path, &alias).unwrap();
        assert!(held.verify().is_err());
        assert!(held.bytes_for_projection().is_err());
    }

    #[test]
    fn aliases_in_any_path_component_are_rejected() {
        let (directory, path, bytes, sha256) = fixture();
        let leaf_alias = directory.path().join("leaf-alias.apk");
        symlink(&path, &leaf_alias).unwrap();
        assert!(HeldInput::open(&leaf_alias, bytes.len() as u64, &sha256).is_err());
        let parent_alias = directory.path().join("parent-alias");
        symlink(directory.path(), &parent_alias).unwrap();
        assert!(
            HeldInput::open(
                &parent_alias.join("provider.apk"),
                bytes.len() as u64,
                &sha256
            )
            .is_err()
        );
        let nested = directory.path().join("nested");
        fs::create_dir(&nested).unwrap();
        let original = nested.join("provider.apk");
        fs::rename(&path, &original).unwrap();
        let held = HeldInput::open(&original, bytes.len() as u64, &sha256).unwrap();
        let moved = directory.path().join("moved");
        fs::rename(&nested, &moved).unwrap();
        symlink(&moved, &nested).unwrap();
        assert!(held.verify().is_err());
        assert!(held.bytes_for_projection().is_err());
    }

    #[test]
    fn bounds_regular_file_and_exact_hash_are_enforced() {
        let (directory, path, bytes, sha256) = fixture();
        assert!(HeldInput::open(&path, bytes.len() as u64 + 1, &sha256).is_err());
        assert!(HeldInput::open(&path, bytes.len() as u64 - 1, &sha256).is_err());
        assert!(HeldInput::open(&path, APK_BYTES + 1, &sha256).is_err());
        assert!(HeldInput::open(&path, 0, &sha256).is_err());
        assert!(HeldInput::open(&path, bytes.len() as u64, &"0".repeat(64)).is_err());
        assert!(HeldInput::open(directory.path(), bytes.len() as u64, &sha256).is_err());
        let noncanonical = directory.path().join(".").join("provider.apk");
        assert!(HeldInput::open(&noncanonical, bytes.len() as u64, &sha256).is_err());
        assert!(HeldInput::open(Path::new("relative.apk"), bytes.len() as u64, &sha256).is_err());
        let non_utf8 = directory
            .path()
            .join(std::ffi::OsString::from_vec(b"non-utf8-\xff.apk".to_vec()));
        fs::write(&non_utf8, &bytes).unwrap();
        assert!(HeldInput::open(&non_utf8, bytes.len() as u64, &sha256).is_err());
    }

    #[test]
    fn concurrent_readers_keep_one_held_seek_offset() {
        let (_directory, path, bytes, sha256) = fixture();
        let held = HeldInput::open(&path, bytes.len() as u64, &sha256).unwrap();
        std::thread::scope(|scope| {
            let first = scope.spawn(|| held.bytes_for_projection().unwrap());
            let second = scope.spawn(|| held.bytes_for_projection().unwrap());
            assert_eq!(first.join().unwrap(), bytes);
            assert_eq!(second.join().unwrap(), bytes);
        });
        held.verify().unwrap();
    }
}
