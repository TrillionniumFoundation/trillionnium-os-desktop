#!/usr/bin/env python3
"""Build a separate minimal installed G6a fixture from exact signed packages.

No D1/D2I artifact is edited or qualified. Run in an isolated root builder;
only files beneath the new output directory are created. The signing key is a
new disposable *test* key, never a repository or production signing authority.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GUEST = ROOT / "packaging/debian/g6a"
spec = importlib.util.spec_from_file_location("g6a_guest_build", GUEST / "guest_selector.py")
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


def run(args, *, pass_fds=()):
    result = subprocess.run([str(arg) for arg in args], pass_fds=pass_fds, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(f"fixture command failed: {args[0]}: {result.stderr.decode(errors='replace')[-2000:]}")
    return result.stdout


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def put(path, payload, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)


def extract_package(path, entry, destination):
    """Extract only the exact signed-index bytes captured in a sealed fd.

    A downloaded path can change after the inventory scan. dpkg-deb therefore
    never receives that mutable name as its authenticated input.
    """
    source = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    snapshot = None
    try:
        metadata = os.fstat(source)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != entry["size"] or not 0 < metadata.st_size <= 512 * 1024**2:
            raise RuntimeError("bounded regular signed package required")
        snapshot = os.memfd_create("g6a-signed-package", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        sha256 = hashlib.sha256()
        remaining = entry["size"]
        while remaining:
            chunk = os.read(source, min(1024**2, remaining))
            if not chunk:
                raise RuntimeError("signed package snapshot truncated")
            sha256.update(chunk)
            cursor = 0
            while cursor < len(chunk):
                written = os.write(snapshot, chunk[cursor:])
                if written <= 0:
                    raise RuntimeError("signed package snapshot write failed")
                cursor += written
            remaining -= len(chunk)
        if os.read(source, 1) or sha256.hexdigest() != entry["sha256"]:
            raise RuntimeError("actual extracted bytes differ from signed index")
        fcntl.fcntl(snapshot, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        run(["dpkg-deb", "--extract", f"/proc/self/fd/{snapshot}", destination], pass_fds=(snapshot,))
    finally:
        if snapshot is not None:
            os.close(snapshot)
        os.close(source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--packages-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("isolated root builder required")
    output = args.output_dir.absolute()
    if output.exists():
        raise RuntimeError("new empty output directory required")
    selection = json.loads((ROOT / "manifests/debian-g6a.selection.v1.json").read_bytes())
    if digest(args.lock) != selection["package_lock_sha256"]:
        raise RuntimeError("package lock is not the exact reviewed G6a input")
    lock = json.loads(args.lock.read_bytes())
    if lock["package_set_sha256"] != selection["package_set_sha256"] or lock["resolved_package_count"] != selection["package_count"]:
        raise RuntimeError("package closure binding differs")
    packages = lock["packages"]
    if hashlib.sha256(guest.canonical(packages)).hexdigest() != lock["package_set_sha256"]:
        raise RuntimeError("package closure digest differs")
    expected = {item["sha256"]: item for item in packages}
    actual = {}
    for path in args.packages_dir.rglob("*.deb"):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("unsafe package input")
        sha = digest(path)
        if sha not in expected or sha in actual or path.stat().st_size != expected[sha]["size"]:
            raise RuntimeError("package bytes are outside exact signed closure")
        actual[sha] = path
    if set(actual) != set(expected):
        raise RuntimeError("complete downloaded package closure required")
    output.mkdir(mode=0o755)
    staging = output / "initramfs-root"
    artifacts = output / "artifacts"
    staging.mkdir()
    artifacts.mkdir()
    for item in sorted(packages, key=lambda value: value["package"]):
        extract_package(actual[item["sha256"]], item, staging)
    # Extracted usr-merged packages do not run base-files postinst. Create only
    # the fixed merged-usr aliases needed by the actual ELF interpreters.
    for name in ("bin", "sbin", "lib", "lib64"):
        alias = staging / name
        if not alias.exists():
            alias.symlink_to("usr/" + name)
    kernels = list((staging / "boot").glob("vmlinuz-*"))
    configs = list((staging / "boot").glob("config-*"))
    if len(kernels) != 1 or len(configs) != 1:
        raise RuntimeError("exactly one signed-package kernel required")
    kernel_version = kernels[0].name.removeprefix("vmlinuz-")
    configuration = configs[0].read_text()
    for key in ("CONFIG_BLK_DEV_DM=", "CONFIG_DM_VERITY=", "CONFIG_EXT4_FS=", "CONFIG_VIRTIO_BLK=", "CONFIG_DEVTMPFS="):
        if not any(key + state in configuration.splitlines() for state in ("m", "y")):
            raise RuntimeError("kernel lacks required actual driver: " + key)
    shutil.copyfile(kernels[0], artifacts / "vmlinuz")
    run(["chroot", staging, "/usr/sbin/depmod", kernel_version])
    # Keep actual dependencies of the fixed guest devices, not the whole
    # distribution's several-hundred-MiB module catalog in early RAM.
    needed = set()
    for module in ("virtio_pci", "virtio_blk", "ext4", "dm_mod", "dm_verity", "sha256_generic"):
        dependencies = run(["chroot", staging, "/usr/sbin/modprobe", "--ignore-install", "--show-depends", "--set-version", kernel_version, module]).decode("ascii")
        for line in dependencies.splitlines():
            if line.startswith("insmod "):
                path = staging / line.split()[1].removeprefix("/")
                resolved = path.resolve()
                resolved.relative_to(staging)
                needed.add(resolved)
            elif line and not line.startswith("builtin "):
                raise RuntimeError("unexpected actual kernel dependency command")
    for path in (staging / "usr/lib/modules").rglob("*"):
        if path.is_file() and ".ko" in path.name and path.resolve() not in needed:
            path.unlink()
    run(["chroot", staging, "/usr/sbin/depmod", kernel_version])
    shutil.rmtree(staging / "boot")
    # No package post-install scripts, system services or desktop are claimed.
    for directory in ("proc", "sys", "dev", "state", "newroot", "run", "tmp"):
        (staging / directory).mkdir(exist_ok=True)
    for file, destination in (("init", "init"), ("guest_selector.py", "guest_selector.py")):
        put(staging / destination, (GUEST / file).read_bytes(), 0o755)
    private = output / "fixture-private.pem"
    run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", private])
    private.chmod(0o600)
    public = run(["openssl", "pkey", "-in", private, "-pubout"])
    put(staging / "g6a-public.pem", public, 0o444)
    state_tree = output / "state-root"
    state_root = state_tree / "g6a"
    state_root.mkdir(parents=True, mode=0o700)
    state_root.chmod(0o700)
    descriptors = {}
    for slot in ("A", "B"):
        tree = output / ("root-" + slot)
        shutil.copytree(staging, tree, symlinks=True, ignore=shutil.ignore_patterns("boot", "newroot"))
        modules = tree / "usr/lib/modules"
        if modules.exists():
            shutil.rmtree(modules)
        put(tree / "etc/g6a-slot", (slot + "\n").encode(), 0o444)
        put(tree / "usr/lib/g6a/root_probe.py", (GUEST / "root_probe.py").read_bytes(), 0o555)
        put(tree / "usr/sbin/g6a-fixture-init", (GUEST / "fixture-init").read_bytes(), 0o555)
        (tree / "newroot").mkdir(exist_ok=True)
        image = artifacts / ("root-" + slot + ".ext4")
        with image.open("wb") as stream:
            stream.truncate(selection["root_image_bytes"])
        run(["mke2fs", "-q", "-F", "-t", "ext4", "-b", "4096", "-O", "^has_journal", "-E", "lazy_itable_init=0", "-d", tree, image])
        run(["e2fsck", "-fn", image])
        hashes = artifacts / ("root-" + slot + ".verity")
        salt = hashlib.sha256(("g6a fixture salt " + slot).encode()).hexdigest()
        value = {"schema": guest.SCHEMA, "slot": slot, "generation": 1 if slot == "A" else 2,
                 "data_sha256": digest(image), "data_bytes": image.stat().st_size,
                 "hash_sha256": "0" * 64, "hash_bytes": 4096,
                 "verity": {"format": 1, "algorithm": "sha256", "data_block_size": 4096, "hash_block_size": 4096, "data_blocks": image.stat().st_size // 4096, "hash_start_block": 0, "root_hash": "0" * 64, "salt": salt},
                 "signature_sha256": "0" * 64, "fixture_only": True, "production_activation_enabled": False}
        root_hash_file = output / ("root-hash-" + slot)
        run(["veritysetup", *guest.verity_options(value), "--root-hash-file", root_hash_file, "format", image, hashes])
        value["verity"]["root_hash"] = root_hash_file.read_text().strip()
        value["hash_sha256"] = digest(hashes)
        value["hash_bytes"] = hashes.stat().st_size
        run(["veritysetup", *guest.verity_options(value), "verify", image, hashes, value["verity"]["root_hash"]])
        preimage = output / ("preimage-" + slot)
        put(preimage, guest.signing_bytes(value))
        signature = run(["openssl", "dgst", "-sha256", "-sign", private, preimage])
        value["signature_sha256"] = hashlib.sha256(signature).hexdigest()
        guest.verify_signature(value, signature, public)
        put(state_root / ("root-" + slot + ".json"), guest.canonical(value))
        put(state_root / ("root-" + slot + ".sig"), signature)
        descriptors[slot] = value
    state = {"schema": guest.STATE_SCHEMA, "source_slot": "A", "pending_slot": None, "attempts": 0, "boot_number": 0, "operation_id": os.urandom(16).hex(), "fixture_only": True, "production_activation_enabled": False}
    put(state_root / "boot-state.json", guest.canonical(state))
    put(state_root / "case-control.json", guest.canonical({"pause_at": None, "target_failure": False}))
    state_image = artifacts / "state.ext4"
    with state_image.open("wb") as stream:
        stream.truncate(selection["state_image_bytes"])
    run(["mke2fs", "-q", "-F", "-t", "ext4", "-b", "4096", "-E", "lazy_itable_init=0,lazy_journal_init=0", "-d", state_tree, state_image])
    # Kernel /init owns selection. The host never varies the root= slot.
    initrd = artifacts / "initrd.img"
    listing = subprocess.run(["find", ".", "-print0"], cwd=staging, stdout=subprocess.PIPE, check=True).stdout
    cpio = subprocess.run(["cpio", "--null", "-o", "-H", "newc", "--owner=0:0", "--quiet"], cwd=staging, input=listing, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
    import gzip
    put(initrd, gzip.compress(cpio, compresslevel=1, mtime=0), 0o644)
    # Images/hash trees are public test artifacts; only the disposable signing
    # key outside this directory remains private. QEMU runs without host root.
    for path in artifacts.iterdir():
        path.chmod(0o644)
    report = {"schema": "trillionnium.desktop.g6a-build-result.v1", "fixture_only": True,
              "package_lock_sha256": digest(args.lock), "package_set_sha256": lock["package_set_sha256"],
              "kernel_version": kernel_version, "fixture_public_key_sha256": hashlib.sha256(public).hexdigest(),
              "source_inputs": {str(path.relative_to(ROOT)): digest(path) for path in [Path(__file__).resolve(), *sorted(GUEST.iterdir())] if path.is_file()},
              "kernel_driver_dependencies": {str(path.relative_to(staging)): digest(path) for path in sorted(needed)},
              "descriptors": descriptors, "artifacts": {path.name: {"bytes": path.stat().st_size, "sha256": digest(path)} for path in sorted(artifacts.iterdir())},
              "production_activation_enabled": False, "firmware_authenticated": False,
              "desktop_installed_qualified": False, "measured_health_qualified": False, "protected_rollback_anchor": False, "reproducible_build_qualified": False}
    put(artifacts / "build-result.json", guest.canonical(report), 0o644)
    print(json.dumps({"artifacts": str(artifacts), "fixture_only": True, "production_activation_enabled": False}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("G6a fixture build refused: " + str(error), file=sys.stderr)
        raise SystemExit(1)
