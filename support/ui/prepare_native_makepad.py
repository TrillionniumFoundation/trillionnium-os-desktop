#!/usr/bin/env python3
"""Package the exact Cargo-resolved Hepta/Makepad resources without changing checkouts."""
import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
import prepare_native_sdk
from product import native_sdk

ACCESSKIT_REVISION = "405d578cdfd8496ee79020d24cfaac8c29a8a48f"
ACCESSKIT_CRATES = {"accesskit": "0.17.1", "accesskit_consumer": "0.26.0",
                   "accesskit_atspi_common": "0.10.1", "accesskit_unix": "0.13.1"}
DEPENDENCY_FILES = {"LICENSE-APACHE", "LICENSE-MIT", "LICENSE.chromium",
                    "HEPTA_UPSTREAM.json", "HEPTA_PATCH.diff", "HEPTA_PATCH.md"}
LIBERATION_SOURCE_MIRRORS = {
    "fe3ea5f7a2d3bdea8b8f0d82cdc6c07d14ace67c6e06d7aa33b83fd9e640adae": (
        "https://ftp.gnu.org/gnu/freedink/fonts/liberation-fonts-1.04.93.devel.src.tar.gz",
        "https://eu.edge.kernel.org/gnu/freedink/fonts/liberation-fonts-1.04.93.devel.src.tar.gz",
    ),
}


def original_accesskit(metadata, ui_root, ui_source):
    vendor = (ui_root / "../../../../codex-rs/third_party/accesskit-0.17.1").resolve(strict=True)
    paths = {"accesskit": "common", "accesskit_consumer": "consumer",
             "accesskit_atspi_common": "platforms/atspi-common", "accesskit_unix": "platforms/unix"}
    resolved = {}
    for name, version in ACCESSKIT_CRATES.items():
        candidates = [entry for entry in metadata["packages"] if entry["name"] == name and entry["version"] == version]
        if len(candidates) != 1:
            raise ValueError("Native AccessKit must resolve one exact original package: " + name)
        entry = candidates[0]
        if entry.get("source") != ui_source or Path(entry["manifest_path"]).resolve(strict=True) != vendor / paths[name] / "Cargo.toml":
            raise ValueError("Native AccessKit and original UI must use the same pinned Hepta source: " + name)
        resolved[name] = {"version": version, "source": entry.get("source")}
    upstream = json.loads((vendor / "HEPTA_UPSTREAM.json").read_bytes())
    if upstream["revision"] != ACCESSKIT_REVISION or upstream["crates"] != ACCESSKIT_CRATES:
        raise ValueError("Unexpected native AccessKit upstream provenance")
    return vendor, resolved


def checked(data, record):
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError("resource identity differs: " + str(record))
    return data


def original_bytes(path, record, url, offline, mirrors=()):
    if path.is_file():
        with path.open("rb") as stream:
            return checked(stream.read(record["bytes"] + 1), record)
    if offline or not url:
        raise ValueError("original resource is absent: " + str(path))
    failures = []
    for candidate in (url, *mirrors):
        request = urllib.request.Request(candidate, headers={"User-Agent": "Trillionnium-original-Makepad-packager"})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return checked(response.read(record["bytes"] + 1), record)
        except urllib.error.URLError as error:
            failures.append(str(error))
    raise ValueError("original resource download failed: " + "; ".join(failures))


