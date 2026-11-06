package org.droidloom.qa.successor.p8f89f253350ba2fa.r1;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Instrumentation;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.ResolveInfo;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Build;
import android.os.Process;
import android.os.SystemClock;
import android.util.Base64;
import android.util.SparseArray;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import android.app.UiAutomation;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;
import java.util.zip.GZIPOutputStream;
import org.json.JSONArray;
import org.json.JSONObject;

/** An owned self-instrumentation; it never instruments the commercial app. */
public final class ActionRunner extends Instrumentation {
    static final String PROTOCOL = "pocket4-owned-successor-qa-v1";
    static final String PACKAGE = "com.lianjia.beike";
    static final String SELF = "org.droidloom.qa.successor.p8f89f253350ba2fa.r1";
    static final String MAIN_EPOCH = "7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c";
    static final String MAIN_BASELINE_SCHEMA = "pocket4-successor-runtime-baseline-v1";
    static final String MAIN_BASELINE_SHA = "7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8";
    static final String MAIN_BASELINE_QUALIFICATION_SHA = "4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6";
    static final String RUNTIME_EPOCH = "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9";
    static final String APP_SCOPE_SHA = "2f3ed55a035e64401189cd2afbaded2414c7b0b9a3c641a82308a1c68b96a8eb";
    static final int TARGET_UID = 10143;
    static final int MAX_REQUEST = 16384, MAX_RESULT = 524288, MAX_COMPRESSED_WIRE = 262144;
    static final int MAX_NODES = 512, MAX_DEPTH = 32, MAX_CHILDREN = 64;
    static final String PUBLIC_SEARCH_QUERY = "\u5317\u4eac";
    static final long DEADLINE_MS = 8000, WATCHDOG_MS = 12000, MAX_INSPECTION_AGE_MS = 10000;
    static final long WINDOW_WAIT_MS = 2000;
    static final long WINDOW_RECHECK_MS = 100;
    static final int MAX_WINDOW_QUERIES = 64;
    private Bundle arguments;
    private volatile boolean finished;
    private long started;
    private boolean actionAttempted;
    private UiAutomation automation;
    private Method publicCacheClearMethod;
    private int originalFlags, originalCapabilities;
    private boolean originalServiceInfoCaptured;
    private final JSONObject restoration = new JSONObject();
    private final Object windowEvents = new Object();
    private long windowEventSerial;
    private JSONObject windowObservation = new JSONObject();
    private final JSONArray treeObservations = new JSONArray();
    private JSONObject currentTreeObservation;
    private InspectionIdleGate.Observation inspectionIdle;

