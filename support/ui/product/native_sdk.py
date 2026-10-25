"""Strict identity contracts for separately qualified original SDK candidates.

This validates retained source evidence and package bytes. It does not certify
compilation, rendering, accessibility or execution authority.
"""
import hashlib
from pathlib import Path
import re

UPSTREAM = "https://github.com/kevinaboos/makepad"
REVISION = "337566c8b25d47f7e4fff6a202157b65bf183330"
TREE = "e5ae930cc6a0a528719673deff44ec2830f4bdfa"
MANIFEST_SHA256 = "cd511d5c0862ce720f596285f17aa2e4e3d133f3c45b76bcaa5a5d962d005f73"
LICENSE_SHA256 = "3855d73a873244ec424ac5781d5d8fc8e2a789ff9d2f1cb804bec585a64ea88f"
PATCHES = [{"file": "native-clipboard-read.patch", "bytes": 19919,
            "sha256": "0edf1c0f806fec15ce29f03670e722d3eda4ec3943911537874087e8a8d4fa1f"},
           {"file": "sdk-num-traits-path.patch", "bytes": 521,
            "sha256": "5a1778061979f444063ba0d0c9b9dce1815c345e242eb87178252a6779c6ea1c"}]
SOURCE_ID = "prepared+" + UPSTREAM + "#" + TREE
PREEDIT_TREE = "8d867396d16dcdca812ef27da21e8da59e7aee6f"
PREEDIT_SOURCE_ID = "prepared+" + UPSTREAM + "#" + PREEDIT_TREE
PREEDIT_MANIFEST_SHA256 = "e572e28b56db9897ab92b7371ffb4e34d256b7fb4b6373a49bd8f82da02597c9"
PREEDIT_PATCHES = [
    {"file": "native-preedit-callbacks.patch", "bytes": 13752,
     "sha256": "24eaa6bfa6e0422c7dce7c936687067e6a27d851373071560ed709a0f9caabee"},
    {"file": "sdk-num-traits-path.patch", "bytes": 521,
     "sha256": "5a1778061979f444063ba0d0c9b9dce1815c345e242eb87178252a6779c6ea1c"}]
NOTICE_NAMES = {"LICENSE-MIT", "MANIFEST.json", "native-clipboard-read.patch",
                "sdk-num-traits-path.patch", "README.md"}
NOTICE_PATHS = {"dependency-notices/makepad/" + name for name in NOTICE_NAMES}
REQUIRED = {"makepad-widgets": "widgets/Cargo.toml", "makepad-draw": "draw/Cargo.toml",
            "makepad-platform": "platform/Cargo.toml", "makepad-script": "platform/script/Cargo.toml"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def contract(profile=None):
    """Select one named immutable candidate; the historical default is unchanged."""
    require(profile in (None, "clipboard", "preedit-callbacks"), "Unknown named SDK candidate")
    if profile == "preedit-callbacks":
        names = {"LICENSE-MIT", "MANIFEST.json", "native-preedit-callbacks.patch",
                 "sdk-num-traits-path.patch", "README.md"}
        return {"tree": PREEDIT_TREE, "manifest": PREEDIT_MANIFEST_SHA256, "patches": PREEDIT_PATCHES,
                "feature": "native-presentation", "names": names, "source": PREEDIT_SOURCE_ID}
    return {"tree": TREE, "manifest": MANIFEST_SHA256, "patches": PATCHES,
            "feature": "native-clipboard-sdk", "names": NOTICE_NAMES, "source": SOURCE_ID}


def validate_profile(profile):
    selected = contract(profile.get("sdk_profile"))
    require(profile.get("schema") == "hepta.verified-original-sdk-source.v1"
            and profile.get("native_ui_feature") == selected["feature"]
            and profile.get("upstream_repository") == UPSTREAM
            and profile.get("upstream_commit") == REVISION
            and profile.get("patched_tree") == selected["tree"]
            and profile.get("manifest_sha256") == selected["manifest"]
            and profile.get("patches") == selected["patches"], "Unknown original SDK source or patch profile")
    if profile.get("sdk_profile") == "preedit-callbacks":
        require(profile.get("upstream_tree") == "c6e18be7754f9634492ec5251bac3e8b4f7e09b7",
                "Preedit SDK upstream full tree differs")
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
    return selected


def validate_notice_inventory(notices):
    """Bind every reviewed patch before either preparing or packaging its bytes."""
    selected = contract(notices.get("sdkProfile"))
    require(notices.get("schema") == "hepta.native-sdk-notices.v1"
            and notices.get("upstreamRepository") == UPSTREAM
            and notices.get("upstreamRevision") == REVISION
            and notices.get("patchedTree") == selected["tree"]
            and notices.get("sourceManifestSha256") == selected["manifest"],
            "SDK notice inventory does not identify the reviewed original patch")
    files = notices.get("files", [])
    require(len(files) == len(selected["names"])
            and {entry["path"] for entry in files} == {"dependency-notices/makepad/" + name for name in selected["names"]},
            "Incomplete SDK source and patch notices")
    by_path = {entry["path"]: entry for entry in files}
    require(by_path["dependency-notices/makepad/MANIFEST.json"]["sha256"] == selected["manifest"]
            and by_path["dependency-notices/makepad/LICENSE-MIT"]["sha256"] == LICENSE_SHA256,
            "Original SDK license or patch identity differs")
    for patch in selected["patches"]:
        entry = by_path["dependency-notices/makepad/" + patch["file"]]
        require(entry["sha256"] == patch["sha256"] and entry["bytes"] == patch["bytes"],
                "Original SDK license or patch identity differs")
    return files


def bundle_records(root, bundle, read_json, regular_bytes, expected_profile=None, bind_binary=False):
    """Return additional records after verifying the fixed SDK/source contract."""
    if bundle.get("makepadSource") not in (SOURCE_ID, PREEDIT_SOURCE_ID):
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
    files = validate_notice_inventory(notices)
    selected = validate_profile(profile)
    require(bundle.get("makepadSource") == selected["source"]
            and notices.get("patchedTree") == selected["tree"]
            and bundle.get("sdkNotices") == len(selected["names"]), "Incomplete or mixed SDK source and patch notices")
    if bind_binary or expected_profile is not None:
        require(expected_profile == profile, "Resource SDK profile differs from the binary source profile")
    return [(entry["path"], entry) for entry in files] + [
        ("NATIVE-SDK-PATCH.json", {"bytes": len(notice_bytes), "sha256": sha(notice_bytes)}),
        ("NATIVE-SDK-SOURCE.json", {"bytes": len(profile_bytes), "sha256": sha(profile_bytes)})]
