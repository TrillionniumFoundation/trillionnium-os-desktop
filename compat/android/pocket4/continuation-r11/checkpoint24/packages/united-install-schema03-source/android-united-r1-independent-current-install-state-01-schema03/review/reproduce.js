// Pure V8 reproduction; inputs are exact UTF-8 blobs in this immutable tree.
function reproduceSchema03(inputs) {
 const d=Function(inputs.packageDeriver+"\nreturn deriveHelperArtifactSchema03;")();
 const out=d(inputs.utility,inputs.contextDeriver,inputs.controlsFragment,"united",inputs.originalRequest);
 const H=Function(inputs.utility+"\nreturn {utf8,sha256,gitBlob};")();
 const expected={"packet":{"bytes":216675,"sha256":"5b448074bee9caa56e1a798048f20172f3fce49df67f806dc3bb0e91fd45c70d","git_blob_sha1":"006d553d33daaea187adb73e8d12c556e8219b55"},"request":{"bytes":228965,"sha256":"bedce3b896b3ab6a48d2d4b9716a1a25dd3424d0d67e53a55643c63d53aebd7b","git_blob_sha1":"d48f30f8d1565663c7fc5c56bd66f83b4d599f1f"}};
 for(const [kind,p]of Object.entries(expected)) { const s=out[kind+"Raw"]; if(p===null) {if(s!==null)throw Error("UNBOUND_REQUEST");continue;} if(H.utf8(s).length!==p.bytes||H.sha256(H.utf8(s))!==p.sha256||H.gitBlob(H.utf8(s))!==p.git_blob_sha1)throw Error("EXACT_REPRODUCTION_"+kind); }
 return out;
}
