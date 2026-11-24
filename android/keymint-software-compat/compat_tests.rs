// SPDX-License-Identifier: Apache-2.0
//! Synthetic keyblob migration tests. No userdata or caller keys are read.
//! Legacy instances use the historical profile only inside this test module.

use super::*;
use kmr_common::keyblob::{
    EncryptedKeyBlob, LegacyKeyHandler, PlaintextKeyBlob, SecureDeletionSlot,
};
use kmr_common::Error;
use kmr_ta::HalInfo;
use kmr_wire::keymint::{
    Algorithm, BootInfo, Digest, ErrorCode, KeyCharacteristics, KeyCreationResult, KeyParam,
    KeyPurpose, VerifiedBootState,
};
use kmr_wire::*;

const APP_ID: &[u8] = b"synthetic-app-id";
const APP_DATA: &[u8] = b"synthetic-app-data";

fn boot() -> BootInfo {
    BootInfo {
        verified_boot_key: vec![0; 32],
        device_boot_locked: false,
        verified_boot_state: VerifiedBootState::Unverified,
        verified_boot_hash: vec![0; 32],
        boot_patchlevel: 20260605,
    }
}

fn configured(mut ta: KeyMintTa, info: BootInfo, os: u32) -> KeyMintTa {
    ta.set_boot_info(info).expect("configure synthetic boot root");
    ta.set_hal_info(HalInfo { os_version: os, os_patchlevel: 202606, vendor_patchlevel: 20260605 });
    ta
}

fn software() -> KeyMintTa {
    configured(build_ta(), boot(), 170000)
}

// The test-only constructor matches the historical reference provider's key
// source, crypto, no-SDD profile and root handling. It does not ship in a service.
fn profile(level: SecurityLevel, legacy: Option<Box<dyn LegacyKeyHandler>>) -> KeyMintTa {
    let hw = HardwareInfo {
        version_number: 1,
        security_level: level,
        impl_name: "synthetic compatibility fixture",
        author_name: "test",
        unique_id: "synthetic-only",
    };
    let rpc_info = RpcInfo::V3(RpcInfoV3 {
        author_name: "test",
        unique_id: "synthetic-only",
        fused: false,
        supported_num_of_keys_in_csr: MINIMUM_SUPPORTED_KEYS_IN_CSR,
    });
    let dev = Implementation {
        keys: Box::new(soft::Keys),
        sign_info: Some(Box::new(attest::CertSignInfo::new())),
        attest_ids: None,
        sdd_mgr: None,
        bootloader: Box::new(BootloaderDone),
        sk_wrapper: None,
        tup: Box::new(TrustedPresenceUnsupported),
        legacy_key: legacy,
        rpc: Box::new(soft::RpcArtifacts::new(soft::Derive::default(), CsrSigningAlgorithm::EdDSA)),
    };
    KeyMintTa::new(hw, rpc_info, boringssl_crypto_impls(), dev)
}

fn legacy() -> KeyMintTa {
    configured(profile(SecurityLevel::TrustedEnvironment, None), boot(), 170000)
}

fn hidden() -> Vec<KeyParam> {
    vec![KeyParam::ApplicationId(APP_ID.to_vec()), KeyParam::ApplicationData(APP_DATA.to_vec())]
}

fn key_params() -> Vec<KeyParam> {
    let mut params = vec![
        KeyParam::Algorithm(Algorithm::Hmac),
        KeyParam::KeySize(KeySizeInBits(256)),
        KeyParam::Purpose(KeyPurpose::Sign),
        KeyParam::Digest(Digest::Sha256),
        KeyParam::MinMacLength(128),
        KeyParam::NoAuthRequired,
    ];
    params.extend(hidden());
    params
}

fn call(ta: &mut KeyMintTa, request: PerformOpReq) -> Result<PerformOpRsp, i32> {
    let request = request.into_vec().expect("encode test request");
    let response =
        PerformOpResponse::from_slice(&ta.process(&request)).expect("decode test response");
    if response.error_code == 0 {
        Ok(response.rsp.expect("success must carry a response"))
    } else {
        Err(response.error_code)
    }
}

