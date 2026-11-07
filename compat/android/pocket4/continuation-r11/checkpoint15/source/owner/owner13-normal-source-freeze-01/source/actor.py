#!/usr/bin/env python3
"""One actual producer13 cell inside one inherited, finite private outer unit."""
import argparse, ctypes, hashlib, json, os, signal, socket, stat, sys, time, traceback, types
from pathlib import Path


def load(args):
    raw = Path(args.prepared).read_bytes()
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != args.prepared_sha256:
        raise RuntimeError('external prepared digest differs')
    prepared = json.loads(raw)
    if not prepared.get('success'): raise RuntimeError('preparation did not succeed')
    here = Path(__file__).parent
    modules = {}
    for name in ('pinned_support', 'owned', 'prepare', 'qualify'):
        path = here / (name + '.py'); fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd); body = os.read(fd, 256 * 1024)
            row = prepared['source_files'][name + '.py']
            if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022 or len(body) != row['bytes'] or hashlib.sha256(body).hexdigest() != row['sha256']:
                raise RuntimeError('held packaged module differs: ' + name)
        finally: os.close(fd)
        module = types.ModuleType(name); module.__file__ = str(path); sys.modules[name] = module
        exec(compile(body, str(path), 'exec'), module.__dict__); modules[name] = module
    owned = modules['owned']; plan, _ = owned.read_json(here.parent / 'plan.json', prepared['plan_sha256'])
    owned.need(str(here) == plan['package'] + '/source' and str(args.prepared) == plan['state'] + '/prepared.json', 'package/state authority differs')
    for name, row in prepared['source_files'].items():
        fd = modules['pinned_support'].pinned(here / name, row['sha256'])
        os.close(fd)
    return prepared, plan, modules


def mount(source, target, kind, flags, data=None):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mount.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p)
    libc.mount.restype = ctypes.c_int
    b = lambda x: None if x is None else str(x).encode()
    if libc.mount(b(source), b(target), b(kind), flags, b(data)):
        error = ctypes.get_errno(); raise OSError(error, os.strerror(error), str(target))


def namespace_ids():
    names = ('pid', 'pid_for_children', 'mnt', 'cgroup', 'user', 'net', 'ipc', 'uts', 'time', 'time_for_children')
    return {name: {'device': (s := os.stat('/proc/self/ns/' + name)).st_dev, 'inode': s.st_ino} for name in names}


def isolate(plan, owned):
    before = namespace_ids()
    initial_user = os.stat('/proc/1/ns/user')
    owned.need(before['user'] == {'device': initial_user.st_dev, 'inode': initial_user.st_ino}, 'initial user namespace required')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.unshare(0x00020000 | 0x40000000):
        code = ctypes.get_errno(); raise OSError(code, os.strerror(code), 'private mount/net unshare')
    after = namespace_ids()
    owned.need(all(after[k] != before[k] for k in ('mnt', 'net')) and
               all(after[k] == before[k] for k in before if k not in ('mnt', 'net')), 'private namespace boundary differs')
    mount(None, '/', None, (1 << 18) | 16384)
    # Both mount targets already exist. No mkdir/chmod happens in the host view.
    mount('tmpfs', '/run', 'tmpfs', 2 | 4, 'mode=0755,size=134217728')
    mount('tmpfs', '/var/lib', 'tmpfs', 2 | 4 | 8, 'mode=0755,size=16777216')
    for path, mode in (('/run/netns', 0o755), ('/run/droidloom', 0o755),
                       ('/run/droidloom/cells', 0o755), ('/var/lib/droidloom', 0o700),
                       ('/var/lib/droidloom/lifecycle-claims', 0o700)):
        os.mkdir(path, mode)
    mount(plan['claim_store_backing'], '/var/lib/droidloom/lifecycle-claims', None, 4096)
    source = owned.root_directory(plan['claim_store_backing'])
    target = owned.root_directory('/var/lib/droidloom/lifecycle-claims')
    try: owned.need(owned.file_id(source) == owned.file_id(target), 'persistent private claim projection differs')
    finally: os.close(source); os.close(target)
    owned.need(Path('/run/netns').is_dir() and namespace_ids() == after, 'private isolation changed')
    return {'before': before, 'after': after, 'persistent_claim_backing': plan['claim_store_backing'],
            'private_run_identity': {'device': (s := os.stat('/run')).st_dev, 'inode': s.st_ino},
            'private_var_lib_identity': {'device': (s := os.stat('/var/lib')).st_dev, 'inode': s.st_ino}}


