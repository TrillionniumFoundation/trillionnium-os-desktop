"""New owned helper on the frozen recorder's held Main transport.

Default is PLAN_ONLY. Execution requires an externally pinned completed build,
an already installed byte-identical owned APK, a separately initialized fresh
recorder flow, an explicit once-only plan, and interactive-production admission.
This file does not install, launch, close tasks, enter numeric PID namespaces,
or call the old v2 helper. Original task ownership and Main guards are retained.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

HERE = Path(__file__).resolve().parent
RECORDER_MANIFEST_SHA = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
SELF = 'org.droidloom.qa.bestbuy.r1'
BUILD_COMMANDS = ['javac','d8','aapt-package','align','create-owned-signing-key','sign',
                  'signature','alignment','badging','permissions','manifest']


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded(path, maximum=1048576):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and
                0 <= first.st_size <= maximum, 'BOUNDED_SINGLE_REGULAR_FILE_REQUIRED')
        chunks = []; count = 0
        while True:
            part = os.read(fd, min(65536, maximum + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
            require(count <= maximum, 'FILE_GREW_PAST_BOUND')
        last = os.fstat(fd)
        fields = ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        require(count == first.st_size and all(getattr(first,k) == getattr(last,k) for k in fields),
                'FILE_CHANGED_DURING_READ')
        return b''.join(chunks)
    finally:
        os.close(fd)


def pinned(path, expected, maximum=1048576):
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'EXTERNAL_SHA_REQUIRED')
    raw = bounded(path, maximum)
    require(sha(raw) == expected, 'PINNED_FILE_CHANGED: '+str(path))
    return raw


def load(path, expected, name):
    raw = pinned(path, expected)
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def own_source(expected):
    manifest = json.loads(pinned(HERE/'SOURCE_PINS.json', expected, 131072))
    require(isinstance(manifest.get('files'), dict) and 4 <= len(manifest['files']) <= 32,
            'EXACT_OWNED_SOURCE_SET_REQUIRED')
    for name, row in manifest['files'].items():
        rel = Path(name)
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == name,
                'SOURCE_RELATIVE_PATH_REQUIRED')
        require(len(pinned(HERE/name, row['sha256'])) == row['bytes'], 'SOURCE_SIZE_CHANGED')
    require({'qa_adapter.py','qa_contract.py','build_candidate.py','AndroidManifest.xml',
             'src/org/droidloom/qa/bestbuy/r1/ActionRunner.java'} <= set(manifest['files']),
            'OWNED_SOURCE_CLOSURE_INCOMPLETE')
    return manifest


def validate_plan(plan, qa):
    require(isinstance(plan, dict) and plan.get('schema') == 1 and
            plan.get('operation') in ('state','inspect','click'), 'OWNED_PLAN_REQUIRED')
    op = plan['operation']; keys = {'schema','operation','nonces'}
    if op in ('click','set_text'):
        keys.add('selector')
        selector = plan.get('selector')
        require(isinstance(selector, dict) and selector and
                set(selector) <= {'resource_id','text','content_desc','class'} and
                all(isinstance(v, str) and 0 < len(v.encode('utf-8')) <= 256 for v in selector.values()),
                'EXACT_NODE_SELECTOR_REQUIRED')
    if op == 'set_text':
        keys.add('value')
        require(plan.get('value') == qa.PUBLIC_SEARCH_QUERY and
                {'resource_id','class'}<=set(plan['selector']) and plan['selector']['class']=='android.widget.EditText' and
                re.fullmatch(r'com\.bestbuy\.android:id/[A-Za-z0-9_]+',plan['selector']['resource_id']),
                'ONLY_OBSERVED_EXACT_EDIT_RESOURCE_AND_PUBLIC_QUERY')
    require(set(plan) == keys and isinstance(plan['nonces'], dict), 'EXACT_PLAN_KEYS_REQUIRED')
    names = {'state'} if op == 'state' else {'before','inspect','after'} | ({'action'} if op in ('click','set_text') else set())
    require(set(plan['nonces']) == names, 'EXACT_PHASE_NONCES_REQUIRED')
    values = [qa.nonce(value) for value in plan['nonces'].values()]
    require(len(set(values)) == len(values), 'DISTINCT_PHASE_NONCES_REQUIRED')
    return plan


def qualified_build(args, manifest, builder):
    raw = pinned(args.build_receipt, args.build_receipt_sha256)
    receipt = json.loads(raw)
    require(receipt.get('state') == 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN' and
            receipt.get('package') == SELF and receipt.get('source_manifest_sha256') == args.source_manifest_sha256,
            'MATCHING_COMPLETED_OWNED_BUILD_REQUIRED')
    require(receipt.get('source_sha256') == {key: row['sha256'] for key, row in manifest['files'].items()} and
            receipt.get('source_unchanged') is True and receipt.get('tools_unchanged') is True and
            receipt.get('manifest_contract') == builder.manifest_contract(), 'BUILD_SOURCE_OR_MANIFEST_DIFFERS')
    require(receipt.get('tools_before') == receipt.get('tools_after') and
            set(receipt['tools_before']) == set(builder.TOOLS), 'BUILD_TOOL_SET_DIFFERS')
    for name, (path, digest) in builder.TOOLS.items():
        value = receipt['tools_before'][name]
        require(value['sha256'] == digest and value['declared_path'] == path and
                type(value['bytes']) is int and value['bytes'] > 0, 'BUILD_TOOL_PIN_DIFFERS')
    require(receipt.get('error') is None and receipt.get('android_installed') is False and
            receipt.get('Main_mutations') == receipt.get('Android_UI_actions') == 0, 'BUILD_SCOPE_CHANGED')
    commands = receipt.get('commands')
    require(isinstance(commands, list) and [row.get('name') for row in commands] == BUILD_COMMANDS and
            all(row.get('returncode') == 0 and row.get('owned_child_joined') is True and
                row.get('error') is None and row.get('secondary_errors') == [] for row in commands),
            'ACTUAL_BUILD_COMMAND_COMPLETION_REQUIRED')
    artifact = receipt.get('APK')
    require(isinstance(artifact, dict) and artifact.get('sha256') == args.apk_sha256 and
            type(artifact.get('bytes')) is int and 0 < artifact['bytes'] <= 2097152 and
            receipt.get('signer_certificate_sha256') == args.signer_certificate_sha256,
            'EXTERNALLY_REVIEWED_APK_AND_SIGNER_REQUIRED')
    require(re.fullmatch('[0-9a-f]{64}', args.apk_sha256) and
            re.fullmatch('[0-9a-f]{64}', args.signer_certificate_sha256), 'EXPLICIT_APK_SIGNER_SHA_REQUIRED')
    return {'build_receipt_sha256':sha(raw), 'source_manifest_sha256':args.source_manifest_sha256,
            'APK':artifact, 'signer_certificate_sha256':args.signer_certificate_sha256,
            'self_instrumentation':True, 'old_v2_provenance_inherited':False}


class Session:
    def __init__(self, flow, recorder, qa, proof, helper_uid):
        require(flow.contract.sha256 == RECORDER_MANIFEST_SHA and not flow._private_backend_transport,
                'FROZEN_PUBLIC_RECORDER_TRANSPORT_REQUIRED')
        require(type(helper_uid) is int and 10000 <= helper_uid < 100000 and helper_uid not in (10130,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190,10137,10196),
                'EXACT_NEW_OWNED_HELPER_UID_REQUIRED')
        self.flow, self.recorder, self.qa, self.proof, self.uid = flow, recorder, qa, proof, helper_uid
        self.nonces = set()

    def installed(self):
        f = self.flow; f.guard(); binding = f.bind()
        actual = f.android(['/system/bin/cmd','package','list','packages','-U','--user','0',SELF], 8)
        require(actual.decode('utf-8','strict').splitlines() == ['package:'+SELF+' uid:'+str(self.uid)],
                'OWNED_HELPER_UID_READBACK_DIFFERS')
        raw = f.android(['/system/bin/cmd','package','path','--user','0',SELF], 8)
        lines = raw.decode('utf-8','strict').splitlines()
        require(len(lines) == 1 and lines[0].startswith('package:/data/app/') and lines[0].endswith('/base.apk'),
                'SINGLE_OWNED_BASE_APK_REQUIRED')
        path = lines[0][8:]
        require(len(path) <= 1024 and '\0' not in path and '..' not in Path(path).parts and str(Path(path)) == path,
                'OWNED_APK_PATH_INVALID')
        data, metadata = binding.target.read_file(path, 2097152)
        require(len(data) == self.proof['APK']['bytes'] and sha(data) == self.proof['APK']['sha256'],
                'INSTALLED_APK_NOT_MATCHING_VERIFIED_SOURCE_AND_SIGNER')
        del data
        f.guard()
        return {'package':SELF, 'uid':self.uid, 'base_apk':path, 'apk_sha256':self.proof['APK']['sha256'],
                'bytes':self.proof['APK']['bytes'], 'held_file':metadata,
                'signer_bound_by_exact_signed_apk_bytes':self.proof['signer_certificate_sha256']}

    def instrument(self, request):
        qa, f = self.qa, self.flow
        qa.validate_request(request)
        require(request['nonce'] not in self.nonces, 'NONCE_CANNOT_BE_REPLAYED')
        self.nonces.add(request['nonce'])
        self.recorder.write_new(f.step/(request['nonce']+'.request.json'), request)
        before = f.command_index
        out = f.android(qa.instrumentation_argv(request), 20, mutation=request['op'] in ('click','set_text'))
        require(f.command_index == before+1, 'ONE_ACTUAL_HELD_COMMAND_REQUIRED')
        stem = f.step/('command-%03d' % f.command_index)
        raw = bounded(str(stem)+'.result.json', 65536); row = json.loads(raw)
        stderr = bounded(str(stem)+'.stderr', 1048576)
        require(row.get('owned_command_joined') is True and row.get('spawned') is True and
                row.get('timed_out') is False and row.get('errors') == [] and
                row.get('stdout_sha256') == sha(out) and row.get('stderr_sha256') == sha(stderr),
                'ACTUAL_JOINED_COMMAND_OBSERVATION_REQUIRED')
        # f.android has already recorded lease exit and the mandatory post guard.
        try:
            assessed = qa.parse_completed(out, stderr, row['returncode'], request, self.uid)
        except BaseException as primary:
            # Keep the strict finish gate and original exception. A helper's
            # explicit finish(0) can additionally explain the failure without
            # exporting an inspection tree or manufacturing a success result.
            failure = {'request_nonce':request['nonce'],'operation':request['op'],
                'qualified_success':False,'command_result_sha256':sha(raw),
                'stdout_sha256':sha(out),'stderr_sha256':sha(stderr),
                'primary_error':{'type':type(primary).__name__,'message':str(primary)}}
            try:
                failure['helper_rejection'] = qa.failure_diagnostic(out,request,self.uid)
            except Exception as diagnostic_error:
                failure['diagnostic_unavailable'] = type(diagnostic_error).__name__
            primary.details = {'previous_details':getattr(primary,'details',None),
                               'owned_helper_failure':failure}
            try:
                self.recorder.write_new(f.step/(request['nonce']+'.failed-assessment.json'),failure)
            except BaseException as secondary:
                primary.add_note('failed assessment write: '+type(secondary).__name__)
            raise
        assessed['recorder_command_result_sha256'] = sha(raw)
        assessed['held_transport_returned_after_post_guard'] = True
        self.recorder.write_new(f.step/(request['nonce']+'.assessment.json'), assessed)
        return assessed

    def foreground(self):
        f = self.flow
        original = f.contract.load('references/android_backend.py', 'owned_qa_exact_foreground')
        # Preserve the old backend's privacy boundary: raw dumpsys is parsed in
        # memory and discarded. Transport still records intent/rc/length/hash.
        require(not f._private_backend_transport, 'NO_NESTED_PRIVATE_BACKEND')
        f._private_backend_transport = True
        try:
            original.arun = lambda argv, timeout=30: f.android(argv, timeout, mutation=False)
            value = original.foreground()
        finally:
            f._private_backend_transport = False
        require(value['package'] == self.qa.PACKAGE, 'FOREGROUND_MUST_STILL_BE_BESTBUY')
        return self.qa.scope({'package':value['package'], 'uid':self.qa.UID, 'user':0, 'display':0,
            'activity':value['package']+'/'+value['activity'], 'window_token':value['window_token'],
            'main_epoch_sha256':self.qa.MAIN_EPOCH})

    def task(self):
        selected = self.flow.selected_task()
        require(selected['package'] == self.qa.PACKAGE and selected['prelaunch_absent'] is True and
                selected['cleanup_allowed'] is True, 'ORIGINAL_OWNED_TASK_SCOPE_REQUIRED')
        _, roots, _ = self.flow.stacks()
        require(self.flow.tasks.exact_leaf(roots, selected['task'], self.qa.PACKAGE), 'FLOW_TASK_SCOPE_CHANGED')
        return selected

    def sequence(self, plan):
        qa = self.qa; names = plan['nonces']
        result = {'installed_before':self.installed(), 'old_v2_helper_called':False,
                  'business_success_verified':False, 'audio_verified':False}
        def request(phase, op, **extra):
            return {'protocol':qa.PROTOCOL, 'nonce':names[phase], 'op':op, **extra}
        if plan['operation'] == 'state':
            result['state_only'] = self.instrument(request('state','state'))
            result['installed_after'] = self.installed()
            require(result['installed_before'] == result['installed_after'], 'OWNED_HELPER_INSTALLATION_CHANGED')
            return result
        primary = None; before = middle = after = scope = None
        state_sequence_started = False
        result.update(error=None,secondary_errors=[],after_state_attempted=False,
                      after_state_completed=False,restoration_qualified=False)
        self.sequence_observation = result

        def remember(phase, error):
            nonlocal primary
            record = {'phase':phase,'type':type(error).__name__,'message':str(error)}
            if primary is None:
                primary = error; result['error'] = record
            else:
                result['secondary_errors'].append(record)
                primary.add_note(phase+': '+type(error).__name__+': '+str(error))

        try:
            result['owned_task'] = self.task()
            state_sequence_started = True
            before = self.instrument(request('before','state'))
            scope = self.foreground(); result['foreground_before'] = scope
            inspected = self.instrument(request('inspect','inspect', scope=scope))
            require(self.foreground() == scope, 'ORIGINAL_ACTIVITY_OR_WINDOW_CHANGED_AFTER_INSPECT')
            middle = inspected
            result['inspection_wire_sha256'] = inspected['wire_sha256']
            if plan['operation'] in ('click','set_text'):
                editing = plan['operation']=='set_text'
                node = (qa.select_unique_editable if editing else qa.select_unique_clickable)(
                    inspected['helper']['inspection'], plan['selector'])
                extra = {'value':plan['value']} if editing else {}
                action = request('action',plan['operation'], scope=scope, inspection_nonce=names['inspect'],
                    inspection_sha256=inspected['wire_sha256'], **node, **extra)
                middle = None
                middle = self.instrument(action)
                require(middle['helper']['action_window'] == inspected['helper']['inspection']['window'],
                        'ACKNOWLEDGED_ACTION_WINDOW_DIFFERS')
                result['set_text_acknowledged' if editing else 'click_acknowledged'] = True
        except BaseException as error:
            remember('state_inspection_or_action',error)
        finally:
            # Exactly one fresh after nonce, even after the inspection rejected.
            # The original transport guard may itself reject this attempt when
            # an earlier command did not join; that remains a secondary failure.
            if state_sequence_started:
                result['after_state_attempted'] = True
                try:
                    after = self.instrument(request('after','state'))
                    result['after_state_completed'] = True
                    result['post_termination_state'] = {'nonce':names['after'],
                        'wire_sha256':after['wire_sha256'],'state':after['helper']['state'],
                        'helper_uid':after['helper']['self_uid'],
                        'ui_automation_connected':after['helper']['ui_automation_connected']}
                    if before is not None:
                        result['post_state_matches_before'] = before['helper']['state'] == after['helper']['state']
                        require(result['post_state_matches_before'],'POST_TERMINATION_ACCESSIBILITY_STATE_CHANGED')
                    if before is not None and middle is not None:
                        result['accessibility_restoration'] = qa.assess_restoration(before,middle,after)
                        result['restoration_qualified'] = True
                except BaseException as error:
                    remember('independent_after_state',error)
            if scope is not None:
                try:
                    result['foreground_after'] = self.foreground()
                    if plan['operation'] == 'inspect':
                        require(result['foreground_after'] == scope,'READ_ONLY_INSPECT_FOREGROUND_CHANGED')
                except BaseException as error:
                    remember('post_foreground',error)
            if 'owned_task' in result:
                try:
                    require(self.task() == result['owned_task'],'POST_OPERATION_OWNED_TASK_CHANGED')
                except BaseException as error:
                    remember('post_owned_task',error)
            try:
                result['installed_after'] = self.installed()
                require(result['installed_before'] == result['installed_after'],'OWNED_HELPER_INSTALLATION_CHANGED')
            except BaseException as error:
                remember('post_installed_identity',error)
        if primary is not None:
            primary.details = {'previous_details':getattr(primary,'details',None),
                               'qa_sequence_observation':result}
            raise primary
        require(result['after_state_completed'] and result['restoration_qualified'],
                'INDEPENDENT_AFTER_STATE_AND_RESTORATION_REQUIRED')
        return result


def execute(args):
    # This source-bound library cannot activate the old Bili business Flow.
    # A separate exact BESTBUY artifact/held-transport/task adapter is required.
    raise RuntimeError('DEDICATED_BESTBUY_HELD_FLOW_ADMISSION_REQUIRED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-once', action='store_true')
    parser.add_argument('--interactive-production', action='store_true')
    for name in ('source-manifest-sha256','build-receipt-sha256','apk-sha256',
                 'signer-certificate-sha256','plan-sha256','step'):
        parser.add_argument('--'+name)
    for name in ('build-receipt','recorder-root','flow-dir','plan'):
        parser.add_argument('--'+name, type=Path)
    parser.add_argument('--helper-uid', type=int)
    args = parser.parse_args()
    if not args.execute_once:
        print(json.dumps({'state':'PLAN_ONLY', 'package':SELF, 'recorder_manifest_sha256':RECORDER_MANIFEST_SHA,
            'operations':['state','inspect','click'], 'install_launch_task_cleanup_or_UI_actions':0,
            'actual_build_install_and_runtime_qualification_required':True,
            'standalone_execute_admitted':False,'dedicated_BESTBUY_flow_required':True}))
        return 0
    require(all(getattr(args, name) is not None for name in ('source_manifest_sha256','build_receipt_sha256',
        'apk_sha256','signer_certificate_sha256','plan_sha256','step','build_receipt','recorder_root',
        'flow_dir','plan','helper_uid')), 'ALL_EXACT_EXTERNAL_BINDINGS_REQUIRED')
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
