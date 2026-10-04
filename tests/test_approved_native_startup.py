"""Closed composition source checks; these tests never execute native Servo."""
from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest

from tools import verify_approved_native_startup as verifier

ROOT = Path(__file__).resolve().parents[1]


class ApprovedNativeStartupSourceTests(unittest.TestCase):
    def queue(self):
        return (ROOT / verifier.QUEUE).read_text(encoding="utf-8")

    def native(self):
        return (ROOT / verifier.NATIVE).read_text(encoding="utf-8")

    def composition(self, contract=None, **changes):
        values = {
            "contract": verifier.load(ROOT / verifier.CONTRACT) if contract is None else contract,
            "queue": self.queue(), "native": self.native(),
            "product": (ROOT / "apps/hepta-browserd/src/product_dispatch.rs").read_text(encoding="utf-8"),
            "native_owner": (ROOT / "experiments/servo-product-owner/src/native_owner.rs").read_text(encoding="utf-8"),
        }
        values.update(changes)
        verifier.check_composition(**values)

    def test_actual_closed_contract_and_both_public_api_catalogs_match_source(self):
        self.composition()
        for path, text in [(verifier.QUEUE, self.queue()), (verifier.NATIVE, self.native())]:
            inventory = verifier.rust_inventory(text)
            self.assertEqual(sorted(inventory["public_api"]), verifier.EXPECTED["api_catalog"][path])
        self.assertEqual(sum(map(len, verifier.EXPECTED["api_catalog"].values())), 22)

    def test_nested_contract_limits_and_claims_are_closed_exact_types(self):
        original = verifier.load(ROOT / verifier.CONTRACT)
        for group, key, values in [
            ("ownership", "maximum_queued", [True, 1.0, 2]),
            ("ownership", "maximum_active", [True, 1.0, 2]),
            ("ownership", "maximum_result_queue", [True, 1.0, 2]),
            ("deadlines", "accepted_seconds_maximum", [20.0, True, 21]),
            ("deadlines", "native_seconds_maximum", [5.0, True, 20]),
            ("deadlines", "renewal", [0, True]),
            ("retirement", "all_drop_bounded", [0, True]),
            ("retirement", "drop_joins_worker", [0, True]),
            ("non_claims", "production_policy_provisioned", [0, True]),
            ("non_claims", "headed_or_hardware_qualified", [0, True]),
        ]:
            for value in values:
                with self.subTest(group=group, key=key, value=value):
                    mutant = copy.deepcopy(original)
                    mutant[group][key] = value
                    with self.assertRaises(ValueError): self.composition(mutant)

    def test_missing_unknown_reordered_and_duplicate_catalog_fields_refuse(self):
        original = verifier.load(ROOT / verifier.CONTRACT)
        mutations = []
        missing = copy.deepcopy(original); del missing["ownership"]["maximum_active"]
        mutations.append(missing)
        extra = copy.deepcopy(original); extra["admission"]["caller_approved"] = False
        mutations.append(extra)
        unknown = copy.deepcopy(original); unknown["api_catalog"]["other.rs"] = []
        mutations.append(unknown)
        for transform in [lambda value: value[:-1], lambda value: value + [value[0]],
                          lambda value: list(reversed(value))]:
            mutant = copy.deepcopy(original)
            mutant["api_catalog"][verifier.QUEUE] = transform(mutant["api_catalog"][verifier.QUEUE])
            mutations.append(mutant)
        for mutant in mutations:
            with self.subTest(mutant=mutant):
                with self.assertRaises(ValueError): self.composition(mutant)

    def test_public_api_name_and_signature_drift_cannot_rebind_contract(self):
        for text, check, mutations in [
            (self.queue(), verifier.check_queue, [
                ("selection: ApprovedAgentSelection", "selection: bool"),
                ("pub fn deadline(&self)", "pub fn deadline(&mut self)"),
                ("pub fn approved_retained_queue()", "pub fn caller_owned_queue()"),
            ]),
            (self.native(), verifier.check_native, [
                ("servo: Servo", "servo: ServoRuntimeEndpoint"),
                ("pub fn original_deadline(&self)", "pub fn original_deadline(&mut self)"),
                ("pub fn drive(&mut self)", "pub fn dispatch(&mut self)"),
            ]),
        ]:
            for before, after in mutations:
                with self.subTest(before=before):
                    self.assertIn(before, text)
                    with self.assertRaises(ValueError): check(text.replace(before, after, 1))
            with self.assertRaises(ValueError): check(text + "\npub fn split_pair() {}\n")

    def test_native_constructor_order_fixed_capacity_and_original_wake_ceiling(self):
        text = self.native()
        verifier.check_native(text)
        mutations = [
            ("ClosedImmutableNativeOwner::new(servo, context, waker)", "make_caller_owner(servo, context, waker)"),
            ("approved_retained_queue_before(original_deadline)?", "approved_retained_queue()"),
            ("mpsc::sync_channel(1)", "mpsc::sync_channel(2)"),
            ("first.coordinator(endpoint, journal, image_id)", "ProductRequestCoordinator::from_connection(endpoint, journal, image_id)"),
            ("value.min(self.original_deadline)", "value.max(self.original_deadline)"),
            ("Instant::now() >= self.original_deadline", "Instant::now() < self.original_deadline"),
            ("value.runtime_state() != RuntimeState::Ready", "false"),
        ]
        for before, after in mutations:
            with self.subTest(before=before):
                self.assertIn(before, text)
                with self.assertRaises(ValueError): verifier.check_native(text.replace(before, after, 1))
        changed_order = text.replace("        first.deadline()?;\n        let (endpoint, native)",
                                     "        let (endpoint, native)", 1)
        self.assertNotEqual(changed_order, text)
        with self.assertRaises(ValueError): verifier.check_native(changed_order)

    def test_native_owner_checks_precede_state_and_inherited_cleanup(self):
        text = self.native()
        mutations = [
            ("self.creator_pid != std::process::id()", "false"),
            ("self.creator_thread != thread::current().id()", "false"),
            ("self.current_owner()?;", ""),
            ("std::mem::forget(self.native.take());", "drop(self.native.take());"),
            ("std::mem::forget(self.observations.take());", "drop(self.observations.take());"),
            ("self.worker.take();", "self.worker.take().unwrap().join().unwrap();"),
        ]
        for before, after in mutations:
            with self.subTest(before=before):
                self.assertIn(before, text)
                with self.assertRaises(ValueError): verifier.check_native(text.replace(before, after, 1))

    def test_native_constructor_creator_refusal_preserves_inherited_engine_arguments(self):
        text = self.native()
        for before, after in [
            ("admission.ensure_creating_process()", "Ok(())"),
            ("std::mem::forget(servo);", "drop(servo);"),
            ("std::mem::forget(context);", "drop(context);"),
            ("std::mem::forget(waker);", "drop(waker);"),
        ]:
            with self.subTest(before=before):
                self.assertIn(before, text)
                with self.assertRaises(ValueError): verifier.check_native(text.replace(before, after, 1))
        queue = self.queue()
        marker = "creating(self.owner_pid)\n    }\n    pub fn from_received"
        self.assertIn(marker, queue)
        with self.assertRaises(ValueError):
            verifier.check_queue(queue.replace(marker, "self.deadline().map(|_| ())\n    }\n    pub fn from_received", 1))

    def test_contract_deadline_maxima_bind_existing_product_and_native_constants(self):
        for field, path, before, after in [
            ("product", "apps/hepta-browserd/src/product_dispatch.rs",
             "MAX_PRODUCT_CONNECTION_BUDGET: Duration = Duration::from_secs(20)",
             "MAX_PRODUCT_CONNECTION_BUDGET: Duration = Duration::from_secs(21)"),
            ("native_owner", "experiments/servo-product-owner/src/native_owner.rs",
             "OWNER_BUDGET: Duration = Duration::from_secs(5)",
             "OWNER_BUDGET: Duration = Duration::from_secs(20)"),
            ("native_owner", "experiments/servo-product-owner/src/native_owner.rs",
             "completion.deadline().min(local_stop)", "completion.deadline().max(local_stop)"),
        ]:
            with self.subTest(field=field, before=before):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(before, text)
                with self.assertRaises(ValueError): self.composition(**{field: text.replace(before, after, 1)})

    def test_actual_json_parser_rejects_duplicate_contract_fields(self):
        document = verifier.load(ROOT / verifier.CONTRACT)
        text = json.dumps(document)
        self.assertEqual(text.count('"maximum_queued": 1'), 1)
        with tempfile.TemporaryDirectory(prefix="approved-native-source-contract-") as temporary:
            path = Path(temporary) / "contract.json"
            path.write_text(text, encoding="utf-8")
            verifier.typed_equal(verifier.load(path), verifier.EXPECTED)
            for before, after in [
                ('"maximum_queued": 1', '"maximum_queued": 1, "maximum_queued": 1'),
                ('"default_activation": false', '"default_activation": false, "default_activation": false'),
            ]:
                with self.subTest(field=before):
                    path.write_text(text.replace(before, after, 1), encoding="utf-8")
                    with self.assertRaises(ValueError): verifier.load(path)

    def test_native_declared_cases_are_explicitly_registered_in_target(self):
        path = verifier.EXPECTED["qualification"]["native_target"]
        text = (ROOT / path).read_text(encoding="utf-8")
        inventory = verifier.check_native_target(text)
        self.assertEqual(len([name for name in inventory["functions"]
                              if name.startswith("actual_approved_startup_")]), 2)
        for name in verifier.EXPECTED["qualification"]["native_case_names"]:
            marker = name + "()"
            # Change only the actual call, leaving the defined test intact.
            location = text.rindex(marker)
            mutant = text[:location] + "unregistered_case()" + text[location + len(marker):]
            with self.subTest(name=name):
                with self.assertRaises(ValueError): verifier.check_native_target(mutant)
        with self.assertRaises(ValueError):
            verifier.check_native_target(text + "\nfn actual_approved_startup_unregistered() {}\n")

    def test_actual_prepare_source_mapping_and_harness_match_closed_native_target(self):
        path = verifier.EXPECTED["qualification"]["prepare"]
        text = (ROOT / path).read_text(encoding="utf-8")
        verifier.check_prepare(text)
        for before, after in [
            ("components/servo/tests/trillionnium_approved_startup.rs", "components/servo/tests/other_startup.rs"),
            ('name = "trillionnium_approved_connected"', 'name = "other_target"'),
            ("harness = false", "harness = true"),
            ("result = original.prepare(upstream, root)", "result = {}"),
        ]:
            with self.subTest(before=before):
                self.assertIn(before, text)
                mutant = text.replace(before, after, 1)
                with self.assertRaises(ValueError): verifier.check_prepare(mutant)

    def test_actual_workflow_compile_and_both_explicit_case_invocations_match(self):
        path = verifier.EXPECTED["qualification"]["workflow"]
        text = (ROOT / path).read_text(encoding="utf-8")
        verifier.check_workflow(text)
        for before, after in [
            ("--test trillionnium_approved_connected", "--test other_target"),
            ("cargo test --locked --profile checked-release", "cargo test --profile checked-release"),
            ("            actual_approved_startup_policy_refusal_before_constructor; do", "            unknown_case; do"),
            ('test "$count" = 2', 'test "$count" = 1'),
            ('"$binary" "$test_name" "$unit.service"', '"$binary" "$unit.service"'),
        ]:
            with self.subTest(before=before):
                self.assertIn(before, text)
                with self.assertRaises(ValueError): verifier.check_workflow(text.replace(before, after, 1))

    def test_actual_complete_source_validator_retains_pending_execution_claims(self):
        verifier.validate(ROOT)
        self.assertFalse(verifier.EXPECTED["default_activation"])
        self.assertTrue(all(value is False for value in verifier.EXPECTED["non_claims"].values()))
        self.assertEqual(verifier.EXPECTED["status"], "SOURCE_CANDIDATE_EXACT_PIN_EXECUTION_PENDING")

    def test_actual_queue_opaque_pair_capacity_deadline_and_worker_guards(self):
        inventory = verifier.check_queue(self.queue())
        self.assertIn("ApprovedRetainedAdmission::from_received", inventory["public_api"])
        self.assertIn("ApprovedRetainedAdmission::serve", inventory["public_api"])
        self.assertNotIn("ApprovedRetainedAdmission::into_parts", inventory["public_api"])

    def test_comments_and_literals_cannot_supply_missing_execution_guards(self):
        text = self.queue()
        marker = "coordinator.ensure_owner()?;"
        self.assertIn(marker, text)
        for replacement in ["// " + marker, 'let misleading = "' + marker + '";',
                            "/* " + marker + " */"]:
            with self.subTest(replacement=replacement):
                mutant = text.replace(marker, replacement, 1)
                with self.assertRaises(ValueError): verifier.check_queue(mutant)

    def test_actual_queue_deadline_and_identity_guard_source_mutations_refuse(self):
        text = self.queue()
        mutations = [
            ("current != self.original_deadline", "current < self.original_deadline"),
            ("product_time_remaining(self.original_deadline)?;", "let renewed = Instant::now();"),
            ("coordinator.ensure_owner()?;", ""),
            ("ApprovedRetainedProductConnection::from_received(received, selection)?", "legacy_admit(received, selection)?"),
            ("ProductRequestCoordinator::from_approved_retained_connection(", "ProductRequestCoordinator::from_connection("),
            ("worker.receive(remaining.min(Duration::from_millis(5)))", "worker.receive(Duration::from_secs(20))"),
            ("Arc::ptr_eq(state, &self.state)", "true"),
            ("drop(worker);", "worker.join().unwrap();"),
        ]
        for before, after in mutations:
            with self.subTest(before=before):
                self.assertIn(before, text)
                mutant = text.replace(before, after, 1)
                with self.assertRaises(ValueError): verifier.check_queue(mutant)

    def test_capacity_clone_extraction_field_visibility_and_retirement_mutants_refuse(self):
        text = self.queue()
        mutations = [
            ("mpsc::sync_channel(1);\n    let state", "mpsc::sync_channel(2);\n    let state"),
            ("pub struct ApprovedRetainedAdmission", "#[derive(Clone)]\npub struct ApprovedRetainedAdmission"),
            ("connection: Option<ApprovedRetainedProductConnection>", "pub connection: Option<ApprovedRetainedProductConnection>"),
            ("retired.store(true", "retired.store(false"),
            ("pub fn cancellation(&self)", "pub fn into_parts(&self)"),
        ]
        for before, after in mutations:
            with self.subTest(before=before):
                self.assertIn(before, text)
                with self.assertRaises(ValueError): verifier.check_queue(text.replace(before, after, 1))

    def test_pid_precedes_cancellation_latch_and_fork_channel_cleanup(self):
        text = self.queue()
        mutants = [
            text.replace("creating(cancellation.0.owner_pid)?;", "", 1),
            text.replace("creating(self.0.owner_pid)?;\n        self.0.retired.store", "self.0.retired.store", 1),
            text.replace("std::mem::forget(self.sender.take());", "drop(self.sender.take());", 1),
            text.replace("std::mem::forget(self.receiver.take());", "drop(self.receiver.take());", 1),
            text.replace("cancellation.0.active.try_lock()", "cancellation.0.active.lock()", 1),
            text.replace("cancellation.0.transport.try_lock()", "cancellation.0.transport.lock()", 1),
        ]
        for mutant in mutants:
            with self.subTest(mutant=mutant[-100:]):
                self.assertNotEqual(mutant, text)
                with self.assertRaises(ValueError): verifier.check_queue(mutant)

    def test_private_monitor_receiver_retains_pid_and_remaining_wait_budget(self):
        text = self.queue()
        section = text.split("impl ReportWorker {", 1)[1].split("impl Drop for ReportWorker", 1)[0]
        marker = "creating(self.owner_pid)?;"
        self.assertEqual(section.count(marker), 1)
        with self.assertRaises(ValueError):
            verifier.check_queue(text.replace(section, section.replace(marker, "", 1), 1))
        mutations = [
            ("recv_timeout(remaining)", "recv_timeout(Duration::from_secs(20))"),
            ("std::mem::forget(self.thread.take());", "drop(self.thread.take());"),
        ]
        for before, after in mutations:
            with self.subTest(before=before):
                self.assertIn(before, text)
                with self.assertRaises(ValueError): verifier.check_queue(text.replace(before, after, 1))

    def test_exact_type_and_closed_nested_fields_do_not_accept_boolean_integer_aliases(self):
        expected = {"claim": False, "capacity": 1, "nested": {"source": True}}
        verifier.typed_equal(copy.deepcopy(expected), expected)
        for mutation in [{"claim": 0, "capacity": 1, "nested": {"source": True}},
                         {"claim": False, "capacity": True, "nested": {"source": True}},
                         {"claim": False, "capacity": 1.0, "nested": {"source": True}},
                         {"claim": False, "capacity": 1, "nested": {"source": True, "extra": False}},
                         {"claim": False, "capacity": 1, "nested": {}}]:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError): verifier.typed_equal(mutation, expected)


