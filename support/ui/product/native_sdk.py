"""Strict identity contract for the separately qualified original SDK candidate.

This validates retained source evidence and package bytes. It does not certify
compilation, rendering, accessibility or execution authority.
"""
import hashlib
from pathlib import Path
import re

UPSTREAM = "https://github.com/kevinaboos/makepad"
REVISION = "337566c8b25d47f7e4fff6a202157b65bf183330"
TREE = "f9efec87ff9d5690b8c9fd23ea0c8f3535a9d8eb"
MANIFEST_SHA256 = "a7f36936a4101d85df78b30a7776ee85388fd004b7b8fccd0d1d3a460d859b3a"
LICENSE_SHA256 = "3855d73a873244ec424ac5781d5d8fc8e2a789ff9d2f1cb804bec585a64ea88f"
PATCHES = [{"file": "native-clipboard-read.patch", "bytes": 19919,
            "sha256": "0edf1c0f806fec15ce29f03670e722d3eda4ec3943911537874087e8a8d4fa1f"}]
SOURCE_ID = "prepared+" + UPSTREAM + "#" + TREE
NOTICE_NAMES = {"LICENSE-MIT", "MANIFEST.json", "native-clipboard-read.patch", "README.md"}
NOTICE_PATHS = {"dependency-notices/makepad/" + name for name in NOTICE_NAMES}
REQUIRED = {"makepad-widgets": "widgets/Cargo.toml", "makepad-draw": "draw/Cargo.toml",
            "makepad-platform": "platform/Cargo.toml", "makepad-script": "platform/script/Cargo.toml"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_profile(profile):
    require(profile.get("schema") == "hepta.verified-original-sdk-source.v1"
            and profile.get("native_ui_feature") == "native-clipboard-sdk"
            and profile.get("upstream_repository") == UPSTREAM
            and profile.get("upstream_commit") == REVISION
            and profile.get("patched_tree") == TREE
            and profile.get("manifest_sha256") == MANIFEST_SHA256
            and profile.get("patches") == PATCHES, "Unknown original SDK source or patch profile")
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


def bundle_records(root, bundle, read_json, regular_bytes, expected_profile=None, bind_binary=False):
    """Return additional records after verifying the fixed SDK/source contract."""
    if bundle.get("makepadSource") != SOURCE_ID:
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
    require(notices.get("schema") == "hepta.native-sdk-notices.v1"
            and notices.get("upstreamRepository") == UPSTREAM
            and notices.get("upstreamRevision") == REVISION
            and notices.get("patchedTree") == TREE
            and notices.get("sourceManifestSha256") == MANIFEST_SHA256,
            "SDK notice inventory does not identify the reviewed original patch")
    files = notices.get("files", [])
    require(len(files) == bundle.get("sdkNotices") == 4
            and {entry["path"] for entry in files} == NOTICE_PATHS, "Incomplete SDK source and patch notices")
    by_path = {entry["path"]: entry for entry in files}
    require(by_path["dependency-notices/makepad/MANIFEST.json"]["sha256"] == MANIFEST_SHA256
            and by_path["dependency-notices/makepad/native-clipboard-read.patch"]["sha256"] == PATCHES[0]["sha256"]
            and by_path["dependency-notices/makepad/native-clipboard-read.patch"]["bytes"] == PATCHES[0]["bytes"]
            and by_path["dependency-notices/makepad/LICENSE-MIT"]["sha256"] == LICENSE_SHA256,
            "Original SDK license or patch identity differs")
    validate_profile(profile)
    if bind_binary or expected_profile is not None:
        require(expected_profile == profile, "Resource SDK profile differs from the binary source profile")
    return [(entry["path"], entry) for entry in files] + [
        ("NATIVE-SDK-PATCH.json", {"bytes": len(notice_bytes), "sha256": sha(notice_bytes)}),
        ("NATIVE-SDK-SOURCE.json", {"bytes": len(profile_bytes), "sha256": sha(profile_bytes)})]
