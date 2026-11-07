#!/usr/bin/env python3
"""Exercise real controller/adapter methods with saved native nodes and bounded protocol fixtures.

No Android commands are run. Synthetic action replies test only controller safety;
they are never evidence that Gallery controls or playback worked on the device.
"""
from pathlib import Path
import base64
import copy
import hashlib
import importlib.util
import json
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def module(name, path, expected):
    raw = path.read_bytes()
    assert digest(raw) == expected, (name, "source changed")
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), result.__dict__)
    return result


controller = module("gallery04_boundaries", HERE / "run_video01.py",
                    "7d3e8e81c36eb18a4d0f1c46c23e37ec2ba657fc885f2e5197cfb730c4657d26")
adapter = module("actual_android_adapter", ROOT / "camera-accept08/reference/android-app.py",
                 "eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66")
saved_path = HERE.parent / "revision03/saved-export-original.json"
saved_raw = saved_path.read_bytes()
assert digest(saved_raw) == "3e631e8c9cf613d47b97f67819275300542534f056a395fdb8b03f6ec0ce70f6"
saved = json.loads(saved_raw)["ui_records"]["051-pause-control-observation-0.json"]["value"]["native"]
VIDEO = next(n for n in saved["nodes"] if n["class"] == "android.widget.VideoView")
FOCUS = {"package": controller.GALLERY, "activity": controller.MOVIE,
         "focused_activity": controller.MOVIE, "window_token": "2448f5b", "task": 960}
Flow = controller.make_class(types.SimpleNamespace(Gallery=object))
results = []


def button(label):
    return {"package": controller.GALLERY, "class": "android.widget.ImageView",
            "content-desc": label, "visible": True, "enabled": True, "clickable": True,
            "bounds_array": [850, 680, 990, 820], "resource-id": "",
            "window_id": VIDEO["window_id"]}


def scene(label=None):
    result = copy.deepcopy(saved)
    if label:
        result["nodes"].append(button(label))
    return result


