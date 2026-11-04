#!/usr/bin/env python3
"""Write a create-only build request after a real preparation SHA is observed."""
import argparse
import hashlib
import json
from pathlib import Path

CONTROLLER_SHA = "ba4dffc59b224b32e6f42f7f66222d35cdd62eecb82dabea67d05dc888635d6d"
PREPARE_REQUEST_SHA = "3f9e163d78fa7f4559a012341d4e5dde84f1dda5f6eb0c77916c93afd95f11d9"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preparation-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sha = args.preparation_sha256
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        parser.error("provide the exact SHA from the successful remote preparation, in lowercase hex")
    here = Path(__file__).resolve().parent
    source = (here / "combined_build.py").read_bytes()
    raw = (here / "exact-preparation-request.json").read_bytes()
    if hashlib.sha256(source).hexdigest() != CONTROLLER_SHA or hashlib.sha256(raw).hexdigest() != PREPARE_REQUEST_SHA:
        raise RuntimeError("frozen controller/request changed")
    request = json.loads(raw)
    if request["stdin"].encode() != source or request["args"][-1] != "--prepare":
        raise RuntimeError("unexpected preparation request shape")
    request["args"] = request["args"][:-1] + ["--build", "--preparation-sha256", sha]
    request["idempotency_key"] = "pocket4-native-combined04-full-engine-flag0-build-01-20261104"
    request["timeout_seconds"] = 6400
    request["cpu_quota_percent"] = 200
    request["memory_max_bytes"] = 11811160064
    body = (json.dumps(request, ensure_ascii=False, indent=2) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(body)
    print(json.dumps({"request": str(args.output), "bytes": len(body),
                      "sha256": hashlib.sha256(body).hexdigest(),
                      "preparation_sha256": sha, "submitted": False}))


if __name__ == "__main__":
    main()
