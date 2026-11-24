// SPDX-License-Identifier: Apache-2.0
//! Compatibility with the original in-process KMR software provider.
//!
//! A historical TrustedEnvironment tag is authenticated as part of the old
//! keyblob before it is reclassified as Software. This implementation has no
//! secure-world transport and must never be installed as a hardware provider.

use kmr_common::{
    crypto,
    keyblob::{self, EncryptedKeyBlob, LegacyKeyHandler, PlaintextKeyBlob, RootOfTrustInfo},
    km_err, tag, Error,
};
use kmr_ta::device::RetrieveKeyMaterial;
use kmr_wire::{
    keymint::{BootInfo, KeyParam, SecurityLevel},
    AsCborValue,
};

/// Opt-in conversion of the original nonsecure V1 KMR keyblob profile.
pub struct LegacyNonsecureKmr {
    crypto: crypto::Implementation,
}

impl Default for LegacyNonsecureKmr {
    fn default() -> Self {
        Self::new()
    }
}

impl LegacyNonsecureKmr {
    pub fn new() -> Self {
        Self { crypto: crate::boringssl_crypto_impls() }
    }

    fn authenticated_legacy(
        &self,
        serialized: &[u8],
        params: &[KeyParam],
        boot_info: &BootInfo,
    ) -> Result<PlaintextKeyBlob, Error> {
        let encrypted = EncryptedKeyBlob::new(serialized)?;
        let EncryptedKeyBlob::V1(blob) = &encrypted;

        // These are the original process-local provider's exact structural
        // boundaries. Never accept another provider's root context, deletion
        // state, StrongBox characteristics, or mixed security-level buckets.
        if !blob.kek_context.is_empty()
            || blob.secure_deletion_slot.is_some()
            || blob.characteristics.len() != 1
            || blob.characteristics[0].security_level != SecurityLevel::TrustedEnvironment
        {
            return Err(km_err!(InvalidKeyBlob, "not an original nonsecure KMR V1 keyblob"));
        }

        // Keep the original characteristics untouched until authentication
        // succeeds: their serialized bytes participate in the HKDF input.
        // Bind application ID/data and boot root exactly as the original TA did.
        let root_of_trust = RootOfTrustInfo {
            verified_boot_key: boot_info.verified_boot_key.clone(),
            device_boot_locked: boot_info.device_boot_locked,
            verified_boot_state: boot_info.verified_boot_state,
        }
        .into_vec()
        .map_err(|_| km_err!(EncodingError, "cannot encode legacy boot root"))?;
        let hidden = tag::hidden(params, &root_of_trust)?;
        let root_key = crate::soft::Keys.root_kek(encrypted.kek_context())?;
        keyblob::decrypt(None, &*self.crypto.aes, &*self.crypto.hkdf, &root_key, encrypted, hidden)
    }
}

impl LegacyKeyHandler for LegacyNonsecureKmr {
    fn software_keyblob_upgrade_required(
        &self,
        serialized: &[u8],
        params: &[KeyParam],
        boot_info: &BootInfo,
    ) -> Result<bool, Error> {
        let EncryptedKeyBlob::V1(blob) = EncryptedKeyBlob::new(serialized)?;
        if blob.characteristics.len() == 1
            && blob.characteristics[0].security_level == SecurityLevel::Software
        {
            // Current software keys use the normal TA validation path.
            return Ok(false);
        }
        // Do not swallow authentication or profile errors and let a foreign
        // historical blob fall back to the generic upgrade implementation.
        self.authenticated_legacy(serialized, params, boot_info)?;
        Ok(true)
    }

    fn is_legacy_key(&self, serialized: &[u8], params: &[KeyParam], boot_info: &BootInfo) -> bool {
        // Recognition includes authentication. The plaintext remains inside the
        // provider and is discarded; no key bytes are returned or logged.
        self.authenticated_legacy(serialized, params, boot_info).is_ok()
    }

    fn convert_legacy_key(
        &self,
        serialized: &[u8],
        params: &[KeyParam],
        boot_info: &BootInfo,
        security_level: SecurityLevel,
    ) -> Result<PlaintextKeyBlob, Error> {
        if security_level != SecurityLevel::Software {
            return Err(km_err!(InvalidArgument, "nonsecure migration only targets Software"));
        }
        let mut plaintext = self.authenticated_legacy(serialized, params, boot_info)?;
        // Preserve every authorization value, key material and key identity.
        // The caller's normal upgrade path still checks versions, generates a
        // fresh derivation nonce and returns an encrypted replacement blob.
        plaintext.characteristics[0].security_level = SecurityLevel::Software;
        Ok(plaintext)
    }

    fn delete_legacy_key(&mut self, _serialized: &[u8]) -> Result<(), Error> {
        // This profile has no secure deletion slot or external persistent state.
        Ok(())
    }
}
