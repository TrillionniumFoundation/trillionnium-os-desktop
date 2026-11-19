"""An executable public-page sequence. No browser or filesystem I/O at import.

The production adapter performs the real held-Flow commands. Offline doubles
exercise protocol decisions only, and cannot issue an application acceptance.
"""
from firefox_custody import Refused, need, PACKAGE, APK_BYTES, APK_SHA256, VERSION_CODE

PAGES = {
    "manifesto": {"url": "https://www.mozilla.org/en-US/about/manifesto/", "heading": "The Mozilla Manifesto"},
    "history": {"url": "https://www.mozilla.org/en-US/about/history/", "heading": "History of the Mozilla Project"},
}
STEPS = ("admit_owned_session", "open_manifesto", "open_history_same_tab", "back", "forward",
         "open_second_owned_tab", "close_second_owned_tab", "normal_close_owned_task",
         "independent_reopen_owned_task", "owned_cleanup")


def no_release_credit():
    return {"runtime_qualified": False, "native_compatibility_qualified": False,
            "business_qualified": False, "whole_app_business_accepted": False,
            "production_ready": False, "all_39_runtime_accepted": False,
            "all_39_latest_qualified": False}


def same_binding(value, binding):
    need(type(value) is dict and value.get("binding") == binding,
         "CURRENT_MAIN_UID_USER_EPOCH_APK_HELPER_BINDING_CHANGED")
    need(value.get("evidence_complete") is True and value.get("outcome_unknown") is False
         and value.get("automatic_retry") is False, "ACTUAL_COMPLETE_NONREPLAYED_OBSERVATION_REQUIRED")


def page(value, binding, expected, task, tab, owned):
    same_binding(value, binding)
    need(value.get("task") == task and value.get("tab") == tab
         and value.get("owned_tabs") == owned and value.get("session") == binding["session"],
         "EXACT_OWNED_BROWSER_SESSION_TASK_AND_TAB_REQUIRED")
    need(value.get("url") == PAGES[expected]["url"] and value.get("heading") == PAGES[expected]["heading"]
         and value.get("heading_visible") is True and value.get("normal_https_page") is True
         and value.get("network_error") is False and value.get("certificate_warning") is False,
         "EXACT_VISIBLE_PUBLIC_HTTPS_PAGE_REQUIRED")
    need(value.get("user_tab_enumeration") is False and value.get("user_history_read") is False,
         "PUBLIC_ONLY_OBSERVATION_BOUNDARY")
    return value


