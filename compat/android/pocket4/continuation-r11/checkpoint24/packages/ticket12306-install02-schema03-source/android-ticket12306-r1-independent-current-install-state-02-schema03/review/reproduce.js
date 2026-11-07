// Pure V8 reproduction; inputs are exact UTF-8 blobs in this immutable tree.
function reproduceSchema03(inputs) {
 const d=Function(inputs.packageDeriver+"\nreturn deriveHelperArtifactSchema03;")();
 const out=d(inputs.utility,inputs.contextDeriver,inputs.controlsFragment,"ticket12306",inputs.originalRequest);
 const H=Function(inputs.utility+"\nreturn {utf8,sha256,gitBlob};")();
 const expected={"packet":{"bytes":214054,"sha256":"7f9b9476db6713303e33a737c6b01ad4d1cfc1dc163fc9a9052c748597512871","git_blob_sha1":"e09d5541ee9f92b77689a1ac19743e92caa71888"},"request":{"bytes":226027,"sha256":"6984b2c0637dfcfddb2a7896da70370be23e666672a6c4c3e43a2b8e26d18f8e","git_blob_sha1":"b33a40bd0ee7358fe4fc9d57d3ed96894b73add6"}};
 for(const [kind,p]of Object.entries(expected)) { const s=out[kind+"Raw"]; if(p===null) {if(s!==null)throw Error("UNBOUND_REQUEST");continue;} if(H.utf8(s).length!==p.bytes||H.sha256(H.utf8(s))!==p.sha256||H.gitBlob(H.utf8(s))!==p.git_blob_sha1)throw Error("EXACT_REPRODUCTION_"+kind); }
 return out;
}
