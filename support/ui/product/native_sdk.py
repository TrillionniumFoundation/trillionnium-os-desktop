"""Strict identity contract for the separately qualified original SDK candidate.

This validates retained source evidence and package bytes. It does not certify
compilation, rendering, accessibility or execution authority.
"""
import hashlib
from pathlib import Path
import re

UPSTREAM = "https://github.com/kevinaboos/makepad"
REVISION = "337566c8b25d47f7e4fff6a202157b65bf183330"
TREE = "ceb83c36b474eb55336cb69b430ff9d898cb51f6"
MANIFEST_SHA256 = "bf3eb835f02b19609c6a51ef8276d46120cab7bd991d8844afc0aa113e1ebee4"
LICENSE_SHA256 = "3855d73a873244ec424ac5781d5d8fc8e2a789ff9d2f1cb804bec585a64ea88f"
PATCHES = [{"file": "native-clipboard-read.patch", "bytes": 19919,
            "sha256": "0edf1c0f806fec15ce29f03670e722d3eda4ec3943911537874087e8a8d4fa1f"},
           {"file": "sdk-num-traits-path.patch", "bytes": 521,
            "sha256": "5a1778061979f444063ba0d0c9b9dce1815c345e242eb87178252a6779c6ea1c"},
           {"file": "native-ime-preedit.patch", "bytes": 6920,
            "sha256": "11c5eacffca25eaf9aace39fdbf583e51cc8cd8ed3cbb1ebb9e29bb955a328a0"}]
SOURCE_ID = "prepared+" + UPSTREAM + "#" + TREE
NOTICE_NAMES = {"LICENSE-MIT", "MANIFEST.json", "native-clipboard-read.patch",
                "sdk-num-traits-path.patch", "native-ime-preedit.patch", "README.md"}
NOTICE_PATHS = {"dependency-notices/makepad/" + name for name in NOTICE_NAMES}
REQUIRED = {"makepad-widgets": "widgets/Cargo.toml", "makepad-draw": "draw/Cargo.toml",
            "makepad-platform": "platform/Cargo.toml", "makepad-script": "platform/script/Cargo.toml"}

