"""CLI for deterministic AgentPort bridge evidence."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from .evidence import build_result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--contract",type=Path,default=Path("contracts/agent-port-bridge.v1.json"))
    parser.add_argument("--write-result",type=Path)
    args=parser.parse_args(); result=build_result(args.contract)
    if args.write_result:
        args.write_result.parent.mkdir(parents=True,exist_ok=True)
        args.write_result.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True)); return 0