class ApprovedNativeStartupGitIdentityTests(unittest.TestCase):
    """Execute the entire separate guard with real private Git objects and refs."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".approved-startup-git-", dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.repository = self.directory / "checkout"
        self.remote = self.directory / "origin.git"
        self.repository.mkdir()
        self.git("init", "--bare", str(self.remote), cwd=self.directory)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Private startup Git fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("remote", "add", "origin", str(self.remote))
        self.commit("base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "main")
        self.git("switch", "-c", "fork-topic")
        self.commit("fork head")
        self.head = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "HEAD:refs/pull/7/head")
        self.git("switch", "main")
        self.git("merge", "--no-ff", "fork-topic", "-m", "prospective")
        self.merge = self.git("rev-parse", "HEAD").strip()

    def git(self, *arguments, cwd=None):
        return subprocess.run(
            ["git", *arguments], cwd=cwd or self.repository, check=True,
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"},
        ).stdout

    def commit(self, message):
        (self.repository / "input").write_text(message + "\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", message)

    @staticmethod
    def guard():
        lines = (ROOT / ".github/workflows/g2-approved-native-startup.yml").read_text().splitlines()
        name = "      - name: Bind current canonical pull refs and ordered prospective parents"
        if lines.count(name) != 1:
            raise ValueError("one complete prospective identity step is required")
        start = lines.index(name)
        begin = lines.index("        run: |", start) + 1
        end = begin
        while end < len(lines) and (not lines[end].strip() or lines[end].startswith("          ")):
            end += 1
        body = "\n".join(line[10:] for line in lines[begin:end]) + "\n"
        if "${{" in body:
            raise ValueError("the guard obtains event fields through its environment")
        return body

    def execute(self, checkout=None, body=None, **changes):
        tested = checkout or self.merge
        self.git("checkout", "--detach", tested)
        self.summary = self.directory / "summary"
        self.summary.unlink(missing_ok=True)
        facts = {
            "EVENT_NAME": "pull_request", "PR_NUMBER": "7", "BASE_REF": "main",
            "EVENT_HEAD": self.head, "EVENT_BASE": self.base, "EVENT_TESTED": tested,
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "LC_ALL": "C", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
        }
        facts.update(changes)
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-c", self.guard() if body is None else body],
            cwd=self.repository, env={**os.environ, **facts},
            capture_output=True, text=True, timeout=10,
        )

    def denied(self, **changes):
        result = self.execute(**changes)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.summary.exists(), "a refusal cannot record an accepted identity")

    def test_guard_event_fields_and_position_are_bound_to_the_actual_pr(self):
        text = (ROOT / ".github/workflows/g2-approved-native-startup.yml").read_text()
        marker = "      - name: Bind current canonical pull refs and ordered prospective parents\n"
        before, step = text.split(marker, 1)
        prefix, _body = step.split("        run: |\n", 1)
        self.assertEqual(prefix, """        shell: bash
        env:
          EVENT_NAME: ${{ github.event_name }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          EVENT_HEAD: ${{ github.event.pull_request.head.sha }}
          EVENT_BASE: ${{ github.event.pull_request.base.sha }}
          EVENT_TESTED: ${{ github.sha }}
          BASE_REF: ${{ github.event.pull_request.base.ref }}
""")
        self.assertIn("  source-prospective:\n    if: github.event_name == 'pull_request'", before)
        self.assertNotIn("rustup toolchain install", before)
        self.assertIn("      - name: Source contract and original workspace regressions on prospective merge", step)

    def test_legal_fork_uses_only_pull_ref_and_records_exact_tree_and_parents(self):
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/fork-topic"), "")
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.summary.read_text().splitlines(), [
            "tested_commit=" + self.merge,
            "tested_tree=" + self.git("rev-parse", self.merge + "^{tree}").strip(),
            "live_base_ref=refs/heads/main", "live_base=" + self.base,
            "live_head_ref=refs/pull/7/head", "live_head=" + self.head,
            "ordered_parents=" + self.base + " " + self.head,
        ])

    def test_canonical_positive_numbers_and_nested_base_ref(self):
        for number in ("1", "123456789"):
            self.git("push", "origin", self.head + ":refs/pull/" + number + "/head")
            result = self.execute(PR_NUMBER=number)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.git("push", "origin", self.base + ":refs/heads/release/stable")
        result = self.execute(BASE_REF="release/stable")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_zero_leading_zero_alias_and_invalid_number_or_base_ref_refuse(self):
        for number in ("0", "07", "-7", "+7", "7.0"):
            self.git("push", "origin", self.head + ":refs/pull/" + number + "/head")
        for number in ("", "0", "07", "-7", "+7", "7.0", "7/head", "*", "7\n8"):
            with self.subTest(number=number):
                self.denied(PR_NUMBER=number)
        for branch in ("", "main*", "main..stable", "@{-1}", "main\nstable", "-main"):
            with self.subTest(branch=branch):
                self.denied(BASE_REF=branch)
        self.denied(EVENT_NAME="push")

    def test_wrong_missing_pr_or_base_never_falls_back_to_same_named_branch(self):
        self.git("push", "origin", self.head + ":refs/heads/fork-topic")
        self.denied(PR_NUMBER="8")
        self.git("push", "--force", "origin", self.base + ":refs/pull/7/head")
        self.denied()
        self.git("push", "origin", ":refs/pull/7/head")
        self.denied()
        self.git("push", "origin", self.head + ":refs/pull/7/head")
        self.denied(BASE_REF="missing")
        self.git("push", "--force", "origin", self.head + ":refs/heads/main")
        self.denied()

    def test_actual_slash_suffix_advertisements_cannot_substitute_or_ambiguate_refs(self):
        for query, alias, changes, object_id in (
            ("refs/pull/8/head", "refs/heads/refs/pull/8/head", {"PR_NUMBER": "8"}, self.head),
            ("refs/heads/missing", "refs/heads/refs/heads/missing", {"BASE_REF": "missing"}, self.base),
        ):
            self.git("push", "origin", object_id + ":" + alias)
            advertisement = self.git("ls-remote", "origin", query)
            self.assertIn(alias, advertisement)
            self.denied(**changes)
        for alias, object_id in (("refs/heads/refs/pull/7/head", self.head),
                                 ("refs/heads/refs/heads/main", self.base)):
            self.git("push", "origin", object_id + ":" + alias)
            self.denied()
            self.git("push", "origin", ":" + alias)

    def test_stale_event_objects_checkout_and_current_live_head_or_base_refuse(self):
        for changes in ({"EVENT_HEAD": self.base}, {"EVENT_BASE": self.head},
                        {"EVENT_TESTED": self.head}, {"EVENT_TESTED": self.merge.upper()},
                        {"EVENT_HEAD": self.head + "0"}):
            with self.subTest(changes=changes):
                self.denied(**changes)
        self.denied(checkout=self.base, EVENT_TESTED=self.merge)
        self.git("push", "--force", "origin", self.base + ":refs/pull/7/head")
        self.denied()
        self.git("push", "--force", "origin", self.head + ":refs/pull/7/head")
        self.git("switch", "-c", "live-base-moved", self.base)
        self.commit("base advanced")
        self.git("push", "origin", "HEAD:refs/heads/main")
        self.denied()

    def test_zero_one_reversed_and_three_actual_parents_refuse(self):
        tree = self.git("rev-parse", self.merge + "^{tree}").strip()
        third = self.git("commit-tree", tree, "-m", "independent root").strip()
        variants = [third,
                    self.git("commit-tree", tree, "-p", self.base, "-m", "one parent").strip(),
                    self.git("commit-tree", tree, "-p", self.head, "-p", self.base,
                             "-m", "reversed parents").strip(),
                    self.git("commit-tree", tree, "-p", self.base, "-p", self.head,
                             "-p", third, "-m", "three parents").strip()]
        for variant in variants:
            with self.subTest(variant=variant):
                self.denied(checkout=variant)


class ApprovedNativeStartupDirectLibcTests(unittest.TestCase):
    """Finite additive lock profile; synthetic source checks, never native qualification."""
    def locks(self):
        before = (b'version=4\n[[package]]\nname="servo"\nversion="0.5.0"\n'
                  b'dependencies=["original"]\n[[package]]\nname="original"\nversion="1.0.0"\n'
                  b'[[package]]\nname="libc"\nversion="0.2.189"\n'
                  b'source="registry+https://github.com/rust-lang/crates.io-index"\n'
                  b'checksum="3eaf3ede3fee6db1a4c2ee091bf8a8b4dccdc6d17f656fb07896ee72867612f2"\n')
        after = before.replace(b'dependencies=["original"]', b'dependencies=["libc","original"]')
        after = after.replace(b'0.2.189', b'0.2.186').replace(
            b'3eaf3ede3fee6db1a4c2ee091bf8a8b4dccdc6d17f656fb07896ee72867612f2',
            b'68ab91017fe16c622486840e4c83c9a37afeff978bd239b5293d61ece587de66')
        return before, after

    def check(self, before, after, **profile):
        from unittest.mock import patch
        from tools import prepare_native_product_owner as original
        with tempfile.TemporaryDirectory(prefix="approved-libc-lock-") as temporary:
            root = Path(temporary)
            old, new = root / "before.lock", root / "after.lock"
            old.write_bytes(before); new.write_bytes(after)
            with patch.dict(original.PIN_FILES, {"Cargo.lock": original.digest(before)}):
                return original.verify_lock(old, new, **profile)

    def test_unique_precise_direct_edge_only_in_approved_profile(self):
        before, after = self.locks()
        self.assertFalse(self.check(before, before)["actual_servo_execution"])
        self.assertFalse(self.check(before, after, approved_startup=True)["actual_servo_execution"])
        with self.assertRaises(ValueError): self.check(before, after)
        with self.assertRaises(ValueError): self.check(before, before, approved_startup=True)

    def test_missing_duplicate_qualified_or_other_package_edge_refuses(self):
        before, after = self.locks()
        mutants = [after.replace(b'"libc","original"', b'"original"'),
                   after.replace(b'"libc","original"', b'"libc","libc","original"'),
                   after.replace(b'"libc","original"', b'"libc 0.2.186","original"'),
                   after.replace(b'"libc","original"', b'"libc","changed"'),
                   after.replace(b'name="original"\nversion="1.0.0"',
                                 b'name="original"\nversion="1.0.0"\ndependencies=["libc"]'),
                   after.replace(b'version="0.5.0"', b'version="0.6.0"')]
        for mutant in mutants:
            with self.subTest(mutant=mutant):
                with self.assertRaises(ValueError): self.check(before, mutant, approved_startup=True)

    def test_registry_checksum_fields_and_exact_bool_refuse(self):
        before, after = self.locks()
        for mutant in [after.replace(b'68ab91017fe', b'08ab91017fe'),
                       after.replace(b'version="0.2.186"', b'version="0.2.189"'),
                       after + b'dependencies=["original"]\n',
                       after + b'unknown="field"\n']:
            with self.subTest(mutant=mutant):
                with self.assertRaises(ValueError): self.check(before, mutant, approved_startup=True)
        for value in [1, 0, None, "true"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): self.check(before, after, approved_startup=value)

    def test_closed_assembler_dependency_and_strict_lock_invocation(self):
        from tools import prepare_approved_native_startup as approved
        text = (ROOT / verifier.EXPECTED["qualification"]["prepare"]).read_text(encoding="utf-8")
        verifier.check_prepare(text)
        self.assertEqual(approved.TARGET.count(b"[dev-dependencies.libc]"), 1)
        for before, after in [("[dev-dependencies.libc]", "[dependencies.libc]"),
                              ("workspace = true", "version = '0.2'"),
                              ("approved_startup=True", "approved_startup=False"),
                              ("approved_startup=True", "approved_startup=1"),
                              (", approved_startup=True", "")]:
            with self.subTest(before=before):
                self.assertIn(before, text)
                with self.assertRaises(ValueError): verifier.check_prepare(text.replace(before, after, 1))


class ApprovedNativeStartupDiagnosticTests(unittest.TestCase):
    """Run the complete corpus shell with harmless local process fixtures.

    These are orchestration regressions, not native Servo or systemd evidence.
    No privileged command, policy installation or network operation runs here.
    """
    def body(self):
        workflow = (ROOT / verifier.EXPECTED["qualification"]["workflow"]).read_text()
        tail = workflow.split("      - name: Actual explicit-root approved same-channel native startup cases\n", 1)[1]
        block = tail.split("        run: |\n", 1)[1].split("      - name:", 1)[0]
        return "\n".join(line[10:] for line in block.splitlines()) + "\n"

    def exercise(self, first=0, second=0, marker="yes", tee_failure="no", drift="no"):
        import hashlib
        with tempfile.TemporaryDirectory(prefix="approved-native-diagnostics-") as directory:
            root = Path(directory)
            fakebin = root / "bin"
            fakebin.mkdir()
            binary = root / "fixture-binary"
            binary.write_text("harmless diagnostic executable fixture\n")
            (root / "native-owner-binary.txt").write_text(str(binary) + "\n")
            source = root / "source"
            source.write_text("unchanged source fixture\n")
            (root / "native-owner-source.sha256").write_text(
                hashlib.sha256(source.read_bytes()).hexdigest() + "  " + str(source) + "\n")
            sudo = fakebin / "sudo"
            sudo.write_text("""#!/bin/bash
set -euo pipefail
printf '%s\\n' "$*" >> "$RUNNER_TEMP/calls"
case " $* " in
  *" actual_approved_startup_semantic_lifecycle "*) status=$FIRST_STATUS; first=yes ;;
  *" actual_approved_startup_policy_refusal_before_constructor "*) status=$SECOND_STATUS; first=no ;;
  *) exit 91 ;;
