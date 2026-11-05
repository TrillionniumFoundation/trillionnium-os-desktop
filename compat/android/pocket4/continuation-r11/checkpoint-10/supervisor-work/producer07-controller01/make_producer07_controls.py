from pathlib import Path
import ast
import difflib
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parent
OLD = ROOT / 'controller-recovery04-freeze-01'
SOURCE = ROOT / 'producer07-audit-freeze-01'
OUT = ROOT / 'producer07-controller-work-01'
REVISION = 'producer07-audit01'
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-audit-r11-build-07-01'
NEW = 'runtime/droidloom-supervisor/src/relay_lifecycle/audit.rs'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(name, data):
    with (OUT / name).open('xb') as stream:
        stream.write(data)


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


os.umask(0o077)
OUT.mkdir(mode=0o700)
manifest_raw = (SOURCE / 'manifest.json').read_bytes()
assert sha(manifest_raw) == 'c91fcbb5318d01848d00eb533ddef8b4bed4ad53b59c95a54db0e12315bb672d'
manifest = json.loads(manifest_raw)
for row in manifest['files']:
    raw = (SOURCE / row['path']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
inputs = json.loads((SOURCE / 'input-manifest.json').read_bytes())
candidate = {r['path']: r for r in inputs['candidate_inputs']}
overlays = {p: {'text': (SOURCE / 'source' / p).read_text(),
                'bytes': candidate[p]['bytes'], 'sha256': candidate[p]['sha256']}
            for p in inputs['changed_inputs']}
preimage = {r['path']: {'bytes': r['bytes'], 'sha256': r['sha256']} for r in inputs['basis_inputs']}
assert len(preimage) == 31 and len(overlays) == 10 and set(overlays) - set(preimage) == {NEW}
overlay_constant = 'EXACT_OVERLAY = {\n' + ''.join(
    f'    {p!r}: ({row["bytes"]}, {row["sha256"]!r}),\n' for p, row in sorted(overlays.items())
) + '}\nNEW_SOURCE_FILES = {' + repr(NEW) + '}\n'

old_path_tail = '''    need(stat.S_ISREG((root / name).lstat().st_mode),
         "source input is not a real regular file")
    return root / name'''
new_path_tail = '''    destination = root / name
    if must_be_absent:
        need(name in NEW_SOURCE_FILES, "only the frozen new module may be created")
        try:
            destination.lstat()
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError("new source module already exists")
    else:
        need(stat.S_ISREG(destination.lstat().st_mode),
             "source input is not a real regular file")
    return destination'''
old_overlay = '''        for name, row in cfg["overlays"].items():
            destination = plain_input_path(CANDIDATE, name)
            original = read_regular(destination, SOURCE_LIMIT)
            pin = cfg["preimage"][name]
            need(len(original) == pin["bytes"] and sha(original) == pin["sha256"],
                 "copied overlay preimage changed")
            put(OUT / "preimage" / name, original)
            fd = os.open(destination, os.O_WRONLY | os.O_TRUNC |
                         os.O_NOFOLLOW | os.O_CLOEXEC)
            with os.fdopen(fd, "wb") as stream:
                stream.write(row["text"].encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())'''
new_overlay = '''        for name, row in cfg["overlays"].items():
            creating = name in NEW_SOURCE_FILES
            destination = plain_input_path(CANDIDATE, name, must_be_absent=creating)
            flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC
            if creating:
                need(name not in cfg["preimage"], "new source must have no preimage")
                flags |= os.O_CREAT | os.O_EXCL
            else:
                original = read_regular(destination, SOURCE_LIMIT)
                pin = cfg["preimage"][name]
                need(len(original) == pin["bytes"] and sha(original) == pin["sha256"],
                     "copied overlay preimage changed")
                put(OUT / "preimage" / name, original)
                flags |= os.O_TRUNC
            fd = os.open(destination, flags, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(row["text"].encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())'''

programs = {}
for name, expected in [('compile.py', '7e71dfb136e23eb9b623cb6467466e8d0c98ee410c9819e4f264af4851b31358'),
                       ('run.py', 'd45b2d238c77dd3778a2707475089416129b1f06ee16d0f33d2ff73bdfb02c2c')]:
    raw = (OLD / name).read_bytes()
    assert sha(raw) == expected
    old = raw.decode()
    text = old.replace('producer06-deadline-recovery04', REVISION)
    text = text.replace('/home/alex/work/pocket4-supervisor-lmkd-lifecycle-r11-work-01',
                        '/home/alex/work/pocket4-supervisor-lmkd-deadline-r11-build-06-recovery04')
    text = once(text,
        'OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-deadline-r11-build-06-recovery04")',
        f'OUT = Path("{REMOTE}")')
    text = once(text, 'PRIOR_RECEIPT = BASE / "integration-producer-build-05/build-result.json"',
                'PRIOR_RECEIPT = BASE / "compile-result.json"')
    text = text.replace('1623811c108a7cac8af3460d828c063ed9e7064519d2d4e41d70bce4ab25e64c',
                        '2eb658308593cf760b7f99bbc9e3d7762295ef18c4628b050221838ffa274d4f')
    text = text.replace('a603f4f2eeeb44ccf0063ddf44ee9be4986567b6befb9cc1799fd9f6664481a5',
                        '731fcdae3856011a418e244b19b0568160f9316e94b31ba3aa6e75e423cab5eb')
    text = text.replace('0d9bd3796dee86faa1963791314d9be26cf0c55beaba57529a572a3bbd648f3a',
                        '4f25a4311f9b1f981af60f5600c1f1c9be260d12f962714d3061850dea8bdef7')
    text = text.replace('ad66ab3800fecbfc75bf10a5dcefbd46fad1a7fb642ff205b2d26cd10a010bf3',
                        'c91fcbb5318d01848d00eb533ddef8b4bed4ad53b59c95a54db0e12315bb672d')
    begin = text.index('EXACT_OVERLAY = {')
    end = text.index('BINARIES = ', begin)
    text = text[:begin] + overlay_constant + text[end:]
    text = once(text, 'def plain_input_path(root, name):',
                'def plain_input_path(root, name, *, must_be_absent=False):')
    text = once(text, old_path_tail, new_path_tail)
    text = text.replace('exact 31 input pins differ', 'exact source input pins differ')
    text = once(text,
        '         set(cfg["overlays"]) == set(EXACT_OVERLAY), "wrong input/overlay set")',
        '         set(cfg["overlays"]) == set(EXACT_OVERLAY) and\n'
        '         set(cfg["overlays"]) - set(cfg["preimage"]) == NEW_SOURCE_FILES and\n'
        '         len(set(cfg["preimage"]) | set(cfg["overlays"])) == 32, "wrong input/overlay set")')
    text = text.replace('producer05-actual-build-result.json', 'producer06-recovery04-actual-compile-result.json')
    text = text.replace('actual producer05 receipt', 'actual producer06 recovery04 receipt')
    text = text.replace('producer05 lineage receipt', 'producer06 recovery04 lineage receipt')
    if name == 'compile.py':
        text = once(text,
            '        need(prior["success"] is True and prior["candidate"] == str(SOURCE) and\n',
            '        need(prior["success"] is True and prior["compile_only"] is True and\n'
            '             prior["revision"] == "producer06-deadline-recovery04" and\n'
            '             prior["candidate"] == str(SOURCE) and\n')
        text = once(text, old_overlay, new_overlay)
        text = text.replace('"31 inputs changed during compile"', '"32 inputs changed during compile"')
    else:
        text = once(text,
            'expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 112',
            'expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 119')
        text = once(text, 'rust_tests_passed={"droidloom-pressure-relay": 23, "droidloom-supervisor": 112},',
                    'rust_tests_passed={"droidloom-pressure-relay": 23, "droidloom-supervisor": 119},')
    ast.parse(text)
    programs[name] = text
    put(name, text.encode())
    put(name + '.diff', ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
        fromfile='producer06-recovery04/' + name, tofile=REVISION + '/' + name)).encode())

