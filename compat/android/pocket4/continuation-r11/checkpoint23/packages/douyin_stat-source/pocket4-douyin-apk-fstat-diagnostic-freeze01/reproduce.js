function reproduce(files) {
  const H=Function(files["pure-js-binary.js"]+"\nreturn {utf8,sha256,gitBlob};")();
  const D=Function("return ("+files["diff-util.js"]+")")();
  const derive=Function("return ("+files["derive.js"]+")")();
  const output=derive({
    template:files["read_apk_metadata.template.py"],
    fixed:JSON.parse(files["fixed-binding.json"]),
    original_report:files["references/actual/result.original.json"],
    original_source:files["references/metadata-source.original.py"],
    original_request:files["references/metadata-request.original.json"],
    key:"pocket4-current-cell02-douyin-apk-fstat-diagnostic-01-20261106"
  },H,D);
  for(const [name,raw] of Object.entries(output))
    if(files[name]!==raw)throw Error("reproduction differs: "+name);
  const q=JSON.parse(files["exact-request.json"]);
  if(q.stdin!==files["read_apk_metadata.py"]||q.stdin!==files["exact-stdin.py"]||
     q.args[5]!==files["transport.py"])throw Error("request wire mismatch");
  return {ok:true,reproduced:Object.keys(output),source_bytes:H.utf8(q.stdin).length,
    source_sha256:H.sha256(H.utf8(q.stdin)),
    request_bytes:H.utf8(files["exact-request.json"]).length,
    request_sha256:H.sha256(H.utf8(files["exact-request.json"])),
    Python_compilation:"NOT_PERFORMED",device_execution:"UNRUN",App_nonce_consumed:0};
}
