"""Verify explicit preedit inputs with one frozen original source tool revision.

Preparation tools can initially be a separate clean checkout. A final product
must freeze the integrated companion in both helper and execution fields; no
special case keeps the UI on a different runtime commit.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from product import native_sdk

HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def settings():
    return json.loads((HERE / "linux-preedit-profile.json").read_bytes())


def verified_helper(root):
    require(root is not None, "Preedit SDK requires its explicitly pinned source-tool checkout")
    root = Path(root).resolve(strict=True)
    expected = settings()["sdk_helper"]
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0")

    def git(*args):
        return subprocess.check_output(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args], env=env)

    require(Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve() == root,
            "SDK helper must be a full independent source root")
    require(git("rev-parse", "HEAD").decode().strip() == expected["commit"]
            and git("rev-parse", "HEAD^{tree}").decode().strip() == expected["tree"],
            "SDK helper commit/tree differs from the frozen product profile")
    require(not git("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"),
            "SDK helper checkout is dirty")
    require(all(not item or item[:1] == b"H" for item in git("ls-files", "-v", "-z").split(b"\0")),
            "SDK helper flags hide tracked source")
    directory = root / "apps/hepta-control-ui/test"
    for name, digest in expected["files"].items():
        path = directory / name
        require(path.is_file() and not path.is_symlink()
                and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                "SDK helper script bytes differ: " + name)
    return root, directory


def verify(metadata_bytes, sdk_root, profile_path, original_metadata_path, config_path, helper_root):
    require(all((original_metadata_path, config_path)),
            "Preedit SDK requires original metadata and exact all-crate Cargo config")
    helper_root, directory = verified_helper(helper_root)
    # -B only prevents writes; it does not prevent reading an ignored cached
    # .pyc. Give both checked source helpers a fresh, non-writing cache scope.
    old_prefix, old_write = sys.pycache_prefix, sys.dont_write_bytecode
    with tempfile.TemporaryDirectory(prefix="trill-source-tools-") as cache:
        sys.pycache_prefix, sys.dont_write_bytecode = cache, True
        try:
            spec = importlib.util.spec_from_file_location("preedit_original_sdk_verifier", directory / "verify-native-clipboard-sdk.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            actual = module.verify(helper_root, Path(sdk_root).resolve(strict=True),
                Path(original_metadata_path).read_bytes(), metadata_bytes, Path(config_path).read_bytes(), "preedit-callbacks")
        finally:
            sys.pycache_prefix, sys.dont_write_bytecode = old_prefix, old_write
    native_sdk.validate_profile(actual)
    if profile_path is not None:
        profile_bytes = Path(profile_path).read_bytes()
        require(len(profile_bytes) <= 1024 * 1024 and json.loads(profile_bytes) == actual,
                "Preedit source receipt differs from the actual complete Cargo graph")
    verified_helper(helper_root)
    return actual


def prepare_files(metadata_bytes, sdk_root, profile_path, original_metadata_path, config_path, helper_root):
    actual = verify(metadata_bytes, sdk_root, profile_path, original_metadata_path, config_path, helper_root)
    notice_root = HERE / "preedit-sdk"
    notice_bytes = (notice_root / "NATIVE-SDK-PATCH.json").read_bytes()
    notices = json.loads(notice_bytes)
    records = native_sdk.validate_notice_inventory(notices)
    profile_bytes = Path(profile_path).read_bytes()
    files = {"NATIVE-SDK-PATCH.json": notice_bytes, "NATIVE-SDK-SOURCE.json": profile_bytes}
    for entry in records:
        name = entry["path"].removeprefix("dependency-notices/makepad/")
        data = (notice_root / name).read_bytes()
        require(len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"],
                "Preedit source or license notice differs: " + name)
        files[entry["path"]] = data
    require(actual["sdk_profile"] == notices["sdkProfile"], "Mixed SDK candidate notices")
    return files, {"sdkSourceProfileSha256": hashlib.sha256(profile_bytes).hexdigest(),
                   "sdkNoticeInventorySha256": hashlib.sha256(notice_bytes).hexdigest(),
                   "sdkNotices": len(records)}
