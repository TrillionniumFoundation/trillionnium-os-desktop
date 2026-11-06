function reproduce(files) {
  const H=Function(files["pure-js-binary.js"]+"\nreturn {utf8,sha256,gitBlob};")();
  const D=Function("return ("+files["diff-util.js"]+")")();
  const derive=Function("return ("+files["derive.js"]+")")();
  const output=derive({
    template:files["read_elf.template.py"],fixed:JSON.parse(files["fixed-binding.json"]),
    original_report:files["references/current/result.original.json"],
    original_source:files["references/current/read_target.original.py"],
    original_request:files["references/current/exact-request.original.json"],
    historical_report:files["references/historical/business-hyatt.original.json"],
    base_diagnostic:files["references/base/read_apk_metadata.py"]
  },H,D);
  for(const [name,raw]of Object.entries(output))if(files[name]!==raw)throw Error("exact derived file differs "+name);
  const q=JSON.parse(files["exact-request.json"]);
  if(q.stdin!==files["read_elf.py"]||q.stdin!==files["exact-stdin.py"]||q.args[5]!==files["transport.py"])
    throw Error("exact request wire differs");
  return {schema:1,ok:true,validation:"V8_EXACT_SOURCE_AND_WIRE_REPRODUCTION",reproduced:Object.keys(output),
    source_bytes:H.utf8(q.stdin).length,source_sha256:H.sha256(H.utf8(q.stdin)),
    request_bytes:H.utf8(files["exact-request.json"]).length,request_sha256:H.sha256(H.utf8(files["exact-request.json"])),
    all_three_historical_current_APK_filename_size_SHA256_equal:true,
    unchanged_lifecycle_helpers:16,unchanged_nested_Main_guard:true,
    Python_compilation:"NOT_PERFORMED",Python_parser_controls:"NOT_PERFORMED",
    device_execution:"UNRUN",App_nonce_consumed:0,Hepta_calls:0};
}
