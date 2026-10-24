"""Reverify the exact patched SDK source graph before copying resource evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path

from product import native_sdk


def prepare(metadata_bytes, ui_root, sdk_root, profile_path, original_metadata_path, config_path):
    if not all((profile_path, original_metadata_path, config_path)):
        raise ValueError("Prepared SDK requires its verified profile, complete original Cargo metadata and exact Cargo config")
    hepta = ui_root.resolve(strict=True).parents[3]
    verifier = hepta / "apps/hepta-control-ui/test/verify-native-clipboard-sdk.py"
    spec = importlib.util.spec_from_file_location("original_sdk_source_verifier", verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actual = module.verify(hepta, sdk_root.resolve(strict=True).parent,
                           original_metadata_path.read_bytes(), metadata_bytes, config_path.read_bytes())
    native_sdk.validate_profile(actual)
    profile_bytes = profile_path.read_bytes()
    if len(profile_bytes) > 1024 * 1024 or json.loads(profile_bytes) != actual:
        raise ValueError("Prepared SDK profile is stale or differs from the actual complete Cargo graph")
    notice_path = hepta / "apps/hepta-native/resources/NATIVE-SDK-PATCH.json"
    notice_bytes = notice_path.read_bytes()
    notices = json.loads(notice_bytes)
    if (notices.get("schema") != "hepta.native-sdk-notices.v1"
            or notices.get("upstreamRepository") != native_sdk.UPSTREAM
            or notices.get("upstreamRevision") != native_sdk.REVISION
            or notices.get("patchedTree") != native_sdk.TREE
            or notices.get("sourceManifestSha256") != native_sdk.MANIFEST_SHA256
            or len(notices.get("files", [])) != 4
            or {entry["path"] for entry in notices["files"]} != native_sdk.NOTICE_PATHS):
        raise ValueError("Unexpected original SDK notice inventory")
    files = {"NATIVE-SDK-PATCH.json": notice_bytes, "NATIVE-SDK-SOURCE.json": profile_bytes}
    for entry in notices["files"]:
        name = entry["path"].removeprefix("dependency-notices/makepad/")
        data = (hepta / "third_party/makepad-patches" / name).read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("SDK source/patch notice bytes differ: " + name)
        files[entry["path"]] = data
    return files, {"sdkSourceProfileSha256": hashlib.sha256(profile_bytes).hexdigest(),
                   "sdkNoticeInventorySha256": hashlib.sha256(notice_bytes).hexdigest(),
                   "sdkNotices": 4}
