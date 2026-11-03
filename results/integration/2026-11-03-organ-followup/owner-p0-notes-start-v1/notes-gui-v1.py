import hashlib, importlib.util, json, os, select, subprocess, sys, time
from pathlib import Path
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi, GLib

request=json.loads(sys.argv[1]); output=Path(request['output'])
assert os.getuid()==1000 and not output.exists()
pid=request['pid']; pidfd=request['pidfd']; mode=request['mode']
receipt={'scope':'Assistant-operated actual original user GUI; no synthetic authority or direct model API',
         'mode':mode,'pid':pid,'start_ticks':request['start_ticks'],'actions':[],
         'physical_keyboard_qualified':False,'started_unix_ms':int(time.time()*1000),'passed':False}

def save():
    raw=(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode()
    temporary=output.with_suffix('.partial')
    with temporary.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temporary,output)

def alive():
    poll=select.poll();poll.register(pidfd,select.POLLIN)
    if poll.poll(0):raise RuntimeError('original held UI lifetime exited')
    assert f'Pid:\t{pid}\n' in Path('/proc/self/fdinfo/'+str(pidfd)).read_text()
    fields=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
    assert int(fields[19])==request['start_ticks'] and int(fields[1])==request['parent_pid']
    assert Path('/proc/'+str(pid)+'/exe').resolve(strict=True)==Path(request['executable'])

def settle():
    context=GLib.MainContext.default()
    for _ in range(64):
        if not context.pending():break
        context.iteration(False)

def wait(probe,label,seconds=12):
    end=time.monotonic()+seconds;last=None
    while time.monotonic()<end:
        alive();settle()
        try:
            value=probe()
            if value:return value
        except Exception as e:last=str(e)
        time.sleep(.04)
    raise RuntimeError(label+'; last='+str(last))

def children(node):
    for i in range(node.get_child_count()):
        child=node.get_child_at_index(i)
        if child is not None:yield child

def walk(node):
    todo=[node]
    for _ in range(4096):
        if not todo:return
        node=todo.pop();yield node;todo.extend(reversed(list(children(node))))
    raise RuntimeError('owned accessibility tree exceeded bound')

try:
    alive()
    helper=Path('/home/qian-qi/work/trill-organ-20261103-f1/hepta-current-source/apps/hepta-control-ui/test/x11_client_owner.py')
    assert hashlib.sha256(helper.read_bytes()).hexdigest()=='65744abe7717e9d9e5d018306114452df00990aed490e700ccfb3ea98ee20fbd'
    spec=importlib.util.spec_from_file_location('original_x11_owner',helper)
    owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
    with owner.XResOwner() as xres:
        window=wait(lambda:xres.find_visible(pid),'exact original window')
        receipt['x11_owner']=window
        if mode=='close':
            alive();xres.require_pid(window['xid'],pid)
            receipt['actions'].append({'name':'normal_window_close','attempted_unix_ms':int(time.time()*1000)})
            save()
            result=subprocess.run(['/usr/bin/xdotool','windowclose',str(window['xid'])],capture_output=True,text=True,timeout=5)
            receipt['close_exit_code']=result.returncode
            assert result.returncode==0
            poll=select.poll();poll.register(pidfd,select.POLLIN)
            assert poll.poll(8000),'owned GUI did not exit after normal window close'
            receipt['actual_lifetime_exited']=True
        elif mode=='send':
            Atspi.init();desktop=Atspi.get_desktop(0)
            app=wait(lambda:next((n for n in children(desktop) if n.get_process_id()==pid),None),'exact original AT-SPI process')
            def named(name):return next((n for n in walk(app) if n.get_name()==name),None)
            editor=wait(lambda:named('Message / 消息'),'original composer')
            assert Atspi.Text.get_text(editor,0,-1)=='','refuse to replace a pre-existing draft'
            assert editor.get_component_iface().grab_focus()
            editable=wait(lambda:editor.get_editable_text_iface(),'actual EditableText interface')
            receipt['prompt']=request['prompt']
            receipt['actions'].append({'name':'set_exact_composer_text','attempted_unix_ms':int(time.time()*1000)})
            save()
            assert editable.set_text_contents(request['prompt'])
            wait(lambda:Atspi.Text.get_text(editor,0,-1)==request['prompt'],'original composer readback')
            send=wait(lambda:named('Send'),'original Send control')
            wait(lambda:send.get_state_set().contains(Atspi.StateType.ENABLED),'real original authenticated Send enabled')
            action=send.get_action_iface();names=[action.get_action_name(i) for i in range(action.get_n_actions())]
            index=next(i for i,name in enumerate(names) if name.lower() in ('click','press','activate'))
            alive();xres.require_pid(window['xid'],pid)
            receipt['actions'].append({'name':'one_original_send','attempted_unix_ms':int(time.time()*1000),'no_retry':True})
            save() # A lost acknowledgement cannot cause another Send.
            receipt['send_acknowledged']=bool(action.do_action(index))
            assert receipt['send_acknowledged']
            wait(lambda:Atspi.Text.get_text(editor,0,-1)=='','original composer consumed once')
            receipt['composer_consumed']=True
        else:raise RuntimeError('unknown finite GUI action')
    receipt['passed']=True
except Exception as e:
    receipt['error']=repr(e)
finally:
    receipt['finished_unix_ms']=int(time.time()*1000);save();print(json.dumps(receipt,ensure_ascii=False))
if not receipt['passed']:sys.exit(1)
