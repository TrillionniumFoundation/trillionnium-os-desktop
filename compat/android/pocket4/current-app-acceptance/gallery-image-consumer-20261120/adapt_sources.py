#!/usr/bin/env python3
"""Reproduce new image consumers; never edit or unretire historical entries."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD_SHA = '6677d382076f10f0502c813c7614c32127ccf3cd8f02756b75a8c3574980e87e'
NEW_SHA = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
GROUPS = {
    'rotation': 'gallery-rotation-current-preparation-20261107-r7',
    'video': 'gallery-video-current-preparation-20261107-r7',
    'seek': 'gallery-seek-current-preparation-20261107-r6',
    'album': 'gallery-album-current-preparation-20261107-r6',
}


def original_directory(group):
    # Some historical groups were already committed in the prior adapter;
    # the video and seek groups were captured from their exact pinned host
    # sources and are retained separately in this change. Never silently
    # accept an absent group as an empty source set.
    for directory in (ROOT/'originals'/group, ROOT/'inputs/additional-originals'/group,
                      ROOT.parent/'system-cp3a-source-adapter-20261119/originals'/group):
        if directory.is_dir():
            return directory
    raise RuntimeError('PINNED_ORIGINAL_SOURCE_GROUP_MISSING:'+group)


def replace(text, old, new, count=1):
    assert text.count(old) == count, (old, text.count(old), count)
    return text.replace(old, new)


def remove_functions(text, names):
    rows = text.splitlines(keepends=True)
    found = {node.name: node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)}
    for name in sorted(names, key=lambda key: found[key].lineno, reverse=True):
        node = found[name]
        del rows[node.lineno-1:node.end_lineno]
    return ''.join(rows)


def source_function(text, name):
    node = next(node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])


def write(path, text):
    compile(text, str(path), 'exec')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def adapt_session(text, video=False):
    text = text.replace(OLD_SHA, NEW_SHA)
    text = replace(text, 'action_lock, install,', 'action_lock, image_capture,')
    text = replace(text, "self.action_lock = action_lock; self.install = install; self.install_ref = request['installation']",
                   'self.action_lock = action_lock; self.image_capture = image_capture; self.image_custody_ref = image_capture.reference')
    text = replace(text, "self.apk_paths = {GALLERY: install['gallery_after']['apk']['path']}",
                   'self.apk_paths = {}; self.gallery_uid = None; self.image_identity = None')
    text = text.replace("'installation': self.install_ref", "'image_custody': self.image_custody_ref")
    space = '                ' if video else '            '
    text = replace(text, 'self.baseline = self.view.baseline; self.environment = self.view.environment',
                   'self.observation = image_capture.bind(self.view)\n' + space +
                   "self.apk_paths[GALLERY] = self.observation['apks'][0]['path']; self.gallery_uid = self.observation['uid']\n" + space +
                   'self.baseline = self.view.baseline; self.environment = self.view.environment')
    if video:
        text = replace(text, 'current_deadline=lambda: self.deadline)',
                       'current_deadline=lambda: self.deadline, gallery_uid=self.gallery_uid)')
    else:
        text = replace(text, "expected = self.install['gallery_after']; protected = expected['protected']",
                       "self.image_capture.bind(self.view)\n        expected = self.image_identity; protected = expected['protected']")
        text = replace(text, "value['uid'] == protected['uid'] == 10064",
                       "value['uid'] == protected['uid'] == self.gallery_uid")
        text = replace(text, "expected['apk']['bytes'] == 7488378", "expected['apk']['bytes'] == 7390425")
        text = replace(text, '    def pm_no_replace_proof(self):',
                       '    def mapped_owner(self, uid, gid=None):\n        return self.image_capture.mapped_owner(self.view, uid, gid)\n\n    def pm_no_replace_proof(self):')
    text = text.replace('match_installed_identity', 'match_image_identity')
    assert "request['installation']" not in text and 'self.install' not in text
    return text


def adapt_case(text, video=False):
    if video:
        text = remove_functions(text, {'verify_current_movie_source'})
    else:
        text = remove_functions(text, {'verify_install', 'runtime_facade'})
        text = replace(text, "actual = originals['identity'].snapshot(session, session.support.APK_SHA)",
                       "session.image_capture.bind(session.view)\n    actual = originals['identity'].snapshot(session, session.observation)")
    text = replace(text, 'current_preparation,\n            current_modules, components,',
                   'image_capture,\n            components,')
    text = replace(text, "'installation': request['installation']", "'image_custody': image_capture.reference")
    old = ('        installation, code_closure = shared_case.verify_install(c, request, current_preparation, support, current_modules)\n'
           if video else '        installation, code_closure = verify_install(c, request, current_preparation, support, current_modules)\n')
    text = replace(text, old, '')
    if video:
        start = text.index("        host_inputs = originals['install'].host_evidence()")
        end = text.index('        lock = shared_session.ActionLock(c, root)', start)
        text = text[:start] + "        c.read_ref(TASK_PROOF)\n" + text[end:]
        text = replace(text, 'lock, installation, source_guard, prior_ref, business_deadline)',
                       'lock, image_capture, source_guard, prior_ref, business_deadline)')
        old = """        need(result['main_before'] == installation['main_after'], 'EXACT_ART_AND_ONCE_INSTALL_QUALIFIED_MAIN')
        result['runtime_before'] = c.write_new(Path(root) / 'runtime-before.json',
            current_modules['closure'].recheck_runtime_code(shared_case.runtime_facade(session), code_closure))
        result['identity_before'] = shared_case.identity_matches(c, originals, session, installation['gallery_after'])"""
        new = """        image_capture.bind(session.view)
        result['identity_before'] = originals['identity'].snapshot(session, session.observation)
        session.image_identity = result['identity_before']
        components['video_runtime.py'].bind_current_uid(session)
        result['static_movie_code_scope'] = {
            'original_complete_image_APK_sha256': support.APK_SHA,
            'modified_methods': [], 'task_option_source': TASK_PROOF,
            'source_only': True, 'runtime_credit': 0,
            'historical_runtime_authority_transferred': False}"""
        text = replace(text, old, new)
        text = replace(text, "shared_case.identity_matches(c, originals, session, installation['gallery_after'])",
                       "shared_case.identity_matches(c, originals, session, session.image_identity)")
        text = replace(text, """                result['runtime_after'] = c.write_new(Path(root) / 'runtime-after.json',
                    current_modules['closure'].recheck_runtime_code(shared_case.runtime_facade(session), code_closure))""",
                       "                image_capture.bind(session.view)")
        text = replace(text, "                need(originals['install'].host_evidence() == host_inputs, 'CURRENT_GALLERY_HOST_PROVENANCE_CHANGED')\n", '')
        text = text.replace('10064', 'session.gallery_uid')
    else:
        text = replace(text, 'lock, installation, source_guard, prior_ref, business_deadline)',
                       'lock, image_capture, source_guard, prior_ref, business_deadline)')
        old = """        need(result['main_before'] == installation['main_after'], 'EXACT_ART_AND_INSTALL_QUALIFIED_MAIN_REQUIRED')
        result['runtime_before'] = c.write_new(root / 'runtime-before.json',
            current_modules['closure'].recheck_runtime_code(runtime_facade(session), code_closure))
        result['identity_before'] = identity_matches(c, originals, session, installation['gallery_after'])"""
        new = """        image_capture.bind(session.view)
        result['identity_before'] = originals['identity'].snapshot(session, session.observation)
        session.image_identity = result['identity_before']
        components['bounded_diagnostics.py'].bind_current_uid(session)"""
        text = replace(text, old, new)
        text = replace(text, "identity_matches(c, originals, session, installation['gallery_after'])",
                       'identity_matches(c, originals, session, session.image_identity)')
        text = replace(text, """                result['runtime_after'] = c.write_new(root / 'runtime-after.json',
                    current_modules['closure'].recheck_runtime_code(runtime_facade(session), code_closure))""",
                       '                image_capture.bind(session.view)')
    text = text.replace('verified new installation', 'fresh original system-image observation')
    assert "request['installation']" not in text and 'current_modules' not in text
    assert 'code_closure' not in text and 'installation[' not in text
    return text


def bind_uid(text):
    return replace(text, "TARGETS={'com.android.gallery3d':10064}", """TARGETS = None

