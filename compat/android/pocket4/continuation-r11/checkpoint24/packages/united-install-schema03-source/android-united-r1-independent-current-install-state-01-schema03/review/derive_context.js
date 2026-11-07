function deriveArtifactReference03(original,label) {
  const need=(ok,m)=>{if(!ok)throw Error(m);};
  const replace=(s,a,b,n=1)=>{need(s.split(a).length-1===n,"EDIT_COUNT:"+a);return s.split(a).join(b);};
  need(["hilton","united","ticket12306"].includes(label),"FIXED_HELPER");
  const upper=label.toUpperCase();
  const before="        require(expected['target'] == {'package':PACKAGE,'uid':UID,'user':0,'version_code':VERSION},\n                'ACTUAL_"+upper+"_METADATA_REFERENCE_REQUIRED')";
  const after="        exact = {'package':PACKAGE,'uid':UID,'user':0,'version_code':VERSION}\n"+
    "        require(type(expected) is dict and expected.get('schema') == 1 and\n"+
    "                {key:expected.get(key) for key in exact} == exact and\n"+
    "                all(type(expected.get(key)) is int for key in ('uid','user','version_code')),\n"+
    "                'ACTUAL_"+upper+"_METADATA_REFERENCE_REQUIRED')\n"+
    "        require(type(expected.get('current_artifacts')) is list and\n"+
    "                type(expected.get('current_APK_count')) is int and\n"+
    "                len(expected['current_artifacts']) == expected['current_APK_count'] == APK_COUNT and\n"+
    "                type(expected.get('current_total_APK_bytes')) is int and\n"+
    "                expected['current_total_APK_bytes'] ==\n"+
    "                    sum(row['held_file']['bytes'] for row in expected['current_artifacts']),\n"+
    "                'ACTUAL_"+upper+"_ARTIFACT_REFERENCE_REQUIRED')\n"+
    "        self.metadata = exact";
  let source=replace(original,before,after);
  source=replace(source,"self.expected['target']","self.metadata",3);
  source=replace(source,"self.expected['artifacts']","self.expected['current_artifacts']",4);
  need(!source.includes("expected['target']")&&!source.includes("expected['artifacts']"),"NO_LEGACY_REFERENCE_READ");
  return source;
}
