"""Real private Git source-role checks; no expensive qualification body runs."""
from __future__ import annotations

import copy
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

from tools import verify_ci_source_identity as guard

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/ci-source-identity.v1.json"
INPUTS = ("tools/verify_ci_source_identity.py", "tests/test_ci_source_identity.py",
          CONTRACT, "docs/architecture/CI_SOURCE_IDENTITY.md")
EXPECTED_PROFILE = {
    "repository": guard.OFFICIAL_REPOSITORY,
    "remote": guard.OFFICIAL_REMOTE,
    "input_fields": list(guard.FIELDS),
    "roles": ["head", "prospective-merge", "event-source"],
    "events": ["pull_request", "push", "workflow_dispatch"],
    "sha": "exact40lowercasehex",
    "pr_number": "canonical positive decimal at most10digits",
    "refs": "full canonical ref; one UTF8row with exactly SHA TAB queriedref",
    "candidate": "live pull head matches event and checkout; parent count unrestricted",
    "prospective": "live base+pull head+pull merge match event; checkout has exactly ordered2parents",
    "push": "official current full branch ref matches event and checkout",
    "manual": "official current full branch matches event and checkout; non-authoritative",
    "snapshot": "same immutable commit/tree/rawparents before and after live lookups; clean checkout; bounded tracked bytes/type/mode match tree; no hidden index flags",
    "limits": {"total_seconds": 20, "command_seconds": 5, "combined_command_output_bytes": 262144,
               "ref_utf8_bytes": 1024, "cleanup_wait_seconds": 5,
               "tracked_files": 4096, "tracked_file_bytes": 16777216,
               "tracked_total_bytes": 67108864, "tracked_chunk_bytes": 65536},
    "subprocess": {"retained_unreaped_group_before_signals": True, "output_and_timeout_checked": True,
                   "fixed_cli_remote_no_override": True, "checkout_local_remote_rewrite_ignored": True},
    "claims": {"source_binding_only": True, "promotion_authority": False, "qualification": False,
               "installed": False, "production_ready": False, "all_async_snapshot_windows_closed": False},
}


def jobs(text):
    lines = text.splitlines(keepends=True)
    start = lines.index("jobs:\n") + 1
    markers = [i for i in range(start, len(lines)) if re.fullmatch(r"  [A-Za-z0-9_-]+:\n", lines[i])]
    result = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1] if index + 1 < len(markers) else len(lines)
        name = lines[marker].strip()[:-1]
        section = lines[marker:end]
        starts = [i for i, line in enumerate(section) if line.startswith("      - ")]
        result[name] = ["".join(section[begin:starts[i + 1] if i + 1 < len(starts) else len(section)]).rstrip()
                        for i, begin in enumerate(starts)]
    return result


def source_profile(value):
    if type(value) is not dict or set(value) != {"schema", "profile", "workflows", "source_index"}:
        raise ValueError("closed CI source contract fields differ")
    if value["schema"] != "trillionnium.ci-source-identity.v1" or json.dumps(value["profile"], sort_keys=True) != json.dumps(EXPECTED_PROFILE, sort_keys=True):
        raise ValueError("closed source role profile differs")
    if value["source_index"] != {"module": "hepta-browser-codec", "tool": INPUTS[0], "test": INPUTS[1], "documentation": INPUTS[3]}:
        raise ValueError("source index differs")


