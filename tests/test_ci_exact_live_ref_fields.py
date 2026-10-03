"""Three complete CI bodies use actual Git refs, fetched provenance and CLI.

Only the fixture repository config maps the unchanged official URL to its
private bare origin. The S07 positive still performs the real carrier fetch,
lineage CLI and its two original source test modules. No Git executable is
replaced, no runtime/compiler is invoked, and none of these are product facts.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASE = "1e7d4cc41eee8c7e6e72dde17ec6c4d8da40d762"
CARRIER = "f0e947e5e7267a3fcdd0a7d5437c0ae00c09ebfe"
OFFICIAL = "https://github.com/TrillionniumFoundation/trillionnium-os-desktop.git"
BODIES = (("s06-browser-actor", "prospective-merge", "Bind merge parents to live remote refs"),
          ("receipt-journal", "prospective-merge", "Bind merge parents to live remote refs"),
          ("s07-servo-retained-node", "prospective-merge-patch-package",
           "Assert prospective merge identity and parent order"))
SOURCE_PATHS = (".github/workflows/s06-browser-actor.yml",
                ".github/workflows/receipt-journal.yml",
                ".github/workflows/s07-servo-retained-node.yml",
                "tests/test_ci_exact_live_ref_fields.py",
                "docs/DEVELOPMENT_GUIDE.md", "manifests/modules.v1.json")


# Exact complete1e7 literal bodies, independently tied to their original Git bytes.
BEFORE_BODIES = {'s06-browser-actor': {'sha256': '21ce28884dba7bd9aed6ae25eb2fd5b510dea6e4d6307c10b989c3806ba7d036', 'script': 'set -euo pipefail\ngit check-ref-format --branch "$BASE_REF"\ntest "$PR_NUMBER" -gt 0\ntest "$(git rev-parse HEAD)" = "${{ github.sha }}"\ntest "$(git rev-list --parents -n 1 HEAD | awk \'{print NF}\')" -eq 3\nlive_base="$(git ls-remote --exit-code origin "refs/heads/$BASE_REF" | awk \'NR == 1 {print $1}\')"\nlive_head="$(git ls-remote --exit-code origin "refs/pull/$PR_NUMBER/head" | awk \'NR == 1 {print $1}\')"\ntest -n "$live_base"\ntest -n "$live_head"\ntest "$live_head" = "$EVENT_HEAD"\ntest "$(git rev-parse HEAD^1)" = "$live_base"\ntest "$(git rev-parse HEAD^2)" = "$live_head"\nmerge_tree="$(git rev-parse \'HEAD^{tree}\')"\nprintf \'evidence_class=prospective_merge\\nsubject_sha=%s\\nsubject_tree=%s\\nbase_ref=%s\\nbase_sha=%s\\nhead_sha=%s\\n\' \\\n  "$(git rev-parse HEAD)" "$merge_tree" "$BASE_REF" "$live_base" "$live_head" \\\n  >> "$GITHUB_STEP_SUMMARY"\n\n'}, 'receipt-journal': {'sha256': '21ce28884dba7bd9aed6ae25eb2fd5b510dea6e4d6307c10b989c3806ba7d036', 'script': 'set -euo pipefail\ngit check-ref-format --branch "$BASE_REF"\ntest "$PR_NUMBER" -gt 0\ntest "$(git rev-parse HEAD)" = "${{ github.sha }}"\ntest "$(git rev-list --parents -n 1 HEAD | awk \'{print NF}\')" -eq 3\nlive_base="$(git ls-remote --exit-code origin "refs/heads/$BASE_REF" | awk \'NR == 1 {print $1}\')"\nlive_head="$(git ls-remote --exit-code origin "refs/pull/$PR_NUMBER/head" | awk \'NR == 1 {print $1}\')"\ntest -n "$live_base"\ntest -n "$live_head"\ntest "$live_head" = "$EVENT_HEAD"\ntest "$(git rev-parse HEAD^1)" = "$live_base"\ntest "$(git rev-parse HEAD^2)" = "$live_head"\nmerge_tree="$(git rev-parse \'HEAD^{tree}\')"\nprintf \'evidence_class=prospective_merge\\nsubject_sha=%s\\nsubject_tree=%s\\nbase_ref=%s\\nbase_sha=%s\\nhead_sha=%s\\n\' \\\n  "$(git rev-parse HEAD)" "$merge_tree" "$BASE_REF" "$live_base" "$live_head" \\\n  >> "$GITHUB_STEP_SUMMARY"\n\n'}, 's07-servo-retained-node': {'sha256': '3e2cf3a1ba4ea2e5a3b04b41eaf82e81b8c05a947aa082ab584d4dfce8484f2f', 'script': 'set -euo pipefail\ntest "$(git rev-parse HEAD)" = "$EXPECTED_MERGE_SHA"\ntest "$(git rev-list --parents -n1 HEAD | awk \'{print NF - 1}\')" -eq 2\ntest "$(git rev-parse HEAD^1)" = "$EXPECTED_BASE_SHA"\ntest "$(git rev-parse HEAD^2)" = "$EXPECTED_HEAD_SHA"\ngit check-ref-format --branch "$EXPECTED_BASE_REF"\n[[ "$PR_NUMBER" =~ ^[1-9][0-9]*$ ]]\nofficial_repository=https://github.com/TrillionniumFoundation/trillionnium-os-desktop.git\nlive_base=$(git ls-remote --exit-code "$official_repository" "refs/heads/$EXPECTED_BASE_REF" | awk \'NR == 1 {print $1}\')\nlive_head=$(git ls-remote --exit-code "$official_repository" "refs/pull/$PR_NUMBER/head" | awk \'NR == 1 {print $1}\')\ntest "$live_base" = "$EXPECTED_BASE_SHA"\ntest "$live_head" = "$EXPECTED_HEAD_SHA"\ngit fetch --no-tags https://github.com/TrillionniumFoundation/trillionnium-os-desktop.git "$S06_HEAD"\npython3 -B tools/verify_s07_qualification_lineage.py \\\n  --mode prospective-merge --expected-sha "$EXPECTED_MERGE_SHA" \\\n  --expected-base "$EXPECTED_BASE_SHA" --expected-head "$EXPECTED_HEAD_SHA" \\\n  > "$RUNNER_TEMP/s07-prospective-source-lineage.json"\npython3 -B -m unittest tests.test_s07_servo_patch_package tests.test_s07_qualification_lineage -v\n\n'}}


def body(workflow: str, job: str, step: str) -> str:
    lines = workflow.splitlines()
    start = lines.index("  " + job + ":")
    end = next((i for i in range(start + 1, len(lines))
                if re.fullmatch(r"  [A-Za-z0-9_-]+:", lines[i])), len(lines))
    selected = [i for i in range(start, end) if lines[i] == "      - name: " + step]
    if len(selected) != 1:
        raise ValueError("one complete identity step required")
    begin = next(i for i in range(selected[0] + 1, end) if lines[i] == "        run: |") + 1
    finish = begin
    while finish < end and (not lines[finish].strip() or lines[finish].startswith("          ")):
        finish += 1
    return "\n".join(line[10:] if line.startswith("          ") else line
                     for line in lines[begin:finish]) + "\n"


class ExactLiveRefFieldsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One fixed source-only carrier read for the class. Warm local objects
        # are fetched normally; cold shallow CI reads the immutable official
        # object once. Failure/30s timeout is a failure, never a skip.
        cls.carrier_temp = tempfile.TemporaryDirectory(prefix=".ci-carrier-", dir=ROOT.parent)
        cls.addClassCleanup(cls.carrier_temp.cleanup)
        cls.carrier = Path(cls.carrier_temp.name) / "carrier.git"
        cls.environment = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null",
                           "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
                           # Every private carrier/checkout/origin Git process
                           # must finish writing before its tempfile is removed.
                           # Process-local settings also reach Bash-body fetches
                           # and their local Git server children; no user or
                           # production-repository Git configuration is changed.
                           "GIT_CONFIG_PARAMETERS": "", "GIT_CONFIG_COUNT": "5",
                           "GIT_CONFIG_KEY_0": "gc.auto", "GIT_CONFIG_VALUE_0": "0",
                           "GIT_CONFIG_KEY_1": "gc.autoDetach", "GIT_CONFIG_VALUE_1": "false",
                           "GIT_CONFIG_KEY_2": "maintenance.auto", "GIT_CONFIG_VALUE_2": "false",
                           "GIT_CONFIG_KEY_3": "maintenance.autoDetach", "GIT_CONFIG_VALUE_3": "false",
                           "GIT_CONFIG_KEY_4": "receive.autogc", "GIT_CONFIG_VALUE_4": "false",
                           "PYTHONDONTWRITEBYTECODE": "1"}
        def native(*args, cwd=ROOT):
            return subprocess.run(["git", *args], cwd=cwd, env=cls.environment,
                                  check=True, capture_output=True, timeout=30).stdout
        native("init", "--quiet", "--bare", str(cls.carrier))
        local = subprocess.run(["git", "cat-file", "-e", CARRIER + "^{commit}"],
                               cwd=ROOT, env=cls.environment, capture_output=True, timeout=30)
        source = str(ROOT) if local.returncode == 0 else OFFICIAL
        native("--git-dir=" + str(cls.carrier), "fetch", "--quiet", "--no-tags",
               "--depth=1", source, CARRIER)
        native("--git-dir=" + str(cls.carrier), "update-ref", "refs/heads/carrier", CARRIER)
        raw = native("--git-dir=" + str(cls.carrier), "cat-file", "commit", CARRIER)
        tree = "b0b0304d70b209e26a08ed8a9d7e26f8a25cba02"
        parents = [line[7:].decode() for line in raw.split(b"\n\n", 1)[0].splitlines()
                   if line.startswith(b"parent ")]
        if (len(raw) > 65536 or hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != CARRIER
                or raw.splitlines()[0] != b"tree " + tree.encode()
                or parents != ["648b204618328c2f9b9271ed6eb6db8aea7d8987"]):
            raise AssertionError("fixed carrier metadata drift")
        if native("--git-dir=" + str(cls.carrier), "cat-file", "-t", tree).strip() != b"tree":
            raise AssertionError("fixed carrier tree absent")
        native("--git-dir=" + str(cls.carrier), "fsck", "--connectivity-only")
        cls.bootstrap = {"source": source, "network_read": local.returncode != 0,
                         "fixed_commit": CARRIER, "fixed_tree": tree, "parents": parents,
                         "shallow_parent_history_only": True, "full_tree_connectivity_checked": True,
                         "timeout_seconds": 30, "runtime_or_installed_qualified": False}
        for record in BEFORE_BODIES.values():
            if hashlib.sha256(record["script"].encode()).hexdigest() != record["sha256"]:
                raise AssertionError("captured complete baseline body drift")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".ci-live-field-", dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.repository = self.directory / "checkout"
        self.repository.mkdir()
        self.remote = self.directory / "origin.git"
        self.output = self.directory / "output"
        self.output.mkdir()
        self.git("init", "--quiet", "-b", "main")
        (self.repository / ".git/objects/info/alternates").write_text(str(self.carrier / "objects") + "\n")
        shallow = self.carrier / "shallow"
        if shallow.exists():
            (self.repository / ".git/shallow").write_bytes(shallow.read_bytes())
        self.git("config", "user.name", "Private live-ref source fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        # Current checked-out sources need no baseline ancestor in cold CI.
        paths = set(self.git("ls-files", "-z", cwd=ROOT).split("\0")) - {""}
        paths.update(SOURCE_PATHS)
        for relative in sorted(paths):
            source = ROOT / relative
            if not source.exists():
                raise AssertionError("current source path missing: " + relative)
            target = self.repository / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "private current source base")
        self.base = self.git("rev-parse", "HEAD").strip()
        (self.repository / "private-fixture-input").write_text("fork head\n")
        self.git("add", "private-fixture-input")
        self.git("commit", "--quiet", "-m", "private fork event head")
        self.head = self.git("rev-parse", "HEAD").strip()
        tree = self.git("rev-parse", "HEAD^{tree}").strip()
        self.merge = self.git("commit-tree", tree, "-p", self.base, "-p", self.head,
                              "-m", "private ordered prospective").strip()
        self.git("init", "--quiet", "--bare", str(self.remote), cwd=self.directory)
        (self.remote / "objects/info/alternates").write_text(str(self.carrier / "objects") + "\n")
        if shallow.exists():
            (self.remote / "shallow").write_bytes(shallow.read_bytes())
        self.git("remote", "add", "origin", self.remote.as_uri())
        self.git("config", "url." + self.remote.as_uri() + ".insteadOf", OFFICIAL)
        self.git("push", "--quiet", "origin", self.base + ":refs/heads/main",
                 self.head + ":refs/pull/7/head")
        self.git("--git-dir=" + str(self.remote), "update-ref", "refs/heads/private-carrier", CARRIER)
        self.records = []

    def git(self, *arguments, cwd=None) -> str:
        result = subprocess.run(["git", *arguments], cwd=cwd or self.repository,
                                env=self.environment, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, "actual Git " + repr(arguments) + "\n" + result.stderr)
        return result.stdout

    def execute(self, entry, *, before=False, checkout=None, **changes):
        workflow, job, step = entry
        source = (ROOT / ".github/workflows" / (workflow + ".yml")).read_text()
        script = BEFORE_BODIES[workflow]["script"] if before else body(source, job, step)
        source_digest = BEFORE_BODIES[workflow]["sha256"] if before else hashlib.sha256(source.encode()).hexdigest()
        self.git("checkout", "--quiet", "--detach", checkout or self.merge)
        facts = {"BASE_REF": "main", "EXPECTED_BASE_REF": "main", "PR_NUMBER": "7",
                 "EVENT_HEAD": self.head, "EXPECTED_HEAD_SHA": self.head,
                 "EXPECTED_BASE_SHA": self.base, "EXPECTED_MERGE_SHA": self.merge,
                 "S06_HEAD": CARRIER, "RUNNER_TEMP": str(self.output),
                 "GITHUB_STEP_SUMMARY": str(self.output / "summary"), "LC_ALL": "C"}
        facts.update(changes)
        script = script.replace("${{ github.sha }}", facts["EXPECTED_MERGE_SHA"])
        if "${{" in script:
            raise ValueError("unresolved CI expression")
        lineage_path = self.output / "s07-prospective-source-lineage.json"
        lineage_path.unlink(missing_ok=True)
        result = subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                                cwd=self.repository, env={**self.environment, **facts},
                                capture_output=True, text=True, timeout=30)
        lineage = json.loads(lineage_path.read_text()) if workflow.startswith("s07") and result.returncode == 0 else None
        if lineage is not None:
            self.assertEqual(lineage["current"]["commit"], self.merge)
            self.assertEqual(lineage["historical_carrier"]["commit"], CARRIER)
            self.assertFalse(lineage["actual_s06_execution_observed"])
            self.assertFalse(lineage["actual_servo_execution_observed"])
            self.assertIn("Ran 17 tests", result.stderr)
            self.assertTrue(result.stderr.rstrip().endswith("OK"))
            self.assertEqual(self.git("rev-parse", "FETCH_HEAD").strip(), CARRIER)
        self.records.append({"entry": entry, "before": before,
                             "source_sha256": source_digest,
                             "source_digest_scope": "captured_complete_baseline_body" if before else "current_workflow_file",
                             "script_sha256": hashlib.sha256(script.encode()).hexdigest(),
                             "checkout": checkout or self.merge, "facts": facts,
                             "exit": result.returncode, "stdout": result.stdout,
                             "stderr": result.stderr, "lineage": lineage})
        return result

    def table(self, expected_before, expected_after, **changes):
        for entry in BODIES:
            with self.subTest(entry=entry, changes=changes):
                old = self.execute(entry, before=True, **changes)
                new = self.execute(entry, **changes)
                before = expected_before(entry) if callable(expected_before) else expected_before
                self.assertEqual(old.returncode, before, old.stderr)
                self.assertEqual(new.returncode, expected_after, new.stderr)

    def test_original_complete_positive_bodies_fetch_and_run_current_source(self):
        self.table(0, 0)

    def test_wrong_and_missing_canonical_head_suffix_never_masks_drift(self):
        self.git("push", "--quiet", "--force", "origin", self.base + ":refs/pull/7/head",
                 self.head + ":refs/heads/refs/pull/7/head")
        self.table(0, 1)
        self.git("--git-dir=" + str(self.remote), "update-ref", "-d", "refs/pull/7/head")
        self.table(0, 1)

    def test_missing_canonical_base_suffix_never_substitutes_parent(self):
        self.git("push", "--quiet", "origin", self.base + ":refs/heads/refs/heads/unadvertised")
        self.table(0, 1, BASE_REF="unadvertised", EXPECTED_BASE_REF="unadvertised")


    def test_positive_canonical_numbers_and_slash_base_are_real_refs(self):
        for number in ("1", "123456789"):
            self.git("--git-dir=" + str(self.remote), "update-ref",
                     "refs/pull/" + number + "/head", self.head)
            self.table(0, 0, PR_NUMBER=number)
        self.git("--git-dir=" + str(self.remote), "update-ref",
                 "refs/heads/release/source", self.base)
        self.table(0, 0, BASE_REF="release/source", EXPECTED_BASE_REF="release/source")

    def test_actual_advertised_noncanonical_PRs_and_malformed_inputs_refuse(self):
        for number in ("07", "+7"):
            self.git("--git-dir=" + str(self.remote), "update-ref",
                     "refs/pull/" + number + "/head", self.head)
            self.table(lambda entry: 1 if entry[0].startswith("s07") else 0,
                       1, PR_NUMBER=number)
        for number in ("", "0", "-7", "7.0", "7/head", "*", "7\n8", "７"):
            self.table(lambda entry: 1 if entry[0].startswith("s07") or number in ("0", "-7") else 2,
                       1, PR_NUMBER=number)

    def test_actual_stale_live_refs_event_or_checkout_refuse(self):
        self.table(1, 1, EVENT_HEAD=self.base, EXPECTED_HEAD_SHA=self.base)
        self.table(1, 1, checkout=self.base)
        self.table(1, 1, EXPECTED_MERGE_SHA=self.head)
        self.git("--git-dir=" + str(self.remote), "update-ref", "refs/heads/main", self.head)
        self.table(1, 1)

    def test_actual_reversed_and_three_parent_commits_refuse(self):
        tree = self.git("rev-parse", self.merge + "^{tree}").strip()
        reversed_merge = self.git("commit-tree", tree, "-p", self.head,
                                  "-p", self.base, "-m", "actual reversed").strip()
        self.table(1, 1, checkout=reversed_merge, EXPECTED_MERGE_SHA=reversed_merge)
        third = self.git("commit-tree", tree, "-m", "independent actual parent").strip()
        three = self.git("commit-tree", tree, "-p", self.base, "-p", self.head,
                         "-p", third, "-m", "actual three parents").strip()
        self.assertEqual(len(self.git("show", "-s", "--format=%P", three).split()), 3)
        self.table(1, 1, checkout=three, EXPECTED_MERGE_SHA=three)

    def test_malformed_base_cannot_turn_full_ref_into_pattern(self):
        for value in ("", "-bad", "../main", "main*", "main..other", "main\nother"):
            self.table(128, 128, BASE_REF=value, EXPECTED_BASE_REF=value)

    def test_native_git_remote_error_never_publishes_lineage(self):
        absent = (self.directory / "absent.git").as_uri()
        self.git("remote", "set-url", "origin", absent)
        self.git("config", "--unset", "url." + self.remote.as_uri() + ".insteadOf")
        self.git("config", "url." + absent + ".insteadOf", OFFICIAL)
        self.table(128, 1)
        self.assertFalse((self.output / "s07-prospective-source-lineage.json").exists())
        self.assertFalse((self.output / "summary").exists())

    def test_exact_parser_stdin_rejects_duplicate_fields_without_partial_hash(self):
        # This checks the real inline parser with controlled stdin, not a wire
        # server or an entire Git/Bash transaction. All other methods use Git.
        ref = "refs/pull/7/head"
        actual = self.git("ls-remote", "--exit-code", "origin", ref)
        self.assertEqual(actual, self.head + "\t" + ref + "\n")
        alias = self.head + "\trefs/heads/" + ref + "\n"
        for entry in BODIES:
            source = (ROOT / ".github/workflows" / (entry[0] + ".yml")).read_text()
            program = re.search(r'awk -v ref="\$1" \'(.*?)\'',
                                body(source, entry[1], entry[2]), re.DOTALL)
            self.assertIsNotNone(program)
            for value, expected in ((actual, 0), (alias + actual, 0),
                                    (actual + actual, 1), (alias, 1), ("", 1)):
                completed = subprocess.run(["awk", "-v", "ref=" + ref, program[1]],
                                           input=value, text=True, capture_output=True,
                                           timeout=10)
                self.assertEqual(completed.returncode, expected, completed.stderr)
                self.assertEqual(completed.stdout, self.head + "\n" if expected == 0 else "")
            old = subprocess.run(["awk", "NR == 1 {print $1}"], input=actual + actual,
                                 text=True, capture_output=True, timeout=10)
            self.assertEqual(old.returncode, 0)
            self.assertEqual(old.stdout, self.head + "\n")

    def seed_native_loose_objects(self):
        # Real Git 2.43 estimates its loose-object count from fanout 17. Keep
        # this actual native-Git input finite and sufficient for gc.auto=1.
        seeds = []
        for number in range(100000):
            raw = ("owned cleanup primitive " + str(number) + "\n").encode()
            sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if not sha.startswith("17"): continue
            result = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                                    cwd=self.repository, env=self.environment,
                                    input=raw, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip().decode(), sha)
            seeds.append(sha)
            if len(seeds) == 2: break
        self.assertEqual(len(seeds), 2)
        return seeds

    def test_private_environment_suppresses_native_auto_maintenance_and_cleans_normally(self):
        for key in ("gc.auto", "gc.autoDetach", "maintenance.auto", "maintenance.autoDetach", "receive.autogc"):
            self.git("config", "--local", key, "1" if key == "gc.auto" else "true")
            self.assertEqual(self.git("config", "--get", key).strip(),
                             "0" if key == "gc.auto" else "false")
        self.seed_native_loose_objects()
        trace = self.output / "disabled-auto-trace2.jsonl"
        environment = {**self.environment, "GIT_TRACE2_EVENT": str(trace)}
        for command in (["git", "commit", "--quiet", "--allow-empty", "-m", "private lifecycle"],
                        ["git", "gc", "--auto", "--quiet"]):
            result = subprocess.run(command, cwd=self.repository, env=environment,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        self.assertTrue(any(row.get("event") == "start" for row in events))
        for row in events:
            if row.get("event") == "child_start":
                self.assertNotIn("maintenance", row.get("argv", []))
                self.assertNotIn("gc", row.get("argv", []))
        self.assertFalse((self.repository / ".git/gc.pid").exists())
        self.assertFalse((self.repository / ".git/gc.log.lock").exists())
        self.temp.cleanup()
        self.assertFalse(self.directory.exists())

    def test_actual_native_gc_during_cleanup_remains_an_error(self):
        # This negative scheduling variant enables GC only for this one native
        # command. Capture .git entries, let actual Git add packed-refs/GC state,
        # then continue the original tempfile cleanup. No error suppression or
        # cleanup retry is installed in the fixture.
        self.seed_native_loose_objects()
        gitdir = self.repository / ".git"
        self.assertFalse((gitdir / "packed-refs").exists())
        original_scandir = os.scandir
        observed = {}
        environment = {**self.environment, "GIT_CONFIG_VALUE_0": "1",
                       "GIT_CONFIG_VALUE_1": "true", "GIT_CONFIG_VALUE_2": "true",
                       "GIT_CONFIG_VALUE_3": "true"}
        class CapturedEntries:
            def __init__(self, entries): self.entries = iter(entries)
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self): return self
            def __next__(self): return next(self.entries)
        def scanned(path):
            name = Path(os.readlink("/proc/self/fd/" + str(path))) if type(path) is int else Path(path)
            if name != gitdir or observed: return original_scandir(path)
            with original_scandir(path) as entries: snapshot = list(entries)
            observed["initial_names"] = [entry.name for entry in snapshot]
            result = subprocess.run(["git", "gc", "--auto", "--quiet"],
                                    cwd=self.repository, env=environment,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((gitdir / "packed-refs").exists())
            pidfile = gitdir / "gc.pid"
            if pidfile.exists(): observed["pid"] = int(pidfile.read_text().split()[0])
            return CapturedEntries(snapshot)
        try:
            with patch.object(os, "scandir", scanned):
                with self.assertRaises(OSError) as raised: self.temp.cleanup()
            self.assertEqual(raised.exception.errno, 39)
            self.assertEqual(raised.exception.filename, ".git")
            self.assertNotIn("packed-refs", observed["initial_names"])
        finally:
            # Observe the owned negative-variant Git worker before the existing
            # addCleanup runs once. The unchanged positive fixture has no worker.
            pid = observed.get("pid"); deadline = time.monotonic() + 30
            while pid:
                try: state = (Path("/proc") / str(pid) / "stat").read_text().split()[2]
                except FileNotFoundError: break
                if state == "Z": break
                if time.monotonic() >= deadline:
                    raise AssertionError("native negative-variant GC exceeded its observation bound")
                time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
