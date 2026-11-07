#!/usr/bin/python3 -I
"""Read exact Contacts search code; no Contacts launch, provider, account or UI action."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, gzip, hashlib, io, json, os, re, struct, types, zipfile, zlib

OUT = Path('/home/alex/work/pocket4-contacts-search-source-20261105-r12-02')
TX = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
TOOLS = Path('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01')
INSPECT_SHA = '4fe7333255ccbcd6df22a4c89d40c669603f7817eae3d0071c7e5f930a6b424f'
PINS_SHA = '20b2752edb6c820577c3467bd38b8386f88825fc18ae66f3394302ae3a630b24'
DECODER = Path('/home/alex/work/pocket4-system-component-tools-20261105-r12-01/decode_manifest.py')
DECODER_SHA = '2483008850e6e6d2de61612e3e87833e9d4fc40251d9d43ce75a98fbd2445dd2'
APK = '/product/priv-app/Contacts/Contacts.apk'
APK_SHA = '11f8be5fd46dd79ee4f7524d5d1334e21ce0f9e23892b2940a5b6091e2f349d0'
DEX_SHA = 'bf85e172e2286e2dd99c0ea36c0cdc43a7163d2e5f3414e4bd7d6dcbf9e0afed'
MANIFEST_SHA = 'b292bac6e86996c0d0f3a7ff1ed8a3af101f8aca8b0c85b84c363cd825bd226c'
PACKAGE = 'com.android.contacts'
EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
ANDROID = '{http://schemas.android.com/apk/res/android}'
TARGETS = ('com.android.contacts.activities.PeopleActivity',)
EXACT_FAMILIES = (
    'Lcom/android/contacts/activities/PeopleActivity',
    'Lcom/android/contacts/activities/ActionBarAdapter',
    'Lcom/android/contacts/list/DefaultContactBrowseListFragment',
    'Lcom/android/contacts/list/ContactBrowseListFragment',
    'Lcom/android/contacts/list/ContactEntryListFragment',
    'Lcom/android/contacts/list/ContactListAdapter',
    'Lcom/android/contacts/list/DefaultContactListAdapter',
    'Lcom/android/contacts/R$string',
    'Lcom/android/contacts/R$id')


def need(ok, reason):
    if not ok: raise RuntimeError(reason)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def load(path, pin):
    raw = path.read_bytes()
    need(sha(raw) == pin, 'PIN_CHANGED:' + path.name)
    module = types.ModuleType('contacts_search_source_' + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def classes(raw):
    need(len(raw) >= 112 and re.fullmatch(rb'dex\n0[34][0-9]\x00', raw[:8]), 'DEX_MAGIC')
    def u32(off):
        need(0 <= off <= len(raw) - 4, 'DEX_U32_BOUND')
        return struct.unpack_from('<I', raw, off)[0]
    need(u32(32) == len(raw) and u32(36) == 112 and u32(40) == 0x12345678, 'DEX_HEADER')
    need(u32(8) == zlib.adler32(raw[12:]) & 0xffffffff
         and raw[12:32] == hashlib.sha1(raw[32:]).digest(), 'DEX_CHECKSUM')
    sc, so, tc, to, cc, co = (u32(x) for x in (56, 60, 64, 68, 96, 100))
    need(so + 4 * sc <= len(raw) and to + 4 * tc <= len(raw)
         and co + 32 * cc <= len(raw), 'DEX_TABLE_BOUNDS')
    names = []
    for off in range(co, co + cc * 32, 32):
        typ = u32(off); need(typ < tc, 'DEX_TYPE_INDEX')
        idx = u32(to + typ * 4); need(idx < sc, 'DEX_STRING_INDEX')
        pos = u32(so + idx * 4)
        for _ in range(5):
            need(pos < len(raw), 'DEX_ULEB_BOUND'); value = raw[pos]; pos += 1
            if value < 128: break
        else: raise RuntimeError('DEX_ULEB_OVERFLOW')
        end = raw.find(b'\0', pos, min(len(raw), pos + 4096))
        need(end >= pos, 'DEX_DESCRIPTOR_TERMINATION')
        name = raw[pos:end].decode('ascii')
        need(re.fullmatch(r'L[^;\s]+;', name), 'DEX_DESCRIPTOR')
        names.append(name)
    need(len(names) == len(set(names)), 'DUPLICATE_CLASS')
    return names


def select(names):
    chosen = sorted(name for name in names if
        any(name == prefix + ';' or name.startswith(prefix + '$') for prefix in EXACT_FAMILIES))
    need('Lcom/android/contacts/activities/PeopleActivity;' in chosen, 'PEOPLE_ACTIVITY_REQUIRED')
    need(1 <= len(chosen) <= 96, 'SELECTED_CLASS_BOUND')
    return chosen

def manifest_projection(data, decoder):
    need(len(data) == 42360 and sha(data) == MANIFEST_SHA, 'MANIFEST_CHANGED')
    elements = decoder.decode(data)
    roots = [e for e in elements if e['path'] == 'manifest']
    apps = [e for e in elements if e['path'] == 'manifest/application']
    need(len(elements) == 316 and len(roots) == len(apps) == 1
         and roots[0]['attributes'].get('package') == PACKAGE, 'MANIFEST_IDENTITY_CHANGED')
    selected = [e for e in elements if e['attributes'].get(ANDROID + 'name') in TARGETS
                or e['path'] in ('manifest/instrumentation', 'manifest/application/uses-library',
                                  'manifest/application/uses-static-library', 'manifest/uses-split')]
    declared = {e['attributes'].get(ANDROID + 'name') for e in selected}
    need(all(target in declared for target in TARGETS), 'EXPECTED_DECLARATION_MISSING')
    return {'sha256': sha(data), 'bytes': len(data), 'application': apps[0],
            'root': roots[0], 'selected_declarations': selected,
            'resource_boolean_values_resolved': False}


def literal_counts(data):
    return {target: {'dotted_utf8': data.count(target.encode()),
                     'slash_utf8': data.count(target.replace('.', '/').encode()),
                     'dotted_utf16le': data.count(target.encode('utf-16-le'))}
            for target in TARGETS}


def capture():
    need(os.geteuid() == 0 and not os.path.lexists(OUT), 'NEW_ROOT_REQUIRED')
    tx = load(TX, TX_SHA)
    need(tx.ACTIVATION_SHA == ACTIVATION_SHA, 'RESOURCE_PROFILE_CHANGED')
    inspector = load(TOOLS / 'inspect_clock_dex01.py', INSPECT_SHA)
    decoder = load(DECODER, DECODER_SHA)
    raw_pins = (TOOLS / 'baksmali-pins.json').read_bytes()
    need(sha(raw_pins) == PINS_SHA, 'TOOL_MANIFEST_CHANGED')
    pins = json.loads(raw_pins)
    for group in ('jre', 'jars'):
        for entry in pins[group].values(): inspector.check_tool(entry)
    os.umask(0o077); OUT.mkdir(mode=0o750); os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
    os.sched_setaffinity(0, {20})
    result = {'schema': 'pocket4-contacts-search-source-v1', 'state': 'FAILED',
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'planned_read_only_PM_queries': 2, 'UI_actions': 0, 'telephony_actions': 0,
              'SIM_or_account_writes': 0, 'package_changes': 0, 'APK_code_executed': False,
              'functional_or_runtime_gate_granted': False, 'sources': {},
              'tool_pins_sha256': PINS_SHA, 'transport_sha256': TX_SHA,
              'activation_sha256': ACTIVATION_SHA}
    try:
        with tx.CameraSession(OUT / 'commands') as session:
            result['guard_before'] = session.guard()
            need(session.epoch_sha256 == EPOCH, 'MAIN_CHANGED')
            lines = session.android(['/system/bin/pm', 'path', '--user', '0', PACKAGE]).decode().splitlines()
            need(lines == ['package:' + APK], 'ACTIVE_APK_CHANGED')
            listed = session.android(['/system/bin/pm', 'list', 'packages', '-U', '--user', '0', PACKAGE]).decode().splitlines()
            need(len(listed) == 2 and set(listed) == {'package:com.android.contactspicker uid:10019', 'package:' + PACKAGE + ' uid:10055'}, 'EXACT_PM_FILTER_UID_SET_CHANGED')
            apk, before = session.target.read_file(APK, 16 * 1024 * 1024, single_link=True)
            need(len(apk) == 11839391 and sha(apk) == APK_SHA, 'INSTALLED_APK_CHANGED')
            result['APK'] = {'path': APK, 'sha256': sha(apk), 'bytes': len(apk), 'metadata': before}
            cp = ':'.join(pins['jars'][name]['canonical'] for name in sorted(pins['jars']))
            command = [pins['jre']['bin/java']['canonical'], '-Xmx192m', '-cp', cp, 'org.jf.baksmali.Main']
            help_result = session.run_host('contacts-search-baksmali-help', command + ['disassemble', '--help'], 15)
            need(help_result['rc'] == 0 and help_result['joined'] and not help_result['timed_out']
                 and b'--classes' in help_result['stdout'] + help_result['stderr'], 'BAKSMALI_FILTER_UNVERIFIED')
            with zipfile.ZipFile(io.BytesIO(apk)) as archive:
                members = archive.namelist()
                need(len(members) == len(set(members)) and archive.testzip() is None, 'APK_ZIP_INTEGRITY')
                dex_names = sorted(n for n in members if re.fullmatch(r'classes(?:[2-9][0-9]*)?\.dex', n))
                need(dex_names == ['classes.dex'], 'DEX_SET_CHANGED')
                need(archive.getinfo('classes.dex').file_size == 4493268, 'DEX_SIZE_CHANGED')
                dex = archive.read('classes.dex')
                need(sha(dex) == DEX_SHA, 'DEX_CHANGED')
                names = classes(dex)
                need(len(names) == 4706, 'DEX_CLASS_COUNT_CHANGED')
                related = sorted(n for n in names if n.startswith(('Lcom/android/contacts/list/',
                    'Lcom/android/contacts/activities/')))
                need(len(related) <= 512, 'RELATED_DESCRIPTOR_BOUND')
                result['DEX'] = {'name': 'classes.dex', 'sha256': sha(dex), 'bytes': len(dex),
                    'class_count': len(names), 'related_defined_descriptors': related,
                    'target_defined': {n: 'L' + n.replace('.', '/') + ';' in names for n in TARGETS},
                    'target_literal_counts': literal_counts(dex),
                    'literal_counts_are_not_reachability_or_reflection_absence_proof': True}
                result['manifest'] = manifest_projection(archive.read('AndroidManifest.xml'), decoder)
                chosen = select(names); result['DEX']['selected'] = chosen
                dex_path = OUT / 'classes.dex'; tx.write_new(dex_path, dex)
                destination = OUT / 'selected-smali'
                run = session.run_host('contacts-search-selected-classes', command + ['disassemble', '--jobs', '1',
                    '--classes', ','.join(chosen), '--output', str(destination), str(dex_path)], 90)
                need(run['rc'] == 0 and run['joined'] and not run['timed_out'], 'DISASSEMBLY_FAILED')
                source_bytes = 0
                for descriptor in chosen:
                    code = (destination / (descriptor[1:-1] + '.smali')).read_bytes()
                    source_bytes += len(code)
                    need(len(code) <= 512 * 1024 and source_bytes <= 2 * 1024 * 1024, 'SOURCE_SIZE_BOUND')
                    result['sources'][descriptor] = {'sha256': sha(code), 'bytes': len(code), 'smali': code.decode()}
                hits = []
                xml_names = sorted(n for n in members if n.startswith('res/xml') and n.endswith('.xml'))
                need(len(xml_names) <= 128, 'XML_MEMBER_BOUND')
                total = 0
                for name in xml_names:
                    info = archive.getinfo(name); total += info.file_size
                    need(info.file_size <= 256 * 1024 and total <= 2 * 1024 * 1024, 'XML_SIZE_BOUND')
                    data = archive.read(name); counts = literal_counts(data)
                    if any(any(v.values()) for v in counts.values()):
                        hits.append({'member': name, 'sha256': sha(data), 'bytes': len(data), 'target_literal_counts': counts})
                result['compiled_XML_literal_hits'] = hits
                result['compiled_XML_members_scanned'] = len(xml_names)
            again, after = session.target.read_file(APK, 16 * 1024 * 1024, single_link=True)
            need(sha(again) == APK_SHA and before == after, 'APK_CHANGED_DURING_CAPTURE')
            result['guard_after'] = session.guard()
            need(result['guard_before'] == result['guard_after'], 'MAIN_CHANGED_AFTER')
            session.caller_status('contacts-search-source-final')
            result['state'] = 'EXACT_CONTACTS_SEARCH_SOURCE_CAPTURED'
    except BaseException as error:
        result['error'] = type(error).__name__ + ':' + str(error)
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    encoded = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    packed = gzip.compress(encoded, mtime=0)
    need(len(encoded) <= 3 * 1024 * 1024 and len(packed) <= 512 * 1024, 'EXPORT_SIZE_BOUND')
    tx.write_new(OUT / 'result.json', encoded, alex_readable=True)
    tx.write_new(OUT / 'result.json.gz', packed, alex_readable=True)
    print(json.dumps({'state': result['state'], 'error': result.get('error'), 'UI_actions': 0,
        'gzip_path': str(OUT / 'result.json.gz'), 'gzip_bytes': len(packed), 'gzip_sha256': sha(packed),
        'result_bytes': len(encoded), 'result_sha256': sha(encoded), 'selected_classes': len(result['sources'])}))
    return 0 if result['state'] == 'EXACT_CONTACTS_SEARCH_SOURCE_CAPTURED' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true')
    args = parser.parse_args()
    if not args.capture:
        print(json.dumps({'state': 'INERT', 'UI_actions': 0, 'package_changes': 0}))
    else:
        raise SystemExit(capture())
