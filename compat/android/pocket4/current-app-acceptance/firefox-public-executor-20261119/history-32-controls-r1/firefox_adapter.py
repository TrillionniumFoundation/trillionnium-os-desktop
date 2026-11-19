"""Concrete adapter to the existing source-bound Main/Flow UI transport.

No subprocess or Android command is issued outside that transport. A reviewed
controller must supply the actual two flow scopes and a browser-session owner
capability. The latter is deliberately separate from an Android task claim:
the current generic ActionRunner does not implement browser ownership.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import time

from firefox_custody import APK_BYTES, APK_SHA256, PACKAGE, VERSION_CODE, need
from firefox_protocol import PAGES

FLOW_SHA = "926793aabf5610fc32f6b94bd772c660c7e24bc992641f8b2ca4ae257bfa59bb"
BASELINE_SHA = "0d26c720f2d349b97c192a2f18d7db9d62f5421944a50ae31d6499188e5bdcff"
UI_ENTRY_SHA = "c33e86290d835bdd6ed82f5994572025807846addf141e1253c0665398db48f6"
HELPER_APK = {"bytes": 20847, "sha256": "a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058"}
HELPER_PACKAGE = "local.pocket4.actions.v2"
ROLES = {"address", "url_editor", "url_go", "back", "forward", "new_tab", "close_tab",
         "page_url", "secure_indicator", "heading_manifesto", "heading_history"}
VIEW_KINDS = {"browser_toolbar", "browser_menu", "owned_public_content"}


def file_sha(path, limit=131072):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, "SOURCE_CANONICAL_PATH_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and 0 < first.st_size <= limit, "SOURCE_FILE_BOUND")
        body = os.read(fd, limit + 1)
        last = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        need(len(body) == first.st_size and all(getattr(first, k) == getattr(last, k)
             == getattr(path.lstat(), k) for k in fields), "SOURCE_CHANGED_DURING_BINDING")
        return hashlib.sha256(body).hexdigest()
    finally:
        os.close(fd)


def validate_selector_contract(value, binding):
    need(type(value) is dict and value.get("schema") == "p4-firefox-reviewed-selector-contract-v1"
         and value.get("package") == PACKAGE and value.get("apk") == binding["apk"]
         and value.get("reviewed_for_version_code") == VERSION_CODE,
         "CURRENT_FIREFOX_SOURCE_BOUND_SELECTORS_REQUIRED")
    need(type(value.get("roles")) is dict and set(value["roles"]) == ROLES,
         "COMPLETE_REVIEWED_PUBLIC_CONTROL_SET_REQUIRED")
    need(value.get("browser_history_or_tab_list_access") is False
         and value.get("selectors_are_runtime_observed") is True,
         "NO_GUESSED_SELECTORS_OR_USER_TAB_LIST_ROUTE")
    for role, item in value["roles"].items():
        need(type(item) is dict and set(item) == {"selector", "view_kind", "observation", "review", "value_field"}
             and item["view_kind"] in VIEW_KINDS and item["value_field"] in ("text", "value", "content-desc"),
             "EXACT_REVIEWED_SELECTOR_ORIGIN_REQUIRED:" + role)
        selector = item["selector"]
        need(type(selector) is dict and selector and set(selector) <= {"id", "text", "desc", "class", "enabled", "clickable", "editable"}
             and "class" in selector and all(type(v) is (bool if k in ("enabled", "clickable", "editable") else str)
                                             for k, v in selector.items()), "EXACT_NONPOSITIONAL_SELECTOR_REQUIRED")
        need(all(type(v) is not str or 0 < len(v.encode()) <= 512 for v in selector.values()),
             "BOUNDED_SELECTOR_REQUIRED")
        if role.startswith("heading_"):
            name = role.removeprefix("heading_")
            need(selector.get("text") == PAGES[name]["heading"] and item["view_kind"] == "owned_public_content",
                 "ONLY_EXACT_PUBLIC_HEADING_SELECTOR")
        else:
            need(item["view_kind"] in {"browser_toolbar", "browser_menu"}
                 and re.fullmatch(re.escape(PACKAGE) + r":id/[A-Za-z0-9_]+", selector.get("id", "")),
                 "BROWSER_CONTROL_NOT_PAGE_FORM_OR_TAB_LIST")
        need(type(item["observation"]) is dict and type(item["review"]) is dict,
             "ACTUAL_SELECTOR_OBSERVATION_AND_REVIEW_REFERENCES_REQUIRED")
    return value


def one_find(value, package=PACKAGE):
    """Wire fields verified from exact a536… APK / 548dc5… smali, not guessed."""
    need(type(value) is dict and value.get("ok") is True
         and value.get("accessibility_mode_restoration_verified") is True
         and value.get("outcome_unknown") is not True
         and type(value.get("count")) is int and value["count"] == 1
         and type(value.get("matches")) is list and len(value["matches"]) == 1,
         "ONE_ACTUAL_FIND_MATCH_WITH_RESTORATION_REQUIRED")
    node = value["matches"][0]
    need(type(node) is dict and node.get("package") == package and node.get("visible") is True
         and node.get("enabled") is True and node.get("password") is False
         and node.get("source") == "native_accessibility"
         and type(node.get("window_id")) is int and node["window_id"] >= 0,
         "VISIBLE_NONPASSWORD_CURRENT_FIREFOX_NODE_REQUIRED")
    need(type(value.get("window_context")) is dict, "REAL_NATIVE_WINDOW_CONTEXT_REQUIRED")
    return node


def verify_ui_parent_result(flow, step, output, request):
    """Verify the real recorder chain, following the existing Clock guard API."""
    common = flow.c
    step = Path(step)
    need(step.parent == Path(flow.scope["flow_root"]) / "steps", "OWNED_UI_STEP_REQUIRED")
    result = common.parse(common.regular(step / "command-001.result.json")[0])
    logical = common.parse(common.regular(step / "command-001.logical.json")[0])
    entry = flow.modules["business_ui_entry.py"]
    argv = entry.logical_argv(request, PACKAGE, step)
    need(logical == {"schema": "pocket4-final-ui-logical-command-v1", "scope_sha256": flow.scope_ref["sha256"],
         "argv": argv, "mutation": request["op"] in ("click", "set-text"),
         "label": "Existing android-app CLI", "automatic_retry": False},
         "EXACT_SOURCE_BOUND_UI_REQUEST_AND_SCOPE_REQUIRED")
    need(result.get("host_retirement_proved") is True and result.get("evidence_complete") is True
         and result.get("returncode") == 0 and result.get("timed_out") is False
         and result.get("errors") == [] and result.get("first_error") is None
         and result.get("argv") == entry.entry_argv(flow.scope_ref, "client", step.name, "command-001", argv[1:])
         and common.parse(common.read_ref(result["stdout"])) == output,
         "ACTUAL_TYPED_UI_PARENT_EXIT_AND_REAP_REQUIRED")
    common.read_ref(result["stderr"])
    flow.guard()
    return result


class FirefoxFlowAdapter:
    """Actual operations, requiring existing live controller capabilities.

    Controller obligations are checked before any UI/launch. `browser_owner`
    must be an implementation selected by the same reviewed task packet. It
    must verify tab IDs without enumerating user tabs/history. Its absence is
    an explicit admission failure; a JSON boolean/task ID is not a substitute.

    The controller creates ordinary Flow instances through `open_flow(index,
    phase)`, using StreamingCommon only for the exact Firefox APK. It keeps
    the original source/lease/action-lock/recorder guards. Selector observation
    and review refs are independently verified by `validate_selector_origin`.
    These capabilities are not supplied by the historical helper or this file.
    """
    def __init__(self, controller):
        self.c = controller
        self.flow = None
        self.index = 0
        self.calls = 0
        self.launch_attempts = 0
        self.actual_command_acks = 0
        self.mutation_attempts = 0
        self.binding = None
        self.selected = None
        self.owner = getattr(controller, "browser_owner", None)
        self.failed = False
        self.closed = False
        self.evidence = []

    def _guard(self):
        need(not self.closed and not self.failed, "FIREFOX_CASE_CLOSED_OR_POISONED")
        need(type(self.c.deadline) in (int, float) and time.monotonic() < self.c.deadline,
             "ORIGINAL_FIREFOX_CASE_DEADLINE_EXPIRED")
        current = self.c.baseline.guard()
        need(current == self.main_guard, "ACTUAL_MAIN_CHANGED_DURING_FIREFOX_CASE")
        self.c.verify_runtime_bindings(self.binding)
        self.owner.guard(self.binding)
        if self.flow is not None:
            self.flow.guard()
            self.flow.artifacts.verify()
            need(self.flow.scope["package"] == PACKAGE
                 and self.flow.scope["uid"] == self.binding["uid"]
                 and self.flow.scope["user"] == self.binding["user"]
                 and self.flow.scope["framework_epoch_sha256"] == self.binding["epoch"],
                 "CURRENT_FLOW_BINDING_CHANGED")

    def _open(self, phase):
        self._guard()
        if self.flow is not None:
            self.flow.artifacts.revalidate()
            self.flow.close()
            self.flow = None
        flow = self.c.open_flow(self.index, phase)
        try:
            need(type(flow).__name__ == "Flow" and file_sha(type(flow).__init__.__code__.co_filename) == FLOW_SHA,
                 "EXACT_ORIGINAL_HELD_FLOW_IMPLEMENTATION_REQUIRED")
            need(flow.phase == phase and flow.scope["package"] == PACKAGE,
                 "FIREFOX_FLOW_PHASE_CHANGED")
            flow.guard()
            self.flow = flow
            self._guard()
            entry = flow.modules["business_ui_entry.py"]
            need(file_sha(entry.__file__) == UI_ENTRY_SHA, "REVIEWED_TYPED_UI_ENTRY_COHORT_REQUIRED")
            # Check the original consumer verification now, before any launch.
            # A changed live CLI is not silently repinned to this old cohort.
            for ref in (entry.APP, entry.BACKEND):
                self.c.common.read_ref(ref)
            need(flow.helper_identities and any(row.get("metadata", {}).get("package") == HELPER_PACKAGE
                 and len(row.get("artifacts", [])) == 1
                 and {k: row["artifacts"][0][k] for k in ("bytes", "sha256")} == HELPER_APK
                 for row in flow.helper_identities), "ACTUAL_ORIGINAL_HELPER_APK_CUSTODY_REQUIRED")
            return flow
        except BaseException:
            flow.close()
            self.flow = None
            raise

    def _state(self):
        self._guard()
        selected = self.flow.selected_task()
        need(selected["prelaunch_absent"] is True and selected["cleanup_allowed"] is True,
             "ORIGINAL_EXACT_OWNED_TASK_CLAIM_REQUIRED")
        # This provider returns ONLY IDs already owned by this case, never all
        # browser tabs. It must independently prove ownership and unchanged
        # original user state in its reviewed source/receipt chain.
        value = self.owner.observe_owned(self.binding, selected)
        need(type(value) is dict and set(value) == {"session", "task", "tab", "owned_tabs",
             "browser_ownership_proved", "task_ownership_is_browser_ownership", "user_tab_enumeration", "user_history_read"},
             "ONLY_SCOPED_BROWSER_OWNERSHIP_METADATA_MAY_RETURN")
        need(value.get("session") == self.binding["session"] and value.get("task") == selected["task"]
             and value.get("browser_ownership_proved") is True
             and value.get("task_ownership_is_browser_ownership") is False
             and value.get("user_tab_enumeration") is False and value.get("user_history_read") is False,
             "BROWSER_OWNER_HAS_NOT_PROVED_CURRENT_OWNED_TAB_SET")
        need(type(value.get("owned_tabs")) is list and len(value["owned_tabs"]) <= 2
             and all(type(x) is str and 0 < len(x) <= 128 for x in value["owned_tabs"])
             and len(set(value["owned_tabs"])) == len(value["owned_tabs"]),
             "DISTINCT_BOUNDED_ALREADY_OWNED_TAB_IDS_REQUIRED")
        self.selected = selected
        return value

    def _result(self, **extra):
        return {"binding": self.binding, "evidence_complete": True, "outcome_unknown": False,
                "automatic_retry": False, "user_tab_enumeration": False, "user_history_read": False,
                **extra}

    def admit(self):
        need(os.getuid() == os.geteuid() == 0, "ROOT_CURRENT_FIREFOX_CONTROLLER_REQUIRED")
        need(self.owner is not None and not isinstance(self.owner, (dict, bool, int, str)),
             "BROWSER_SESSION_OWNERSHIP_PROVIDER_UNAVAILABLE")
        need(file_sha(type(self.c.baseline).guard.__code__.co_filename) == BASELINE_SHA,
             "ACTUAL_SOURCE_BOUND_BUSINESS_BASELINE_REQUIRED")
        # This is a controller-source review/admission, not a status boolean.
        self.c.verify_controller_source_and_owner_capability()
        self.main_guard = self.c.baseline.guard()
        self.binding = self.c.runtime_binding()
        need(type(self.binding) is dict and set(self.binding) == {"Main", "epoch", "package", "uid", "user",
             "apk", "version_code", "engine_mapping", "helper_custody", "session"},
             "COMPLETE_ACTUAL_FIREFOX_RUNTIME_BINDING_REQUIRED")
        b = self.binding
        need(b["package"] == PACKAGE and b["apk"] == {"bytes": APK_BYTES, "sha256": APK_SHA256}
             and b["version_code"] == VERSION_CODE and type(b["uid"]) is int and type(b["user"]) is int
             and b["user"] == 0 and self.c.baseline.value["data_continuity"]["package_uids"].get(PACKAGE) == b["uid"]
             and b["epoch"] == self.c.baseline.value["framework_epoch"]["sha256"]
             and b["Main"] == self.c.baseline.baseline_ref,
             "CURRENT_ACTUAL_MAIN_UID_USER_VERSION_AND_APK_REQUIRED")
        self.selectors = validate_selector_contract(self.c.selector_contract, b)
        for role, item in self.selectors["roles"].items():
            self.c.validate_selector_origin(role, item, b)
        self.owner.admit_without_user_state_reads(b)
        flow = self._open("launch")
        self.launch_attempts += 1
        self.mutation_attempts += 1
        launched = flow.launch()  # Original acquisition of the global action lock.
        need(launched.get("native_launch_acknowledged") is True, "ACTUAL_NATIVE_FIREFOX_LAUNCH_REQUIRED")
        self.actual_command_acks += 1
        self.owner.claim_initial_owned_tab(b, flow.selected_task())
        self._open("inspect")
        state = self._state()
        need(len(state["owned_tabs"]) == 1 and state.get("tab") == state["owned_tabs"][0],
             "ONE_ACTUAL_INITIAL_OWNED_TAB_REQUIRED")
        return self._result(**state)

    def _ui(self, op, role, value=None):
        self._guard()
        need(self.flow.phase == "inspect" and role in ROLES and op in ("find", "click", "set-text")
             and self.calls < 70, "FINITE_FIREFOX_UI_OPERATION_BOUND")
        state = self._state()
        self.owner.assert_ui_safe_without_enumeration(self.binding, state, role)
        selector = dict(self.selectors["roles"][role]["selector"])
        request = {"op": op, "selector": selector, "accessibility_mode": "none"}
        if op == "click":
            request["method"] = "accessibility"
        if op == "set-text":
            need(role == "url_editor" and value in {p["url"] for p in PAGES.values()},
                 "ONLY_TWO_PUBLIC_URL_INPUTS")
            request["value"] = value
        context = self.c.ui_context(self.flow, request, state)
        self.calls += 1
        if op in ("click", "set-text"):
            self.mutation_attempts += 1
        try:
            output, step = self.flow.ui(request, case_context=context)
            # The existing recorder's raw result, original PIDFD retirement,
            # held-entry post guard and exact helper response are mandatory.
            verify_ui_parent_result(self.flow, step, output, request)
            need(output.get("ok") is True and output.get("outcome_unknown") is not True
                 and output.get("accessibility_mode_restoration_verified") is True,
                 "ACTUAL_UI_ACTION_OR_RESTORATION_UNQUALIFIED")
            if op == "find":
                one_find(output)
            else:
                need(output.get("performed") == op, "ACTUAL_NATIVE_ACTION_ACK_REQUIRED")
                if op == "set-text":
                    need(output.get("password") is False and output.get("readback_verified") is True
                         and output.get("characters") == len(value), "EXACT_PUBLIC_URL_INPUT_READBACK_REQUIRED")
                else:
                    need(type(output.get("target")) is dict and type(output.get("actual_target")) is dict,
                         "ACTUAL_CLICK_TARGET_REQUIRED")
            self.owner.verify_ui_window(self.binding, state, output, request)
            self._guard()
            self.actual_command_acks += 1
            self.evidence.append({"op": op, "role": role, "step": str(step)})
            return output
        except BaseException as error:
            self.failed = True
            if op in ("click", "set-text"):
                error.outcome_unknown = True
            raise

    def _click(self, role):
        found = one_find(self._ui("find", role))
        need(found.get("clickable") is True and found.get("editable") is False,
             "FRESH_UNIQUE_NATIVE_CLICK_CONTROL_REQUIRED")
        result = self._ui("click", role)
        keys = ("resource-id", "text", "content-desc", "class", "package", "clickable", "editable", "password")
        try:
            need(all(tuple(n.get(k) for k in keys) == tuple(found.get(k) for k in keys)
                     for n in (result["target"], result["actual_target"])),
                 "FRESH_CLICK_TARGET_SEMANTICS_CHANGED")
        except BaseException as error:
            self.failed = True
            error.outcome_unknown = True
            raise
        return result

    def _page(self, name):
        state = self._state()
        url = one_find(self._ui("find", "page_url"))
        heading = one_find(self._ui("find", "heading_" + name))
        secure = one_find(self._ui("find", "secure_indicator"))
        need(url.get(self.selectors["roles"]["page_url"]["value_field"]) == PAGES[name]["url"]
             and heading.get("text") == PAGES[name]["heading"], "EXACT_CURRENT_PAGE_URL_AND_HEADING_REQUIRED")
        # A selector-review assertion alone cannot establish TLS. The owner
        # must validate the current browser-chrome security observation.
        self.owner.verify_normal_https_page(self.binding, state, url, secure)
        after = self._state()
        need(after == state, "OWNED_TAB_CHANGED_DURING_PAGE_OBSERVATION")
        return self._result(**state, url=PAGES[name]["url"], heading=PAGES[name]["heading"],
            heading_visible=True, normal_https_page=True, network_error=False, certificate_warning=False)

    def navigate(self, tab, name):
        need(name in PAGES and self._state().get("tab") == tab, "CURRENT_OWNED_TAB_ONLY")
        self._click("address")
        editor = one_find(self._ui("find", "url_editor"))
        need(editor.get("editable") is True, "ACTUAL_BROWSER_URL_EDITOR_REQUIRED")
        self._ui("set-text", "url_editor", PAGES[name]["url"])
        readback = one_find(self._ui("find", "url_editor"))
        need(readback.get(self.selectors["roles"]["url_editor"]["value_field"]) == PAGES[name]["url"],
             "INDEPENDENT_EXACT_URL_EDITOR_READBACK_REQUIRED")
        self._click("url_go")
        self.owner.wait_public_page(self.binding, self.flow, name, self.c.deadline)
        return self._page(name)

    def back(self, tab):
        need(self._state().get("tab") == tab, "BACK_ONLY_CURRENT_OWNED_TAB")
        self._click("back")
        self.owner.wait_public_page(self.binding, self.flow, "manifesto", self.c.deadline)
        return self._page("manifesto")

    def forward(self, tab):
        need(self._state().get("tab") == tab, "FORWARD_ONLY_CURRENT_OWNED_TAB")
        self._click("forward")
        self.owner.wait_public_page(self.binding, self.flow, "history", self.c.deadline)
        return self._page("history")

    def new_tab(self, name):
        before = self._state()
        need(len(before["owned_tabs"]) == 1 and name == "manifesto", "ONE_SECOND_OWNED_TAB_ONLY")
        self._click("new_tab")
        self.owner.record_second_created_tab(self.binding, before, self.evidence[-1])
        after = self._state()
        need(len(after["owned_tabs"]) == 2 and after["owned_tabs"][0] == before["tab"]
             and after["tab"] == after["owned_tabs"][1], "OBSERVED_NEW_OWNED_TAB_TRANSITION_REQUIRED")
        return self.navigate(after["tab"], name)

    def close_tab(self, tab):
        before = self._state()
        need(len(before["owned_tabs"]) == 2 and before["tab"] == tab == before["owned_tabs"][1],
             "ONLY_EXACT_SECOND_OWNED_TAB_MAY_CLOSE")
        self._click("close_tab")
        self.owner.record_closed_tab(self.binding, tab, self.evidence[-1])
        after = self._state()
        need(after["owned_tabs"] == [before["owned_tabs"][0]] and after["tab"] == after["owned_tabs"][0],
             "EXACT_SECOND_TAB_CLOSE_TRANSITION_REQUIRED")
        return self._page("history")

    def normal_close(self):
        before = self._state()
        self._open("cleanup")
        self.mutation_attempts += 1
        closed = self.flow.cleanup()
        need(closed.get("new_leaf_removed_and_verified") is True and closed.get("other_tasks_preserved") is True,
             "NORMAL_CLOSE_MUST_BE_AN_ACTUAL_OWNED_LEAF_REMOVAL")
        self.owner.record_normal_task_close(self.binding, before, closed)
        self.flow.artifacts.revalidate()
        self.flow.close()
        self.flow = None
        return self._result(closed_task=before["task"], owned_task_absent=True, other_tasks_preserved=True,
                            normal_task_close=True, force_stop=False, clear_data=False)

    def reopen(self):
        need(self.index == 0 and self.flow is None, "ONCE_ONLY_INDEPENDENT_REOPEN_REQUIRED")
        self.index = 1
        flow = self._open("launch")
        self.launch_attempts += 1
        self.mutation_attempts += 1
        launched = flow.launch()
        need(launched.get("native_launch_acknowledged") is True, "ACTUAL_REOPEN_NATIVE_ACK_REQUIRED")
        self.actual_command_acks += 1
        self.owner.record_independent_reopen(self.binding, flow.selected_task())
        self._open("inspect")
        value = self._page("history")
        value["independent_launch"] = True
        return value

    def cleanup(self):
        before = self._state()
        need(self.index == 1 and len(before["owned_tabs"]) == 1, "FINAL_EXACT_OWNED_TAB_ONLY")
        self._click("close_tab")
        self.owner.record_closed_tab(self.binding, before["tab"], self.evidence[-1])
        empty = self._state()
        need(empty["owned_tabs"] == [], "NO_OWNED_TABS_REMAIN_REQUIRED")
        result = self.normal_close()
        result["owned_tabs"] = []
        return result

    def close_resources(self):
        self.closed = True
        if self.flow is not None:
            flow, self.flow = self.flow, None
            flow.close()
        # The controller retains a failed Android claim for reconciliation;
        # closing host descriptors never manufactures guest cleanup credit.
        self.c.release_host_resources()
        return True