def _sequence(adapter, *, offline):
    """Run once. Any error stops dispatch; cleanup is never retried blindly."""
    result = {"schema": "p4-firefox-public-execution-v1", "package": PACKAGE,
              "state": "FAILED", "steps": [], "finite_public_case_passed": False,
              "error": None, "automatic_retry": False, "cleanup_completed": False,
              "remaining_common_gates": ["stability/soak", "data preservation", "release review"],
              "offline_control": offline, "Android_execution_observed": False,
              "protocol_control_passed": False,
              **no_release_credit()}
    phase = "admit_owned_session"
    try:
        admitted = adapter.admit()
        binding = admitted["binding"]
        need(binding["package"] == PACKAGE and binding["version_code"] == VERSION_CODE
             and binding["apk"] == {"bytes": APK_BYTES, "sha256": APK_SHA256},
             "CURRENT_SELECTED_FIREFOX_SOURCE_REQUIRED")
        same_binding(admitted, binding)
        need(admitted.get("browser_ownership_proved") is True
             and admitted.get("task_ownership_is_browser_ownership") is False
             and admitted.get("user_tab_enumeration") is False and admitted.get("user_history_read") is False,
             "INDEPENDENT_BROWSER_SESSION_OWNERSHIP_REQUIRED")
        task, first = admitted["task"], admitted["tab"]
        need(type(task) is int and task > 0 and type(first) is str and first
             and admitted.get("owned_tabs") == [first], "ONE_FRESH_OWNED_INITIAL_TAB_REQUIRED")
        result["steps"].append({"id": phase, "evidence": admitted})

        def observe(step, operation, name, current_task=task, current_tab=first, tabs=None):
            nonlocal phase
            phase = step
            value = operation()
            page(value, binding, name, current_task, current_tab, [first] if tabs is None else tabs)
            result["steps"].append({"id": step, "evidence": value})
            return value

        observe("open_manifesto", lambda: adapter.navigate(first, "manifesto"), "manifesto")
        observe("open_history_same_tab", lambda: adapter.navigate(first, "history"), "history")
        observe("back", lambda: adapter.back(first), "manifesto")
        observe("forward", lambda: adapter.forward(first), "history")
        phase = "open_second_owned_tab"
        second_observation = adapter.new_tab("manifesto")
        second = second_observation.get("tab")
        need(type(second) is str and second and second != first, "DISTINCT_ACTUALLY_CREATED_SECOND_TAB_REQUIRED")
        page(second_observation, binding, "manifesto", task, second, [first, second])
        result["steps"].append({"id": phase, "evidence": second_observation})
        observe("close_second_owned_tab", lambda: adapter.close_tab(second), "history")
        phase = "normal_close_owned_task"
        closed = adapter.normal_close()
        same_binding(closed, binding)
        need(closed.get("closed_task") == task and closed.get("owned_task_absent") is True
             and closed.get("other_tasks_preserved") is True and closed.get("normal_task_close") is True
             and closed.get("force_stop") is False and closed.get("clear_data") is False,
             "EXACT_NORMAL_OWNED_TASK_CLOSE_REQUIRED")
        result["steps"].append({"id": phase, "evidence": closed})
        phase = "independent_reopen_owned_task"
        reopened = adapter.reopen()
        next_task = reopened.get("task")
        need(type(next_task) is int and next_task > 0 and next_task != task
             and reopened.get("independent_launch") is True, "DISTINCT_REAL_REOPEN_REQUIRED")
        page(reopened, binding, "history", next_task, first, [first])
        result["steps"].append({"id": phase, "evidence": reopened})
        phase = "owned_cleanup"
        cleaned = adapter.cleanup()
        same_binding(cleaned, binding)
        need(cleaned.get("closed_task") == next_task and cleaned.get("owned_tabs") == []
             and cleaned.get("owned_task_absent") is True and cleaned.get("other_tasks_preserved") is True
             and cleaned.get("user_tab_enumeration") is False and cleaned.get("user_history_read") is False
             and cleaned.get("force_stop") is False and cleaned.get("clear_data") is False,
             "EXACT_OWNED_FINAL_CLEANUP_REQUIRED")
        result["steps"].append({"id": phase, "evidence": cleaned})
        need(tuple(x["id"] for x in result["steps"]) == STEPS, "COMPLETE_ORDERED_PUBLIC_SEQUENCE_REQUIRED")
        result.update(state="OFFLINE_PROTOCOL_CONTROL_PASSED" if offline else "FINITE_PUBLIC_CASE_OBSERVED",
                      finite_public_case_passed=not offline, cleanup_completed=not offline,
                      protocol_control_passed=offline, Android_execution_observed=not offline)
    except BaseException as error:
        result["error"] = {"phase": phase, "type": type(error).__name__, "message": str(error)}
        result["state"] = "UNKNOWN" if getattr(error, "outcome_unknown", False) else "FAILED"
    finally:
        result["Android_execution_observed"] = not offline and getattr(adapter, "actual_command_acks", 0) > 0
        result["UI_command_attempts"] = 0 if offline else getattr(adapter, "calls", 0)
        result["native_launch_attempts"] = 0 if offline else getattr(adapter, "launch_attempts", 0)
        result["Android_mutation_attempts"] = 0 if offline else getattr(adapter, "mutation_attempts", 0)
        # Resource release is distinct from an additional Android action.
        try:
            result["host_resources_released"] = adapter.close_resources()
            need(result["host_resources_released"] is True, "ACTUAL_HOST_RESOURCE_RELEASE_REQUIRED")
        except BaseException as error:
            result["state"] = "UNKNOWN"
            result["finite_public_case_passed"] = False
            result["protocol_control_passed"] = False
            result["resource_error"] = {"type": type(error).__name__, "message": str(error)}
    return result


def execute(adapter):
    """Held until actual controller/browser-owner implementations are bound."""
    from firefox_adapter import FirefoxFlowAdapter, require_frozen_runtime_implementations
    require_frozen_runtime_implementations()
    need(type(adapter) is FirefoxFlowAdapter, "ACTUAL_FLOW_ADAPTER_REQUIRED")
    return _sequence(adapter, offline=False)


def offline_control(adapter):
    """Host contract controls always retain zero Android/application credit."""
    return _sequence(adapter, offline=True)
