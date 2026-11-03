package local.pocket4.actions.v2;

import android.app.UiAutomation;
import android.os.SystemClock;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.json.JSONObject;

/** Opt-in exact binding inside the original one-shot ActionRunner, no ledger. */
final class OrganBinding {
  private final String mode;
  private final String pkg;
  private final String resource;
  private final JSONObject hostGeneration;
  private final JSONObject payload;
  private final JSONObject expected;
  private final String payloadHash;
  private final String operation;
  private final long transportDeadline;
  private JSONObject receiverGeneration;
  private JSONObject checkedBefore;

  private OrganBinding(JSONObject request) throws Exception {
    JSONObject options = request.getJSONObject("organ");
    mode = OrganJson.string(options, "mode");
    OrganJson.require(mode.equals("observe") || mode.equals("apply") || mode.equals("readback"), "INVALID_ORGAN_MODE");
    transportDeadline = OrganJson.integer(options, "transport_expires_elapsed_ms");
    OrganJson.require(transportDeadline > SystemClock.elapsedRealtime()
        && transportDeadline - SystemClock.elapsedRealtime() <= 55000, "INVALID_ORGAN_TRANSPORT_DEADLINE");
    hostGeneration = options.getJSONObject("host_generation");
    if (mode.equals("observe")) {
      OrganJson.keys(options, "mode", "package", "resource_id", "host_generation", "transport_expires_elapsed_ms");
      pkg = OrganJson.string(options, "package");
      resource = OrganJson.string(options, "resource_id");
      payload = expected = null;
      payloadHash = operation = null;
    } else {
      OrganJson.keys(options, "mode", "payload_base64", "payload_sha256", "host_generation", "transport_expires_elapsed_ms");
      String encoded = OrganJson.string(options, "payload_base64");
      OrganJson.require(encoded.length() <= 22000, "ORGAN_PAYLOAD_TOO_LARGE");
      byte[] bytes = Base64.decode(encoded, Base64.NO_WRAP);
      OrganJson.require(bytes.length <= 16384, "ORGAN_PAYLOAD_TOO_LARGE");
      String raw = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
          .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
      payload = new JSONObject(raw);
      // Canonical equality also rejects duplicate keys, non-integer values,
      // alternate escapes and any overwritten or trailing JSON members.
      OrganJson.require(raw.equals(OrganJson.canonical(payload)), "NONCANONICAL_ORGAN_JSON");
      payloadHash = OrganJson.string(options, "payload_sha256");
      OrganJson.require(payloadHash.matches("[0-9a-f]{64}") && payloadHash.equals(OrganJson.hash(bytes)), "ORGAN_PAYLOAD_HASH_MISMATCH");
      OrganJson.keys(payload, "schema_version", "action", "operation_id", "destination_id", "observation", "value", "expires_elapsed_ms");
      OrganJson.require(OrganJson.integer(payload, "schema_version") == 1
          && OrganJson.string(payload, "action").equals("set_text"), "INVALID_ORGAN_PAYLOAD");
      operation = OrganJson.string(payload, "operation_id");
      OrganJson.require(operation.matches("[A-Za-z0-9._:-]{1,128}"), "INVALID_ORGAN_OPERATION");
      String value = OrganJson.string(payload, "value");
      OrganJson.require(value.getBytes(StandardCharsets.UTF_8).length <= 4096, "INVALID_ORGAN_TEXT");
      expected = payload.getJSONObject("observation");
      OrganJson.keys(expected, "schema_version", "generation", "application", "window", "target", "scope_sha256", "observed_elapsed_ms", "atomic_snapshot");
      OrganJson.require(OrganJson.integer(expected, "schema_version") == 1
          && expected.get("atomic_snapshot").equals(Boolean.FALSE), "INVALID_ORGAN_OBSERVATION");
      OrganJson.require(OrganJson.string(expected, "scope_sha256").matches("[0-9a-f]{64}"), "INVALID_ORGAN_HASH");
      JSONObject window = expected.getJSONObject("window");
      OrganJson.keys(window, "package", "activity", "window_token", "display_id", "bounds");
      pkg = OrganJson.string(window, "package");
      OrganJson.require(OrganJson.integer(window, "display_id") == 0
          && OrganJson.string(window, "window_token").matches("[0-9a-f]{1,32}"), "INVALID_ORGAN_WINDOW");
      JSONObject target = expected.getJSONObject("target");
      OrganJson.keys(target, "resource_id", "class", "bounds", "prior_text_sha256", "node_sha256");
      resource = OrganJson.string(target, "resource_id");
      JSONObject unhashed = new JSONObject(OrganJson.canonical(target));
      unhashed.remove("node_sha256");
      OrganJson.require(OrganJson.hash(unhashed).equals(OrganJson.string(target, "node_sha256")), "INVALID_ORGAN_NODE_HASH");
      long observed = OrganJson.integer(expected, "observed_elapsed_ms");
      long expires = OrganJson.integer(payload, "expires_elapsed_ms");
      OrganJson.require(observed <= SystemClock.elapsedRealtime() && expires > observed
          && expires - observed <= 30000, "INVALID_ORGAN_ACTION_DEADLINE");
      OrganJson.require(destination(expected).equals(OrganJson.string(payload, "destination_id")), "ORGAN_DESTINATION_MISMATCH");
    }
    OrganJson.require(OrganSnapshot.PACKAGE.matcher(pkg).matches()
        && resource.matches(java.util.regex.Pattern.quote(pkg) + ":id/[A-Za-z_][A-Za-z0-9_]*"), "EXACT_RESOURCE_ID_REQUIRED");
    OrganJson.require(OrganJson.string(request, "expected_package").equals(pkg)
        && OrganJson.integer(request, "display") == 0
        && OrganJson.string(request, "accessibility_mode").equals("none"), "ORGAN_REQUEST_SCOPE_MISMATCH");
    OrganJson.keys(request.getJSONObject("selector"), "id", "package");
    OrganJson.require(request.getJSONObject("selector").getString("id").equals(resource)
        && request.getJSONObject("selector").getString("package").equals(pkg), "ORGAN_SELECTOR_MISMATCH");
    if (mode.equals("apply")) {
      OrganJson.keys(request, "op", "expected_package", "selector", "display", "accessibility_mode", "organ", "value");
      OrganJson.require(OrganJson.string(request, "op").equals("set-text")
          && OrganJson.string(request, "value").equals(OrganJson.string(payload, "value")), "ORGAN_ACTION_MISMATCH");
    } else {
      OrganJson.keys(request, "op", "expected_package", "selector", "display", "accessibility_mode", "organ");
      OrganJson.require(OrganJson.string(request, "op").equals("find"), "ORGAN_ACTION_MISMATCH");
    }
    deadline();
  }

