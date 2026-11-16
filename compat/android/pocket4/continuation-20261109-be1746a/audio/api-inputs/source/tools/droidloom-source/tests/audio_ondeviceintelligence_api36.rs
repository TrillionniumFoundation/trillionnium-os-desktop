//! Regression for original SDK tracking files consumed by prebuilt_apis.
//! This checks the sparse input contract, not a complete Soong graph.

use std::collections::BTreeSet;
use std::path::Path;

use droidloom_source::{SparseSourceLock, build_plan};
use serde_json::Value;
use sha2::{Digest, Sha256};

#[test]
fn audio_ondeviceintelligence_released_api_provider_inputs_are_selected() {
    let fixture: Value = serde_json::from_str(include_str!(
        "fixtures/ondeviceintelligence-api36/provider-inputs.json"
    ))
    .expect("pinned original SDK fixture");
    let original_body =
        include_bytes!("fixtures/ondeviceintelligence-api36/signature-format-2.0.txt");
    let body_sha256 = hex::encode(Sha256::digest(original_body));
    let files = fixture["original_files"]
        .as_array()
        .expect("original files");
    assert_eq!(files.len(), 4);
    let mut scopes = BTreeSet::new();
    for file in files {
        let path = file["path"].as_str().expect("original path");
        scopes.insert(path.split('/').nth(1).expect("API scope"));
        assert_eq!(file["bytes"].as_u64(), Some(original_body.len() as u64));
        assert_eq!(file["sha256"].as_str(), Some(body_sha256.as_str()));
        assert_eq!(
            file["git_blob"].as_str(),
            Some("d802177e249b3f97128699222e65c35e57ba7540")
        );
    }
    assert_eq!(scopes, BTreeSet::from(["public", "system-server"]));

    let lock: SparseSourceLock = serde_json::from_str(include_str!(
        "../../../android/manifest/audio-bridge-source-lock.json"
    ))
    .expect("normal Audio source lock");
    let plan = build_plan(&lock).expect("unchanged normal source policies");
    let sdk = plan
        .projects
        .iter()
        .find(|project| project.path == Path::new("prebuilts/sdk"))
        .expect("pinned SDK project");
    assert_eq!(
        sdk.commit,
        fixture["sdk_commit"].as_str().expect("SDK commit")
    );
    let missing: Vec<_> = files
        .iter()
        .filter_map(|file| {
            let path = Path::new(file["path"].as_str().expect("original path"));
            (!sdk
                .sparse_paths
                .iter()
                .any(|selected| path == selected || path.starts_with(selected)))
            .then(|| path.display().to_string())
        })
        .collect();
    assert!(
        missing.is_empty(),
        "original SDK 36 public/system-server API provider inputs omitted: {missing:?}"
    );
}
