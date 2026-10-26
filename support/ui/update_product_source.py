#!/usr/bin/env python3
"""Select one reviewed clean Hepta commit; Cargo alone regenerates its locks.

This updates source contracts and manifests, not runtime authority or test
qualification. Run the dependency checks and owning tests after Cargo resolves
the new combination. Existing build receipts remain historical evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "support/release"))
import organ_release_profile as source_profile

REPOSITORY = "https://github.com/TrillionniumFoundation/hepta-private-ci"
MANIFESTS = ("ui/Cargo.toml", "ui/core/Cargo.toml", "services/hepta-session-host/Cargo.toml")
ORIGINAL_FILES = (
    "codex-rs/hepta-agentd/NOTES_ORIGINAL_THREAD.md",
    "codex-rs/hepta-agentd/src/app_runtime.rs",
    "codex-rs/hepta-agentd/src/runtime.rs",
    "codex-rs/hepta-agentd/src/runtime_tests.rs",
    "codex-rs/hepta-agentd/src/notes_thread_seed.rs",
    "codex-rs/hepta-agentd/src/notes_thread_seed_tests.rs",
    "codex-rs/hepta-agentd/src/notes_thread_execution.rs",
    "codex-rs/hepta-agentd/src/notes_thread_execution_tests.rs",
    "codex-rs/hepta-agentd/src/notes_thread_runtime.rs",
    "codex-rs/hepta-agentd/src/notes_thread_tool.rs",
    "codex-rs/hepta-agentd/src/notes_thread_human.rs",
    "codex-rs/hepta-agentd/src/notes_launch_mode.rs",
    "codex-rs/hepta-agentd/src/root_notes_startup.rs",
    "codex-rs/hepta-agentd/src/root_notes_reservation.rs",
    "codex-rs/hepta-agentd/src/authority_host_logind.rs",
    "codex-rs/hepta-agentd/src/authority_host_notes_successor.rs",
    "codex-rs/hepta-agentd/src/authority_host_session.rs",
    "codex-rs/hepta-agentd/src/authority_host_listeners.rs",
    "codex-rs/hepta-agentd/src/authority_host_listeners_tests.rs",
    "codex-rs/hepta-agentd/src/authority_host_native_launch.rs",
    "codex-rs/hepta-agentd/src/authority_host_session_material.rs",
    "codex-rs/hepta-agentd/src/authority_host_material_recovery.rs",
    "codex-rs/hepta-agentd/src/authority_host_checkpoint_material.rs",
    "codex-rs/hepta-agentd/src/authority_host_checkpoint_material_recovery.rs",
    "codex-rs/hepta-agentd/src/config_root_late_writer.rs",
    "codex-rs/hepta-agentd/src/root_production_writer_handoff.rs",
    "codex-rs/hepta-agentd/src/authority_host_writer_rotate.rs",
    "codex-rs/hepta-agentd/src/lib.rs",
    "codex-rs/hepta-agentd/src/deployment_text_human.rs",
    "codex-rs/hepta-agentd/HUMAN_TEXT_PROVENANCE.md",
    "codex-rs/hepta-agentd/tests/fixtures/notes-model-v1.json",
    "codex-rs/hepta-memory/tests/fixtures/notes-model-v1.json",
    "codex-rs/hepta-memory/src/cognitive_checkpoint_image.rs",
    "codex-rs/hepta-memory/src/cognitive_checkpoint_install.rs",
    "codex-rs/third_party/aws-config-1.12.0/Cargo.toml",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hepta-root", type=Path, required=True)
    parser.add_argument("--commit", required=True, help="Explicit reviewed 40-hex original commit")
    args = parser.parse_args()
    try:
        original = source_profile.Repository(args.hepta_root, "hepta")
        source_profile.full_oid(args.commit, "Reviewed Hepta commit")
        if original.git("rev-parse", "HEAD^{commit}").decode().strip() != args.commit:
            raise source_profile.ProfileError("Reviewed commit must equal the selected checkout HEAD")
        tree = original.git("rev-parse", "HEAD^{tree}").decode().strip()
        original.check(args.commit, tree)
        path = ROOT / "support/ui/HEPTA_SHARED_PRESENTER.json"
        source = source_profile.load_json(path)
        names = {entry["path"] for entry in source["files"]} | set(ORIGINAL_FILES)
        records = [original.file(name)[1] for name in sorted(names)]
        # The model and wire fixtures must already match the reviewed owners.
        for name in ("codex-rs/hepta-agentd/tests/fixtures/notes-model-v1.json",
                     "codex-rs/hepta-memory/tests/fixtures/notes-model-v1.json"):
            if original.file(name)[0] != (ROOT / "tests/ui/notes-model-v1.json").read_bytes():
                raise source_profile.ProfileError("Original and Desktop Notes model fixtures differ")
        changed = {}
        for name in MANIFESTS:
            text = (ROOT / name).read_text()
            rows = []
            for row in text.splitlines():
                if REPOSITORY in row:
                    if not re.search(r'rev = "[0-9a-f]{40}"', row):
                        raise source_profile.ProfileError("Unpinned original dependency: " + name)
                    row = re.sub(r'rev = "[0-9a-f]{40}"', 'rev = "' + args.commit + '"', row)
                rows.append(row)
            text = "\n".join(rows) + "\n"
            if name != "ui/core/Cargo.toml" and not re.search(r"^aws-config\s*=", text, re.M):
                text = text.replace("[patch.crates-io]\n", "[patch.crates-io]\naws-config = { git = \""
                                    + REPOSITORY + "\", rev = \"" + args.commit + "\" }\n", 1)
            changed[name] = text
        source.update(commit=args.commit, tree=tree, files=records,
                      contract="One original Hepta source for the Rust presenter, native UI, Core thread tools, Root human admission and physical recovery. Source selection grants no runtime authority; each feature and installed package requires its own exact-source execution evidence.")
        profile_path = ROOT / "support/ui/linux-preedit-profile.json"
        profile = source_profile.load_json(profile_path)
        helper = {name: hashlib.sha256(original.file("apps/hepta-control-ui/test/" + name)[0]).hexdigest()
                  for name in profile["sdk_helper"]["files"]}
        profile.update(hepta_commit=args.commit, hepta_tree=tree,
                       sdk_helper={"commit": args.commit, "tree": tree, "files": helper})
        original.check(args.commit, tree)
        for name, text in changed.items():
            (ROOT / name).write_text(text)
        path.write_bytes(source_profile.canonical(source))
        profile_path.write_bytes(source_profile.canonical(profile))
        print(json.dumps({"hepta_commit": args.commit, "hepta_tree": tree,
                          "source_files": len(records), "cargo_locks_updated": False,
                          "next": "Run cargo update --workspace in each product Cargo root, then verify actual metadata, source caches and fixtures.",
                          "authority_granted": False}, sort_keys=True))
        return 0
    except (OSError, KeyError, ValueError, subprocess.SubprocessError, source_profile.ProfileError) as error:
        parser.exit(1, f"Source selection refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
