"""Require one current Camera source set and run 59 portable capsule controls.

The inventory digest and every capsule byte are checked before any portable
module is imported. All integrity and count gates use explicit exceptions, so
they also run under python -O. Linux decoder tests are checked as source inputs
but are executed only by the separate Linux CI step. Canonical production
sources and their pinned inventory must match all 29 capsule test inputs.
Historical host receipts confer no qualification on the current source set.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import unittest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
CAPSULE = ROOT / "compat/android/pocket4/camera-video-r4"
CANONICAL = ROOT / "compat/android/pocket4/closeout-20261107/continuation/camera_video_current"
CANONICAL_INVENTORY_NAME = "reviewed-source-inventory.json"
CANONICAL_INVENTORY_BYTES = 5173
CANONICAL_INVENTORY_SHA256 = "28e61371c50638a3ac33d4e28b0466754bc2b81c9f5d015f262d43e60243dd00"
INVENTORY_NAME = "FILES-SHA256.json"
INVENTORY_BYTES = 16863
INVENTORY_SHA256 = "0ea3a43d70b394b14878c3b808bfe1d95d94eac8dfef4ecfcaad187e2cf2b2a7"
EXPECTED_FILES = 94
EXPECTED_TESTS = 59
PORTABLE_MODULES = (
    ("tests/test_host_support_binding.py", "pocket4_camera_r4_host_controls", 10,
     (("CameraHostBinding", 10),)),
    ("tests/test_camera_audio_quiescence.py", "pocket4_camera_r4_quiescence_controls", 31,
     (("RawAdmission", 23), ("RuntimeAdmission", 8))),
    ("tests/test_failure_cleanup.py", "pocket4_camera_r4_failure_quiet_controls", 18,
     (("FailureCleanupControls", 18),)),
)


def need(value, message):
    if not value:
        raise RuntimeError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "DUPLICATE_CAMERA_R4_INVENTORY_KEY:" + key)
        result[key] = value
    return result


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_exact_text(path, expected_bytes, expected_sha256):
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode), "CAMERA_R4_REGULAR_FILE_REQUIRED:" + str(path))
    need(before.st_size == expected_bytes, "CAMERA_R4_FILE_SIZE_CHANGED:" + str(path))
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        need(identity(os.fstat(stream.fileno())) == identity(before),
             "CAMERA_R4_FILE_REPLACED_BEFORE_READ:" + str(path))
        raw = stream.read(expected_bytes + 1)
        need(identity(os.fstat(stream.fileno())) == identity(before),
             "CAMERA_R4_FILE_CHANGED_DURING_READ:" + str(path))
    need(identity(path.lstat()) == identity(before),
         "CAMERA_R4_FILE_REPLACED_AFTER_READ:" + str(path))
    need(len(raw) == expected_bytes and hashlib.sha256(raw).hexdigest() == expected_sha256,
         "CAMERA_R4_FILE_DIGEST_CHANGED:" + str(path))
    text = raw.decode("utf-8", "strict")
    need("\x00" not in text, "CAMERA_R4_TEXT_CONTAINS_NUL:" + str(path))
    return text


def verify_canonical_sources(capsule_inventory, canonical=CANONICAL):
    """Keep the capsule's test inputs identical to the sole current source set."""
    canonical = Path(canonical)
    need(canonical.is_absolute() and canonical.resolve(strict=True) == canonical
         and stat.S_ISDIR(canonical.lstat().st_mode),
         "CAMERA_CANONICAL_EXACT_DIRECTORY_REQUIRED")
    inventory_text = read_exact_text(canonical / CANONICAL_INVENTORY_NAME,
                                     CANONICAL_INVENTORY_BYTES,
                                     CANONICAL_INVENTORY_SHA256)
    inventory = json.loads(inventory_text, object_pairs_hook=unique_object)
    need(type(inventory) is dict
         and inventory.get("schema") == "pocket4-reviewed-camera-video-source-inventory-v1"
         and type(inventory.get("source_count")) is int
         and inventory["source_count"] == 29
         and type(inventory.get("files")) is list and len(inventory["files"]) == 29
         and inventory.get("Android_execution_authorized_by_publication") is False
         and inventory.get("whole_app_business_accepted") is False,
         "CAMERA_CANONICAL_EXACT_SOURCE_INVENTORY_REQUIRED")
    capsule_sources = {}
    for row in capsule_inventory["files"]:
        relative = PurePosixPath(row["path"])
        if relative.parts[0] != "source":
            continue
        need(len(relative.parts) == 2 and relative.suffix == ".py"
             and relative.name not in capsule_sources,
             "CAMERA_CAPSULE_EXACT_PRODUCTION_SOURCE_NAME_REQUIRED")
        capsule_sources[relative.name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    need(len(capsule_sources) == 29, "CAMERA_CAPSULE_EXACT_29_PRODUCTION_SOURCES_REQUIRED")
    canonical_sources = {}
    for row in inventory["files"]:
        need(type(row) is dict and set(row) == {"name", "bytes", "sha256"},
             "CAMERA_CANONICAL_EXACT_SOURCE_ROW_REQUIRED")
        name = row["name"]
        need(type(name) is str and name and "\\" not in name
             and PurePosixPath(name).parts == (name,) and name.endswith(".py")
             and name not in canonical_sources
             and type(row["bytes"]) is int and row["bytes"] > 0
             and type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
             "CAMERA_CANONICAL_EXACT_SOURCE_NAME_AND_PIN_REQUIRED")
        canonical_sources[name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    need(canonical_sources == capsule_sources,
         "CAMERA_CANONICAL_AND_CAPSULE_PRODUCTION_PINS_MUST_MATCH")
    for field, name in (("common_sha256", "app_common.py"),
                        ("decoder_sha256", "camera_decode.py"),
                        ("state_sha256", "camera_video_state.py")):
        need(inventory.get(field) == capsule_sources[name]["sha256"],
             "CAMERA_CANONICAL_SUMMARY_PIN_MUST_MATCH:" + field)
    source = canonical / "source"
    need(source.resolve(strict=True) == source and stat.S_ISDIR(source.lstat().st_mode),
         "CAMERA_CANONICAL_EXACT_SOURCE_DIRECTORY_REQUIRED")
    observed = set()
    for path in source.iterdir():
        need(stat.S_ISREG(path.lstat().st_mode),
             "CAMERA_CANONICAL_NONREGULAR_SOURCE_REFUSED:" + path.name)
        observed.add(path.name)
    need(observed == set(capsule_sources), "CAMERA_CANONICAL_EXACT_SOURCE_FILE_SET_REQUIRED")
    for name, ref in sorted(capsule_sources.items()):
        read_exact_text(source / name, ref["bytes"], ref["sha256"])
    return {"source_count": 29, "canonical_inventory_sha256": CANONICAL_INVENTORY_SHA256,
            "capsule_source_bytes_identical": True, "runtime_qualified": False,
            "historical_host_qualification_transferred": False}


def verify_capsule(capsule=CAPSULE, canonical=CANONICAL):
    capsule = Path(capsule)
    need(capsule.is_absolute() and capsule.resolve() == capsule
         and stat.S_ISDIR(capsule.lstat().st_mode),
         "CAMERA_R4_EXACT_CAPSULE_DIRECTORY_REQUIRED")
    inventory_text = read_exact_text(capsule / INVENTORY_NAME, INVENTORY_BYTES, INVENTORY_SHA256)
    inventory = json.loads(inventory_text, object_pairs_hook=unique_object)
    need(type(inventory) is dict
         and inventory.get("schema") == "camera-r4-integrated-review-inventory-v2"
         and type(inventory.get("files")) is list,
         "CAMERA_R4_EXACT_INVENTORY_SCHEMA_REQUIRED")
    need(type(inventory.get("file_count_including_inventory")) is int
         and inventory["file_count_including_inventory"] == EXPECTED_FILES
         and len(inventory["files"]) + 1 == EXPECTED_FILES,
         "CAMERA_R4_EXACT_INVENTORY_COUNT_REQUIRED")
    expected = {INVENTORY_NAME}
    directories = set()
    for row in inventory["files"]:
        need(type(row) is dict and set(row) == {"path", "bytes", "sha256"},
             "CAMERA_R4_EXACT_INVENTORY_ROW_REQUIRED")
        relative = row["path"]
        need(type(relative) is str and relative and "\\" not in relative,
             "CAMERA_R4_CANONICAL_RELATIVE_PATH_REQUIRED")
        parsed = PurePosixPath(relative)
        need(not parsed.is_absolute() and ".." not in parsed.parts and str(parsed) == relative
             and relative not in expected,
             "CAMERA_R4_UNIQUE_RELATIVE_PATH_REQUIRED:" + relative)
        need(type(row["bytes"]) is int and row["bytes"] >= 0
             and type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
             "CAMERA_R4_EXACT_LENGTH_AND_DIGEST_REQUIRED:" + relative)
        expected.add(relative)
        directories.update(str(parent) for parent in parsed.parents if str(parent) != ".")
    observed_files = set()
    observed_directories = set()
    for current, dirs, files in os.walk(capsule, followlinks=False):
        for name in dirs:
            path = Path(current) / name
            need(stat.S_ISDIR(path.lstat().st_mode), "CAMERA_R4_LINKED_DIRECTORY_REFUSED:" + str(path))
            observed_directories.add(path.relative_to(capsule).as_posix())
        for name in files:
            path = Path(current) / name
            need(stat.S_ISREG(path.lstat().st_mode), "CAMERA_R4_NONREGULAR_FILE_REFUSED:" + str(path))
            observed_files.add(path.relative_to(capsule).as_posix())
    need(observed_files == expected and observed_directories == directories,
         "CAMERA_R4_EXACT_FILE_SET_REQUIRED")
    for row in inventory["files"]:
        read_exact_text(capsule / row["path"], row["bytes"], row["sha256"])
    current_sources = verify_canonical_sources(inventory, canonical)
    return {"files_verified": len(expected), "inventory_sha256": INVENTORY_SHA256,
            "canonical_source_check": current_sources,
            "portable_tests": EXPECTED_TESTS, "runtime_qualified": False}


def load_tests(loader, _standard_tests, _pattern):
    verify_capsule()
    combined = unittest.TestSuite()
    for relative, module_name, expected_count, classes in PORTABLE_MODULES:
        path = CAPSULE / relative
        spec = importlib.util.spec_from_file_location(module_name, path)
        need(spec is not None and spec.loader is not None,
             "CAMERA_R4_PORTABLE_MODULE_UNAVAILABLE:" + relative)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        suite = loader.loadTestsFromModule(module)
        need(suite.countTestCases() == expected_count,
             "CAMERA_R4_EXACT_PORTABLE_MODULE_TEST_COUNT_REQUIRED:" + relative)
        for class_name, class_count in classes:
            test_class = getattr(module, class_name, None)
            need(isinstance(test_class, type) and issubclass(test_class, unittest.TestCase)
                 and test_class.__module__ == module_name,
                 "CAMERA_R4_PORTABLE_TEST_CLASS_REQUIRED:" + class_name)
            need(loader.loadTestsFromTestCase(test_class).countTestCases() == class_count,
                 "CAMERA_R4_EXACT_PORTABLE_CLASS_TEST_COUNT_REQUIRED:" + class_name)
        combined.addTests(suite)
    need(combined.countTestCases() == EXPECTED_TESTS,
         "CAMERA_R4_EXACT_TOTAL_PORTABLE_TEST_COUNT_REQUIRED")
    return combined


if __name__ == "__main__":
    unittest.main(verbosity=2)
