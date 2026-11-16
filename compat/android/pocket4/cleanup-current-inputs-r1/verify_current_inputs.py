#!/usr/bin/env python3
"""Read-only verifier for the actual Pocket4 13-preparation / 721-file selector.

Reads the current continuation, its selected-preparation record and its retained
manifest with their real on-host schemas. Never imports selected Python, runs a
build, touches Android, changes CURRENT, reads signing material, or deletes.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import PurePosixPath

SHA = re.compile(r"[0-9a-f]{64}\Z")
SECRET = re.compile(r"(?:\.p12|\.pfx|\.jks|\.keystore|\.key|\.pem)$|(?:^|[-_.])(?:password|private[-_]key)(?:$|[-_.])", re.I)

class Refused(Exception):
    pass

def no_duplicate(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise Refused("DUPLICATE_JSON_KEY:" + k)
        d[k] = v
    return d

def decode(raw):
    return json.loads(raw, object_pairs_hook=no_duplicate,
                      parse_constant=lambda x: (_ for _ in ()).throw(Refused("NONFINITE_JSON")))

def safe_path(path):
    if (not isinstance(path, str) or not path.startswith("/") or path.startswith("//")
            or str(PurePosixPath(path)) != path or ".." in path.split("/")
            or any(c in path for c in ("\0", "\r", "\n"))):
        raise Refused("ABSOLUTE_CANONICAL_PATH_REQUIRED")
    return path

def private_path(path):
    return any(x.lower() in ("private-signing", "private_signing") or SECRET.search(x)
               for x in PurePosixPath(path).parts)

def snap(st):
    return {k: getattr(st, k) for k in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid", "st_size", "st_mtime_ns", "st_ctime_ns")}

def open_exact(path):
    safe_path(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = PurePosixPath(path).parts[1:]
        for i, component in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if i < len(parts) - 1:
                flags |= os.O_DIRECTORY
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        result, fd = fd, -1
        return result
    finally:
        if fd >= 0:
            os.close(fd)

def read_bound(binding, maximum=64 * 1024**2, json_body=False):
    if set(binding) != {"path", "bytes", "sha256"}:
        raise Refused("EXACT_THREE_FIELD_BINDING_REQUIRED")
    path = safe_path(binding["path"])
    if type(binding["bytes"]) is not int or binding["bytes"] < 0 or binding["bytes"] > maximum:
        raise Refused("FILE_SIZE_LIMIT_OR_INVALID_SIZE")
    if not isinstance(binding["sha256"], str) or not SHA.fullmatch(binding["sha256"]):
        raise Refused("INVALID_SHA256")
    if private_path(path):
        raise Refused("SIGNING_OR_SECRET_BODY_REFUSED:" + path)
    fd = open_exact(path)
    try:
        before = snap(os.fstat(fd))
        if not stat.S_ISREG(before["st_mode"]) or before["st_nlink"] != 1:
            raise Refused("REGULAR_SINGLE_LINK_FILE_REQUIRED:" + path)
        if before["st_size"] != binding["bytes"]:
            raise Refused("SIZE_MISMATCH:" + path)
        h = hashlib.sha256(); count = 0; body = []
        while True:
            b = os.read(fd, 1024 * 1024)
            if not b:
                break
            count += len(b)
            if count > maximum:
                raise Refused("READ_LIMIT:" + path)
            h.update(b)
            if json_body:
                body.append(b)
        if count != binding["bytes"] or h.hexdigest() != binding["sha256"]:
            raise Refused("HASH_MISMATCH:" + path)
        if snap(os.fstat(fd)) != before:
            raise Refused("FILE_CHANGED_WHILE_READING:" + path)
        other = open_exact(path)
        try:
            if snap(os.fstat(other)) != before:
                raise Refused("NAMED_PATH_REPLACED:" + path)
        finally:
            os.close(other)
        return (decode(b"".join(body)) if json_body else None), before
    finally:
        os.close(fd)

def read_current(path):
    safe_path(path)
    if private_path(path):
        raise Refused("PRIVATE_CURRENT_PATH_REFUSED")
    fd = open_exact(path)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > 2 * 1024**2:
            raise Refused("CURRENT_NOT_BOUNDED_SINGLE_FILE")
        raw = b""
        while True:
            b = os.read(fd, 65536)
            if not b:
                break
            raw += b
            if len(raw) > 2 * 1024**2:
                raise Refused("CURRENT_BYTE_LIMIT")
        if len(raw) != st.st_size or snap(os.fstat(fd)) != snap(st):
            raise Refused("CURRENT_CHANGED_WHILE_READING")
    finally:
        os.close(fd)
    binding = dict(path=path, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    doc, identity = read_bound(binding, maximum=2 * 1024**2, json_body=True)
    return doc, binding, identity

def manifest_records(doc, expected=721):
    if not isinstance(doc, dict) or doc.get("schema") != "gallery-qpr1-current-source-final-retained-files-v1":
        raise Refused("UNSUPPORTED_ACTUAL_RETAINED_MANIFEST_SCHEMA")
    records = doc.get("files")
    if not isinstance(records, list) or len(records) != expected:
        raise Refused("EXPECTED_721_RECORDS_REQUIRED")
    seen = set()
    for r in records:
        if not isinstance(r, dict) or set(r) != {"path", "bytes", "sha256"}:
            raise Refused("MALFORMED_RETAINED_RECORD")
        p = safe_path(r["path"])
        if p in seen:
            raise Refused("DUPLICATE_RETAINED_PATH")
        seen.add(p)
    return records

def verify(current_path, max_total_bytes=1024**3):
    current, current_binding, current_identity = read_current(current_path)
    if current.get("schema") != "pocket4-linux-android-current-continuation-v1":
        raise Refused("UNSUPPORTED_CURRENT_SCHEMA")
    selected_binding = current["application_qualification_preparations"]
    selected, selected_identity = read_bound(selected_binding, json_body=True)
    if selected.get("schema") != "current-application-preparation-selection-v1":
        raise Refused("UNSUPPORTED_SELECTOR_SCHEMA")
    preparations = selected.get("selected_preparations")
    if not isinstance(preparations, list) or len(preparations) != 13:
        raise Refused("EXACT_13_SELECTED_PREPARATIONS_REQUIRED")
    if len({r.get("path") for r in preparations if isinstance(r, dict)}) != 13:
        raise Refused("DUPLICATE_OR_MALFORMED_SELECTED_PREPARATIONS")
    manifest_binding = selected["retained_manifest"]
    gallery_binding = current["application_current_QPR1_leaf_migration"]["gallery"]["retained_manifest"]
    if gallery_binding != manifest_binding:
        raise Refused("CURRENT_SELECTOR_MANIFEST_CONFLICT")
    manifest, manifest_identity = read_bound(manifest_binding, json_body=True)
    records = manifest_records(manifest)
    total = sum(r["bytes"] for r in records if type(r.get("bytes")) is int)
    if total > max_total_bytes:
        raise Refused("TOTAL_BYTE_LIMIT")
    rows = []; errors = []; identities = {}
    combined = {r["path"]: r for r in records}
    for r in preparations:
        if not isinstance(r, dict) or set(r) != {"path", "bytes", "sha256"}:
            raise Refused("MALFORMED_PREPARATION_BINDING")
        if r["path"] in combined and combined[r["path"]] != r:
            raise Refused("PREPARATION_RETAINED_IDENTITY_CONFLICT")
        combined[r["path"]] = r
    total_union = sum(r["bytes"] for r in combined.values() if type(r.get("bytes")) is int)
    if total_union > max_total_bytes:
        raise Refused("TOTAL_UNION_BYTE_LIMIT")
    for path in sorted(combined):
        r = combined[path]
        try:
            _, identity = read_bound(r)
            identities[path] = identity
            rows.append(dict(**r, identity=identity, verified=True))
        except (Refused, OSError, ValueError) as e:
            errors.append(dict(path=path, error=str(e)))
    for binding, expected in ((current_binding, current_identity), (selected_binding, selected_identity), (manifest_binding, manifest_identity)):
        try:
            _, after = read_bound(binding)
            if after != expected:
                raise Refused("CONTROL_IDENTITY_CHANGED")
        except (Refused, OSError, ValueError) as e:
            errors.append(dict(path=binding["path"], error=str(e)))
    for path, before in identities.items():
        try:
            fd = open_exact(path)
            try:
                if snap(os.fstat(fd)) != before:
                    raise Refused("RETAINED_FILE_CHANGED_DURING_VERIFICATION")
            finally:
                os.close(fd)
        except (Refused, OSError) as e:
            errors.append(dict(path=path, error=str(e)))
    result = dict(schema="pocket4-current-721-independent-readback-v1",
                  observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  current=current_binding, selection=selected_binding, retained_manifest=manifest_binding,
                  foreground_owner=current.get("foreground_owner"),
                  retained_count=len(records), selected_preparation_count=len(preparations),
                  independently_verified_union=len(identities), total_bytes=total_union,
                  all_current_721_verified=not errors, errors=errors,
                  identities_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  Android_actions=0, Main_actions=0, CURRENT_writes=0, private_body_reads=0,
                  source_files_executed=0, deletion_performed=False, deletion_authorized=False,
                  complete_current_dependency_census=False,
                  scope="13 actual selected preparations and the exact 721 retained records; additional current Camera, kernel, service, account and runtime dependencies are outside this readback")
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--current", default="/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json")
    p.add_argument("--max-total-bytes", type=int, default=1024**3)
    a = p.parse_args()
    try:
        result = verify(a.current, a.max_total_bytes)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["all_current_721_verified"] else 2
    except (Refused, OSError, ValueError, TypeError, KeyError) as e:
        print(json.dumps(dict(schema="pocket4-current-721-independent-readback-v1", all_current_721_verified=False,
                              status="UNKNOWN", error=str(e), deletion_authorized=False, deletion_performed=False)))
        return 2

if __name__ == "__main__":
    sys.exit(main())
