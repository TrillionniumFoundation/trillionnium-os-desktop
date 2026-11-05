#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild the reviewed manager into exact supplied baseline inputs; emit an unsigned APK.

This adapts the release07 builder to the reviewed release08 source. It does not reconstruct
the baseline Camera2 build or perform signing or installation. See the input lock.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def artifact(path):
    return {"name": path.name, "sha256": sha(path), "bytes": path.stat().st_size}


def metadata_signature(name):
 return name.upper()=='META-INF/MANIFEST.MF' or re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC)',name,re.I) is not None
def dex_names(data):
 assert data[:4]==b'dex\n' and data[7]==0
 assert struct.unpack_from('<I',data,32)[0]==len(data)
 assert hashlib.sha1(data[32:]).digest()==data[12:32]
 assert (zlib.adler32(data[12:])&0xffffffff)==struct.unpack_from('<I',data,8)[0]
 nstr,stroff=struct.unpack_from('<II',data,56);ntypes,typeoff=struct.unpack_from('<II',data,64)
 nmethods,methodoff=struct.unpack_from('<II',data,88);nclass,classoff=struct.unpack_from('<II',data,96)
 def string(i):
  off=struct.unpack_from('<I',data,stroff+4*i)[0]
  while data[off]&128:off+=1
  off+=1;end=data.index(0,off)
  return data[off:end].decode('utf-8',errors='replace')
 strings=[string(i) for i in range(nstr)]
 types=[strings[struct.unpack_from('<I',data,typeoff+4*i)[0]]for i in range(ntypes)]
 classes=[types[struct.unpack_from('<I',data,classoff+32*i)[0]]for i in range(nclass)]
 assert len(set(classes))==len(classes)
 methods=[]
 for i in range(nmethods):
  cls,proto,name=struct.unpack_from('<HHI',data,methodoff+8*i)
  if 'LambdaMetafactory' in types[cls]:methods.append((types[cls],strings[name]))
 assert not methods
 return {'magic':data[:8].decode('ascii','replace'),'classes':classes,'class_count':nclass,'method_count':nmethods,'checksums_verified':True}
