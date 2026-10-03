"""Closed P2B Source correspondence only. Compilation/native remain separate."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
try:
    from . import verify_approved_native_startup as source_gate
except ImportError:
    import verify_approved_native_startup as source_gate
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/approved-service-runtime.v2.json"
EXPECTED = json.loads('{"schema":"trillionnium.desktop.approved-service-typed-runtime.v2","status":"SOURCE_P2B_FOUNDATION_UNBOUND_RUNTIME_REQUALIFICATION_PENDING","requirements":["G1","G2"],"default_activation":false,"actual_parent":{"head":"5aac2a8503c9d3b84fbb81a803edd22025d52656","tree":"bc641092b05a96163b8d96af01ddd331bffa9dff","scope":"SOURCE_ONLY_ROOT_ACCEPTED_NO_COMPILE_QUALIFICATION"},"public_api":{"ServiceEngineCommand::into_parts":"pub fn into_parts ( self ) - > ( Option < PageOwnerSnapshot > , BrowserActorMessage , ServiceEngineCompletion )","ServiceEngineCompletion::request_id":"pub fn request_id ( & self ) - > & str","ServiceEngineCompletion::deadline":"pub fn deadline ( & self ) - > Instant","ServiceEngineCompletion::ensure_current_request":"pub fn ensure_current_request ( & self ) - > Result < ( ) , RuntimeFailure >","ServiceEngineCompletion::complete":"pub fn complete ( mut self , result : Result < RuntimeReply , RuntimeFailure > ) - > CompletionDelivery","ServiceEngineBridge::pump_one":"pub fn pump_one ( & mut self ) - > CallbackPumpResult","ServiceEngineBridge::take_command":"pub fn take_command ( & mut self ) - > Option < ServiceEngineCommand >","ServiceEngineBridge::next_wake_deadline":"pub fn next_wake_deadline ( & self ) - > Option < Instant >","ServiceEngineBridge::retire":"pub fn retire ( & mut self )","closed_immutable_service_engine_pair":"pub fn closed_immutable_service_engine_pair ( waker : Arc < dyn EngineEventLoopWaker > , ) - > ( ServiceEngineEndpoint , ServiceEngineBridge )","ServiceServoRuntimeCommand::into_parts":"pub fn into_parts ( self ) - > ( Option < PageOwnerSnapshot > , ServoRuntimeOperation , ServiceServoRuntimeCompletion )","ServiceServoRuntimeCompletion::request_id":"pub fn request_id ( & self ) - > & str","ServiceServoRuntimeCompletion::deadline":"pub fn deadline ( & self ) - > Instant","ServiceServoRuntimeCompletion::ensure_current_request":"pub fn ensure_current_request ( & self ) - > Result < ( ) , ServoRuntimeError >","ServiceServoRuntimeCompletion::complete_success":"pub fn complete_success ( self , result : JsonObject , current_url : Option < String > ) - > ServoCompletionDelivery","ServiceServoRuntimeCompletion::complete_error":"pub fn complete_error ( self , error : ServoRuntimeError ) - > ServoCompletionDelivery","ServiceServoRuntimeBridge::pump_one":"pub fn pump_one ( & mut self ) - > ServoPumpResult","ServiceServoRuntimeBridge::take_command":"pub fn take_command ( & mut self ) - > Option < ServiceServoRuntimeCommand >","ServiceServoRuntimeBridge::next_wake_deadline":"pub fn next_wake_deadline ( & self ) - > Option < Instant >","ServiceServoRuntimeBridge::retire":"pub fn retire ( & mut self )","closed_immutable_service_runtime_pair":"pub fn closed_immutable_service_runtime_pair ( waker : Arc < dyn ServoEventLoopWaker > , ) - > ( ServiceServoRuntimeEndpoint , ServiceServoRuntimeBridge )"},"opaque_types":{"ServiceEngineEndpoint":"inner : Option < EngineThreadRuntime > , state : Arc < ServiceEngineState > ,","ServiceEngineCommand":"owner : Option < PageOwnerSnapshot > , message : BrowserActorMessage , completion : ServiceEngineCompletion ,","ServiceEngineCompletion":"inner : Option < EngineCompletion > , engine : Arc < ServiceEngineState > , scope : Arc < ServiceDispatchScope > ,","ServiceEngineBridge":"receiver : Receiver < PendingCall > , state : Arc < ServiceEngineState > , waker : Arc < dyn EngineEventLoopWaker > , active : Option < ServiceActiveCall > , command : Option < ServiceEngineCommand > , retired : bool , _thread_affinity : PhantomData < Rc < ( ) > > ,","ServiceServoRuntimeEndpoint":"inner : Option < ServiceEngineEndpoint > ,","ServiceServoRuntimeCommand":"inner : ServiceEngineCommand ,","ServiceServoRuntimeCompletion":"inner : ServiceEngineCompletion ,","ServiceServoRuntimeBridge":"inner : ServiceEngineBridge ,"},"production_sha256":{"crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop.rs":"beb88f45b8b590eb613eee2a4863a77a18e2dbf59f19a473a8b4586381eb5807","crates/hepta-browser-actor/src/servo_runtime/service_runtime.rs":"df07c1c8d45d62b0a9f6eb72914845e5c301a7d28a48e0fdf2787d05d9021a28"},"all_function_tokens_sha256":{"crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop.rs":{"ServiceDispatchScope::current":"21cdac5eebda176dc01c78d8185fd8adb1a471e48602a025e5115187d5ec3ed5","ServiceEngineState::creator":"9e882074fb2f9da508ff4a88e01355c0f5f4167d743455135af7d91d0e238ea0","ServiceEngineState::service_current":"ba1ca37c8e1cde068d5a394996c0ddb522436c4b4e385a4b9542ebe6d1a7b651","ServiceEngineState::capture":"f92962bf244cd4d07518da86e424aae4ee95fa596beb74984d5a4051ee2909ce","Drop:ServiceEngineEndpoint::drop":"43213cece9967df44c0f2f23981d277128aecf16d536952634093e23989001a5","ServiceEngineCommand::into_parts":"572d79883f624855e433aac1e82303d9bccdffbc15ebf48a306cf6b3a39a2959","ServiceEngineCompletion::request_id":"7c34d97f9f30d6f980c44f4dca506a2cba66ce5d75da7debaf2fa14349ad57a1","ServiceEngineCompletion::deadline":"16b45f8b97933c12a44b73a2bc6afd6360ab4a7114239042bb9cba6f260cbe38","ServiceEngineCompletion::ensure_current_request":"1754af449c9f146e61f9b2999ef613cff84c7edfcae75a0d46c4c3700698f7f2","ServiceEngineCompletion::complete":"8db2ad03bafb36a1e5fd4b0e3ab934a0d8157b04879cef82863f89bb984c522a","Drop:ServiceEngineCompletion::drop":"8e43dcd90fa412a65dc0fa30a648352b16e4062d1752341477fdf667b74ca2a9","ServiceEngineBridge::owner_current":"17358a92c923c78200e539a2fd1413666434fd858876acd46bfc5843b3553663","ServiceEngineBridge::pump_one":"6078b29d1f8511aef6da23fb905b2e958c87811a5bfeed306e7325576d42c4f9","ServiceEngineBridge::poll_active":"fa8d481dafcd99b644b76d1597299dbd416cff2500b0a42b11bbb05dba81fd97","ServiceEngineBridge::fail_active":"1801f94bc74f8a1a419eaf7a65584d25abd1e6fc8ae62ae23e7c77d54e376953","ServiceEngineBridge::take_command":"8019d1032f5500398ca6ee0f8caf8848e80afb5aef29575ae5fbb4c35921cdb9","ServiceEngineBridge::next_wake_deadline":"280cdaf357559da6e3c5d29341b2cee39e24300f6c4caf767c77cd611a06f7c8","ServiceEngineBridge::retire":"a3a64f220c3baf45b7a575a4db901bff35cfea00097b6008049a49b369c5cf2f","Drop:ServiceEngineBridge::drop":"47866b78d382bf79cc2b737ce49c13caf4401fbdd1972fa484f15eb9cd890d1c","closed_operation":"efe4c67bd0b862c85daa5f7cc9e6a9530449b254810e56ecf787dde99b3a73c7","closed_immutable_service_engine_pair":"2103f126649738eab3e37c5a6ec0a2ed031d1717a07de2d029287885e53397a8"},"crates/hepta-browser-actor/src/servo_runtime/service_runtime.rs":{"Drop:ServiceServoRuntimeEndpoint::drop":"cec4a6d68785ea241c43edf60a3fb3a05e11bab8ff288ac27fb24fc0e6336396","ServiceServoRuntimeCommand::into_parts":"d1032fe3ad4a471115878124547d14d6f6170ff0d43aac7d5cb61411561c53b2","ServiceServoRuntimeCompletion::request_id":"3d8e27d4aa3b294a71ffacc6841ade76787ca3117146a46501c1213057e85397","ServiceServoRuntimeCompletion::deadline":"73c7695611ed334dc44c0b99d22222781da36a1aee8ed8cb8a055d6fd8dec01f","ServiceServoRuntimeCompletion::ensure_current_request":"0686ac9e91b65ceff29e2be64a951cafec0ba4712c9d70198970b8afaf60089c","ServiceServoRuntimeCompletion::complete_success":"5182dc3a692ce9b8ef133da55e4bb119f88f300fa028eb063f53a156f8a7da2e","ServiceServoRuntimeCompletion::complete_error":"de503ab8bd6d071fc93ff3d900cd8127729612e3e4b0436641a64c80bbd7f9cd","ServiceServoRuntimeBridge::pump_one":"d5f5029817e6a9d4ead417c7c233f5368ddbb395ebd94708c2970698565c1db7","ServiceServoRuntimeBridge::take_command":"32eb5df346e7a21efacbed9c007c5995dc1e93290ba4a4af4008dc8aeeaab64e","ServiceServoRuntimeBridge::next_wake_deadline":"052563c1845f4f36c7d16e1f86cc3f88a7483ace643c4046df38dcf027d93157","ServiceServoRuntimeBridge::retire":"ccd8521a33d99bfa541f14aec82bb4ef81c1ad17bf734c5e9954c34d52dfc44d","closed_immutable_service_runtime_pair":"0617fdf9d810018d40bccd8aef8eac1d5f6703ce992566b9840255ada90394d2"}},"finite_parent_inverse":{"crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop.rs":{"offset":490,"block":"#[cfg(target_os = \\"linux\\")]\\nmod service_event_loop;\\n#[cfg(target_os = \\"linux\\")]\\npub use service_event_loop::{\\n    ServiceEngineBridge, ServiceEngineCommand, ServiceEngineCompletion, ServiceEngineEndpoint,\\n    closed_immutable_service_engine_pair,\\n};\\n\\n","parent_bytes":18070,"parent_sha256":"f3e861e6963f01b18d535e4c6f4fd836b80ebf3c20c218886cebc9f6b0b9a683","complete_bytes":18321,"complete_sha256":"5462983175422ec898cdfce1ef46aaa688fc91fd8fc639b1a778386132278362","scope":"PRODUCTION_ADJACENT_BEFORE_TEST_MODULES"},"crates/hepta-browser-actor/src/servo_runtime.rs":{"offset":926,"block":"#[cfg(target_os = \\"linux\\")]\\nmod service_runtime;\\n#[cfg(target_os = \\"linux\\")]\\npub use service_runtime::{\\n    ServiceServoRuntimeBridge, ServiceServoRuntimeCommand, ServiceServoRuntimeCompletion,\\n    ServiceServoRuntimeEndpoint, closed_immutable_service_runtime_pair,\\n};\\n\\n","parent_bytes":29360,"parent_sha256":"2a9e93f7da22f3fba4abbaa6d1dbf4588b1eeee9baa7e6525162d0ba8b3db36c","complete_bytes":29630,"complete_sha256":"a015fd45e6740c9aa1761bac035dc30e361d1a2e16f37d4b09e7e89899950848","scope":"PRODUCTION_ADJACENT_BEFORE_TEST_MODULES"},"crates/hepta-browser-actor/src/lib.rs":{"offset":1996,"block":"#[cfg(target_os = \\"linux\\")]\\npub use servo_runtime::{\\n    ServiceServoRuntimeBridge, ServiceServoRuntimeCommand, ServiceServoRuntimeCompletion,\\n    ServiceServoRuntimeEndpoint, closed_immutable_service_runtime_pair,\\n};\\n\\n","parent_bytes":6048,"parent_sha256":"af10d8d266fc67b6695d52ca25e592f8ce09b5f3593e12faa9317d019b390674","complete_bytes":6267,"complete_sha256":"409645d29caac404f78218ef85e68faf0c3027d3927a21045416bdc988252a67","scope":"PRODUCTION_ADJACENT_BEFORE_TEST_MODULES"},"Makefile":{"offset":746,"block":"\\tpython3 tools/verify_approved_service_runtime.py\\n","parent_bytes":2645,"parent_sha256":"fc645701d1bcfa3db0bc7cc737fed704dd71a2337ea356042304b7e8e47dd03e","complete_bytes":2695,"complete_sha256":"06508857115fa54c01a079d2596d4ba83dab98f0c39ca5a3daf5a048c1db8645"},"tools/verify_approved_native_startup.py":{"kind":"EXACT_ONE_READER_TRANSFER","parent":"    value = read(root / path)\\n","actual":"    value = read(root / path)\\n    try:\\n        from .verify_approved_service_runtime import parent_source as service_runtime_parent_source\\n    except ImportError:\\n        from verify_approved_service_runtime import parent_source as service_runtime_parent_source\\n    value = service_runtime_parent_source(path, value.decode(\\"utf-8\\", \\"strict\\")).encode(\\"utf-8\\")\\n","parent_bytes":37487,"parent_sha256":"e86ac78e4b35e9856f545c96b6cdc25d9b4b84ea3317aeeb6bc9506199f85b38","complete_bytes":37816,"complete_sha256":"d485dcc450e731b7f2cd9edaa2dd3d08bf026b344835733d89e18935fa651fa0"}},"scope":{"public_api_count":21,"opaque_count":8,"public_registration_api":false,"generic_runtime_input":false,"raw_endpoint_or_completion_escape":false,"fake_binding_or_observed_principal_approval":false,"scope_selection":"P2A private nested opaque core constructor NOT_IMPLEMENTED; only genuine original Binding/verifier on exact same engine Arc/session, fresh private nonce. No caller proof flag.","current_pair":"session=None and registration=None. No genuine owning slot is minted and no approved native command can be emitted by this P2B foundation.","source_inside_final_pipeline":true,"original_pair_deadline_and_closed_URL_preserved":true,"async_proof":"capture original readonly scope once; no late registrar lookup; readonly Arc does not prolong Agent/Owner custody","completion_queued_is_native_or_durable_success":false,"postsend":"physical send may have happened; Source post failure retires and retains uncertainty, not a claim of rollback","request_and_native_budgets_changed":false,"actual_Servo_or_native60":false,"actor_coordinator_managed_factory_installed_activation":false,"layout_revision":"finite exact production-adjacent insertion; removing reviewed block restores all parent bytes, no items_after_test_module allow","future_privacy_layout":"P2A core nested child of service_event_loop; ServoActor nested child of service_runtime. No public/pub(crate) registrar or raw getter is necessary.","Drop":"local deny-only closure before old token drop; no Source filesystem refresh or inferred external effect rollback","actual_original_clock_correspondence":"with_original_pair returns original P1 ceiling; every scope current requires exact equality to captured original_deadline, dispatch <= it"},"API_preconditions_and_errors":{"factory":"creates unused fixed closed mechanism pair only; no approved Source, session, principal, URL/profile choice or future Instant parameter","pump_take":"original creator PID/thread and P1 full namespace/Source/Owner when bound; original captured request proof/pair/clock before native command. Missing/foreign/reused/private registration -> refuse and retire","completion":"same engine/session/original verifier and full original pair, original Instant and fixed closed URL/object bounds before queue and same captured proof through final forward. Source/pair revocation -> PeerIdentityRevoked, deadline -> DeadlineExceeded, invalid/dropped/uncertain -> retired pair","diagnostic":"request ID/deadline/next wake are read-only original metadata, not authority, new budget, wire delivery or native health","mapping":"only typed closed simulation command; unexpected excluded variant refuses completion and unwinds, no native operation replacement"},"compile_fail_inventory_NOT_EXECUTED":["ServiceEngineEndpoint.inner private","ServiceEngineCompletion.inner private","ServiceEngineCompletion moved single use","ServiceEngineBridge not Send","ServiceServoRuntimeEndpoint.inner private","ServiceServoRuntimeCompletion.inner private"],"new_unit_inventory_NOT_EXECUTED":["unbound_pair_never_emits_an_approved_command","dropped_endpoint_permanently_retires_unused_bridge","fixed_profile_refuses_external_and_unimplemented_operations","create_requires_exact_fixed_ephemeral_profile","thin_unbound_pair_has_no_service_command_or_native_health","thin_endpoint_drop_does_not_reopen_or_replay"]}')

def _sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _read(root, name):
    path = root / name
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 1048576:
        raise ValueError('P2B Source is not a bounded single-link regular file')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError('P2B Source changed before open')
        raw = stream.read(1048577)
        after_fd = os.fstat(stream.fileno())
    after = path.lstat()
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if identity(before) != identity(after_fd) or identity(before) != identity(after) or len(raw) > 1048576:
        raise ValueError('P2B Source changed during read')
    return raw.decode('utf-8', 'strict')

def parent_source(path, text):
    """Exact denial-only inverse; the source hashes never approve a principal."""
    if type(text) is not str:
        raise ValueError('P2B Source type differs')
    rule = EXPECTED['finite_parent_inverse'].get(path)
    if rule is None:
        return text
    raw = text.encode('utf-8')
    if len(raw) == rule['parent_bytes'] and _sha(raw) == rule['parent_sha256']:
        return text
    if len(raw) != rule['complete_bytes'] or _sha(raw) != rule['complete_sha256']:
        raise ValueError('P2B complete parent object differs')
    if rule.get('kind') == 'EXACT_ONE_READER_TRANSFER':
        if text.count(rule['actual']) != 1:
            raise ValueError('P2B reader insertion differs')
        text = text.replace(rule['actual'], rule['parent'], 1)
    else:
        offset, block = rule['offset'], rule['block'].encode('utf-8')
        if raw[offset:offset + len(block)] != block:
            raise ValueError('P2B production insertion position differs')
        text = (raw[:offset] + raw[offset + len(block):]).decode('utf-8', 'strict')
    raw = text.encode('utf-8')
    if len(raw) != rule['parent_bytes'] or _sha(raw) != rule['parent_sha256']:
        raise ValueError('P2B whole parent restoration differs')
    return text

def inputs(root=ROOT):
    paths = set(EXPECTED['production_sha256']) | set(EXPECTED['finite_parent_inverse'])
    return {path: _read(root, path) for path in sorted(paths)}

def check(contract, texts):
    source_gate.typed_equal(contract, EXPECTED)
    if set(texts) != set(EXPECTED['production_sha256']) | set(EXPECTED['finite_parent_inverse']):
        raise ValueError('P2B Source set differs')
    public, types = {}, {}
    for path, expected in EXPECTED['production_sha256'].items():
        text = texts[path]
        if _sha(text.encode('utf-8')) != expected:
            raise ValueError('P2B whole production bytes differ')
        inventory = source_gate.rust_inventory(text)
        public.update(inventory['public_api'])
        types.update({name: ' '.join(rule['body']) for name, rule in inventory['types'].items() if rule['public']})
        tokens = {name: _sha(' '.join(value).encode()) for name, value in inventory['functions'].items()}
        source_gate.typed_equal(tokens, EXPECTED['all_function_tokens_sha256'][path])
    source_gate.typed_equal(public, EXPECTED['public_api'])
    source_gate.typed_equal(types, EXPECTED['opaque_types'])
    for path, rule in EXPECTED['finite_parent_inverse'].items():
        raw = texts[path].encode('utf-8')
        if len(raw) != rule['complete_bytes'] or _sha(raw) != rule['complete_sha256']:
            raise ValueError('P2B current production parent bytes differ')
        parent_source(path, texts[path])

def validate(root=ROOT):
    contract = json.loads(_read(root, CONTRACT))
    check(contract, inputs(root))

def main():
    try:
        validate()
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        print('P2B Source rejected: ' + str(error), file=sys.stderr)
        return 1
    print('P2B Source correspondence accepted; unbound mechanism, no runtime/native qualification')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
