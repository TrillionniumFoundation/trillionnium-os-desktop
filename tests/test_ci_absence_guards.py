"""Actual native absence scans; source guards do not qualify product execution."""
import copy
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

CLOSED_ACTOR_DECLARATIONS = ['pub use servo_runtime : : { ServoBrowserActor , ServoCompletionDelivery , ServoEventLoopWaker , ServoPumpResult , ServoRuntimeCommand , ServoRuntimeCompletion , ServoRuntimeEndpoint , ServoRuntimeError , ServoRuntimeOperation , ServoRuntimeOwner , closed_immutable_servo_runtime_pair , servo_runtime_pair , } ;', 'pub use servo_runtime : : { ServiceServoBrowserActor , ServiceServoRuntimeBridge , ServiceServoRuntimeCommand , ServiceServoRuntimeCompletion , ServiceServoRuntimeEndpoint , closed_immutable_service_runtime_pair , } ;', 'pub use hepta_agent_port : : { AgentPortError , DispatchContext , HandlerOutcome } ;', 'pub use hepta_agent_transport : : PeerIdentity ;', 'pub use hepta_browser_codec : : { BrowserRequest , BrowserResponse , ElementReference , JsonObject , JsonValue , NavigationTarget , ObservationField , PageAction , ProfilePersistence , ProfileSpec , WaitCondition , } ;', 'pub use hepta_peer_attestation : : { AttestedPeer , ProcfsPeerAttestor } ;', 'pub use hepta_session_core : : ReceiptJournal ;', 'pub use simulation : : { CancellationToken , PageOwnerSnapshot , ReceiptLifecycleObserver , TaskFlowPrincipal , executable_sha256 , scoped_frame_id , } ;', 'pub use service_actor : : ServiceServoBrowserActor ;', 'pub use service_runtime : : { ServiceServoBrowserActor , ServiceServoRuntimeBridge , ServiceServoRuntimeCommand , ServiceServoRuntimeCompletion , ServiceServoRuntimeEndpoint , closed_immutable_service_runtime_pair , } ;']


def blocks(path, name):
    lines = (ROOT / path).read_text().splitlines()
    result = []
    for index, line in enumerate(lines):
        if line.strip() != "- name: " + name:
            continue
        start = next(i for i in range(index + 1, len(lines))
                     if lines[i].strip() == "run: |") + 1
        end = start
        while end < len(lines) and (not lines[end].strip() or lines[end].startswith("          ")):
            end += 1
        result.append("\n".join(line[10:] if line.startswith("          ") else line
                                for line in lines[start:end]) + "\n")
    return result


def helper(body, name):
    start = body.index(name + "() {")
    end = body.index("\n}\n", start) + 3
    return body[start:end]


def shell(body, directory):
    return subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", body],
                          cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=10, env={**os.environ, "LC_ALL": "C",
                                           "RUNNER_TEMP": str(directory),
                                           "export_inventory": str(Path(directory) / "s06-public-exports.txt")})


