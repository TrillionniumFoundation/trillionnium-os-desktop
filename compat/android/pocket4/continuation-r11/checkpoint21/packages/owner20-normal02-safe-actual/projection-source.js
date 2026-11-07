"use strict";
// Pure V8 projection only. No filesystem, network, process, or device APIs.
// Bind utf8 and sha256 from pure-JS utility blob 443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d.
function projectOwner20Runtime(raw, expected) {
  const fail = (message) => { throw new Error(message); };
  const require = (value, message) => { if (!value) fail(message); };
  const pin = (text) => { const bytes = utf8(text); return {bytes: bytes.length, sha256: sha256(bytes)}; };
  require(typeof raw === "string" && expected && Number.isSafeInteger(expected.bytes) &&
          expected.bytes > 0 && expected.bytes <= 5 * 1024 * 1024 &&
          /^[0-9a-f]{64}$/.test(expected.sha256), "OWNER20_EXPECTED_PIN");
  const actual = pin(raw);
  require(actual.bytes === expected.bytes && actual.sha256 === expected.sha256, "OWNER20_RAW_PIN");
  const value = JSON.parse(raw, (key, item, context) =>
    typeof item === "number" && !Number.isSafeInteger(item) ? JSON.rawJSON(context.source) : item);
  require(value && !Array.isArray(value) && value.schema === 1 &&
          value.kind === "owner07-normal-external-coordinator01" &&
          value.attempt_nonce === "01fc54ac9d2954bfc4700ab4ef3af465200114dc8eaa887f8ab440584b8d41a5" &&
          value.prepared_sha256 === "cc0b414a8b0c832d3259d2e9dee03e92fbe5227e2c937427ba411416521e73d8",
          "OWNER20_RUNTIME_IDENTITY");
  const phases = new Set(["start_response", "latest_status", "active_response",
                          "stop_response", "retained_status", "failure_cleanup_stop"]);
  const keys = ["ro.build.version.sdk", "ro.build.version.sdk_full",
                "ro.system.build.version.sdk", "ro.system.build.version.sdk_full"];
  const removed = [], sdk = [];
  const decodeHex = (text, max) => {
    require(typeof text === "string" && text.length % 2 === 0 &&
            text.length / 2 <= max && /^[0-9a-f]*$/.test(text), "OWNER20_HEX_SHAPE");
    const out = new Uint8Array(text.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = Number.parseInt(text.slice(i * 2, i * 2 + 2), 16);
    return out;
  };
  const pathText = (path) => path.map(String).join(".");
  function projectNode(node, path, parent) {
    if (node === null || typeof node !== "object" || JSON.isRawJSON(node)) return node;
    if (Array.isArray(node)) return node.map((x, i) => projectNode(x, [...path, i], node));
    const out = {};
    for (const [key, item] of Object.entries(node)) {
      const childPath = [...path, key];
      if (key === "captured_hex") {
        require(path.length === 4 && path[0] === "actor_result" &&
                phases.has(path[1]) && path[2] === "relay_lifecycle" && path[3] === "init_log",
                "OWNER20_UNEXPECTED_CAPTURE_PATH");
        const bytes = decodeHex(item, 262144);
        require(node.capacity_bytes === 262144 && node.captured_bytes === bytes.length &&
                node.captured_sha256 === sha256(bytes), "OWNER20_INIT_CAPTURE_PIN");
        const omitted = {private_capture_omitted: true, decoded_bytes: bytes.length,
                         decoded_sha256: sha256(bytes)};
        out[key] = omitted;
        removed.push({path: pathText(childPath), ...omitted});
      } else if (key === "value_hex") {
        require(path.length === 5 && path[0] === "actor_result" &&
                path[1] === "property_visibility_observation" &&
                ["root_observation", "uid1069_received_unqualified", "uid1069_observation"].includes(path[2]) &&
                path[3] === "values" && Number.isInteger(path[4]) && path[4] >= 0 && path[4] < 4 &&
                node.key === keys[path[4]], "OWNER20_UNEXPECTED_PROPERTY_PATH");
        require(Number.isInteger(node.return) && node.return >= 0 && node.return <= 91,
                "OWNER20_PROPERTY_LENGTH");
        const bytes = decodeHex(item, 91);
        require(bytes.length === node.return && !bytes.includes(0), "OWNER20_PROPERTY_ENCODING");
        let text = "";
        for (const byte of bytes) text += String.fromCharCode(byte);
        const publicNumeric = /^(?:[0-9]+(?:\.[0-9]+)?)?$/.test(text);
        const projected = {raw_property_hex_omitted: true, bytes: bytes.length,
                           sha256: sha256(bytes), public_numeric_literal: publicNumeric ? text : null};
        out[key] = projected;
        sdk.push({path: pathText(childPath), key: node.key, ...projected});
      } else {
        if (key.endsWith("_hex")) {
          require(["hello_wire_hex", "wire_hex", "first_four_bytes_hex"].includes(key) &&
                  typeof item === "string" && /^[0-9a-f]+$/.test(item) &&
                  item.length === (key === "first_four_bytes_hex" ? 8 : 256),
                  "OWNER20_UNEXPECTED_HEX_FIELD");
        }
        require(!/(?:base64|_b64)$/.test(key), "OWNER20_UNEXPECTED_BASE64_FIELD");
        require(!["captured_base64", "packet_hex", "packet_base64", "stderr_hex",
                  "stderr_base64", "raw_init_log", "raw_packet_bytes"].includes(key),
                "OWNER20_UNEXPECTED_RAW_FIELD");
        out[key] = projectNode(item, childPath, node);
      }
    }
    return out;
  }
  const runtime = projectNode(value, [], null);
  return {
    schema: "owner20-runtime-safe-projection-v1",
    scope: "Pure in-memory projection of one externally pinned Owner20 original runtime; no runtime qualification.",
    original_runtime: actual,
    original_full_hash_and_bytes_verified: true,
    not_original_report_bytes: true,
    lossless_number_representation: "Original JSON numeric tokens preserved; no floating-point rounding of metadata.",
    omitted_private_fields: removed,
    public_sdk_value_projections: sdk,
    raw_init_log_or_crash_packet_exported: false,
    root_warmed_cache_limitation_preserved: true,
    new_runtime_qualification_granted: false,
    runtime
  };
}