def validate_workflows(root, contract):
    source_profile(contract)
    paths = sorted(str(path.relative_to(root)) for path in (root / ".github/workflows").glob("*.yml"))
    if paths != sorted(contract["workflows"]): raise ValueError("workflow catalog differs")
    for path, catalog in contract["workflows"].items():
        text = (root / path).read_text(); current = jobs(text)
        if set(current) != set(catalog): raise ValueError("job catalog differs")
        for name, info in catalog.items():
            blocks = current[name]
            selected = [block for block in blocks if block.startswith("      - name: Verify canonical live source role\n")]
            if info["role"] is None:
                if selected: raise ValueError("availability diagnostic acquired source role")
                original = blocks
            else:
                if len(selected) != 1: raise ValueError("one exact source guard required")
                block = selected[0]
                expected_env = {
                    "CI_SOURCE_ROLE": info["role"], "CI_SOURCE_EVENT": "${{ github.event_name }}",
                    "CI_SOURCE_REPOSITORY": "${{ github.repository }}", "CI_SOURCE_REF": "${{ github.ref }}",
                    "CI_SOURCE_REF_NAME": "${{ github.ref_name }}", "CI_SOURCE_SHA": "${{ github.sha }}",
                    "CI_SOURCE_PR_NUMBER": "${{ github.event.pull_request.number }}",
                    "CI_SOURCE_PR_HEAD": "${{ github.event.pull_request.head.sha }}",
                    "CI_SOURCE_PR_BASE": "${{ github.event.pull_request.base.sha }}",
                    "CI_SOURCE_BASE_REF": "${{ github.event.pull_request.base.ref }}",
                }
                template = "      - name: Verify canonical live source role\n        shell: bash\n        env:\n" + "".join(f"          {key}: {value}\n" for key, value in expected_env.items())
                template += "        run: |\n          set -euo pipefail\n          python3 -B tools/verify_ci_source_identity.py"
                if block != template: raise ValueError("source guard command/role/closed fields changed")
                offset = blocks.index(block)
                if offset == 0 or "actions/checkout@" not in blocks[offset - 1] or offset != 1:
                    raise ValueError("source guard must precede old code-run immediately after checkout")
                original = [item for item in blocks if item is not block]
                # Each PR/push paths list must invalidate the same helper inputs.
                lines = text.splitlines()
                for start, line in enumerate(lines):
                    if line == "    paths:":
                        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i].startswith("      ")), len(lines))
                        section = "\n".join(lines[start + 1:end])
                        if any(f'"{item}"' not in section for item in INPUTS): raise ValueError("guard input missing from source trigger")
            if [hashlib.sha256(block.encode()).hexdigest() for block in original] != info["original_step_sha256"]:
                raise ValueError("original qualification step objects changed")


class CISourceIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ci-source-native-git-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.root.chmod(0o700)
        self.repo = self.root / "checkout"; self.repo.mkdir()
        self.remote = self.root / "official-fixture.git"
        self.environment = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                            "GIT_AUTHOR_NAME": "Private source fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                            "GIT_COMMITTER_NAME": "Private source fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
        self.git("init", "--bare", str(self.remote)); self.git("init", str(self.repo))
        self.git("remote", "add", "origin", str(self.remote))
        self.tree = self.git("mktree", input=b"")
        self.base = self.commit("base")
        self.head = self.commit("fork-head", [self.base])
        self.extra = self.commit("third-parent", [self.base])
        self.merge = self.commit("prospective", [self.base, self.head])
        self.triple = self.commit("three-parents", [self.base, self.head, self.extra])
        self.git("update-ref", "HEAD", self.merge)
        self.set_remote("refs/heads/main", self.base)
        self.set_remote("refs/pull/7/head", self.head)
        self.set_remote("refs/pull/7/merge", self.merge)
        self.fields = dict(zip(guard.FIELDS, ["prospective-merge", "pull_request", guard.OFFICIAL_REPOSITORY,
                          "refs/pull/7/merge", "7/merge", self.merge, "7", self.head, self.base, "main"]))

    def git(self, *arguments, input=None, cwd=None):
        return subprocess.check_output(["/usr/bin/git", *arguments], cwd=cwd or self.repo,
                                       env=self.environment, input=input, stderr=subprocess.DEVNULL, timeout=10).decode().strip()

    def commit(self, text, parents=()):
        return self.git("commit-tree", self.tree, *[item for parent in parents for item in ("-p", parent)], input=(text + "\n").encode())

    def set_remote(self, ref, sha):
        self.git("push", "--force", str(self.remote), f"{sha}:{ref}")

    def verify(self, fields=None, **kwargs):
        return guard._verify(self.repo, fields or self.fields, _remote=str(self.remote), **kwargs)

    def test_closed_contract_api_constants_and_catalog(self):
        value = json.loads((ROOT / CONTRACT).read_bytes()); source_profile(value); validate_workflows(ROOT, value)
        self.assertEqual(guard.OUTPUT_BYTES, value["profile"]["limits"]["combined_command_output_bytes"])
        self.assertEqual(guard.TOTAL_SECONDS, value["profile"]["limits"]["total_seconds"])
        self.assertEqual(guard.COMMAND_SECONDS, value["profile"]["limits"]["command_seconds"])
        self.assertEqual(guard.REF_BYTES, value["profile"]["limits"]["ref_utf8_bytes"])
        for constant, key in [(guard.TRACKED_FILES, "tracked_files"),
                              (guard.TRACKED_FILE_BYTES, "tracked_file_bytes"),
                              (guard.TRACKED_TOTAL_BYTES, "tracked_total_bytes"),
                              (guard.TRACKED_CHUNK_BYTES, "tracked_chunk_bytes")]:
            self.assertEqual(constant, value["profile"]["limits"][key])
        index = json.loads((ROOT / "manifests/modules.v1.json").read_bytes())
        module = next(item for item in index["modules"] if item["id"] == "hepta-browser-codec")
        for key, path in [("contracts", CONTRACT), ("tests", INPUTS[1]), ("architecture", INPUTS[3])]: self.assertIn(path, module[key])

    def test_contract_refuses_unknown_missing_type_alias_or_broadened_profiles(self):
        original = json.loads((ROOT / CONTRACT).read_bytes())
        changed = copy.deepcopy(original); changed["caller_approved"] = True
        with self.assertRaises(ValueError): source_profile(changed)
        for key in original:
            changed = copy.deepcopy(original); del changed[key]
            with self.assertRaises(ValueError): source_profile(changed)
        for key in original["profile"]["claims"]:
            changed = copy.deepcopy(original); changed["profile"]["claims"][key] = int(changed["profile"]["claims"][key])
            with self.assertRaises(ValueError): source_profile(changed)

    def test_source_mutants_refuse_guard_removal_role_change_late_guard_and_bad_trigger(self):
        value = json.loads((ROOT / CONTRACT).read_bytes())
        target = ".github/workflows/g2-native-product-owner.yml"
        text = (ROOT / target).read_text(); block = jobs(text)["source-prospective"][1]
        for variant in [text.replace(block, ""), text.replace("CI_SOURCE_ROLE: prospective-merge", "CI_SOURCE_ROLE: head", 1),
                        text.replace("CI_SOURCE_ROLE: prospective-merge", "CI_SOURCE_prospective-merge: prospective-merge", 1),
                        text.replace("python3 -B tools/verify_ci_source_identity.py", "true", 1),
                        text.replace('      - "tools/verify_ci_source_identity.py"\n', "", 1),
                        text.replace(block + "\n\n", "").replace("          make check", "          make check\n\n" + block)]:
            clone = self.root / "source-mutant"; clone.mkdir(exist_ok=True)
            for path in value["workflows"]:
                destination = clone / path; destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / path).read_bytes())
            (clone / target).write_text(variant)
            with self.assertRaises(ValueError): validate_workflows(clone, value)

    def test_actual_fork_only_pull_refs_and_ordered_two_parents_pass(self):
        result = self.verify()
        self.assertEqual(result["binding"], "prospective_merge")
        self.assertEqual(result["parents"], [self.base, self.head])
        self.assertIs(result["promotion_authority"], False)
        self.assertIs(result["production_ready"], False)
        self.assertEqual(self.git("ls-remote", str(self.remote), "refs/heads/fork-topic"), "")

    def test_candidate_head_keeps_normal_and_three_parent_commit_semantics(self):
        for sha in [self.head, self.triple]:
            self.git("update-ref", "HEAD", sha); self.set_remote("refs/pull/7/head", sha)
            fields = {**self.fields, "CI_SOURCE_ROLE": "head", "CI_SOURCE_PR_HEAD": sha}
            result = self.verify(fields)
            self.assertEqual(result["binding"], "candidate_head"); self.assertEqual(result["tested_sha"], sha)

    def test_original_head_only_prefix_accepts_three_parent_but_new_guard_refuses(self):
        self.git("update-ref", "HEAD", self.triple); self.set_remote("refs/pull/7/merge", self.triple)
        prefix = 'set -euo pipefail\ntest "$(git rev-parse HEAD)" = "$EXPECTED"\n'
        actual = subprocess.run(["bash", "-c", prefix], cwd=self.repo, env={**self.environment, "EXPECTED": self.triple}, timeout=5)
        self.assertEqual(actual.returncode, 0)
        with self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, "CI_SOURCE_SHA": self.triple})

    def test_live_base_and_head_drift_refuse_with_event_snapshot_unchanged(self):
        advanced = self.commit("advanced", [self.base])
        for ref, original in [("refs/heads/main", self.base), ("refs/pull/7/head", self.head)]:
            self.set_remote(ref, advanced)
            with self.assertRaises(guard.SourceIdentityError): self.verify()
            self.set_remote(ref, original)

    def test_merge_ref_drift_refuses_even_with_same_ordered_parents(self):
        alternative = self.commit("different-merge-object", [self.base, self.head])
        self.set_remote("refs/pull/7/merge", alternative)
        with self.assertRaises(guard.SourceIdentityError): self.verify()

    def test_missing_pull_head_cannot_use_same_named_branch_or_suffix_alias(self):
        self.git("update-ref", "-d", "refs/pull/7/head", cwd=self.remote)
        self.set_remote("refs/heads/fork-topic", self.head)
        with self.assertRaises(guard.SourceIdentityError): self.verify()
        self.set_remote("refs/vendor/refs/pull/7/head", self.head)
        with self.assertRaises(guard.SourceIdentityError): self.verify()

    def test_native_git_ambiguous_full_ref_rows_are_refused(self):
        self.set_remote("refs/vendor/refs/heads/main", self.base)
        actual = self.git("ls-remote", "--refs", str(self.remote), "refs/heads/main")
        self.assertEqual(len(actual.splitlines()), 2)
        with self.assertRaisesRegex(guard.SourceIdentityError, "MALFORMED_GIT_OUTPUT"): self.verify()

    def test_reverse_single_parent_wrong_checkout_and_wrong_event_ref_refuse(self):
        for sha in [self.head, self.commit("reversed", [self.head, self.base])]:
            self.git("update-ref", "HEAD", sha); self.set_remote("refs/pull/7/merge", sha)
            with self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, "CI_SOURCE_SHA": sha})
        self.git("update-ref", "HEAD", self.merge); self.set_remote("refs/pull/7/merge", self.merge)
        with self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, "CI_SOURCE_SHA": self.head})
        with self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, "CI_SOURCE_REF": "refs/pull/8/merge"})

    def test_push_and_manual_bind_current_branch_without_promotion(self):
        self.set_remote("refs/heads/codex/topic", self.merge)
        for event, binding in [("push", "push_head"), ("workflow_dispatch", "manual_source")]:
            fields = dict(zip(guard.FIELDS, ["event-source", event, guard.OFFICIAL_REPOSITORY,
                              "refs/heads/codex/topic", "codex/topic", self.merge, "", "", "", ""]))
            result = self.verify(fields); self.assertEqual(result["binding"], binding); self.assertIs(result["promotion_authority"], False)
            self.set_remote("refs/heads/codex/topic", self.head)
            with self.assertRaises(guard.SourceIdentityError): self.verify(fields)
            self.set_remote("refs/heads/codex/topic", self.merge)

    def test_push_or_manual_cannot_use_tag_alias_or_prospective_role(self):
        fields = dict(zip(guard.FIELDS, ["event-source", "workflow_dispatch", guard.OFFICIAL_REPOSITORY,
                          "refs/tags/v1", "v1", self.merge, "", "", "", ""]))
        with self.assertRaises(guard.SourceIdentityError): self.verify(fields)
        fields.update(CI_SOURCE_EVENT="push", CI_SOURCE_ROLE="prospective-merge", CI_SOURCE_REF="refs/heads/main", CI_SOURCE_REF_NAME="main")
        with self.assertRaises(guard.SourceIdentityError): self.verify(fields)

    def test_closed_fields_reject_bool_sign_leadingzero_overflow_controls_and_aliases(self):
        for key in guard.FIELDS:
            with self.subTest(key=key), self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, key: True})
        for number in ["", "0", "07", "+7", "-7", "7\n", "7.0", "77777777777", "refs/pull/7/head"]:
            with self.subTest(number=number), self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, "CI_SOURCE_PR_NUMBER": number})
        for branch in ["refs/heads/main", "@{-1}", "main\n", "main ", "-main", "a" * 1025, "a..b"]:
            with self.subTest(branch=branch), self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, "CI_SOURCE_BASE_REF": branch})
        for sha in [self.head.upper(), self.head[:-1], self.head + "0", "g" * 40]:
            with self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, "CI_SOURCE_PR_HEAD": sha})
        with self.assertRaises(guard.SourceIdentityError): self.verify({**self.fields, "caller_approved": "true"})
        missing = dict(self.fields); del missing["CI_SOURCE_PR_BASE"]
        with self.assertRaises(guard.SourceIdentityError): self.verify(missing)

    def test_dirty_or_changed_checkout_refuses_after_live_lookups(self):
        (self.repo / "unexpected").write_text("private untracked mutation")
        with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"): self.verify()
        (self.repo / "unexpected").unlink()
        seen = []
        def trace(frame, event, value):
            if frame.f_code is guard._Git.resolve.__code__ and event == "return" and not seen:
                self.git("update-ref", "HEAD", self.head); seen.append(True)
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"): self.verify()
        finally: sys.settrace(previous)
        self.assertEqual(seen, [True])

    def test_modified_tracked_source_cannot_hide_with_assume_unchanged_or_skip_worktree(self):
        source = self.repo / "source.py"
        source.write_text('print("original")\n')
        self.git("add", "source.py")
        self.git("commit", "-m", "tracked source fixture")
        head = self.git("rev-parse", "HEAD")
        self.set_remote("refs/heads/main", head)
        fields = dict(zip(guard.FIELDS, ["event-source", "push", guard.OFFICIAL_REPOSITORY,
                          "refs/heads/main", "main", head, "", "", "", ""]))
        self.assertEqual(self.verify(fields)["binding"], "push_head")
        for flag, clear in [("--assume-unchanged", "--no-assume-unchanged"),
                            ("--skip-worktree", "--no-skip-worktree")]:
            self.git("update-index", flag, "source.py")
            source.write_text('print("mutated")\n')
            self.assertEqual(self.git("status", "--porcelain=v1"), "")
            with self.subTest(flag=flag), self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"):
                self.verify(fields)
            source.write_text('print("original")\n')
            self.git("update-index", clear, "source.py")
        self.assertEqual(self.verify(fields)["binding"], "push_head")

    def test_equal_length_content_with_restored_mtime_cannot_hide_in_git_stat_cache(self):
        source = self.repo / "source.py"
        source.write_text('print("original")\n')
        past = time.time_ns() - 60000000000
        os.utime(source, ns=(past, past))
        self.git("add", "source.py"); self.git("commit", "-m", "stat-cache source fixture")
        head = self.git("rev-parse", "HEAD"); self.set_remote("refs/heads/main", head)
        fields = dict(zip(guard.FIELDS, ["event-source", "push", guard.OFFICIAL_REPOSITORY,
                          "refs/heads/main", "main", head, "", "", "", ""]))
        self.git("config", "core.trustctime", "false")
        self.git("status", "--porcelain=v1")
        before = source.stat(); source.write_text('print("modified")\n')
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.git("ls-files", "-v"), "H source.py")
        self.assertEqual(self.git("status", "--porcelain=v1"), "")
        with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"):
            self.verify(fields)

    def test_blob_header_executable_mode_and_symlink_bytes_are_bound(self):
        directory = self.repo / "nested"; directory.mkdir()
        source = directory / "source.py"; source.write_text('print("original")\n')
        link = self.repo / "entry"; link.symlink_to("nested/source.py")
        self.git("add", "nested/source.py", "entry"); self.git("commit", "-m", "typed tree fixture")
        head = self.git("rev-parse", "HEAD"); self.set_remote("refs/heads/main", head)
        fields = dict(zip(guard.FIELDS, ["event-source", "push", guard.OFFICIAL_REPOSITORY,
                          "refs/heads/main", "main", head, "", "", "", ""]))
        self.assertEqual(self.verify(fields)["tested_sha"], head)
        source.chmod(0o755)
        with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"):
            self.verify(fields)
        source.chmod(0o644); link.unlink(); link.symlink_to("nested/changed.py")
        with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"):
            self.verify(fields)
        link.unlink(); link.write_text("nested/source.py")
        with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"):
            self.verify(fields)
        link.unlink(); link.symlink_to("nested/source.py")
        source.unlink(); os.mkfifo(source)
        before = time.monotonic()
        with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"):
            self.verify(fields)
        self.assertLess(time.monotonic() - before, 1)

    def test_parent_symlink_and_oversize_tracked_file_refuse_without_following(self):
        directory = self.repo / "nested"; directory.mkdir()
        source = directory / "source.py"; source.write_text("tracked\n")
        self.git("add", "nested/source.py"); self.git("commit", "-m", "parent source fixture")
        head = self.git("rev-parse", "HEAD"); self.set_remote("refs/heads/main", head)
        fields = dict(zip(guard.FIELDS, ["event-source", "push", guard.OFFICIAL_REPOSITORY,
                          "refs/heads/main", "main", head, "", "", "", ""]))
        directory.rename(self.repo / "moved"); directory.symlink_to("moved", target_is_directory=True)
        with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_DRIFT"):
            self.verify(fields)
        directory.unlink(); (self.repo / "moved").rename(directory)
        with source.open("wb") as stream:
            stream.truncate(guard.TRACKED_FILE_BYTES + 1)
        with self.assertRaisesRegex(guard.SourceIdentityError, "SOURCE_LIMIT"):
            self.verify(fields)

    def test_real_output_limit_timeout_and_expired_budget_retire_owned_process(self):
        for program, expected in [(f"import os;os.write(1,b'x'*{guard.OUTPUT_BYTES + 4096})", "OUTPUT_LIMIT"),
                                  ("import time;time.sleep(5)", "COMMAND_TIMEOUT")]:
            before = time.monotonic()
            with self.assertRaisesRegex(guard.SourceIdentityError, expected):
                guard._run([sys.executable, "-c", program], cwd=self.root, deadline=time.monotonic() + 0.15)
            self.assertLess(time.monotonic() - before, 1.0)
        with self.assertRaisesRegex(guard.SourceIdentityError, "COMMAND_TIMEOUT"): self.verify(_budget=-1)
        gc.collect()

    def test_cli_missing_or_unknown_input_is_static_refusal_without_remote_override(self):
        command = [sys.executable, "-B", str(ROOT / INPUTS[0]), "--repository", str(self.repo)]
        for environment in [{}, {**self.fields, "CI_SOURCE_CALLER_APPROVED": "true"}]:
            result = subprocess.run(command, env={"PATH": "/usr/bin:/bin", **environment}, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1); self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr.strip(), "CI_SOURCE_IDENTITY_REFUSED:INVALID_INPUT")
        result = subprocess.run(command + ["--remote", str(self.remote)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
