export function reproduceRequest(files) {
  const source = files["read_source.py"];
  if (typeof source !== "string") throw new Error("missing exact reader source");
  const request = {
    host: "pocket4", executable: "/usr/bin/python3",
    args: ["-I", "-B", "-c", source], stdin: "", cwd: "/",
    cpu_quota_percent: 25, memory_max_bytes: 134217728, nice: 15,
    timeout_seconds: 15,
    idempotency_key: "pocket4-native469-retirement-four-fixed-dependencies-read01-20261106"
  };
  return JSON.stringify(request, null, 2) + "\n";
}