def zwrite(z,name,data,stored=False):
 zi=zipfile.ZipInfo(name,(2009,1,1,0,0,0));zi.compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
 zi.external_attr=0o100644<<16;z.writestr(zi,data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs-json", required=True, type=Path,
                        help="Local JSON object mapping every input-lock key to its file path.")
    parser.add_argument("--out", type=Path,
                        help="New output directory; existing directories are rejected.")
    parser.add_argument("--verify-inputs-only", action="store_true")
    args = parser.parse_args()
    lock = json.loads((ROOT / "dependencies.lock.json").read_text())
    supplied = json.loads(args.inputs_json.read_text())
    paths = {}
    for key, entry in lock["inputs"].items():
        require(key in supplied, "Missing external input: " + key)
        path = Path(supplied[key]).resolve()
        require(path.is_file(), "External input is not a file: " + key)
        require(path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"],
                "External input hash/size mismatch: " + key)
        paths[key] = path
    source = ROOT / "source/packages/apps/Camera2/src/com/android/camera/one/v2/Camera2OneCameraManagerImpl.java"
    require(sha(source) == lock["expected"]["source_sha256"], "Reviewed source hash mismatch")
    if args.verify_inputs_only:
        print(json.dumps({"success": True, "inputs_verified": len(paths),
                          "source_sha256": sha(source),
                          "clean_full_apk_reproduction_verified": False}, indent=2))
        return 0
    require(args.out is not None, "--out is required for a build")
    out = args.out.resolve()
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name in ("logs", "classes", "dex", "empty-sourcepath"):
        (out / name).mkdir()
    variables = {key: str(path) for key, path in paths.items()}
    variables.update(source=str(source), classes=str(out / "classes"),
                     dex=str(out / "dex"), empty_sourcepath=str(out / "empty-sourcepath"),
                     program=str(out / "program.jar"), unsigned=str(out / "Camera2-unsigned.apk"),
                     aligned=str(out / "Camera2-aligned-unsigned.apk"))
    result = {
        "schema": "pocket4-camera-portable-unsigned-rebuild-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "production_ready": False,
        "signed": False,
        "installed": False,
        "clean_full_apk_reproduction_verified": False,
        "verified_external_inputs": len(paths),
        "source_sha256": sha(source),
        "commands": [],
    }

    def save():
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def run(label, timeout):
        argv = [argument.format_map(variables) for argument in lock["commands"][label]]
        started = time.monotonic()
        with (out / "logs" / (label + ".stdout")).open("wb") as stdout, (
                out / "logs" / (label + ".stderr")).open("wb") as stderr:
            process = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=timeout)
        result["commands"].append({"label": label, "exit_code": process.returncode,
                                   "elapsed_seconds": time.monotonic() - started})
        save()
        require(process.returncode == 0, label + " failed; inspect local build logs")

    save()
    try:
        run("javac", 90)
        overlay = {str(path.relative_to(out / "classes")): path.read_bytes()
                   for path in (out / "classes").rglob("*.class")}
        expected = lock["expected"]["class_entry"]
        require(set(overlay) == {expected}, "Compile produced an unexpected class set")
        require(hashlib.sha256(overlay[expected]).hexdigest()
                == lock["expected"]["class_after_sha256"],
                "Compiled manager differs from the pinned release08 class")
        program = out / "program.jar"
        with zipfile.ZipFile(paths["original_program"]) as baseline, zipfile.ZipFile(
                program, "w", compression=zipfile.ZIP_DEFLATED) as revised:
            names = baseline.namelist()
            require(len(names) == len(set(names)) and expected in names,
                    "Invalid baseline program inventory")
            require(hashlib.sha256(baseline.read(expected)).hexdigest()
                    == lock["expected"]["class_before_sha256"],
                    "Baseline manager class precondition mismatch")
            for name in names:
                zwrite(revised, name, overlay[name] if name in overlay else baseline.read(name))
        require(sha(program) == lock["expected"]["program_sha256"],
                "Rebuilt program JAR differs from pinned release08")
        with zipfile.ZipFile(paths["original_program"]) as baseline, zipfile.ZipFile(program) as revised:
            require(baseline.namelist() == revised.namelist(), "Program entry set changed")
            require([name for name in baseline.namelist()
                     if baseline.read(name) != revised.read(name)] == [expected],
                    "A class outside the reviewed manager changed")

        run("d8", 240)
        dex_files = sorted((out / "dex").glob("classes*.dex"))
        require(bool(dex_files), "D8 did not produce dex files")
        inventory = {path.name: dex_names(path.read_bytes()) for path in dex_files}
        new_classes = [name for row in inventory.values() for name in row["classes"]]
        require(len(set(new_classes)) == len(new_classes), "Duplicate dex class descriptors")
        with zipfile.ZipFile(paths["parent_apk"]) as baseline:
            previous = [dex_names(baseline.read(name)) for name in baseline.namelist()
                        if re.fullmatch(r"classes\d*\.dex", name)]
        old_classes = [name for row in previous for name in row["classes"]]
        require(set(new_classes) == set(old_classes)
                and len(new_classes) == lock["expected"]["dex_class_count"],
                "Dex class inventory differs from baseline")
        require("Landroid/hardware/camera2/CameraManager;" not in new_classes
                and "LHotplugRegression;" not in new_classes,
                "Host test bindings leaked into the Android artifact")

        unsigned = out / "Camera2-unsigned.apk"
        with zipfile.ZipFile(paths["parent_apk"]) as baseline, zipfile.ZipFile(
                unsigned, "w", compression=zipfile.ZIP_DEFLATED) as revised:
            for entry in baseline.infolist():
                name = entry.filename
                if metadata_signature(name) or re.fullmatch(r"classes\d*\.dex", name):
                    continue
                zwrite(revised, name, baseline.read(name),
                       stored=entry.compress_type == zipfile.ZIP_STORED or name == "resources.arsc")
            for path in dex_files:
                zwrite(revised, path.name, path.read_bytes())
        run("zipalign", 45)
        run("alignment_verify", 45)
        aligned = out / "Camera2-aligned-unsigned.apk"
        keep = lambda name: not metadata_signature(name) and re.fullmatch(r"classes\d*\.dex", name) is None
        with zipfile.ZipFile(paths["parent_apk"]) as baseline, zipfile.ZipFile(aligned) as revised:
            require(revised.testzip() is None, "APK ZIP checksum failure")
            require(len(revised.namelist()) == len(set(revised.namelist())), "Duplicate APK entries")
            before = {name for name in baseline.namelist() if keep(name)}
            after = {name for name in revised.namelist() if keep(name)}
            require(before == after, "Non-dex APK entry set changed")
            for name in sorted(before):
                require(baseline.read(name) == revised.read(name), "Unexpected payload change: " + name)
            for path in dex_files:
                require(revised.read(path.name) == path.read_bytes(), "Dex payload mismatch")
            require({name for name in revised.namelist() if re.fullmatch(r"classes\d*\.dex", name)}
                    == set(inventory), "Unexpected dex APK entries")
            require(len(before) == lock["expected"]["non_dex_entry_count"],
                    "Non-dex entry count differs from pinned release08")
        result.update(
            success=True, unsigned_apk=artifact(aligned), program=artifact(program),
            class_sha256=hashlib.sha256(overlay[expected]).hexdigest(),
            validation={
                "real_android_sdk_compile": True,
                "recorded_manager_class_reproduced": True,
                "recorded_program_jar_reproduced": True,
                "one_reviewed_class_changed": True,
                "dex_class_set_equal": True,
                "class_count": len(new_classes),
                "test_bindings_absent": True,
                "non_dex_payload_byte_equal": True,
                "preserved_non_dex_entries": len(before),
                "alignment_16k_verified": True,
                "runtime_execution": False,
            })
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error))
    finally:
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
