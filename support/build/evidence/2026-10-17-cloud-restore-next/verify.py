#!/usr/bin/env python3
"""Verify preserved new-instance dependency restoration without installers or VMs."""
import gzip
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(name):
    require(isinstance(name, str) and name, "empty/non-string path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and str(path) == name and all(x not in (".", "..") for x in path.parts), "unsafe member path")
    return name


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "input is not a regular private file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read()
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        require(tuple(getattr(before, k) for k in fields) == tuple(getattr(after, k) for k in fields), "input changed during read")
        return data
    finally:
        os.close(fd)


def sums(raw):
    result = {}
    for line in raw.decode().splitlines():
        digest, name = line.split("  ", 1)
        canonical(name)
        require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest) and name not in result, "invalid checksum entry")
        result[name] = digest
    return result


def paragraphs(source):
    current = {}
    previous = None
    for line in source:
        line = line.rstrip("\r\n")
        if not line:
            if current:
                yield current
            current, previous = {}, None
        elif line[0].isspace() and previous:
            current[previous] += " " + line.strip()
        elif ":" in line:
            previous, value = line.split(":", 1)
            current[previous] = value.strip()
    if current:
        yield current


def main():
    outer = sums(regular(HERE / "SHA256SUMS"))
    for name, digest in outer.items():
        require(sha(regular(HERE / name)) == digest, "outer checksum mismatch: " + name)
    description = json.loads(regular(HERE / "archive.json"))
    member_description = json.loads(regular(HERE / "member-manifest.json"))["members"]
    compressed = bytearray()
    for part in description["parts"]:
        raw = regular(HERE / canonical(part["path"]))
        require(0 < len(raw) <= 2097152 and len(raw) == part["size"] and sha(raw) == part["sha256"], "archive chunk differs")
        compressed.extend(raw)
    require(len(compressed) == description["compressed_size"] and sha(compressed) == description["sha256"], "assembled archive differs")
    payload = {}
    with tarfile.open(fileobj=io.BytesIO(compressed), mode="r|gz") as archive:
        for index, info in enumerate(archive):
            require(index < len(member_description), "extra tar member")
            expected = member_description[index]
            require(info.name == canonical(expected["path"]) and info.name not in payload and info.isfile() and info.size == expected["size"], "tar type/name/order/size differs")
            require((info.uid, info.gid, info.mtime, info.mode, info.uname, info.gname) == (0, 0, 0, 0o644, "", ""), "non-canonical tar metadata")
            raw = archive.extractfile(info).read()
            require(len(raw) == expected["size"] and sha(raw) == expected["sha256"], "tar member digest differs")
            payload[info.name] = raw
    require(len(payload) == len(member_description) == description["regular_member_count"] == 226, "frozen member count differs")
    inner = sums(payload["SHA256SUMS"])
    # The original immutable freeze's checksum writer excluded every basename
    # SHA256SUMS. Preserve it unchanged and check the nested prior checksum
    # through the captured manifest and its independently fixed hash below.
    require(set(inner) == set(payload) - {"SHA256SUMS", "prior-reference/SHA256SUMS"} and all(sha(payload[n]) == h for n, h in inner.items()), "inner checksum set differs")
    require(sha(payload["SHA256SUMS"]) == description["inner_sha256sums_sha256"] == "a3cd39678aa15bb850f538d6bc7b1a661a9a3ed1559a080231c75c42611fe00a", "frozen checksum identity differs")
    load = lambda name: json.loads(payload[name])
    captured = load("manifest.json")
    require(sha(payload["manifest.json"]) == "5a84bb6223c17c7dfc4dfe78e23c31f55ecbc1f6d78d512edcd9d34d3c214d21", "frozen source receipt identity differs")
    require({r["path"] for r in captured["files"]} == set(payload) - {"manifest.json", "SHA256SUMS"}, "capture receipt coverage differs")
    for row in captured["files"]:
        require(len(payload[row["path"]]) == row["bytes"] and sha(payload[row["path"]]) == row["sha256"], "capture row differs")
    require(sha(payload["prior-reference/SHA256SUMS"]) == "638b3c5e0a1534a4c9c0656af5390374ace6f97ffd92a985cb01f2db4949da00", "prior phase checksum binding differs")
    lock = load("prior-reference/package-lock.json")["entries"]
    wanted = {(p["Package"], p["Version"]): p for p in lock}
    require(len(lock) == len(wanted) == 57, "locked package count differs")
    found = set()
    key_raw = payload["prior-reference/signatures/ubuntu-archive-keyring.gpg"]
    require(sha(key_raw) == "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31", "public keyring differs")
    require(sha(payload["prior-reference/experimental-native/restore.py"]) == "c7570e7e6cf5ef756c80eb728a46b456754008032aeb0685401cb7828f9232dd", "archived native controller differs")
    require(payload["native-original/restore.py"] == payload["prior-reference/experimental-native/restore.py"], "executed native controller differs from archive")
    for name, expected in (("prior-reference/experimental-native/restore.py", "54bbfcc65d14c781e401d11785d544c676cdbf68"), ("prior-reference/package-lock.json", "8bf22b2b33cb1dfcdb4edb5c063e98119dcfca50"), ("prior-reference/rust-restore/restore-rust.py", "926306c8c7e59a113b920abda27599b923bc3596")):
        raw = payload[name]
        require(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected, "prior source Git blob differs")
    index_count = 0
    # This temporary directory is task-owned, exclusively created and removed;
    # no archived tar pathname is extracted or interpreted as a write location.
    with tempfile.TemporaryDirectory(prefix=".verify-", dir=HERE) as temporary:
        temporary = Path(temporary)
        key = temporary / "archive-keyring.gpg"
        key.write_bytes(key_raw)
        for suite in ("noble", "noble-updates", "noble-security"):
            signed = temporary / (suite + "-InRelease")
            signed.write_bytes(payload["native-original/signed/" + suite + "-InRelease"])
            release = temporary / (suite + "-Release")
            result = subprocess.run(["gpgv", "--keyring", str(key), "--status-fd", "1", "--output", str(release), str(signed)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, check=False)
            require(result.returncode == 0, "fresh InRelease signature invalid: " + result.stdout.decode(errors="replace"))
            require(release.read_bytes() == payload["native-original/signed/" + suite + "-Release"], "authenticated Release body differs")
            hashes, active = {}, False
            for line in release.read_text().splitlines():
                if line == "SHA256:":
                    active = True
                elif line and not line[0].isspace():
                    active = False
                elif active:
                    digest, size, name = line.split()
                    hashes[name] = (digest, int(size))
            for component in ("main", "universe"):
                raw = payload["native-original/indexes/" + suite + "-" + component + "-Packages.xz"]
                digest, size = hashes[component + "/binary-amd64/Packages.xz"]
                require(len(raw) == size and sha(raw) == digest, "signed index digest differs")
                index_count += 1
                with lzma.open(io.BytesIO(raw), "rt") as stream:
                    for package in paragraphs(stream):
                        identity = (package.get("Package"), package.get("Version"))
                        if identity in wanted and package.get("Architecture") in ("amd64", "all"):
                            require(all(str(package.get(k)) == str(wanted[identity].get(k)) for k in ("Package", "Version", "Architecture", "Filename", "Size", "SHA256")), "locked record differs from signed stanza")
                            found.add(identity)
    require(found == set(wanted), "incomplete signed package binding")
    fields = ("Package", "Version", "Architecture", "Filename", "Size", "SHA256")
    normalize = lambda rows: sorted(tuple(row[k] for k in fields) for row in rows)
    plan = load("native-original/package-plan.json")
    require(normalize(plan) == normalize(lock) and sum(p["Size"] for p in plan) == 132706754, "actual signed plan differs")
    downloads = load("native-original/verified-downloads.json")
    require(len(downloads) == 57 and {(d["package"], d["version"]) for d in downloads} == set(wanted), "download receipt set differs")
    for row in downloads:
        expected = wanted[(row["package"], row["version"])]
        require(row["bytes"] == expected["Size"] and row["sha256"] == expected["SHA256"], "download receipt digest differs")
    extracts = load("native-original/extractions.json")
    require(len(extracts) == 57 and {(e["package"], e["version"]) for e in extracts} == set(wanted), "extraction receipt set differs")
    for row in extracts:
        require(row["extraction_exit"] == 0 and row["maintainer_scripts_executed"] is False and row["deb_sha256"] == wanted[(row["package"], row["version"])]["SHA256"], "extraction receipt invalid")
    for group, count in (("restore-native", 4), ("restore-native-validation", 19), ("restore-rust", 12)):
        commands = load(group + "/commands.json")
        require(len(commands) == count and all(c["returncode"] == 0 for c in commands), "actual command count/exit differs: " + group)
        for row in commands:
            log = payload[group + "/" + (Path(row["log"]).name if "log" in row else row["name"] + ".log")]
            require(len(log) == row["log_bytes"] and sha(log) == row["log_sha256"], "command log differs")
    identities = load("restore-native-validation/identities.json")
    require(len(identities) == 10 and all(i["passed"] and i["sha256"] == i["expected_sha256"] for i in identities), "private executable/BIOS identity receipts differ")
    qemu = load("restore-native-validation/qemu-paused.json")
    require(qemu["passed"] and qemu["alive_after_one_second"] and not qemu["unexpected_warning"] and not qemu["guest_kernel_executed"], "paused QEMU receipt invalid")
    require(all(flag in qemu["argv"] for flag in ("-bios", "-L", "-S", "-nodefaults", "-no-user-config")), "private QEMU probe arguments incomplete")
    qlog = payload["restore-native-validation/qemu-paused.log"]
    require(len(qlog) == qemu["log_bytes"] and sha(qlog) == qemu["log_sha256"], "paused QEMU log differs")
    nightly = payload["restore-rust-inputs/channel-rust-nightly.toml"]
    require(len(nightly) == 929653 and sha(nightly) == "c0b09f4e128768b2d6eab27050625a1ce974f8b39c07871370368cd82fbf8617", "complete fresh nightly body differs")
    require(gzip.decompress(regular(HERE / "fresh-nightly-manifest.toml.gz")) == nightly, "direct fresh manifest copy differs")
    inputs = load("restore-rust-inputs/result.json")
    require(inputs["all_passed"] and len(inputs["fresh_inputs"]) == 2 and all(i["passed"] and i["returncode"] == 0 and i["actual_sha256"] == i["expected_sha256"] and i["actual_size"] == i["expected_size"] for i in inputs["fresh_inputs"]), "fresh Rust download receipts differ")
    require("87e5904f5eb6398af6b22eac2802c78934260c48" in payload["restore-rust/rustc-version.log"].decode(), "compiler commit differs")
    components = payload["restore-rust/components-installed.log"].decode()
    require(all(c in components for c in ("rust-src", "rustc-dev", "llvm-tools", "rustfmt", "clippy")), "fixed compiler components missing")
    require("x86_64-unknown-none" in payload["restore-rust/targets-installed.log"].decode(), "freestanding target missing")
    vdso = payload["restore-rust/vdso-identity.log"].decode()
    require("8af571775a3d3a1df3e84fc9709b9d6b160c771a" in vdso and "8e0a300d78c2a020ccc79f1253bc27a8301416e6" in vdso, "vDSO source differs")
    rust = load("restore-rust/result.json")
    require(rust["passed"] and rust["original_eight_commands_passed"] and not rust["global_cargo_osdk_installed"], "Rust completion receipt invalid")
    rust_commands = {r["name"]: r for r in load("restore-rust/commands.json")}
    require(rust_commands["cargo-binutils-install"]["argv"] == ["cargo", "+nightly-2026-07-21", "install", "--locked", "--version", "0.4.0", "cargo-binutils"], "locked cargo-binutils operation differs")
    require(rust_commands["fixed-toolchain-install"]["argv"] == ["rustup", "toolchain", "install", "nightly-2026-07-21", "--profile", "minimal", "--component", "rust-src,rustc-dev,llvm-tools-preview,rustfmt,clippy", "--target", "x86_64-unknown-none"], "fixed toolchain operation differs")
    require(rust_commands["rustup-install"]["argv"][1:] == ["-y", "--no-modify-path", "--default-toolchain", "none"], "private installer options differ")
    before = load("before-restoration-audit/host-probe.json")
    require(before["hostname"] == captured["actual_host"] == "24f0ea2620fe" and before["boot_id"] == captured["boot_id"] == "952006db-88a3-4a56-8049-0adbbe2acfb2", "actual new instance identity differs")
    require(before["dpkg_status_sha256"] == "315debd2c0d91242550234b1fc27842103bccdf4274aa75c59b6d1f51d07966e" and before["keyring_sha256"] == sha(key_raw), "public baseline differs")
    print(json.dumps({"verified": True, "outer_entries": len(outer), "frozen_regular_members": len(payload), "fresh_signed_releases": 3, "signed_indexes": index_count, "locked_packages": len(wanted), "native_runtime_checks": 19, "rust_commands": 12, "actual_host": captured["actual_host"], "archive_sha256": description["sha256"], "scope": "Offline inputs and original completed receipt verification only; no download, dependency installation, compiler or guest rerun."}, sort_keys=True))


if __name__ == "__main__":
    main()
