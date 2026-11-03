package local.pocket4.actions.v2;

import android.app.UiAutomation;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONArray;
import org.json.JSONObject;

/** Reads only public native state through the original instrumentation. */
final class OrganSnapshot {
  static final Pattern PACKAGE = Pattern.compile("[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+");
  private static final Pattern FOCUS = Pattern.compile(
      "mCurrentFocus=Window\\{([0-9a-fA-F]+)\\s+u\\d+\\s+([A-Za-z_][A-Za-z0-9_.]*)/([A-Za-z0-9_.$]+)");

  static String bounded(InputStream stream, int limit) throws Exception {
    try (InputStream input = stream; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[4096];
      for (int n; (n = input.read(buffer)) != -1;) {
        OrganJson.require(out.size() + n <= limit, "NATIVE_OBSERVATION_TOO_LARGE");
        out.write(buffer, 0, n);
      }
      return new String(out.toByteArray(), StandardCharsets.UTF_8);
    }
  }

  static String shell(UiAutomation ui, String fixedCommand, int limit) throws Exception {
    ParcelFileDescriptor descriptor = ui.executeShellCommand(fixedCommand);
    OrganJson.require(descriptor != null, "NATIVE_OBSERVATION_UNAVAILABLE");
    return bounded(new ParcelFileDescriptor.AutoCloseInputStream(descriptor), limit);
  }

  private static String ticks(UiAutomation ui, String file) throws Exception {
    OrganJson.require(file.matches("/proc/[1-9][0-9]{0,9}/stat"), "INVALID_NATIVE_PROCESS_PATH");
    String stat = shell(ui, "/system/bin/timeout -k 1 2 /system/bin/cat " + file, 8192);
    int end = stat.lastIndexOf(')');
    OrganJson.require(end > 0, "INVALID_NATIVE_PROCESS_IDENTITY");
    String[] fields = stat.substring(end + 1).trim().split("\\s+");
    OrganJson.require(fields.length >= 20 && fields[19].matches("[0-9]+"), "INVALID_NATIVE_PROCESS_IDENTITY");
    return fields[19];
  }

  static JSONObject generation(UiAutomation ui) throws Exception {
    String boot = shell(ui, "/system/bin/timeout -k 1 2 /system/bin/cat /proc/sys/kernel/random/boot_id", 64).trim();
    OrganJson.require(boot.matches("[0-9a-f-]{36}"), "INVALID_NATIVE_BOOT_ID");
    String[] namespaces = shell(ui, "/system/bin/timeout -k 1 2 /system/bin/readlink /proc/1/ns/mnt /proc/1/ns/pid /proc/1/ns/time", 512).trim().split("\\s+");
    OrganJson.require(namespaces.length == 3 && namespaces[0].matches("mnt:\\[[0-9]+\\]")
        && namespaces[1].matches("pid:\\[[0-9]+\\]") && namespaces[2].matches("time:\\[[0-9]+\\]"), "NATIVE_CELL_NAMESPACE_UNAVAILABLE");
    // App storage namespaces can differ from init. Read the production init's
    // identity through the original shell capability, never the app's own mnt.
    return new JSONObject().put("boot_id", boot).put("init_start_ticks", ticks(ui, "/proc/1/stat"))
        .put("mount_namespace", namespaces[0]).put("pid_namespace", namespaces[1]).put("time_namespace", namespaces[2]);
  }

  static JSONObject application(UiAutomation ui, String pkg) throws Exception {
    OrganJson.require(PACKAGE.matcher(pkg).matches(), "INVALID_NATIVE_PACKAGE");
    // A package with multiple main processes or an inaccessible public process
    // identity is unsupported. Never guess a PID or choose a positional match.
    String pid = shell(ui, "/system/bin/timeout -k 1 2 /system/bin/pidof " + pkg, 1024).trim();
    OrganJson.require(pid.matches("[1-9][0-9]{0,9}"), "APPLICATION_PROCESS_NOT_UNIQUE");
    return new JSONObject().put("pid", Long.parseLong(pid)).put("start_ticks", ticks(ui, "/proc/" + pid + "/stat"))
        .put("process_name", pkg);
  }

  static JSONObject window(UiAutomation ui, JSONObject selected, String pkg) throws Exception {
    OrganJson.require(selected != null && selected.getInt("display_id") == 0
        && selected.getBoolean("focused") && selected.getInt("type") == 1, "FOCUSED_NATIVE_WINDOW_REQUIRED");
    String raw = shell(ui, "/system/bin/timeout -k 1 2 /system/bin/dumpsys window displays", 262144);
    Matcher matcher = FOCUS.matcher(raw);
    JSONObject result = null;
    while (matcher.find()) {
      JSONObject found = new JSONObject().put("package", matcher.group(2)).put("activity", matcher.group(3))
          .put("window_token", matcher.group(1).toLowerCase(java.util.Locale.ROOT))
          .put("display_id", 0).put("bounds", selected.getJSONArray("bounds"));
      if (result != null) OrganJson.require(OrganJson.canonical(result).equals(OrganJson.canonical(found)), "AMBIGUOUS_NATIVE_FOCUS");
      result = found;
    }
    OrganJson.require(result != null && pkg.equals(result.getString("package")), "WINDOW_MANAGER_SCOPE_MISMATCH");
    return result;
  }

