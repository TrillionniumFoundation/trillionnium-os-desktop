"""Read this run's sole owned video bucket and recognize its actual thumbnail.

Two bounded album VIEW intents are inserted before the two original Movie VIEW
intents. No album thumbnail is clicked, no default-album pixels are captured,
and the original playback, seek, metadata and cleanup predicates remain intact.
"""
import copy
import io
import math
import re
from pathlib import Path
from PIL import Image

GALLERY='com.android.gallery3d'
ACTIVITY=GALLERY+'.app.GalleryActivity'
MIME='vnd.android.cursor.dir/video'

def need(ok,reason):
    if not ok:raise RuntimeError(reason)

def expand(activity):
    return GALLERY+activity if activity.startswith('.') else activity

def owned_id(flow):
    m=re.fullmatch(r'content://media/external_primary/video/media/([1-9][0-9]*)',flow.media['uri'])
    need(m is not None,'EXACT_CURRENT_OWNED_VIDEO_URI');return int(m[1])

def metadata_sql(flow):
    m=flow.s.components['video_flow.py']
    fields='_id,_data,_display_name,relative_path,owner_package_name,media_type,mime_type,_size,width,height,is_pending,bucket_id,bucket_display_name'
    return 'SELECT '+fields+' FROM files WHERE _id='+str(owned_id(flow))+" AND owner_package_name='"+m.PACKAGE+"' AND _data='"+m.GUEST_FILE+"' ORDER BY _id"

def members_sql(bucket):
    need(type(bucket) is int and -(2**31)<=bucket<2**31,'SIGNED_ACTUAL_BUCKET_ID')
    return 'SELECT _id,owner_package_name FROM files WHERE media_type=3 AND bucket_id='+str(bucket)+' ORDER BY _id'

def owned_bucket(flow,rows):
    m=flow.s.components['video_flow.py'];need(type(rows) is list and len(rows)==1,'ONE_OWNED_VIDEO_BUCKET_ROW')
    row=rows[0]
    wanted={'_id':owned_id(flow),'_data':m.GUEST_FILE,'_display_name':m.NAME,'relative_path':m.RELATIVE,
        'owner_package_name':m.PACKAGE,'media_type':3,'mime_type':'video/mp4','_size':123394,'width':640,'height':480,'is_pending':0,
        'bucket_display_name':m.FOLDER}
    need(set(row)==set(wanted)|{'bucket_id'} and all(row[k]==v for k,v in wanted.items()),'COMPLETE_OWNED_VIDEO_METADATA_TUPLE')
    members_sql(row['bucket_id']);return copy.deepcopy(row)

def allow_sql(s,label,transaction):
    f=s.case
    need(s.phase=='business' and f is not None and f.ui.owned is not None and f.media is not None
        and f.album_index in (0,1) and f.pending is None and f.album_context is None,
        'ALBUM_METADATA_ONLY_BEFORE_OWNED_VIEW')
    s.original_caller(['video_album.py'],{'inspect_album'},skip=('allow_sql',))
    index=f.album_index
    if label=='album-owned-row-'+str(index):sql=metadata_sql(f)
    elif label=='album-sole-bucket-'+str(index):
        need(f.album_bucket_row is not None,'ACTUAL_OWNED_BUCKET_ROW_FIRST');sql=members_sql(f.album_bucket_row['bucket_id'])
    else:raise RuntimeError('NO_OTHER_ALBUM_SQL_LABEL')
    need(transaction=='PRAGMA query_only=ON;BEGIN;'+sql+';ROLLBACK;','EXACT_READONLY_OWNED_BUCKET_SQL')
    return True

def is_command(argv):
    return argv==['/system/bin/dumpsys','activity','activities',GALLERY] or (
        argv[:2]==['/system/bin/am','start-activity'] and argv[-2:]==['-n',GALLERY+'/.app.GalleryActivity'])