cfg = {'schema': 1, 'revision': REVISION, 'preimage': preimage, 'overlays': overlays,
       'original_diff_sha256': '4f25a4311f9b1f981af60f5600c1f1c9be260d12f962714d3061850dea8bdef7',
       'source_manifest_sha256': 'c91fcbb5318d01848d00eb533ddef8b4bed4ad53b59c95a54db0e12315bb672d'}
payload = json.dumps(cfg, indent=2, ensure_ascii=False) + '\n'
assert len(payload.encode()) < 512 * 1024 and "'''" not in payload
put('payload.json', payload.encode())
stdin = programs['compile.py'] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
ast.parse(stdin)
request = json.loads((OLD / 'compile-request.json').read_bytes())
request['stdin'] = stdin
request['idempotency_key'] = 'p4-producer07-audit01-compile01-' + sha(stdin.encode())[:16]
put('compile-request.json', (json.dumps(request, indent=2, ensure_ascii=False) + '\n').encode())
template = json.loads((OLD / 'ordinary-run-request-template.json').read_bytes())
assert template['execution_ready'] is False
template['request_template']['stdin'] = programs['run.py']
template['request_template']['idempotency_key'] = 'p4-producer07-audit01-ordinary01-REQUIRES_ACTUAL_SHA16'
template['requires'] = 'Complete external SHA-256 of successful actual producer07-audit01 compile-result.json and a root execution window. No old receipt substitution.'
template['scope'] = 'Two selected library ELFs (23 relay, original 112 plus 7 new supervisor controls = 119), two targeted public retirement controls, seven owned IPC controls, worker-context and entry ABI. No integration/bin-test suites, real Owner, Android, pressure, namespaces or network execution.'
put('ordinary-run-request-template.json', (json.dumps(template, indent=2, ensure_ascii=False) + '\n').encode())
put('resource_guard.py', (OLD / 'resource_guard.py').read_bytes())
summary = {'schema': 1, 'revision': REVISION, 'execution_status': 'NOT_SUBMITTED',
           'source_tree': '52dd841fcdf47f5053116491bd74da62cd8504cd',
           'source_manifest_sha256': cfg['source_manifest_sha256'],
           'prior_compile_receipt_sha256': '2eb658308593cf760b7f99bbc9e3d7762295ef18c4628b050221838ffa274d4f',
           'source_origin': '/home/alex/work/pocket4-supervisor-lmkd-deadline-r11-build-06-recovery04/candidate',
           'source_origin_inventory_sha256': '731fcdae3856011a418e244b19b0568160f9316e94b31ba3aa6e75e423cab5eb',
           'remote_output': REMOTE, 'changed_existing_inputs': 9, 'new_input': NEW,
           'candidate_input_count': 32, 'compile_stdin': {'bytes': len(stdin.encode()), 'sha256': sha(stdin.encode())},
           'compile_request': {'bytes': (OUT / 'compile-request.json').stat().st_size,
                               'sha256': sha((OUT / 'compile-request.json').read_bytes()), 'idempotency_key': request['idempotency_key']},
           'resource_guard_unchanged': True, 'selected_test_targets': [['droidloom_pressure_relay', 'lib'], ['droidloom_supervisor', 'lib']],
           'expected_library_tests': {'droidloom-pressure-relay': 23, 'droidloom-supervisor': 119},
           'targeted_retirement_expected_passed_filtered': [1, 22],
           'actual_owner_lifecycle_qualified': False, 'device_actions_performed': False}
put('generation-summary.json', (json.dumps(summary, indent=2, sort_keys=True) + '\n').encode())
print(json.dumps(summary, indent=2, sort_keys=True))
