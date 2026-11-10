#!/usr/bin/env python3
"""Patch only captured Calendar methods; never opens or installs a device artifact."""
from pathlib import Path
import argparse, hashlib, json, re, shutil

APK_SHA='7522e88fe03f4997513b0e03591da215b8ebc67f6c933939a73addc3c75495a9'
DEX_SHA='ad94f4234e06c7b97ff5f4631fadd22ed7fc03f01187ded30f3c5c3125b194d8'
PREFIX='com/android/calendar/'
ACTIONS='Lcom/android/calendar/repair/CalendarActions;'
EDITOR='Lcom/android/calendar/event/EditEventActivity;'
ALERTS='Lcom/android/calendar/alerts/RestoredAlerts;'
KNOWN={
 'AllInOneActivity.smali':'42345124f47ce4bb7b86919e2298525e2914684d43ce7482129c0e157a83cadd',
 'AllInOneActivity$QueryHandler.smali':'95ca070b4de74cb7b34177b315d43bb2de12a1be132799ab71eb3eccb81d7c29',
 'CalendarController.smali':'382a929b2ff76472c491a2a14c65dece0f048c295b63b75db00c90c91c44e732',
 'EventInfoActivity.smali':'4539e600603ca54d30c37a71a627fa1f9e313d47b60a2aad4fe023e49643fa8c',
 'alerts/AlertService.smali':'784231b7896c8c182c6d414b8e9820a0c094ca3a321db8cc5f42ded552fd4a83',
 'alerts/AlertReceiver.smali':'9a0e2283ef33cc0a2376580dd2758bc321490703c027ee149138751471eb5094',
}
METHOD=re.compile(r'^\.method[^\n]*\n.*?^\.end method$',re.M|re.S)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def require(value,reason):
    if not value: raise RuntimeError(reason)
def once(text,old,new):
    require(text.count(old)==1,'EXPECTED_EXACTLY_ONE_ANCHOR:'+old[:100])
    return text.replace(old,new,1)

