"""Exact accepted producer identities; these pins grant no execution authority."""
import hashlib
import json
from pathlib import Path

HEAD = '9ecce4f94dec80500c05322106907e48a0668b05'
TREE = '12fe22ce02be9759963835faa4e7a7d0a762ddc2'
TRACKED_FILES = 2118
LOCK_SHA = '30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4'
SPEC_SHA = 'a8e8145524482f3ceea153b117e9df334c7f4f2c4fe8cd33a289b284d18c2f4d'
PRODUCT = 'droidloom_x86_64'
FRAMEWORK_TARGETS = ['services', 'WmTests', 'FrameworksServicesTests', 'UsbTests', 'AudioServiceTests', 'module-info']
VENDOR_TARGETS = ['vendorimage', 'secilc']
TEST_PROVIDERS = {
    'WmTests': 'frameworks/base/services/tests/wmtests',
    'FrameworksServicesTests': 'frameworks/base/services/tests/servicestests',
    'UsbTests': 'frameworks/base/tests/UsbTests',
    'AudioServiceTests': 'frameworks/base/services/tests/audio',
}
TOOL_PINS = {
    'droidloom-source': (1529072, 'e5e0f1a0b51b42e3d16a9482f6583c8cd01036f7750ef157245329f32911c208'),
    'droidloom-update': (7578944, '11ac8a474009aacc2c407c02b5b59a6344b2d6ca0bd0e4702634d01d3f83dac6'),
}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def spec():
    raw = Path(__file__).with_name('PRODUCER-SPEC.json').read_bytes()
    need(len(raw) == 23580 and hashlib.sha256(raw).hexdigest() == SPEC_SHA, 'exact reviewed producer specification changed')
    value = json.loads(raw)
    need((value['head'], value['tree'], value['tracked_files']) == (HEAD, TREE, TRACKED_FILES), 'producer specification identity differs')
    return value


def targets(phase):
    need(phase in ('vendor', 'wm'), 'only the two original finite carrier roles')
    return list(VENDOR_TARGETS if phase == 'vendor' else FRAMEWORK_TARGETS)


def validate_frozen(frozen):
    need(frozen['recipe_commit'] == HEAD and frozen['recipe_tree'] == TREE and
         len(frozen['recipe_source_files']) == TRACKED_FILES, 'wrong current full producer')
    need(set(frozen['recipe_source_refs']) == set(frozen['recipe_source_files']), 'complete current source reference map required')
    tools = frozen['normal_tools']
    need(len(tools) == 2 and {Path(row['path']).name for row in tools} == set(TOOL_PINS), 'exact two current normal tools required')
    for row in tools:
        need((row['bytes'], row['sha256']) == TOOL_PINS[Path(row['path']).name], 'current normal ELF pin differs')
    need(frozen.get('recipe_directory_refs') and frozen.get('recipe_git_directory_refs'), 'complete recipe and Git directory membership required')
    return True


def require_new_execution_binding():
    # No switches, environment overrides or fabricated owner receipt can turn
    # this source-only repair into dispatch authority. The still-historical
    # carrier paths must be rebound in a separately reviewed source generation.
    raise RuntimeError('SOURCE_ONLY_CANDIDATE: fresh finite storage owner, full admission, output/control paths and exact namespace binding have not been reviewed')
