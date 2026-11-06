#!/usr/bin/env python3
"""Root release decision from fixed gates and independently reviewed actual evidence."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def meta(p):
 b=p.read_bytes();return {'path':str(p.relative_to(ROOT)),'bytes':len(b),'sha256':sha(b)}
def pinned(p,pin):
 b=p.read_bytes();assert sha(b)==pin;return json.loads(b)
result=pinned(P/'result04-original.json','3e94b99a354719380674a7115d8b202c613beee4e2d90fccc6d443c3d7664327')
runtime=pinned(P/'ROOT_RUNTIME_DIAGNOSTICS_REVIEW04.json','955125dc87cb9961320fc0483e0d57c20b207a137fb264b39007d4a0a8a52851')
peer=pinned(P/'CLOCK_ACTUAL_FEATURE_REVIEW04.json','6d9a0d7dc6202555e84e281e5a8aa8b787cdfe9b8b5d01d3b4cf5603cacac1e5')
gates=pinned(ROOT/'all-app-readiness08/app-gates.json','441289f9c04b46f38e1dd6e19f23ec6e4c6729b6a6f814cab81c0ae6fbbb1e78')
assert runtime['all_checks_passed'] and peer['conclusion']=='ALL_DECLARED_QA_FEATURES_DATA_ISOLATION_AND_THREE_OWNED_LIFECYCLES_SUPPORTED_FOR_CURRENT_APK'
assert runtime['original_result_sha256']==meta(P/'result04-original.json')['sha256']
for source in peer['inputs']+peer['complete_source_contract']['all_five_Dex_classes_reviewed']+peer['retained_attempt_reconciliation']:
 b=(ROOT/source['path']).read_bytes();assert len(b)==source['bytes'] and sha(b)==source['sha256'],source['path']
assert peer['identity']['apk_sha256']==result['identity_before']['apk_sha256']==result['identity_after']['apk_sha256']
assert peer['identity']['certificate_sha256']==['df1baddab9b5bf8ec8581a35c5294519511e3bbeb709ce14dfee5e873afa3e1b']
required=set(gates['common_gates'])|set(gates['profiles']['fixture']['checks']);assert len(required)==9
assert result['whole_app_production_ready'] is False and result['runtime']['stable_complete_mapping_samples']==0
explanations={
 'identity':'Both current held APK reads match91e352, UID10115/user0/version0/48cb epoch; original45 verifier v2/v3 certificate df1b is bound by identical full APK bytes. Six stable snapshots across all three actual process generations bind x86_64 app_process64/ART and381 identical whole-hashed filesystem ELF objects. Non-executable heuristic candidates and named JIT/kernel mappings are explicitly classified in the runtime review.',
 'lifecycle':'Three separately owned tasks1008/1009/1010 launched and normally removed, each closing to original task851; two independent reopens restore the intentional default view-only state, and actual Confirm verifies empty contents. All three exact guest process exits are owned remove-task events.',
 'stability':'The predeclared three>=30-second QA-fixture repeat budget completed118.238466 seconds of live observation.255 samples cover three process generations with no unexplained within-round replacement. Independent resource reconstruction matches the frozen caps and late-growth thresholds;20 consecutive retained diagnostic intervals show no new exact-UID crash/ANR or unexplained exit.',
 'data_permissions':'CE/DE inode, ownership and mode preserved; files/shared_prefs/databases/no_backup remain absent before and after. Exact permissions remain empty;0 package/permission/account/Provider mutations and no such API in the complete app code. Framework-generated cache contents are outside this App-model contract.',
 'ui_observation':'Source-enforced current owned foreground/window/native/geometry validation and fresh exact state comparisons precede and follow the9 positive controls; saved effect records independently match each expectation. Raw ambiguity reply confirms refusal without effect; no inferred or replayed inputs.',
 'fixture.contract':'All five actual DEX classes and the sole manifest Activity reviewed. The shipping purpose is a tracked local QA fixture with two independent text fields, Confirm and a result label; no account/network/provider/file or additional component contract is present.',
 'fixture.controls':'Actual empty Confirm, Unicode/emoji first field, independent second field, first-field echo, each field clearing, two fresh-empty reopen confirmations and duplicate-selector refusal cover every declared control and positive/negative QA contract.',
 'fixture.isolation':'Both original model stores remain empty, target UID maps only to this package, baseline task851 is preserved, all own tasks are closed and no pending launch/input/close remains. Other packages and user media were not modified by this flow.',
 'release_scope':'Root explicitly accepts the complete declared QA-fixture release for this exact APK and epoch after independent feature and runtime reviews. Retained parser/hint failures are reconciled by actual later source/state evidence; no unresolved finding remains within this declared contract.'}
assert set(explanations)==required
qualification={'schema':'pocket4-probe04-whole-qa-app-release-review/v1','reviewer':'root','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),
 'observed_at_utc':result['finished_utc'],'scope':'whole_app_release','package':'local.pocket4.fixture','app_kind':'qa_fixture','uid':10115,'android_user':0,'version_code':0,
 'apk_sha256':peer['identity']['apk_sha256'],'apk_bytes':12713,'certificate_sha256':peer['identity']['certificate_sha256'][0],'framework_epoch_sha256':result['guard_after']['epoch_sha256'],
 'gate_definitions':meta(ROOT/'all-app-readiness08/app-gates.json'),'checks':{k:'passed' for k in sorted(required)},'check_reasoning':explanations,
 'all_features_reviewed':True,'retained_failures_reconciled':True,'unresolved_findings':[],'whole_app_production_ready':True,
 'qualification_scope':'Exact installed five-class Pocket4 local QA fixture on the current Linux/DroidLoom Android17 epoch, for its complete declared view-only controls/isolation contract and predeclared bounded repeat/resource budget.',
 'dependencies':'Current unchanged native action v2 APK a5368465 supplies the QA control interface; actual exact UID process mapping records the installed ART/runtime dependency. No external accounts, network service or Provider is needed by the fixture.',
 'retained_attempt_reconciliation':peer['retained_attempt_reconciliation'],
 'evidence':[meta(P/name) for name in ('result04-original.json','status04-02-tool-original.json','ROOT_TERMINAL_REVIEW.json','ROOT_RUNTIME_DIAGNOSTICS_REVIEW04.json','INDEPENDENT_ELF_INVENTORY04.json','CLOCK_ACTUAL_FEATURE_REVIEW04.json','saved-runtime-export04.json','SOURCE_REVIEW04.json')],
 'original_controller_fields_preserved':{'whole_app_production_ready':False,'release_scope_requires_independent_review':True,'stable_complete_mapping_samples':0},
 'separate_review_not_original_result_rewrite':True,'limits':runtime['limits']+['This is one QA fixture entry in the fixed45-App denominator, not an end-user business App completion or an Android/native-helper/Asterinas release.','Normal task removal/reopen default state is qualified; no unsupported persistent-editor, IME composition or unspecified UI feature is claimed.'],
 'new_device_or_UI_operations':0,'other_app_readiness_changed':False}
path=P/'ROOT_WHOLE_QA_RELEASE_REVIEW04.json'
with path.open('x') as f:json.dump(qualification,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps(meta(path)))