  static OrganBinding parse(JSONObject request) throws Exception {
    return request.has("organ") ? new OrganBinding(request) : null;
  }

  static String destination(JSONObject observation) throws Exception {
    JSONObject scope = new JSONObject().put("application", observation.getJSONObject("application"))
        .put("generation", observation.getJSONObject("generation"))
        .put("package", observation.getJSONObject("window").getString("package"))
        .put("resource_id", observation.getJSONObject("target").getString("resource_id"));
    return "pocket4.android:" + OrganJson.hash(scope);
  }

  private void deadline() throws Exception {
    long now = SystemClock.elapsedRealtime();
    OrganJson.require(now < transportDeadline, "ORGAN_DEADLINE_EXCEEDED");
    if (mode.equals("apply")) OrganJson.require(now < OrganJson.integer(payload, "expires_elapsed_ms"), "ORGAN_ACTION_DEADLINE_EXCEEDED");
  }

  private void generation(JSONObject observed) throws Exception {
    receiverGeneration = observed.getJSONObject("generation");
    OrganJson.require(OrganJson.canonical(receiverGeneration).equals(OrganJson.canonical(hostGeneration)), "RECEIVER_CELL_GENERATION_MISMATCH");
    if (expected == null) return;
    for (String name : new String[]{"generation", "application", "window"})
      OrganJson.require(OrganJson.canonical(expected.get(name)).equals(OrganJson.canonical(observed.get(name))),
          name.equals("generation") ? "CELL_GENERATION_CHANGED" : name.equals("application") ? "APPLICATION_GENERATION_CHANGED" : "WINDOW_CHANGED_NO_ACTION_TAKEN");
    JSONObject target = observed.getJSONObject("target"), prior = expected.getJSONObject("target");
    for (String name : new String[]{"resource_id", "class", "bounds"})
      OrganJson.require(OrganJson.canonical(target.get(name)).equals(OrganJson.canonical(prior.get(name))), "TARGET_CHANGED_NO_ACTION_TAKEN");
  }