def bind_current_uid(session):
    global TARGETS
    observed = session.image_capture.bind(session.view)
    need(type(observed['uid']) is int and observed['uid'] == session.gallery_uid,
         'ACTUAL_CURRENT_IMAGE_UID_REQUIRED')
    TARGETS = {'com.android.gallery3d': observed['uid']}
""")


def adapt_identity():
    text = (ROOT/'dependencies/gallery_identity_qpr1.py').read_text()
    assert hashlib.sha256(text.encode()).hexdigest() == '77a4468baa0adfe88fbd0d9b2e74a66137e4f7a59f10e1de5d5a2549a9b0e3ee'
    ns = {}; exec(compile(text, 'identity-original', 'exec'), ns)
    names = sorted(row.split(':', 1)[0] for row in ns['EXPECTED']['all_permission_rows'])
    header = '''"""Current-image Gallery metadata conservation, without historic data credit."""
import hashlib, io, os, re, stat, struct, zipfile
from pathlib import Path
PACKAGE = 'com.android.gallery3d'
APK_SHA = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
APK_BYTES = 7390425
APK_PATHS = ('/system/product/app/Gallery2/Gallery2.apk', '/product/app/Gallery2/Gallery2.apk')
MANIFEST_SHA = '2d4399372058787b9a9986a797ddc8f2d3722e4cee85a055721da4dc546890ee'
'''
    result = header + 'PERMISSION_NAMES = ' + repr(names) + '\n\n'
    for name in ('need', 'sha', 'fp', 'active_block', 'parse_package', 'native_payload', 'snapshot'):
        result += source_function(text, name) + '\n\n'
    result = replace(result, 'def parse_package(raw):', 'def parse_package(raw, expected_uid):')
    result = replace(result, "uid==10064 and version==('40030','37','28')",
                     "type(expected_uid) is int and 0 < expected_uid < 100000 and uid==expected_uid and version==('40030','37','28')")
    result = replace(result, "need(state==EXPECTED['user0_state'],'GALLERY_USER0_STATE_CHANGED')",
                     "user_state=dict(item.split('=',1) for item in tokens)\n    need(user_state.get('installed')=='true' and user_state.get('hidden')=='false'\n         and user_state.get('suspended')=='false' and user_state.get('enabled')=='0',\n         'CURRENT_GALLERY_MUST_BE_INSTALLED_AND_ENABLED')")
    result = replace(result, "{r.split(':',1)[0] for r in EXPECTED['all_permission_rows']}", 'set(PERMISSION_NAMES)')
    result = replace(result, 'def snapshot(session,expected_sha):\n    need(expected_sha in (OLD_SHA,NEW_SHA),\'UNREVIEWED_GALLERY_TARGET_HASH\')',
                     "def snapshot(session,observation):\n    need(observation==session.image_capture.bind(session.view), 'CURRENT_CAPTURE_OBSERVATION_REQUIRED')\n    expected_uid=observation['uid']")
    result = replace(result, 'parsed=parse_package(dump)', 'parsed=parse_package(dump,expected_uid)')
    result = replace(result, """    if expected_sha==OLD_SHA:need(path==OLD_PATH,'ORIGINAL_PRODUCT_GALLERY_REQUIRED')
    else:need(re.fullmatch(r'/data/app/~~[^/]+/com\\.android\\.gallery3d-[^/]+/base\\.apk',path)
              is not None,'UPDATED_GALLERY_PATH_REQUIRED')""",
                     "    need(path in APK_PATHS and path==observation['apks'][0]['path'], 'CURRENT_ORIGINAL_SYSTEM_GALLERY_PATH_REQUIRED')")
    result = replace(result, "observed['sha256']==expected_sha and len(apk)==(OLD_BYTES if expected_sha==OLD_SHA else NEW_BYTES)",
                     "observed['sha256']==APK_SHA and len(apk)==APK_BYTES")
    result = replace(result, 'info.st_uid==info.st_gid==10064',
                     '(info.st_uid,info.st_gid)==session.mapped_owner(expected_uid)')
    result = result.replace('# Actual cached original and candidate contain no embedded native namespace.',
                            '# The exact official image member contains no embedded native namespace.')
    write(ROOT/'generated/shared/gallery_image_identity.py', result)


def main():
    export = json.loads((ROOT/'inputs/source-origin-pins.json').read_bytes())
    for role, group in GROUPS.items():
        directory = original_directory(group)
        expected = {Path(name).name for name in export['files'] if name.startswith(group+'/')}
        assert {path.name for path in directory.glob('*.py')} == expected, group
        for source in sorted(directory.glob('*.py')):
            record = export['files'][group+'/'+source.name]
            raw = source.read_bytes()
            assert len(raw) == record['bytes'] and hashlib.sha256(raw).hexdigest() == record['sha256']
            if source.name.endswith('_entry.py'):
                # Retired reviewed entry points are never edited or imported.
                continue
            text = raw.decode().replace(OLD_SHA, NEW_SHA)
            if source.name in ('gallery_rotation_session.py', 'video_session.py'):
                text = adapt_session(text, role != 'rotation')
            elif source.name in ('gallery_rotation_case.py', 'video_case.py'):
                text = adapt_case(text, role != 'rotation')
            elif source.name in ('gallery_rotation_policy.py', 'video_policy.py'):
                text = replace(text, "'--uid=10064'", "'--uid=' + str(s.gallery_uid)")
            elif source.name == 'gallery_rotation_flow.py':
                text = replace(text, 'GALLERY_SHA,10064,40030', 'GALLERY_SHA,self.s.gallery_uid,40030')
                text = replace(text, "self.result['current_verified_installation']=self.s.install_ref",
                               "self.result['current_verified_image_custody']=self.s.image_custody_ref")
            elif source.name in ('video_base.py', 'video_flow.py'):
                text = text.replace('10064', 'self.s.gallery_uid')
            elif source.name in ('bounded_diagnostics.py', 'video_runtime.py'):
                text = bind_uid(text)
                if source.name == 'bounded_diagnostics.py':
                    text = replace(text, "if re.search(r'android\\.permission\\.[A-Za-z0-9_]+: granted=',line))",
                                   "if ': granted=' in line)")
                    text = replace(text, "need(lines,'PERMISSION_ROWS_EMPTY_OR_UNPARSED')",
                                   "need(len(lines)==29 and len({row.split(':',1)[0] for row in lines})==29\n            and all(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]+: granted=(true|false)(?:, flags=\\[[A-Z_ |]*\\])?',row) for row in lines),\n            'ALL_29_ACTUAL_PERMISSION_ROWS_REQUIRED')")
                    text = replace(text, "result[package]={'permission_rows':lines,'rows_sha256':sha('\\n'.join(lines).encode())}",
                                   "android_rows=[row for row in lines if row.startswith('android.permission.')]\n        need(len(android_rows)==27,'ORIGINAL_27_ANDROID_PERMISSION_DIAGNOSTICS_REQUIRED')\n        result[package]={'permission_rows':lines,'rows_sha256':sha('\\n'.join(lines).encode()),\n            'android_permission_rows':android_rows,'android_rows_sha256':sha('\\n'.join(android_rows).encode())}")
            elif source.name == 'owned_media.py':
                # This is the independently reviewed current CP3A MediaProvider
                # postimage, not a recreated hardcoded provider identity.
                text = (ROOT/'reviewed/owned_media.py').read_text()
            if source.name in ('rotation_package.py', 'video_identity.py', 'video_fixture.py'):
                text = replace(text, 'info.st_uid==info.st_gid==uid',
                               '(info.st_uid,info.st_gid)==session.mapped_owner(uid)')
            text = text.replace('match_installed_identity', 'match_image_identity')
            assert OLD_SHA not in text and '10064' not in text, source
            write(ROOT/'generated'/role/source.name, text)
    adapt_identity()
    old_support = (original_directory('gallery-new-runtime-preparation-20261107-r7')/'gallery_runtime_support_current.py').read_text()
    support = '''"""Original process resource limits; no Gallery install or ART replacement API."""
import os, resource
from pathlib import Path
PACKAGE = 'com.android.gallery3d'
APK_SHA = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
APK_BYTES = 7390425
def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)
'''
    support += '\n' + source_function(old_support, 'resources').replace('def resources():', 'def _local_resources():', 1) + '\n'
    support += '\n' + (ROOT/'templates/held_resource_binding.py').read_text()
    write(ROOT/'generated/shared/gallery_image_support.py', support)
    print(json.dumps({'source_only': True, 'runtime_qualified': False,
                      'generated_files': len(list((ROOT/'generated').rglob('*.py')))}))


if __name__ == '__main__':
    main()