fn generate(ta: &mut KeyMintTa, params: Vec<KeyParam>) -> KeyCreationResult {
    match call(
        ta,
        PerformOpReq::DeviceGenerateKey(GenerateKeyRequest {
            key_params: params,
            attestation_key: None,
        }),
    )
    .expect("generate synthetic key")
    {
        PerformOpRsp::DeviceGenerateKey(r) => r.ret,
        _ => panic!("unexpected response type"),
    }
}

fn characteristics(ta: &mut KeyMintTa, blob: &[u8]) -> Result<Vec<KeyCharacteristics>, i32> {
    match call(
        ta,
        PerformOpReq::DeviceGetKeyCharacteristics(GetKeyCharacteristicsRequest {
            key_blob: blob.to_vec(),
            app_id: APP_ID.to_vec(),
            app_data: APP_DATA.to_vec(),
        }),
    )? {
        PerformOpRsp::DeviceGetKeyCharacteristics(r) => Ok(r.ret),
        _ => panic!("unexpected response type"),
    }
}

fn upgrade_with(ta: &mut KeyMintTa, blob: &[u8], params: Vec<KeyParam>) -> Result<Vec<u8>, i32> {
    match call(
        ta,
        PerformOpReq::DeviceUpgradeKey(UpgradeKeyRequest {
            key_blob_to_upgrade: blob.to_vec(),
            upgrade_params: params,
        }),
    )? {
        PerformOpRsp::DeviceUpgradeKey(r) => Ok(r.ret),
        _ => panic!("unexpected response type"),
    }
}

fn upgrade(ta: &mut KeyMintTa, blob: &[u8]) -> Result<Vec<u8>, i32> {
    upgrade_with(ta, blob, hidden())
}

fn begin(ta: &mut KeyMintTa, blob: &[u8], purpose: KeyPurpose) -> Result<i64, i32> {
    let mut params = hidden();
    params.extend([KeyParam::Digest(Digest::Sha256), KeyParam::MacLength(256)]);
    match call(
        ta,
        PerformOpReq::DeviceBegin(BeginRequest {
            purpose,
            key_blob: blob.to_vec(),
            params,
            auth_token: None,
        }),
    )? {
        PerformOpRsp::DeviceBegin(r) => Ok(r.ret.op_handle),
        _ => panic!("unexpected response type"),
    }
}

fn sign(ta: &mut KeyMintTa, blob: &[u8]) -> Result<Vec<u8>, i32> {
    let op_handle = begin(ta, blob, KeyPurpose::Sign)?;
    match call(
        ta,
        PerformOpReq::OperationFinish(FinishRequest {
            op_handle,
            input: Some(b"synthetic continuity challenge".to_vec()),
            signature: None,
            auth_token: None,
            timestamp_token: None,
            confirmation_token: None,
        }),
    )? {
        PerformOpRsp::OperationFinish(r) => Ok(r.ret),
        _ => panic!("unexpected response type"),
    }
}

fn rejected<T>(result: Result<T, i32>) {
    match result {
        Err(code) => {
            assert_ne!(code, 0);
            assert_ne!(
                code,
                ErrorCode::KeyRequiresUpgrade as i32,
                "unauthenticated input must not be recognized as migratable"
            );
        }
        Ok(_) => panic!("invalid input unexpectedly accepted"),
    }
}

#[test]
fn new_keys_and_provider_report_software() {
    let mut ta = software();
    match call(&mut ta, PerformOpReq::DeviceGetHardwareInfo(GetHardwareInfoRequest {})).unwrap() {
        PerformOpRsp::DeviceGetHardwareInfo(r) => {
            assert_eq!(r.ret.security_level, SecurityLevel::Software);
            assert_eq!(r.ret.key_mint_name, "Droidloom software KeyMint (KMR legacy v1)");
        }
        _ => panic!("unexpected response type"),
    }
    let key = generate(&mut ta, key_params());
    let chars = characteristics(&mut ta, &key.key_blob).unwrap();
    assert_eq!(chars.len(), 1);
    assert_eq!(chars[0].security_level, SecurityLevel::Software);
    assert_eq!(sign(&mut ta, &key.key_blob).unwrap().len(), 32);
}

