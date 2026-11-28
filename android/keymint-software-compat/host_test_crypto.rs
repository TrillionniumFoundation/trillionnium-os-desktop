// SPDX-License-Identifier: Apache-2.0
//! Cargo-only crypto adapter for the synthetic compatibility tests.
//! Not projected into Android. The official Soong target uses BoringSSL.
//! AES, HKDF, HMAC, RNG, EC and RSA use the pinned KMR OpenSSL backends.
//! CMAC and ML-DSA are deliberately unsupported by this host test adapter.

use kmr_common::{crypto, km_err, Error};
use kmr_crypto_boring as backend;
use kmr_wire::keymint::{KeyParam, MlDsaVariant};

struct Unsupported;
impl crypto::Ckdf for Unsupported {
    fn ckdf(
        &self,
        _key: &crypto::OpaqueOr<crypto::aes::Key>,
        _label: &[u8],
        _chunks: &[&[u8]],
        _out_len: usize,
    ) -> Result<Vec<u8>, Error> {
        Err(km_err!(UnsupportedAlgorithm, "CMAC is unavailable in the host test adapter"))
    }
}
impl crypto::MlDsa for Unsupported {
    fn generate_key(
        &self,
        _rng: &mut dyn crypto::Rng,
        _variant: MlDsaVariant,
        _params: &[KeyParam],
    ) -> Result<crypto::KeyMaterial, Error> {
        Err(km_err!(UnsupportedAlgorithm, "ML-DSA is unavailable in the host test adapter"))
    }
    fn import_raw_key(
        &self,
        _data: &[u8],
        _variant: MlDsaVariant,
        _params: &[KeyParam],
    ) -> Result<crypto::KeyMaterial, Error> {
        Err(km_err!(UnsupportedAlgorithm, "ML-DSA is unavailable in the host test adapter"))
    }
    fn import_pkcs8_key(
        &self,
        _data: &[u8],
        _params: &[KeyParam],
    ) -> Result<crypto::KeyMaterial, Error> {
        Err(km_err!(UnsupportedAlgorithm, "ML-DSA is unavailable in the host test adapter"))
    }
    fn subject_public_key(
        &self,
        _key: &crypto::OpaqueOr<crypto::mldsa::Key>,
    ) -> Result<Vec<u8>, Error> {
        Err(km_err!(UnsupportedAlgorithm, "ML-DSA is unavailable in the host test adapter"))
    }
    fn begin_sign(
        &self,
        _key: crypto::OpaqueOr<crypto::mldsa::Key>,
    ) -> Result<Box<dyn crypto::AccumulatingOperation>, Error> {
        Err(km_err!(UnsupportedAlgorithm, "ML-DSA is unavailable in the host test adapter"))
    }
}

pub fn implementation(
    rng: Box<dyn crypto::Rng>,
    clock: Box<dyn crypto::MonotonicClock>,
) -> crypto::Implementation {
    crypto::Implementation {
        rng,
        clock: Some(clock),
        compare: Box::new(backend::eq::BoringEq),
        aes: Box::new(backend::aes::BoringAes),
        des: Box::new(backend::des::BoringDes),
        hmac: Box::new(backend::hmac::BoringHmac),
        rsa: Box::<backend::rsa::BoringRsa>::default(),
        ec: Box::<backend::ec::BoringEc>::default(),
        ckdf: Box::new(Unsupported),
        hkdf: Box::new(backend::hmac::BoringHmac),
        sha256: Box::new(backend::sha256::BoringSha256),
        mldsa: Box::new(Unsupported),
    }
}