def view_argv(flow,index):
    need(flow.ui.owned is not None and flow.album_bucket_row is not None,'ACTUAL_BUCKET_AND_OWNED_TASK')
    return ['/system/bin/am','start-activity','-W','--user','0','--display','0','--task',str(flow.ui.owned[0]),
        '--activity-clear-top','-a','android.intent.action.VIEW','-d',
        'content://media/external/video/media?bucketId='+str(flow.album_bucket_row['bucket_id']),'-t',MIME,
        '-n',GALLERY+'/.app.GalleryActivity']

def admit_command(policy,argv,timeout):
    s=policy.s;f=s.case;need(f is not None and s.phase=='business' and f.ui.owned is not None,'ALBUM_BUSINESS_OWNED_TASK')
    if argv==['/system/bin/dumpsys','activity','activities',GALLERY]:
        s.original_caller(['video_album.py'],{'read_route'},skip=('admit_command',))
        need(timeout==12 and f.album_index in policy.album_views_sent and f.album_activity_reads<8
            and (f.pending=='album-view-'+str(f.album_index) or f.album_context is not None),
            'BOUNDED_CURRENT_ALBUM_ROUTE_READ')
        f.album_activity_reads+=1;return False
    s.original_caller(['video_album.py'],{'inspect_album'},skip=('admit_command',))
    index=f.album_index
    need(timeout==35 and index in (0,1) and index not in policy.album_views_sent
        and f.pending=='album-view-'+str(index) and len(f.album_attempts)==index+1
        and len(f.album_checks)==index and len(f.result['pixel_rounds'])==index
        and f.album_context is None and f.album_sole_bucket_verified is True
        and len(f.native_launches)==s.native_launches==index+1 and f.native_launches[-1]==f.ui.owned[0]
        and f.media['sha256']==s.components['video_policy.py'].VIDEO_SHA,
        'ONE_EXACT_ALBUM_VIEW_BEFORE_EACH_ORIGINAL_MOVIE_ROUND')
    need(argv==view_argv(f,index),'ONLY_ACTUAL_OWNED_BUCKET_VIEW_ARGUMENTS')
    s.check_owned_task();s.consume_intent('album-view',argv);policy.album_views_sent.add(index);return True

def gallery_focus(flow,label):
    focus=flow.ui.focus(label)
    need(flow.ui.focus_allowed(focus,False) and focus['package']==GALLERY
        and expand(focus['activity'])==expand(focus['focused_activity'])==ACTIVITY,
        'CURRENT_OWNED_ALBUM_ACTIVITY_REQUIRED')
    return focus

def read_route(flow,before,expected_focus=None):
    index=flow.album_index;focus=gallery_focus(flow,'album-route-focus-'+str(index))
    need(focus['task']==before['task']==flow.ui.owned[0] and focus['window_token']!=before['window_token'],
        'ALBUM_VIEW_MUST_RECREATE_THE_OWNED_STANDARD_ACTIVITY_WINDOW')
    if expected_focus is not None:need(focus==expected_focus,'ALBUM_ROUTE_CHANGED_BEFORE_READBACK')
    uri='content://media/external/video/media?bucketId='+str(flow.album_bucket_row['bucket_id'])
    raw=flow.s.android(['/system/bin/dumpsys','activity','activities',GALLERY],12).decode('utf-8','strict')
    blocks=re.split(r'(?=^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{)',raw,flags=re.M)
    expression=r'^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{[^\n]*\bu0 '+re.escape(GALLERY)+r'/(?:\.app\.GalleryActivity|com\.android\.gallery3d\.app\.GalleryActivity) t'+str(focus['task'])+r'\b'
    selected=[b for b in blocks if re.search(expression,b)]
    need(len(selected)==1,'ONE_CURRENT_OWNED_ALBUM_ACTIVITY_RECORD');block=selected[0]
    record_token=re.search(r'ActivityRecord\{([0-9a-f]+)\b',block)
    need(record_token is not None,'CURRENT_ALBUM_ACTIVITY_RECORD_IDENTITY')
    need(re.findall(r'\blaunchedFromUid=(\d+)\b',block)==['1000'],'ALBUM_VIEW_NOT_FROM_CURRENT_ANDROID_UID1000_CALLER')
    intents=[line.strip() for line in block.splitlines() if re.match(r'\s*Intent \{',line)]
    need(len(intents)==1 and re.search(r'\bact=android\.intent\.action\.VIEW\b',intents[0])
        and re.search(r'\bdat='+re.escape(uri)+r'(?:\s|\})',intents[0])
        and re.search(r'\btyp='+re.escape(MIME)+r'(?:\s|\})',intents[0]),'ACTUAL_ALBUM_INTENT_MUST_MATCH_EXACT_OWNED_BUCKET')
    need(gallery_focus(flow,'album-route-focus-after-'+str(index))==focus,'ALBUM_ROUTE_WINDOW_CHANGED_DURING_READBACK')
    return {'verified':True,'round':index,'focus':focus,'previous_normal_launch_focus':before,
        'album_uri':uri,'caller_uid':1000,'activity_record_token':record_token[1],
        'actual_intent':intents[0],'actual_activity_block':block,'owned_bucket_row':copy.deepcopy(flow.album_bucket_row),
        'sole_video_row_in_bucket':True,'historical_runtime_authority_transferred':False}

