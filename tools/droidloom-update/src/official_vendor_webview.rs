//! Preserve the publisher's APK in a normal vendor app import and select it
//! with a factory overlay. Build evidence never grants provider/runtime credit.
use super::*;
use droidloom_image::webview_provider::{VerifiedWebView, APK_BYTES, APK_SHA256, PACKAGE_NAME};

pub(super) const MODULES: &[&str] = &["DroidloomGoogleWebView", "DroidloomGoogleWebViewOverlay"];
const MANIFEST: &str =
    include_str!("../../../android/framework/droidloom-webview-provider/AndroidManifest.xml");
const PROVIDERS: &str = include_str!(
    "../../../android/framework/droidloom-webview-provider/res/xml/config_webview_packages.xml"
);
const PROVIDERS_SHA256: &str = "ccbf6c3b552d0d99a55b5403552211b711799ca454212e574902b8673125b99c";
const BLUEPRINT: &str = r#"
license {
    name: "droidloom_google_webview_prebuilt_license",
    license_kinds: ["legacy_proprietary"],
    package_name: "Android System WebView",
    copyright_notice: "Google LLC",
    license_text: [],
}
android_app_import {
    name: "DroidloomGoogleWebView",
    licenses: ["droidloom_google_webview_prebuilt_license"],
    apk: "webview/GoogleWebView.apk",
    vendor: true,
    preprocessed: true,
    enforce_uses_libs: true,
    optional_uses_libs: [
        "android.test.base",
        "androidx.window.extensions",
        "android.ext.adservices",
    ],
}
runtime_resource_overlay {
    name: "DroidloomGoogleWebViewOverlay",
    vendor: true,
    manifest: "webview-overlay/AndroidManifest.xml",
    resource_dirs: ["webview-overlay/res"],
    sdk_version: "core_platform",
    aaptflags: [
        "--auto-add-overlay",
        "-I vendor/droidloom/android/prebuilts/framework-res.apk",
    ],
}
"#;

fn configuration() -> Result<&'static str> {
    if format!("{:x}", Sha256::digest(PROVIDERS.as_bytes())) != PROVIDERS_SHA256
        || !PROVIDERS.contains(&format!("packageName=\"{PACKAGE_NAME}\""))
    {
        return fail("factory WebView provider configuration changed without review");
    }
    Ok(PROVIDERS)
}

pub(super) fn project(
    pack: &Path,
    input: &VerifiedWebView,
    projection: &mut Projection,
) -> Result<&'static str> {
    input.verify_unchanged()?;
    let providers = configuration()?;
    // preprocessed keeps the original v3 signature and delegates alignment,
    // JNI compression and uses-library checks to ordinary Soong rules.
    projection.put(
        &pack.join("webview/GoogleWebView.apk"),
        input.bytes_for_projection()?,
    )?;
    projection.put(&pack.join("webview-overlay/AndroidManifest.xml"), MANIFEST)?;
    projection.put(
        &pack.join("webview-overlay/res/xml/config_webview_packages.xml"),
        providers,
    )?;
    input.verify_unchanged()?;
    Ok(BLUEPRINT)
}

pub(super) fn verify_installed(
    input: &VerifiedWebView,
    product_out: &Path,
    sparse_converter: &crate::coherent_images::FileRef,
    scratch: &Path,
) -> Result<Value> {
    input.verify_unchanged()?;
    configuration()?;
    let installed = artifact(
        &product_out.join("vendor/app/DroidloomGoogleWebView/DroidloomGoogleWebView.apk"),
        APK_BYTES,
    )?;
    if installed.bytes != APK_BYTES || installed.sha256 != APK_SHA256 {
        return fail("normal vendor changed the original signed WebView APK");
    }
    let overlay = artifact(
        &product_out.join("vendor/overlay/DroidloomGoogleWebViewOverlay.apk"),
        16 * 1024 * 1024,
    )?;
    let entries = crate::coherent_images::verify_vendor_webview_entries(
        product_out,
        sparse_converter,
        scratch,
        &installed.sha256,
        &overlay.sha256,
    )?;
    installed.check()?;
    overlay.check()?;
    input.verify_unchanged()?;
    Ok(json!({
        "schema":"droidloom.factory-webview-normal-build.v1",
        "input":input.receipt()?,
        "installed_original_apk":installed,
        "factory_overlay":overlay,
        "provider_configuration_sha256":PROVIDERS_SHA256,
        "manifest_sha256":format!("{:x}",Sha256::digest(MANIFEST.as_bytes())),
        "normal_modules":MODULES,
        "image_entries":entries,
        "original_signed_apk_bytes_preserved":true,
        "default_provider_qualified":false,
        "rendering_qualified":false,
        "latest_qualified":false,
        "runtime_qualified":false,
        "production_ready":false,
    }))
}
