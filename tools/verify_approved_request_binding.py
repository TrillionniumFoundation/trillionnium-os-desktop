#!/usr/bin/env python3
"""Finite source/API correspondence. Actual kernel/Servo execution is separate."""
from pathlib import Path
import hashlib, json, sys
try:
    from .verify_approved_native_startup import rust_inventory, signature, typed_equal, function, require
except ImportError:
    from verify_approved_native_startup import rust_inventory, signature, typed_equal, function, require
ROOT=Path(__file__).resolve().parents[1]
CONTRACT="contracts/approved-request-binding.v1.json"
EXPECTED=json.loads('{"api": {"crates/hepta-browser-actor-simulation/src/approved_rebinding.rs": {"BrowserActor::rebind_approved_request": "pub fn rebind_approved_request(&mut self, request: &ApprovedAgentRequestBinding, session: &ApprovedAgentSession) -> Result<(), AgentPortError>"}, "crates/hepta-browser-actor/src/servo_runtime/approved_binding.rs": {"ServoBrowserActor::from_approved_request": "pub fn from_approved_request(request: &ApprovedAgentRequestBinding, endpoint: ServoRuntimeEndpoint) -> Result<Self, AgentPortError>", "ServoBrowserActor::rebind_approved_request": "pub fn rebind_approved_request(&mut self, request: &ApprovedAgentRequestBinding) -> Result<(), AgentPortError>"}, "crates/hepta-peer-attestation/src/approved_policy/request_binding.rs": {"ApprovedAgentReceivedStream::consume_with_request_binding": "pub fn consume_with_request_binding<T>(self, consumer: impl FnOnce(UnixStream, Instant, ControlRequestCustody, AttestedRetainedReceiver, AttestedPeer, &str, ApprovedAgentRequestBinding) -> T) -> Result<T, ApprovedPolicyError>", "ApprovedAgentRequestBinding::start_session": "pub fn start_session(&self) -> Result<ApprovedAgentSession, ApprovedPolicyError>", "ApprovedAgentRequestBinding::verifier_for_session": "pub fn verifier_for_session(&self, session: &ApprovedAgentSession) -> Result<ApprovedAgentRequestVerifier, ApprovedPolicyError>", "ApprovedAgentRequestBinding::verify_for_session": "pub fn verify_for_session(&self, session: &ApprovedAgentSession) -> Result<(PeerIdentity, PeerRuntimeSnapshot, String), ApprovedPolicyError>", "ApprovedAgentRequestVerifier::ensure_pair_alive_for_session": "pub fn ensure_pair_alive_for_session(&self, session: &ApprovedAgentSession) -> Result<(), ApprovedPolicyError>", "ApprovedAgentRequestVerifier::verify_for_session": "pub fn verify_for_session(&self, session: &ApprovedAgentSession) -> Result<(), ApprovedPolicyError>", "ApprovedAgentRequestVerifier::with_original_pair": "pub fn with_original_pair<T>(&self, session: &ApprovedAgentSession, consumer: impl FnOnce(&ProcfsPeerAttestor, &AttestedPeer, &ControlRequestVerifier, Instant) -> T) -> Result<T, ApprovedPolicyError>"}}, "authority": {"approved_controlled_arguments_supply_authority": false, "approved_controlled_original_pair_from_opaque_verifier": true, "attestor": "ProcfsPeerAttestor_default", "borrowed_pair_keeps_original_nonclone_custody": true, "both_role_entries_equal": true, "caller_principal_or_snapshot_mints_proof": false, "current_original_pair_required_alive": true, "legacy_actor_approval_retrofit": false, "legacy_fixed_pid_unchanged": true, "old_request_peer_required_alive_for_replacement": false, "proof": "consumed_same_approved_original_stream", "selected_fields": 13, "source_drift_irreversible": true, "uncontrolled_approved_actor_dispatch": false}, "documentation": "docs/architecture/APPROVED_REQUEST_BINDING.md", "errors": {"AgentPortError": "Handler refusal, no binding mutation on failed replacement", "ApprovedPolicyError": "original typed process/deadline/source/peer refusal; no recovery or repair", "ProductDispatchError": "PeerRefused/DeadlineExceeded/StorageUnavailable/RecoveryRequired at existing composition gates"}, "evidence": {"actual_native_qualification_pending": true, "callback": "synthetic_source_only", "command": "cargo test --locked --release -p hepta-browserd --test approved_request_binding_kernel", "contract_tests": "tests/test_approved_request_binding.py", "kernel": "apps/hepta-browserd/tests/approved_request_binding_kernel.rs", "kernel_groups": 13, "original_native_six_cases_unchanged": true, "validator": "tools/verify_approved_request_binding.py", "zero_skips_required": true}, "non_claims": {"default_activation_changed": false, "firmware_root_approval": false, "independent_review": false, "installed_persistent_owner": false, "native_Servo_effect": false, "production_ready": false, "sixty_second_health": false}, "opaque_types": ["ApprovedAgentRequestBinding", "ApprovedAgentSession", "ApprovedAgentRequestVerifier"], "platform": "Linux", "preserved_sources": {"apps/hepta-browserd/tests/approved_native_startup_kernel.rs": "0aed2dfaabfd529ddfb21ca1791091c864ad79b4787e42bba23621f625fec365", "apps/hepta-browserd/tests/configured_retained_bootstrap_kernel.rs": "b8417a869e41b9dbf21028613ce754525f6a54aa9fdee90c5358c42afbb10118", "experiments/servo-product-owner/src/approved_connected_tests.rs": "a3acc13594c818caa3b0a2d367bc6ec04bd084120adcd112128efa6ae12758c4", "experiments/servo-product-owner/src/approved_startup.rs": "582242f4826110a81f26fdec3ad497a2eb1dd76fb20d1e7601d95559b3296b25", "experiments/servo-product-owner/src/approved_test_support.rs": "19e1e5269027ab4b81fa4a5ac41517dd6dfea5665141486297f351bf01e4745d", "experiments/servo-product-owner/src/connected_tests.rs": "e22417fdccfadfb0eccaa7d253a7af9ed93f210d739cd16e32e952c29ccb7f5f", "experiments/servo-product-owner/src/native_owner.rs": "5b9d5a3116617f1e4d5f973464e3f5e4c82466f40a98f870f272381b6be685e1"}, "requirements": ["G2"], "schema": "trillionnium.desktop.approved-request-binding.v1", "scope": {"cheap_gate_is_full_attestation": false, "controlled_full_readback_before_runtime": true, "creator_pid_checked": true, "deadline_renewal": false, "first_absolute_instant_preserved": true, "full_exec_readback_before_rebinding": true, "maximum_seconds": 20, "new_deadline_above_first_refused": true, "page_owner_and_receipts_preserved": true, "prepared_active_poisoned_conflict_refused": true, "unknown_after_callback_cannot_rebind": true, "unresolved_history_refused": true}, "sources": ["crates/hepta-peer-attestation/src/approved_policy/request_binding.rs", "crates/hepta-browser-actor/src/servo_runtime/approved_binding.rs", "crates/hepta-browser-actor-simulation/src/approved_rebinding.rs"], "status": "SOURCE_BOUNDED_APPROVED_REQUEST_REPLACEMENT"}')
STATE={
 "ApprovedAgentRequestBinding":"owner_pid:u32,guard:ApprovedGuard,deadline:Instant,peer:PeerIdentity,snapshot:PeerRuntimeSnapshot,original:PeerRequestCustody,control:ControlRequestVerifier,",
 "ApprovedAgentSession":"owner_pid:u32,guard:ApprovedGuard,deadline:Instant,",
 "ApprovedAgentRequestVerifier":"owner_pid:u32,guard:ApprovedGuard,deadline:Instant,original:PeerRequestVerifier,control:ControlRequestVerifier,",
}
def check(value, texts):
    typed_equal(value, EXPECTED)
    for path, apis in EXPECTED["api"].items():
        inventory=rust_inventory(texts[path])
        actual=inventory["public_api"]
        if path==EXPECTED["sources"][2]:
            require(inventory["tokens"],"impl<R: PageRuntime> BrowserActor<R>","generic actor owner")
            actual={key.replace("<::", "BrowserActor::"):value for key,value in actual.items()}
        if set(actual)!=set(apis): raise ValueError("additive public inventory differs")
        for name, declared in apis.items():
            if signature(actual[name])!=signature(declared): raise ValueError("additive signature differs")
    peer=rust_inventory(texts[EXPECTED["sources"][0]])
    if {k for k,v in peer["types"].items() if v["public"]}!=set(STATE): raise ValueError("opaque type inventory differs")
    for name, fields in STATE.items():
        entry=peer["types"][name]
        if "pub" in entry["body"] or signature(" ".join(entry["body"]))!=signature(fields): raise ValueError("opaque state differs")
        items=peer["tokens"]
        position=next(i for i in range(len(items)-2) if items[i:i+3]==["pub","struct",name])-1
        while position>=0 and items[position]=="]":
            end=position; depth=1; position-=1
            while position>=0 and depth:
                depth+=(items[position]=="]")-(items[position]=="["); position-=1
            if "Clone" in items[position+1:end+1]: raise ValueError("opaque scope gains Clone")
            if position>=0 and items[position]=="#": position-=1
    for name in ["ApprovedAgentRequestBinding::verify_for_session","ApprovedAgentRequestVerifier::verify_for_session","ApprovedAgentRequestVerifier::ensure_pair_alive_for_session"]:
        body=function(peer,name)
        for marker in ["remaining(self.owner_pid,self.deadline)?", "remaining(session.owner_pid,session.deadline)?", "session.guard.state.inspect()?", "self.guard.state.inspect()?", "self.deadline > session.deadline", "self.guard.state.entries != session.guard.state.entries"]:
            require(body,marker,name)
    require(function(peer,"ApprovedAgentRequestBinding::verify_current"),"self.control.verify_pair_current(&self.original.verifier())","full own original pair")
    require(function(peer,"ApprovedAgentRequestVerifier::verify_for_session"),"self.control.verify_pair_current(&self.original)","full verifier")
    consume=function(peer,"ApprovedAgentReceivedStream::consume_with_request_binding")
    for marker in ["self.attested.request_custody()", "self.custody.verifier()", "PeerIdentity::from_stream(&self.stream)", "self.consume_before("]: require(consume,marker,"same original stream")
    sim=rust_inventory(texts[EXPECTED["sources"][2]])
    body=function(sim,"<::rebind_approved_request")
    for marker in ["self.ensure_prepared_request_owner()?", "self.runtime_unavailable", "!self.cancellation_tokens.is_empty()", "!self.cancelled_requests.is_empty()", "self.request_authority.borrow().is_some()", "self.control_authority.borrow().is_some()", "PrincipalBinding::bind_attested(self.binding.principal.clone(),peer,&snapshot)"]:
        require(body,marker,"idle replacement")
    full=require(body,"request.verify_for_session(session)","original current verification")
    mutation=require(body,"self.binding = replacement", "sole mechanism mutation")
    if full>=mutation or sum(1 for t in body if t=="verify_for_session")!=2: raise ValueError("replacement observation order differs")
    actor=rust_inventory(texts[EXPECTED["sources"][1]])
    require(function(actor,"ServoBrowserActor::rebind_approved_request"),"self.approved_session.as_ref()","no legacy approval retrofit")
    require(function(actor,"ServoBrowserActor::ensure_approved_request"),".ensure_pair_alive_for_session(session)","scope gate")
    raw=function(actor,"ServoBrowserActor::refuse_uncontrolled_approved_request")
    require(raw,"if self.approved_session.is_some()", "approved raw refusal")
    require(raw,"return Err(", "approved raw refusal")
    facade=rust_inventory(texts["crates/hepta-browser-actor/src/servo_runtime.rs"].split("/// Operation delivered")[0])
    for name in ["handle_attested","preflight_attested"]:
        require(function(facade,"ServoBrowserActor::"+name),"self.refuse_uncontrolled_approved_request()?", "no uncontrolled authority")
    for name in ["handle_attested_controlled","preflight_attested_controlled"]:
        body=function(facade,"ServoBrowserActor::"+name)
        require(body,"self.ensure_approved_request()?", "controlled original scope")
        if name=="preflight_attested_controlled":
            require(body,"self.with_approved_pair(context,", "opaque original source preflight")
            for marker in ["original_attestor","original_attested","original_custodian"]:
                require(body,marker,"no caller original source authority")
        else: require(body,"self.handle_approved_controlled(context, request)", "opaque original source handle")
    for name in ["with_approved_pair","handle_approved_controlled"]:
        body=function(actor,"ServoBrowserActor::"+name)
        require(body,"self.ensure_approved_creator()?", "creating PID before aliases")
        require(body,"context.effective_deadline > ceiling", "no caller time extension")
        require(body,"verifier.with_original_pair(session", "actual opaque source")
    handle=function(actor,"ServoBrowserActor::handle_approved_controlled")
    require(signature(" ".join(handle)),"inner.handle_attested_controlled(context,request,attestor,attested,custodian)", "full private source dispatch")
    require(handle,"self.approved_uncertain = true", "late scope uncertainty latch")
    require(handle,"*uncertain = true", "unwind after possible dispatch stays closed")
    require(handle,"BrowserErrorCode::Indeterminate", "late scope unknown preserved")
    for name in ["rebind_approved_request","ensure_approved_request"]:
        body=function(actor,"ServoBrowserActor::"+name)
        require(body,"self.ensure_approved_creator()?", "creating PID before state")
        require(body,"if self.approved_uncertain", "uncertainty blocks authority")
    scope=function(peer,"ApprovedAgentRequestVerifier::with_original_pair")
    require(scope,"self.original.original_attested_peer()", "original private pidfd source")
    require(scope,"consumer(&ProcfsPeerAttestor::default(), original, &self.control", "original default procfs pair")
    if scope.count("ensure_pair_alive_for_session")!=2: raise ValueError("original borrowed pair scope differs")
    product=rust_inventory(texts["apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs"])
    create=function(product,"ApprovedRetainedProductConnection::from_received")
    require(create,".consume_with_request_binding(", "opaque source transport")
    serve=function(product,"ProductRequestCoordinator::serve_approved_retained_connection")
    for marker in ["connection.principal != self.principal", "self.storage_failed", "self.state != RuntimeState::Ready", "self.pending_reconciliation.is_some()", ".has_unresolved_receipts()", ".rebind_approved_request(&connection.binding)"]:
        require(serve,marker,"coordinator idle/history")
    if require(serve,".rebind_approved_request(&connection.binding)","replacement")>=require(serve,"self.serve_retained_connection(connection.inner)","original terminal serving"): raise ValueError("replacement after dispatch")
    for path, digest in EXPECTED["preserved_sources"].items():
        if hashlib.sha256(texts[path].encode()).hexdigest()!=digest: raise ValueError("preserved native/kernel source differs")
    legacy=rust_inventory(texts["crates/hepta-browser-actor-simulation/src/lib.rs"].split("pub enum PrincipalBindingError")[0])
    fixed=function(legacy,"PrincipalBinding::verify_dispatch_attestation")
    for marker in ["self.verify_dispatch_peer(peer)?", "snapshot.pid", "snapshot.start_time_ticks"]:
        require(fixed,marker,"legacy fixed identity")
def inputs(root=ROOT):
    paths=list(EXPECTED["sources"])+list(EXPECTED["preserved_sources"])+["crates/hepta-browser-actor/src/servo_runtime.rs","apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs","crates/hepta-browser-actor-simulation/src/lib.rs"]
    return {p:(root/p).read_text() for p in paths}
def main():
    try: check(json.loads((ROOT/CONTRACT).read_text()),inputs())
    except (ValueError,KeyError,OSError) as e: print("approved request binding REFUSED: "+str(e),file=sys.stderr); return 1
    print("PASS approved request binding finite correspondence; runtime/native/installed qualification separate"); return 0
if __name__=="__main__": raise SystemExit(main())