def selected_native(value):
    context=value.get('window_context',{});window=context.get('selected_window',{});root=context.get('root',{})
    need(value.get('ok') is True and value.get('accessibility_mode_restoration_verified') is True
        and context.get('snapshot_complete') is True and context.get('truncated') is False
        and context.get('display_id')==window.get('display_id')==0 and window.get('active') is True
        and window.get('focused') is True and window.get('type')==1 and root.get('package')==GALLERY
        and root.get('visible') is True and window.get('root',{}).get('package')==GALLERY
        and type(root.get('window_id')) is int and root['window_id']==window.get('window_id'),
        'COMPLETE_CURRENT_NATIVE_ALBUM_WINDOW_REQUIRED')
    bounds=window.get('bounds');need(type(bounds) is list and len(bounds)==4 and all(type(v) is int for v in bounds)
        and bounds[0]<bounds[2] and bounds[1]<bounds[3],'ACTUAL_ALBUM_WINDOW_BOUNDS')
    return value.get('nodes',[]),bounds,window['window_id']

def title(nodes,bounds,window_id,folder):
    def one(predicate):
        selected=[n for n in nodes if n.get('package')==GALLERY and n.get('visible') is True and n.get('enabled') is True and predicate(n)]
        need(len(selected)==1,'ONE_EXACT_OWNED_ALBUM_TITLE_NODE');return selected[0]
    bar=one(lambda n:n.get('resource-id')=='android:id/action_bar' and n.get('class')=='android.view.ViewGroup')
    node=one(lambda n:n.get('class')=='android.widget.LinearLayout' and n.get('text')==''
        and n.get('content-desc')==folder+', Navigate up' and n.get('clickable') is True
        and n.get('editable') is False and n.get('password') is False and 16 in n.get('supported_actions',[]))
    icons=[one(lambda n,key=key:n.get('class')=='android.widget.ImageView' and n.get('resource-id')==key) for key in ('android:id/up','android:id/home')]
    def inside(outer,inner):
        return type(inner) is list and len(inner)==4 and all(type(x) is int for x in inner) and outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3]
    need(all(v.get('window_id')==window_id and inside(bounds,v.get('bounds_array')) for v in [bar,node,*icons])
        and inside(bar['bounds_array'],node['bounds_array']) and all(inside(node['bounds_array'],v['bounds_array']) for v in icons),
        'OWNED_ALBUM_TITLE_MUST_STAY_INSIDE_SAME_NATIVE_WINDOW')
    return {'verified':True,'album_name':folder,'observed_navigation_node':node,'actual_action_bar':bar,
        'actual_navigation_icons':icons,'native_window_id':window_id,'navigation_control_pressed':False}