#[test]
fn authenticated_legacy_upgrade_preserves_key_and_authorizations_across_restart() {
    let mut old = legacy();
    let key = generate(&mut old, key_params());
    let mut expected = characteristics(&mut old, &key.key_blob).unwrap();
    assert_eq!(expected.len(), 1);
    assert_eq!(expected[0].security_level, SecurityLevel::TrustedEnvironment);
    let signature = sign(&mut old, &key.key_blob).unwrap();

    let mut new = software();
    assert_eq!(
        characteristics(&mut new, &key.key_blob).err(),
        Some(ErrorCode::KeyRequiresUpgrade as i32)
    );
    assert_eq!(sign(&mut new, &key.key_blob).err(), Some(ErrorCode::KeyRequiresUpgrade as i32));
    let upgraded = upgrade(&mut new, &key.key_blob).unwrap();
    assert!(!upgraded.is_empty());
    assert_ne!(upgraded, key.key_blob);
    expected[0].security_level = SecurityLevel::Software;
    assert_eq!(characteristics(&mut new, &upgraded).unwrap(), expected);
    assert_eq!(sign(&mut new, &upgraded).unwrap(), signature);
    let mut restarted = software();
    assert_eq!(sign(&mut restarted, &upgraded).unwrap(), signature);
    // The unchanged original still works in its original provider; no deletion
    // or rewriting of an external blob is performed by this operation.
    assert_eq!(sign(&mut old, &key.key_blob).unwrap(), signature);
}

#[test]
fn software_upgrade_is_idempotent() {
    let mut old = legacy();
    let key = generate(&mut old, key_params());
    let mut new = software();
    let upgraded = upgrade(&mut new, &key.key_blob).unwrap();
    let expected = sign(&mut new, &upgraded).unwrap();
    assert!(upgrade(&mut new, &upgraded).unwrap().is_empty());
    assert!(upgrade(&mut new, &upgraded).unwrap().is_empty());
    assert_eq!(sign(&mut new, &upgraded).unwrap(), expected);
}

#[test]
fn wrong_root_or_hidden_parameters_are_rejected_before_migration() {
    let key = generate(&mut legacy(), key_params());
    let mut roots = vec![boot(), boot(), boot()];
    roots[0].verified_boot_key[0] ^= 1;
    roots[1].device_boot_locked = true;
    roots[2].verified_boot_state = VerifiedBootState::Verified;
    for root in roots {
        let mut new = configured(build_ta(), root, 170000);
        rejected(characteristics(&mut new, &key.key_blob));
        rejected(upgrade(&mut new, &key.key_blob));
    }
    let mut new = software();
    for params in [
        vec![],
        vec![
            KeyParam::ApplicationId(b"wrong".to_vec()),
            KeyParam::ApplicationData(APP_DATA.to_vec()),
        ],
        vec![
            KeyParam::ApplicationId(APP_ID.to_vec()),
            KeyParam::ApplicationData(b"wrong".to_vec()),
        ],
    ] {
        rejected(upgrade_with(&mut new, &key.key_blob, params));
    }
}

#[test]
fn corrupted_ciphertext_nonce_and_characteristics_are_rejected() {
    let key = generate(&mut legacy(), key_params());
    let original = EncryptedKeyBlob::new(&key.key_blob).unwrap();
    for kind in 0..4 {
        let mut changed = original.clone();
        let EncryptedKeyBlob::V1(blob) = &mut changed;
        match kind {
            0 => blob.encrypted_key_material.ciphertext.as_mut().unwrap()[0] ^= 1,
            1 => blob.key_derivation_input[0] ^= 1,
            2 => blob.characteristics[0].authorizations.push(KeyParam::Purpose(KeyPurpose::Verify)),
            3 => blob.characteristics[0].security_level = SecurityLevel::Software,
            _ => unreachable!(),
        }
        let damaged = changed.into_vec().unwrap();
        let mut new = software();
        rejected(characteristics(&mut new, &damaged));
        rejected(upgrade(&mut new, &damaged));
    }
    let mut truncated = key.key_blob;
    truncated.pop();
    rejected(upgrade(&mut software(), &truncated));
}

