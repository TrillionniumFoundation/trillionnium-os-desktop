package local.pocket4.actions.v2;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;

/** Exact UTF-8 wire identity, shared with the canonical Python owner proposal. */
final class OrganJson {
  static void require(boolean condition, String code) {
    if (!condition) throw new IllegalArgumentException(code);
  }

  static String hash(byte[] bytes) throws Exception {
    return hex(MessageDigest.getInstance("SHA-256").digest(bytes));
  }

  static String hex(byte[] bytes) {
    StringBuilder out = new StringBuilder(bytes.length * 2);
    for (byte b : bytes) out.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
    return out.toString();
  }

  static String hash(Object value) throws Exception {
    return hash(canonical(value).getBytes(StandardCharsets.UTF_8));
  }

  static void keys(JSONObject object, String... names) {
    require(object.length() == names.length, "UNKNOWN_ORGAN_FIELD");
    for (String name : names) require(object.has(name), "MISSING_ORGAN_FIELD");
  }

  static String string(JSONObject object, String name) throws Exception {
    Object value = object.get(name);
    require(value instanceof String, "INVALID_ORGAN_STRING");
    String result = (String) value;
    require(result.indexOf('\0') < 0, "INVALID_ORGAN_STRING");
    canonical(result); // Reject unpaired UTF-16 surrogates before encoding.
    return result;
  }

  static long integer(JSONObject object, String name) throws Exception {
    Object value = object.get(name);
    require(value instanceof Integer || value instanceof Long, "INVALID_ORGAN_INTEGER");
    long result = ((Number) value).longValue();
    require(result >= 0 && result < (1L << 53), "INVALID_ORGAN_INTEGER");
    return result;
  }

  static String canonical(Object value) throws Exception {
    if (value instanceof JSONObject) {
      JSONObject object = (JSONObject) value;
      List<String> keys = new ArrayList<>();
      for (Iterator<String> it = object.keys(); it.hasNext();) keys.add(it.next());
      Collections.sort(keys);
      StringBuilder out = new StringBuilder("{");
      for (String key : keys) {
        if (out.length() > 1) out.append(',');
        out.append(canonical(key)).append(':').append(canonical(object.get(key)));
      }
      return out.append('}').toString();
    }
    if (value instanceof JSONArray) {
      JSONArray array = (JSONArray) value;
      StringBuilder out = new StringBuilder("[");
      for (int i = 0; i < array.length(); i++) {
        if (i > 0) out.append(',');
        out.append(canonical(array.get(i)));
      }
      return out.append(']').toString();
    }
    if (value instanceof String) {
      StringBuilder out = new StringBuilder("\"");
      String text = (String) value;
      for (int i = 0; i < text.length(); i++) {
        char c = text.charAt(i);
        if (Character.isHighSurrogate(c)) {
          require(i + 1 < text.length() && Character.isLowSurrogate(text.charAt(i + 1)), "INVALID_UTF16");
          out.append(c).append(text.charAt(++i));
        } else if (Character.isLowSurrogate(c)) {
          throw new IllegalArgumentException("INVALID_UTF16");
        } else {
          switch (c) {
            case '"': out.append("\\\""); break;
            case '\\': out.append("\\\\"); break;
            case '\b': out.append("\\b"); break;
            case '\f': out.append("\\f"); break;
            case '\n': out.append("\\n"); break;
            case '\r': out.append("\\r"); break;
            case '\t': out.append("\\t"); break;
            default:
              if (c < 32) out.append(String.format(java.util.Locale.ROOT, "\\u%04x", (int) c));
              else out.append(c);
          }
        }
      }
      return out.append('"').toString();
    }
    if (value == JSONObject.NULL) return "null";
    if (value instanceof Boolean) return value.toString();
    require(value instanceof Integer || value instanceof Long, "NONINTEGER_ORGAN_JSON");
    return value.toString();
  }
}