def role_env(runtime):
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': runtime + '/home',
        'XDG_RUNTIME_DIR': runtime, 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=' + runtime + '/bus',
        'XDG_CONFIG_HOME': runtime + '/config', 'XDG_STATE_HOME': runtime + '/state',
        'XDG_CACHE_HOME': runtime + '/cache', 'XDG_DATA_HOME': runtime + '/data',
        'TMPDIR': runtime + '/tmp', 'TMP': runtime + '/tmp', 'TEMP': runtime + '/tmp',
        'XDG_SESSION_TYPE': 'wayland', 'OMP_NUM_THREADS': '1'}


def native_lmkd(init, expected, owned):
    matches = []
    target_ns = init.snapshot()['namespaces'][0]
    for name in os.listdir('/proc'):
        if not name.isdecimal(): continue
        try:
            st = os.stat('/proc/' + name + '/ns/pid')
            if {'device': st.st_dev, 'inode': st.st_ino} != target_ns: continue
            directory = owned.directory('/proc/' + name)
            try:
                status = dict(line.split(':', 1) for line in owned.bounded(directory, 'status').decode().splitlines() if ':' in line)
                if [int(x) for x in status['Uid'].split()] != [1069] * 4: continue
            finally: os.close(directory)
            proc = owned.Process(int(name))
            if proc.exe_sha256 == expected: matches.append(proc)
            else: proc.close()
        except (FileNotFoundError, ProcessLookupError): continue
    if len(matches) != 1:
        for proc in matches: proc.close()
        raise RuntimeError('exact native LMKD process is not unique')
    proc = matches[0]
    try:
        owned.need(proc.value['parent'] == init.value['pid'], 'native LMKD is not actual init service child')
        directory = os.open('fd', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=proc.proc)
        try:
            inherited = []
            for number in (198, 199, 200, 201):
                try: inherited.append({'fd': number, 'target': os.readlink(str(number), dir_fd=directory)})
                except FileNotFoundError: pass
            owned.need(not inherited, 'fixed init capabilities survived native LMKD exec')
        finally: os.close(directory)
        proc.live()
        return proc, {'snapshot': proc.snapshot(), 'fixed_inherited_slots_absent': True}
    except BaseException:
        proc.close(); raise


def observe_init_hello(audit, owned):
    """One live, held identity/clock sample; no kernel log attribution."""
    matches = [row for row in audit['records'] if row['detail']['event'] == 'init_hello']
    if not matches: return None
    owned.need(len(matches) == 1, 'repeated init HELLO in identity observation')
    row = matches[0]; init = row['detail']['init']
    nonce = audit['nonce']
    owned.need(isinstance(nonce, str) and len(nonce) == 64 and nonce != '0' * 64 and
               all(c in '0123456789abcdef' for c in nonce), 'observed generation nonce malformed')
    proc = owned.Process(init['process']['pid'])
    try:
        proc.live()
        before = time.monotonic_ns()
        boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        realtime = time.time_ns()
        snapshot = proc.snapshot()
        after = time.monotonic_ns()
        for key in ('process', 'namespaces', 'executable', 'executable_sha256'):
            owned.need(snapshot[key] == init[key], 'observed init differs from actual HELLO: ' + key)
        owned.need(0 < row['observed_monotonic_ns'] <= before <= after and boot > 0 and realtime > 0,
                   'observed init clock bracket invalid')
        proc.live()
        return proc, {'schema': 1, 'generation_nonce': nonce, 'audit_sequence': row['sequence'],
            'audit_observed_monotonic_ns': row['observed_monotonic_ns'], 'snapshot': snapshot,
            'monotonic_before_ns': before, 'monotonic_after_ns': after,
            'boottime_ns': boot, 'realtime_ns': realtime, 'atomic_clock_sample': False,
            'global_kernel_lines_attributed': False}
    except BaseException:
        proc.close(); raise