class NativeCiAbsenceGuardTests(unittest.TestCase):
    def actor_fixture(self, directory, marker=""):
        # Execute the actual scanner and retained-reader dependencies inside
        # this owned fixture; production guards never import a host fallback.
        tools = directory / "tools"
        tools.mkdir()
        for name in ("scan_s06_public_exports.py", "artifact_evidence.py",
                     "browser_codec_reference_security.py"):
            (tools / name).write_bytes((ROOT / "tools" / name).read_bytes())
        target = directory / "crates/hepta-browser-actor/src"
        target.parent.mkdir(parents=True)
        shutil.copytree(ROOT / "crates/hepta-browser-actor/src", target)
        # The complete product already supplies from_attested/handle_attested.
        # Only this case's forbidden marker is additive to its closed inventory.
        (target / "fixture.rs").write_text(marker + "\n")
        contracts = directory / "contracts"
        contracts.mkdir()
        (contracts / "browser-actor.v1.json").write_bytes(
            (ROOT / "contracts/browser-actor.v1.json").read_bytes())

    def actor_bodies(self):
        result = blocks(".github/workflows/s06-browser-actor.yml",
                        "Reconfirm sealed product API and claim ceiling")
        self.assertEqual(len(result), 2)
        return result

    def test_both_complete_actor_bodies_reject_both_exposed_api_groups(self):
        for body in self.actor_bodies():
            for marker, expected, reason in (
                    ("pub struct BrowserActor<R> {}", 1, b"forbidden source match"),
                    ("pub type PrincipalBinding = (); ", 2,
                     b"closed product export inventory differs")):
                with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temp:
                    directory = Path(temp)
                    self.actor_fixture(directory, marker)
                    result = shell(body, directory)
                    self.assertEqual(result.returncode, expected, result.stdout.decode())
                    self.assertIn(reason, result.stdout)

    def test_both_complete_actor_bodies_preserve_clean_source_result(self):
        for body in self.actor_bodies():
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                self.actor_fixture(directory)
                result = shell(body, directory)
                self.assertEqual(result.returncode, 0, result.stdout.decode())

    def test_actor_native_missing_input_fails_before_following_success(self):
        for body in self.actor_bodies():
            commands = [line for line in body.splitlines() if line.startswith("reject_match -R")]
            self.assertEqual(len(commands), 2)
            for command in commands:
                with tempfile.TemporaryDirectory() as temp:
                    result = shell("set -euo pipefail\n" + helper(body, "reject_match")
                                   + command + "\nprintf reached-success\n", temp)
                    self.assertEqual(result.returncode, 2, result.stdout.decode())
                    self.assertNotIn(b"reached-success", result.stdout)

    def test_servo_native_guard_tail_refuses_marker_and_missing_source(self):
        source = (ROOT / ".github/workflows/s07-servo-retained-node.yml").read_text()
        text = "\n".join(line[10:] if line.startswith("          ") else line
                         for line in source.splitlines()) + "\n"
        command = next(line for line in text.splitlines()
                       if line.startswith('reject_match -R -F "TODO(#4344)'))
        body = "set -euo pipefail\n" + helper(text, "reject_match") + command + "\ngit -C servo diff --check\n"
        for case, expected in (("clean", 0), ("marker", 1), ("missing", 2)):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                target = directory / "servo/ports/servoshell/desktop/headed_window.rs"
                target.parent.mkdir(parents=True)
                subprocess.run(["git", "init", "-q", str(directory / "servo")], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if case != "missing":
                    target.write_text("// TODO(#4344): Forward action to Servo\n" if case == "marker"
                                      else "// actual forwarded callback\n")
                result = shell(body, directory)
                self.assertEqual(result.returncode, expected, result.stdout.decode())

    def test_d2i_native_guard_tail_distinguishes_clean_forbidden_and_read_error(self):
        text = (ROOT / "tools/run_d2i_integrated_image.sh").read_text()
        lines = text.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("  reject_source_match -RInE"))
        body = "set -euo pipefail\n" + helper(text, "reject_source_match") + "\n".join(lines[start:start + 2]) + "\n"
        for case, expected in (("clean", 0), ("write_permission", 1), ("push", 1), ("missing", 2)):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                (directory / "tools").mkdir()
                (directory / "tools/run_d2i_integrated_image.sh").write_text(text)
                if case != "missing":
                    (directory / ".github/workflows").mkdir(parents=True)
                    content = {"clean": "permissions:\n  contents: read\n",
                               "write_permission": "permissions:\n  contents: write\n",
                               "push": "# forbidden command: git push\n"}[case]
                    (directory / ".github/workflows/d2i-integrated-image.yml").write_text(content)
                result = shell(body, directory)
                self.assertEqual(result.returncode, expected, result.stdout.decode())


    def test_actual_actor_fixture_keeps_all_five_product_files_and_no_toy_exports(self):
        source = ROOT / "crates/hepta-browser-actor/src"
        retained = sorted(path.relative_to(source) for path in source.rglob("*.rs"))
        self.assertEqual(retained, sorted([Path("lib.rs"), Path("servo_runtime.rs"),
                                   Path("servo_runtime/approved_binding.rs"),
                                   Path("servo_runtime/service_runtime.rs"),
                                   Path("servo_runtime/service_runtime/service_actor.rs")]))
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.actor_fixture(directory)
            target = directory / "crates/hepta-browser-actor/src"
            self.assertEqual(sorted(path.relative_to(target) for path in target.rglob("*.rs")),
                             sorted(retained + [Path("fixture.rs")]))
            for path in retained:
                self.assertEqual((target / path).read_bytes(), (source / path).read_bytes())
            self.assertEqual((target / "fixture.rs").read_bytes(), b"\n")
            for name in ("scan_s06_public_exports.py", "artifact_evidence.py",
                         "browser_codec_reference_security.py"):
                self.assertEqual((directory / "tools" / name).read_bytes(),
                                 (ROOT / "tools" / name).read_bytes())
            self.assertEqual((directory / "contracts/browser-actor.v1.json").read_bytes(),
                             (ROOT / "contracts/browser-actor.v1.json").read_bytes())

    def test_both_complete_actor_bodies_write_the_exact_ten_product_declarations(self):
        # This independently fixed ordered oracle is never learned from CLI output.
        declarations = CLOSED_ACTOR_DECLARATIONS
        contract = json.loads((ROOT / "contracts/browser-actor.v1.json").read_text())
        self.assertEqual(contract["public_export_inventory"]["lexical_declarations"],
                         declarations)
        self.assertEqual(len(declarations), 10)
        for index, body in enumerate(self.actor_bodies()):
            with self.subTest(body=index), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                self.actor_fixture(directory)
                result = shell(body, directory)
                self.assertEqual(result.returncode, 0, result.stdout.decode())
                self.assertEqual((directory / "s06-public-exports.txt").read_text(),
                                 "\n".join(declarations) + "\n")

    def test_both_complete_actor_bodies_refuse_missing_product_declaration_before_success(self):
        for index, body in enumerate(self.actor_bodies()):
            with self.subTest(body=index), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                self.actor_fixture(directory)
                (directory / "crates/hepta-browser-actor/src/servo_runtime/service_runtime.rs").unlink()
                result = shell(body + "printf reached-success\n", directory)
                self.assertEqual(result.returncode, 2, result.stdout.decode())
                self.assertIn(b"closed product export inventory differs", result.stdout)
                self.assertNotIn(b"reached-success", result.stdout)

    def _fully_rebound_fixture(self, replacement):
        from tests.test_service_dispatch_denial_cutoff import CurrentPhysicalIngressBoundaryTests
        from tools import verify_service_dispatch_denial_cutoff as gate
        current = gate.inputs()
        path = "tests/test_ci_absence_guards.py"
        harness = CurrentPhysicalIngressBoundaryTests()
        harness.texts = current
        rebound, texts = harness._fully_rebound({path: replacement})
        previous_assignment = gate.expected_assignment(rebound)
        parent = gate.s06_ci_fixture_parent_source(path, current[path])
        old, complete = parent.splitlines(True), replacement.splitlines(True)
        complete_offsets = [0]
        for line in complete:
            complete_offsets.append(complete_offsets[-1] + len(line.encode()))
        rule = copy.deepcopy(rebound["s06_ci_fixture_parent_inverse1"][path])
        rule.update(complete_bytes=len(replacement.encode()),
                    complete_sha256=gate._sha(replacement.encode()))
        rule["byte_edits"] = []
        for kind, a, b, x, y in difflib.SequenceMatcher(None, old, complete, autojunk=False).get_opcodes():
            if kind != "equal":
                rule["byte_edits"].append({"complete_start": complete_offsets[x],
                                          "complete_end": complete_offsets[y],
                                          "complete_text": "".join(complete[x:y]),
                                          "parent_text": "".join(old[a:b])})
        rebound["s06_ci_fixture_parent_inverse1"][path] = rule
        rebound["s06_ci_fixture_current_physical1"][path] = gate._sha(replacement.encode())
        self.assertEqual(rebound["preserved_original_sha256"][path], gate._sha(replacement.encode()))
        self.assertEqual(texts[gate.TOOL].count(previous_assignment), 1)
        texts[gate.TOOL] = texts[gate.TOOL].replace(previous_assignment, gate.expected_assignment(rebound), 1)
        texts[gate.CONTRACT] = gate.canonical_contract_text(rebound)
        with mock.patch.object(gate, "EXPECTED", rebound):
            rebound["checker_nonEXPECTED_whole_sha256"] = gate._sha(gate.checker_body(texts[gate.TOOL]).encode())
        # The checker body stayed whole; only its canonical mutable envelope changed.
        self.assertEqual(texts[gate.CONTRACT], gate.canonical_contract_text(rebound))
        self.assertIn(gate.expected_assignment(rebound), texts[gate.TOOL])
        raw = replacement.encode()
        for edit in reversed(rule["byte_edits"]):
            start, end = edit["complete_start"], edit["complete_end"]
            self.assertEqual(raw[start:end], edit["complete_text"].encode())
            raw = raw[:start] + edit["parent_text"].encode() + raw[end:]
        self.assertEqual(raw, parent.encode())
        return gate, current, rebound, texts

    def test_unknown_fixture_is_refused_after_all_mutable_metadata_is_rebound(self):
        from tools import verify_service_dispatch_denial_cutoff as original
        path = "tests/test_ci_absence_guards.py"
        changed = original.inputs()[path] + "\n# fully rebound unknown fixture bytes\n"
        gate, current, rebound, texts = self._fully_rebound_fixture(changed)
        self.assertNotEqual(gate._sha(changed.encode()), gate._sha(current[path].encode()))
        with mock.patch.object(gate, "EXPECTED", rebound):
            self.assertEqual(texts[gate.CONTRACT], gate.canonical_contract_text(gate.EXPECTED))
            self.assertEqual(gate._sha(gate.checker_body(texts[gate.TOOL]).encode()),
                             rebound["checker_nonEXPECTED_whole_sha256"])
            self.assertEqual(rebound["s06_ci_fixture_current_physical1"][path], gate._sha(changed.encode()))
            self.assertEqual(rebound["s06_ci_fixture_parent_inverse1"][path]["complete_bytes"], len(changed.encode()))
            self.assertEqual(rebound["s06_ci_fixture_parent_inverse1"][path]["complete_sha256"], gate._sha(changed.encode()))
            with self.assertRaisesRegex(ValueError, "^P3 independent current S06 CI fixture physical Source differs$"):
                gate.check(rebound, texts)
            with self.assertRaisesRegex(ValueError, "^P3 unknown complete S06 CI fixture Source cannot normalize$"):
                gate.s06_ci_fixture_parent_source(path, changed)

    def test_exact_old_fixture_is_history_only_and_cannot_rebind_current_physical_admission(self):
        from tools import verify_service_dispatch_denial_cutoff as original
        from tools import verify_approved_service_product as product
        path = "tests/test_ci_absence_guards.py"
        current = original.inputs()[path]
        parent = original.s06_ci_fixture_parent_source(path, current)
        self.assertNotEqual(current, parent)
        self.assertEqual(original.s06_ci_fixture_parent_source(path, parent), parent)
        self.assertEqual(original.joint_parent_source(path, current), parent)
        self.assertEqual(product._read(ROOT, path), parent)
        self.assertEqual(original.parent_source(path, current), current)
        self.assertEqual(product.parent_source(path, current), current)
        gate, baseline, rebound, texts = self._fully_rebound_fixture(parent)
        with mock.patch.object(gate, "EXPECTED", rebound):
            self.assertEqual(texts[gate.CONTRACT], gate.canonical_contract_text(gate.EXPECTED))
            self.assertEqual(gate._sha(gate.checker_body(texts[gate.TOOL]).encode()),
                             rebound["checker_nonEXPECTED_whole_sha256"])
            self.assertEqual(rebound["preserved_original_sha256"][path], gate._sha(parent.encode()))
            self.assertEqual(rebound["s06_ci_fixture_current_physical1"][path], gate._sha(parent.encode()))
            self.assertEqual(rebound["s06_ci_fixture_parent_inverse1"][path]["byte_edits"], [])
            with self.assertRaisesRegex(ValueError, "^P3 independent current S06 CI fixture physical Source differs$"):
                gate.check(rebound, texts)
            self.assertEqual(gate.s06_ci_fixture_parent_source(path, parent), parent)


if __name__ == "__main__":
    unittest.main()
