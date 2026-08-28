"""Command-line interface for deterministic reference evidence."""
from __future__ import annotations

import argparse, json
from pathlib import Path
from .evidence import build_result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("contracts/browser-codec.v1.json"))
    parser.add_argument("--write-result", type=Path)
    parser.add_argument("--write-golden-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(); result = build_result(args.contract)
    if args.write_result:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.write_golden_dir:
        args.write_golden_dir.mkdir(parents=True, exist_ok=True)
        for group in ("requests", "responses"):
            for item in result[group]:
                name = str(item["request_id"]).replace(":", "-") + ".wire.json"
                (args.write_golden_dir / name).write_text(str(item["canonical_utf8"]), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True)); return 0
