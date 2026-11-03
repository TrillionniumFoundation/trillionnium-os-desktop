#!/usr/bin/python3 -I
"""Pocket4 Droidloom/Digitalis Android control. No ADB and no arbitrary shell API."""
import argparse,base64,csv,fcntl,glob,hashlib,io,json,math,os,re,subprocess,sys,time
from PIL import Image, ImageChops

CTL='/usr/bin/droidloomctl'
RUNNER='local.pocket4.actions.v2/.ActionRunner'
HELPER='/usr/local/libexec/android-digitalis-observe-helper'
ENV_KEYS={
 'PATH','BOOTCLASSPATH','DEX2OATBOOTCLASSPATH','ANDROID_ART_ROOT','ANDROID_ASSETS',
 'ANDROID_BOOTLOGO','ANDROID_DATA','ANDROID_I18N_ROOT','ANDROID_ROOT','ANDROID_STORAGE',
 'ANDROID_TZDATA_ROOT','ASEC_MOUNTPOINT','DOWNLOAD_CACHE','EXTERNAL_STORAGE',
 'LOOP_MOUNTPOINT','STANDALONE_SYSTEMSERVER_JARS','SYSTEMSERVERCLASSPATH','LANG'
}
HOST_ENV={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8'}
OCR_ENV={**HOST_ENV,'OMP_THREAD_LIMIT':'1','OMP_NUM_THREADS':'1'}

def proc_cmd(pid):
    return open(f'/proc/{pid}/cmdline','rb').read().replace(b'\0',b' ').decode('utf-8','replace').strip()

def ppid(pid):
    for line in open(f'/proc/{pid}/status',encoding='utf-8',errors='replace'):
        if line.startswith('PPid:'): return int(line.split()[1])
    raise RuntimeError('PPID_NOT_FOUND')

def require_root_process(pid,exe=None):
    if type(pid) is not int or pid<=1: raise RuntimeError('INVALID_CELL_PID')
    fields={line.split(':',1)[0]:line.split(':',1)[1].strip()
            for line in open(f'/proc/{pid}/status',encoding='utf-8',errors='replace') if ':' in line}
    if fields.get('Uid','').split()!=['0','0','0','0']:
        raise RuntimeError('CELL_PROCESS_NOT_ROOT')
    if exe is not None and os.readlink(f'/proc/{pid}/exe')!=exe:
        raise RuntimeError('UNEXPECTED_CELL_EXECUTABLE')

def cell_ancestors(pid,host):
    # Only the daemon-recorded production host may anchor a bridge. A separate
    # test cell can have the same command line but is never a fallback target.
    cur=pid; seen={pid}; ancestors=[]
    for _ in range(128):
        par=ppid(cur)
        if par<=1 or par in seen: return None
        ancestors.append(par)
        if par==host: return ancestors
        seen.add(par); cur=par
    return None

def discover():
    status=json.loads(subprocess.run([CTL,'status','--json'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8,env=HOST_ENV,check=True).stdout)
    if status.get('state')!='running' or 'Android is ready' not in status.get('message',''):
        raise RuntimeError('DROIDLOOM_NOT_READY')
    host=status.get('host_pid')
    require_root_process(host)
    bridges=[]
    for p in glob.glob('/proc/[0-9]*'):
        try:
            pid=int(p.rsplit('/',1)[1])
            if proc_cmd(pid)=='app_process /system/bin com.android.droidloom.input.InputBridge':
                ancestors=cell_ancestors(pid,host)
                if ancestors is not None: bridges.append((pid,ancestors))
        except (OSError,ValueError):
            pass
    if len(bridges)!=1: raise RuntimeError(f'INPUT_BRIDGE_COUNT:{len(bridges)}')
    bridge,ancestors=bridges[0]; init=None
    for par in ancestors:
        try: cmd=proc_cmd(par)
        except OSError: cmd=''
        if cmd=='/init' or cmd.startswith('/init '):
            init=par; break
    if not init: raise RuntimeError('ANDROID_INIT_NOT_FOUND')
    require_root_process(bridge,'/system/bin/app_process64')
    require_root_process(init,'/system/bin/init')
    owner=ppid(init)
    require_root_process(owner,'/usr/bin/unshare')
    expected='/usr/bin/unshare --mount --pid --mount-proc --ipc --uts --fork --kill-child=TERM --propagation=private /usr/bin/droidloom-supervisor development-enter --spec /etc/droidloom/cell.json'
    if proc_cmd(owner)!=expected: raise RuntimeError('UNEXPECTED_CELL_OWNER')
    # The verified Ubuntu compatibility launcher is the daemon's recorded
    # host_pid; its immediate child is the real util-linux unshare process.
    # Also accept a directly recorded real unshare process on an upstream host.
    if owner!=host and ppid(owner)!=host: raise RuntimeError('CELL_OWNER_NOT_STATUS_CHILD')
    if owner!=host:
        expected_host='/usr/bin/python3 -I /usr/local/libexec/droidloom-compat/unshare --mount --pid --mount-proc --ipc --uts --fork --kill-child=TERM --forward-signals --propagation=private /usr/bin/droidloom-supervisor development-enter --spec /etc/droidloom/cell.json'
        if proc_cmd(host)!=expected_host: raise RuntimeError('UNEXPECTED_CELL_LAUNCHER')
        if not re.fullmatch(r'/usr/bin/python3(?:\.\d+)?',os.readlink(f'/proc/{host}/exe')):
            raise RuntimeError('UNEXPECTED_CELL_LAUNCHER_EXECUTABLE')
    for ns in ('mnt','pid','uts','ipc'):
        if os.readlink(f'/proc/{bridge}/ns/{ns}')!=os.readlink(f'/proc/{init}/ns/{ns}'):
            raise RuntimeError('INPUT_BRIDGE_NAMESPACE_MISMATCH')
    if os.readlink(f'/proc/{init}/ns/mnt')==os.readlink('/proc/self/ns/mnt'):
        raise RuntimeError('ANDROID_CELL_IS_HOST_MOUNT_NAMESPACE')
    raw=open(f'/proc/{bridge}/environ','rb').read().split(b'\0')
    env={}
    for item in raw:
        if b'=' not in item: continue
        k,v=item.split(b'=',1)
        k=k.decode('utf-8','strict')
        if k in ENV_KEYS:
            value=v.decode('utf-8','strict')
            if len(value)>65536 or '\x00' in value: raise RuntimeError('INVALID_ANDROID_ENV')
            env[k]=value
    required={'PATH','BOOTCLASSPATH','DEX2OATBOOTCLASSPATH','ANDROID_ROOT','ANDROID_DATA','ANDROID_ART_ROOT'}
    if not required.issubset(env): raise RuntimeError('INCOMPLETE_ANDROID_ENV')
    return init,env,status

def arun(args,timeout=30):
    init,env,_=discover()
    envargs=[]
    for k in sorted(env): envargs.append(k+'='+env[k])
    # Terminate the Android command's process group before the host deadline.
    # Instrumentation may already have acted; timeout still means unknown
    # outcome and must not invite an automatic retry.
    inner_timeout=max(1,timeout-5)
    cmd=['/usr/bin/nsenter','-t',str(init),'-m','-p','-u','-i','/system/bin/env']+envargs+['/system/xbin/su','2000','/system/bin/timeout','-k','2',str(inner_timeout)]+list(args)
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,env=HOST_ENV)
    if p.returncode in (124,137):
        raise subprocess.TimeoutExpired(cmd,inner_timeout,output=p.stdout,stderr=p.stderr)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).decode('utf-8','replace')[-1800:])
    return p.stdout

