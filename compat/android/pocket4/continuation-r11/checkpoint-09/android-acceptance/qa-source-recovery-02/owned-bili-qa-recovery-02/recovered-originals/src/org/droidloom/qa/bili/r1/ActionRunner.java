package org.droidloom.qa.bili.r1;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Instrumentation;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.ResolveInfo;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;
import android.util.Base64;
import android.view.accessibility.AccessibilityManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import android.app.UiAutomation;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;
import org.json.JSONArray;
import org.json.JSONObject;

/** An owned self-instrumentation; it never instruments the commercial app. */
public final class ActionRunner extends Instrumentation {
    static final String PROTOCOL = "pocket4-owned-bili-qa-v1";
    static final String PACKAGE = "tv.danmaku.bili";
    static final String SELF = "org.droidloom.qa.bili.r1";
    static final String MAIN_EPOCH = "48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f";
    static final int TARGET_UID = 10117;
    static final int MAX_REQUEST = 16384, MAX_RESULT = 262144;
    static final int MAX_NODES = 128, MAX_DEPTH = 24, MAX_CHILDREN = 64;
    static final long DEADLINE_MS = 8000, WATCHDOG_MS = 12000, MAX_INSPECTION_AGE_MS = 10000;
    private Bundle arguments;
    private volatile boolean finished;
    private long started;
    private boolean actionAttempted;
    private UiAutomation automation;
    private int originalFlags, originalCapabilities;
    private boolean originalServiceInfoCaptured;
    private final JSONObject restoration = new JSONObject();

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
            else throw new Rejected("UNSUPPORTED_OPERATION");
            need(PROTOCOL.equals(string(request, "protocol", 64)), "PROTOCOL_MISMATCH");
            nonce = string(request, "nonce", 32);
            need(nonce.matches("[0-9a-f]{32}"), "EXACT_NONCE_REQUIRED");
            need(SELF.equals(getContext().getPackageName()) && SELF.equals(getTargetContext().getPackageName()), "SELF_INSTRUMENTATION_REQUIRED");
            need(Process.myUid() / 100000 == 0, "USER_ZERO_REQUIRED");
            result.put("protocol", PROTOCOL).put("nonce", nonce).put("op", op).put("request_sha256", hash(raw));
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
                    Capture captured = inspect(null);
                    try { result.put("inspection", captured.json); }
                    finally { captured.close(); }
                } else click(request, result);
            }
        } catch (Exception error) { primary = error; }
        finally {
            try { restoreOwnServiceInfo(); }
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
            // The adapter must observe the state AFTER am instrument terminates. The helper
            // cannot honestly assert that framework connection teardown has already completed.
            result.put("accessibility_mode_restoration_verified", JSONObject.NULL);
            result.put("requires_post_termination_state_check", automation != null);
            result.put("helper_work_completed", true).put("finished_elapsed_ms", SystemClock.elapsedRealtime());
            byte[] output = canonical(result).getBytes(StandardCharsets.UTF_8);
            need(output.length <= MAX_RESULT, "RESULT_BOUND");
            if (claimed) writeNew(nonce + ".result.json", output);
            Bundle bundle = new Bundle();
            bundle.putString("owned_qa_result_base64", Base64.encodeToString(output, Base64.NO_WRAP));
            // Keep the watchdog armed through framework teardown. Its return and the
            // command's actual termination are separately assessed by the host adapter.
            finish(primary == null ? -1 : 0, bundle);
            finished = true;
        } catch (Exception outputError) {
            // A lost/partial result is unknown, never an automatically retryable action.
            Process.killProcess(Process.myPid());
        }
    }

    static String errorCode(Exception error) {
        return error instanceof Rejected ? error.getMessage() : "EXCEPTION_" + error.getClass().getSimpleName();
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
        keys(scope, "package", "uid", "user", "activity", "window_token", "main_epoch_sha256");
        need(PACKAGE.equals(string(scope, "package", 64)) && integer(scope, "uid") == TARGET_UID && integer(scope, "user") == 0, "EXACT_BILI_SCOPE_REQUIRED");
        need(string(scope, "activity", 256).matches("tv\\.danmaku\\.bili/[A-Za-z0-9_.$]+"), "HOST_ACTIVITY_ATTESTATION_REQUIRED");
        need(string(scope, "window_token", 32).matches("[0-9a-f]{1,32}"), "HOST_WINDOW_TOKEN_REQUIRED");
        need(MAIN_EPOCH.equals(string(scope, "main_epoch_sha256", 64)), "HOST_EPOCH_ATTESTATION_REQUIRED");
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
    JSONObject node(AccessibilityNodeInfo value, String path) throws Exception {
        need(PACKAGE.equals(text(value.getPackageName())), "CROSS_PACKAGE_NODE");
        JSONObject out = new JSONObject();
        out.put("path", path).put("package", PACKAGE).put("enabled", value.isEnabled()).put("clickable", value.isClickable())
            .put("visible", value.isVisibleToUser()).put("focused", value.isFocused()).put("selected", value.isSelected())
            .put("checked", value.isChecked()).put("password", value.isPassword()).put("child_count", value.getChildCount());
        textField(out, "resource_id", value.getViewIdResourceName()); textField(out, "class", value.getClassName());
        // Password text and content descriptions are never read or hashed.
        if (!value.isPassword() && value.isVisibleToUser()) { textField(out, "text", value.getText()); textField(out, "content_desc", value.getContentDescription()); }
        else out.put("content_redacted", true);
        Rect box = new Rect(); value.getBoundsInScreen(box); out.put("bounds", bounds(box)); return out;
    }
    void walk(AccessibilityNodeInfo value, String path, int depth, JSONArray rows, Capture capture, String wanted) throws Exception {
        timeBound(); need(depth <= MAX_DEPTH && rows.length() < MAX_NODES, "TREE_NODE_OR_DEPTH_BOUND");
        need(value.getChildCount() >= 0 && value.getChildCount() <= MAX_CHILDREN, "TREE_CHILD_BOUND");
        JSONObject row = node(value, path); row.put("node_sha256", hashJson(row)); rows.put(row);
        if (path.equals(wanted)) { need(capture.target == null, "AMBIGUOUS_NODE_PATH"); capture.target = AccessibilityNodeInfo.obtain(value); }
        if (value.isPassword() || !value.isVisibleToUser()) return;
        for (int n = 0; n < value.getChildCount(); n++) {
            AccessibilityNodeInfo child = value.getChild(n); need(child != null, "TREE_CHANGED_NULL_CHILD");
            try { walk(child, path + "/" + n, depth + 1, rows, capture, wanted); }
            finally { child.recycle(); }
        }
    }
    Capture inspect(String wanted) throws Exception {
        timeBound(); List<AccessibilityWindowInfo> windows = automation.getWindows();
        need(windows != null && windows.size() <= 32, "WINDOW_LIST_BOUND");
        AccessibilityWindowInfo chosen = null;
        AccessibilityNodeInfo root = null;
        Capture capture = new Capture(new JSONObject());
        try {
            for (AccessibilityWindowInfo window : windows) {
                if (window.getDisplayId() == 0 && window.isFocused() && window.getType() == AccessibilityWindowInfo.TYPE_APPLICATION) {
                    need(chosen == null, "AMBIGUOUS_FOCUSED_APPLICATION_WINDOW"); chosen = window;
                }
            }
            need(chosen != null, "NO_FOCUSED_APPLICATION_WINDOW"); root = chosen.getRoot();
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
            need(canonical(capture.json).getBytes(StandardCharsets.UTF_8).length <= MAX_RESULT - 16384, "TREE_RESULT_BOUND");
            return capture;
        } catch (Exception error) { capture.close(); throw error; }
        finally {
            if (root != null) root.recycle();
            for (AccessibilityWindowInfo window : windows) window.recycle();
        }
    }
    void click(JSONObject request, JSONObject result) throws Exception {
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
        need(path.matches("0(?:/[0-9]{1,2}){0,24}"), "EXACT_NODE_PATH_REQUIRED");
        String nodeHash = string(request, "node_sha256", 64);
        need(nodeHash.matches("[0-9a-f]{64}"), "EXACT_NODE_HASH_REQUIRED");
        Capture current = inspect(path);
        try {
            need(current.json.getString("tree_sha256").equals(expected.getString("tree_sha256"))
                 && current.json.getString("window_sha256").equals(expected.getString("window_sha256")), "INSPECTED_TREE_OR_WINDOW_CHANGED");
            need(current.target != null && current.target.refresh(), "TARGET_REFRESH_FAILED");
            need(hashJson(node(current.target, path)).equals(nodeHash), "TARGET_CHANGED_BEFORE_ACTION");
            need(current.target.getWindowId() == current.windowId && current.target.isEnabled() && current.target.isClickable()
                 && current.target.isVisibleToUser() && !current.target.isPassword(), "ACTION_TARGET_NOT_ELIGIBLE");
            Capture finalWindow = inspect(null);
            try {
                need(finalWindow.windowId == current.windowId && finalWindow.json.getString("tree_sha256").equals(current.json.getString("tree_sha256")), "FOCUS_CHANGED_BEFORE_ACTION");
            } finally { finalWindow.close(); }
            timeBound(); actionAttempted = true;
            boolean acknowledged = current.target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            result.put("inspection_nonce", priorNonce).put("inspection_sha256", expectedHash)
                .put("target_node_path", path).put("target_node_sha256", nodeHash)
                .put("action_window", current.json.getJSONObject("window"))
                .put("connection_scoped_window_id", current.windowId)
                .put("node_action", "ACTION_CLICK").put("node_action_returned", acknowledged);
            need(acknowledged, "CLICK_NOT_ACKNOWLEDGED_OUTCOME_UNKNOWN");
        } finally { current.close(); }
    }
}
