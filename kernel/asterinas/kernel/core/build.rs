// SPDX-License-Identifier: MPL-2.0

//! Only the new image experiment hashes/freezes a reviewed owner build input.
//! Ordinary/legacy builds require no additional input or host hashing command.

#[cfg(all(
    feature = "g2-original-owner-a39-v1",
    feature = "g2-original-owner-publish-v1"
))]
compile_error!("select only one original-owner image version");

#[allow(dead_code)]
#[cfg_attr(
    not(feature = "g2-original-owner-publish-v1"),
    path = "src/process/program_loader/elf/original_owner_profile.rs"
)]
#[cfg_attr(
    feature = "g2-original-owner-publish-v1",
    path = "src/process/program_loader/elf/publication_owner_profile.rs"
)]
mod profile;

fn main() {
    println!("cargo:rerun-if-env-changed=HEPTA_TRUSTED_INITIAL_ELF");
    if std::env::var_os("CARGO_FEATURE_G2_ORIGINAL_OWNER_A39_V1").is_none()
        && std::env::var_os("CARGO_FEATURE_G2_ORIGINAL_OWNER_PUBLISH_V1").is_none()
    {
        return;
    }
    #[cfg(unix)]
    freeze_reviewed_image();
    #[cfg(not(unix))]
    panic!("the exact original-owner image experiment requires a Unix build host");
}

#[cfg(unix)]
fn freeze_reviewed_image() {
    use std::{
        env, fs,
        io::{Read, Write},
        os::unix::fs::{MetadataExt, PermissionsExt},
        path::PathBuf,
        process::{Command, Stdio},
    };

    let source = PathBuf::from(
        env::var_os("HEPTA_TRUSTED_INITIAL_ELF")
            .expect("the exact original-owner image profile requires its reviewed ELF"),
    );
    assert!(
        source.is_absolute(),
        "original-owner input must be absolute"
    );
    let source_text = source.to_str().expect("UTF-8 original-owner input path");
    assert!(!source_text.contains('\n') && !source_text.contains('\r'));
    println!("cargo:rerun-if-changed={source_text}");
    assert!(
        fs::symlink_metadata(&source).unwrap().file_type().is_file(),
        "original-owner input must be a regular file, not a symlink"
    );
    let source_file = fs::File::open(&source).expect("open reviewed original-owner input");
    let metadata = source_file.metadata().unwrap();
    assert!(metadata.is_file() && metadata.len() == profile::FILE_BYTES as u64);
    let mut bytes = Vec::with_capacity(profile::FILE_BYTES);
    source_file
        .take(profile::FILE_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .expect("read the one bounded original-owner snapshot");
    assert_eq!(
        bytes.len(),
        profile::FILE_BYTES,
        "original-owner file length differs"
    );

    // Hash the byte vector already read, not a second pathname lookup. The
    // compiler's private input below is written from this exact same vector.
    let mut digest = Command::new("/usr/bin/sha256sum")
        .arg("-")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("the experimental Linux build host requires /usr/bin/sha256sum");
    let written = digest.stdin.take().unwrap().write_all(&bytes);
    let output = digest
        .wait_with_output()
        .expect("wait for original-owner digest");
    written.expect("send the complete original-owner snapshot to sha256sum");
    assert!(
        output.status.success(),
        "original-owner digest command failed"
    );
    assert_eq!(
        output.stdout,
        format!("{}  -\n", profile::OWNER_SHA256).as_bytes(),
        "original-owner complete SHA-256 differs from the source-reviewed profile"
    );

    let output_dir = PathBuf::from(env::var_os("OUT_DIR").expect("Cargo private OUT_DIR"));
    let frozen = output_dir.join("reviewed-original-owner.elf");
    match fs::symlink_metadata(&frozen) {
        Ok(metadata) => {
            assert!(metadata.file_type().is_file() && metadata.len() == bytes.len() as u64);
            assert_eq!(
                fs::read(&frozen).unwrap(),
                bytes,
                "existing compiler input differs"
            );
            assert_eq!(metadata.permissions().mode() & 0o777, 0o444);
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            // Never expose a partial/writable final input. A terminated build
            // may leave its private temporary file, but no later build consumes
            // that name. create_new and hard_link never overwrite another file.
            let (temporary, mut destination) = (0..16)
                .find_map(|attempt| {
                    let path = output_dir.join(format!(
                        ".reviewed-original-owner-{}-{attempt}.tmp",
                        std::process::id()
                    ));
                    match fs::OpenOptions::new()
                        .write(true)
                        .create_new(true)
                        .open(&path)
                    {
                        Ok(file) => Some((path, file)),
                        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => None,
                        Err(error) => {
                            panic!("cannot create private compiler staging input: {error}")
                        }
                    }
                })
                .expect("private compiler staging names are occupied");
            let owned = destination.metadata().expect("own compiler staging input");
            let published = (|| -> std::io::Result<()> {
                destination.write_all(&bytes)?;
                destination.set_permissions(fs::Permissions::from_mode(0o444))?;
                destination.sync_all()?;
                let current = fs::symlink_metadata(&temporary)?;
                assert_eq!((current.dev(), current.ino()), (owned.dev(), owned.ino()));
                fs::hard_link(&temporary, &frozen)?;
                Ok(())
            })();
            // Remove only the staging inode still owned by this invocation.
            if let Ok(current) = fs::symlink_metadata(&temporary) {
                if (current.dev(), current.ino()) == (owned.dev(), owned.ino()) {
                    fs::remove_file(&temporary).expect("remove owned compiler staging link");
                }
            }
            published.expect("atomically publish the sealed original-owner compiler input");
        }
        Err(error) => panic!("cannot inspect private original-owner input: {error}"),
    }
    // The loader includes this checked copy. It cannot embed a later pathname
    // replacement of the supplied HEPTA_TRUSTED_INITIAL_ELF.
    println!(
        "cargo:rustc-env=HEPTA_REVIEWED_ORIGINAL_OWNER_ELF={}",
        frozen.display()
    );
}
