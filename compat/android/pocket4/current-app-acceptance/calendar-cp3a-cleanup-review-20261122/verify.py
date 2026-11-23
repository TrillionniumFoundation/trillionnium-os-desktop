#!/usr/bin/env python3
"""Replay the bounded CalendarProvider cleanup review against both original APKs."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
POCKET4 = HERE.parent.parent
LINE = re.compile(rb"(?m)^    \.line [0-9]+\n")
METHOD = re.compile(rb"(?ms)^\.method ([^\n]+)\n.*?^\.end method\n")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_record(pin):
    path = POCKET4 / pin["path"]
    data = path.read_bytes()
    check(sha(data) == pin["sha256"], f"source record changed: {path.name}")
    return json.loads(data)


def read_apk(path, pin):
    with path.open("rb") as stream:
        data = stream.read(pin["apk_bytes"] + 1)
    check(len(data) == pin["apk_bytes"] and sha(data) == pin["apk_sha256"],
          f"APK size or digest mismatch: {path}")
    return data


def read_dex(data, pin):
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        check(package.namelist().count("classes.dex") == 1, "ambiguous classes.dex")
        dex = package.read("classes.dex")
    check(sha(dex) == pin["dex_sha256"], "DEX mismatch")
    return dex


def selected_methods(dex, tool, methods, package="com/android/providers/calendar"):
    with tempfile.TemporaryDirectory(prefix="calendar-smali-") as directory:
        root = Path(directory)
        dex_path = root / "classes.dex"
        dex_path.write_bytes(dex)
        output = root / "smali"
        subprocess.run([tool, "disassemble", "--jobs", "1", "-o", str(output), str(dex_path)],
                       check=True, timeout=60)
        classes = output / package
        selected = {}
        for row in methods:
            klass, signature = row["class"], row["signature"]
            key = klass, signature
            check(key not in selected, f"duplicate method definition: {key}")
            body = (classes / (klass + ".smali")).read_bytes()
            matches = [m.group() for m in METHOD.finditer(body)
                       if m.group(1).rsplit(b" ", 1)[-1] == signature.encode("ascii")]
            check(len(matches) == 1, f"missing or ambiguous method: {key}")
            selected[key] = matches[0]
        return selected


def check_routes(body, additions):
    # The two reviewed initializers use literal register assignments here.
    # Compare complete, pinned disassembly first; these checks expose the
    # actual collection/item registrations and the two additional root paths.
    insns = [line.strip() for line in LINE.sub(b"", body).decode("ascii").splitlines()
             if line.strip()]
    add = "invoke-virtual {v11, v5, v4, v15}, Landroid/content/UriMatcher;->addURI(Ljava/lang/String;Ljava/lang/String;I)V"
    anchor = 'const-string v5, "com.android.calendar"'
    check(insns.count(anchor) == 1, "URI authority changed")
    for pattern, number in (("calendars", 4), ("calendars/#", 5)):
        matches = [i for i, s in enumerate(insns) if s == f'const-string v4, "{pattern}"']
        check(len(matches) == 1 and matches[0] > insns.index(anchor),
              f"missing or ambiguous route: {pattern}")
        start = matches[0]
        check(insns[start + 1:start + 3] == [f"const/4 v15, 0x{number:x}", add],
              f"URI route changed: {pattern}")
    first = insns.index(anchor)
    literal_null_and_id = ["const/4 v15, 0x0", "move-object/from16 v16, v4",
                           "const/16 v4, 0x29", "move-object/from16 v17, v5"]
    root_registration = ["invoke-virtual {v11, v5, v15, v4}, Landroid/content/UriMatcher;->addURI(Ljava/lang/String;Ljava/lang/String;I)V",
                         'const-string v4, "#"', "const/16 v15, 0x2a", add]
    check((insns[first-4:first] == literal_null_and_id) is additions, "root 41 registration changed")
    check((insns[first+1:first+5] == root_registration) is additions, "root 42 registration changed")


def verify_client(path, tool, pin):
    data = read_apk(path, pin)
    dex = read_dex(data, pin)
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        members = package.namelist()
        check(len(members) == len(set(members)) == pin["zip_members"],
              "client archive members differ")
        check([name for name in members if name.endswith(".dex")] == ["classes.dex"],
              "unexpected client DEX")
        check(sha(package.read("resources.arsc")) == pin["resources_sha256"],
              "client resource table changed")
        for name in members:
            member = package.read(name).lower()
            for token in pin["legacy_literals"]:
                for encoding in ("utf-8", "utf-16-le"):
                    check(token.lower().encode(encoding) not in member,
                          f"legacy literal {token!r} found in {name}")

    key = pin["class"], pin["signature"]
    method = selected_methods(dex, tool, [pin], "com/android/calendar")[key]
    check(sha(method) == pin["method_sha256"], "client account callback changed")
    return {"current_client_verified": True, "zip_members": len(members),
            "legacy_literals_present": False, "empty_query_account_type": "com.google"}


def verify(previous_apk, current_apk, tool, calendar_apk=None):
    review = json.loads((HERE / "review.json").read_bytes())
    previous = load_record(review["previous_review"])
    receipt = load_record(review["current_provider_receipt"])
    inputs = review["inputs"]
    check(inputs["previous"]["apk_sha256"] == previous["provider_apk_sha256"]
          and inputs["previous"]["dex_sha256"] == previous["provider_dex_sha256"],
          "previous artifact binding changed")
    check(inputs["current"]["apk_sha256"] == receipt["apk"]["sha256"]
          and inputs["current"]["apk_bytes"] == receipt["apk"]["bytes"]
          and review["system_image_member"] == receipt["original_image_path"]
          and review["system_image_sha256"] == receipt["full_system_image"]["sha256"],
          "current image receipt changed")
    methods = review["methods"]
    old = selected_methods(read_dex(read_apk(previous_apk, inputs["previous"]), inputs["previous"]), tool, methods)
    new = selected_methods(read_dex(read_apk(current_apk, inputs["current"]), inputs["current"]), tool, methods)
    previous_review_members = {}
    matched = 0
    for row in methods:
        key = row["class"], row["signature"]
        left, right = old[key], new[key]
        check(sha(left) == row["previous_sha256"] and sha(right) == row["current_sha256"],
              f"disassembly mismatch: {key}")
        if "previous_review_member" in row:
            previous_review_members[row["previous_review_member"]] = sha(left)
        if key == ("CalendarProvider2", "<clinit>()V"):
            check_routes(left, False)
            check_routes(right, True)
            check(row["line_independent_sha256"] is None, "changed initializer counted as identical")
            continue
        canonical = LINE.sub(b"", left)
        check(canonical == LINE.sub(b"", right)
              and sha(canonical) == row["line_independent_sha256"],
              f"method changed beyond source line numbers: {key}")
        matched += 1
    check(previous_review_members == previous["extracted_methods"],
          "incomplete original seven-method review")
    expected = review["observed"]
    check(matched == expected["methods_equal_excluding_line_numbers"] == 15
          and len(methods) == matched + 1 and len(previous_review_members) == 7, "review scope changed")
    result = {"previous_methods_reproduced": len(previous_review_members), "matching_methods": matched,
            "calendar_uri_ids": [4, 5], "current_extra_root_ids": [41, 42],
            "provider_writes": 0, "runtime_cleanup_qualified": False}
    if calendar_apk is not None:
        result.update(verify_client(calendar_apk, tool, review["calendar_client"]))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-apk", type=Path, required=True)
    parser.add_argument("--current-apk", type=Path, required=True)
    parser.add_argument("--baksmali", default="baksmali")
    parser.add_argument("--current-calendar", type=Path, help="also verify the CP3A Calendar client")
    args = parser.parse_args()
    print(json.dumps(verify(args.previous_apk, args.current_apk, args.baksmali, args.current_calendar), sort_keys=True))
