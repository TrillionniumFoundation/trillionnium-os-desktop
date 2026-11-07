// Pure V8 reproduction; inputs are exact UTF-8 blobs in this immutable tree.
function reproduceSchema03(inputs) {
 const d=Function(inputs.packageDeriver+"\nreturn deriveHelperArtifactSchema03;")();
 const out=d(inputs.utility,inputs.contextDeriver,inputs.controlsFragment,"hilton",inputs.originalRequest);
 const H=Function(inputs.utility+"\nreturn {utf8,sha256,gitBlob};")();
 const expected={"packet":{"bytes":216900,"sha256":"fdf6357bbdd199c7302aeee1c625db2f5c41dc667a73afbd7d0c9e7c98de250b","git_blob_sha1":"8643968d77bf0318a1fd1c05d93fba4a7d080ccd"},"request":null};
 for(const [kind,p]of Object.entries(expected)) { const s=out[kind+"Raw"]; if(p===null) {if(s!==null)throw Error("UNBOUND_REQUEST");continue;} if(H.utf8(s).length!==p.bytes||H.sha256(H.utf8(s))!==p.sha256||H.gitBlob(H.utf8(s))!==p.git_blob_sha1)throw Error("EXACT_REPRODUCTION_"+kind); }
 return out;
}
