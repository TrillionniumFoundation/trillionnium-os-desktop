// Pure source transformation. No filesystem/process/device access.
const REPLACEMENTS = [
  [
    "    require(type(artifact_reference) is dict and artifact_reference.get('target') == exact and\n            value.get('artifacts') == artifact_reference.get('artifacts') and\n            type(value.get('artifacts')) is list and len(value['artifacts']) == APK_COUNT and\n            value.get('apk_paths_before') == sorted(r['path'] for r in value['artifacts']) and\n            value.get('total_apk_bytes') == sum(r['held_file']['bytes'] for r in value['artifacts']),\n            'ACTUAL_METADATA_AND_BUILT_TARGET_ARTIFACT_REFERENCE_MUST_MATCH')",
    "    require(type(artifact_reference) is dict and artifact_reference.get('schema') == 1 and\n            {k:artifact_reference.get(k) for k in exact} == exact and\n            all(type(artifact_reference.get(k)) is int for k in ('uid','user','version_code')) and\n            value.get('artifacts') == artifact_reference.get('current_artifacts') and\n            type(value.get('artifacts')) is list and len(value['artifacts']) == APK_COUNT and\n            type(artifact_reference.get('current_APK_count')) is int and\n            artifact_reference['current_APK_count'] == APK_COUNT and\n            value.get('apk_paths_before') == sorted(r['path'] for r in value['artifacts']) and\n            type(artifact_reference.get('current_total_APK_bytes')) is int and\n            artifact_reference['current_total_APK_bytes'] == value.get('total_apk_bytes') ==\n                sum(r['held_file']['bytes'] for r in value['artifacts']),\n            'ACTUAL_METADATA_AND_BUILT_TARGET_ARTIFACT_REFERENCE_MUST_MATCH')"
  ],
  [
    "    require(type(dirs) is list and dirs == value.get('data_directories_after') and len(dirs) == 2 and",
    "    require(type(dirs) is list and dirs == value.get('data_directories_after') ==\n            artifact_reference.get('current_data_directories') and len(dirs) == 2 and"
  ],
  [
    "    qualify_target_metadata(authority, {\n        'target':authority.get('metadata_before'),'artifacts':authority.get('artifacts')})",
    "    metadata = authority.get('metadata_before')\n    qualify_target_metadata(authority, {\n        **(metadata if type(metadata) is dict else {}), 'schema':1,\n        'current_APK_count':APK_COUNT,\n        'current_artifacts':authority.get('artifacts'),\n        'current_total_APK_bytes':authority.get('total_apk_bytes'),\n        'current_data_directories':authority.get('data_directories_before')})"
  ]
];
const PINS = {
  "ticket": {
    "baseline_context": {
      "bytes": 24565,
      "sha256": "6614dfec823bd78f1ae0d95523f443cdd4c52ae5b6941e95c9eeac708a4634f0",
      "git_blob_sha1": "a390a9438fab1a890b3775011f0fc80e5bb9835f"
    },
    "candidate_context": {
      "bytes": 25356,
      "sha256": "c117d8dcc0ea905614106d95c6581a3e27d968b58ff6afab3d3537d2049145b1",
      "git_blob_sha1": "5a901de831981b7a0c763c1c5fdd38a6adbe8580"
    },
    "actual_metadata": {
      "bytes": 11978,
      "sha256": "f573eb50b3e0c2a098101035df116ba76bfdbf5f486e3dafb7588399661bb868",
      "git_blob_sha1": "4118c053d3da58dd50f00cf433eb5083b3adaed6"
    },
    "artifact_reference": {
      "bytes": 3513,
      "sha256": "57220958eacec13fb0b82755d4e22ffb6e02e42ecb05224103c6c5d37036db0c",
      "git_blob_sha1": "60609aadd2ed57e7322fa219eb3e458d3b204418"
    },
    "original_controls": {
      "bytes": 28570,
      "sha256": "34ed04cf0edb5af6de052c64e2b08979909732992ffb9b8b44e5414123b7885a",
      "git_blob_sha1": "7de33782f35cbc7356b5a6d36ffc0d589d5533eb"
    },
    "actual_schema_lossless_equal": true,
    "reference_body_unchanged": true,
    "metadata_body_unchanged": true,
    "controls_body_unchanged": true
  },
  "hilton": {
    "baseline_context": {
      "bytes": 24457,
      "sha256": "695b7e0c21761900aa97af797e4cb21520655512b1b603a889745883dccc506e",
      "git_blob_sha1": "275083aaddfa3d68ce86ab086775208cedee7691"
    },
    "candidate_context": {
      "bytes": 25248,
      "sha256": "eaf426c17c8818f88f0abcf4d7ab59d86b10e5e536d10640a15db80d6b37d460",
      "git_blob_sha1": "4c01cf3280a38115f583b58cef3ee2436b64b427"
    },
    "actual_metadata": {
      "bytes": 13997,
      "sha256": "cd4f46876a1bd0b48289d6b6a9c8379b2480073b4a24849397f8d990cabeb0dd",
      "git_blob_sha1": "5e43bfe675aae41e387bc7752668eb08f1825a2d"
    },
    "artifact_reference": {
      "bytes": 5083,
      "sha256": "a7ecc2530967eeb3d340b4d53cdab634223263b50e871382caaef8508c930f6a",
      "git_blob_sha1": "275b9350a6f7836978bd73f533aadca8a86af156"
    },
    "original_controls": {
      "bytes": 28555,
      "sha256": "a516a184ea168220dc03724e6ac9a98ea01cd82523124398e1fae33063458b59",
      "git_blob_sha1": "fc058b4e7bc3a334906dcf29120b131e8d803f26"
    },
    "actual_schema_lossless_equal": true,
    "reference_body_unchanged": true,
    "metadata_body_unchanged": true,
    "controls_body_unchanged": true
  },
  "united": {
    "baseline_context": {
      "bytes": 24456,
      "sha256": "b3402a26cdb30a698f1a78a462bc70b9efe09056346e0d4cfad900945c89209e",
      "git_blob_sha1": "bc939992041923dbffc9675256ed08c8a0247670"
    },
    "candidate_context": {
      "bytes": 25247,
      "sha256": "afb4ef79a762e6cfc5bca0fd558e77c1611ff8183c85a2333e99cd94415a7e57",
      "git_blob_sha1": "490217ccbb1f2db2da948df5ae4197b58c15d3f5"
    },
    "actual_metadata": {
      "bytes": 13946,
      "sha256": "7820efe97d7a8ebd55f91b6234d829576e2f0c2c0e6277710f143aca3759dc76",
      "git_blob_sha1": "a47962c9d7fb8cd344dd67f8667ed1d3520a7a7f"
    },
    "artifact_reference": {
      "bytes": 5048,
      "sha256": "9fd00a8b3b3f88e958b75d093247e27d8736747e9191bda26b4ac9955f16cc9a",
      "git_blob_sha1": "b28a323194d32b598b39de16c1a4e635cb7a83d6"
    },
    "original_controls": {
      "bytes": 28555,
      "sha256": "f0b91b3ff2d68baaff9df54969733fb84ab400dd2832c4bb14a617e3f096c172",
      "git_blob_sha1": "ab11b3e93f881b38126843d86a717e041118f15f"
    },
    "actual_schema_lossless_equal": true,
    "reference_body_unchanged": true,
    "metadata_body_unchanged": true,
    "controls_body_unchanged": true
  }
};
function reproduceMetadataSchemaContext(utilitySource,label,baselineRaw,actualMetadataRaw,artifactReferenceRaw){
  const U=Function(utilitySource+"\nreturn {utf8,sha256,gitBlob};")();
  const need=(v,m)=>{if(!v)throw Error(m);};
  need(U.gitBlob(U.utf8(utilitySource))==="443e39b58cd6fe72faa1cb1d1c7b0a813fa0032d","UTILITY_PIN");
  const pins=PINS[label];need(pins,"EXACT_APP");
  const pin=(raw,p)=>need(U.utf8(raw).length===p.bytes&&U.sha256(U.utf8(raw))===p.sha256&&U.gitBlob(U.utf8(raw))===p.git_blob_sha1,"WHOLE_PIN");
  pin(baselineRaw,pins.baseline_context);pin(actualMetadataRaw,pins.actual_metadata);pin(artifactReferenceRaw,pins.artifact_reference);
  const parse=raw=>JSON.parse(raw,(_k,v,c)=>typeof v==="number"&&Number.isInteger(v)&&!Number.isSafeInteger(v)?c.source:v);
  const a=parse(artifactReferenceRaw),m=parse(actualMetadataRaw),eq=(x,y)=>JSON.stringify(x)===JSON.stringify(y);
  need(a.schema===1&&eq(Object.fromEntries(["package","uid","user","version_code"].map(k=>[k,a[k]])),m.metadata_before)&&eq(m.metadata_before,m.metadata_after),"ACTUAL_REFERENCE_TOP_LEVEL_METADATA");
  need(eq(a.current_artifacts,m.artifacts)&&a.current_APK_count===m.artifacts.length&&a.current_total_APK_bytes===m.total_apk_bytes&&a.current_total_APK_bytes===m.artifacts.reduce((s,r)=>s+r.held_file.bytes,0),"ACTUAL_REFERENCE_ARTIFACTS");
  need(eq(a.current_data_directories,m.data_directories_before)&&eq(m.data_directories_before,m.data_directories_after),"ACTUAL_REFERENCE_DIRECTORIES");
  let candidate=baselineRaw;for(const [before,after] of REPLACEMENTS){need(candidate.split(before).length===2,"ONE_EXACT_BLOCK");candidate=candidate.replace(before,after);}
  let inverse=candidate;for(const [before,after]of [...REPLACEMENTS].reverse()){need(inverse.split(after).length===2,"ONE_INVERSE_BLOCK");inverse=inverse.replace(after,before);}
  need(inverse===baselineRaw,"FULL_SOURCE_INVERSE");pin(candidate,pins.candidate_context);return candidate;
}
