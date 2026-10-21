#!/usr/bin/env python3
"""Verify this archive offline; write only temporary signature/index outputs.

No package, installer, extracted native tool, or network client is executed.
The native and Rust results are checked as retained receipts, not rerun here.
"""

import argparse
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


KEYRING_SHA256 = "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31"
SUITES = ("noble", "noble-updates", "noble-security")
COMPONENTS = ("main", "universe")
PACKAGE_COUNT = 57
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class VerificationError(Exception):
    """An archive object does not satisfy the recorded schema or binding."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, f"{label}: invalid integer")
    return value


def sha256_value(value, label):
    require(isinstance(value, str) and SHA256_RE.fullmatch(value),
            f"{label}: invalid SHA256")
    return value


def text_value(value, label):
    require(isinstance(value, str), f"{label}: expected string")
    return value


def relative_path(value, label):
    text_value(value, label)
    path = PurePosixPath(value)
    require(value and not path.is_absolute() and ".." not in path.parts
            and str(path) == value and "\\" not in value,
            f"{label}: expected normalized relative archive path")
    return path


def archive_file(root, value):
    path = root.joinpath(*relative_path(value, value).parts)
    require(path.is_file() and not path.is_symlink(), f"{value}: missing regular file")
    require(path.resolve().is_relative_to(root), f"{value}: path escapes archive")
    return path


def read_json(root, value):
    path = archive_file(root, value)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{value}: invalid UTF-8 JSON: {error}") from error


def records(value, count, label):
    require(isinstance(value, list) and len(value) == count,
            f"{label}: expected {count} records")
    require(all(isinstance(record, dict) for record in value),
            f"{label}: expected object records")
    return value


def file_digest(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def release_hashes(raw, suite):
    require(b"\r" not in raw, f"{suite}: Release is not LF text")
    lines = raw.decode("utf-8").splitlines()
    require(f"Suite: {suite}" in lines, f"{suite}: signed Release suite mismatch")
    positions = [index for index, line in enumerate(lines) if line == "SHA256:"]
    require(len(positions) == 1, f"{suite}: expected one signed SHA256 table")
    result = {}
    for line in lines[positions[0] + 1:]:
        if not line.startswith((" ", "\t")):
            break
        pieces = line.split()
        require(len(pieces) == 3, f"{suite}: malformed signed SHA256 entry")
        digest, size, path = pieces
        sha256_value(digest, f"{suite}/{path}")
        require(size.isdecimal(), f"{suite}/{path}: invalid signed size")
        relative_path(path, f"{suite}/{path}")
        require(path not in result, f"{suite}/{path}: duplicate signed entry")
        result[path] = (int(size), digest)
    require(result, f"{suite}: empty signed SHA256 table")
    return result


def verify_signatures(root, temporary, gpgv):
    keyring = archive_file(root, "signatures/ubuntu-archive-keyring.gpg")
    require(file_digest(keyring)[1] == KEYRING_SHA256, "Ubuntu keyring SHA256 mismatch")
    home = temporary / "gnupg"
    home.mkdir(mode=0o700)
    result = {}
    for suite in SUITES:
        signed = archive_file(root, f"signatures/{suite}-InRelease")
        output = temporary / f"{suite}-Release"
        command = [gpgv, "--homedir", str(home), "--keyring", str(keyring),
                   "--status-fd", "1", "--output", str(output), str(signed)]
        process = subprocess.run(command, capture_output=True, check=False, timeout=60)
        status = process.stdout.decode("utf-8", errors="replace")
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        require(process.returncode == 0, f"{suite}: gpgv failed: {detail}")
        require("[GNUPG:] VALIDSIG " in status,
                f"{suite}: gpgv returned no valid-signature status")
        require(output.is_file() and output.stat().st_size > 0,
                f"{suite}: gpgv produced no signed Release content")
        result[suite] = release_hashes(output.read_bytes(), suite)
    return result


def deb822_fields(raw, label):
    require(b"\r" not in raw, f"{label}: stanza is not LF text")
    text = raw.decode("utf-8")
    result = {}
    current = None
    ended = False
    for line in text.split("\n"):
        if line == "":
            ended = True
            continue
        require(not ended, f"{label}: contains more than one paragraph")
        if line[0] in " \t":
            require(current is not None, f"{label}: orphan continuation")
            result[current] += "\n" + line
            continue
        key, separator, value = line.partition(":")
        require(separator and key and not any(char.isspace() for char in key),
                f"{label}: malformed field")
        require(key not in result, f"{label}: duplicate {key}")
        result[key] = value.lstrip(" \t")
        current = key
    return result


def lock_entries(root):
    lock = read_json(root, "package-lock.json")
    require(isinstance(lock, dict), "package-lock.json: expected object")
    require(type(lock.get("count")) is int and lock["count"] == PACKAGE_COUNT,
            "package-lock.json: count mismatch")
    entries = records(lock.get("entries"), PACKAGE_COUNT, "package-lock.json entries")
    by_package = {}
    stanza_paths = set()
    for entry in entries:
        package = text_value(entry.get("Package"), "lock Package")
        require(package and package not in by_package, f"{package}: duplicate/empty package")
        for field in ("Version", "Architecture", "Filename"):
            text_value(entry.get(field), f"{package}: {field}")
        for field in ("Depends", "Pre-Depends"):
            require(field in entry and (entry[field] is None or isinstance(entry[field], str)),
                    f"{package}: {field}: expected string or absent-field null")
        require(entry["Architecture"] in ("amd64", "all"),
                f"{package}: unexpected architecture")
        relative_path(entry["Filename"], f"{package}: Filename")
        require(entry["Filename"].endswith(".deb"), f"{package}: not a .deb Filename")
        integer(entry.get("Size"), f"{package}: Size", 1)
        sha256_value(entry.get("SHA256"), f"{package}: SHA256")
        require(entry.get("suite") in SUITES and entry.get("component") in COMPONENTS,
                f"{package}: invalid suite/component")
        stanza_path = text_value(entry.get("stanza_path"), f"{package}: stanza_path")
        require(stanza_path not in stanza_paths, f"{package}: duplicate stanza_path")
        stanza_paths.add(stanza_path)
        raw = archive_file(root, stanza_path).read_bytes()
        require(raw.endswith(b"\n\n"), f"{package}: stanza lacks final empty line")
        digest = sha256_value(entry.get("stanza_sha256"), f"{package}: stanza_sha256")
        require(hashlib.sha256(raw).hexdigest() == digest, f"{package}: saved stanza SHA mismatch")
        check_stanza_fields(raw, entry)
        by_package[package] = (entry, raw)
    return by_package


def check_stanza_fields(raw, entry):
    package = entry["Package"]
    fields = deb822_fields(raw, package)
    for field in ("Package", "Version", "Architecture", "Filename", "SHA256"):
        require(fields.get(field) == entry[field], f"{package}: {field} differs from index stanza")
    size = fields.get("Size", "")
    require(size.isdecimal() and int(size) == entry["Size"],
            f"{package}: Size differs from index stanza")
    for field in ("Depends", "Pre-Depends"):
        if entry[field] is None:
            require(field not in fields, f"{package}: {field} is present despite lock null")
        else:
            require(" ".join(fields.get(field, "").split()) == " ".join(entry[field].split()),
                    f"{package}: {field} differs from index stanza")
    return fields


def index_stanzas(path, label):
    stanza = []
    with lzma.open(path, "rb") as stream:
        for line in stream:
            require(b"\r" not in line, f"{label}: index is not LF text")
            line.decode("utf-8")
            if line == b"\n" and not stanza:
                continue
            stanza.append(line)
            if line == b"\n":
                yield b"".join(stanza)
                stanza = []
    if stanza:
        yield b"".join(stanza)


def verify_indexes(root, temporary, signed, selected):
    indexes = records(read_json(root, "index-storage.json"), 6, "index-storage.json")
    expected_pairs = {(suite, component) for suite in SUITES for component in COMPONENTS}
    seen = set()
    found = set()
    for number, index in enumerate(indexes):
        suite, component = index.get("suite"), index.get("component")
        pair = (suite, component)
        require(pair in expected_pairs and pair not in seen,
                "index-storage.json: invalid/duplicate suite/component")
        seen.add(pair)
        release_path = f"{component}/binary-amd64/Packages.xz"
        require(index.get("release_path") == release_path,
                f"{suite}/{component}: unexpected Release path")
        size = integer(index.get("expected_bytes"), f"{suite}/{component}: bytes", 1)
        digest = sha256_value(index.get("expected_sha256"), f"{suite}/{component}: SHA256")
        require(signed[suite].get(release_path) == (size, digest),
                f"{suite}/{component}: storage metadata differs from signed Release")
        parts = index.get("parts")
        require(isinstance(parts, list) and parts and all(isinstance(part, dict) for part in parts),
                f"{suite}/{component}: missing storage parts")
        combined = temporary / f"index-{number}.xz"
        combined_digest = hashlib.sha256()
        combined_size = 0
        with combined.open("xb") as destination:
            for part in parts:
                part_path = archive_file(root, part.get("path"))
                part_size = integer(part.get("bytes"), f"{part_path.name}: bytes", 1)
                part_sha = sha256_value(part.get("sha256"), f"{part_path.name}: SHA256")
                actual_sha = hashlib.sha256()
                actual_size = 0
                with part_path.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        destination.write(chunk)
                        actual_sha.update(chunk)
                        combined_digest.update(chunk)
                        actual_size += len(chunk)
                        combined_size += len(chunk)
                require((actual_size, actual_sha.hexdigest()) == (part_size, part_sha),
                        f"{part_path.name}: storage part size/SHA mismatch")
        require((combined_size, combined_digest.hexdigest()) == (size, digest),
                f"{suite}/{component}: reassembled index differs from signed Release")
        wanted = {package: value for package, value in selected.items()
                  if (value[0]["suite"], value[0]["component"]) == pair}
        for raw in index_stanzas(combined, f"{suite}/{component}"):
            fields = deb822_fields(raw, f"{suite}/{component}")
            package = fields.get("Package")
            if package not in wanted:
                continue
            entry, saved = wanted[package]
            if fields.get("Version") != entry["Version"] or fields.get("Architecture") != entry["Architecture"]:
                continue
            require(package not in found, f"{package}: multiple matching signed stanzas")
            require(raw == saved, f"{package}: saved stanza is not exact signed index bytes")
            check_stanza_fields(raw, entry)
            found.add(package)
    require(seen == expected_pairs, "index-storage.json: missing suite/component")
    require(found == set(selected), "selected packages absent from signed indexes: "
            + ", ".join(sorted(set(selected) - found)))
    return len(indexes)


def verify_package_receipts(root, selected):
    downloads = records(read_json(root, "experimental-native/verified-downloads.json"),
                        PACKAGE_COUNT, "verified-downloads.json")
    seen = set()
    for receipt in downloads:
        package = receipt.get("package")
        require(isinstance(package, str) and package in selected and package not in seen,
                "verified-downloads.json: unknown/duplicate package")
        seen.add(package)
        entry = selected[package][0]
        for recorded, locked in (("version", "Version"), ("architecture", "Architecture"),
                                 ("sha256", "SHA256")):
            require(receipt.get(recorded) == entry[locked], f"{package}: download {recorded} mismatch")
        require(type(receipt.get("bytes")) is int and receipt["bytes"] == entry["Size"],
                f"{package}: download size mismatch")
    require(seen == set(selected), "verified-downloads.json: package coverage mismatch")
    extractions = records(read_json(root, "experimental-native/extractions.json"),
                          PACKAGE_COUNT, "extractions.json")
    seen = set()
    for receipt in extractions:
        package = receipt.get("package")
        require(isinstance(package, str) and package in selected and package not in seen,
                "extractions.json: unknown/duplicate package")
        seen.add(package)
        entry = selected[package][0]
        require(receipt.get("version") == entry["Version"]
                and receipt.get("deb_sha256") == entry["SHA256"],
                f"{package}: extraction version/SHA mismatch")
        require(type(receipt.get("deb_bytes")) is int and receipt["deb_bytes"] == entry["Size"],
                f"{package}: extraction size mismatch")
        require(type(receipt.get("extraction_exit")) is int and receipt["extraction_exit"] == 0,
                f"{package}: extraction was not successful")
        require(receipt.get("maintainer_scripts_executed") is False,
                f"{package}: maintainer-script execution is not recorded false")
    require(seen == set(selected), "extractions.json: package coverage mismatch")
    return len(extractions)


def command_receipt(receipt, label):
    argv = receipt.get("argv")
    require(isinstance(argv, list) and argv and all(isinstance(arg, str) for arg in argv),
            f"{label}: missing command argv")
    require(isinstance(receipt.get("cwd"), str) and receipt["cwd"], f"{label}: missing cwd")


def verify_execution_receipts(root):
    rust = records(read_json(root, "rust-restore/rust-commands.json"), 8, "rust-commands.json")
    names = set()
    for receipt in rust:
        name = receipt.get("name")
        require(isinstance(name, str) and name and name not in names,
                "rust-commands.json: duplicate/empty name")
        names.add(name)
        command_receipt(receipt, name)
        require(type(receipt.get("returncode")) is int and receipt["returncode"] == 0,
                f"{name}: Rust command was not successful")
    initial = read_json(root, "before/controller.json")
    require(isinstance(initial, dict) and type(initial.get("returncode")) is int
            and initial["returncode"] == 100,
            "before/controller.json: original apt failure 100 not preserved")
    checks = records(read_json(root, "experimental-native/validation-results.json"),
                     27, "validation-results.json")
    labels = set()
    passed = 0
    failures = []
    deadlines = 0
    paused_labels = {"qemu-paused-tcg-firmware", "qemu-paused-no-datadir-override"}
    for receipt in checks:
        label = receipt.get("label")
        require(isinstance(label, str) and label and label not in labels,
                "validation-results.json: duplicate/empty label")
        labels.add(label)
        command_receipt(receipt, label)
        require(type(receipt.get("passed")) is bool, f"{label}: invalid passed flag")
        require(type(receipt.get("raw_exit_code")) is int and receipt["raw_exit_code"] == 0,
                f"{label}: native command raw exit was not zero")
        if label not in paused_labels:
            require(type(receipt.get("expected_exit_code")) is int
                    and receipt["expected_exit_code"] == 0
                    and receipt.get("deadline_reached") is not True,
                    f"{label}: native command exit mismatch")
        else:
            argv = receipt["argv"]
            require(PurePosixPath(argv[0]).name == "qemu-system-x86_64"
                    and argv.count("-S") == 1 and argv.count("-accel") == 1
                    and argv.index("-accel") + 1 < len(argv)
                    and argv[argv.index("-accel") + 1] == "tcg"
                    and receipt.get("deadline_reached") is True
                    and receipt.get("deadline_seconds") == 3
                    and "-kernel" not in argv and "-cdrom" not in argv
                    and "-drive" not in argv and "-hda" not in argv,
                    f"{label}: not the recorded bounded paused TCG initialization")
            expected_datadir_options = 1 if label == "qemu-paused-tcg-firmware" else 0
            require(argv.count("-L") == expected_datadir_options,
                    f"{label}: recorded QEMU resource override differs")
        if receipt.get("deadline_reached") is True:
            deadlines += 1
        if receipt["passed"]:
            passed += 1
            require(receipt.get("resource_lookup_clean") is not False,
                    f"{label}: resource warning incorrectly marked passed")
        else:
            failures.append(receipt)
    require(passed == 26 and len(failures) == 1,
            "validation-results.json: expected 26 passes and one retained resource failure")
    failed = failures[0]
    require(failed["label"] == "qemu-paused-no-datadir-override"
            and failed["raw_exit_code"] == 0
            and failed.get("deadline_reached") is True
            and failed.get("resource_lookup_clean") is False,
            "native resource lookup failure receipt differs")
    messages = failed.get("observed_missing_resource_messages")
    require(isinstance(messages, list) and all(isinstance(message, str) for message in messages)
            and any("Could not open option rom 'kvmvapic.bin'" in message for message in messages),
            "native resource lookup warning not preserved")
    require(deadlines == 2, "expected two bounded paused-QEMU initialization receipts")
    require(paused_labels <= labels, "missing one of the two paused-QEMU receipts")
    return len(rust), passed, len(failures), initial["returncode"]


def verify(root, gpgv):
    root = root.resolve()
    require(root.is_dir(), "archive directory is missing")
    selected = lock_entries(root)
    with tempfile.TemporaryDirectory(prefix="a01-private-toolchain-verify-") as name:
        temporary = Path(name)
        signed = verify_signatures(root, temporary, gpgv)
        indexes = verify_indexes(root, temporary, signed, selected)
    extractions = verify_package_receipts(root, selected)
    rust, passed, failed, initial = verify_execution_receipts(root)
    return {"pass": True, "signatures": len(signed), "indexes": indexes,
            "packages": len(selected), "extractions": extractions,
            "nativechecks": {"passed": passed, "failed": failed},
            "rust": rust, "initialapt": initial}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--gpgv", default="/usr/bin/gpgv", help="trusted local gpgv executable")
    args = parser.parse_args()
    try:
        result = verify(args.archive, args.gpgv)
    except (VerificationError, OSError, UnicodeError, lzma.LZMAError,
            subprocess.SubprocessError, TypeError, ValueError) as error:
        print(json.dumps({"pass": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