def verify_thumbnail(image,palettes):
    """Recognize one four-quadrant fixture using two fixed source color profiles.

    MediaMetadataRetriever/bitmap and video-surface paths can use either the
    generated RGB codes or the independently specified 170M-to-sRGB profile.
    Neither profile is fitted to observed pixels; this is fixture identity,
    not color fidelity or an assertion about a thumbnail crop implementation.
    """
    need(image.mode=='RGB' and min(image.size)>=120,'OWNED_ALBUM_IMAGE_SIZE')
    factor=max(1,math.ceil(max(image.size)/360));small=image.resize((image.width//factor,image.height//factor),resample=0)
    proofs=[]
    for profile,palette in palettes.items():
        groups=[[] for _ in range(4)]
        for i,pixel in enumerate(small.getdata()):
            for color,target in enumerate(palette):
                if all(abs(pixel[j]-target[j])<=6 for j in range(3)):
                    groups[color].append((i%small.width,i//small.width));break
        if not all(len(g)>=40 for g in groups):continue
        boxes=[]
        for points in groups:
            l=min(x for x,y in points);r=max(x for x,y in points)+1;t=min(y for x,y in points);b=max(y for x,y in points)+1
            if len(points)/((r-l)*(b-t))<.94:break
            boxes.append([l,t,r,b])
        if len(boxes)!=4:continue
        red,green,blue,yellow=boxes
        if not (red[2]<=green[0] and blue[2]<=yellow[0] and red[3]<=blue[1] and green[3]<=yellow[1]):continue
        if not all(abs(a-b)<=2 for a,b in ((red[0],blue[0]),(green[0],yellow[0]),(red[2],blue[2]),(green[2],yellow[2]),
             (red[1],green[1]),(blue[1],yellow[1]),(red[3],green[3]),(blue[3],yellow[3]))):continue
        l=min(v[0] for v in boxes);t=min(v[1] for v in boxes);r=max(v[2] for v in boxes);b=max(v[3] for v in boxes)
        width=r-l;height=b-t;fraction=width*height/(small.width*small.height)
        if not (64<=width*factor<=512 and 64<=height*factor<=512 and .85<=width/height<=1.4
            and fraction<.20 and sum(map(len,groups))/(width*height)>.84):continue
        proofs.append({'verified':True,'thumbnail_verified':True,'full_image_verified':False,'palette_profile':profile,
            'fixed_palette_RGB':[list(v) for v in palette],'color_tolerance':6,'scope_size':list(image.size),
            'sample_size':list(small.size),'scope_fraction':fraction,'quadrant_counts':list(map(len,groups)),
            'sample_quadrant_bounds':boxes,'scope_pattern_bounds':[round(l*image.width/small.width),round(t*image.height/small.height),
                round(r*image.width/small.width),round(b*image.height/small.height)],'source_geometry':[640,480],
            'crop_algorithm_qualified':False,'audio_qualified':False,'color_fidelity_qualified':False})
    need(len(proofs)==1,'ONE_UNAMBIGUOUS_OWNED_VIDEO_THUMBNAIL_REQUIRED');return proofs[0]

def begin_api(s,name,request):
    f=s.case;c=s.c;a=f.album_context
    c.need(s.active_api is None and s.phase=='business' and a is not None and a['route']['verified'] is True
        and f.pending is None and a['round']==f.album_index and len(f.album_attempts)==a['round']+1,
        'ONLY_CURRENT_VERIFIED_ALBUM_READ_CONTEXT')
    caller=s.original_caller(['video_album.py','video_ui.py'],skip=('begin_api',))
    if name=='ui':
        c.need(caller=={'source':'video_album.py','function':'inspect_album'} and request=={
            'op':'dump','expected_package':GALLERY,'display':0,'accessibility_mode':'none'},'ONLY_CURRENT_ALBUM_TITLE_DUMP')
    else:
        c.need(name=='dispatch' and caller=={'source':'video_ui.py','function':'observe'} and a.get('title_ref') is not None
            and request=={'op':'observe','package':GALLERY,'display':0,'accessibility_mode':'none',
                'window_token':a['route']['focus']['window_token'],'with_png':True},'NO_ALBUM_PIXELS_BEFORE_OWNED_TITLE')
        c.read_ref(a['title_ref'])
    c.read_ref(a['route_ref']);s.guard();f.ui.stacks('api-current-owned-album-task');task=s.check_owned_task()
    actual=s.helper.foreground_callback();s.api_sequence+=1
    context={'schema':'pocket4-gallery-current-owned-video-album-api-context-v1','api':name,'request':copy.deepcopy(request),
        'phase':s.phase_ref,'owned_task':task,'claim':s.claimed_tasks[task]['source_ref'],'caller':caller,
        'api_sequence':s.api_sequence,'mutation_sent':False,'native_returns':0,'automatic_retry':False,
        'album_observation':True,'observed_focus':copy.deepcopy(a['route']['focus']),'album_route':a['route_ref']}
    foreground(s,actual,context)
    context['output']=str(c.private_dir(s.api_root/('api-%04d'%s.api_sequence),create=True))
    c.write_new(Path(context['output'])/'context.json',context);s.active_api=context;return context

def foreground(s,value,context):
    f=s.case;focus=s.last_focus;a=f.album_context
    s.c.need(s.phase=='business' and a is not None and context['mutation_sent'] is False
        and type(value) is dict and set(value)=={'package','activity','window_token'}
        and focus==context['observed_focus']==a['route']['focus'] and focus.get('verified') is True
        and focus['package']==GALLERY and expand(focus['activity'])==expand(focus['focused_activity'])==ACTIVITY
        and f.ui.owned is not None and focus['task']==f.ui.owned[0]==context['owned_task'] and focus['task'] in s.claimed_tasks
        and value=={k:focus[k] for k in ('package','activity','window_token')},'CURRENT_OWNED_ALBUM_WINDOW_CHANGED')

def write(flow,label,value):
    return flow.tx.write_new(Path(flow.s.root)/('album-'+label+'.json'),value)

def same_route(before,after):
    # ActivityRecord diagnostics also contain elapsed times and visibility
    # counters. Preserve both raw records, but compare their actual identity,
    # intent, caller, owned media and exact current window rather than timers.
    return {k:v for k,v in before.items() if k!='actual_activity_block'}=={
        k:v for k,v in after.items() if k!='actual_activity_block'}

def same_title(before,after):
    # Separate accessibility instrumentation connections may assign different
    # native window IDs to the same WindowManager window. Each native dump has
    # already required internally consistent root/window/node IDs. Across the
    # two dumps compare all title fields except those connection-local IDs;
    # the surrounding album context still binds the exact WM token and route.
    def stable(value):
        value=copy.deepcopy(value);value.pop('native_window_id')
        value['observed_navigation_node'].pop('window_id');value['actual_action_bar'].pop('window_id')
        for node in value['actual_navigation_icons']:node.pop('window_id')
        return value
    return stable(before)==stable(after)

def inspect_album(flow,index):
    s=flow.s;m=s.components['video_flow.py'];p=s.components['verify_pattern.py']
    need(index in (0,1) and index==len(flow.album_checks)==len(flow.album_attempts)==len(flow.result['pixel_rounds'])
        and flow.pending is None and flow.album_context is None and flow.ui.owned is not None,'ONE_ALBUM_CHECK_PER_ORIGINAL_NORMAL_ROUND')
    flow.album_index=index;flow.album_bucket_row=None;flow.album_sole_bucket_verified=False
    row=owned_bucket(flow,flow.query('album-owned-row-'+str(index),metadata_sql(flow)));flow.album_bucket_row=row
    members=flow.query('album-sole-bucket-'+str(index),members_sql(row['bucket_id']))
    need(members==[{'_id':row['_id'],'owner_package_name':m.PACKAGE}],'NO_OTHER_VIDEO_MAY_SHARE_THIS_OWNED_BUCKET')
    flow.album_sole_bucket_verified=True;before=gallery_focus(flow,'album-before-view-'+str(index));argv=view_argv(flow,index)
    flow.record('album-view-'+str(index)+'-intent',{'argv':argv,'owned_bucket':row,'focus':before,'automatic_retry':False})
    flow.pending='album-view-'+str(index);flow.album_attempts.append({'round':index,'task':flow.ui.owned[0],'automatic_retry':False})
    raw=s.android(argv,35).decode('utf-8','strict');flow.record('album-view-'+str(index)+'-receipt',{'stdout':raw})
    need(re.findall(r'^Status:\s*(\S+)',raw,re.M)==['ok'] and 'Error:' not in raw and 'Exception' not in raw,'ALBUM_VIEW_OUTCOME_UNKNOWN')
    route=read_route(flow,before);route_ref=write(flow,'route-'+str(index),route)
    flow.album_context={'round':index,'route':route,'route_ref':route_ref,'title_ref':None};flow.pending=None
    native=s.helper.ui({'op':'dump','expected_package':GALLERY,'display':0,'accessibility_mode':'none'})
    need(gallery_focus(flow,'album-after-native-title-'+str(index))==route['focus'],'ALBUM_TITLE_WINDOW_CHANGED')
    nodes,bounds,window_id=selected_native(native);album_title=title(nodes,bounds,window_id,m.FOLDER)
    title_ref=write(flow,'title-'+str(index),{'native':native,'title':album_title,'focus':route['focus']});flow.album_context['title_ref']=title_ref
    label='owned-video-album-'+str(index);fresh_nodes=flow.ui.observe(label,route['focus'])
    observed=flow.ui.last_observation;fresh_native=observed['native'];fresh_nodes,after_bounds,after_window=selected_native(fresh_native)
    after_title=title(fresh_nodes,after_bounds,after_window,m.FOLDER)
    need(after_bounds==bounds and same_title(album_title,after_title),'ALBUM_CHANGED_BETWEEN_TITLE_AND_PIXELS')
    after_title_ref=write(flow,'title-after-'+str(index),{'native':fresh_native,'title':after_title,'focus':route['focus']})
    shot=observed['screenshot'];png=s.c.regular(Path(s.components['video_ui.py'].ROOT)/(label+'.png'),33554432)
    with Image.open(io.BytesIO(png[0])) as decoded:
        image=decoded.convert('RGB');need(image.size==(shot['scope_width'],shot['scope_height'])
            and s.helper.image_sha(image)==shot['scope_sha256'],'ALBUM_PNG_NOT_BOUND_TO_ACTUAL_OBSERVATION')
        visual=verify_thumbnail(image,{'generated_source_RGB':p.SOURCE_COLORS,'source_170M_to_sRGB':p.COLORS})
    after_route=read_route(flow,before,route['focus']);after_route_ref=write(flow,'route-after-'+str(index),after_route)
    need(same_route(route,after_route),'ALBUM_ROUTE_CHANGED_AFTER_PIXELS')
    result={'verified':True,'round':index,'owned_media_uri':flow.media['uri'],'owned_media_sha256':flow.media['sha256'],
        'actual_sole_bucket':row,'route':route_ref,'route_after_pixels':after_route_ref,'title':title_ref,'title_after_pixels':after_title_ref,
        'thumbnail':visual,'actual_owned_window_png':png[1],
        'actual_scope_sha256':shot['scope_sha256'],'actual_context_token':shot['context_token'],
        'thumbnail_pressed':False,'default_album_pixels_captured':False,'new_UI_inputs':0,'album_VIEW_intents':1}
    write(flow,'verified-'+str(index),result);flow.album_checks.append(result)
    flow.result['album_checks']=copy.deepcopy(flow.album_checks);flow.album_context=None
    return result
