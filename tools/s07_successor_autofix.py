#!/usr/bin/env python3
"""Repair the extracted S07 package against the final S06 successor."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S06_HEAD = "f0e947e5e7267a3fcdd0a7d5437c0ae00c09ebfe"
BRANCH = "codex/s07-servo-retained-node-closure-v1"
SERVO = "670ae8a70801b162e186f81cbb5bdd2d59c39108"


def replace_exact(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{label}: expected {count} matches, found {actual}")
    return text.replace(old, new)


def patch_manifest() -> None:
    path = ROOT / "manifests/lab-d3-servo-retained-node-action.v1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["status"] = "bounded_exact_parent_source_and_real_servo_harness_candidate"
    manifest["carrier_branch"] = BRANCH
    manifest["carrier_base_commit"] = S06_HEAD
    manifest["carrier_parent_binding"] = (
        "pull_request_base_sha_equals_carrier_base_commit_and_commit_is_ancestor_of_exact_head"
    )
    manifest["carrier_head_binding"] = (
        "runtime_exact_checkout_plus_evidence_artifact_no_self_referential_static_sha"
    )
    qualification = manifest["qualification"]
    qualification["transitive_cli_sources"] = [
        "tools/qualify_servo_exact_pin_v3.py",
        "tools/_qualify_servo_exact_pin_v3_impl.py",
        "tools/qualify_servo_exact_pin.py",
        "tools/verify_d3_servo_patch.py",
    ]
    qualification["prospective_merge_applies_complete_package"] = True
    qualification["post_format_test_subject"] = (
        "staged_servo_tree_plus_full_index_patch_sha256_recorded_before_behavior_and_rechecked_after"
    )
    qualification["head_identity_location"] = (
        "evidence.json.carrier_commit_and_pull_request_live_head"
    )
    required = qualification["required"]
    additions = [
        "actual closure branch trigger and every transitive qualification source",
        "carrier base commit ancestry and live pull-request base equality",
        "complete base plus hardening application in the prospective merge job",
        "post-format tested Servo patch digest and staged tree identity",
        "post-behavior byte-for-byte tested patch and tree revalidation",
        "prospective merge complete changed-path equality and tested-tree evidence artifact",
    ]
    for item in additions:
        if item not in required:
            required.append(item)
    manifest["claim_ceiling"] = (
        "A green exact-head workflow proves clean complete-package application and the bounded "
        "retained-node corpus on the recorded post-format Servo tree in Servo's real test harness. "
        "A green prospective-merge job proves the live synthetic merge retains the same complete "
        "base-plus-hardening package, allowed changed paths, patch digest and staged Servo tree. "
        "Neither proves installed Trillionnium BrowserActor/receipt integration, independent image "
        "replay, release eligibility, physical hardware, protected-environment approval or HSM signing."
    )
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def patch_workflow() -> None:
    path = ROOT / ".github/workflows/s07-servo-retained-node.yml"
    text = path.read_text(encoding="utf-8")

    text = replace_exact(
        text,
        'branches: ["codex/s07-servo-retained-node-v1"]',
        f'branches: ["{BRANCH}"]',
        "push branch",
    )
    source_pair = '''      - "tools/verify_d3_servo_patch.py"
      - "tools/qualify_servo_exact_pin_v3.py"
'''
    source_block = '''      - "tools/verify_d3_servo_patch.py"
      - "tools/qualify_servo_exact_pin_v3.py"
      - "tools/_qualify_servo_exact_pin_v3_impl.py"
      - "tools/qualify_servo_exact_pin.py"
'''
    text = replace_exact(text, source_pair, source_block, "transitive path filters", count=2)
    text = replace_exact(
        text,
        f"env:\n  D3_SERVO_COMMIT: {SERVO}\n",
        f"env:\n  S06_HEAD: {S06_HEAD}\n  D3_SERVO_COMMIT: {SERVO}\n",
        "global S06 identity",
    )

    identity = '''          test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA"
          git rev-parse HEAD^{tree}
          python3 -m unittest discover -s tests -p 'test_s07_servo_patch_package.py' -v
'''
    bound_identity = f'''          test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA"
          git rev-parse HEAD^{{tree}}
          test "$(git merge-base HEAD "$S06_HEAD")" = "$S06_HEAD"
          test "$(jq -r '.carrier_base_commit' "$D3_SERVO_MANIFEST")" = "$S06_HEAD"
          test "$(jq -r '.carrier_branch' "$D3_SERVO_MANIFEST")" = "{BRANCH}"
          python3 -m unittest discover -s tests -p 'test_s07_servo_patch_package.py' -v
'''
    text = replace_exact(text, identity, bound_identity, "exact source parent binding")

    text = replace_exact(
        text,
        'git -C servo diff --binary --full-index > "$RUNNER_TEMP/d3-servo-squashed.patch"',
        'git -C servo diff --binary --full-index > "$RUNNER_TEMP/d3-servo-applied.patch"',
        "pre-format patch name",
    )

    format_anchor = '''          grep -Fxq components/servo/tests/accessibility.rs "$RUNNER_TEMP/d3-changed-formatted.txt"
'''
    format_extension = '''          grep -Fxq components/servo/tests/accessibility.rs "$RUNNER_TEMP/d3-changed-formatted.txt"
          git add -A
          git diff --cached --binary --full-index > "$RUNNER_TEMP/d3-servo-tested.patch"
          test -s "$RUNNER_TEMP/d3-servo-tested.patch"
          sha256sum "$RUNNER_TEMP/d3-servo-tested.patch" > "$RUNNER_TEMP/d3-servo-tested.patch.sha256"
          git write-tree > "$RUNNER_TEMP/d3-servo-tested-tree.txt"
          test -s "$RUNNER_TEMP/d3-servo-tested-tree.txt"
'''
    text = replace_exact(text, format_anchor, format_extension, "tested subject capture")

    collect_marker = "\n      - name: Collect bounded exact-head evidence\n"
    immutable_check = '''
          git diff --cached --binary --full-index > "$RUNNER_TEMP/d3-servo-after-behavior.patch"
          cmp "$RUNNER_TEMP/d3-servo-tested.patch" "$RUNNER_TEMP/d3-servo-after-behavior.patch"
          test "$(git write-tree)" = "$(cat "$RUNNER_TEMP/d3-servo-tested-tree.txt")"
          sha256sum -c "$RUNNER_TEMP/d3-servo-tested.patch.sha256"

      - name: Collect bounded exact-head evidence
'''
    text = replace_exact(text, collect_marker, "\n" + immutable_check, "post-behavior identity")

    old_files = '''          for file in d3-servo.patch d3-servo-base.patch d3-servo-hardening.patch \\
            d3-servo-squashed.patch d3-patch-verification.json d3-changed.txt \\
            d3-changed-formatted.txt d3-unexpected-formatted.txt d3-allowed.txt \\
'''
    new_files = '''          for file in d3-servo.patch d3-servo-base.patch d3-servo-hardening.patch \\
            d3-servo-applied.patch d3-servo-tested.patch d3-servo-tested.patch.sha256 \\
            d3-servo-tested-tree.txt d3-servo-after-behavior.patch \\
            d3-patch-verification.json d3-changed.txt d3-changed-formatted.txt \\
            d3-unexpected-formatted.txt d3-allowed.txt \\
'''
    text = replace_exact(text, old_files, new_files, "evidence file inventory")

    old_vars = '''          carrier=$(git rev-parse HEAD)
          carrier_tree=$(git rev-parse HEAD^{tree})
          jq -n \\
            --arg carrier "$carrier" \\
            --arg carrier_tree "$carrier_tree" \\
            --arg servo "$D3_SERVO_COMMIT" \\
'''
    new_vars = '''          carrier=$(git rev-parse HEAD)
          carrier_tree=$(git rev-parse HEAD^{tree})
          tested_patch_sha256=$(cut -d' ' -f1 "$RUNNER_TEMP/d3-servo-tested.patch.sha256")
          tested_tree=$(cat "$RUNNER_TEMP/d3-servo-tested-tree.txt")
          jq -n \\
            --arg carrier "$carrier" \\
            --arg carrier_tree "$carrier_tree" \\
            --arg carrier_base "$S06_HEAD" \\
            --arg servo "$D3_SERVO_COMMIT" \\
            --arg tested_patch_sha256 "$tested_patch_sha256" \\
            --arg tested_tree "$tested_tree" \\
'''
    text = replace_exact(text, old_vars, new_vars, "evidence identity arguments")

    old_object = '''              carrier_commit:$carrier,
              carrier_tree:$carrier_tree,
              servo_commit:$servo,
'''
    new_object = '''              carrier_commit:$carrier,
              carrier_tree:$carrier_tree,
              carrier_base_commit:$carrier_base,
              servo_commit:$servo,
              tested_servo_patch_sha256:$tested_patch_sha256,
              tested_servo_tree:$tested_tree,
              source_tree_rechecked_after_behavior:($behavior == "success"),
'''
    text = replace_exact(text, old_object, new_object, "evidence object identity")

    prospective_tail = '''          patch --dry-run --batch --forward -d servo -p1 < "$RUNNER_TEMP/s07-hardening.patch"
          git diff --check
'''
    prospective_replacement = '''          patch --dry-run --batch --forward -d servo -p1 < "$RUNNER_TEMP/s07-hardening.patch"
          patch --batch --forward -d servo -p1 < "$RUNNER_TEMP/s07-hardening.patch"
          git -C servo diff --name-only | sort > "$RUNNER_TEMP/s07-changed.txt"
          jq -r '.patch.allowed_paths[]' "$D3_SERVO_MANIFEST" | sort > "$RUNNER_TEMP/s07-allowed.txt"
          cmp "$RUNNER_TEMP/s07-allowed.txt" "$RUNNER_TEMP/s07-changed.txt"
          git -C servo diff --check
          git -C servo add -A
          git -C servo diff --cached --binary --full-index > "$RUNNER_TEMP/s07-tested.patch"
          test -s "$RUNNER_TEMP/s07-tested.patch"
          tested_patch_sha256=$(sha256sum "$RUNNER_TEMP/s07-tested.patch" | awk '{print $1}')
          tested_tree=$(git -C servo write-tree)
          merge_commit=$(git rev-parse HEAD)
          merge_tree=$(git rev-parse HEAD^{tree})
          base_commit=$(git rev-parse HEAD^1)
          head_commit=$(git rev-parse HEAD^2)
          jq -n \\
            --arg merge_commit "$merge_commit" \\
            --arg merge_tree "$merge_tree" \\
            --arg base_commit "$base_commit" \\
            --arg head_commit "$head_commit" \\
            --arg servo_commit "$D3_SERVO_COMMIT" \\
            --arg tested_patch_sha256 "$tested_patch_sha256" \\
            --arg tested_tree "$tested_tree" \\
            '{
              schema:"trillionnium.desktop.s07-prospective-merge.v1",
              merge_commit:$merge_commit,
              merge_tree:$merge_tree,
              base_commit:$base_commit,
              head_commit:$head_commit,
              servo_commit:$servo_commit,
              complete_base_and_hardening_applied:true,
              tested_patch_sha256:$tested_patch_sha256,
              tested_servo_tree:$tested_tree,
              changed_paths_equal_allowlist:true,
              product_integration_proven:false,
              release_authorized:false
            }' > "$RUNNER_TEMP/s07-prospective-evidence.json"
          {
            echo "tested_patch_sha256=$tested_patch_sha256"
            echo "tested_servo_tree=$tested_tree"
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Upload prospective-merge package evidence
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          name: s07-prospective-${{ github.event.pull_request.head.sha }}
          path: |
            ${{ runner.temp }}/s07-prospective-evidence.json
            ${{ runner.temp }}/s07-combined.patch
            ${{ runner.temp }}/s07-base.patch
            ${{ runner.temp }}/s07-hardening.patch
            ${{ runner.temp }}/s07-tested.patch
            ${{ runner.temp }}/s07-changed.txt
            ${{ runner.temp }}/s07-allowed.txt
          if-no-files-found: error
          retention-days: 30
'''
    text = replace_exact(text, prospective_tail, prospective_replacement, "complete prospective package")
    path.write_text(text, encoding="utf-8")


def write_tests() -> None:
    path = ROOT / "tests/test_s07_servo_patch_package.py"
    path.write_text(
        f'''import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests/lab-d3-servo-retained-node-action.v1.json"
EXPECTED_BASE = "{S06_HEAD}"
EXPECTED_BRANCH = "{BRANCH}"
EXPECTED_SERVO = "{SERVO}"
TRANSITIVE_CLI_SOURCES = (
    "tools/qualify_servo_exact_pin_v3.py",
    "tools/_qualify_servo_exact_pin_v3_impl.py",
    "tools/qualify_servo_exact_pin.py",
    "tools/verify_d3_servo_patch.py",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject_duplicate(pairs):
    output = {{}}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {{key}}")
        output[key] = value
    return output


class ServoPatchPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )

    def test_manifest_binds_exact_successor_parent_and_runtime_head(self) -> None:
        manifest = self.manifest
        self.assertEqual(manifest["schema"], "trillionnium.lab.servo-patch.v1")
        self.assertEqual(manifest["blocker"], "D3-01")
        self.assertEqual(manifest["carrier_branch"], EXPECTED_BRANCH)
        self.assertEqual(manifest["carrier_base_commit"], EXPECTED_BASE)
        self.assertIn("pull_request_base_sha", manifest["carrier_parent_binding"])
        self.assertIn("runtime_exact_checkout", manifest["carrier_head_binding"])
        self.assertEqual(manifest["upstream"]["repository"], "servo/servo")
        self.assertEqual(manifest["upstream"]["commit"], EXPECTED_SERVO)
        self.assertEqual(manifest["extracted_from"]["pull_request"], 73)
        self.assertEqual(
            manifest["qualification"]["transitive_cli_sources"],
            list(TRANSITIVE_CLI_SOURCES),
        )
        self.assertTrue(
            manifest["qualification"]["prospective_merge_applies_complete_package"]
        )

    def test_ordered_patch_parts_match_every_declared_digest(self) -> None:
        patch = self.manifest["patch"]
        hardening = self.manifest["hardening"]
        base = b""
        hardening_bytes = b""
        seen = set()
        for section, accumulator in ((patch, "base"), (hardening, "hardening")):
            data = b""
            for record in section["parts"]:
                source = ROOT / record["path"]
                self.assertTrue(source.is_file(), record["path"])
                self.assertNotIn(record["path"], seen)
                seen.add(record["path"])
                chunk = source.read_bytes()
                self.assertEqual(digest(chunk), record["sha256"])
                data += chunk
            self.assertEqual(digest(data), section["sha256"])
            if accumulator == "base":
                base = data
            else:
                hardening_bytes = data
        self.assertGreater(len(base), 0)
        self.assertGreater(len(hardening_bytes), 0)
        self.assertEqual(len(seen), 8)

    def test_production_verify_d3_patch_command_executes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            combined = temporary / "d3-servo.patch"
            base = temporary / "d3-servo-base.patch"
            hardening = temporary / "d3-servo-hardening.patch"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/qualify_servo_exact_pin_v3.py"),
                    "verify-d3-patch",
                    "--manifest", str(MANIFEST_PATH),
                    "--root", str(ROOT),
                    "--output", str(combined),
                    "--base-output", str(base),
                    "--hardening-output", str(hardening),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertIs(result["ok"], True)
            self.assertEqual(result["base_sha256"], self.manifest["patch"]["sha256"])
            self.assertEqual(result["hardening_sha256"], self.manifest["hardening"]["sha256"])
            self.assertEqual(digest(combined.read_bytes()), result["sha256"])
            separator = b"" if base.read_bytes().endswith(b"\n") else b"\n"
            self.assertEqual(combined.read_bytes(), base.read_bytes() + separator + hardening.read_bytes())
            self.assertEqual(result["changed_paths"], sorted(self.manifest["patch"]["allowed_paths"]))

    def test_original_exact_pin_cli_remains_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools/qualify_servo_exact_pin_v3.py"), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--servo-root", completed.stdout)
        self.assertIn("--output", completed.stdout)

    def test_workflow_covers_complete_package_and_exact_tested_tree(self) -> None:
        workflow = (ROOT / ".github/workflows/s07-servo-retained-node.yml").read_text(encoding="utf-8")
        self.assertIn(f'branches: ["{{EXPECTED_BRANCH}}"]', workflow)
        for source in TRANSITIVE_CLI_SOURCES:
            self.assertGreaterEqual(workflow.count(f'"{{source}}"'), 2, source)
        for required in (
            "exact-head-real-servo-behavior",
            "prospective-merge-patch-package",
            "refs/pull/${{ github.event.pull_request.number }}/merge",
            'patch --batch --forward -d servo -p1 < "$RUNNER_TEMP/s07-hardening.patch"',
            'cmp "$RUNNER_TEMP/s07-allowed.txt" "$RUNNER_TEMP/s07-changed.txt"',
            "d3-servo-tested.patch",
            "d3-servo-tested-tree.txt",
            "tested_servo_patch_sha256",
            "tested_servo_tree",
            "s07-prospective-evidence.json",
            "running != ['1']",
        ):
            self.assertIn(required, workflow)
        self.assertNotIn('RUSTFLAGS: "-D warnings"', workflow)

    def test_verifier_and_dispatcher_are_single_purpose(self) -> None:
        dispatcher = (ROOT / "tools/qualify_servo_exact_pin_v3.py").read_text(encoding="utf-8")
        verifier = (ROOT / "tools/verify_d3_servo_patch.py").read_text(encoding="utf-8")
        implementation = (ROOT / "tools/_qualify_servo_exact_pin_v3_impl.py").read_text(encoding="utf-8")
        self.assertIn('sys.argv[1] == "verify-d3-patch"', dispatcher)
        self.assertIn("from verify_d3_servo_patch import main", dispatcher)
        self.assertIn("from _qualify_servo_exact_pin_v3_impl import main", dispatcher)
        self.assertIn("import qualify_servo_exact_pin as qualifier", implementation)
        for required in (
            "load_patch_section",
            "verify_digest",
            "FORBIDDEN_ADDED_PATTERNS",
            "root.resolve() not in path.parents",
            "changed-path mismatch",
        ):
            self.assertIn(required, verifier)
        self.assertNotIn("subprocess", verifier)

    def test_claim_ceiling_remains_below_product_or_release(self) -> None:
        claim = self.manifest["claim_ceiling"].lower()
        for denied in (
            "installed trillionnium browseractor",
            "physical hardware",
            "hsm signing",
            "release eligibility",
        ):
            self.assertIn(denied, claim)
        required = [entry.lower() for entry in self.manifest["qualification"]["required"]]
        self.assertIn("post-format tested servo patch digest and staged tree identity", required)
        self.assertIn("complete base plus hardening application in the prospective merge job", required)


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )


def write_document() -> None:
    path = ROOT / "docs/implementation/D3_SERVO_RETAINED_NODE_ACTION.md"
    path.write_text(
        f'''# S07 exact-pin Servo retained-node action boundary

## Status and immutable parent

This document describes the bounded S07 source and real-test-harness candidate
on `{BRANCH}`, based on exact S06 commit
`{S06_HEAD}`. Only the 15 S07-specific files from the rejected older candidate
were extracted; no BrowserActor, daemon, platform, image, update, hardware,
signing, publication, or release source was imported from frozen PR #73 or old
PR #102.

The source manifest stores the immutable S06 parent and actual carrier branch.
The S07 head cannot safely contain its own SHA without a self-referential commit;
therefore the exact head and tree are asserted at runtime and recorded in the
workflow evidence artifact and live pull request. Any parent restack changes the
static parent field and fails the package tests until deliberately updated.

## Servo target and claim ceiling

The package targets Servo commit `{SERVO}` exactly. A green exact-head job proves
complete patch application and the retained-node corpus on the explicitly
recorded post-format Servo patch digest and staged tree. A green prospective
merge job proves the live two-parent PR merge retains and applies the complete
base plus hardening package with the declared changed paths. Neither job proves
installed product wiring, unrestricted navigation, target hardware, HSM custody,
publication, or release.

## Security property

At the pinned Servo revision the non-root AccessKit action path stops at
`TODO(#4344)`. The reviewed patch routes the exact retained `TreeId + NodeId`
back to the current active document and dispatches at most one untrusted Click
only when that same retained node advertises Click and remains connected,
enabled, visible, element-backed, and layout-finalized. Coordinate targeting,
JavaScript, WebDriver, selectors, text search, DOM-order lookup, and a separated
resolve-then-act phase remain forbidden.

## Route

1. `HeadedWindow` handles root-tree chrome locally and routes a non-root tree
   only when exactly one current WebView owns it.
2. WebView and Constellation retain the original typed AccessKit request and
   callback, bind it to the active top-level pipeline, and reject stale or
   ambiguous ownership.
3. Script refreshes retained accessibility/layout state and resolves the node
   inside one script-thread task, preventing page-script interleaving at the
   final lookup/action boundary.
4. The exact node must advertise Click and pass document, connection, element,
   enabled, visibility, and finalized-bounds checks.
5. One typed terminal callback reports dispatch or a closed failure class. A
   dropped receiver cannot cause duplicate dispatch.

## Immutable package and transitive qualification sources

The manifest binds eight ordered patch parts, every part digest, aggregate base
and hardening digests, the allowed Servo path set, source invariants and claim
ceiling. The production dispatcher is only a router, but its default path also
depends on `_qualify_servo_exact_pin_v3_impl.py` and
`qualify_servo_exact_pin.py`; all four transitive CLI sources are included in
both pull-request and push workflow filters.

The verifier rejects duplicate/escaping paths, digest or changed-path drift,
missing retained-node tokens, and forbidden coordinate/JavaScript/WebDriver/
selector/text-search additions.

## Exact tested Servo bytes

The exact-head job applies both patch stages, captures the pre-format result,
formats only patch-owned Rust files, stages the resulting Servo tree, writes the
full-index tested patch, and records its SHA-256 and Git tree. The behavior suite
then runs without source mutation. After the tests, the workflow regenerates the
staged patch, compares it byte-for-byte, rechecks the Git tree, and verifies the
recorded digest before marking evidence complete.

The prospective-merge job also applies both stages—not merely a base application
plus hardening dry run—compares the complete final changed-path set to the
allowlist, checks whitespace on the actual Servo worktree, stages the tree, and
publishes a merge evidence artifact containing live base/head/merge identities,
tested patch digest and tested Servo tree.

## Behavior matrix

The real Servo harness covers a valid retained button click, exactly-once
callback/dispatch, unadvertised Click, unsupported action/data, replaced node,
stale or inactive tree, disabled/hidden/non-element targets, missing finalized
bounds, dropped callback receiver, and the pinned accessibility mapping
regression. Each command must execute exactly one named test and produce one
passing terminal result.

## Remaining integration

A later successor must introduce a distinct concrete Servo product adapter and
prove the complete attested AgentPort → BrowserActor → Servo → durable receipt →
response path. Installed-image, hardware endurance, independent builders,
offline/HSM signing, protected publication and release claims remain outside S07.
''',
        encoding="utf-8",
    )


patch_manifest()
patch_workflow()
write_tests()
write_document()
