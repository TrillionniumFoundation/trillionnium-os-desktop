"""Create fixed IHG APK source and a separate actual-Main runtime contract.

render_prebuilt() supplies fixed Java and manifest bytes to the normal release
producer. create() separately guards the actual BusinessBaseline and renders
the Python comparison contract for that Main. The helper receives those four
values only through the admitted runtime binding; scope and nonce checks stay.
"""
import hashlib
import json
import os
from pathlib import Path
import re

SELF = 'org.droidloom.qa.ihg.finalmain.r1'
PROTOCOL = 'pocket4-owned-ihg-qa-final-main-v2'
OLD_SELF = 'org.droidloom.qa.ihg.r4'
OLD_PROTOCOL = 'pocket4-owned-ihg-qa-v4'
SCHEMA = 'droidloom.native-leaf-business-baseline.v1'
OLD = {'MAIN_EPOCH': '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c',
       'MAIN_BASELINE_SCHEMA': 'pocket4-main-current-baseline-v2',
       'MAIN_BASELINE_SHA': '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364',
       'MAIN_BASELINE_QUALIFICATION_SHA': 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'}
ORIGINAL_ROOT='/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/templates/ihg'
ORIGINALS = {
    'qa_contract.py': (28757, '5d83ba26324fd180abfd9069538a077a90a661d94c7a3d123694197b39430405'),
    'ActionRunner.java': (42244, '8b94f47113e435c013715ac8b3d623755e88d140fdae8c71cefa95240aff5117'),
    'AndroidManifest.xml': (713, 'f351faacc98ae4428f2f42f0c4dfbcf2ce72cfd8b14cf430565ce204c6de3246')}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def actual_values(baseline):
    need(baseline.value['schema'] == SCHEMA, 'ACTUAL_DISTINCT_FINAL_BASELINE_REQUIRED')
    return {'MAIN_EPOCH': baseline.value['framework_epoch']['sha256'],
        'MAIN_BASELINE_SCHEMA': baseline.value['schema'],
        'MAIN_BASELINE_SHA': baseline.baseline_ref['sha256'],
        'MAIN_BASELINE_QUALIFICATION_SHA': baseline.qualification_ref['sha256']}


# Every declared edit is exactly reversible to the pinned original helper.
JAVA_EDITS = (
    ("    static final String MAIN_EPOCH = \"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\";\n    static final String MAIN_BASELINE_SCHEMA = \"pocket4-main-current-baseline-v2\";\n    static final String MAIN_BASELINE_SHA = \"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\";\n    static final String MAIN_BASELINE_QUALIFICATION_SHA = \"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\";", "    /** The host's actual opaque Main is the authority. This only parses its\n     * four comparison values; an instrumentation argument grants no authority.\n     */\n    static final class MainBinding {\n        final String epoch, schema, baseline, qualification, sha256;\n        private MainBinding(JSONObject value, byte[] raw) throws Exception {\n            keys(value, \"main_epoch_sha256\", \"main_baseline_schema\",\n                 \"main_baseline_sha256\", \"main_baseline_qualification_sha256\");\n            epoch = string(value, \"main_epoch_sha256\", 64);\n            schema = string(value, \"main_baseline_schema\", 64);\n            baseline = string(value, \"main_baseline_sha256\", 64);\n            qualification = string(value, \"main_baseline_qualification_sha256\", 64);\n            need(\"droidloom.native-leaf-business-baseline.v1\".equals(schema)\n                 && epoch.matches(\"[0-9a-f]{64}\") && baseline.matches(\"[0-9a-f]{64}\")\n                 && qualification.matches(\"[0-9a-f]{64}\"), \"EXACT_CURRENT_MAIN_BINDING_REQUIRED\");\n            sha256 = hash(raw);\n        }\n        static MainBinding parse(String encoded) throws Exception {\n            need(encoded != null && encoded.length() <= 4 * ((512 + 2) / 3),\n                 \"MAIN_BINDING_BASE64_BOUND\");\n            byte[] raw = Base64.decode(encoded, Base64.NO_WRAP);\n            need(raw.length > 0 && raw.length <= 512\n                 && Base64.encodeToString(raw, Base64.NO_WRAP).equals(encoded),\n                 \"CANONICAL_MAIN_BINDING_BASE64_REQUIRED\");\n            JSONObject value = new JSONObject(new String(raw, StandardCharsets.UTF_8));\n            need(Arrays.equals(canonical(value).getBytes(StandardCharsets.UTF_8), raw),\n                 \"CANONICAL_MAIN_BINDING_JSON_REQUIRED\");\n            return new MainBinding(value, raw);\n        }\n    }\n    private MainBinding mainBinding;"),
    ("            need(arguments != null && arguments.keySet().equals(Collections.singleton(\"request\")), \"ONLY_REQUEST_ARGUMENT_ALLOWED\");", "            need(arguments != null && arguments.keySet().equals(new HashSet<String>(Arrays.asList(\"request\", \"main_binding\"))), \"EXACT_REQUEST_AND_MAIN_BINDING_ARGUMENTS_REQUIRED\");\n            mainBinding = MainBinding.parse(arguments.getString(\"main_binding\"));"),
    ("                .put(\"wire_codec\", \"gzip-canonical-json-v1\");", "                .put(\"wire_codec\", \"gzip-canonical-json-v1\").put(\"main_binding_sha256\", mainBinding.sha256);"),
    ("        need(MAIN_EPOCH.equals(string(scope, \"main_epoch_sha256\", 64)), \"HOST_EPOCH_ATTESTATION_REQUIRED\");", "        need(mainBinding.epoch.equals(string(scope, \"main_epoch_sha256\", 64)), \"HOST_EPOCH_ATTESTATION_REQUIRED\");"),
    ("        need(MAIN_BASELINE_SCHEMA.equals(string(scope, \"main_baseline_schema\", 64))\n            && MAIN_BASELINE_SHA.equals(string(scope, \"main_baseline_sha256\", 64))\n            && MAIN_BASELINE_QUALIFICATION_SHA.equals(string(scope, \"main_baseline_qualification_sha256\", 64)),", "        need(mainBinding.schema.equals(string(scope, \"main_baseline_schema\", 64))\n            && mainBinding.baseline.equals(string(scope, \"main_baseline_sha256\", 64))\n            && mainBinding.qualification.equals(string(scope, \"main_baseline_qualification_sha256\", 64)),"),
    ("        need(previous.getJSONObject(\"restoration\").getBoolean(\"service_info_verified\"), \"INSPECTION_RESTORATION_UNVERIFIED\");", "        need(mainBinding.sha256.equals(previous.getString(\"main_binding_sha256\")), \"INSPECTION_MAIN_BINDING_CHANGED\");\n        need(previous.getJSONObject(\"restoration\").getBoolean(\"service_info_verified\"), \"INSPECTION_RESTORATION_UNVERIFIED\");"),
)
PYTHON_EDITS = (
    ("def instrumentation_argv(request):\n    raw = validate_request(request)\n    return ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request',\n            base64.b64encode(raw).decode('ascii'), COMPONENT]", "def main_binding():\n    require(MAIN_BASELINE_SCHEMA == 'droidloom.native-leaf-business-baseline.v1',\n            'CURRENT_MAIN_BASELINE_SCHEMA_REQUIRED')\n    value = {'main_epoch_sha256': digest(MAIN_EPOCH),\n             'main_baseline_schema': MAIN_BASELINE_SCHEMA,\n             'main_baseline_sha256': digest(MAIN_BASELINE_SHA),\n             'main_baseline_qualification_sha256': digest(MAIN_BASELINE_QUALIFICATION_SHA)}\n    raw = canonical(value)\n    require(0 < len(raw) <= 512, 'MAIN_BINDING_BOUND')\n    return raw\n\n\ndef instrumentation_argv(request):\n    raw = validate_request(request)\n    return ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request',\n            base64.b64encode(raw).decode('ascii'), '-e', 'main_binding',\n            base64.b64encode(main_binding()).decode('ascii'), COMPONENT]"),
    ("    require(value.get('protocol') == PROTOCOL and value.get('nonce') == request['nonce'] and\n            value.get('op') == request['op'] and value.get('request_sha256') == sha(raw_request) and\n            value.get('wire_codec') == 'gzip-canonical-json-v1',\n            'RESULT_REQUEST_BINDING_FAILED')", "    require(value.get('protocol') == PROTOCOL and value.get('nonce') == request['nonce'] and\n            value.get('op') == request['op'] and value.get('request_sha256') == sha(raw_request) and\n            value.get('wire_codec') == 'gzip-canonical-json-v1' and\n            value.get('main_binding_sha256') == sha(main_binding()),\n            'RESULT_REQUEST_BINDING_FAILED')"),
    ("10196, 10153, 10156)", "10196, 10153, 10156, 10158)"),
)


def _original(originals, name):
    need(set(originals) == set(ORIGINALS), 'EXACT_ORIGINAL_SOURCE_SET_REQUIRED')
    raw = originals[name]; size, expected = ORIGINALS[name]
    need(type(raw) is bytes and len(raw) == size and hashlib.sha256(raw).hexdigest() == expected,
         'EXACT_ORIGINAL_HELPER_SOURCE_REQUIRED:' + name)
    return raw


def _transform(raw, edits):
    text = raw.decode('utf-8'); applied = []
    for old, new in edits:
        need(text.count(old) == 1, 'EXACT_DECLARED_HELPER_TRANSFORMATION_REQUIRED')
        text = text.replace(old, new, 1); applied.append((old, new))
    for old, new in ((OLD_SELF, SELF), (OLD_PROTOCOL, PROTOCOL)):
        count = text.count(old)
        need(count >= (1 if old == OLD_SELF else 0), 'ORIGINAL_LITERAL_MISSING')
        text = text.replace(old, new); applied.append((old, new))
    reverse = text
    for old, new in reversed(applied):
        reverse = reverse.replace(new, old)
    need(reverse.encode('utf-8') == raw, 'UNDECLARED_HELPER_BODY_CHANGE')
    return text.encode('utf-8')


def render_prebuilt(originals):
    """Normal release producer input. No Main or device operation."""
    java = _transform(_original(originals, 'ActionRunner.java'), JAVA_EDITS)
    manifest = _transform(_original(originals, 'AndroidManifest.xml'), ())
    need(all(value.encode() not in java for value in OLD.values()),
         'STATIC_APK_MUST_NOT_EMBED_A_MAIN_GENERATION')
    return {'ActionRunner.java': java, 'AndroidManifest.xml': manifest}


def render(originals, values):
    need(set(values) == set(OLD), 'EXACT_RUNTIME_MAIN_VALUES_REQUIRED')
    need(values['MAIN_BASELINE_SCHEMA'] == SCHEMA and all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v)
         for k, v in values.items() if k != 'MAIN_BASELINE_SCHEMA'), 'TYPED_NEW_MAIN_VALUES_REQUIRED')
    need(all(values[k] != OLD[k] for k in OLD), 'HISTORICAL_MAIN_VALUES_MUST_NOT_REAUTHORIZE')
    output = render_prebuilt(originals)
    edits = list(PYTHON_EDITS) + [(key + ' = ' + repr(old), key + ' = ' + repr(values[key]))
                                for key, old in OLD.items()]
    output['qa_contract.py'] = _transform(_original(originals, 'qa_contract.py'), edits)
    changes = {'schema': 'droidloom.ihg-main-binding-source-transform.v2',
        'fixed_java_edits': len(JAVA_EDITS), 'fixed_python_edits': len(PYTHON_EDITS),
        'actual_main_values_in_python': sorted(OLD), 'actual_main_values_in_apk': [],
        'package': SELF, 'protocol': PROTOCOL,
        'previous_inspection_main_binding_checked': True}
    return output, changes