def ack(target=VIDEO, method="mouse"):
    value = {"ok": True, "performed": "click", "method": method,
             "source": "native_bounds_mouse" if method == "mouse" else "native_accessibility",
             "target": copy.deepcopy(target), "actual_target": copy.deepcopy(target),
             "visual_verified": False, "business_success_verified": False,
             "accessibility_mode_restoration_verified": True}
    if method == "mouse":
        b = target["bounds_array"]
        value["coordinates"] = [(b[0] + b[2]) // 2, (b[1] + b[3]) // 2]
    return value


class Harness:
    def __init__(self, before=None, after=None, response=None):
        self.before = copy.deepcopy(saved if before is None else before)
        self.after = copy.deepcopy(scene("Pause") if after is None else after)
        self.response = copy.deepcopy(ack() if response is None else response)
        self.requests = []
        self.mutations = []
        self.focus_changes_after = False
        self.foreign_before = False
        self.forbid_focus = False
        flow = Flow.__new__(Flow)
        self.flow = flow
        flow.s = types.SimpleNamespace(helper=adapter, guard=lambda: None)
        flow.ui = types.SimpleNamespace(ready_focus=lambda unused: self.focus(),
                                        focus=lambda unused: self.focus(),
                                        focus_allowed=lambda value, unused: not self.forbid_focus)
        flow.pending = None
        flow.inputs = 0
        flow.result = {"inputs": []}
        flow.record = lambda label, value: None
        adapter.arun = self.arun
        adapter.capture = self.no_capture
        adapter.dispatch = self.no_capture

    @staticmethod
    def no_capture(*args, **kwargs):
        raise AssertionError("semantic path must not use snapshot or dispatch")

    def focus(self):
        value = copy.deepcopy(FOCUS)
        if self.foreign_before:
            value["package"] = "unrelated.package"
        if self.focus_changes_after and self.mutations:
            value["window_token"] = "different-window"
            value["task"] = 961
        return value

    def arun(self, argv, timeout):
        assert argv[:5] == ["/system/bin/am", "instrument", "-w", "-r", "-e"]
        assert argv[-1] == "local.pocket4.actions.v2/.ActionRunner"
        request = json.loads(base64.b64decode(argv[6]))
        self.requests.append(request)
        if request["op"] == "dump":
            reply = self.after if self.mutations else self.before
        else:
            assert request["op"] == "click"
            self.mutations.append(request)
            reply = self.response
            if isinstance(reply, BaseException):
                raise reply
        encoded = base64.b64encode(json.dumps(reply).encode()).decode()
        return ("INSTRUMENTATION_RESULT: sidecar_result_base64=" + encoded + "\n"
                "INSTRUMENTATION_CODE: 0\n").encode()


def check(name, harness, effect, expect_error=None, count=0, pending=False):
    error = None
    try:
        effect(harness.flow)
    except BaseException as exc:
        error = str(exc)
    if expect_error:
        assert error == expect_error, (name, error, expect_error)
    else:
        assert error is None, (name, error)
    assert len(harness.mutations) == count, (name, "input count", harness.mutations)
    assert bool(harness.flow.pending) is pending, (name, "pending", harness.flow.pending)
    if pending:
        assert harness.flow.result["inputs"] == [], (name, "unverified action was credited")
    for request in harness.mutations:
        assert "index" not in request and "coords" not in request
        assert request["expected_package"] == controller.GALLERY
    results.append({"case": name, "passed": True, "synthetic_native_mutation_requests": count,
                    "pending_retained": pending, "expected_error": expect_error})


check("saved_actual03_native_schema", Harness(), lambda f: f.native_controls("saved"))
check("single_native_mouse_then_fresh_pause", Harness(), lambda f: f.ensure_controls(), count=1)
check("already_visible_pause_requires_no_show_input", Harness(before=scene("Pause")), lambda f: f.ensure_controls())

bad = scene(); bad["nodes"].append(copy.deepcopy(VIDEO))
check("duplicate_video_blocks_before_input", Harness(before=bad), lambda f: f.ensure_controls(),
      "UNIQUE_OBSERVED_NATIVE_VIDEO_VIEW_REQUIRED")
bad = scene(); bad["window_context"]["snapshot_complete"] = False
check("incomplete_tree_blocks_before_input", Harness(before=bad), lambda f: f.ensure_controls(),
      "NATIVE_CONTROL_SCOPE_INCOMPLETE")
bad = scene(); bad["window_context"]["selected_window"]["display_id"] = 1
check("wrong_display_blocks_before_input", Harness(before=bad), lambda f: f.ensure_controls(),
      "NATIVE_CONTROL_SCOPE_INCOMPLETE")
bad = scene(); bad["window_context"]["root"]["window_id"] += 1
check("mismatched_native_window_blocks_before_input", Harness(before=bad), lambda f: f.ensure_controls(),
      "NATIVE_CONTROL_SCOPE_INCOMPLETE")
bad = scene(); bad["nodes"][-1]["bounds_array"][0] = 0
check("out_of_window_video_bounds_block_before_input", Harness(before=bad), lambda f: f.ensure_controls(),
      "NATIVE_VIDEO_VIEW_OUTSIDE_OWNED_WINDOW")
h = Harness(); h.foreign_before = True
check("foreign_activity_blocks_before_input", h, lambda f: f.ensure_controls(), "EXACT_MOVIE_FOCUS_REQUIRED")
h = Harness(); h.forbid_focus = True
check("unowned_task_blocks_before_input", h, lambda f: f.ensure_controls(), "NATIVE_CONTROL_WINDOW_CHANGED")

failure = {"ok": False, "error": "AMBIGUOUS_MATCH", "outcome_unknown": False,
           "automatic_retry": False, "accessibility_mode_restoration_verified": True}
check("native_definite_no_effect_not_retried", Harness(response=failure), lambda f: f.ensure_controls(),
      "AMBIGUOUS_MATCH", count=1)
failure["error"] = "MOUSE_INPUT_MAY_HAVE_OCCURRED"; failure["outcome_unknown"] = True
check("native_unknown_is_retained_without_replay", Harness(response=failure), lambda f: f.ensure_controls(),
      "MOUSE_INPUT_MAY_HAVE_OCCURRED", count=1, pending=True)
check("transport_unknown_is_retained_without_replay", Harness(response=OSError("simulated transport")),
      lambda f: f.ensure_controls(), "UI_RUNNER_TRANSPORT_ERROR", count=1, pending=True)
bad = ack(); bad["accessibility_mode_restoration_verified"] = False
check("restoration_unknown_blocks_credit", Harness(response=bad), lambda f: f.ensure_controls(),
      "ACCESSIBILITY_MODE_RESTORATION_UNVERIFIED", count=1, pending=True)
bad = ack(); bad["coordinates"][0] += 1
check("wrong_returned_mouse_center_blocks_credit", Harness(response=bad), lambda f: f.ensure_controls(),
      "NATIVE_MOUSE_RECEIPT_NOT_JOINED", count=1, pending=True)
check("ack_without_visible_pause_is_not_success", Harness(after=scene()), lambda f: f.ensure_controls(),
      "PLAYING_CONTROL_NOT_OBSERVED_AFTER_NATIVE_SHOW", count=1, pending=True)
h = Harness(); h.focus_changes_after = True
check("post_action_window_change_retains_pending", h, lambda f: f.ensure_controls(),
      "PLAYING_CONTROL_NOT_OBSERVED_AFTER_NATIVE_SHOW", count=1, pending=True)
bad = scene("Pause"); bad["nodes"].append(button("Pause"))
check("duplicate_post_action_pause_retains_pending", Harness(after=bad), lambda f: f.ensure_controls(),
      "PLAYBACK_CONTROL_AMBIGUOUS", count=1, pending=True)

for before, after, label in [("Pause", "Play", "pause"), ("Play", "Pause", "resume")]:
    check("semantic_" + label + "_requires_actual_state_control", Harness(after=scene(after), response=ack(button(before), "accessibility")),
          lambda f, b=before, a=after, label=label: f.click_control(label, FOCUS, button(b), {a}), count=1)
check("semantic_pause_ack_without_state_change_is_not_success", Harness(after=scene("Pause"), response=ack(button("Pause"), "accessibility")),
      lambda f: f.click_control("pause", FOCUS, button("Pause"), {"Play"}),
      "PLAYBACK_STATE_CONTROL_NOT_CHANGED", count=1, pending=True)
h = Harness(); h.flow.inputs = controller.MAX_INPUTS
check("exhausted_input_budget_blocks_mutation", h, lambda f: f.ensure_controls(), "INPUT_SCOPE_OR_BUDGET")

value = {"schema": "gallery-native-controls04-local-boundaries/v1", "state": "LOCAL_BOUNDARIES_PASSED",
         "controller_sha256": digest((HERE / "run_video01.py").read_bytes()),
         "actual_adapter_sha256": digest((ROOT / "camera-accept08/reference/android-app.py").read_bytes()),
         "actual_saved_export_sha256": digest(saved_raw),
         "source_sha256": digest(Path(__file__).read_bytes()), "passed": len(results), "cases": results,
         "actual_new_Android_commands": 0, "actual_new_UI_inputs": 0,
         "synthetic_protocol_replies_are_not_business_evidence": True,
         "actual_Gallery_controls_qualified": False, "whole_app_production_ready": False}
output = HERE / "NATIVE_CONTROL_BOUNDARIES.json"
with output.open("x") as stream:
    stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
print(json.dumps({"passed": len(results), "result": str(output), "sha256": digest(output.read_bytes())}))