  JSONObject read(UiAutomation ui, JSONObject selected, List<AccessibilityNodeInfo> found,
                  boolean complete) throws Exception {
    deadline();
    OrganJson.require(!mode.equals("apply") && complete && found.size() == 1, "EXACT_COMPLETE_NATIVE_MATCH_REQUIRED");
    JSONObject observation = OrganSnapshot.observe(ui, selected, found.get(0), pkg, resource);
    generation(observation);
    deadline();
    JSONObject result = new JSONObject().put("ok", true).put("observation", observation)
        .put("destination_id", destination(observation)).put("action_submitted", false)
        .put("independent_readback", mode.equals("readback")).put("causal_receipt_persisted", false)
        .put("business_success_verified", false).put("automatic_retry", false);
    if (mode.equals("readback")) result.put("state_matches_requested_value",
        observation.getJSONObject("target").getString("prior_text_sha256").equals(
            OrganJson.hash(OrganJson.string(payload, "value").getBytes(StandardCharsets.UTF_8))))
        .put("terminal_outcome", "unproven");
    return decorate(result);
  }

  void beforeAction(UiAutomation ui, JSONObject selected, AccessibilityNodeInfo node) throws Exception {
    OrganJson.require(mode.equals("apply"), "ORGAN_READ_ONLY_MODE");
    deadline();
    checkedBefore = OrganSnapshot.observe(ui, selected, node, pkg, resource);
    generation(checkedBefore);
    OrganJson.require(OrganJson.canonical(expected.getJSONObject("target")).equals(
        OrganJson.canonical(checkedBefore.getJSONObject("target"))), "TARGET_PREDECESSOR_CHANGED");
    OrganJson.require(expected.getString("scope_sha256").equals(checkedBefore.getString("scope_sha256")), "STALE_NATIVE_SCOPE");
    // Fresh node, real WindowManager token, application start time and cell
    // identity were all re-read above. The final deadline check is adjacent
    // to the original performAction; no caller-side success is accepted.
    deadline();
  }

  JSONObject completed(JSONObject original) throws Exception {
    deadline();
    OrganJson.require(checkedBefore != null && original.getBoolean("readback_verified")
        && !original.getBoolean("password"), "ORGAN_POSTCONDITION_UNKNOWN");
    return decorate(original.put("action_submitted", true).put("receiver_preconditions_checked", true)
        .put("postcondition_observed", true).put("independent_readback_required", true)
        .put("receiver_action_observed_elapsed_ms", SystemClock.elapsedRealtime())
        .put("causal_receipt_persisted", false).put("business_success_verified", false)
        .put("automatic_retry", false));
  }

  JSONObject decorate(JSONObject result) throws Exception {
    result.put("organ_protocol", "pocket4-bound-text-v1");
    if (receiverGeneration != null) result.put("receiver_generation", receiverGeneration);
    if (operation != null) result.put("operation_id", operation).put("payload_sha256", payloadHash);
    return result;
  }
}
