use super::*;

fn sparse_fixture() -> (Vec<u8>, Vec<u8>) {
    let raw: Vec<u8> = (0..4096).map(|i| (i % 251) as u8).collect();
    let fill = 0x1020_3040_u32.to_le_bytes();
    let mut encoded = 0xed26_ff3a_u32.to_le_bytes().to_vec();
    for value in [1_u16, 0, 28, 12] {
        encoded.extend_from_slice(&value.to_le_bytes());
    }
    for value in [4096_u32, 3, 3, 0] {
        encoded.extend_from_slice(&value.to_le_bytes());
    }
    for (kind, total, data) in [
        (0xcac1_u16, 4108_u32, raw.as_slice()),
        (0xcac2_u16, 16_u32, fill.as_slice()),
        (0xcac3_u16, 12_u32, &[][..]),
    ] {
        encoded.extend_from_slice(&kind.to_le_bytes());
        encoded.extend_from_slice(&0_u16.to_le_bytes());
        encoded.extend_from_slice(&1_u32.to_le_bytes());
        encoded.extend_from_slice(&total.to_le_bytes());
        encoded.extend_from_slice(data);
    }
    let mut expected = raw;
    for _ in 0..1024 {
        expected.extend_from_slice(&fill);
    }
    expected.extend_from_slice(&[0_u8; 4096]);
    (encoded, expected)
}

#[test]
fn sparse_input_without_recorded_converter_cannot_fall_back_to_path() -> Result<()> {
    let work = tempfile::tempdir()?;
    let (encoded, _) = sparse_fixture();
    let input = work.path().join("input.img");
    fs::write(&input, encoded)?;
    let original = pin(&input, MAX_IMAGE)?;
    let output = work.path().join("output.img");
    assert!(decode_image(&original, &output, None).is_err());
    assert!(!output.exists());
    recheck(&original, MAX_IMAGE)?;
    let raw = work.path().join("already-raw.img");
    fs::write(&raw, b"ordinary raw bytes")?;
    let raw = pin(&raw, MAX_IMAGE)?;
    let (same, converter) = decode_image(&raw, &output, None)?;
    assert_eq!(same, raw);
    assert!(converter.is_none());
    assert!(!output.exists());
    Ok(())
}

#[test]
#[ignore = "requires the actual completed normal Soong host output"]
fn actual_normal_sparse_converter_round_trip_and_identity() -> Result<()> {
    let normal = PathBuf::from(
        std::env::var_os("DROIDLOOM_TEST_NORMAL_OUT")
            .ok_or("DROIDLOOM_TEST_NORMAL_OUT is required")?,
    );
    let converter = normal_sparse_converter(&normal)?;
    let work = tempfile::tempdir()?;
    let _scope = resources::Scope::writing(work.path(), resources::GIB)?;
    let (encoded, expected) = sparse_fixture();
    let input = work.path().join("input.img");
    fs::write(&input, encoded)?;
    let original = pin(&input, MAX_IMAGE)?;
    let output = work.path().join("output.img");
    let (decoded, selected) = decode_image(&original, &output, Some(&converter))?;
    assert_eq!(selected.as_ref(), Some(&converter));
    assert_eq!(fs::read(&decoded.path)?, expected);
    assert!(decode_image(&original, &output, Some(&converter)).is_err());
    recheck(&original, MAX_IMAGE)?;
    recheck(&converter, 256 * 1024 * 1024)?;

    let copied_out = work.path().join("copied-normal");
    let copied = copied_out.join("host/linux-x86/bin/simg2img");
    fs::create_dir_all(copied.parent().unwrap())?;
    fs::copy(&converter.path, &copied)?;
    let before = normal_sparse_converter(&copied_out)?;
    let replacement = copied.with_extension("replacement");
    fs::copy(&converter.path, &replacement)?;
    fs::rename(&replacement, &copied)?;
    let rejected = work.path().join("replaced-tool-output.img");
    assert!(decode_image(&original, &rejected, Some(&before)).is_err());
    assert!(!rejected.exists());
    fs::remove_file(&copied)?;
    std::os::unix::fs::symlink(&converter.path, &copied)?;
    assert!(normal_sparse_converter(&copied_out).is_err());
    recheck(&converter, 256 * 1024 * 1024)?;
    eprintln!(
        "actual normal sparse converter: {} {} bytes sha256={}",
        converter.path.display(),
        converter.bytes,
        converter.sha256
    );
    Ok(())
}

#[test]
#[ignore = "requires a completed normal vendor image and installed graphics HALs"]
fn actual_normal_vendor_graphics_image_entries() -> Result<()> {
    let normal = PathBuf::from(
        std::env::var_os("DROIDLOOM_TEST_NORMAL_OUT")
            .ok_or("DROIDLOOM_TEST_NORMAL_OUT is required")?,
    );
    let converter = normal_sparse_converter(&normal)?;
    let product = normal.join("target/product/droidloom_x86_64");
    let image = pin(&product.join("vendor.img"), MAX_IMAGE)?;
    let scratch = tempfile::tempdir()?;
    let labels = verify_vendor_graphics_hal_entries(&product, &converter, scratch.path())?;
    assert_eq!(labels.len(), 2);
    assert_eq!(
        labels["/vendor/bin/hw/android.hardware.graphics.composer3-service.droidloom"],
        "u:object_r:hal_graphics_composer_default_exec:s0"
    );
    assert_eq!(
        labels["/vendor/bin/hw/android.hardware.graphics.allocator-service.minigbm"],
        "u:object_r:hal_graphics_allocator_default_exec:s0"
    );
    recheck(&image, MAX_IMAGE)?;
    recheck(&converter, 256 * 1024 * 1024)?;
    eprintln!(
        "actual normal vendor image={} bytes sha256={} entries={:?}",
        image.bytes, image.sha256, labels
    );
    Ok(())
}