def package(metadata, destination, offline=False, liberation_source=None,
            sdk_source_profile=None, sdk_original_metadata=None, sdk_cargo_config=None, metadata_bytes=None,
            asset_cache=None):
    selected = {}
    for name in ("hepta-robrix-ui", "hepta-control-core", "makepad-widgets"):
        candidates = [entry for entry in metadata["packages"] if entry["name"] == name]
        if len(candidates) != 1:
            raise ValueError("Native product must resolve one exact package: " + name)
        selected[name] = candidates[0]
    ui = selected["hepta-robrix-ui"]
    core = selected["hepta-control-core"]
    sdk = selected["makepad-widgets"]
    if ui.get("source") != core.get("source"):
        raise ValueError("original UI and core must resolve to the same source")
    ui_root = Path(ui["manifest_path"]).parent
    sdk_root = Path(sdk["manifest_path"]).parent
    sdk_files, sdk_identity = {}, {}
    nodes = {entry["id"]: entry for entry in (metadata.get("resolve") or {}).get("nodes", [])}
    if ui["id"] not in nodes:
        raise ValueError("Resource preparation requires full Cargo metadata with resolved features")
    clipboard_feature = "native-clipboard-sdk" in nodes[ui["id"]].get("features", [])
    original_source = "git+" + native_sdk.UPSTREAM + "?rev=" + native_sdk.REVISION + "#" + native_sdk.REVISION
    if sdk.get("source") == original_source:
        if clipboard_feature:
            raise ValueError("Native clipboard feature requires the exact verified prepared SDK source")
        if any((sdk_source_profile, sdk_original_metadata, sdk_cargo_config)):
            raise ValueError("Patch evidence cannot be attached to unmodified original SDK resolution")
        sdk_source = original_source
    elif sdk.get("source") is None:
        if not clipboard_feature:
            raise ValueError("Prepared SDK requires the explicit native-clipboard-sdk feature")
        sdk_files, sdk_identity = prepare_native_sdk.prepare(
            metadata_bytes or json.dumps(metadata).encode(), ui_root, sdk_root,
            sdk_source_profile, sdk_original_metadata, sdk_cargo_config)
        sdk_source = native_sdk.SOURCE_ID
    else:
        raise ValueError("Makepad must resolve to the original pinned SDK or its exact verified prepared source")
    vendor, accessibility_sources = original_accesskit(metadata, ui_root, ui.get("source"))
    native = ui_root / "../../../hepta-native/resources"
    inventory_path = native / "NATIVE-ASSETS.json"
    inventory = json.loads(inventory_path.read_text())
    dependency_path = native / "NATIVE-DEPENDENCIES.json"
    dependencies = json.loads(dependency_path.read_bytes())
    if (dependencies["schema"] != "hepta.native-dependency-notices.v1"
            or dependencies["upstreamRevision"] != ACCESSKIT_REVISION
            or dependencies["crates"] != ACCESSKIT_CRATES
            or {entry["path"] for entry in dependencies["files"]} != {"dependency-notices/accesskit/" + name for name in DEPENDENCY_FILES}
            or len(dependencies["files"]) != len(DEPENDENCY_FILES)):
        raise ValueError("Unsupported native dependency notice inventory")
    fonts = json.loads((ui_root / "resources/fonts/MANIFEST.json").read_text())
    font_urls = {item["logical"]: item["url"] for item in fonts["assets"]}
    if (inventory["schema"] != "hepta.native-embedded-assets.v1"
            or inventory["makepadRevision"] != "337566c8b25d47f7e4fff6a202157b65bf183330"
            or len(inventory["assets"]) != 29 or len(inventory["noticeFileSha256"]) != 15):
        raise ValueError("unsupported original resource inventory")
    if destination.exists():
        raise ValueError("destination already exists; keep the previous bundle intact")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".makepad-assets-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        for entry in inventory["assets"]:
            logical = entry["logical"]
            package_name, relative = logical.split("/", 1)
            source = {"makepad_widgets": sdk_root, "hepta_robrix_ui": ui_root}[package_name] / relative
            # A retained original bundle can supply missing download-only fonts
            # without modifying a Cargo checkout. Every cached byte still has
            # to match this source's original inventory; invalid cache is fatal.
            cached = asset_cache / logical if asset_cache is not None else None
            if cached is not None and cached.is_file():
                data = original_bytes(cached, entry, None, True)
            else:
                data = original_bytes(source, entry, font_urls.get(logical), offline)
            target = stage / logical
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for entry in inventory["noticeFileSha256"]:
            data = original_bytes(native / entry["path"], entry, None, offline)
            target = stage / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        source = inventory["liberationSource"]
        source_path = liberation_source or native / "sources" / source["file"]
        data = original_bytes(source_path, source, source["url"], offline or liberation_source is not None,
                              LIBERATION_SOURCE_MIRRORS.get(source["sha256"], ()))
        (stage / "sources").mkdir()
        (stage / "sources" / source["file"]).write_bytes(data)
        shutil.copyfile(inventory_path, stage / "NATIVE-ASSETS.json")
        shutil.copyfile(dependency_path, stage / "NATIVE-DEPENDENCIES.json")
        for entry in dependencies["files"]:
            name = entry["path"].removeprefix("dependency-notices/accesskit/")
            data = original_bytes(vendor / name, entry, None, True)
            target = stage / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        identity = {"schema": "trill.original-makepad-bundle.v1", "heptaSource": ui.get("source"),
                    "makepadSource": sdk_source, "assets": 29, "notices": 15,
                    "inventorySha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
                    "dependencyInventorySha256": hashlib.sha256(dependency_path.read_bytes()).hexdigest(),
                    "dependencyNotices": len(DEPENDENCY_FILES), "accessibilitySources": accessibility_sources}
        for name, data in sdk_files.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        identity.update(sdk_identity)
        (stage / "bundle.json").write_text(json.dumps(identity, indent=2) + "\n")
        stage.rename(destination)
    return identity


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True, type=Path,
                        help="Full metadata: trill-shell/hepta-native-makepad baseline, or explicit trill-shell/hepta-native-clipboard-sdk candidate")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--liberation-source", type=Path,
                        help="Existing exact source archive; the pinned size and SHA-256 remain mandatory")
    parser.add_argument("--asset-cache", type=Path,
                        help="Read original assets by logical path from an existing bundle; all pinned hashes remain mandatory")
    parser.add_argument("--sdk-source-profile", type=Path, help="Exact post-resolution original SDK source receipt")
    parser.add_argument("--sdk-original-metadata", type=Path, help="Complete native metadata before the SDK source override")
    parser.add_argument("--sdk-cargo-config", type=Path, help="Exact generated all-crate SDK override TOML")
    options = parser.parse_args()
    print(json.dumps(package(json.loads(options.metadata.read_text()), options.output.absolute(),
                             options.offline, options.liberation_source, options.sdk_source_profile,
                             options.sdk_original_metadata, options.sdk_cargo_config, options.metadata.read_bytes(),
                             options.asset_cache)))