STRING_SELECTORS={'text','contains','id','desc','package','class'}
BOOL_SELECTORS={'focused','editable','enabled','clickable','scrollable','selected','checked'}
MAX_PNG=32*1024*1024

class ControlError(RuntimeError):
    def __init__(self,code,**details):
        super().__init__(code); self.details=details

def require(condition,code,**details):
    if not condition: raise ControlError(code,**details)

def package_name(value):
    require(isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+',value)),'INVALID_PACKAGE')
    return value

def digest(value):
    require(isinstance(value,str) and bool(re.fullmatch('[0-9a-f]{64}',value)),'INVALID_SHA256')
    return value

def ui(r):
    mutation=r['op'] in ('click','set-text','type-text','scroll-forward','scroll-backward')
    protocol_details={'outcome_unknown':mutation,'automatic_retry':False}
    selector=r.get('selector',{})
    require(isinstance(selector,dict) and not set(selector)-(STRING_SELECTORS|BOOL_SELECTORS),'INVALID_SELECTOR')
    for k,v in selector.items():
        require((k in STRING_SELECTORS and isinstance(v,str) and len(v.encode('utf8'))<=4096)
                or (k in BOOL_SELECTORS and type(v) is bool),'INVALID_SELECTOR_VALUE')
    if 'index' in r: require(type(r['index']) is int and r['index']>=0,'INVALID_INDEX')
    if r['op'] in ('set-text','type-text'):
        require(isinstance(r.get('value'),str) and len(r['value'].encode('utf8'))<=4096,'TEXT_TOO_LARGE')
    encoded=base64.b64encode(json.dumps(r,ensure_ascii=True,separators=(',',':')).encode()).decode()
    try:raw=arun(['/system/bin/am','instrument','-w','-r','-e','request',encoded,RUNNER],timeout=70).decode('utf8','replace')
    except subprocess.TimeoutExpired:raise
    except Exception:raise ControlError('UI_RUNNER_TRANSPORT_ERROR',**protocol_details)
    matches=re.findall(r'^INSTRUMENTATION_RESULT: sidecar_result_base64=(.*)$',raw,re.M)
    require(len(matches)==1,'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
    try: result=json.loads(base64.b64decode(matches[0],validate=True))
    except Exception: raise ControlError('UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
    require(isinstance(result,dict),'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
    require(type(result.get('ok')) is bool,'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
    if result.get('ok') is not True:
        require(type(result.get('outcome_unknown')) is bool and result.get('automatic_retry') is False,
                'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
        code=result.get('error')
        require(isinstance(code,str) and bool(re.fullmatch('[A-Z0-9_]+',code)),'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
        raise ControlError(code,outcome_unknown=result.get('outcome_unknown') is True or 'MAY_HAVE_OCCURRED' in code,automatic_retry=False)
    if mutation:
        require(result.get('performed')==r['op'],'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
        if r['op'] in ('click','scroll-forward','scroll-backward'):
            require(isinstance(result.get('target'),dict) and isinstance(result.get('actual_target'),dict)
                    and result.get('visual_verified') is False and result.get('business_success_verified') is False,
                    'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
        else:
            require(type(result.get('characters')) is int and result['characters']>=0 and type(result.get('password')) is bool
                    and type(result.get('readback_verified')) is bool,'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
            require(result['password'] or result['readback_verified'],'UI_RUNNER_PROTOCOL_ERROR',**protocol_details)
    require(result.get('accessibility_mode_restoration_verified') is True,'ACCESSIBILITY_MODE_RESTORATION_UNVERIFIED',
            outcome_unknown=mutation,automatic_retry=False)
    return result

def foreground():
    # Discard raw dumpsys immediately. Only package/activity identifiers are retained.
    raw=arun(['/system/bin/dumpsys','window','displays'],timeout=15).decode('utf8','replace')
    lines=[line.strip() for line in raw.splitlines() if 'mCurrentFocus=' in line]
    values=[]
    for line in lines:
        m=re.search(r'\bWindow\{([0-9a-fA-F]+)\s+u\d+\s+([A-Za-z_][A-Za-z0-9_.]*)/([A-Za-z0-9_.$]+)',line)
        if m: values.append((m.group(1).lower(),m.group(2),m.group(3)))
    require(len(set(values))==1,'FOREGROUND_UNVERIFIED')
    token,pkg,activity=values[0];return {'package':package_name(pkg),'activity':activity,'window_token':token}

def window_state(expected_package=None,window_token=None,display=0,accessibility_mode='none'):
    require(type(display) is int and display==0,'ONLY_DEFAULT_DISPLAY_SUPPORTED')
    request={'op':'meta','display':display,'accessibility_mode':accessibility_mode}
    if expected_package: request['expected_package']=package_name(expected_package)
    result=ui(request); meta=result['window_context']; selected=meta.get('selected_window')
    require(isinstance(selected,dict),'NO_VERIFIED_FOCUSED_APPLICATION_WINDOW')
    require(selected.get('display_id')==display and selected.get('focused') is True and selected.get('type')==1,'WINDOW_NOT_FOCUSED_APPLICATION')
    pkg=package_name(selected.get('root',{}).get('package',''))
    front=foreground(); require(front['package']==pkg,'FOREGROUND_PACKAGE_MISMATCH')
    if expected_package: require(pkg==expected_package,'FOREGROUND_PACKAGE_MISMATCH')
    if window_token is not None:
        require(isinstance(window_token,str) and bool(re.fullmatch('[0-9a-f]{1,32}',window_token)),'INVALID_WINDOW_TOKEN')
        require(window_token==front['window_token'],'WINDOW_CHANGED')
    init,_,_=discover()
    return {'package':pkg,'activity':front['activity'],'window_token':front['window_token'],
            'window_id':selected['window_id'],'a11y_window_id_is_connection_scoped':True,'display_id':display,
            'window_bounds':selected['bounds'],'android_init_host_pid':init,'accessibility_mode':accessibility_mode,
            'accessibility_query':{k:meta.get(k) for k in ('flags','capabilities','is_accessibility_tool','accessibility_enabled','touch_exploration_enabled')}}

def png_image(data):
    require(isinstance(data,bytes) and len(data)<=MAX_PNG and data.startswith(b'\x89PNG\r\n\x1a\n'),'INVALID_SCREENSHOT')
    try:
        with Image.open(io.BytesIO(data)) as image:
            require(image.format=='PNG' and 0<image.width<=8192 and 0<image.height<=8192 and image.width*image.height<=32_000_000,'INVALID_SCREENSHOT_DIMENSIONS')
            image.load();return image.convert('RGB')
    except ControlError: raise
    except Exception: raise ControlError('INVALID_SCREENSHOT')

def valid_rect(rect,width,height):
    require(isinstance(rect,(list,tuple)) and len(rect)==4 and all(type(v) is int for v in rect),'INVALID_CROP')
    l,t,r,b=rect;require(0<=l<r<=width and 0<=t<b<=height,'CROP_OUTSIDE_ORIGINAL_SCREEN')
    return list(rect)

def image_sha(image):
    return hashlib.sha256(image.width.to_bytes(4,'big')+image.height.to_bytes(4,'big')+image.tobytes()).hexdigest()

def stable_window(state):
    return {k:state[k] for k in ('package','activity','window_token','display_id','window_bounds','android_init_host_pid')}

def context_token(state,rect,size):
    return hashlib.sha256(json.dumps({'window':stable_window(state),'scope':rect,'screen':size},sort_keys=True,separators=(',',':')).encode()).hexdigest()

def capture(r):
    # Metadata/camera pixels do not need touch exploration. Only the requested native operation enables it.
    before=window_state(r.get('package'),r.get('window_token'),r.get('display',0),'none')
    data=arun(['/system/bin/screencap','-p'],timeout=20);image=png_image(data)
    after=window_state(before['package'],before['window_token'],before['display_id'],before['accessibility_mode'])
    require(stable_window(before)==stable_window(after),'WINDOW_CHANGED_DURING_CAPTURE')
    win=valid_rect(before['window_bounds'],image.width,image.height)
    rect=valid_rect(r.get('crop',win),image.width,image.height)
    require(rect[0]>=win[0] and rect[1]>=win[1] and rect[2]<=win[2] and rect[3]<=win[3],'CROP_OUTSIDE_APPLICATION_WINDOW')
    scoped=image.crop(tuple(rect))
    meta={'source':'android_screencap','frame_sha256':hashlib.sha256(data).hexdigest(),'scope_sha256':image_sha(scoped),
          'width':image.width,'height':image.height,'scope_bounds':rect,'scope_width':scoped.width,'scope_height':scoped.height,
          'coordinate_space':'original_android_screen_pixels','scope':before,'context_token':context_token(before,rect,[image.width,image.height]),
          'captured_unix_ms':int(time.time()*1000),'atomic_snapshot':False}
    return {'meta':meta,'image':scoped}

def ocr_words(frame):
    # Only the requested in-window region enters OCR. No temp images or text logs.
    image=frame['image'];scale=2 if image.width<=2048 and image.height<=2048 else 1
    image=image.resize((image.width*scale,image.height*scale),Image.Resampling.LANCZOS) if scale!=1 else image
    buf=io.BytesIO();image.save(buf,format='PNG')
    require(os.path.isfile('/usr/bin/tesseract'),'OCR_NOT_INSTALLED')
    p=subprocess.run(['/usr/bin/nice','-n','10','/usr/bin/tesseract','stdin','stdout','-l','chi_sim+eng','--psm','11','tsv'],input=buf.getvalue(),
                     stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20,env=OCR_ENV)
    require(p.returncode==0,'OCR_FAILED');require(len(p.stdout)<=4*1024*1024,'OCR_OUTPUT_TOO_LARGE')
    words=[];left,top,right,bottom=frame['meta']['scope_bounds']
    try:
        for row in csv.DictReader(io.StringIO(p.stdout.decode('utf8','strict')),delimiter='\t'):
            if row.get('level')!='5' or not row.get('text','').strip():continue
            conf=float(row['conf']);x,y,w,h=(int(row[k]) for k in ('left','top','width','height'))
            require(math.isfinite(conf) and 0<=conf<=100 and w>0 and h>0,'OCR_INVALID_RECORD')
            bounds=[max(left,left+math.floor(x/scale)),max(top,top+math.floor(y/scale)),
                    min(right,left+math.ceil((x+w)/scale)),min(bottom,top+math.ceil((y+h)/scale))]
            require(bounds[0]<bounds[2] and bounds[1]<bounds[3],'OCR_INVALID_RECORD')
            words.append({'text':row['text'],'confidence':conf,'bounds':bounds,'line':tuple(row[k] for k in ('page_num','block_num','par_num','line_num'))})
            require(len(words)<=4000,'OCR_TOO_MANY_WORDS')
    except ControlError:raise
    except Exception:raise ControlError('OCR_INVALID_RECORD')
    return words

def normalized(text):
    return ''.join(text.split())

def visual_matches(words,text,min_confidence=85):
    require(isinstance(text,str) and 0<len(text.encode('utf8'))<=256 and normalized(text),'INVALID_VISUAL_TEXT')
    require(type(min_confidence) in (int,float) and math.isfinite(min_confidence) and 85<=min_confidence<=100,'CONFIDENCE_MUST_BE_85_TO_100')
    target=normalized(text);lines={}
    for word in words:lines.setdefault(word['line'],[]).append(word)
    matches={}
    for line in lines.values():
        for start in range(len(line)):
            joined=''
            for end in range(start,min(len(line),start+64)):
                joined+=normalized(line[end]['text'])
                if len(joined)>len(target):break
                if joined!=target:continue
                span=line[start:end+1];bounds=[min(w['bounds'][0] for w in span),min(w['bounds'][1] for w in span),
                      max(w['bounds'][2] for w in span),max(w['bounds'][3] for w in span)];confidence=min(w['confidence'] for w in span)
                # OCR letters do not establish native editability/clickability or a resource ID.
                item={'text':' '.join(w['text'] for w in span),'source':'ocr_tesseract','confidence':confidence,
                      'confidence_is_probability':False,'eligible':confidence>=min_confidence,'bounds':bounds,
                      'resource_id':None,'editable':None,'clickable':None,'native_semantics_verified':False}
                matches[tuple(bounds)]=item
    return list(matches.values())

def validate_snapshot(r,frame):
    require('package' in r and 'window_token' in r and 'display' in r,'EXPLICIT_WINDOW_SCOPE_REQUIRED')
    meta=frame['meta']
    require(r['package']==meta['scope']['package'] and r['display']==meta['scope']['display_id']
            and r['window_token']==meta['scope']['window_token'],'WINDOW_CHANGED',action_taken=False)
    for request_key,meta_key in [('frame_sha256','frame_sha256'),('scope_sha256','scope_sha256'),('context_token','context_token')]:
        require(digest(r.get(request_key))==meta[meta_key],'STALE_FRAME',action_taken=False)

def click_result(r,before,point):
    l,t,right,bottom=before['meta']['scope_bounds'];x,y=point
    require(type(x) is int and type(y) is int and l<=x<right and t<=y<bottom,'COORDINATES_OUTSIDE_OBSERVED_SCOPE')
    fresh=capture(r);validate_snapshot(r,fresh)
    # Last fresh capture includes public foreground verification. Injection targets display 0 explicitly.
    source=r.get('input_source','touch');require(source in ('touch','mouse'),'INVALID_INPUT_SOURCE')
    command=['/system/bin/input']+(['mouse'] if source=='mouse' else [])+['-d','0','tap',str(x),str(y)]
    try:arun(command)
    except Exception:raise ControlError('INPUT_RESULT_UNKNOWN',outcome_unknown=True,automatic_retry=False)
    result={'ok':True,'performed':r['op'],'input_command_completed':True,'coordinates':[x,y],
            'source':'ocr_coordinate' if r['op']=='visual-click' else 'observed_coordinate','input_source':source,'before':fresh['meta'],
            'business_success_verified':False,'automatic_retry':False}
    try:
        time.sleep(.25);after=capture({'package':r['package'],'display':0,'crop':r.get('crop',before['meta']['scope_bounds']),
                                     'accessibility_mode':r.get('accessibility_mode','none')})
        result['after']=after['meta'];result['screen_changed']=after['meta']['scope_sha256']!=fresh['meta']['scope_sha256']
        if after['image'].size==fresh['image'].size:
            difference=ImageChops.difference(fresh['image'],after['image']).convert('L')
            histogram=difference.histogram();result['changed_pixel_fraction']=round(1-histogram[0]/(difference.width*difference.height),6)
        result['visual_verified']=False
        result['observation_note']='Pixel change does not establish whether the intended business action succeeded.'
    except Exception:
        result.update({'post_action_observation_available':False,'visual_verified':False,'outcome_unknown':True})
    return result

def enhanced_dispatch(r):
    op=r['op'];frame=capture(r)
    if op=='observe':
        result={'ok':True,'screenshot':frame['meta']}
        if r.get('with_png'):
            buf=io.BytesIO();frame['image'].save(buf,format='PNG');result['screenshot_png_base64']=base64.b64encode(buf.getvalue()).decode()
        # The native tree may contain unrelated/private content outside a requested crop: crop observations omit it.
        if 'crop' not in r:
            native=ui({'op':'dump','expected_package':frame['meta']['scope']['package'],'display':0,
                       'accessibility_mode':r.get('accessibility_mode','none')})
            end=window_state(frame['meta']['scope']['package'],frame['meta']['scope']['window_token'],0,'none')
            require(stable_window(end)==stable_window(frame['meta']['scope']),'WINDOW_CHANGED_DURING_OBSERVE')
            result['native']=native
        else:result['native']={'included':False,'reason':'cropped_observation_excludes_unscoped_native_text'}
        return result
    if op=='snapshot-tap':
        validate_snapshot(r,frame);require(isinstance(r.get('coords'),list) and len(r['coords'])==2,'INVALID_COORDINATES')
        return click_result(r,frame,r['coords'])
    if op=='visual-click':validate_snapshot(r,frame)
    words=ocr_words(frame);matches=visual_matches(words,r.get('text'),r.get('min_confidence',85))
    if op=='visual-find':return {'ok':True,'source':'ocr_tesseract','screenshot':frame['meta'],'count':len(matches),'matches':matches,
                                 'semantic_controls_available':False,'matching':'exact_text_ignoring_whitespace'}
    require(op=='visual-click','UNSUPPORTED_OPERATION');validate_snapshot(r,frame)
    require(len(matches)>0,'NO_VISUAL_MATCH',action_taken=False)
    require(len(matches)==1,'AMBIGUOUS_VISUAL_MATCH',count=len(matches),action_taken=False)
    require(matches[0]['eligible'],'LOW_OCR_CONFIDENCE',action_taken=False)
    l,t,right,bottom=matches[0]['bounds'];result=click_result(r,frame,[(l+right)//2,(t+bottom)//2])
    result['target']=matches[0];return result

def dispatch(r):
    allowed={'op','coords','duration','package','selector','index','value','display','window_id','window_token','crop','with_png',
             'frame_sha256','scope_sha256','context_token','text','min_confidence','include_invisible','accessibility_mode','accessibilityMode','method','input_source'}
    require(not set(r)-allowed,'UNKNOWN_ARGUMENT');op=r.get('op')
    if 'accessibilityMode' in r:
        require('accessibility_mode' not in r or r['accessibility_mode']==r['accessibilityMode'],'CONFLICTING_ACCESSIBILITY_MODE')
        r=dict(r);r['accessibility_mode']=r.pop('accessibilityMode')
    require(r.get('accessibility_mode','none') in ('none','touch-exploration'),'INVALID_ACCESSIBILITY_MODE')
    if r.get('accessibility_mode')=='touch-exploration':require(r.get('package')=='com.tencent.mm','TOUCH_EXPLORATION_REQUIRES_EXPLICIT_WECHAT_SCOPE')
    if 'method' in r:require(op=='click' and r['method'] in ('accessibility','mouse'),'INVALID_CLICK_METHOD')
    if 'input_source' in r:require(op in ('visual-click','snapshot-tap') and r['input_source'] in ('touch','mouse'),'INVALID_INPUT_SOURCE')
    for key in ('with_png','include_invisible'):
        if key in r:require(type(r[key]) is bool,'INVALID_BOOLEAN')
    if op in ('observe','visual-find','visual-click','snapshot-tap'):return enhanced_dispatch(r)
    if op=='commit-text':raise ControlError('COMMIT_TEXT_NOT_CONFIGURED')
    if op in ('dump','find','click','set-text','type-text','scroll-forward','scroll-backward'):
        request={k:v for k,v in r.items() if k in {'op','selector','index','value','display','include_invisible','accessibility_mode','method'}}
        if 'package' in r:request['expected_package']=package_name(r['package'])
        if op not in ('click','scroll-forward','scroll-backward'):return ui(request)
        before=capture(r)
        request['expected_package']=before['meta']['scope']['package']
        result=ui(request);result['before']=before['meta'];result['business_success_verified']=False
        try:
            time.sleep(.25)
            after=capture({'package':before['meta']['scope']['package'],'display':0,'accessibility_mode':r.get('accessibility_mode','none')})
            result['after']=after['meta'];result['screen_changed']=before['meta']['scope_sha256']!=after['meta']['scope_sha256']
            result['observation_note']='Pixel change does not establish whether the intended business action succeeded.'
        except Exception:result.update({'post_action_observation_available':False,'outcome_unknown':True,'automatic_retry':False})
        return result
    if op=='status':
        init,_,st=discover();props=dict(re.findall(r'^\[([^\]]+)\]: \[(.*)\]$',arun(['/system/bin/getprop']).decode('utf8','replace'),re.M))
        return {'ok':True,'backend':'droidloom-teto-digitalis-derived','running':True,'host_pid':st.get('host_pid'),'android_init_host_pid':init,
                'boot_completed':props.get('sys.boot_completed',''),'android':props.get('ro.build.version.release',''),'sdk':props.get('ro.build.version.sdk',''),
                'native_bridge':props.get('ro.dalvik.vm.native.bridge',''),'berberis_flags':props.get('ro.berberis.flags',''),
                'adbd':props.get('init.svc.adbd',''),'adb_tcp_port':props.get('service.adb.tcp.port',''),
                'persist_adb_tcp_port':props.get('persist.adb.tcp.port',''),'usb_config':props.get('sys.usb.config',''),
                'persist_usb_config':props.get('persist.sys.usb.config','')}
    if op=='screenshot':return arun(['/system/bin/screencap','-p'])
    if op=='apps':return {'ok':True,'packages':arun(['/system/bin/pm','list','packages','-3']).decode().splitlines()}
    if op in ('home','back','enter'):
        arun(['/system/bin/input','keyevent',{'home':'KEYCODE_HOME','back':'KEYCODE_BACK','enter':'KEYCODE_ENTER'}[op]])
        return {'ok':True,'performed':op,'visual_verified':False}
    if op in ('tap','swipe'):
        coords=r.get('coords',[]);require(isinstance(coords,list) and len(coords)==(2 if op=='tap' else 4) and all(type(x) is int and 0<=x<=32767 for x in coords),'INVALID_COORDINATES')
        args=['/system/bin/input',op]+[str(x) for x in coords]
        if op=='swipe':
            duration=r.get('duration',300);require(type(duration) is int and 50<=duration<=5000,'INVALID_DURATION');args.append(str(duration))
        arun(args);return {'ok':True,'performed':op,'visual_verified':False}
    if op=='launch':
        pkg=package_name(r.get('package'));text=arun(['/system/bin/cmd','package','resolve-activity','--brief','-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER',pkg]).decode()
        comps=[s.strip() for s in text.splitlines() if re.fullmatch(r'[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+',s.strip())]
        if len(comps)!=1:
            apps=json.loads(subprocess.run([CTL,'applications','--json'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8,env=HOST_ENV,check=True).stdout)
            comps=[x.get('component','') for x in apps.get('applications',[]) if x.get('package')==pkg and re.fullmatch(r'[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+',x.get('component',''))]
        require(len(comps)==1,'NO_UNIQUE_LAUNCHER');out=arun(['/system/bin/am','start','-W','-n',comps[0]],timeout=35).decode('utf8','replace')
        require('Error:' not in out and 'Exception' not in out,'LAUNCH_FAILED');return {'ok':True,'component':comps[0],'output':out}
    raise ControlError('UNSUPPORTED_OPERATION')

def helper():
    require(os.geteuid()==0,'HELPER_REQUIRES_SUDO');raw=sys.stdin.buffer.readline(65537)
    require(len(raw)<=65536,'REQUEST_TOO_LARGE')
    try:r=json.loads(raw)
    except Exception:raise ControlError('INVALID_JSON')
    require(isinstance(r,dict),'OBJECT_REQUIRED')
    fd=os.open('/run/lock/android-digitalis-actions.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ControlError('DIGITALIS_BUSY_NO_ACTION_TAKEN')
        result=dispatch(r)
        if isinstance(result,bytes):require(result.startswith(b'\x89PNG\r\n\x1a\n'),'INVALID_SCREENSHOT');sys.stdout.buffer.write(result)
        else:print(json.dumps(result,ensure_ascii=False))
    finally:os.close(fd)

def client():
    p=argparse.ArgumentParser(description='Pocket4 local Android control and explicitly labelled visual observations; no ADB.')
    sub=p.add_subparsers(dest='op',required=True)
    for op in ('status','apps','home','back','enter'):sub.add_parser(op)
    s=sub.add_parser('screenshot');s.add_argument('output',nargs='?',default='-')
    s=sub.add_parser('tap');s.add_argument('coords',nargs=2,type=int)
    s=sub.add_parser('swipe');s.add_argument('coords',nargs=4,type=int);s.add_argument('--duration',type=int,default=300)
    s=sub.add_parser('launch');s.add_argument('package')
    for op in ('dump','find','click','set-text','type-text','scroll-forward','scroll-backward'):
        s=sub.add_parser(op);s.add_argument('--package');s.add_argument('--accessibility-mode',choices=('none','touch-exploration'),default=None)
        if op in ('find','click','set-text','scroll-forward','scroll-backward'):
            for key in sorted(STRING_SELECTORS-{'package'}):s.add_argument('--'+key)
            for key in sorted(BOOL_SELECTORS):s.add_argument('--'+key,action=argparse.BooleanOptionalAction,default=None)
            if op in ('click','set-text'):s.add_argument('--index',type=int)
            if op=='click':s.add_argument('--method',choices=('accessibility','mouse'))
        if op in ('set-text','type-text'):s.add_argument('value')
        if op=='dump':s.add_argument('--include-invisible',action='store_true',default=None)
    for op in ('observe','visual-find','visual-click','snapshot-tap'):
        s=sub.add_parser(op);s.add_argument('--package',required=op in ('visual-click','snapshot-tap'))
        s.add_argument('--accessibility-mode',choices=('none','touch-exploration'),default=None)
        s.add_argument('--display',type=int,default=0);s.add_argument('--window-id',type=int,help='Observed connection-scoped accessibility ID, metadata only')
        s.add_argument('--window-token',required=op in ('visual-click','snapshot-tap'),help='Stable WindowManager token from observation')
        s.add_argument('--crop',nargs=4,type=int)
        if op=='observe':s.add_argument('--output')
        if op in ('visual-find','visual-click'):s.add_argument('--text',required=True);s.add_argument('--min-confidence',type=float,default=85)
        if op in ('visual-click','snapshot-tap'):
            for name in ('frame-sha256','scope-sha256','context-token'):s.add_argument('--'+name,required=True)
            s.add_argument('--input-source',choices=('touch','mouse'),default=None)
        if op=='snapshot-tap':s.add_argument('coords',nargs=2,type=int)
    s=sub.add_parser('commit-text');s.add_argument('value')
    args=vars(p.parse_args());output=args.pop('output',None);r={k:v for k,v in args.items() if v is not None}
    if r['op'] in ('find','click','set-text','scroll-forward','scroll-backward'):
        r['selector']={k:r.pop(k) for k in STRING_SELECTORS|BOOL_SELECTORS if k in r and k!='package'}
        if 'package' in r:r['selector']['package']=r['package']
    if r['op']=='observe' and output:r['with_png']=True
    q=subprocess.run(['/usr/bin/sudo','-n',HELPER],input=(json.dumps(r,ensure_ascii=False)+'\n').encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
    if q.stderr:sys.stderr.buffer.write(q.stderr)
    if q.returncode:return q.returncode
    if output and output!='-':
        if r['op']=='screenshot':
            with open(output,'wb') as f:f.write(q.stdout)
            print(json.dumps({'ok':True,'path':os.path.abspath(output),'bytes':len(q.stdout)}));return 0
        result=json.loads(q.stdout);encoded=result.pop('screenshot_png_base64',None)
        if encoded:
            image=base64.b64decode(encoded,validate=True)
            with open(output,'wb') as f:f.write(image)
            result['screenshot']['saved_scope_path']=os.path.abspath(output)
        print(json.dumps(result,ensure_ascii=False))
    else:sys.stdout.buffer.write(q.stdout)
    return 0

if __name__=='__main__':
    try:
        if os.path.basename(sys.argv[0])==os.path.basename(HELPER):helper()
        else:sys.exit(client())
    except subprocess.TimeoutExpired:
        print(json.dumps({'ok':False,'error':'TIMEOUT','outcome_unknown':True,'automatic_retry':False}),file=sys.stderr);sys.exit(2)
    except ControlError as e:
        print(json.dumps({'ok':False,'error':str(e),'automatic_retry':False,**e.details},ensure_ascii=False),file=sys.stderr);sys.exit(1)
    except Exception:
        # Never put OCR/selector/input/private UI strings in an exception log.
        print(json.dumps({'ok':False,'error':'CONTROL_FAILED','automatic_retry':False}),file=sys.stderr);sys.exit(1)