def patch_tree(original,output,manifest_path):
    manifest=json.loads(manifest_path.read_text())
    require(manifest['state']=='CAPTURED_COMPLETE_CALENDAR_PREIMAGE','INCOMPLETE_PREIMAGE')
    require(manifest['apk_sha256']==APK_SHA and manifest['dex_sha256']==DEX_SHA,'PREIMAGE_IDENTITY')
    rows={r['path']:r for r in manifest['class_manifest']}
    require(len(rows)==445 and not output.exists(),'NEW_OUTPUT_AND_445_CLASSES_REQUIRED')
    files={p.relative_to(original).as_posix():p for p in original.rglob('*.smali')}
    require(set(rows)==set(files),'PREIMAGE_CLASS_SET')
    for name,row in rows.items():
        raw=files[name].read_bytes()
        require(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'PREIMAGE_CLASS_CHANGED:'+name)
    for name,digest in KNOWN.items(): require(rows[PREFIX+name]['sha256']==digest,'SELECTED_CLASS_CHANGED:'+name)
    shutil.copytree(original,output)
    changes=[]
    def alter(name,signature,operation):
        path=output/(PREFIX+name); text=path.read_text()
        matches=[m for m in METHOD.finditer(text) if m.group().splitlines()[0].split()[-1]==signature]
        require(len(matches)==1,'METHOD_NOT_UNIQUE:'+name+':'+signature)
        match=matches[0]; before=match.group(); after=operation(before)
        require(after!=before and after.splitlines()[0]==before.splitlines()[0],'METHOD_HEADER_CHANGED:'+signature)
        path.write_text(text[:match.start()]+after+text[match.end():])
        changes.append({'class':PREFIX+name,'method':signature,'before_sha256':sha(before.encode()),
                        'after_sha256':sha(after.encode()),'before_bytes':len(before.encode()),'after_bytes':len(after.encode())})

    alter('AllInOneActivity.smali','onCreateOptionsMenu(Landroid/view/Menu;)Z',lambda block:
        once(block,'    .registers 5\n','    .registers 5\n\n    invoke-static {p1}, '+ACTIONS+'->addNewEvent(Landroid/view/Menu;)V\n'))
    menu='''    move-object/from16 v2, p0
    move-object/from16 v3, p1
    const/4 v4, 0x0
    iget-object v0, v2, Lcom/android/calendar/AllInOneActivity;->mController:Lcom/android/calendar/CalendarController;
    if-eqz v0, :restored_menu_time_ready
    invoke-virtual {v0}, Lcom/android/calendar/CalendarController;->getTime()Ljava/lang/Long;
    move-result-object v4
    :restored_menu_time_ready
    invoke-static {v2, v3, v4}, ACTIONS->onMenu(Landroid/app/Activity;Landroid/view/MenuItem;Ljava/lang/Long;)Z
    move-result v0
    if-eqz v0, :restored_menu_original
    return v0
    :restored_menu_original
'''.replace('ACTIONS',ACTIONS)
    alter('AllInOneActivity.smali','onOptionsItemSelected(Landroid/view/MenuItem;)Z',lambda block:
        once(block,'    .registers 17\n','    .registers 17\n\n'+menu))
    alter('AllInOneActivity.smali','onResume()V',lambda block:
        once(block,'    invoke-super {v1}, Landroid/app/Activity;->onResume()V',
                   '    invoke-super {v1}, Landroid/app/Activity;->onResume()V\n\n    invoke-static {v1}, '+ACTIONS+'->onCalendarStarted(Landroid/app/Activity;)V'))

    def first_use(block):
        # Keep the actual query result, finishing check, cursor close and catchall.
        # Replace only the original automatic account operation after cursor close.
        start=block.index('    .line 159\n')
        end=block.index('    :catchall_51\n',start)
        automatic=block[start:end]
        require(automatic.count('->addAccount(')==1 and automatic.endswith('    return-void\n\n'),
            'EXACT_AUTOMATIC_ACCOUNT_BRANCH')
        local='''    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity$QueryHandler;->this$0:Lcom/android/calendar/AllInOneActivity;
    invoke-static {v0}, ACTIONS->onNoCalendars(Landroid/app/Activity;)V
    return-void

'''.replace('ACTIONS',ACTIONS)
        return block[:start]+local+block[end:]
    alter('AllInOneActivity$QueryHandler.smali','onQueryComplete(ILjava/lang/Object;Landroid/database/Cursor;)V',first_use)

    route='''    iget-object v0, p0, Lcom/android/calendar/CalendarController;->mContext:Landroid/content/Context;
    iget-wide v1, p2, Lcom/android/calendar/CalendarController$EventInfo;->eventType:J
    iget-wide v3, p2, Lcom/android/calendar/CalendarController$EventInfo;->id:J
    iget-object v5, p2, Lcom/android/calendar/CalendarController$EventInfo;->startTime:Landroid/text/format/Time;
    iget-object v6, p2, Lcom/android/calendar/CalendarController$EventInfo;->endTime:Landroid/text/format/Time;
    invoke-static/range {v0 .. v6}, ACTIONS->onEvent(Landroid/content/Context;JJLandroid/text/format/Time;Landroid/text/format/Time;)Z
    move-result v0
    if-eqz v0, :restored_controller_original
    return-void
    :restored_controller_original
    const-wide/16 v0, 0x0
'''.replace('ACTIONS',ACTIONS)
    # Existing per-sender filter runs first. Unhandled event types retain the
    # original zero wide value and continue through unchanged dispatch/locking.
    alter('CalendarController.smali','sendEvent(Ljava/lang/Object;Lcom/android/calendar/CalendarController$EventInfo;)V',
        lambda block:once(block,'    :cond_1b\n','    :cond_1b\n'+route))

    info=output/(PREFIX+'EventInfoActivity.smali')
    info.write_text(once(info.read_text(),'.super Landroid/app/Activity;','.super '+EDITOR))
    changes.append({'class':PREFIX+'EventInfoActivity.smali','declaration':'super',
                    'before':'Landroid/app/Activity;','after':EDITOR})
    alter('EventInfoActivity.smali','<init>()V',lambda block:
        once(block,'invoke-direct {p0}, Landroid/app/Activity;-><init>()V',
                   'invoke-direct {p0}, '+EDITOR+'-><init>()V'))
    for signature,registers in [
        ('onCreate(Landroid/os/Bundle;)V',2),('onResume()V',1),('onPause()V',1),
        ('onDestroy()V',1),('onSaveInstanceState(Landroid/os/Bundle;)V',2),
        ('onNewIntent(Landroid/content/Intent;)V',2),
    ]:
        def delegate(block,signature=signature,registers=registers):
            params='{p0, p1}' if registers==2 else '{p0}'
            return block.splitlines()[0]+'\n    .registers '+str(registers)+'\n\n    invoke-super '+params+', '+EDITOR+'->'+signature+'\n    return-void\n.end method'
        alter('EventInfoActivity.smali',signature,delegate)
    def receiver(block):
        return block.splitlines()[0]+'\n    .registers 3\n\n    invoke-static {p0, p1, p2}, '+ALERTS+'->onReceive(Landroid/content/BroadcastReceiver;Landroid/content/Context;Landroid/content/Intent;)V\n    return-void\n.end method'
    alter('alerts/AlertReceiver.smali','onReceive(Landroid/content/Context;Landroid/content/Intent;)V',receiver)
    def service(block):
        return block.splitlines()[0]+'\n    .registers 4\n\n    invoke-static {p0, p1, p3}, '+ALERTS+'->onServiceStart(Landroid/app/Service;Landroid/content/Intent;I)I\n    move-result p0\n    return p0\n.end method'
    alter('alerts/AlertService.smali','onStartCommand(Landroid/content/Intent;II)I',service)

    changed_classes={row['class'] for row in changes}
    unchanged=[]
    for name,old in files.items():
        after=(output/name).read_bytes()
        if name not in changed_classes:
            require(after==old.read_bytes(),'UNRELATED_CLASS_CHANGED:'+name);unchanged.append(name)
    result={'schema':'calendar-method-patch-v1','parent_apk_sha256':APK_SHA,'parent_dex_sha256':DEX_SHA,
            'original_classes':445,'changed_classes':sorted(changed_classes),
            'unchanged_class_bytes':len(unchanged),'changes':changes,
            'installed':False,'art_runtime_verified':False}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('original',type=Path)
    parser.add_argument('output',type=Path);parser.add_argument('manifest',type=Path)
    args=parser.parse_args();result=patch_tree(args.original,args.output,args.manifest)
    print(json.dumps(result,sort_keys=True,indent=2))