def create(common, request, output, source_packet_ref):
    need(os.getuid() == os.geteuid() == 0 and set(request) == {'baseline', 'qualification'},
         'EXPLICIT_ACTUAL_FINAL_MAIN_REFERENCES_REQUIRED')
    packet = common.parse(common.read_ref(source_packet_ref))
    need(packet['schema'] == 'pocket4-final-app-preparation-source-v1'
         and packet['Android_execution_authorized_by_publication'] is False,
         'FROZEN_PREPARATION_PACKET_REQUIRED')
    for row in packet['files'] + packet['origins']:
        common.read_ref(row)
    _, modules = common.support()
    baseline = modules['business_baseline.py'].BusinessBaseline(request['baseline'], request['qualification'])
    baseline.require_preinstall_inventory()
    before = baseline.guard(); originals = {}
    for name, (size, digest) in ORIGINALS.items():
        relative = 'src/org/droidloom/qa/ihg/r4/ActionRunner.java' if name == 'ActionRunner.java' else name
        originals[name] = common.read_ref({'path': ORIGINAL_ROOT + '/' + relative,
                                          'bytes': size, 'sha256': digest})
    rendered, changes = render(originals, actual_values(baseline))
    root = Path(output)
    need(root.parent == common.QUALIFICATION and
         re.fullmatch(r'business-ihg-helper-source-[0-9a-f]{32}', root.name),
         'NEW_HELPER_SOURCE_ROOT_REQUIRED')
    root = common.private_dir(root, create=True)
    result = {'schema': 'pocket4-final-ihg-helper-source-v2', 'state': 'SOURCE_GENERATED_ANDROID_UNRUN',
        **request, 'framework_epoch_sha256': baseline.value['framework_epoch']['sha256'],
        'package': SELF, 'protocol': PROTOCOL, 'target_package': 'com.ihg.apps.android', 'target_uid': 10137,
        'source_packet': source_packet_ref, 'declared_transformations': changes,
        'files': {}, 'APK': None, 'installed_UID': None, 'Android_UI_actions': 0,
        'old_runtime_authority_transferred': False, 'whole_app_business_accepted': False}
    for name, raw in rendered.items():
        result['files'][name] = common.write_new(root / name, raw, 0o400)
    for name in ('ihg_helper_build.py', 'ihg_helper_controls.py', 'ihg_session.py', 'app_runtime.py',
                 'ihg_check_baseline.py', 'ihg_check_input.py'):
        refs = [row for row in packet['files'] if Path(row['path']).name == name]
        need(len(refs) == 1, 'EXACT_GENERATED_HELPER_SUPPORT_SOURCE_REQUIRED:' + name)
        result['files'][name] = common.write_new(root / name, common.read_ref(refs[0]), 0o400)
    result['Main_before'] = before; result['Main_after'] = baseline.guard()
    need(result['Main_before'] == result['Main_after'], 'MAIN_CHANGED_DURING_SOURCE_CONSTRUCTION')
    for row in packet['files'] + packet['origins']:
        common.read_ref(row)
    return common.write_new(root / 'source.json', result, 0o400)