    static final class Rejected extends Exception {
        Rejected(String code) { super(code); }
    }
    static void need(boolean value, String code) throws Rejected {
        if (!value) throw new Rejected(code);
    }
    static String hash(byte[] value) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(value);
        StringBuilder out = new StringBuilder(64);
        for (byte item : digest) out.append(String.format(java.util.Locale.ROOT, "%02x", item & 255));
        return out.toString();
    }
    static String hashJson(Object value) throws Exception { return hash(canonical(value).getBytes(StandardCharsets.UTF_8)); }
    static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        final char[] digits = "0123456789abcdef".toCharArray();
        for (int n = 0; n < value.length(); n++) {
            char c = value.charAt(n);
            switch (c) {
                case '"': out.append("\\\""); break;
                case '\\': out.append("\\\\"); break;
                case '\b': out.append("\\b"); break;
                case '\f': out.append("\\f"); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 32 || c > 126) {
                        out.append("\\u");
                        for (int shift = 12; shift >= 0; shift -= 4) out.append(digits[(c >> shift) & 15]);
                    } else out.append(c);
            }
        }
        return out.append('"').toString();
    }
    static String canonical(Object value) throws Exception {
        if (value == null || value == JSONObject.NULL) return "null";
        if (value instanceof String) return quote((String) value);
        if (value instanceof Boolean || value instanceof Integer || value instanceof Long) return value.toString();
        StringBuilder out = new StringBuilder();
        if (value instanceof JSONArray) {
            JSONArray list = (JSONArray) value; out.append('[');
            for (int n = 0; n < list.length(); n++) { if (n > 0) out.append(','); out.append(canonical(list.get(n))); }
            return out.append(']').toString();
        }
        need(value instanceof JSONObject, "UNSUPPORTED_JSON_VALUE");
        JSONObject object = (JSONObject) value;
        List<String> keys = new ArrayList<String>();
        for (Iterator<String> it = object.keys(); it.hasNext();) keys.add(it.next());
        Collections.sort(keys); out.append('{');
        for (int n = 0; n < keys.size(); n++) {
            if (n > 0) out.append(','); String key = keys.get(n);
            out.append(quote(key)).append(':').append(canonical(object.get(key)));
        }
        return out.append('}').toString();
    }
    static void keys(JSONObject value, String... names) throws Exception {
        Set<String> actual = new HashSet<String>();
        for (Iterator<String> it = value.keys(); it.hasNext();) actual.add(it.next());
        need(actual.equals(new HashSet<String>(Arrays.asList(names))), "EXACT_REQUEST_KEYS_REQUIRED");
    }
    static String string(JSONObject value, String name, int maximum) throws Exception {
        Object raw = value.get(name); need(raw instanceof String, "STRING_REQUIRED");
        String text = (String) raw;
        need(text.getBytes(StandardCharsets.UTF_8).length <= maximum && text.indexOf('\0') < 0,
             "STRING_BOUND_OR_NUL");
        return text;
    }
    static long integer(JSONObject value, String name) throws Exception {
        Object raw = value.get(name);
        need(raw instanceof Integer || raw instanceof Long, "INTEGER_REQUIRED");
        return ((Number) raw).longValue();
    }
    void timeBound() throws Exception { need(SystemClock.elapsedRealtime() - started <= DEADLINE_MS, "OWNED_DEADLINE"); }

    @Override public void onCreate(Bundle args) {
        super.onCreate(args); arguments = args; start();
    }

    @Override public void onStart() {
        started = SystemClock.elapsedRealtime();
        Thread watchdog = new Thread(new Runnable() {
            @Override public void run() {
                while (!finished && SystemClock.elapsedRealtime() - started < WATCHDOG_MS) SystemClock.sleep(50);
                if (!finished) Process.killProcess(Process.myPid());
            }
        }, "owned-qa-watchdog");
        watchdog.setDaemon(true); watchdog.start();
        JSONObject result = new JSONObject();
        String nonce = null;
        boolean claimed = false;
        Exception primary = null;
        JSONArray secondary = new JSONArray();
        try {
            need(arguments != null && arguments.keySet().equals(Collections.singleton("request")), "ONLY_REQUEST_ARGUMENT_ALLOWED");
            String encoded = arguments.getString("request");
            need(encoded != null && encoded.length() <= 4 * ((MAX_REQUEST + 2) / 3), "REQUEST_BASE64_BOUND");
            byte[] raw = Base64.decode(encoded, Base64.NO_WRAP);
            need(raw.length > 0 && raw.length <= MAX_REQUEST && Base64.encodeToString(raw, Base64.NO_WRAP).equals(encoded), "CANONICAL_BASE64_REQUIRED");
            JSONObject request = new JSONObject(new String(raw, StandardCharsets.UTF_8));
            need(Arrays.equals(canonical(request).getBytes(StandardCharsets.UTF_8), raw), "CANONICAL_JSON_REQUIRED");
            String op = string(request, "op", 16);
            need(Arrays.asList("state", "inspect", "click", "set_text").contains(op), "COMPILED_OPERATION_POLICY");
            if (op.equals("state")) keys(request, "protocol", "nonce", "op");
            else if (op.equals("inspect")) keys(request, "protocol", "nonce", "op", "scope");
            else if (op.equals("click")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "node_path", "node_sha256");
            else if (op.equals("reveal_controls")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "player_scope_sha256", "viewport_bounds");
            else if (op.equals("player_button")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "transition", "player_frame_sha256");
            else if (op.equals("set_text")) {
                keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "node_path", "node_sha256", "node_resource_id", "value");
                need(PUBLIC_SEARCH_QUERY.equals(string(request, "value", 64)), "ONLY_FIXED_PUBLIC_SEARCH_QUERY_ALLOWED");
                need(string(request, "node_resource_id", 256).matches("com\\.lianjia\\.beike:id/[A-Za-z0-9_]+"), "EXACT_EDIT_RESOURCE_REQUIRED");
            }
            else throw new Rejected("UNSUPPORTED_OPERATION");
            need(PROTOCOL.equals(string(request, "protocol", 64)), "PROTOCOL_MISMATCH");
            nonce = string(request, "nonce", 32);
            need(nonce.matches("[0-9a-f]{32}"), "EXACT_NONCE_REQUIRED");
            need(SELF.equals(getContext().getPackageName()) && SELF.equals(getTargetContext().getPackageName()), "SELF_INSTRUMENTATION_REQUIRED");
            need(Process.myUid() / 100000 == 0, "USER_ZERO_REQUIRED");
            result.put("protocol", PROTOCOL).put("nonce", nonce).put("op", op).put("request_sha256", hash(raw))
                .put("wire_codec", "gzip-canonical-json-v1");
            result.put("self_uid", Process.myUid()).put("self_pid", Process.myPid()).put("started_elapsed_ms", started);
            writeNew(nonce + ".claim.json", canonical(request).getBytes(StandardCharsets.UTF_8));
            claimed = true;
            if (op.equals("state")) {
                // No getUiAutomation call, so this operation creates no accessibility connection.
                result.put("state", accessibilityState()).put("ui_automation_connected", false);
            } else {
                JSONObject scope = request.getJSONObject("scope"); validateScope(scope);
                result.put("host_scope_attestation", scope).put("activity_verified_inside_helper", false);
                result.put("target_uid_verified", TARGET_UID);
                result.put("accessibility_state_before_connection", accessibilityState());
                connect();
                if (op.equals("inspect")) {
                    waitForInspectionIdle();
                    Capture captured = inspect(null, "inspection");
                    try { result.put("inspection", captured.json); }
                    finally { captured.close(); }
                } else if (op.equals("reveal_controls")) revealControls(request, result);
                else if (op.equals("player_button")) playerButton(request, result);
                else act(request, result);
            }
        } catch (Exception error) { primary = error; }
        finally {
            try { restoreOwnServiceInfo(); }
            catch (Exception error) { if (primary == null) primary = error; else secondary.put(errorCode(error)); }
            try { if (automation != null) automation.setOnAccessibilityEventListener(null); }
            catch (Exception error) { if (primary == null) primary = error; else secondary.put(errorCode(error)); }
        }
        try {
            // False means the complete write/sync/close did not finish; it does not
            // assert that no claim file exists after an I/O failure.
            result.put("claim_persistence_completed", claimed).put("action_attempted", actionAttempted);
            result.put("ok", primary == null).put("error", primary == null ? JSONObject.NULL : errorCode(primary));
            result.put("secondary_errors", secondary).put("automatic_retry", false);
            result.put("outcome_unknown", actionAttempted).put("business_success_verified", false);
            result.put("restoration", restoration);
            need(canonical(windowObservation).getBytes(StandardCharsets.UTF_8).length <= 32768, "WINDOW_CENSUS_RESULT_BOUND");
            result.put("window_observation", windowObservation);
            result.put("tree_observations", treeObservations);
            result.put("inspection_idle_observation", inspectionIdleObservation());
            // The adapter must observe the state AFTER am instrument terminates. The helper
            // cannot honestly assert that framework connection teardown has already completed.
            result.put("accessibility_mode_restoration_verified", JSONObject.NULL);
            result.put("requires_post_termination_state_check", automation != null);
            result.put("helper_work_completed", true).put("finished_elapsed_ms", SystemClock.elapsedRealtime());
            byte[] output = canonical(result).getBytes(StandardCharsets.UTF_8);
            need(output.length <= MAX_RESULT, "RESULT_BOUND");
            if (claimed) writeNew(nonce + ".result.json", output);
            Bundle bundle = new Bundle();
            ByteArrayOutputStream compressed = new ByteArrayOutputStream();
            try (GZIPOutputStream stream = new GZIPOutputStream(compressed)) { stream.write(output); }
            byte[] wire = compressed.toByteArray();
            need(wire.length > 0 && wire.length <= MAX_COMPRESSED_WIRE, "COMPRESSED_WIRE_BOUND");
            bundle.putString("owned_qa_result_gzip_base64", Base64.encodeToString(wire, Base64.NO_WRAP));
            // Keep the watchdog armed through framework teardown. Its return and the
            // command's actual termination are separately assessed by the host adapter.
            finish(primary == null ? -1 : 0, bundle);
            finished = true;
        } catch (Exception outputError) {
            // A lost/partial result is unknown, never an automatically retryable action.
            Process.killProcess(Process.myPid());
        }
    }

    void waitForInspectionIdle() throws Exception {
        need(DEADLINE_MS == InspectionIdleGate.OPERATION_DEADLINE_MS, "INSPECTION_IDLE_DEADLINE_CHANGED");
        if (inspectionIdle == null) inspectionIdle = new InspectionIdleGate.Observation(started);
        InspectionIdleGate.once(inspectionIdle, new InspectionIdleGate.Clock() {
            @Override public long now() { return SystemClock.elapsedRealtime(); }
        }, new InspectionIdleGate.Waiter() {
            @Override public void waitForIdle(long quietMillis, long globalMillis) throws Exception {
                automation.waitForIdle(quietMillis, globalMillis);
            }
        });
    }

    JSONObject inspectionIdleObservation() throws Exception {
        if (inspectionIdle == null) return new JSONObject();
        InspectionIdleGate.Observation value = inspectionIdle;
        return new JSONObject().put("schema", 1).put("operation", "inspect")
            .put("invoked", value.invoked).put("call_count", value.callCount)
            .put("operation_started_elapsed_ms", value.operationStarted)
            .put("began_elapsed_ms", value.began).put("last_elapsed_ms", value.last)
            .put("waited_ms", value.waited).put("quiet_timeout_ms", InspectionIdleGate.QUIET_MS)
            .put("global_timeout_cap_ms", InspectionIdleGate.GLOBAL_CAP_MS)
            .put("global_timeout_ms", value.globalMillis)
            .put("operation_deadline_ms", InspectionIdleGate.OPERATION_DEADLINE_MS)
            .put("api_returned", value.apiReturned).put("qualified", value.qualified)
            .put("exception_class", value.exceptionClass)
            .put("secondary_clock_exception_class", value.secondaryClockExceptionClass)
            .put("gate_error", value.error).put("event_quiet_only", true)
            .put("content_ready_proven", false).put("future_stability_proven", false);
    }

    static String errorCode(Exception error) {
        return error instanceof Rejected || error instanceof TouchTransaction.Fault || error instanceof PlayerButtonTransaction.Fault
            || error instanceof InspectionIdleGate.Fault
            ? error.getMessage() : "EXCEPTION_" + error.getClass().getSimpleName();
    }
    void writeNew(String name, byte[] value) throws Exception {
        need(name.matches("[0-9a-f]{32}\\.(claim|result)\\.json"), "OWNED_FILENAME_REQUIRED");
        File destination = new File(getContext().getFilesDir(), name);
        need(destination.createNewFile(), "NONCE_OR_RESULT_ALREADY_CLAIMED");
        try (FileOutputStream stream = new FileOutputStream(destination, false)) {
            stream.write(value); stream.flush(); stream.getFD().sync();
        }
    }
    byte[] readInspection(String nonce) throws Exception {
        need(nonce.matches("[0-9a-f]{32}"), "INSPECTION_NONCE_REQUIRED");
        File path = new File(getContext().getFilesDir(), nonce + ".result.json");
        need(path.isFile() && path.length() > 0 && path.length() <= MAX_RESULT, "INSPECTION_FILE_BOUND");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (FileInputStream stream = new FileInputStream(path)) {
            byte[] buffer = new byte[4096]; int got;
            while ((got = stream.read(buffer)) != -1) {
                need(bytes.size() + got <= MAX_RESULT, "INSPECTION_FILE_GREW"); bytes.write(buffer, 0, got); timeBound();
            }
        }
        return bytes.toByteArray();
    }
    JSONObject accessibilityState() throws Exception {
        AccessibilityManager manager = (AccessibilityManager) getContext().getSystemService(Context.ACCESSIBILITY_SERVICE);
        need(manager != null, "ACCESSIBILITY_MANAGER_MISSING");
        List<AccessibilityServiceInfo> services = manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK);
        need(services != null && services.size() <= 64, "ACCESSIBILITY_SERVICE_LIST_BOUND");
        List<String> identities = new ArrayList<String>();
        for (AccessibilityServiceInfo info : services) {
            ResolveInfo resolved = info.getResolveInfo();
            need(resolved != null && resolved.serviceInfo != null, "ACCESSIBILITY_SERVICE_IDENTITY_UNAVAILABLE");
            // Only a sorted digest/count leaves the process, never other services' names.
            identities.add(resolved.serviceInfo.packageName + "/" + resolved.serviceInfo.name + ":" + info.flags + ":" + info.getCapabilities());
        }
        Collections.sort(identities);
        JSONArray serial = new JSONArray(); for (String identity : identities) serial.put(identity);
        return new JSONObject().put("accessibility_enabled", manager.isEnabled())
            .put("touch_exploration_enabled", manager.isTouchExplorationEnabled())
            .put("enabled_service_count", identities.size()).put("enabled_services_sha256", hashJson(serial));
    }
    void validateScope(JSONObject scope) throws Exception {
        keys(scope, "package", "uid", "user", "display", "activity", "window_token", "main_epoch_sha256", "main_baseline_schema", "main_baseline_sha256", "main_baseline_qualification_sha256", "runtime_epoch_sha256", "app_scope_sha256");
        need(RUNTIME_EPOCH.equals(string(scope, "runtime_epoch_sha256", 64)) && APP_SCOPE_SHA.equals(string(scope, "app_scope_sha256", 64)), "EXACT_RUNTIME_AND_APP_VERSION_SCOPE_REQUIRED");
        need(PACKAGE.equals(string(scope, "package", 64)) && integer(scope, "uid") == TARGET_UID
            && integer(scope, "user") == 0 && integer(scope, "display") == 0, "EXACT_BILI_SCOPE_REQUIRED");
        need(string(scope, "activity", 256).matches("com\\.lianjia\\.beike/[A-Za-z0-9_.$]+"), "HOST_ACTIVITY_ATTESTATION_REQUIRED");
        need(string(scope, "window_token", 32).matches("[0-9a-f]{1,32}"), "HOST_WINDOW_TOKEN_REQUIRED");
        need(MAIN_EPOCH.equals(string(scope, "main_epoch_sha256", 64)), "HOST_EPOCH_ATTESTATION_REQUIRED");
        need(MAIN_BASELINE_SCHEMA.equals(string(scope, "main_baseline_schema", 64))
            && MAIN_BASELINE_SHA.equals(string(scope, "main_baseline_sha256", 64))
            && MAIN_BASELINE_QUALIFICATION_SHA.equals(string(scope, "main_baseline_qualification_sha256", 64)),
            "HOST_CURRENT_BASELINE_ATTESTATION_REQUIRED");
        ApplicationInfo info = getContext().getPackageManager().getApplicationInfo(PACKAGE, 0);
        need(info.uid == TARGET_UID, "ACTUAL_TARGET_UID_CHANGED");
    }
    void connect() throws Exception {
        timeBound();
        automation = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        need(automation != null, "UI_AUTOMATION_CONNECT_FAILED");
        AccessibilityServiceInfo info = automation.getServiceInfo();
        need(info != null, "OWN_SERVICE_INFO_UNAVAILABLE");
        need((info.flags & AccessibilityServiceInfo.FLAG_REQUEST_TOUCH_EXPLORATION_MODE) == 0, "UNEXPECTED_OWN_TOUCH_EXPLORATION_FLAG");
        originalFlags = info.flags; originalCapabilities = info.getCapabilities(); originalServiceInfoCaptured = true;
        restoration.put("connection_flags", UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
            .put("service_flags_before", originalFlags).put("service_capabilities_before", originalCapabilities);
        // Listen only for window-change readiness, before enabling enumeration.
        // Never read event text, source nodes, titles or other services' state.
        automation.setOnAccessibilityEventListener(new UiAutomation.OnAccessibilityEventListener() {
            @Override public void onAccessibilityEvent(AccessibilityEvent event) {
                if (event != null && (event.getEventType() == AccessibilityEvent.TYPE_WINDOWS_CHANGED
                        || event.getEventType() == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED)) {
                    synchronized (windowEvents) { windowEventSerial++; windowEvents.notifyAll(); }
                }
            }
        });
        info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
        automation.setServiceInfo(info);
        AccessibilityServiceInfo current = automation.getServiceInfo();
        need(current != null && current.flags == info.flags && current.getCapabilities() == originalCapabilities, "OWN_SERVICE_INFO_APPLY_UNVERIFIED");
        restoration.put("service_flags_during", current.flags);
        timeBound();
    }
    void restoreOwnServiceInfo() throws Exception {
        restoration.put("service_info_captured", originalServiceInfoCaptured);
        if (!originalServiceInfoCaptured) { restoration.put("service_info_verified", automation == null); return; }
        AccessibilityServiceInfo current = automation.getServiceInfo();
        need(current != null, "OWN_SERVICE_INFO_RESTORE_UNAVAILABLE");
        current.flags = originalFlags; automation.setServiceInfo(current);
        AccessibilityServiceInfo actual = automation.getServiceInfo();
        need(actual != null, "OWN_SERVICE_INFO_RESTORE_READBACK_MISSING");
        restoration.put("service_flags_after", actual.flags).put("service_capabilities_after", actual.getCapabilities());
        boolean verified = actual.flags == originalFlags && actual.getCapabilities() == originalCapabilities;
        restoration.put("service_info_verified", verified);
        need(verified, "OWN_SERVICE_INFO_RESTORE_MISMATCH");
    }

    static final class Capture {
        final JSONObject json;
        AccessibilityNodeInfo target;
        int windowId;
        Capture(JSONObject value) { json = value; }
        void close() { if (target != null) { target.recycle(); target = null; } }
    }
    static JSONArray bounds(Rect box) { return new JSONArray().put(box.left).put(box.top).put(box.right).put(box.bottom); }
    static String text(CharSequence input) { return input == null ? "" : input.toString(); }
    static void textField(JSONObject out, String key, CharSequence value) throws Exception {
        String full = text(value); need(full.length() <= 16384, "NODE_TEXT_BOUND");
        out.put(key, full.length() <= 256 ? full : full.substring(0, 256));
        out.put(key + "_sha256", hash(full.getBytes(StandardCharsets.UTF_8))).put(key + "_truncated", full.length() > 256);
    }
    static boolean supportsAction(AccessibilityNodeInfo value, int action) throws Exception {
        List<AccessibilityNodeInfo.AccessibilityAction> actions = value.getActionList();
        need(actions != null && actions.size() <= 64, "NODE_ACTION_LIST_BOUND");
        for (AccessibilityNodeInfo.AccessibilityAction item : actions) {
            need(item != null, "NODE_ACTION_ENTRY_MISSING");
            if (item.getId() == action) return true;
        }
        return false;
    }
    JSONObject node(AccessibilityNodeInfo value, String path) throws Exception {
        need(PACKAGE.equals(text(value.getPackageName())), "CROSS_PACKAGE_NODE");
        JSONObject out = new JSONObject();
        out.put("path", path).put("package", PACKAGE).put("enabled", value.isEnabled()).put("clickable", value.isClickable())
            .put("visible", value.isVisibleToUser()).put("focused", value.isFocused()).put("selected", value.isSelected())
            .put("checked", value.isChecked()).put("password", value.isPassword()).put("child_count", value.getChildCount())
            .put("editable", value.isEditable()).put("supports_set_text", supportsAction(value, AccessibilityNodeInfo.ACTION_SET_TEXT));
        textField(out, "resource_id", value.getViewIdResourceName()); textField(out, "class", value.getClassName());
        // Password text and content descriptions are never read or hashed.
        if (!value.isPassword() && value.isVisibleToUser()) { textField(out, "text", value.getText()); textField(out, "content_desc", value.getContentDescription()); }
        else out.put("content_redacted", true);
        Rect box = new Rect(); value.getBoundsInScreen(box); out.put("bounds", bounds(box)); return out;
    }
    void walk(AccessibilityNodeInfo value, String path, int depth, JSONArray rows, Capture capture, String wanted) throws Exception {
        timeBound();
        currentTreeObservation.put("attempted_nodes", currentTreeObservation.getInt("attempted_nodes") + 1)
            .put("max_attempted_depth", Math.max(depth, currentTreeObservation.getInt("max_attempted_depth")))
            .put("emitted_nodes", rows.length()).put("last_elapsed_ms", SystemClock.elapsedRealtime());
        need(depth <= MAX_DEPTH, "TREE_DEPTH_BOUND");
        need(rows.length() < MAX_NODES, "TREE_NODE_COUNT_BOUND");
        int children = value.getChildCount();
        currentTreeObservation.put("max_observed_children", Math.max(children, currentTreeObservation.getInt("max_observed_children")));
        need(children >= 0 && children <= MAX_CHILDREN, "TREE_CHILD_BOUND");
        JSONObject row = node(value, path); row.put("node_sha256", hashJson(row)); rows.put(row);
        currentTreeObservation.put("emitted_nodes", rows.length());
        if (path.equals(wanted)) { need(capture.target == null, "AMBIGUOUS_NODE_PATH"); capture.target = AccessibilityNodeInfo.obtain(value); }
        if (value.isPassword() || !value.isVisibleToUser()) return;
        for (int n = 0; n < value.getChildCount(); n++) {
            AccessibilityNodeInfo child = value.getChild(n); need(child != null, "TREE_CHANGED_NULL_CHILD");
            try { walk(child, path + "/" + n, depth + 1, rows, capture, wanted); }
            finally { child.recycle(); }
        }
    }
    static void recycleWindows(SparseArray<List<AccessibilityWindowInfo>> windows) {
        if (windows == null) return;
        for (int n = 0; n < windows.size(); n++) {
            List<AccessibilityWindowInfo> values = windows.valueAt(n);
            if (values != null) for (AccessibilityWindowInfo window : values) if (window != null) window.recycle();
        }
    }
    static final class SelectedWindows {
        final SparseArray<List<AccessibilityWindowInfo>> all;
        final AccessibilityWindowInfo selected;
        SelectedWindows(SparseArray<List<AccessibilityWindowInfo>> windows, AccessibilityWindowInfo window) {
            all = windows; selected = window;
        }
        void close() { recycleWindows(all); }
    }
    boolean clearOwnPublicWindowCache() throws Exception {
        // clearCache() is public since API 34. Reflection keeps the pinned
        // compile-SDK-31 input; it does not request a hidden API exemption.
        need(Build.VERSION.SDK_INT >= 34, "PUBLIC_CACHE_API_LEVEL_REQUIRED");
        need(automation != null, "OWN_UI_AUTOMATION_REQUIRED_FOR_CACHE_CLEAR");
        if (publicCacheClearMethod == null) {
            Method method = UiAutomation.class.getMethod("clearCache");
            need(method.getDeclaringClass() == UiAutomation.class
                && method.getReturnType() == boolean.class && method.getParameterTypes().length == 0
                && Modifier.isPublic(method.getModifiers()) && !Modifier.isStatic(method.getModifiers()),
                "EXACT_PUBLIC_CACHE_API_REQUIRED");
            publicCacheClearMethod = method;
        }
        final Object result;
        try { result = publicCacheClearMethod.invoke(automation); }
        catch (InvocationTargetException invocation) {
            Throwable cause = invocation.getCause();
            if (cause instanceof Exception) throw (Exception) cause;
            if (cause instanceof Error) throw (Error) cause;
            throw invocation;
        }
        need(result instanceof Boolean, "PUBLIC_CACHE_BOOLEAN_RESULT_REQUIRED");
        return (Boolean) result;
    }
    SelectedWindows awaitFocusedWindow() throws Exception {
        final long began = SystemClock.elapsedRealtime();
        final long deadline = Math.min(started + DEADLINE_MS, began + WINDOW_WAIT_MS);
        windowObservation = new JSONObject().put("requested_display", 0)
            .put("selection", "exact-display-0-focused-application")
            .put("wait_budget_ms", WINDOW_WAIT_MS).put("recheck_max_ms", WINDOW_RECHECK_MS)
            .put("sample_timings", new JSONArray()).put("ready", false)
            .put("cache_api", "android.app.UiAutomation.clearCache()")
            .put("cache_policy", "require_public_own_connection_clear_before_each_query")
            .put("cache_runtime_sdk", Build.VERSION.SDK_INT)
            .put("cache_attempts", 0).put("cache_clears", 0)
            .put("cache_last_result", JSONObject.NULL).put("cache_last_exception", JSONObject.NULL);
        int samples = 0;
        for (;;) {
            timeBound(); need(samples < MAX_WINDOW_QUERIES, "WINDOW_QUERY_BOUND");
            final long serial;
            synchronized (windowEvents) { serial = windowEventSerial; }
            windowObservation.put("cache_attempts", samples + 1)
                .put("cache_last_result", JSONObject.NULL).put("cache_last_exception", JSONObject.NULL);
            final boolean cacheCleared;
            try { cacheCleared = clearOwnPublicWindowCache(); }
            catch (Exception cacheError) {
                windowObservation.put("cache_last_exception", cacheError.getClass().getName());
                throw cacheError;
            }
            catch (Error cacheError) {
                windowObservation.put("cache_last_exception", cacheError.getClass().getName());
                throw cacheError;
            }
            windowObservation.put("cache_last_result", cacheCleared);
            need(cacheCleared, "PUBLIC_CACHE_CLEAR_NOT_CONFIRMED");
            windowObservation.put("cache_clears", samples + 1);
            timeBound();
            need(SystemClock.elapsedRealtime() <= deadline, "WINDOW_READINESS_DEADLINE");
            SparseArray<List<AccessibilityWindowInfo>> windows = automation.getWindowsOnAllDisplays();
            boolean retained = false;
            try {
                timeBound();
                need(windows != null && windows.size() <= 8, "WINDOW_DISPLAY_BOUND");
                AccessibilityWindowInfo chosen = null;
                JSONArray rows = new JSONArray();
                JSONArray displays = new JSONArray();
                int total = 0;
                for (int n = 0; n < windows.size(); n++) {
                    int display = windows.keyAt(n); List<AccessibilityWindowInfo> values = windows.valueAt(n);
                    need(display >= 0 && values != null && values.size() <= 32, "WINDOW_LIST_BOUND");
                    displays.put(display); total += values.size(); need(total <= 128, "WINDOW_TOTAL_BOUND");
                    for (AccessibilityWindowInfo window : values) {
                        need(window != null && window.getDisplayId() == display, "WINDOW_DISPLAY_ID_MISMATCH");
                        rows.put(new JSONObject().put("display", display).put("id", window.getId())
                            .put("type", window.getType()).put("focused", window.isFocused())
                            .put("active", window.isActive()).put("accessibility_focused", window.isAccessibilityFocused())
                            .put("layer", window.getLayer()));
                        if (display == 0 && window.isFocused() && window.getType() == AccessibilityWindowInfo.TYPE_APPLICATION) {
                            need(chosen == null, "AMBIGUOUS_FOCUSED_APPLICATION_WINDOW"); chosen = window;
                        }
                    }
                }
                JSONObject census = new JSONObject().put("sample", ++samples).put("event_serial", serial)
                    .put("elapsed_ms", SystemClock.elapsedRealtime() - began).put("displays", displays).put("windows", rows);
                JSONObject nextObservation = new JSONObject(canonical(windowObservation));
                if (samples == 1) nextObservation.put("first", census);
                nextObservation.put("last", census).put("samples", samples)
                    .put("waited_ms", SystemClock.elapsedRealtime() - began);
                nextObservation.getJSONArray("sample_timings").put(new JSONObject()
                    .put("sample", samples).put("event_serial", serial)
                    .put("elapsed_ms", census.getLong("elapsed_ms")).put("cache_cleared", cacheCleared));
                need(canonical(nextObservation).getBytes(StandardCharsets.UTF_8).length <= 32000, "WINDOW_CENSUS_RESULT_BOUND");
                windowObservation = nextObservation;
                need(SystemClock.elapsedRealtime() <= deadline, "WINDOW_READINESS_DEADLINE");
                if (chosen != null) {
                    windowObservation.put("ready", true).put("selected_display", 0).put("selected_window_id", chosen.getId());
                    retained = true; return new SelectedWindows(windows, chosen);
                }
            } finally { if (!retained) recycleWindows(windows); }
            long remaining = deadline - SystemClock.elapsedRealtime();
            need(remaining > 0, "NO_FOCUSED_APPLICATION_WINDOW");
            // A window event may arrive before the observable window changes.
            // Re-read this condition within the same deadline even if no later
            // event arrives. Events still wake immediately; no action is retried.
            // Serial closes the query/wait gap without holding a lock across IPC.
            synchronized (windowEvents) {
                if (windowEventSerial == serial) windowEvents.wait(Math.min(remaining, WINDOW_RECHECK_MS));
            }
            windowObservation.put("waited_ms", SystemClock.elapsedRealtime() - began);
            need(SystemClock.elapsedRealtime() < deadline, "NO_FOCUSED_APPLICATION_WINDOW");
        }
    }
    Capture inspect(String wanted, String purpose) throws Exception {
        timeBound();
        need(treeObservations.length() < 3, "TREE_OBSERVATION_COUNT_BOUND");
        currentTreeObservation = new JSONObject().put("capture", treeObservations.length() + 1)
            .put("purpose", purpose).put("node_limit", MAX_NODES).put("depth_limit", MAX_DEPTH)
            .put("child_limit", MAX_CHILDREN).put("json_byte_limit", MAX_RESULT - 65536)
            .put("attempted_nodes", 0).put("emitted_nodes", 0).put("max_attempted_depth", 0)
            .put("max_observed_children", 0).put("serialized_bytes", 0).put("complete", false)
            .put("began_elapsed_ms", SystemClock.elapsedRealtime());
        currentTreeObservation.put("last_elapsed_ms", currentTreeObservation.getLong("began_elapsed_ms"));
        treeObservations.put(currentTreeObservation);
        SelectedWindows windows = awaitFocusedWindow();
        AccessibilityWindowInfo chosen = windows.selected;
        AccessibilityNodeInfo root = null;
        Capture capture = new Capture(new JSONObject());
        try {
            need(chosen.getDisplayId() == 0 && chosen.isFocused()
                && chosen.getType() == AccessibilityWindowInfo.TYPE_APPLICATION, "FOCUSED_WINDOW_SCOPE_CHANGED");
            root = chosen.getRoot();
            need(root != null && PACKAGE.equals(text(root.getPackageName())), "FOCUSED_PACKAGE_MISMATCH");
            Rect box = new Rect(); chosen.getBoundsInScreen(box);
            JSONObject stable = new JSONObject().put("package", PACKAGE).put("display", 0).put("type", chosen.getType())
                .put("focused", chosen.isFocused()).put("bounds", bounds(box));
            capture.windowId = chosen.getId();
            JSONArray rows = new JSONArray(); walk(root, "0", 0, rows, capture, wanted);
            capture.json.put("window", stable).put("window_sha256", hashJson(stable))
                .put("connection_scoped_window_id", chosen.getId()).put("nodes", rows).put("tree_sha256", hashJson(rows))
                .put("observed_elapsed_ms", SystemClock.elapsedRealtime()).put("complete", true)
                .put("traversal", "visible-non-password-subtrees");
            int serializedBytes = canonical(capture.json).getBytes(StandardCharsets.UTF_8).length;
            currentTreeObservation.put("serialized_bytes", serializedBytes);
            need(serializedBytes <= MAX_RESULT - 65536, "TREE_RESULT_BOUND");
            currentTreeObservation.put("complete", true).put("last_elapsed_ms", SystemClock.elapsedRealtime());
            return capture;
        } catch (Exception error) { capture.close(); throw error; }
        finally {
            if (root != null) root.recycle();
            windows.close();
        }
    }
    static final String REVEAL_ACTIVITY = PACKAGE + "/com.bilibili.ship.theseus.detail.UnitedBizDetailsActivity";
    static final String REVEAL_TITLE = "7ff99f77d6b59f394c4c6c0ca167aded470663d4cef66215fcce841ed549afba";
    static final String REVEAL_AUTHOR = "3355707b07511199c7d280b9a77510b5e9b8698c7c7e4aedcf938805a3822d64";

    static int[] revealRect(JSONArray value) throws Exception {
        need(value.length() == 4, "REVEAL_RECT_SHAPE");
        int[] out = new int[4];
        for (int i = 0; i < 4; i++) {
            Object item = value.get(i);
            need(item instanceof Integer || item instanceof Long, "REVEAL_RECT_INTEGER");
            long number = ((Number) item).longValue();
            need(number >= 0 && number <= 16384, "REVEAL_RECT_BOUND"); out[i] = (int) number;
        }
        need(out[0] < out[2] && out[1] < out[3], "REVEAL_RECT_POSITIVE"); return out;
    }
    static boolean revealInside(int[] a, int[] b) {
        return b[0] <= a[0] && a[2] <= b[2] && b[1] <= a[1] && a[3] <= b[3];
    }
    static boolean revealEligible(JSONObject node) throws Exception {
        return node.getBoolean("visible") && node.getBoolean("enabled") && !node.getBoolean("password")
            && !node.getBoolean("class_truncated") && !node.getBoolean("resource_id_truncated");
    }
    static JSONObject revealOne(JSONArray nodes, String resource, String kind, String textHash) throws Exception {
        JSONObject selected = null; int matches = 0;
        for (int i = 0; i < nodes.length(); i++) {
            JSONObject node = nodes.getJSONObject(i);
            if (resource.equals(node.getString("resource_id")) && kind.equals(node.getString("class"))
                && revealEligible(node)) {
                if (textHash != null) {
                    if (node.getBoolean("text_truncated") || !(node.opt("text") instanceof String)
                        || !textHash.equals(node.getString("text_sha256"))
                        || !textHash.equals(hash(node.getString("text").getBytes(StandardCharsets.UTF_8)))) continue;
                }
                selected = node; matches++;
            }
        }
        need(matches == 1, "REVEAL_UNIQUE_PLAYER_ROLE_REQUIRED"); return selected;
    }
    static boolean revealUnder(JSONObject node, JSONObject parent) throws Exception {
        return node.getString("path").startsWith(parent.getString("path") + "/");
    }
    static JSONObject revealPlayer(JSONObject inspection, JSONObject scope, boolean requireHiddenControls) throws Exception {
        need(REVEAL_ACTIVITY.equals(scope.getString("activity")), "REVEAL_EXACT_COURSE_ACTIVITY");
        need(inspection.getBoolean("complete") && "visible-non-password-subtrees".equals(inspection.getString("traversal")),
             "REVEAL_COMPLETE_PLAYER_REQUIRED");
        JSONObject window = inspection.getJSONObject("window"); JSONArray nodes = inspection.getJSONArray("nodes");
        need(PACKAGE.equals(window.getString("package")) && window.getBoolean("focused")
             && integer(window,"display") == 0 && integer(window,"type") == 1,
             "REVEAL_FOCUSED_DISPLAY_ZERO_PLAYER_REQUIRED");
        JSONObject title = revealOne(nodes,PACKAGE+":id/title","android.widget.TextView",REVEAL_TITLE);
        JSONObject author = revealOne(nodes,PACKAGE+":id/author_name","android.widget.TextView",REVEAL_AUTHOR);
        JSONObject area = revealOne(nodes,PACKAGE+":id/video_area","android.widget.FrameLayout",null);
        JSONObject container = revealOne(nodes,PACKAGE+":id/video_container","android.widget.FrameLayout",null);
        JSONObject overlay = revealOne(nodes,PACKAGE+":id/video_area_float_layer_container","android.widget.FrameLayout",null);
        JSONObject toolbar = revealOne(nodes,PACKAGE+":id/collapsing_toolbar","android.widget.FrameLayout",null);
        int[] full = revealRect(area.getJSONArray("bounds")), crop = revealRect(overlay.getJSONArray("bounds"));
        need(Arrays.equals(full,revealRect(container.getJSONArray("bounds")))
             && Arrays.equals(crop,revealRect(toolbar.getJSONArray("bounds"))) && !Arrays.equals(crop,full)
             && revealInside(crop,full) && revealInside(full,revealRect(window.getJSONArray("bounds")))
             && revealUnder(container,area) && revealUnder(overlay,area), "REVEAL_ABSOLUTE_PLAYER_GEOMETRY");
        JSONObject areaSurface = null, cropSurface = null; int surfaceCount = 0, areaCount = 0, cropCount = 0;
        for (int i = 0; i < nodes.length(); i++) {
            JSONObject node = nodes.getJSONObject(i); String kind = node.getString("class");
            if ("android.view.SurfaceView".equals(kind) || "android.view.TextureView".equals(kind)) {
                surfaceCount++;
                need("android.view.SurfaceView".equals(kind) && revealEligible(node)
                     && node.getString("resource_id").isEmpty() && revealUnder(node,container)
                     && !revealUnder(node,overlay) && !revealUnder(node,toolbar), "REVEAL_SURFACE_SCOPE");
                int[] bounds = revealRect(node.getJSONArray("bounds"));
                if (Arrays.equals(bounds,full)) { areaSurface = node; areaCount++; }
                if (Arrays.equals(bounds,crop)) { cropSurface = node; cropCount++; }
            }
            if (revealUnder(node,container) && node.getBoolean("visible")) {
                need(!node.getBoolean("password"), "REVEAL_PLAYER_PASSWORD_DESCENDANT");
                String text = node.getString("text");
                need(text.isEmpty() || !node.getBoolean("text_truncated"), "REVEAL_PLAYER_TEXT_COMPLETENESS");
                need(!text.startsWith("Buffering..."), "REVEAL_BUFFERING_PLAYER_REJECTED");
            }
        }
        need(surfaceCount == 2 && areaCount == 1 && cropCount == 1, "REVEAL_EXACT_TWO_SURFACE_ROLES");
        if (requireHiddenControls) {
            JSONObject controls = revealOne(nodes,PACKAGE+":id/control_container","android.widget.FrameLayout",null);
            need(revealUnder(controls,container) && integer(controls,"child_count") == 0
                 && canonical(controls.getJSONArray("bounds")).equals(canonical(overlay.getJSONArray("bounds"))),
                 "REVEAL_CURRENT_HIDDEN_CONTROL_CONTAINER");
            for (int i = 0; i < nodes.length(); i++) {
                JSONObject node = nodes.getJSONObject(i);
                if (revealUnder(node,area) && node.getBoolean("visible") && node.getBoolean("enabled"))
                    need(!node.getBoolean("clickable") && !"android.widget.SeekBar".equals(node.getString("class")),
                         "REVEAL_ALREADY_INTERACTIVE_PLAYER_REJECTED");
            }
        }
        JSONArray surfaces = new JSONArray(); String priorParent = null;
        JSONObject[] surfaceNodes = new JSONObject[]{areaSurface,cropSurface};
        String[] roleNames = new String[]{"area-sized","crop-sized"};
        for (int i = 0; i < surfaceNodes.length; i++) {
            JSONObject node = surfaceNodes[i]; String path = node.getString("path");
            int slash = path.lastIndexOf('/'); need(slash > 0, "REVEAL_SURFACE_PARENT_PATH");
            String parentPath = path.substring(0,slash); JSONObject parent = null; int matches = 0;
            for (int j = 0; j < nodes.length(); j++) {
                JSONObject candidate = nodes.getJSONObject(j);
                if (parentPath.equals(candidate.getString("path"))) { parent = candidate; matches++; }
            }
            need(matches == 1 && revealEligible(parent) && revealUnder(parent,container)
                 && "android.widget.FrameLayout".equals(parent.getString("class"))
                 && parent.getString("resource_id").isEmpty()
                 && canonical(parent.getJSONArray("bounds")).equals(canonical(node.getJSONArray("bounds")))
                 && !parentPath.equals(priorParent), "REVEAL_EXACT_DISTINCT_SURFACE_PARENTS");
            priorParent = parentPath;
            surfaces.put(new JSONObject().put("role",roleNames[i]).put("node_sha256",node.getString("node_sha256"))
                .put("parent_node_sha256",parent.getString("node_sha256")).put("bounds",node.getJSONArray("bounds")));
        }
        JSONArray fixed = new JSONArray();
        JSONObject[] fixedNodes = new JSONObject[]{area,container,overlay,toolbar};
        String[] fixedNames = new String[]{"area","container","overlay","toolbar"};
        for (int i = 0; i < fixedNodes.length; i++) {
            JSONObject node = fixedNodes[i];
            fixed.put(new JSONObject().put("role",fixedNames[i]).put("path_sha256",hash(node.getString("path").getBytes(StandardCharsets.UTF_8)))
                .put("bounds",node.getJSONArray("bounds")).put("class",node.getString("class")).put("resource_id",node.getString("resource_id")));
        }
        JSONObject render = new JSONObject().put("fixed_roles",fixed).put("surfaces",surfaces);
        return new JSONObject().put("scope",scope).put("window",window).put("window_sha256",inspection.getString("window_sha256"))
            .put("tree_sha256",inspection.getString("tree_sha256")).put("viewport_bounds",overlay.getJSONArray("bounds"))
            .put("full_area_bounds",area.getJSONArray("bounds")).put("render_structure_sha256",hashJson(render))
            .put("title_text_sha256",title.getString("text_sha256")).put("author_text_sha256",author.getString("text_sha256"));
    }
    static boolean sameRevealFrame(JSONObject first, JSONObject second) throws Exception {
        for (String key : new String[]{"scope","window","window_sha256","viewport_bounds","full_area_bounds",
                "render_structure_sha256","title_text_sha256","author_text_sha256"})
            if (!canonical(first.get(key)).equals(canonical(second.get(key)))) return false;
        return true;
    }
    static Method publicDisplayMotionFactory() throws Exception {
        need(Build.VERSION.SDK_INT >= 34, "REVEAL_PUBLIC_DISPLAY_MOTION_API_34_REQUIRED");
        Method method = MotionEvent.class.getMethod("obtain",long.class,long.class,int.class,int.class,
            MotionEvent.PointerProperties[].class,MotionEvent.PointerCoords[].class,int.class,int.class,
            float.class,float.class,int.class,int.class,int.class,int.class,int.class,int.class);
        need(method.getDeclaringClass() == MotionEvent.class && method.getReturnType() == MotionEvent.class
             && Modifier.isPublic(method.getModifiers()) && Modifier.isStatic(method.getModifiers()),
             "REVEAL_EXACT_PUBLIC_DISPLAY_MOTION_FACTORY");
        return method;
    }
    static MotionEvent displayMotion(Method factory, int action, long downTime, long eventTime, int x, int y) throws Exception {
        MotionEvent.PointerProperties properties = new MotionEvent.PointerProperties();
        properties.id = 0; properties.toolType = MotionEvent.TOOL_TYPE_FINGER;
        MotionEvent.PointerCoords coordinates = new MotionEvent.PointerCoords();
        coordinates.x = x; coordinates.y = y; coordinates.pressure = action == MotionEvent.ACTION_DOWN ? 1 : 0;
        coordinates.size = 1;
        Object raw;
        try {
            raw = factory.invoke(null,downTime,eventTime,action,1,new MotionEvent.PointerProperties[]{properties},
                new MotionEvent.PointerCoords[]{coordinates},0,0,1.0f,1.0f,0,0,InputDevice.SOURCE_TOUCHSCREEN,0,0,MotionEvent.CLASSIFICATION_NONE);
        } catch (InvocationTargetException error) {
            Throwable cause = error.getCause();
            if (cause instanceof Exception) throw (Exception) cause;
            throw error;
        }
        need(raw instanceof MotionEvent, "REVEAL_MOTION_EVENT_REQUIRED");
        MotionEvent event = (MotionEvent) raw;
        try {
            need(event.getActionMasked() == action && event.getPointerCount() == 1 && event.getPointerId(0) == 0
                 && event.getToolType(0) == MotionEvent.TOOL_TYPE_FINGER && event.getX() == x && event.getY() == y
                 && event.getSource() == InputDevice.SOURCE_TOUCHSCREEN && event.getDownTime() == downTime
                 && event.getEventTime() == eventTime, "REVEAL_EXACT_SINGLE_POINTER_EVENT");
            return event;
        } catch (Exception primary) {
            try { event.recycle(); } catch (Exception secondary) { primary.addSuppressed(secondary); }
            throw primary;
        }
    }
    static JSONObject touchObservation(TouchTransaction.Observation value, int x, int y) throws Exception {
        JSONArray secondary = new JSONArray(); for (String error : value.secondary) secondary.put(error);
        return new JSONObject().put("display",0).put("point",new JSONArray().put(x).put(y)).put("pointer_count",1)
            .put("source",InputDevice.SOURCE_TOUCHSCREEN).put("explicit_public_display_factory",true)
            .put("runtime_sdk",Build.VERSION.SDK_INT).put("down_attempted",value.downAttempted).put("down_acknowledged",value.downAcknowledged)
            .put("up_attempted",value.upAttempted).put("up_acknowledged",value.upAcknowledged)
            .put("cancel_creation_attempted",value.cancelCreationAttempted).put("cancel_attempted",value.cancelAttempted)
            .put("cancel_acknowledged",value.cancelAcknowledged).put("down_created",value.downCreated).put("up_created",value.upCreated)
            .put("cancel_created",value.cancelCreated).put("down_recycled",value.downRecycled).put("up_recycled",value.upRecycled)
            .put("cancel_recycled",value.cancelRecycled).put("all_created_events_recycled",value.allCreatedRecycled())
            .put("input_stream_terminated",value.inputTerminated()).put("down_time_ms",value.downTime)
            .put("up_admission_elapsed_ms",value.upAdmissionElapsed).put("finished_time_ms",value.finishedTime)
            .put("up_admission_budget_ms",TouchTransaction.MAX_DOWN_TO_UP_ADMISSION_MS)
            .put("primary_error",value.primary == null ? JSONObject.NULL : errorCode(value.primary)).put("secondary_errors",secondary)
            .put("atomic_input_target_attribution",false).put("controls_revealed",JSONObject.NULL)
            .put("business_success_verified",false);
    }
    void revealControls(JSONObject request, JSONObject result) throws Exception {
        final Method factory = publicDisplayMotionFactory();
        String priorNonce = string(request,"inspection_nonce",32), expectedHash = string(request,"inspection_sha256",64);
        need(!priorNonce.equals(string(request,"nonce",32)) && expectedHash.matches("[0-9a-f]{64}"), "REVEAL_PRIOR_NONCE_AND_HASH");
        byte[] bytes = readInspection(priorNonce); need(hash(bytes).equals(expectedHash), "REVEAL_PRIOR_WIRE_CHANGED");
        JSONObject previous = new JSONObject(new String(bytes,StandardCharsets.UTF_8));
        need(PROTOCOL.equals(previous.getString("protocol")) && "inspect".equals(previous.getString("op"))
             && priorNonce.equals(previous.getString("nonce")) && previous.getBoolean("claim_persistence_completed")
             && previous.getBoolean("helper_work_completed") && previous.getBoolean("ok") && !previous.getBoolean("action_attempted")
             && previous.getJSONObject("restoration").getBoolean("service_info_verified"), "REVEAL_PRIOR_COMPLETE_INSPECTION");
        final JSONObject scope = request.getJSONObject("scope");
        need(canonical(scope).equals(canonical(previous.getJSONObject("host_scope_attestation"))), "REVEAL_PRIOR_SCOPE_CHANGED");
        JSONObject expected = previous.getJSONObject("inspection");
        long age = SystemClock.elapsedRealtime() - integer(expected,"observed_elapsed_ms");
        need(age >= 0 && age <= MAX_INSPECTION_AGE_MS, "REVEAL_INSPECTION_TOO_OLD");
        final String proofHash = string(request,"player_scope_sha256",64);
        need(proofHash.matches("[0-9a-f]{64}"), "REVEAL_PLAYER_PROOF_HASH");
        Capture current = inspect(null,"reveal_target");
        try {
            need(current.json.getString("tree_sha256").equals(expected.getString("tree_sha256"))
                 && current.json.getString("window_sha256").equals(expected.getString("window_sha256")),
                 "REVEAL_INSPECTED_TREE_OR_WINDOW_CHANGED");
            final JSONObject proof = revealPlayer(current.json,scope,true);
            need(hashJson(proof).equals(proofHash) && canonical(proof.getJSONArray("viewport_bounds"))
                 .equals(canonical(request.getJSONArray("viewport_bounds"))), "REVEAL_PLAYER_PROOF_CHANGED");
            Capture finalWindow = inspect(null,"reveal_final_window");
            try {
                need(finalWindow.windowId == current.windowId && finalWindow.json.getString("tree_sha256")
                     .equals(current.json.getString("tree_sha256")) && hashJson(revealPlayer(finalWindow.json,scope,true)).equals(proofHash),
                     "REVEAL_FINAL_ABSOLUTE_PLAYER_CHANGED");
            } finally { finalWindow.close(); }
            int[] crop = revealRect(proof.getJSONArray("viewport_bounds"));
            final int x = crop[0] + (crop[2]-crop[0])/2, y = crop[1] + (crop[3]-crop[1])/2;
            need(crop[0]+16 < x && x < crop[2]-16 && crop[1]+16 < y && y < crop[3]-16,
                 "REVEAL_STRICT_INTERIOR_POINT_REQUIRED");
            TouchTransaction.Observation touch = TouchTransaction.run(new TouchTransaction.Backend<MotionEvent>() {
                @Override public long now() { return SystemClock.uptimeMillis(); }
                @Override public MotionEvent obtain(int action,long downTime,long eventTime) throws Exception {
                    return displayMotion(factory,action,downTime,eventTime,x,y);
                }
                @Override public void beforeDown() throws Exception { timeBound(); }
                @Override public boolean inject(MotionEvent event) throws Exception {
                    if (event.getActionMasked() == MotionEvent.ACTION_DOWN) actionAttempted = true;
                    return automation.injectInputEvent(event,true);
                }
                @Override public void recycle(MotionEvent event) { event.recycle(); }
            });
            result.put("touch",touchObservation(touch,x,y)).put("inspection_nonce",priorNonce).put("inspection_sha256",expectedHash)
                .put("player_scope_sha256",proofHash).put("player_scope",proof).put("action_window",current.json.getJSONObject("window"))
                .put("connection_scoped_window_id",current.windowId).put("strict_interior_margin_px",16);
            if (touch.primary != null) throw touch.primary;
            need(touch.downAcknowledged && touch.upAcknowledged && touch.inputTerminated() && touch.allCreatedRecycled(),
                 "REVEAL_INPUT_COMPLETION_REQUIRED");
            Capture after = inspect(null,"reveal_after");
            try {
                JSONObject afterProof = revealPlayer(after.json,scope,false);
                need(after.windowId == current.windowId && sameRevealFrame(proof,afterProof),
                     "REVEAL_ABSOLUTE_SCOPE_CHANGED_DURING_INPUT");
                result.put("post_inspection",after.json).put("post_player_scope",afterProof)
                    .put("scope_unchanged_after_input",true).put("requires_independent_controls_readback",true);
            } finally { after.close(); }
        } finally { current.close(); }
    }

    static final String PLAYER_BUTTON_RESOURCE = PACKAGE+":id/gemini_halfscreen_play";
    static JSONObject playerFrame(JSONObject proof) throws Exception {
        JSONObject value=new JSONObject();
        for (String key:new String[]{"scope","window","window_sha256","viewport_bounds","full_area_bounds",
                "render_structure_sha256","title_text_sha256","author_text_sha256"}) value.put(key,proof.get(key));
        return value;
    }
    static final class PlayerSelection {
        final String path,nodeHash,inspectionHash;final JSONObject proof;
        PlayerSelection(String p,String h,String whole,JSONObject value) { path=p;nodeHash=h;inspectionHash=whole;proof=value; }
    }
    static PlayerSelection playerButtonCurrent(JSONObject inspection,JSONObject scope,String transition) throws Exception {
        need("pause".equals(transition)||"resume".equals(transition),"FIXED_PLAYER_TRANSITION_REQUIRED");
        String label="pause".equals(transition)?"暂停":"播放";
        JSONObject proof=revealPlayer(inspection,scope,false);JSONArray nodes=inspection.getJSONArray("nodes");
        JSONObject button=null,controls=null,container=null,parent=null;int buttonCount=0,controlsCount=0,containerCount=0;
        for (int i=0;i<nodes.length();i++) {
            JSONObject node=nodes.getJSONObject(i);String resource=node.getString("resource_id");
            if (PLAYER_BUTTON_RESOURCE.equals(resource)) { button=node;buttonCount++; }
            if ((PACKAGE+":id/control_container").equals(resource)) { controls=node;controlsCount++; }
            if ((PACKAGE+":id/video_container").equals(resource)) { container=node;containerCount++; }
        }
        need(buttonCount==1,"UNIQUE_CURRENT_PLAYBACK_RESOURCE_REQUIRED");
        need(controlsCount==1,"UNIQUE_CURRENT_CONTROL_CONTAINER_REQUIRED");
        need(containerCount==1,"UNIQUE_CURRENT_VIDEO_CONTAINER_REQUIRED");
        need(revealEligible(button) && "android.widget.ImageView".equals(button.getString("class")) && button.getBoolean("clickable")
            && !button.getBoolean("content_desc_truncated") && label.equals(button.getString("content_desc"))
            && hash(label.getBytes(StandardCharsets.UTF_8)).equals(button.getString("content_desc_sha256")),
            "EXACT_CURRENT_PLAYER_BUTTON_LABEL_REQUIRED");
        String path=button.getString("path");int slash=path.lastIndexOf('/');need(slash>0,"CURRENT_PLAYER_BUTTON_PARENT_PATH");
        String parentPath=path.substring(0,slash);int parentCount=0;
        for (int i=0;i<nodes.length();i++) {
            JSONObject candidate=nodes.getJSONObject(i);
            if (parentPath.equals(candidate.getString("path"))) { parent=candidate;parentCount++; }
        }
        int[] crop=revealRect(proof.getJSONArray("viewport_bounds")),box=revealRect(button.getJSONArray("bounds"));
        need(revealEligible(controls) && "android.widget.FrameLayout".equals(controls.getString("class"))
            && revealUnder(controls,container) && Arrays.equals(crop,revealRect(controls.getJSONArray("bounds")))
            && integer(controls,"child_count")==1 && parentCount==1 && revealEligible(parent)
            && "android.view.ViewGroup".equals(parent.getString("class")) && parent.getString("resource_id").isEmpty()
            && parentPath.lastIndexOf('/')>0 && parentPath.substring(0,parentPath.lastIndexOf('/')).equals(controls.getString("path"))
            && Arrays.equals(crop,revealRect(parent.getJSONArray("bounds"))) && !button.getBoolean("editable")
            && button.getString("text").isEmpty() && !button.getBoolean("text_truncated") && revealInside(box,crop),
            "EXACT_CURRENT_PLAYER_DIRECT_CONTROL_REQUIRED");
        return new PlayerSelection(path,button.getString("node_sha256"),hashJson(inspection),proof);
    }
    static JSONObject playerCaptureBinding(Capture capture) throws Exception {
        return new JSONObject().put("tree_sha256",capture.json.getString("tree_sha256"))
            .put("window_sha256",capture.json.getString("window_sha256"))
            .put("connection_scoped_window_id",capture.windowId)
            .put("observed_elapsed_ms",integer(capture.json,"observed_elapsed_ms"));
    }
    void playerButton(final JSONObject request,final JSONObject result) throws Exception {
        final String transition=string(request,"transition",6);
        need("pause".equals(transition)||"resume".equals(transition),"FIXED_PLAYER_TRANSITION_REQUIRED");
        String priorNonce=string(request,"inspection_nonce",32),priorHash=string(request,"inspection_sha256",64);
        need(!priorNonce.equals(string(request,"nonce",32)) && priorHash.matches("[0-9a-f]{64}"),"PLAYER_CONTEXT_NONCE_AND_HASH");
        byte[] previousRaw=readInspection(priorNonce);need(hash(previousRaw).equals(priorHash),"PLAYER_CONTEXT_BYTES_CHANGED");
        JSONObject previous=new JSONObject(new String(previousRaw,StandardCharsets.UTF_8));
        need(PROTOCOL.equals(previous.getString("protocol")) && previous.getBoolean("ok")
            && previous.getBoolean("claim_persistence_completed") && previous.getBoolean("helper_work_completed")
            && "inspect".equals(previous.getString("op")) && priorNonce.equals(previous.getString("nonce"))
            && !previous.getBoolean("action_attempted") && previous.getJSONObject("restoration").getBoolean("service_info_verified"),
            "PLAYER_SUCCESSFUL_RESTORED_CONTEXT_REQUIRED");
        final JSONObject scope=request.getJSONObject("scope");
        need(canonical(previous.getJSONObject("host_scope_attestation")).equals(canonical(scope)),"PLAYER_CONTEXT_SCOPE_CHANGED");
        JSONObject inspected=previous.getJSONObject("inspection");
        long age=SystemClock.elapsedRealtime()-integer(inspected,"observed_elapsed_ms");
        need(age>=0 && age<=MAX_INSPECTION_AGE_MS,"PLAYER_CONTEXT_INSPECTION_TOO_OLD");
        PlayerSelection prior=playerButtonCurrent(inspected,scope,transition);
        final String frameHash=string(request,"player_frame_sha256",64);
        need(frameHash.matches("[0-9a-f]{64}") && hashJson(playerFrame(prior.proof)).equals(frameHash),"PLAYER_CONTEXT_FRAME_CHANGED");
        result.put("inspection_nonce",priorNonce).put("inspection_sha256",priorHash)
            .put("transition",transition).put("player_frame_sha256",frameHash)
            .put("prior_inspection_is_context_only",true).put("atomic_android_transaction",false);
        PlayerButtonTransaction.run(new PlayerButtonTransaction.Backend<Capture,PlayerSelection>() {
            @Override public Capture inspectSelection() throws Exception { return inspect(null,"player_selection"); }
            @Override public PlayerSelection selectCurrent(Capture first) throws Exception {
                PlayerSelection selected=playerButtonCurrent(first.json,scope,transition);
                need(hashJson(playerFrame(selected.proof)).equals(frameHash),"CURRENT_PLAYER_CONTEXT_FRAME_CHANGED");
                return selected;
            }
            @Override public Capture inspectTarget(PlayerSelection selected) throws Exception { return inspect(selected.path,"action_target"); }
            @Override public void requireSameWholeTreeAndWindow(Capture first,Capture target) throws Exception {
                need(first.windowId==target.windowId && first.json.getString("tree_sha256").equals(target.json.getString("tree_sha256"))
                    && first.json.getString("window_sha256").equals(target.json.getString("window_sha256")),
                    "CURRENT_PLAYER_TREE_OR_WINDOW_CHANGED");
            }
            @Override public void requireRefreshedTarget(Capture current,PlayerSelection selected) throws Exception {
                need(current.target!=null && current.target.refresh(),"TARGET_REFRESH_FAILED");
                need(hashJson(node(current.target,selected.path)).equals(selected.nodeHash),"TARGET_CHANGED_BEFORE_ACTION");
                need(current.target.getWindowId()==current.windowId && current.target.isEnabled()
                    && current.target.isVisibleToUser() && !current.target.isPassword(),"ACTION_TARGET_NOT_ELIGIBLE");
                need(current.target.isClickable(),"ACTION_TARGET_NOT_CLICKABLE");
            }
            @Override public Capture inspectFinal() throws Exception { return inspect(null,"action_final_window"); }
            @Override public void requireFinalWholeTreeAndWindow(Capture target,Capture last) throws Exception {
                need(last.windowId==target.windowId && last.json.getString("tree_sha256").equals(target.json.getString("tree_sha256"))
                    && last.json.getString("window_sha256").equals(target.json.getString("window_sha256")),"FOCUS_CHANGED_BEFORE_ACTION");
            }
            @Override public void bindEvidence(Capture first,Capture current,Capture last,PlayerSelection selected) throws Exception {
                result.put("player_inspection",first.json).put("player_inspection_sha256",selected.inspectionHash)
                    .put("player_scope",selected.proof).put("target_node_path",selected.path).put("target_node_sha256",selected.nodeHash)
                    .put("action_window",current.json.getJSONObject("window")).put("connection_scoped_window_id",current.windowId)
                    .put("player_capture_bindings",new JSONArray().put(playerCaptureBinding(first)).put(playerCaptureBinding(current)).put(playerCaptureBinding(last)))
                    .put("same_connection_full_tree_rechecks",2);
            }
            @Override public long selectedAt(Capture first) throws Exception { return integer(first.json,"observed_elapsed_ms"); }
            @Override public long now() { return SystemClock.elapsedRealtime(); }
            @Override public void beforeAction(long admitted,long selectionAge) throws Exception {
                timeBound();result.put("player_action_admitted_elapsed_ms",admitted).put("player_selection_age_ms",selectionAge)
                    .put("player_selection_age_limit_ms",PlayerButtonTransaction.MAX_SELECTION_AGE_MS);
            }
            @Override public boolean clickOnce(Capture current) throws Exception {
                actionAttempted=true;
                boolean acknowledged=current.target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                result.put("node_action","ACTION_CLICK").put("node_action_returned",acknowledged);
                return acknowledged;
            }
            @Override public void close(Capture capture) { capture.close(); }
        });
    }

    void act(JSONObject request, JSONObject result) throws Exception {
        final boolean editing = "set_text".equals(string(request, "op", 16));
        String priorNonce = string(request, "inspection_nonce", 32);
        need(!priorNonce.equals(string(request, "nonce", 32)), "ACTION_REQUIRES_DISTINCT_NONCE");
        String expectedHash = string(request, "inspection_sha256", 64);
        need(expectedHash.matches("[0-9a-f]{64}"), "INSPECTION_HASH_REQUIRED");
        byte[] previousRaw = readInspection(priorNonce);
        need(hash(previousRaw).equals(expectedHash), "INSPECTION_BYTES_CHANGED");
        JSONObject previous = new JSONObject(new String(previousRaw, StandardCharsets.UTF_8));
        need(PROTOCOL.equals(previous.getString("protocol")) && previous.getBoolean("ok")
             && previous.getBoolean("claim_persistence_completed") && previous.getBoolean("helper_work_completed") && "inspect".equals(previous.getString("op"))
             && priorNonce.equals(previous.getString("nonce")) && !previous.getBoolean("action_attempted"), "SUCCESSFUL_INSPECTION_REQUIRED");
        need(previous.getJSONObject("restoration").getBoolean("service_info_verified"), "INSPECTION_RESTORATION_UNVERIFIED");
        need(canonical(previous.getJSONObject("host_scope_attestation")).equals(canonical(request.getJSONObject("scope"))), "INSPECTION_HOST_SCOPE_CHANGED");
        JSONObject expected = previous.getJSONObject("inspection");
        long age = SystemClock.elapsedRealtime() - integer(expected, "observed_elapsed_ms");
        need(age >= 0 && age <= MAX_INSPECTION_AGE_MS, "INSPECTION_TOO_OLD");
        String path = string(request, "node_path", 160);
        need(path.matches("0(?:/[0-9]{1,2}){0,32}"), "EXACT_NODE_PATH_REQUIRED");
        String nodeHash = string(request, "node_sha256", 64);
        need(nodeHash.matches("[0-9a-f]{64}"), "EXACT_NODE_HASH_REQUIRED");
        Capture current = inspect(path, "action_target");
        try {
            need(current.json.getString("tree_sha256").equals(expected.getString("tree_sha256"))
                 && current.json.getString("window_sha256").equals(expected.getString("window_sha256")), "INSPECTED_TREE_OR_WINDOW_CHANGED");
            need(current.target != null && current.target.refresh(), "TARGET_REFRESH_FAILED");
            need(hashJson(node(current.target, path)).equals(nodeHash), "TARGET_CHANGED_BEFORE_ACTION");
            need(current.target.getWindowId() == current.windowId && current.target.isEnabled()
                 && current.target.isVisibleToUser() && !current.target.isPassword(), "ACTION_TARGET_NOT_ELIGIBLE");
            if (editing) {
                need(current.target.isEditable() && "android.widget.EditText".equals(text(current.target.getClassName()))
                     && string(request, "node_resource_id", 256).equals(current.target.getViewIdResourceName())
                     && supportsAction(current.target, AccessibilityNodeInfo.ACTION_SET_TEXT), "EXACT_EDITABLE_RESOURCE_REQUIRED");
            } else need(current.target.isClickable(), "ACTION_TARGET_NOT_CLICKABLE");
            Capture finalWindow = inspect(null, "action_final_window");
            try {
                need(finalWindow.windowId == current.windowId && finalWindow.json.getString("tree_sha256").equals(current.json.getString("tree_sha256")), "FOCUS_CHANGED_BEFORE_ACTION");
            } finally { finalWindow.close(); }
            timeBound(); actionAttempted = true;
            final boolean acknowledged;
            if (editing) {
                Bundle value = new Bundle();
                value.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, PUBLIC_SEARCH_QUERY);
                acknowledged = current.target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, value);
            } else acknowledged = current.target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            result.put("inspection_nonce", priorNonce).put("inspection_sha256", expectedHash)
                .put("target_node_path", path).put("target_node_sha256", nodeHash)
                .put("action_window", current.json.getJSONObject("window"))
                .put("connection_scoped_window_id", current.windowId)
                .put("node_action", editing ? "ACTION_SET_TEXT" : "ACTION_CLICK").put("node_action_returned", acknowledged);
            need(acknowledged, "ACTION_NOT_ACKNOWLEDGED_OUTCOME_UNKNOWN");
            if (editing) {
                result.put("target_resource_id", string(request, "node_resource_id", 256))
                    .put("requested_value_sha256", hash(PUBLIC_SEARCH_QUERY.getBytes(StandardCharsets.UTF_8)));
                need(current.target.refresh(), "EDIT_READBACK_REFRESH_FAILED");
                need(current.target.getWindowId() == current.windowId && current.target.isEditable()
                     && current.target.isVisibleToUser() && !current.target.isPassword()
                     && string(request, "node_resource_id", 256).equals(current.target.getViewIdResourceName()),
                     "EDIT_READBACK_TARGET_CHANGED");
                String observed = text(current.target.getText());
                need(observed.length() <= 16384, "EDIT_READBACK_TEXT_BOUND");
                result.put("observed_value_sha256", hash(observed.getBytes(StandardCharsets.UTF_8)));
                need(PUBLIC_SEARCH_QUERY.equals(observed), "EDIT_VALUE_NOT_OBSERVED");
                result.put("value_readback_verified", true);
            }
        } finally { current.close(); }
    }
}
