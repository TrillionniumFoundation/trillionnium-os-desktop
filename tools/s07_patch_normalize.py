#!/usr/bin/env python3
"""Normalize patch-file trailing whitespace and rebind every declared digest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest_path = root / "manifests/lab-d3-servo-retained-node-action.v1.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

for section_name in ("patch", "hardening"):
    section = manifest[section_name]
    aggregate = bytearray()
    for record in section["parts"]:
        path = root / record["path"]
        text = path.read_text(encoding="utf-8")
        normalized = "\n".join(line.rstrip(" \t") for line in text.splitlines()) + "\n"
        data = normalized.encode("utf-8")
        path.write_bytes(data)
        record["sha256"] = hashlib.sha256(data).hexdigest()
        aggregate.extend(data)
    section["sha256"] = hashlib.sha256(bytes(aggregate)).hexdigest()

manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
