package org.droidloom.qa.amazon.r4;

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
    static final String PROTOCOL = "pocket4-owned-amazon-qa-v4";
    static final String PACKAGE = "com.amazon.mShop.android.shopping";
    static final String SELF = "org.droidloom.qa.amazon.r4";
    static final String MAIN_EPOCH = "7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c";
    static final String MAIN_BASELINE_SCHEMA = "pocket4-main-current-baseline-v2";
    static final String MAIN_BASELINE_SHA = "633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364";
    static final String MAIN_BASELINE_QUALIFICATION_SHA = "ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e";
    static final int TARGET_UID = 10129;
    static final int MAX_REQUEST = 16384, MAX_RESULT = 524288, MAX_COMPRESSED_WIRE = 262144;
    static final int MAX_NODES = 512, MAX_DEPTH = 32, MAX_CHILDREN = 64;
    static final String PUBLIC_SEARCH_QUERY = "usb c cable";
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
            if (op.equals("state")) keys(request, "protocol", "nonce", "op");
            else if (op.equals("inspect")) keys(request, "protocol", "nonce", "op", "scope");
            else if (op.equals("click")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "node_path", "node_sha256");
            else if (op.equals("set_text")) {
                keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "node_path", "node_sha256", "node_resource_id", "value");
                need(PUBLIC_SEARCH_QUERY.equals(string(request, "value", 64)), "ONLY_FIXED_PUBLIC_SEARCH_QUERY_ALLOWED");
                need(string(request, "node_resource_id", 256).matches("com\\.amazon\\.mShop\\.android\\.shopping:id/[A-Za-z0-9_]+"), "EXACT_EDIT_RESOURCE_REQUIRED");
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
                } else act(request, result);
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
        return error instanceof Rejected || error instanceof InspectionIdleGate.Fault ? error.getMessage() : "EXCEPTION_" + error.getClass().getSimpleName();
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
        keys(scope, "package", "uid", "user", "display", "activity", "window_token", "main_epoch_sha256", "main_baseline_schema", "main_baseline_sha256", "main_baseline_qualification_sha256");
        need(PACKAGE.equals(string(scope, "package", 64)) && integer(scope, "uid") == TARGET_UID
            && integer(scope, "user") == 0 && integer(scope, "display") == 0, "EXACT_BILI_SCOPE_REQUIRED");
        need(string(scope, "activity", 256).matches("com\\.amazon\\.mShop\\.android\\.shopping/[A-Za-z0-9_.$]+"), "HOST_ACTIVITY_ATTESTATION_REQUIRED");
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