def run(args, prepared, plan, modules):
    owned, support, prepare, qualify = (modules[x] for x in ('owned', 'pinned_support', 'prepare', 'qualify'))
    result = {'schema': 1, 'kind': 'owner13-real-normal01', 'attempt_nonce': plan['attempt_nonce'],
              'success': False, 'production_ready': False, 'installed_owner_qualified': False,
              'pressure_effect_qualified': False, 'rc_property_reload_qualified': False, 'errors': [],
              'prepared_sha256': args.prepared_sha256, 'started_monotonic_ns': time.monotonic_ns()}
    evidence = state = outer = host = domains = -1; tools = {}; children = []; held = {}; domain = endpoint_fd = -1
    daemon = None; socket_id = None; stop_requested = False; before = None; start_attempted = False
    try:
        owned.need(os.getuid() == os.geteuid() == os.getgid() == 0 and os.uname().machine == 'x86_64', 'real owned actor requires host root/x86_64')
        state = owned.root_directory(plan['state']); evidence = owned.root_directory(plan['state'] + '/evidence')
        owned.need(owned.file_id(state) == prepared['state_identity'], 'prepared state replaced')
        group, outer = owned.own_cgroup()
        owned.need(group == '/system.slice/' + plan['unit'], 'actor is outside exact new unit')
        before = owned.sample_cgroup(outer); owned.require_limits(before, plan['outer_limits'])
        result['outer_before'] = before; result['actor_pid'] = os.getpid()
        self_process = owned.Process(os.getpid())
        try: result['actor_initial'] = self_process.snapshot()
        finally: self_process.close()
        end = time.monotonic() + 15
        while True:
            try: gate, gate_sha = owned.read_json(Path(plan['state']) / 'gate.json'); break
            except FileNotFoundError:
                owned.need(time.monotonic() < end, 'external initial unit binding deadline exceeded'); time.sleep(0.02)
        owned.need(gate['attempt_nonce'] == plan['attempt_nonce'] and gate['prepared_sha256'] == args.prepared_sha256 and
                   gate['actor_process'] == result['actor_initial']['process'] and gate['cgroup_identity'] == before['identity'] and
                   gate['invocation'] == os.environ.get('INVOCATION_ID') and len(gate['invocation']) == 32, 'external unit gate differs')
        result['gate_sha256'] = gate_sha; result['invocation'] = gate['invocation']
        owned.save(state, 'runtime-claim.json', {'attempt_nonce': plan['attempt_nonce'], 'prepared_sha256': args.prepared_sha256,
            'actor_process': result['actor_initial']['process'], 'cgroup_identity': before['identity'], 'invocation': gate['invocation'], 'retry_allowed': False})
        result['id_availability'] = prepare.available_ids(plan['spec'])
        prepare.resources(plan)
        for path, row in prepared['tools'].items():
            fd, observed = prepare.inspect_tool(path, row['sha256']); owned.need(observed == row, 'prepared host tool identity changed'); tools[path] = fd
        fd, row = prepare.inspect_tool(plan['presenter']['path'], plan['presenter']['sha256'])
        owned.need(row == prepared['presenter'], 'actual private presenter changed'); tools['presenter'] = fd
        for role, row in prepared['copied_artifacts'].items():
            tools[role] = support.pinned(row['path'], row['sha256'], role != 'init-barrier')
            owned.need(owned.file_id(tools[role]) == row['identity'], 'sealed candidate replaced')
        spec_raw = Path(plan['package'] + '/cell.json').read_bytes()
        owned.need(hashlib.sha256(spec_raw).hexdigest() == plan['canonical_spec_sha256'], 'sealed actual CellSpec differs')
        # All children inherit host/ and can never be started by a host manager
        # after the private namespace boundary has been established.
        host = owned.make_child(outer, 'host')
        owned.write_at(host, 'cgroup.procs', str(os.getpid()))
        owned.need(not owned.bounded(outer, 'cgroup.procs').strip(), 'outer unit has unexpected internal process')
        owned.write_at(outer, 'cgroup.subtree_control', '+memory +cpu +pids')
        domains = owned.make_child(outer, 'domains')
        owned.write_at(domains, 'cgroup.subtree_control', '+memory +cpu +pids')
        result['isolation'] = isolate(plan, owned)
        runtime = '/run/p4-owner07-user'; os.mkdir(runtime, 0o700); os.chown(runtime, 1000, 1000)
        for name in ('home', 'config', 'state', 'cache', 'data', 'tmp'):
            path = runtime + '/' + name; os.mkdir(path, 0o700); os.chown(path, 1000, 1000)
        for name, body in [('bus.conf', '<busconfig><type>session</type><listen>unix:path=' + runtime + '/bus</listen><auth>EXTERNAL</auth><policy context="default"><deny user="*"/><allow user="1000"/><allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>\n'),
                           ('sway.conf', 'xwayland disable\noutput HEADLESS-1 mode 1280x800@30Hz scale 1\ndefault_border none\nfocus_follows_mouse no\nmouse_warping none\n')]:
            path = Path(runtime) / name; fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try: os.write(fd, body.encode()); os.fchown(fd, 1000, 1000)
            finally: os.close(fd)
        env = role_env(runtime)
        bus = owned.Child('bus', ['/usr/bin/dbus-daemon', '--nofork', '--nopidfile', '--config-file=' + runtime + '/bus.conf'], tools['/usr/bin/dbus-daemon'], evidence, env, 1000, prepared['helper_groups']); children.append(bus)
        owned.endpoint(runtime + '/bus', bus.process, 1000, socket.SOCK_STREAM)
        sway_env = dict(env, WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='gles2', WLR_RENDER_DRM_DEVICE='/dev/dri/renderD128')
        sway = owned.Child('sway', ['/usr/bin/sway', '--config', runtime + '/sway.conf'], tools['/usr/bin/sway'], evidence, sway_env, 1000, prepared['helper_groups']); children.append(sway)
        end = time.monotonic() + 20; wayland = None
        while time.monotonic() < end:
            sway.process.live()
            paths = [x for x in Path(runtime).glob('wayland-*') if stat.S_ISSOCK(x.lstat().st_mode)]
            if len(paths) == 1:
                owned.endpoint(str(paths[0]), sway.process, 1000, socket.SOCK_STREAM, 2); wayland = str(paths[0]); break
            owned.need(len(paths) <= 1, 'multiple private Wayland endpoints'); time.sleep(0.05)
        owned.need(wayland is not None, 'private headless compositor did not become ready')
        presenter_env = dict(env, WAYLAND_DISPLAY=wayland, DROIDLOOM_MODE='desktop',
            DROIDLOOM_HOST_SOCKET=plan['spec']['denial_socket'], DROIDLOOM_HOST_PEER_UID='1000',
            DROIDLOOM_HOST_PEER_GID='1000', DROIDLOOM_RENDER_NODE='/dev/dri/renderD128')
        presenter = owned.Child('presenter', [plan['presenter']['path']], tools['presenter'], evidence, presenter_env, 1000, prepared['helper_groups']); children.append(presenter)
        owned.endpoint(plan['spec']['denial_socket'], presenter.process, 1000, socket.SOCK_SEQPACKET)
        daemon_env = {'PATH': '/usr/local/libexec/droidloom-compat:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}
        daemon = owned.Child('daemon', [plan['package'] + '/bin/droidloomd', '--socket', plan['control_socket'],
            '--supervisor', plan['package'] + '/bin/droidloom-supervisor', '--spec-directory', plan['package']], tools['droidloomd'], evidence, daemon_env); children.append(daemon)
        socket_id = owned.endpoint(plan['control_socket'], daemon.process, 0, socket.SOCK_STREAM)
        result['producer'] = daemon.process.snapshot()
        for child in children:
            snap = child.process.snapshot()
            owned.need(snap['namespaces'][2] == result['isolation']['after']['mnt'] and
                       snap['namespaces'][5] == result['isolation']['after']['net'], 'actual child escaped private outer namespaces')
        result['children'] = [child.original for child in children]
        initial = owned.control(plan['control_socket'], daemon.process, socket_id, {'command': 'status'})
        owned.need(initial['ok'] and initial['state'] == 'stopped' and 'relay_lifecycle' not in initial, 'fresh daemon has unexpected previous generation')
        result['start_requested_monotonic_ns'] = time.monotonic_ns(); start_attempted = True
        result['start_response'] = owned.control(plan['control_socket'], daemon.process, socket_id,
            {'command': 'start', 'spec': plan['package'] + '/cell.json'}, 20)
        owned.need(result['start_response']['ok'], 'actual producer Start failed')
        end = time.monotonic() + 65
        while time.monotonic() < end:
            response = owned.control(plan['control_socket'], daemon.process, socket_id, {'command': 'status'}, 4)
            result['latest_status'] = response
            audit = response.get('relay_lifecycle')
            if audit and 'init_identity_clock_observation' not in result and 'init_identity_clock_observation_error' not in result:
                try:
                    observed = observe_init_hello(audit, owned)
                    if observed is not None:
                        held['init'], result['init_identity_clock_observation'] = observed
                except BaseException as error:
                    # A diagnostic miss must not replace the original lifecycle
                    # failure. The success qualifier separately requires this
                    # live binding, and there is no silent PID retry.
                    result['init_identity_clock_observation_error'] = repr(error)
            owned.need(response['ok'] and response['state'] == 'running', 'actual producer stopped or failed before ACTIVE')
            if audit:
                owned.need(not audit['recording_incomplete'] and not audit['first_failure'] and not audit['retirement_failure'] and not audit['cleanup_failure'], 'actual lifecycle audit records a failure')
                events = [r['detail']['event'] for r in audit['records']]
                if events and events[-1] == 'broker_active':
                    result['active_response'] = response; result['active_observed_monotonic_ns'] = time.monotonic_ns(); break
            time.sleep(0.05)
        owned.need('active_response' in result, 'actual native enrollment ACTIVE deadline exceeded')
        audit = result['active_response']['relay_lifecycle']
        details = {r['detail']['event']: r['detail'] for r in audit['records']}
        for role, record in [('owner', details['owner_attached']['process']),
                             ('init', details['init_hello']['init']['process']),
                             ('broker', details['broker_ready']['process'])]:
            if role not in held: held[role] = owned.Process(record['pid'])
            proc = held[role]
            owned.need(proc.observation() == record, 'actual ' + role + ' differs from producer audit')
        native, native_record = native_lmkd(held['init'], plan['artifacts']['lmkd']['sha256'], owned)
        held['lmkd'] = native; result['native_lmkd'] = native_record
        result['observed_processes'] = {role: proc.snapshot() for role, proc in held.items()}
        init_root = os.open('root', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=held['init'].proc)
        projected = -1
        try:
            result['init_root_identity'] = owned.file_id(init_root)
            projected = os.dup(init_root)
            for part in ('sys', 'fs', 'cgroup'):
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=projected)
                os.close(projected); projected = next_fd
            owned.require_cgroup2(projected)
            result['init_projected_cgroup_identity'] = owned.file_id(projected)
            held['init'].live()
        finally:
            if projected >= 0: os.close(projected)
            os.close(init_root)
        nonce = audit['nonce']; owned.need(len(nonce) == 64 and all(c in '0123456789abcdef' for c in nonce), 'actual generation nonce malformed')
        result['actual_generation_nonce'] = nonce
        result['generation_claim'], result['generation_claim_sha256'] = owned.read_json(Path(plan['claim_store_backing']) / ('u' + str(plan['spec']['host_uid']) + '.active'))
        domain_path = plan['spec']['pressure_relay']['cgroup_parent'] + '/g-' + nonce + '/android'
        domain = owned.directory(domain_path); result['generation_domain_before_stop'] = owned.sample_cgroup(domain)
        owned.need(owned.file_id(domain) == details['prepared']['domain'], 'externally held Android domain differs')
        endpoint_path = plan['spec']['runtime_dir'] + '/lmkd-relay-' + nonce + '/droidloom-lmkd-psi'
        endpoint_fd = os.open(endpoint_path, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
        result['endpoint_identity'] = owned.file_id(endpoint_fd)
        owned.need(result['endpoint_identity'] == details['broker_ready']['status']['endpoint'], 'actual broker endpoint differs')
        result['children_alive_at_active'] = [child.process.snapshot() for child in children]
        # The only normal lifecycle effect after Start is the original public Stop.
        stop_requested = True; result['stop_requested_monotonic_ns'] = time.monotonic_ns()
        result['stop_response'] = owned.control(plan['control_socket'], daemon.process, socket_id, {'command': 'stop'}, 25)
        result['stop_returned_monotonic_ns'] = time.monotonic_ns()
        owned.need(result['stop_response']['ok'] and result['stop_response']['state'] == 'stopped', 'actual original Stop failed')
        for proc in held.values(): owned.await_dead(proc.pidfd, 4)
        result['held_generation_processes_dead'] = {role: owned.dead(proc.pidfd) for role, proc in held.items()}
        result['retained_status'] = owned.control(plan['control_socket'], daemon.process, socket_id, {'command': 'status'})
        owned.need(result['retained_status']['relay_lifecycle'] == result['stop_response']['relay_lifecycle'], 'retained retirement audit changed')
        absent = [Path(plan['spec']['runtime_dir']), Path(plan['claim_store_backing']) / ('u' + str(plan['spec']['host_uid']) + '.active'), Path(domain_path).parent]
        owned.need(all(not os.path.lexists(p) for p in absent), 'owned runtime/claim/domain remains after normal Stop')
        result['runtime_claim_domain_absent'] = [str(p) for p in absent]
        result['native_lifecycle_validated'] = qualify.qualify_lifecycle(plan, result)
    except BaseException as error:
        owned.record_error(result, 'normal', error); result['traceback'] = traceback.format_exc()
    finally:
        if daemon is not None and socket_id is not None and start_attempted and not stop_requested:
            try:
                stop_requested = True
                result['failure_cleanup_stop'] = owned.control(plan['control_socket'], daemon.process, socket_id, {'command': 'stop'}, 25)
                owned.need(result['failure_cleanup_stop']['ok'], 'failure cleanup original Stop failed')
            except BaseException as error: owned.record_error(result, 'failure_cleanup_stop', error)
        result['child_retirement'] = []
        for child in reversed(children):
            try:
                row = child.stop(); row['role'] = child.role; result['child_retirement'].append(row)
                owned.need(not row.get('forced_kill') and row.get('returncode') in (0, -signal.SIGTERM), 'owned helper required abnormal cleanup')
                if child.role == 'daemon': owned.need(row.get('returncode') == 0, 'real daemon shutdown did not succeed')
            except BaseException as error: owned.record_error(result, 'retire_' + child.role, error)
            finally: child.close()
        for role, proc in held.items():
            try: owned.need(owned.dead(proc.pidfd), 'generation process survived actual producer shutdown: ' + role)
            except BaseException as error: owned.record_error(result, 'generation_final_' + role, error)
            finally: proc.close()
        if endpoint_fd >= 0: os.close(endpoint_fd)
        if domain >= 0: os.close(domain)
        if outer >= 0:
            try:
                final = owned.sample_cgroup(outer); owned.require_limits(final, plan['outer_limits'])
                owned.healthy(before, final)
                owned.need(final['values']['pids.current'] == '1' and not final['values']['cgroup.procs'], 'unknown descendant survives outer retirement')
                owned.need(host >= 0 and owned.bounded(host, 'cgroup.procs').decode().split() == [str(os.getpid())], 'final host subgroup differs')
                if domains >= 0:
                    owned.need(owned.counters(owned.bounded(domains, 'cgroup.events').decode()).get('populated') == '0' and
                               owned.bounded(domains, 'pids.current').strip() == b'0', 'generation domain remains populated')
                    extra = [n for n in os.listdir(domains) if stat.S_ISDIR(os.stat(n, dir_fd=domains, follow_symlinks=False).st_mode)]
                    owned.need(not extra, 'generation cgroup residue remains')
                result['outer_final'] = {'sample': final, 'actor_pid': os.getpid(), 'invocation': result.get('invocation'),
                    'attempt_nonce': plan['attempt_nonce'], 'observed_monotonic_ns': time.monotonic_ns(), 'unit': plan['unit']}
            except BaseException as error: owned.record_error(result, 'outer_final', error)
        result['finished_monotonic_ns'] = time.monotonic_ns()
        result['success'] = not result['errors'] and result.get('native_lifecycle_validated') is True and 'outer_final' in result
        if state >= 0: owned.save(state, 'actor-result.json', result)
        for fd in tools.values(): os.close(fd)
        for fd in (domains, host, outer, evidence, state):
            if fd >= 0: os.close(fd)
    print(json.dumps({'success': result['success'], 'first_error': result.get('first_error'), 'result_path': plan['state'] + '/actor-result.json', 'production_ready': False}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--prepared', required=True); parser.add_argument('--prepared-sha256', required=True)
    arguments = parser.parse_args()
    raise SystemExit(run(arguments, *load(arguments)))
