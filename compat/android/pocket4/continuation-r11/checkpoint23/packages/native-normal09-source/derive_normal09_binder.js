function deriveNormal09Binder(original,D,H){
"use strict";
const need=(x,m)=>{if(!x)throw Error(m);};
const pin=s=>{const b=H.utf8(s);return{bytes:b.length,sha256:H.sha256(b)};};
need(pin(original).bytes===18449&&pin(original).sha256==="db011f56c40a4f13d455833fe7a61e1d6c228c6561ff1b4baa55758afe12b3bb","original08 binder");
need(pin(D.framework).bytes===63597&&pin(D.framework).sha256==="dd6734852b33517cd971f88a5f6ee263df4f78ec18d1b389da28e174b765e12e"&&pin(D.fence).sha256==="808daeb71496b9f8e49937c493d2a236a0d5110032cdd07464e0c4295d15bb55","exact09 source templates");
let s=original;const edits=[];
function edit(before,after,count=1){const offsets=[];for(let p=s.indexOf(before);p>=0;p=s.indexOf(before,p+before.length))offsets.push(p);need(offsets.length===count,"binder preimage "+before.slice(0,80));edits.push({before,after,count,offsets});for(const p of [...offsets].reverse())s=s.slice(0,p)+after+s.slice(p+before.length);}
function line(prefix,after){const a=s.split("\n").filter(x=>x.startsWith(prefix));need(a.length===1,"single binder line "+prefix);edit(a[0],after);}
edit("function bindNormal08(","function bindNormal09(");
edit("normal07RequestText","normal08RequestText",4);
line("  const templatePins=","  const templatePins="+JSON.stringify(D.pins.templateFiles)+";");
line("  const oldRequestPin=",'  const oldRequestPin={"bytes":1022914,"sha256":"7ac74723eaff25849512943bfe25ec87ec0eff36807f5b787f44862c31033c65"};');
line("  const expectedTests=","  const expectedTests="+JSON.stringify(D.tests)+";");
line("  const expectedIndices=","  const expectedIndices="+JSON.stringify(D.indices)+";");
line("  const expectedLabels=","  const expectedLabels="+JSON.stringify(D.labels)+";");
line("  const expectedDelta=","  const expectedDelta="+JSON.stringify(D.delta)+";");
edit("pocket4-native-typed-ingress-builder471-systemui-test-projection-compile-01-20261106","pocket4-native-typed-ingress-builder473-audiocontrol-example-projection-compile-01-20261106");
edit("c29c7b05fcfdf3def918d2bc963c6fe0c25a0430c87249f3de781d5d8bf68ae0","a3426e40f9446b85931c82e8ba08335e72cd9bd0ac4a3f70aa01d54200d1ae13");
edit("actual Normal07 source request differs","actual Normal08 source request differs");
edit("result.focused_tests_passed===30&&result.updater_focused_tests_passed===21","result.focused_tests_passed===33&&result.updater_focused_tests_passed===24");
edit("result.systemui_test_projection_tests_passed===3&&","result.systemui_test_projection_tests_passed===3&&result.audiocontrol_example_projection_tests_passed===3&&");
edit("result.actual_registered_test_count===211","result.actual_registered_test_count===214");
edit("actual fixed builder471 focused test scope incomplete","actual fixed builder473 focused test scope incomplete");
edit("result.commands.length===68","result.commands.length===71");
edit('[expectedIndices,expectedTests,211,"test_elf"','[expectedIndices,expectedTests,214,"test_elf"');
edit("result.copied_manifest.bytes===99548","result.copied_manifest.bytes===99775");
const before=`       result.actual_parent470_compile_authority.bytes===172040&&
       result.actual_parent470_compile_authority.sha256==="f4e78f21dec485f59ff2149cb12298c070142dbad4e29b00a776729a376eea4c"&&
       result.systemui_test_projection_authority.bytes===6531&&
       result.systemui_test_projection_authority.sha256==="17fe54cebd452ef14258461f0817b9cbc753ccb0619f28e7274e61879a89d762"&&
       result.systemui_test_original_fixture_authority.bytes===3392&&
       result.systemui_test_original_fixture_authority.sha256==="f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da"&&`;
const after=`       result.actual_parent471_compile_authority.bytes===181273&&
       result.actual_parent471_compile_authority.sha256==="466d01e56fa6579636be8e82eedbc4276c31ce3e6b390dc985fe3bc454ead1e9"&&
       result.audiocontrol_example_projection_authority.bytes===6453&&
       result.audiocontrol_example_projection_authority.sha256==="c642e886b77adeb07d8f38a3dd10d042218e8e6582d6fd523be751ef1317b2e5"&&
       result.audiocontrol_example_original_fixture_authority.bytes===1869&&
       result.audiocontrol_example_original_fixture_authority.sha256==="9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6"&&
       result.systemui_test_projection_retained_from_parent471===true&&`;
edit(before,after);
edit("actual builder source, parent470, fixed SystemUI test projection and unchanged lock differ","actual builder source, parent471, fixed Audiocontrol example projection and unchanged lock differ");
for(const token of ["BUILDER471_SHA256","BUILDER471_BYTES","COMPILE471_RESULT_SHA256","COMPILE471_RESULT_BYTES"])edit("__ACTUAL_"+token+"__","__ACTUAL_"+token.replace("471","473")+"__");
edit("__BOUND_FRAMEWORK471_CONTROLLER_SHA256__","__BOUND_FRAMEWORK473_CONTROLLER_SHA256__");
edit("actual-builder471-result.json","actual-builder473-result.json");
edit('const oldRoot="typed-ingress-framework-provider-build-07-20261106",newRoot="typed-ingress-framework-provider-build-08-20261106";','const oldRoot="typed-ingress-framework-provider-build-08-20261106",newRoot="typed-ingress-framework-provider-build-09-20261106";');
edit('.replace("-07-20261106","-08-20261106")','.replace("-08-20261106","-09-20261106")');
edit("ACTUAL471_BOUND_NORMAL08_NOT_EXECUTED","ACTUAL473_BOUND_NORMAL09_NOT_EXECUTED");
edit("focused_tests:30,compile_commands:68","focused_tests:33,compile_commands:71");
let back=s;for(const e of [...edits].reverse()){for(let i=0;i<e.offsets.length;i++){const p=e.offsets[i];need(back.slice(p,p+e.after.length)===e.after,"binder inverse exact position "+p);back=back.slice(0,p)+e.before+back.slice(p+e.after.length);}}need(back===original,"binder inverse bytes");
return{source:s,edits,pin:pin(s)};
}
