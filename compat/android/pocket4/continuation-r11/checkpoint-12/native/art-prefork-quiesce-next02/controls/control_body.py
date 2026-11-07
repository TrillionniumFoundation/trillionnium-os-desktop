def function(text, signature):
    require(text.count(signature) == 1, 'function signature is absent or ambiguous: '+signature)
    start = text.index(signature)
    masked = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda match: ''.join('\n' if c == '\n' else ' ' for c in match.group()),
                    text, flags=re.S)
    opening = masked.index('{', start)
    depth = 0
    for end in range(opening, len(masked)):
        if masked[end] == '{':
            depth += 1
        elif masked[end] == '}':
            depth -= 1
            if depth == 0:
                return text[start:end+1]+'\n'
    raise RuntimeError('function body not closed')


def run_case(binary, argument, expected_code, expected_events, label, report):
    require(not children(), 'owned child before case')
    stdout = OUT/(label+'.stdout')
    stderr = OUT/(label+'.stderr')
    with stdout.open('xb') as out, stderr.open('xb') as err:
        proc = subprocess.Popen([str(binary), argument], cwd=OUT,
                                env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C'},
                                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                start_new_session=True)
        timeout = False
        try:
            code = proc.wait(timeout=min(12, DEADLINE-time.monotonic()))
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait(timeout=3)
    data, outpin = held(stdout, 65536)
    _, errpin = held(stderr, 65536)
    lines = data.decode().splitlines()
    events = [line[6:] for line in lines if line.startswith('EVENT ')]
    fatals = [line for line in lines if line.startswith('FATAL ')]
    row = {'label':label, 'argv':[str(binary),argument], 'returncode':code,
           'timed_out':timeout, 'stdout':outpin, 'stderr':errpin,
           'events':events, 'fatal_records':fatals, 'direct_child_reaped':True,
           'remaining_owned_children':children(), 'expected_code':expected_code,
           'pass':False}
    report['cases'].append(row)
    require(not timeout and code == expected_code and not row['remaining_owned_children'],
            'owned case exit/reaping differs: '+label)
    require(events == expected_events, 'actual extracted call order differs: '+label)
    if expected_code == 70:
        require(fatals == ['FATAL kernel-single-thread-wait reads=2001 callbacks=0 quiesces=0'],
                'baseline did not reach the actual bounded wait failure')
    elif expected_code == 71:
        require(fatals == ['FATAL bridge-quiesce-rejected reads=0 callbacks=1 quiesces=1'],
                'rejected quiesce was not fatal before the actual kernel wait')
    else:
        require(not fatals, 'unexpected fatal record')
    row['pass'] = True


