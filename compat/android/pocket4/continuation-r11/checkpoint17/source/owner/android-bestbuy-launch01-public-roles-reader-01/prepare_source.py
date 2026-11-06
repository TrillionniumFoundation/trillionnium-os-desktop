#!/usr/bin/env python3
"""Derive fixed historical BestBuy counts reader; no device/process actions."""
from pathlib import Path
import ast,difflib,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
BASE=ROOT/'android-ihg-launch01-public-roles-reader-01'

def replace(source,before,after,count=1):
    assert source.count(before)==count,(before,source.count(before),count)
    return source.replace(before,after)
def assignment(source,name,value):
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
    lines=source.splitlines(True);lines[node.lineno-1:node.end_lineno]=[name+'='+repr(value)+'\n'];return ''.join(lines)
def pin(path):
    raw=path.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def main():
    assert pin(BASE/'read_roles.py')=={'bytes':19209,'sha256':'e6413134cb585885c45ad36a644f04170193bb948216612d2c8559c6c0233aa9'}
    evidence=ROOT/'root-recovery-20261104-02/evidence/bestbuy-launch-five-results-read01'
    names={
        'coordinator':(13536,'1b9632bc59f615cf364e148d4dd5d14a5c540e48764616d1cfded9a904159b07'),
        'stage':(1713,'8a1f5f8b6b24b8e53c47d409a4e2e4a8005d4b4695703e916160ab4b3d5ca60f'),
        'launch':(13279,'82c72f7a7be021c5acbddf500ce497b323da06e7746fabbc14da06fc42176eb9'),
        'inspect':(21067,'95b15ea5f365c7a672cffa446ddb39faed675388ed7b123c84db8f55f818fd14'),
        'cleanup':(12151,'fb11b08fb51bc6228c737b3dad48ce3e85a72e233c123a561bd2dd248a5b2f8b')}
    for name,(size,digest) in names.items():assert pin(evidence/(name+'.json'))=={'bytes':size,'sha256':digest}
    c=json.loads((evidence/'coordinator.json').read_bytes());inspect=json.loads((evidence/'inspect.json').read_bytes())
    meta=inspect['assessments']['inspect']
    assert meta['assessment_bytes']==19799 and meta['assessment_sha256']=='63f143c770ff2194f2b0e25f69026961764224af4c9f0d6836ba59d3bb6cf549'
    assert meta['nonce']=='304e502d5e668874fe3879215395eecd' and meta['node_count']==12
    qa=ROOT/'owned-bestbuy-qa-r1-build01/source/qa_contract.py';qapin=pin(qa)
    assert qapin=={'bytes':28173,'sha256':'e751f26cba0e02258427216fdc69fb8cbfdd673623148c3700ea2dbe35364195'}
    source=(BASE/'read_roles.py').read_text().replace('com.ihg.apps.android','com.bestbuy.android').replace('ihg','bestbuy').replace('IHG','BESTBUY')
    source=source.replace('public hotel-entry','public entry and onboarding')
    substitutions={
        '399444a5b72d53139b880a4afefdb31a':c['nonce'],
        '704bf0640c6a207ad8177dfc0240896cc785b6fa6db34521fbea5cd02e42a6fd':c['source_manifest_sha256'],
        '573fdcd691ed51b76f965151b74b38cfcbd12ed5aa972d668146ae136744d7e1':qapin['sha256'],
        'ab971f5b361f1d97b8036c954a6b88734b7faedbeed6349b873ead85fa79d5f3':'1dc5ae021d8b4d3165ac81dd09aef7035651118a9a81380139bdd1caaef668f8',
        '212fb7088216fc6760d30b7224f245ee':meta['nonce'],
        '902c325a2ceaecafced4abc93a4654ad22699dddce216a3af3f8d7c6d938fa3a':meta['wire_sha256'],
        '10196':'10198','10137':'10130','1002':'1012',
        "meta.get('node_count')==63":"meta.get('node_count')==12",
        '86558':'19799','28150':'28173',
        '2e0a9c2af7c403b330e92566a058dd8a0e790654b8c2f89e1a89330e035123de':meta['assessment_sha256'],
        'FIXED_SIX_FILE_ALLOWLIST_REQUIRED':'FIXED_SEVEN_FILE_ALLOWLIST_REQUIRED',
        'hotel_search_login_or_booking_verified':'shopping_login_or_purchase_verified',
    }
    for before,after in substitutions.items():source=source.replace(before,after)
    oldpins={
        "ROOT/'result.json':(13631,'6a354bc4cfe0066263b8f6041be90d674fce05700cd57b21dcf5880122312211')":
            "ROOT/'result.json':"+repr(names['coordinator']),
        "ROOT/'stage-result.json':(1710,'bb34503b97e7702a8b10c6da10cb4bb6e3a95043168ff59859a15cbdf56d7bf1')":
            "ROOT/'stage-result.json':"+repr(names['stage']),
        "STEP/'result.json':(19064,'6ded83f7b28e3b9658efe9c1d166513734b58d21a05267d5612b6ddce6d4f836')":
            "FLOW/'steps/launch-01/result.json':"+repr(names['launch'])+",\n STEP/'result.json':"+repr(names['inspect']),
        "FLOW/'steps/cleanup-01/result.json':(10012,'eea9b4b856e6a799255626f02213c643ceefced73a86ae503c82119faba9591f')":
            "FLOW/'steps/cleanup-01/result.json':"+repr(names['cleanup']),
    }
    for before,after in oldpins.items():source=replace(source,before,after)
    roles={
        'search_tab':('search',),'home_tab':('home',),'shop_tab':('shop',),'browse_tab':('browse',),
        'search_products':('search products','search best buy','search bestbuy'),
        'country_selector':('country','select country','select your country','choose your country','country/region','select your country or region'),
        'united_states':('united states','united states of america','usa','u.s.','u.s.a.'),'canada':('canada',),
        'continue':('continue',),'next':('next',),'skip':('skip',),'get_started':('get started',),
        'guest_continue':('continue as guest','continue without signing in','browse as guest'),
        'defer_signin':('not now','maybe later'), 'sign_in':('sign in','log in'),
        'retry':('retry','try again'),'fixed_network_error':('no internet connection','something went wrong'),
    }
    resources=('android:id/button1','android:id/button2','android:id/button3','android:id/search_src_text',
        'com.bestbuy.android:id/search_button','com.bestbuy.android:id/search','com.bestbuy.android:id/search_src_text',
        'com.bestbuy.android:id/country','com.bestbuy.android:id/country_selector',
        'com.bestbuy.android:id/continue_button','com.bestbuy.android:id/btn_continue',
        'com.bestbuy.android:id/skip','com.bestbuy.android:id/continue_as_guest','com.bestbuy.android:id/bottom_navigation')
    source=assignment(source,'PUBLIC_ROLES',roles);source=assignment(source,'PUBLIC_RESOURCES',resources)
    source=replace(source,'def validate_retained(c,s,phase,cleanup):','def validate_retained(c,s,launch,phase,cleanup):')
    source=replace(source,'    for value in (c,s,phase,cleanup):','    for value in (c,s,launch,phase,cleanup):')
    source=replace(source,"    for value,kind in ((phase,'inspect'),(cleanup,'cleanup')):","    for value,kind in ((launch,'launch'),(phase,'inspect'),(cleanup,'cleanup')):")
    source=replace(source,"    need(s.get('coordinator_result')==fixed_pin(ROOT/'result.json') and",
        "    need(s.get('coordinator_result')==fixed_pin(ROOT/'result.json') and\n         c.get('launch_result')==c.get('retained_phase_results',{}).get('launch')==fixed_pin(FLOW/'steps/launch-01/result.json') and")
    source=replace(source,"    task=c['owned_task']","    need(launch.get('action_lock_released') is True and launch.get('launch',{}).get('native_launch_acknowledged') is True,\n         'EXACT_ORIGINAL_NATIVE_LAUNCH_RETIRED')\n    for value in (launch,phase,cleanup):\n        need(value.get('target_before')==value.get('target_after')==phase['target_before'] and\n             value['target_FD_cleanup']['held_APK_FDs_closed']==3 and\n             value.get('helper_before')==value.get('helper_after')==phase['helper_before'],\n             'EXACT_THREE_APK_AND_HELPER_PHASE_IDENTITIES_REQUIRED')\n    task=c['owned_task']\n    need(launch.get('owned_task')==task,'EXACT_LAUNCH_OWNED_TASK_REQUIRED')")
    source=replace(source,"    phase=read_json(STEP/'result.json');cleanup=read_json(FLOW/'steps/cleanup-01/result.json')\n    scope,metadata,state_before=validate_retained(c,s,phase,cleanup)",
        "    launch=read_json(FLOW/'steps/launch-01/result.json')\n    phase=read_json(STEP/'result.json');cleanup=read_json(FLOW/'steps/cleanup-01/result.json')\n    scope,metadata,state_before=validate_retained(c,s,launch,phase,cleanup)")
    ast.parse(source)
    with (HERE/'read_roles.py').open('x') as out:out.write(source)
    raw=source.encode();readerpin={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    maker=(BASE/'make_request.py').read_text()
    maker=assignment(maker,'READER_SHA',readerpin['sha256']);maker=assignment(maker,'READER_BYTES',readerpin['bytes'])
    maker=assignment(maker,'KEY','pocket4-bestbuy-launch01-public-roles-readonly-01-20261106')
    maker=maker.replace('len(raw)==19209','len(raw)=='+str(readerpin['bytes']))
    with (HERE/'make_request.py').open('x') as out:out.write(maker)
    controls=(BASE/'pure_controls.py').read_text().replace('ihg','bestbuy').replace('IHG','BESTBUY')
    controls=controls.replace('28150','28173').replace('10196','10198').replace('10137','10130')
    controls=controls.replace('FIXED_SIX_FILE_ALLOWLIST_REQUIRED','FIXED_SEVEN_FILE_ALLOWLIST_REQUIRED')
    controls=controls.replace("    a=function_ast(ROOT/'android-bili-r6-fresh02-reveal-role-reader-01/read_roles.py');b=function_ast(HERE/'read_roles.py')",
        "    a=function_ast(ROOT/'android-ihg-launch01-public-roles-reader-01/read_roles.py');b=function_ast(HERE/'read_roles.py')")
    controls=controls.replace("source=path.read_text().replace('FIXED_SEVEN_FILE_ALLOWLIST_REQUIRED','FIXED_EIGHT_FILE_ALLOWLIST_REQUIRED').replace(\"helper.get('self_uid')==10198\",\"helper.get('self_uid')==10184\")",
        "source=path.read_text().replace('FIXED_SIX_FILE_ALLOWLIST_REQUIRED','FIXED_COMMON_FILE_ALLOWLIST_REQUIRED').replace('FIXED_SEVEN_FILE_ALLOWLIST_REQUIRED','FIXED_COMMON_FILE_ALLOWLIST_REQUIRED').replace(\"helper.get('self_uid')==10196\",\"helper.get('self_uid')==10184\").replace(\"helper.get('self_uid')==10198\",\"helper.get('self_uid')==10184\")")
    controls=controls.replace("'Find a hotel'","'Continue'").replace("['find_hotel']","['continue']")
    controls=controls.replace("('stage',r.ROOT/'stage-result.json'),('inspect',r.STEP/'result.json')","('stage',r.ROOT/'stage-result.json'),('launch',r.FLOW/'steps/launch-01/result.json'),('inspect',r.STEP/'result.json')")
    controls=controls.replace("meta['node_count']==63","meta['node_count']==12").replace('four_actual_safe_originals','five_actual_safe_originals')
    # Additional fixed parent-link negatives; the actual assessment remains remote only.
    anchor="    helper={'protocol':qa.PROTOCOL"
    extra="    changed=copy.deepcopy(records);changed[0]['launch_result']['sha256']='0'*64\n    reject('wrong_launch_child_pin_rejected',lambda:r.validate_retained(*changed),'EXACT_PARENT_CHILD_RESULT_PINS_REQUIRED')\n    changed=copy.deepcopy(records);changed[2]['target_FD_cleanup']['held_APK_FDs_closed']=1\n    reject('incomplete_three_APK_FD_cleanup_rejected',lambda:r.validate_retained(*changed),'EXACT_THREE_APK_AND_HELPER_PHASE_IDENTITIES_REQUIRED')\n"
    controls=replace(controls,anchor,extra+anchor)
    with (HERE/'pure_controls.py').open('x') as out:out.write(controls)
    for name in ('read_roles.py','make_request.py','pure_controls.py'):
        done=subprocess.run(['/usr/bin/python3','-B',str(HERE/name)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (HERE/(name[:-3]+'.stdout.json')).write_bytes(done.stdout);(HERE/(name[:-3]+'.stderr.log')).write_bytes(done.stderr)
        assert done.returncode==0 and not done.stderr,done.stderr.decode()
    done=subprocess.run(['/usr/bin/python3','-B',str(HERE/'make_request.py'),'--write-once','--output',str(HERE/'exact-request.json')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (HERE/'generation.json').write_bytes(done.stdout);(HERE/'generation.stderr.log').write_bytes(done.stderr)
    assert done.returncode==0 and not done.stderr,done.stderr.decode()
    (HERE/'reader-derivation.patch').write_text(''.join(difflib.unified_diff((BASE/'read_roles.py').read_text().splitlines(True),source.splitlines(True),fromfile='reviewed-IHG-public-role-reader',tofile='fixed-BestBuy-public-role-reader')))
    print(json.dumps({'reader':readerpin,'request':pin(HERE/'exact-request.json'),'request_not_submitted':True,'device_calls':0},sort_keys=True))

if __name__=='__main__':main()
