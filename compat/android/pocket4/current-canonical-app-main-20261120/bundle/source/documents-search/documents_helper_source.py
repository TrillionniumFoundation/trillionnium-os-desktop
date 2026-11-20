"""Pure rendering of the original Documents helper for an explicit new name.

The caller supplies a FeaturesNames value and exact reviewed template bytes.
No APK is built or installed, no path is created, and no Main/task authority
is inferred. The future trusted entry must separately bind actual Main/plan,
create-only absence, producer dependencies, signature, APK and installed UID.
"""
import hashlib
import json

OLD_RUN = 'eeff7aa90e47139a'
OLD_LABEL = 'Pocket4 Owned Documents eeff7aa9'
ORIGIN_ROOT='/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/templates/documents-search/'
TEMPLATES = {
    'AndroidManifest.xml': (721, '9173e63c6bf8699792e461fc6e4656c0dbc91279c51d746816df4bff1d8813b7', 'AndroidManifest.xml'),
    'FeaturesActivity.java': (19190, '24a2fad6ce1ecb023f34279a0b34ac4a5d21f71e4854f9ce60ab9b1bfc006f0b',
                             'src/org/droidloom/qa/documents/r12/neeff7aa90e47139a/FeaturesActivity.java'),
    'ids.xml': (451, '2cb07cba41fa376ebc3d8f72f7e9491a8dc88ae87672d75ab1fcba1f0fb82083', 'res/values/ids.xml'),
    'contract.json': (2659, '7635b98d1296fbcb9ceee29619a5e3db5633be04776dfffa88fee4fe256b4637', 'contract.json'),
}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def render(names, templates):
    names.require_kind('features10')
    need(type(templates) is dict and set(templates) == set(TEMPLATES), 'EXACT_REVIEWED_HELPER_TEMPLATES_REQUIRED')
    origins = []
    for name, (size, digest, original) in TEMPLATES.items():
        raw = templates[name]
        need(type(raw) is bytes and len(raw) == size and sha(raw) == digest, 'ORIGINAL_HELPER_TEMPLATE_CHANGED:' + name)
        origins.append({'path': ORIGIN_ROOT + original, 'bytes': size, 'sha256': digest})
    old_java = templates['FeaturesActivity.java']
    old_manifest = templates['AndroidManifest.xml']
    old = OLD_RUN.encode('ascii'); new = names.RUN.encode('ascii')
    need(new not in old_java and new not in old_manifest and names.APP_LABEL.encode() not in old_manifest,
         'NEW_LITERAL_MUST_NOT_ALIAS_ORIGINAL_TEMPLATE_CONTENT')
    need(old_java.count(old) == 2 and old_manifest.count(old) == 1
         and old_manifest.count(OLD_LABEL.encode()) == 1, 'EXACT_ORIGINAL_PACKAGE_RUN_AND_LABEL_BINDINGS')
    java = old_java.replace(old, new)
    manifest = old_manifest.replace(old, new).replace(OLD_LABEL.encode(), names.APP_LABEL.encode())
    need(java.replace(new, old) == old_java
         and manifest.replace(names.APP_LABEL.encode(), OLD_LABEL.encode()).replace(new, old) == old_manifest,
         'ONLY_DECLARED_NAME_LITERAL_SUBSTITUTIONS_ALLOWED')
    old_contract = json.loads(templates['contract.json'])
    need(old_contract['permissions'] == [] and old_contract['network'] is False
         and old_contract['launcher'] is False and old_contract['lease_ms'] == 1200000
         and old_contract['fixture_provider_delete_calls'] == 0, 'ORIGINAL_HELPER_SCOPE_CHANGED')
    contract = dict(old_contract)
    contract.update(package=names.PACKAGE, run_id=names.RUN,
                    activity=names.PACKAGE + '/.FeaturesActivity', root=names.FOLDER,
                    source_directory=names.SOURCE, ui_created_directory=names.COPIES,
                    files={name: {'bytes': size, 'sha256': digest} for name, (size, digest) in names.PAYLOAD.items()},
                    qualification='SOURCE_RENDERED_ONLY_UNBUILT_UNINSTALLED_NO_MAIN_AUTHORITY',
                    historical_contract_qualification=old_contract['qualification'],
                    original_contract=origins[-1], original_business_semantics_preserved=True,
                    original_flow_deferred_supported_features=['search', 'sort'],
                    current_main_bound=False, APK_built=False, installed=False, Android_UI_actions=0,
                    whole_app_business_accepted=False)
    files = {'AndroidManifest.xml': manifest,
             'src/' + names.PACKAGE.replace('.', '/') + '/FeaturesActivity.java': java,
             'res/values/ids.xml': templates['ids.xml'], 'contract.json': encoded(contract)}
    source_manifest = {'schema': 'pocket4-documents-fresh-name-helper-source-v1',
        'package': names.PACKAGE, 'run_id': names.RUN,
        'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())},
        'original_templates': origins, 'original_java_preserved_except_package_and_RUN': True,
        'original_manifest_preserved_except_package_and_label': True,
        'original_payload_expressions_and_lengths_preserved': True,
        'permissions': [], 'launcher': False, 'network': False,
        'runtime_authority_created': False, 'built': False, 'installed': False,
        'Main_actions': 0, 'Android_UI_actions': 0,
        'build_and_install_factory_complete': False, 'whole_app_business_accepted': False}
    files['SOURCE_PINS.json'] = encoded(source_manifest)
    return files, source_manifest
