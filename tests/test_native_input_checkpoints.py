"""Real private-file host-driver regressions; no Servo qualification is minted."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_input_checkpoints as gate


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.nonce = "a" * 32
        self.pid = os.getpid()
        self.start = gate.process_start(self.pid)
        self.identity = gate.root_identity(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def record(self, sequence=1, phase="up_accepted"):
        pointer = 100 if sequence == 0 else sequence * 3
        chrome = phase == "chrome_ready"
        down = phase in {"down_accepted", "up_accepted"}
        up = phase == "up_accepted"
        return {"schema": "trillionnium.desktop.native-input-checkpoint.v1",
                "nonce": self.nonce, "owner_pid": self.pid, "owner_start_time": self.start,
                "generation": 1, "sequence": sequence, "phase": phase,
                "content_point": None if chrome else list(gate.POINTS[max(0, sequence - 1)]),
                "pointer_event_id": None if chrome else f"InputEventId({pointer})",
                "down_event_id": f"InputEventId({pointer + 1})" if down else None,
                "up_event_id": f"InputEventId({pointer + 2})" if up else None,
                "pointer_dispatch_accepted": not chrome, "down_dispatch_accepted": down,
                "up_dispatch_accepted": up, "completed_pairs": sequence if up else max(0, sequence - 1),
                "product_ready": False}

    def write(self, sequence, phase, value=None):
        name = f"input-pair-{sequence}-{phase}.json"
        temporary = self.root / ("." + name)
        temporary.write_text(json.dumps(value or self.record(sequence, phase)) + "\n")
        temporary.chmod(0o600)
        temporary.replace(self.root / name)
        return self.root / name

    def validate(self, value):
        gate.validate_checkpoint(value, nonce=self.nonce, pid=self.pid, start=self.start,
                                 sequence=1, phase="up_accepted")

    def inventory(self):
        digests = {}
        for sequence, phases in [(0, ("prelude_ready", "chrome_ready")),
                                 *[(n, ("ready", "down_accepted", "up_accepted")) for n in range(1, 4)]]:
            for phase in phases:
                path = self.write(sequence, phase)
                digests[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt = {"schema": "trillionnium.desktop.native-input-stimulus.v1", "status": "HOST_STIMULUS_COMPLETE",
                   "nonce": self.nonce, "owner_pid": self.pid, "owner_start_time": self.start,
                   "window_id": 123, "commands": copy.deepcopy(gate.STIMULI),
                   "checkpoint_sha256": digests, "product_ready": False}
        path = self.root / "input-stimulus.json"
        path.write_text(json.dumps(receipt))
        path.chmod(0o600)
        return receipt

    def test_complete_private_chain_is_structurally_consistent(self):
        self.inventory()
        gate.verify(self.root, self.nonce, self.pid)

    def test_identity_phase_claim_types_and_actual_ids_are_closed(self):
        mutations = [("nonce", "b" * 32), ("owner_pid", self.pid + 1),
                     ("owner_start_time", self.start + 1), ("generation", 2),
                     ("generation", True), ("sequence", True), ("phase", "ready"),
                     ("content_point", [200, 132]), ("pointer_event_id", "caller-fact"),
                     ("up_event_id", "InputEventId(4)"), ("up_dispatch_accepted", False),
                     ("down_dispatch_accepted", 1), ("completed_pairs", 0), ("product_ready", True)]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                record = self.record()
                record[field] = value
                with self.assertRaises(ValueError):
                    self.validate(record)
        record = self.record()
        record["caller_approved"] = True
        with self.assertRaises(ValueError):
            self.validate(record)

    def test_missing_stage_or_changed_same_generation_record_is_refused(self):
        receipt = self.inventory()
        path = self.root / "input-pair-2-up_accepted.json"
        path.unlink()
        with self.assertRaises((FileNotFoundError, ValueError)):
            gate.verify(self.root, self.nonce, self.pid)
        self.write(2, "up_accepted")
        path.write_text(path.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "changed after"):
            gate.verify(self.root, self.nonce, self.pid)
        self.assertEqual(len(receipt["checkpoint_sha256"]), 11)

    def test_cross_pair_id_reuse_is_refused_even_with_consistent_hash_inventory(self):
        receipt = self.inventory()
        for phase in ("ready", "down_accepted", "up_accepted"):
            value = self.record(3, phase)
            for field in ("pointer_event_id", "down_event_id", "up_event_id"):
                if value[field] is not None:
                    value[field] = self.record(1, phase)[field]
            path = self.write(3, phase, value)
            receipt["checkpoint_sha256"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.root / "input-stimulus.json").write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "reuse"):
            gate.verify(self.root, self.nonce, self.pid)

    def test_full_inventory_detects_a_predecessor_changed_during_a_later_read(self):
        self.inventory()
        real_load = gate.load_private
        def changed(root, name, identity, **kwargs):
            result = real_load(root, name, identity, **kwargs)
            if name == "input-pair-3-up_accepted.json":
                with (root / "input-pair-1-ready.json").open("a") as stream:
                    stream.write(" ")
            return result
        with patch.object(gate, "load_private", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "earlier"):
                gate.verify(self.root, self.nonce, self.pid)

    def test_an_extra_click_or_a_failed_driver_receipt_is_refused(self):
        receipt = self.inventory()
        receipt["commands"].append(["mousedown", "1"])
        (self.root / "input-stimulus.json").write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            gate.verify(self.root, self.nonce, self.pid)
        receipt["commands"] = copy.deepcopy(gate.STIMULI)
        receipt["status"] = "FAILED_NO_REPLAY"
        (self.root / "input-stimulus.json").write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            gate.verify(self.root, self.nonce, self.pid)

    def test_symlink_ancestor_symlink_leaf_hard_link_and_unsafe_mode_are_refused(self):
        path = self.write(1, "up_accepted")
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            gate.load_private(alias, path.name, self.identity)
        path.rename(self.root / "original")
        path.symlink_to(self.root / "original")
        with self.assertRaises(ValueError):
            gate.load_private(self.root, path.name, self.identity)
        path.unlink()
        os.link(self.root / "original", path)
        with self.assertRaises(ValueError):
            gate.load_private(self.root, path.name, self.identity)
        path.unlink()
        (self.root / "original").rename(path)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            gate.load_private(self.root, path.name, self.identity)

    def test_bounded_strict_json_and_actual_mid_read_modification_are_refused(self):
        path = self.write(1, "up_accepted")
        for data in (b" " * (gate.MAX_BYTES + 1), b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}'):
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                gate.load_private(self.root, path.name, self.identity)
        self.write(1, "up_accepted")
        real_read = os.read
        def changed(descriptor, size):
            data = real_read(descriptor, size)
            with path.open("a") as stream:
                stream.write(" ")
            return data
        with patch.object(gate.os, "read", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed while"):
                gate.load_private(self.root, path.name, self.identity)

    def fixture_driver(self, timeout=1, *, missing_up=False, failed_up=False):
        fixture = self
        class FixtureDriver(gate.Driver):
            """Actual private-file callbacks simulated solely to test this host driver."""
            sequence = 0
            prelude = False
            chrome = False
            worker = None
            def command(self, arguments):
                self.remaining()
                if arguments == ["getwindowfocus"]:
                    return str(self.window)
                if arguments == ["getwindowpid", str(self.window)]:
                    return str(self.pid)
                if arguments[0] == "mousemove":
                    point = arguments[-2:]
                    if not self.prelude:
                        self.prelude = True
                        fixture.write(0, "prelude_ready")
                    elif point == ["10", "10"]:
                        self.chrome = True
                        fixture.write(0, "chrome_ready")
                    else:
                        self.sequence += 1
                        if self.sequence > 1:
                            assert (fixture.root / f"input-pair-{self.sequence - 1}-up_accepted.json").is_file()
                        fixture.write(self.sequence, "ready")
                elif arguments[0] == "mousedown" and self.sequence:
                    fixture.write(self.sequence, "down_accepted")
                elif arguments[0] == "mouseup" and self.sequence:
                    if missing_up:
                        return ""
                    value = fixture.record(self.sequence, "up_accepted")
                    if failed_up:
                        value["up_dispatch_accepted"] = False
                    if self.sequence == 1:
                        def delayed():
                            time.sleep(0.03)
                            fixture.write(1, "up_accepted", value)
                        self.worker = threading.Thread(target=delayed)
                        self.worker.start()
                    else:
                        fixture.write(self.sequence, "up_accepted", value)
                return ""
        return FixtureDriver(self.root, self.pid, 123, self.nonce, timeout)

    def test_driver_waits_for_matching_release_before_exactly_next_original_down(self):
        driver = self.fixture_driver()
        driver.run()
        driver.worker.join()
        self.assertEqual(driver.commands, gate.STIMULI)
        driver.receipt("HOST_STIMULUS_COMPLETE")
        gate.verify(self.root, self.nonce, self.pid)

    def test_missing_ack_uses_one_absolute_deadline_and_never_resends_down_or_cleanup_up(self):
        driver = self.fixture_driver(timeout=0.06, missing_up=True)
        with self.assertRaisesRegex(ValueError, "deadline"):
            driver.run()
        self.assertEqual(driver.commands, gate.STIMULI[:9])
        self.assertEqual(driver.sequence, 1)
        self.assertLess(time.monotonic() - driver.deadline, 0.1)

    def test_dispatch_failure_does_not_authorize_the_next_pair(self):
        driver = self.fixture_driver(failed_up=True)
        with self.assertRaisesRegex(ValueError, "matching accepted"):
            driver.run()
        driver.worker.join()
        self.assertEqual(driver.commands, gate.STIMULI[:9])
        self.assertEqual(driver.sequence, 1)

    def test_owner_incarnation_change_stops_before_any_new_stimulus(self):
        driver = self.fixture_driver()
        with patch.object(gate, "process_start", return_value=driver.start + 1):
            with self.assertRaisesRegex(ValueError, "incarnation"):
                driver.run()
        self.assertEqual(driver.commands, [])

    def test_current_owner_generation_cannot_reuse_an_already_published_checkpoint(self):
        self.write(1, "ready")
        with self.assertRaisesRegex(ValueError, "replay is refused"):
            self.fixture_driver()
        (self.root / "input-pair-1-ready.json").unlink()
        (self.root / "input-stimulus.json").symlink_to(self.root / "absent")
        with self.assertRaisesRegex(ValueError, "replay is refused"):
            self.fixture_driver()

    def test_foreign_window_or_lost_native_focus_receives_no_stimulus(self):
        for foreign in ("pid", "focus"):
            driver = self.fixture_driver()
            real_command = driver.command
            def bad(arguments):
                if (foreign == "pid" and arguments[0] == "getwindowpid") or (
                        foreign == "focus" and arguments[0] == "getwindowfocus"):
                    return "9999999"
                return real_command(arguments)
            with patch.object(driver, "command", side_effect=bad):
                with self.assertRaisesRegex(ValueError, "another process|lost actual X11 focus"):
                    driver.run()
            self.assertEqual(driver.commands, [])

    def test_changed_observed_checkpoint_stops_before_the_next_stimulus(self):
        driver = self.fixture_driver()
        driver.stimulus(gate.STIMULI[0])
        driver.wait(0, "prelude_ready")
        with (self.root / "input-pair-0-prelude_ready.json").open("a") as stream:
            stream.write(" ")
        with self.assertRaisesRegex(ValueError, "earlier"):
            driver.stimulus(gate.STIMULI[1])
        self.assertEqual(driver.commands, gate.STIMULI[:1])

    def test_receipt_publication_refuses_actual_root_replacement_and_foreign_leaf(self):
        driver = self.fixture_driver()
        (self.root / "input-stimulus.json").symlink_to(self.root / "outside")
        with self.assertRaises(FileExistsError):
            driver.receipt("FAILED_NO_REPLAY")
        self.assertFalse((self.root / "outside").exists())
        (self.root / "input-stimulus.json").unlink()
        real_open = os.open
        displaced = self.root.with_name(self.root.name + "-displaced")
        def replaced(path, flags, *args, **kwargs):
            descriptor = real_open(path, flags, *args, **kwargs)
            if path == driver.root and flags & os.O_DIRECTORY:
                self.root.rename(displaced)
                self.root.mkdir(mode=0o700)
            return descriptor
        try:
            with patch.object(gate.os, "open", side_effect=replaced):
                with self.assertRaisesRegex(ValueError, "root custody"):
                    driver.receipt("FAILED_NO_REPLAY")
            self.assertFalse((self.root / "input-stimulus.json").exists())
            self.assertFalse((displaced / "input-stimulus.json").exists())
        finally:
            displaced.rmdir()

    def test_source_both_normal_entrypoints_use_driver_and_keep_strict_evidence(self):
        workflow = (ROOT / ".github/workflows/servo-headed-runtime.yml").read_text()
        runner = (ROOT / "tools/run_servo_headed_runtime_gate.sh").read_text()
        normal = runner.split("step_run_runtime() {", 1)[1].split("step_enforce_evidence() {", 1)[0]
        for source in (workflow, normal):
            self.assertIn("native_input_checkpoints.py drive", source)
            self.assertNotIn("xdotool mousedown", source)
            self.assertIn("HEPTA_D0A02_INPUT_NONCE", source)
        for source in (workflow, runner.split("step_enforce_evidence() {", 1)[1]):
            self.assertIn("native_input_checkpoints.py verify", source)
            self.assertIn("initial['pointerDowns'] == 3", source)
            self.assertIn("report['native_ime_events'] > 0", source)
        negative = runner.split("step_run_held_gestures_v1() {", 1)[1].split("step_run_runtime() {", 1)[0]
        self.assertIn("environment.pop('HEPTA_D0A02_INPUT_NONCE', None)", negative)
        self.assertNotIn("['xdotool', 'mouseup'", negative)

    def test_native_checkpoint_callbacks_bind_actual_dispatch_and_current_owner(self):
        source = (ROOT / "experiments/servo-headed-runtime/src/main.rs").read_text()
        callback = source.split("    fn notify_input_event_handled(", 1)[1].split("    fn notify_crashed", 1)[0]
        self.assertIn("if let Some(state) = self.current()", callback)
        self.assertIn(".remove(&event_id)", callback)
        self.assertIn("if !acknowledged", callback)
        self.assertIn("button != Some(Button::Primary)", callback)
        self.assertIn("input.point()", callback)
        self.assertIn("input.window_focused()", callback)
        self.assertIn("input.button_ready(self.generation, Button::Primary)", callback)
        self.assertIn("!result.contains(InputEventResult::DispatchFailed)", callback)
        self.assertLess(callback.index("acknowledge_release("), callback.index("input.acknowledge("))
        drive = source.split("    fn drive(", 1)[1].split("    fn request_content_screenshot", 1)[0]
        self.assertEqual(drive.count("&& self.qualification_input_complete()"), 2)


if __name__ == "__main__":
    unittest.main()
