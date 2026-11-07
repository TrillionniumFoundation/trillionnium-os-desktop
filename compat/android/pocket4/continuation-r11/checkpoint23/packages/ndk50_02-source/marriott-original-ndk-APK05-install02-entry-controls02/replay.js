// Pure actual replay. Does not invoke the resulting control request or install anything.
const ACTUAL={
  "readonly": {
    "stdout_pin": {
      "bytes": 6407,
      "sha256": "7ff0ed239e77335b04c1b4197eab194ed108d75d2deff8673185a3ee0c7d5256"
    },
    "terminal_pin": {
      "bytes": 731,
      "sha256": "8f02badd8c546fb2aba3e58a2ceab3f23d99811d8c1e6e142d92d1f93b3ad804"
    },
    "job_id": "1a1b2ce69a8-fc05-7fd6"
  },
  "nonce": {
    "stdout_pin": {
      "bytes": 796,
      "sha256": "8cad97eca9ec88beb9a2e7e285f9a61eeb752bac01058ac4e4afc6af9addf960"
    },
    "terminal_pin": {
      "bytes": 729,
      "sha256": "52e68d12c4fd510a66342540c96fa26f2ee04d6a99b314c036782930b96c21e7"
    },
    "job_id": "1a1b2d0e7ab-fc05-7fdf"
  },
  "global_after_pin": {
    "bytes": 35039,
    "sha256": "31d5455e4c3cbe6f1951d032a45d94c442c2535ce3eddc3f745769f7a8969520"
  }
};
const OUTPUTS={
  "manifestRaw": {
    "bytes": 1054,
    "sha256": "684209fb84cf81921a1c65e8c52c7bf95db87ca0167d46badf8a8d974a2ba237",
    "git_blob_sha1": "4ce32c5c8c59b9733506fd28b0568bdf7a679f9b"
  },
  "basePacketRaw": {
    "bytes": 235774,
    "sha256": "1de1413339cf1bc6150164e2a8feaa133c917cfac8af805249d4216d75683057",
    "git_blob_sha1": "b9af0c4b7e710c61a93a5f80cd54c81a49261605"
  },
  "controlsPacketRaw": {
    "bytes": 182714,
    "sha256": "e72d255c7e80ecf33309079077816f8497a604acf3d3f54d048dc78bfac1f657",
    "git_blob_sha1": "14c0d3e171206a117a423e8d69a5aeab948ff4b7"
  },
  "controlsStdin": {
    "bytes": 253686,
    "sha256": "6ddbb93730a5ad9a42fc618b99d1cebcb46e8281b339b55c900b7ad7d2af8498",
    "git_blob_sha1": "b776bd9c61290b22a5caeac1d2f310b69f2da8cd"
  },
  "controlsRequestRaw": {
    "bytes": 254263,
    "sha256": "3f0327b9172e5d94fddb0ac750eaaec0266becc8792a15b4f846f0cbb2af9c7d",
    "git_blob_sha1": "fdd760374299e43d668534056f9326fdc3a75617"
  },
  "proofRaw": {
    "bytes": 4257,
    "sha256": "90b3371db0821551064d91393658e1278972dc64b0c85c183e28390395b45f3d",
    "git_blob_sha1": "ea8d14fb2cc871b38719182216a31a43e6f28e2f"
  },
  "substitutionsRaw": {
    "bytes": 1815,
    "sha256": "6ce926a44e98657ae9fdc4e15200c5745679f1f2bdc698f7fe5d34126749ace7",
    "git_blob_sha1": "4b8bc9dbc41359eb2eee0a9d3415b95406b799ed"
  }
};
function replayInstall02Controls(utilitySource,binderSource,templateFiles,knownReferences,oldControlsRequest,originalReferences){
 const U=Function(utilitySource+"\nreturn {utf8,sha256,gitBlob};")();
 if(U.gitBlob(U.utf8(utilitySource))!=="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d"||U.gitBlob(U.utf8(binderSource))!=="a1e326f9ef7fc12b52d7db3fc4e5605975b8262c")throw Error("REPLAY_UTILITY_OR_BINDER_PIN");
 const input={readonly:{...ACTUAL.readonly,stdout_raw:originalReferences["readonly38.original.json"],terminal_raw:originalReferences["readonly38-terminal.original.json"]},nonce:{...ACTUAL.nonce,stdout_raw:originalReferences["install-nonce.original.json"],terminal_raw:originalReferences["install-nonce-terminal.original.json"]},global_after_raw:originalReferences["global922.original.json"],global_after_pin:ACTUAL.global_after_pin};
 const result=Function(binderSource+"\nreturn prepareInstall02;")()(utilitySource,templateFiles,knownReferences,oldControlsRequest,input);
 for(const[name,p]of Object.entries(OUTPUTS)){const b=U.utf8(result[name]);if(b.length!==p.bytes||U.sha256(b)!==p.sha256||U.gitBlob(b)!==p.git_blob_sha1)throw Error("REPLAY_OUTPUT_"+name);}
 return result;
}