#[test]
fn foreign_context_secure_deletion_and_mixed_profiles_are_rejected() {
    let key = generate(&mut legacy(), key_params());
    let original = EncryptedKeyBlob::new(&key.key_blob).unwrap();
    for kind in 0..4 {
        let mut changed = original.clone();
        let EncryptedKeyBlob::V1(blob) = &mut changed;
        match kind {
            0 => blob.kek_context.push(1),
            1 => blob.secure_deletion_slot = Some(SecureDeletionSlot(1)),
            2 => blob.characteristics.push(KeyCharacteristics {
                security_level: SecurityLevel::Software,
                authorizations: vec![],
            }),
            3 => blob.characteristics[0].security_level = SecurityLevel::Strongbox,
            _ => unreachable!(),
        }
        let damaged = changed.into_vec().unwrap();
        let mut new = software();
        rejected(characteristics(&mut new, &damaged));
        rejected(upgrade(&mut new, &damaged));
    }
}

// It implements the original trait only and deliberately does not opt in to
// same-format software migration. This verifies the new trait default is false.
struct NotOptedIn;
impl LegacyKeyHandler for NotOptedIn {
    fn convert_legacy_key(
        &self,
        blob: &[u8],
        params: &[KeyParam],
        root: &BootInfo,
        level: SecurityLevel,
    ) -> Result<PlaintextKeyBlob, Error> {
        legacy_nonsecure::LegacyNonsecureKmr::new().convert_legacy_key(blob, params, root, level)
    }
    fn delete_legacy_key(&mut self, _blob: &[u8]) -> Result<(), Error> {
        Ok(())
    }
}

#[test]
fn generic_software_provider_does_not_implicitly_opt_in() {
    assert!(!NotOptedIn.software_keyblob_upgrade_required(&[], &[], &boot()).unwrap());
    let key = generate(&mut legacy(), key_params());
    let mut new =
        configured(profile(SecurityLevel::Software, Some(Box::new(NotOptedIn))), boot(), 170000);
    rejected(characteristics(&mut new, &key.key_blob));
    rejected(sign(&mut new, &key.key_blob));
    // Stock upgrade of a parseable foreign-level blob returns no replacement.
    // It must not migrate or authorize use merely because a handler exists.
    assert!(upgrade(&mut new, &key.key_blob).unwrap().is_empty());
    rejected(sign(&mut new, &key.key_blob));
}

#[test]
fn tee_provider_never_uses_the_software_migration_hook() {
    let key = generate(&mut legacy(), key_params());
    let mut ta = configured(
        profile(
            SecurityLevel::TrustedEnvironment,
            Some(Box::new(legacy_nonsecure::LegacyNonsecureKmr::new())),
        ),
        boot(),
        170000,
    );
    assert_eq!(
        characteristics(&mut ta, &key.key_blob).unwrap()[0].security_level,
        SecurityLevel::TrustedEnvironment
    );
    assert_eq!(sign(&mut ta, &key.key_blob).unwrap().len(), 32);
    assert!(upgrade(&mut ta, &key.key_blob).unwrap().is_empty());
}

#[test]
fn migration_preserves_purpose_and_authentication_restrictions() {
    let key = generate(&mut legacy(), key_params());
    let mut new = software();
    let upgraded = upgrade(&mut new, &key.key_blob).unwrap();
    assert_eq!(
        begin(&mut new, &upgraded, KeyPurpose::Verify).err(),
        Some(ErrorCode::IncompatiblePurpose as i32)
    );

    let mut params = key_params();
    params.retain(|p| *p != KeyParam::NoAuthRequired);
    params.extend([
        KeyParam::UserSecureId(42),
        KeyParam::UserAuthType(1),
        KeyParam::AuthTimeout(30),
    ]);
    let mut old = legacy();
    let key = generate(&mut old, params);
    let mut expected = characteristics(&mut old, &key.key_blob).unwrap();
    expected[0].security_level = SecurityLevel::Software;
    let upgraded = upgrade(&mut new, &key.key_blob).unwrap();
    assert_eq!(characteristics(&mut new, &upgraded).unwrap(), expected);
    assert_eq!(
        begin(&mut new, &upgraded, KeyPurpose::Sign).err(),
        Some(ErrorCode::KeyUserNotAuthenticated as i32)
    );
}

#[test]
fn migration_does_not_allow_version_downgrades() {
    let mut future = configured(profile(SecurityLevel::TrustedEnvironment, None), boot(), 180000);
    let key = generate(&mut future, key_params());
    assert_eq!(
        upgrade(&mut software(), &key.key_blob).err(),
        Some(ErrorCode::InvalidArgument as i32)
    );
}