esac
if test "$DRIFT" = yes; then printf 'changed fixture bytes\\n' > "$(cat "$RUNNER_TEMP/native-owner-binary.txt")"; fi
if test "$MARKER" = yes || test "$first" = no; then printf 'ACTUAL_APPROVED_NATIVE_STARTUP fixture-only\\n'; fi
exit "$status"
""")
            tee = fakebin / "tee"
            tee.write_text("""#!/bin/bash
/usr/bin/tee "$@"
case "$*" in *native-owner-1.log*) test "$TEE_FAILURE" != yes || exit 77 ;; esac
""")
            sudo.chmod(0o700)
            tee.chmod(0o700)
            environment = {"PATH": str(fakebin) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
                           "RUNNER_TEMP": str(root), "GITHUB_WORKSPACE": str(root),
                           "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                           "FIRST_STATUS": str(first), "SECOND_STATUS": str(second),
                           "MARKER": marker, "TEE_FAILURE": tee_failure, "DRIFT": drift}
            result = subprocess.run(["/bin/bash", "-c", self.body()], env=environment,
                                    capture_output=True, text=True, timeout=10, check=False)
            rows = (root / "native-owner-case-status.tsv").read_text().splitlines()
            calls = (root / "calls").read_text().splitlines()
            for call in calls:
                self.assertIn("--property=RuntimeMaxSec=60", call)
                self.assertIn("--property=NoNewPrivileges=yes", call)
                self.assertIn("--service-type=exec", call)
            return result, rows, calls

    def test_both_original_cases_succeed_only_with_successful_process_log_and_marker(self):
        result, rows, calls = self.exercise()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(rows[0], "case\tprocess_status\tlog_status\tmarker_status")
        self.assertEqual([row.split("\t")[1:] for row in rows[1:]], [["0", "0", "0"]] * 2)

    def test_first_process_failure_preserves_failure_and_runs_second_case(self):
        result, rows, calls = self.exercise(first=101)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(rows[1].split("\t")[1:], ["101", "0", "0"])
        self.assertEqual(rows[2].split("\t")[1:], ["0", "0", "0"])

    def test_second_process_failure_still_fails_aggregate(self):
        result, rows, calls = self.exercise(second=42)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(rows[2].split("\t")[1:], ["42", "0", "0"])

    def test_missing_first_marker_is_recorded_without_suppressing_second_case(self):
        result, rows, calls = self.exercise(marker="no")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(rows[1].split("\t")[1:], ["0", "0", "1"])

    def test_log_pipeline_failure_is_separate_and_never_promoted_to_success(self):
        result, rows, calls = self.exercise(tee_failure="yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(rows[1].split("\t")[1:], ["0", "77", "0"])

    def test_changed_executable_stops_before_any_additional_launch(self):
        result, rows, calls = self.exercise(drift="yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(rows), 2)

    def test_diagnostics_preserve_native_assertion_and_one_drive_per_turn(self):
        text = (ROOT / verifier.EXPECTED["qualification"]["native_target"]).read_text()
        run = verifier.function(verifier.rust_inventory(text), "run")
        self.assertEqual(run.count("drive"), 1)
        for token in ["original_deadline", "saturating_add", "try_observation"]:
            self.assertIn(token, run)
        self.assertIn("Instant::now() < driver.original_deadline().unwrap()", text)
        self.assertIn("original accepted budget, no renewal", text)
        self.assertEqual(text.count("APPROVED_NATIVE_DIAGNOSTIC"), 6)

    def test_physical_diagnostics_and_exact_historical_inverse_are_both_required(self):
        from tools import verify_service_dispatch_denial_cutoff as gate
        texts = gate.inputs(ROOT)
        gate.check(gate.EXPECTED, texts)
        for path, rule in gate.CLOSED_NATIVE_DIAGNOSTIC_SOURCE_RULES.items():
            with self.subTest(path=path):
                parent = gate.native_diagnostics_parent_source(path, texts[path])
                self.assertEqual(gate._sha(parent.encode()), rule["parent_sha256"])
                self.assertEqual(gate.native_diagnostics_parent_source(path, parent), parent)
                with self.assertRaises(ValueError):
                    gate.native_diagnostics_parent_source(path, texts[path] + "\n")
                mutant = dict(texts)
                mutant[path] = parent
                with self.assertRaises(ValueError):
                    gate.check(gate.EXPECTED, mutant)


if __name__ == "__main__":
    unittest.main()