def execute():
    global DEADLINE
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator UID1000 required')
    require(Path(__file__).absolute() == HERE/'run_control.py', 'exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(), 'create-only attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    DEADLINE = time.monotonic()+100
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36,1,0,0,0) == 0, 'cannot establish owned subreaper')
    require(not children(), 'unexpected initial owned child')
    report = {'schema':1,'state':'RUNNING','started_utc':utc(),
              'scope':'exact three extracted ART/NativeBridge functions with real owned kernel threads and explicit peripheral fixtures',
              'complete_ART_translation_unit':False, 'production_raw_owner':False,
              'installed_ART_binding':False, 'Android_execution':False, 'Main_actions':0,
              'commands':[], 'cases':[]}
    source_rows = {}
    tool_rows = {}
    resource_fd = -1
    before = None
    def interrupted(number, frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned signal '+str(number))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        resource_fd, before = begin_resources()
        report['owned_resources_before'] = before
        sources = {}
        for name, expected in INPUTS.items():
            raw, row = held(HERE/name, 524288)
            require(row['sha256'] == expected['sha256'] and row['bytes'] == expected['bytes'],
                    'frozen source mismatch: '+name)
            source_rows[name] = row
            sources[name] = raw.decode()
        for name in ['/usr/bin/g++','/usr/bin/ld','/usr/bin/as']:
            path = Path(name).resolve(strict=True)
            require(path.is_relative_to('/usr/bin') or path.is_relative_to('/usr/lib'),
                    'compiler tool resolved outside installed system roots')
            _, row = held(path, 128*1024*1024)
            tool_rows[name] = {'resolved':str(path), **row}
        env = {'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C','TMPDIR':str(OUT)}
        command(['/usr/bin/g++','--version'], OUT, env, 'compiler-version', report['commands'], 5)
        wait = function(sources['preimage-runtime.cc'], 'static void WaitUntilSingleThreaded() {')
        require(wait == function(sources['candidate-runtime.cc'], 'static void WaitUntilSingleThreaded() {'),
                'actual wait body changed')
        bridge = function(sources['bridge-full.cc'], 'void PreZygoteForkNativeBridge() {')
        wrapper = function(sources['art-interface-full.cc'], 'void PreZygoteForkNativeBridge() {')
        report['extracted_sources'] = {'wait_sha256':sha(wait.encode()),
                                      'native_bridge_hook_sha256':sha(bridge.encode()),
                                      'art_wrapper_sha256':sha(wrapper.encode())}
        binaries = {}
        for arm, name, flag in [('preimage1','preimage-runtime.cc',1),
                                ('candidate1','candidate-runtime.cc',1),
                                ('candidate0','candidate-runtime.cc',0)]:
            directory = OUT/arm
            directory.mkdir(mode=0o700)
            body = function(sources[name], 'void Runtime::PreZygoteFork() {')
            for filename, text in [('art_wait.inc',wait),('art_prefork.inc',body),
                                   ('native_bridge_prefork.inc',bridge),('art_bridge_wrapper.inc',wrapper)]:
                write_new(directory/filename,text.encode())
            binary = directory/'order-control'
            argv = ['/usr/bin/g++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-pthread',
                    '-DDROIDLOOM_NATIVE_GENERATION_RUNTIME='+str(flag),'-I'+str(directory),
                    str(HERE/'lifecycle_fixture.cc'),'-o',str(binary)]
            command(argv, OUT, env, 'compile-'+arm, report['commands'], 20)
            raw, row = held(binary, 4*1024*1024)
            require(raw.startswith(b'\x7fELF'), 'compiled control is not ELF')
            binaries[arm] = (binary,row)
        run_case(binaries['preimage1'][0], 'worker', 70,
                 ['worker-ready','jit-prefork','art-threadlist-wait','kernel-wait-first-read'],
                 'baseline-owner-prevents-kernel-wait', report)
        run_case(binaries['candidate1'][0], 'worker', 0,
                 ['worker-ready','jit-prefork','legacy-guest-log-close','quiesce-enter',
                  'quiesce-complete','art-threadlist-wait','kernel-wait-first-read','heap-prefork','returned'],
                 'enabled-quiesce-precedes-kernel-wait', report)
        run_case(binaries['candidate0'][0], 'no-worker', 0,
                 ['jit-prefork','art-threadlist-wait','kernel-wait-first-read','heap-prefork',
                  'legacy-guest-log-close','generation-disabled','returned'],
                 'disabled-original-call-order', report)
        run_case(binaries['candidate1'][0], 'reject-stop', 71,
                 ['worker-ready','jit-prefork','legacy-guest-log-close','quiesce-enter'],
                 'enabled-stop-rejection-remains-fatal', report)
        require(all(held(path,4*1024*1024)[1] == row for path,row in binaries.values()),
                'control ELF changed during run')
        report['ELFs'] = {arm:row for arm,(_,row) in binaries.items()}
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type':type(error).__name__, 'message':str(error),
                                  'errno':getattr(error,'errno',None), 'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['cleanup'] = cleanup_children()
        changes = []
        for name,row in source_rows.items():
            try:
                if held(HERE/name,524288)[1] != row: changes.append(name)
            except Exception as error:
                changes.append({'source':name,'error':repr(error)})
        for name,row in tool_rows.items():
            try:
                path = Path(name).resolve(strict=True)
                if str(path) != row['resolved'] or held(path,128*1024*1024)[1] != {k:v for k,v in row.items() if k != 'resolved'}:
                    changes.append(name)
            except Exception as error:
                changes.append({'tool':name,'error':repr(error)})
        report['source_and_compiler_changes'] = changes
        report['observed_signals'] = OBSERVED_SIGNALS
        try:
            require(before is not None and resource_fd >= 0, 'owned resource admission missing')
            report['owned_resource_gate'] = finish_resources(resource_fd,before,report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}
            report['state'] = 'FAIL'
        finally:
            if resource_fd >= 0: os.close(resource_fd)
        cleanup = report['cleanup']
        if changes or cleanup['forced_cleanup'] or cleanup['remaining'] or cleanup['errors']:
            report['state'] = 'FAIL'
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json',report)
        print(json.dumps({'state':report['state'],'result':result,'complete_ART_TU':False,'Main_actions':0}),flush=True)
    return 0 if report['state'] == 'PASS' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'owned_cases':4,'full_ART_TU':False,
                          'actual_kernel_wait':True,'peripheral_ART_and_owner_actions':'explicit fixtures',
                          'requires_explicit_execute_once':True,'Main_actions':0}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: run_control.py [--execute-once]')
