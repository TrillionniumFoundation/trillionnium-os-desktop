//! Linux controls for byte-identical updater sources; no Android qualification.
#![allow(dead_code)]
mod util {
    pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
}
mod audio_vendor_candidate;
mod audio_vendor_zip;