# This is one retained installed release, not another accepted build target.
# Its immutable Root deployment record must bind the exact package manifest
# before historical validation is selected. Source preparation and pack() never
# select this contract, and package-supplied Python is never imported.
HISTORICAL_B_ID = "trill.installed-sdk.e5-a762-22.v1"
HISTORICAL_B = {
    "release_id": "a7621d8022f5-7bb3f08ce5c1",
    "manifest_sha256": "b1872f83b9e882ddc4f241be5b7a50039c8f40c24c6fc50cf3845c3ba4a53aa7",
    "desktop_commit": "a7621d8022f52add679bd6edba5d0bad6772dabc",
    "hepta_commit": "22e87e0dd6560a7b925e716a33011378ae07a9a2",
    "source_profile_sha256": "fe29b7cfc8c367fbdfc947169ef8d3a0a43faa751ffc41179bde556bb709a5dd",
    "sdk_source_profile_sha256": "ee76f8dc021c253ad23a4de54ea7b0ab6c0333036f62822bc9922aa77f922986",
    "sdk_notice_inventory_sha256": "a761ceb436df275a605190ccab6060ff5a593e4c36e020a7cbd58851ea4f1a38",
    "bundle_sha256": "0c3d8f8890fe262ac8b3320a5a4e7603d03c94f72b2b678487c71b77e2833011",
    "files": 72, "resources": 61,
    "tree": "e5ae930cc6a0a528719673deff44ec2830f4bdfa",
    "manifest": "cd511d5c0862ce720f596285f17aa2e4e3d133f3c45b76bcaa5a5d962d005f73",
    "license": "3855d73a873244ec424ac5781d5d8fc8e2a789ff9d2f1cb804bec585a64ea88f",
    "patches": [
        {"file": "native-clipboard-read.patch", "bytes": 19919,
         "sha256": "0edf1c0f806fec15ce29f03670e722d3eda4ec3943911537874087e8a8d4fa1f"},
        {"file": "sdk-num-traits-path.patch", "bytes": 521,
         "sha256": "5a1778061979f444063ba0d0c9b9dce1815c345e242eb87178252a6779c6ea1c"}],
    "notice_names": {"LICENSE-MIT", "MANIFEST.json", "native-clipboard-read.patch",
                     "sdk-num-traits-path.patch", "README.md"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def historical_install_contract(manifest, manifest_sha256):
    """Select history only after the caller binds the protected record's hash."""
    if manifest_sha256 != HISTORICAL_B["manifest_sha256"]:
        return None
    require(all(manifest.get(name) == HISTORICAL_B[name]
                for name in ("release_id", "desktop_commit", "hepta_commit")),
            "Historical package source identity differs")
    files = manifest.get("files")
    require(isinstance(files, dict) and len(files) == HISTORICAL_B["files"]
            and sum(name.startswith("resources/") for name in files) == HISTORICAL_B["resources"],
            "Historical package inventory differs")
    return HISTORICAL_B_ID


def historical_installation(version):
    require(version == HISTORICAL_B_ID, "Unknown installed SDK history contract")
    return HISTORICAL_B


def _contract(installed_version=None):
    if installed_version is not None:
        return historical_installation(installed_version)
    return {"tree": TREE, "manifest": MANIFEST_SHA256, "license": LICENSE_SHA256, "patches": PATCHES,
            "notice_names": NOTICE_NAMES}


def resource_source(installed_version=None):
    return "prepared+" + UPSTREAM + "#" + _contract(installed_version)["tree"]


def validate_profile(profile):
    """The source/build entry point always requires the current SDK contract."""
    _validate_profile(profile, _contract())


def _validate_profile(profile, contract):
    require(profile.get("schema") == "hepta.verified-original-sdk-source.v1"
            and profile.get("native_ui_feature") == "native-clipboard-sdk"
            and profile.get("upstream_repository") == UPSTREAM
            and profile.get("upstream_commit") == REVISION
            and profile.get("patched_tree") == contract["tree"]
            and profile.get("manifest_sha256") == contract["manifest"]
            and profile.get("patches") == contract["patches"], "Unknown original SDK source or patch profile")
    require(all(profile.get(name) is True for name in (
        "source_tree_verified", "all_sdk_packages_same_tree", "dependency_edges_verified"))
            and profile.get("effects_authority") is False,
            "SDK source has not passed complete same-tree resolution verification")
    require(all(isinstance(profile.get(name), str) and re.fullmatch(r"[0-9a-f]{64}", profile[name])
                for name in ("original_metadata_sha256", "candidate_metadata_sha256", "cargo_config_sha256")),
            "SDK source evidence hashes are missing")
    require(isinstance(profile.get("prepared_root"), str)
            and len(profile["prepared_root"]) <= 4096 and "\0" not in profile["prepared_root"]
            and Path(profile["prepared_root"]).is_absolute(), "SDK prepared source root is invalid")
    packages = profile.get("resolved_packages", [])
    require(isinstance(packages, list) and 5 <= len(packages) <= 256, "SDK package graph is incomplete or unbounded")
    seen = set()
    required = dict(REQUIRED)
    for package in packages:
        require(set(package) == {"name", "version", "manifest"}, "Unknown SDK package record")
        name, version, manifest = (package[key] for key in ("name", "version", "manifest"))
        require(isinstance(name, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", name)
                and isinstance(version, str) and len(version) <= 100
                and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][a-zA-Z0-9.+-]+)?", version),
                "Invalid SDK package identity")
        require(isinstance(manifest, str) and not manifest.startswith("/") and "\\" not in manifest
                and all(part not in ("", ".", "..") for part in manifest.split("/"))
                and manifest.endswith("/Cargo.toml"), "SDK package manifest escaped the prepared tree")
        require((name, version) not in seen, "Duplicate SDK package identity")
        seen.add((name, version))
        if name in required:
            require(manifest == required.pop(name), "SDK foundational crate has a substituted manifest")
    require(not required and any(name == "unicode-segmentation" for name, _ in seen), "Required SDK packages are missing")


def validate_notice_inventory(notices):
    """Bind every reviewed patch before either preparing or packaging its bytes."""
    return _validate_notice_inventory(notices, _contract())


def _validate_notice_inventory(notices, contract):
    require(notices.get("schema") == "hepta.native-sdk-notices.v1"
            and notices.get("upstreamRepository") == UPSTREAM
            and notices.get("upstreamRevision") == REVISION
            and notices.get("patchedTree") == contract["tree"]
            and notices.get("sourceManifestSha256") == contract["manifest"],
            "SDK notice inventory does not identify the reviewed original patch")
    files = notices.get("files", [])
    names = contract["notice_names"]
    require(len(files) == len(names)
            and {entry["path"] for entry in files} == {"dependency-notices/makepad/" + name for name in names},
            "Incomplete SDK source and patch notices")
    by_path = {entry["path"]: entry for entry in files}
    require(by_path["dependency-notices/makepad/MANIFEST.json"]["sha256"] == contract["manifest"]
            and by_path["dependency-notices/makepad/LICENSE-MIT"]["sha256"] == contract["license"],
            "Original SDK license or patch identity differs")
    for patch in contract["patches"]:
        entry = by_path["dependency-notices/makepad/" + patch["file"]]
        require(entry["sha256"] == patch["sha256"] and entry["bytes"] == patch["bytes"],
                "Original SDK license or patch identity differs")
    return files


def bundle_records(root, bundle, read_json, regular_bytes, expected_profile=None, bind_binary=False,
                   *, installed_version=None):
    """Return additional records after verifying the fixed SDK/source contract."""
    contract = _contract(installed_version)
    if installed_version is not None:
        require(bundle.get("makepadSource") == resource_source(installed_version),
                "Historical SDK source identity differs")
    if bundle.get("makepadSource") != resource_source(installed_version):
        require(not any(key in bundle for key in ("sdkSourceProfileSha256", "sdkNoticeInventorySha256", "sdkNotices")),
                "SDK patch evidence attached to an unrelated SDK source")
        require(expected_profile is None, "Binary SDK patch profile does not match the resource bundle")
        return []
    notice_bytes = regular_bytes(root / "NATIVE-SDK-PATCH.json", 128 * 1024)
    notices = read_json(root / "NATIVE-SDK-PATCH.json", 128 * 1024)
    profile_bytes = regular_bytes(root / "NATIVE-SDK-SOURCE.json", 1024 * 1024)
    profile = read_json(root / "NATIVE-SDK-SOURCE.json", 1024 * 1024)
    require(bundle.get("sdkNoticeInventorySha256") == sha(notice_bytes)
            and bundle.get("sdkSourceProfileSha256") == sha(profile_bytes), "SDK notice/source inventory hash mismatch")
    if installed_version is not None:
        require(sha(notice_bytes) == contract["sdk_notice_inventory_sha256"]
                and sha(profile_bytes) == contract["sdk_source_profile_sha256"],
                "Historical SDK notice/source identity differs")
    files = _validate_notice_inventory(notices, contract)
    require(bundle.get("sdkNotices") == len(contract["notice_names"]), "Incomplete SDK source and patch notices")
    _validate_profile(profile, contract)
    if bind_binary or expected_profile is not None:
        require(expected_profile == profile, "Resource SDK profile differs from the binary source profile")
    return [(entry["path"], entry) for entry in files] + [
        ("NATIVE-SDK-PATCH.json", {"bytes": len(notice_bytes), "sha256": sha(notice_bytes)}),
        ("NATIVE-SDK-SOURCE.json", {"bytes": len(profile_bytes), "sha256": sha(profile_bytes)})]
