from __future__ import annotations

import json
import importlib.util
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "qualify_servo_exact_pin_identity",
    ROOT / "tools/qualify_servo_exact_pin_identity.py",
)
assert SPEC is not None and SPEC.loader is not None
IDENTITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IDENTITY)
EVIDENCE_SPEC = importlib.util.spec_from_file_location(
    "qualify_servo_exact_pin_evidence",
    ROOT / "tools/qualify_servo_exact_pin_evidence.py",
)
assert EVIDENCE_SPEC is not None and EVIDENCE_SPEC.loader is not None
EVIDENCE = importlib.util.module_from_spec(EVIDENCE_SPEC)
EVIDENCE_SPEC.loader.exec_module(EVIDENCE)


class ServoExactPinWorkflowTests(unittest.TestCase):
    def test_trigger_patterns_cover_d0a01_registry_globs(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D0A-01")
        paths = set(gate["invalidation_paths"])
        workflow = (ROOT / ".github/workflows/servo-exact-pin.yml").read_text(
            encoding="utf-8"
        )

        # The registry's wildcard domains are intentional: adding a lock or
        # helper must trigger both the PR and exact-main push gates.
        for pattern in ("manifests/servo*.json", "tools/qualify_servo_exact_pin*"):
            self.assertIn(pattern, paths)
            marker = f'"{pattern}"'
            self.assertGreaterEqual(
                workflow.count(marker),
                2,
                f"D0A-01 workflow must carry {pattern} on PR and push",
            )

        # The permanent gate must trigger for every registered input on both
        # pull requests and exact-main pushes, including shared envelope code.
        for pattern in paths:
            marker = f'"{pattern}"'
            self.assertGreaterEqual(
                workflow.count(marker),
                2,
                f"D0A-01 workflow must trigger for {pattern} on PR and push",
            )

    def test_workflow_binds_desktop_identity_before_external_checkout(self) -> None:
        workflow = (ROOT / ".github/workflows/servo-exact-pin.yml").read_text(
            encoding="utf-8"
        )
        identity = "python3 tools/qualify_servo_exact_pin_identity.py"
        self.assertIn(identity, workflow)
        self.assertIn("EVENT_SHA: ${{ github.sha }}", workflow)
        self.assertIn("PR_HEAD_SHA: ${{ github.event.pull_request.head.sha || '' }}", workflow)
        self.assertIn("PR_BASE_SHA: ${{ github.event.pull_request.base.sha || '' }}", workflow)
        self.assertLess(workflow.index(identity), workflow.index("Check out exact Servo source pin"))
        self.assertIn("qualify_servo_exact_pin_evidence.py", workflow)
        self.assertIn("gate-evidence-envelope.json", workflow)
        self.assertIn("gate_evidence_envelope.py", workflow)
        self.assertNotIn("codex/d0a01-servo-exact-pin-v2-clean", workflow)

    def test_pull_request_identity_requires_live_base_and_head(self) -> None:
        main = "a" * 40
        head = "b" * 40
        merge = "c" * 40
        tree = "d" * 40
        identity = IDENTITY.derive_identity(
            event_name="pull_request",
            source_ref="refs/pull/1/merge",
            source_ref_name="1/merge",
            event_sha=merge,
            tested_sha=merge,
            tested_tree_sha=tree,
            parents=[main, head],
            current_main_sha=main,
            pr_head_sha=head,
            pr_base_sha=main,
        )
        self.assertEqual(identity["EVIDENCE_ROLE"], "pr_synthetic_merge")
        self.assertEqual(identity["TESTED_MERGE_SHA"], merge)
        self.assertEqual(identity["CANDIDATE_HEAD_SHA"], head)
        self.assertEqual(identity["PROMOTION_AUTHORITATIVE"], "false")
        with self.assertRaisesRegex(ValueError, "current origin/main"):
            IDENTITY.derive_identity(
                event_name="pull_request",
                source_ref="refs/pull/1/merge",
                source_ref_name="1/merge",
                event_sha=merge,
                tested_sha=merge,
                tested_tree_sha=tree,
                parents=["e" * 40, head],
                current_main_sha=main,
                pr_head_sha=head,
                pr_base_sha="e" * 40,
            )

    def test_pull_request_identity_rejects_inconsistent_ref_tuple(self) -> None:
        main = "a" * 40
        head = "b" * 40
        merge = "c" * 40
        tree = "d" * 40
        with self.assertRaisesRegex(ValueError, "synthetic merge ref"):
            IDENTITY.derive_identity(
                event_name="pull_request",
                source_ref="refs/heads/main",
                source_ref_name="main",
                event_sha=merge,
                tested_sha=merge,
                tested_tree_sha=tree,
                parents=[main, head],
                current_main_sha=main,
                pr_head_sha=head,
                pr_base_sha=main,
            )

    def test_manual_identity_rejects_pull_request_ref(self) -> None:
        sha = "a" * 40
        with self.assertRaisesRegex(ValueError, "branch or tag"):
            IDENTITY.derive_identity(
                event_name="workflow_dispatch",
                source_ref="refs/pull/1/merge",
                source_ref_name="1/merge",
                event_sha=sha,
                tested_sha=sha,
                tested_tree_sha="b" * 40,
                parents=["c" * 40],
                current_main_sha="d" * 40,
            )

    def test_exact_main_push_is_the_only_authoritative_role(self) -> None:
        main = "a" * 40
        parent = "b" * 40
        tree = "c" * 40
        identity = IDENTITY.derive_identity(
            event_name="push",
            source_ref="refs/heads/main",
            source_ref_name="main",
            event_sha=main,
            tested_sha=main,
            tested_tree_sha=tree,
            parents=[parent],
            current_main_sha=main,
        )
        self.assertEqual(identity["EVIDENCE_ROLE"], "exact_main_push")
        self.assertEqual(identity["INTEGRATED_MAIN_SHA"], main)
        self.assertEqual(identity["PROMOTION_AUTHORITATIVE"], "true")
        with self.assertRaisesRegex(ValueError, "refs/heads/main"):
            IDENTITY.derive_identity(
                event_name="push",
                source_ref="refs/heads/codex/test",
                source_ref_name="codex/test",
                event_sha=main,
                tested_sha=main,
                tested_tree_sha=tree,
                parents=[parent],
                current_main_sha=main,
            )

    def test_d0a01_envelope_cli_binds_downloaded_artifacts(self) -> None:
        # Exercise the actual adapter CLI with a small synthetic qualification
        # result.  This catches schema/digest drift between the D0A adapter and
        # the repository-wide envelope validator before an expensive Servo run.
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            artifact_root = Path(temporary)
            qualification = artifact_root / "servo-qualification-result.json"
            qualification.write_text(
                json.dumps(
                    {
                        "schema": "trillionnium.desktop.servo-qualification-result.v2",
                        "status": "PASS_COMPILE_COMPATIBILITY_ONLY",
                        "servo": {
                            "repository": "https://github.com/servo/servo",
                            "commit": "670ae8a70801b162e186f81cbb5bdd2d59c39108",
                            "clean_checkout": True,
                            "patch_count": 0,
                            "source_hashes": {
                                path: "e" * 64
                                for path in EVIDENCE.required_servo_input_paths()
                            },
                        },
                        "claims": {
                            "servo_started": False,
                            "window_created": False,
                            "frame_rendered": False,
                            "native_input_forwarded": False,
                            "ime_forwarded": False,
                            "network_navigation_performed": False,
                            "web_driver_listener_started": False,
                            "debian_image_built": False,
                            "product_ready": False,
                        },
                        "compile_results": {
                            "cargo_metadata_locked": {
                                "status": "PASS",
                                "log_sha256": "a" * 64,
                            },
                            "official_winit_minimal": {
                                "status": "PASS",
                                "log_sha256": "b" * 64,
                            },
                            "trillionnium_embedder_probe": {
                                "status": "PASS",
                                "log_sha256": "c" * 64,
                            },
                            "official_servoshell": {
                                "status": "PASS",
                                "log_sha256": "d" * 64,
                            },
                        },
                        "next_gate": "D0A-02 product-owned headed local-fixture runtime",
                    }
                ),
                encoding="utf-8",
            )
            (artifact_root / "logs").mkdir()
            (artifact_root / "logs/compile.log").write_text("pass\n", encoding="utf-8")
            output = artifact_root / "gate-evidence-envelope.json"
            env = os.environ.copy()
            env.update(
                {
                    "GITHUB_REPOSITORY": "TrillionniumFoundation/trillionnium-os-desktop",
                    "GITHUB_RUN_ID": "123",
                    "GITHUB_RUN_ATTEMPT": "1",
                    "RUNNER_OS": "Linux",
                    "RUNNER_ARCH": "X64",
                    "EVENT_NAME": "pull_request",
                    "SOURCE_REF": "refs/pull/7/merge",
                    "SOURCE_REF_NAME": "7/merge",
                    "TESTED_SHA": "c" * 40,
                    "TESTED_TREE_SHA": "d" * 40,
                    "BASE_SHA": "a" * 40,
                    "CANDIDATE_HEAD_SHA": "b" * 40,
                    "TESTED_MERGE_SHA": "c" * 40,
                    "INTEGRATED_MAIN_SHA": "",
                    "EVIDENCE_ROLE": "pr_synthetic_merge",
                    "PROMOTION_AUTHORITATIVE": "false",
                }
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/qualify_servo_exact_pin_evidence.py"),
                    "--qualification-result",
                    str(qualification),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            envelope = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(envelope["schema"], "trillionnium.desktop.gate-evidence.v1")
            self.assertEqual(envelope["tested_merge_sha"], "c" * 40)
            self.assertTrue(all(len(item["sha256"]) == 64 for item in envelope["artifacts"]))
            self.assertEqual(
                {item["path"] for item in envelope["artifacts"]},
                {"servo-qualification-result.json", "logs/compile.log"},
            )

            malformed = deepcopy(json.loads(qualification.read_text(encoding="utf-8")))
            malformed["claims"]["servo_started"] = True
            with self.assertRaises(ValueError):
                EVIDENCE.validate_qualification_result(malformed)

    def test_headed_pr_identity_binds_first_parent_to_current_main(self) -> None:
        runner = (ROOT / "tools/run_servo_headed_runtime_gate.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("git fetch --no-tags origin main", runner)
        self.assertIn("current_main=$(git rev-parse origin/main)", runner)
        self.assertIn('[[ "$base_sha" == "$current_main" ]]', runner)
        self.assertIn(
            "merge first parent is not the current origin/main object",
            runner,
        )


if __name__ == "__main__":
    unittest.main()