  static String value(AccessibilityNodeInfo node) {
    return node.isShowingHintText() || node.getText() == null ? "" : node.getText().toString();
  }

  static JSONObject target(AccessibilityNodeInfo node, String pkg, String resource) throws Exception {
    OrganJson.require(node != null && node.refresh() && node.isEditable() && node.isEnabled()
        && node.isVisibleToUser() && !node.isPassword(), "EXACT_VISIBLE_NONPASSWORD_EDITOR_REQUIRED");
    OrganJson.require(pkg.equals(String.valueOf(node.getPackageName()))
        && resource.equals(node.getViewIdResourceName()), "NATIVE_TARGET_SCOPE_MISMATCH");
    boolean supported = false;
    for (AccessibilityNodeInfo.AccessibilityAction action : node.getActionList())
      if (action.getId() == AccessibilityNodeInfo.ACTION_SET_TEXT) supported = true;
    OrganJson.require(supported, "NATIVE_SET_TEXT_UNSUPPORTED");
    Rect rect = new Rect();
    node.getBoundsInScreen(rect);
    JSONObject result = new JSONObject().put("resource_id", resource).put("class", String.valueOf(node.getClassName()))
        .put("bounds", new JSONArray(new int[]{rect.left, rect.top, rect.right, rect.bottom}))
        .put("prior_text_sha256", OrganJson.hash(value(node).getBytes(StandardCharsets.UTF_8)));
    return result.put("node_sha256", OrganJson.hash(result));
  }

  static String scopeHash(UiAutomation ui, JSONArray bounds) throws Exception {
    OrganJson.require(bounds.length() == 4, "INVALID_NATIVE_BOUNDS");
    Bitmap bitmap = ui.takeScreenshot();
    OrganJson.require(bitmap != null, "NATIVE_SCREENSHOT_UNAVAILABLE");
    try {
      int left = bounds.getInt(0), top = bounds.getInt(1), right = bounds.getInt(2), bottom = bounds.getInt(3);
      OrganJson.require(left >= 0 && top >= 0 && right > left && bottom > top
          && right <= bitmap.getWidth() && bottom <= bitmap.getHeight()
          && bitmap.getWidth() <= 8192 && bitmap.getHeight() <= 8192
          && (long) bitmap.getWidth() * bitmap.getHeight() <= 32000000, "INVALID_NATIVE_BOUNDS");
      int width = right - left, height = bottom - top;
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      digest.update(ByteBuffer.allocate(8).putInt(width).putInt(height).array());
      int[] row = new int[width];
      byte[] rgb = new byte[width * 3];
      for (int y = top; y < bottom; y++) {
        bitmap.getPixels(row, 0, width, left, y, width, 1);
        for (int x = 0; x < width; x++) {
          rgb[x * 3] = (byte) (row[x] >> 16);
          rgb[x * 3 + 1] = (byte) (row[x] >> 8);
          rgb[x * 3 + 2] = (byte) row[x];
        }
        digest.update(rgb);
      }
      return OrganJson.hex(digest.digest());
    } finally { bitmap.recycle(); }
  }

  static JSONObject observe(UiAutomation ui, JSONObject selected, AccessibilityNodeInfo node,
                            String pkg, String resource) throws Exception {
    JSONObject generation = generation(ui);
    JSONObject app = application(ui, pkg);
    JSONObject window = window(ui, selected, pkg);
    JSONObject target = target(node, pkg, resource);
    String scope = scopeHash(ui, window.getJSONArray("bounds"));
    OrganJson.require(OrganJson.canonical(generation).equals(OrganJson.canonical(generation(ui))), "CELL_GENERATION_CHANGED");
    OrganJson.require(OrganJson.canonical(app).equals(OrganJson.canonical(application(ui, pkg))), "APPLICATION_GENERATION_CHANGED");
    OrganJson.require(OrganJson.canonical(window).equals(OrganJson.canonical(window(ui, selected, pkg))), "WINDOW_CHANGED_NO_ACTION_TAKEN");
    OrganJson.require(OrganJson.canonical(target).equals(OrganJson.canonical(target(node, pkg, resource))), "TARGET_CHANGED_NO_ACTION_TAKEN");
    return new JSONObject().put("schema_version", 1).put("generation", generation)
        .put("application", app).put("window", window).put("target", target)
        .put("scope_sha256", scope).put("observed_elapsed_ms", SystemClock.elapsedRealtime())
        .put("atomic_snapshot", false);
  }
}
