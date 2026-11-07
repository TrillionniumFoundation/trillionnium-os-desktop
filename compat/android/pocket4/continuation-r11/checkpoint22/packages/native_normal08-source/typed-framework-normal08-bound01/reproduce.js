"use strict";
// Pure V8 function. 'archive' is the exact UTF-8 file map under this frozen prefix.
// Immutable Git/SHA source qualification is performed before invoking this function.
function reproduceNormal08(archive) {
  const need=(ok,m)=>{if(!ok)throw Error(m);};
  const H=Function(archive["references/pure_git_hash.js"]+"\nreturn {utf8,sha256,gitBlob};")();
  const actual=JSON.parse(archive["stdin.json"]),template={};
  for(const [name,raw]of Object.entries(actual.files)) if(name!=="actual-builder471-result.json")template[name]=raw;
  template["framework_build.py"]=archive["template/framework_build.py"];
  template["fenced_build.py"]=archive["template/fenced_build.py"];
  const bind=Function(archive["bind_normal08.js"]+"\nreturn bindNormal08;")();
  const out=bind(template,archive["packet/actual-builder471-result.json"],archive["actual471-stdout.original.json"],archive["references/normal07-exact-request.json"],H);
  need(out.requestText===archive["exact-request.json"]&&out.wire===archive["stdin.json"]&&out.stage===archive["stage.py"]&&out.boundary===archive["transport.py"],"exact request reproduction differs");
  for(const [n,s]of Object.entries(out.files))need(s===archive["packet/"+n],"packet leaf differs: "+n);
  return out.proof;
}
