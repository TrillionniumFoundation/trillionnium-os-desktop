#!/usr/bin/env python3
"""Closed source correspondence for constructor-selected immutable callback URL scope.
This bounded inventory neither expands Rust macros nor substitutes for compilation,
native Servo execution, principal approval, installed qualification or release.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys
try:
    from .verify_approved_native_startup import rust_inventory, function, require, tokens, signature, typed_equal, closing
    from .prepare_native_product_owner import read
    from .artifact_evidence import load
except ImportError:
    from verify_approved_native_startup import rust_inventory, function, require, tokens, signature, typed_equal, closing
    from prepare_native_product_owner import read
    from artifact_evidence import load
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/immutable-callback-url-scope.v1.json"
DISPATCH = "crates/hepta-browser-actor-simulation/src/engine_dispatch.rs"
CALLBACK = "crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop.rs"
SERVO = "crates/hepta-browser-actor/src/servo_runtime.rs"
NATIVE = "experiments/servo-product-owner/src/native_owner.rs"
DOCUMENT = "data:text/html,<!DOCTYPE html><title>Immutable owner</title><main><h1>Owned semantic document</h1><p>Read only native Servo page</p></main>"
SIGNATURE = "pub fn closed_immutable_callback_engine_pair<R: CallbackPageRuntime>(runtime: R, waker: Arc<dyn EngineEventLoopWaker>) -> (EngineThreadRuntime, CallbackEngineOwner<R>)"
EXPECTED = {
    "schema": "trillionnium.desktop.immutable-callback-url-scope.v1", "api_version": "0.1.0",
    "status": "SOURCE_FIXED_DOCUMENT_SCOPE_NATIVE_EXECUTION_PENDING",
    "api": {"source": CALLBACK, "name": "closed_immutable_callback_engine_pair", "signature": SIGNATURE,
        "preconditions": ["construct_and_pump_on_creator_engine_thread", "separately_enforce_closed_operation_profile", "preserve_original_live_peer_custody_and_deadline"],
        "result": "noncloneable_actor_endpoint_and_non_send_non_sync_callback_owner",
        "refusals": {"other_reply_url": "Internal_and_pair_retirement", "other_owner_url": "PolicyDenied_before_dispatch", "invalid_owner_token_or_fixture": "PolicyDenied_before_dispatch"}},
    "fixed_document_url": DOCUMENT,
    "empty_document_url": "about:blank",
    "selection": {"caller_url_parameter": False, "caller_capability_parameter": False,
        "existing_engine_and_callback_defaults": "D3Local_about_blank_or_loopback_http",
        "closed_servo_profile": "ClosedImmutableReadOnly_exact_fixed_or_blank_document",
        "propagated_to": ["EngineThreadRuntime", "CallbackEngineOwner", "EngineCompletion"],
        "checked_at": ["actor_preflight", "actor_call", "callback_completion", "callback_owner_poll"]},
    "native_url_source": "actual_owned_WebView_url_not_replaced_by_constant_or_about_blank",
    "qualification": {"synthetic_host_cases": 6, "native_original_cases": 4, "native_approved_cases": 2,
        "unchanged_native_seconds": 5, "unchanged_connection_seconds": 20},
    "non_claims": {"native_execution_passed": False, "installed_activation": False,
        "approved_principal_minted": False, "human_approval": False, "hardware_or_release": False},
}

# Entire control/URL pipelines are a finite lexical source inventory.
BODY_TOKEN_SHA256 = {
    DISPATCH: {
        'engine_thread_pair': '4c8e5ad2a5f7a4ca6a46034778e0b164cfc71761966ddb1aab9abc4a83806c31',
        'EngineThreadRuntime::preflight': '312f45b6369c7aa7c56f14ad72802bc8122d4935a8fb08e8d9d04311ad38deb6',
        'EngineThreadRuntime::call': '4c2a6487f1fc79e1cf530cfee666b527d1c872dc655bcb8d542caad50e450f29',
        '<::pump_one': '8c2c6fc8434e4c6ae0c015b45c6852ad0b6f06ef6134933c26f33546e6ec891a',
    },
    CALLBACK: {
        'EngineCompletion::complete': '3f18a046628bcfc1a34351e1e83e155a742b9dc3d8053095f5ee90035c8e0f9a',
        '<::poll_active': '2a018d7410d8e3f659327367220e8ce4356f1337c003eb4935ebda953c3be594',
        '<::pump_one': '5e0e3b3b900091628602a3b0be45a4d8a2e6b08ed0b033b9a4064dfb68210e4c',
    },
}

def literal_constant(text, name, public):
    pattern = r'(?m)^' + (r'pub ' if public else '') + r'const ' + re.escape(name) + r': &str = ("[^"\n]*");$'
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError("fixed URL constant inventory differs")
    match = matches[0]
    tokens(text[:match.start()])  # Reject a textual match inside a comment/literal.
    if json.loads(match.group(1)) != DOCUMENT:
        raise ValueError("fixed document URL differs")
    expected = (["pub"] if public else []) + ["const", name, ":", "&", "str", "=", ";"]
    items = tokens(text)
    if sum(items[i:i+len(expected)] == expected for i in range(len(items))) != 1:
        raise ValueError("fixed URL declaration differs")

def selected_function(text, name):
    items = tokens(text)
    indexes = [i for i in range(len(items)-1) if items[i:i+2] == ["fn", name]]
    if len(indexes) != 1:
        raise ValueError("selected function inventory differs")
    start = items.index("{", indexes[0])
    end = closing(items, start)
    return items[start+1:end]

def check(contract, dispatch, callback, servo, native):
    typed_equal(contract, EXPECTED)
    literal_constant(dispatch, "CLOSED_IMMUTABLE_DOCUMENT_URL", False)
    literal_constant(native, "IMMUTABLE_DOCUMENT", True)
    base, cb = rust_inventory(dispatch), rust_inventory(callback)
    for path, inventory in [(DISPATCH, base), (CALLBACK, cb)]:
        for name, expected_digest in BODY_TOKEN_SHA256[path].items():
            body = json.dumps(function(inventory, name), ensure_ascii=False, separators=(",", ":")).encode()
            if hashlib.sha256(body).hexdigest() != expected_digest:
                raise ValueError("whole callback/actor/engine URL control pipeline differs: " + name)
    if sorted(base["public_api"]) != ["<::pump_one", "engine_thread_pair"]:
        raise ValueError("original engine public API inventory differs")
    scope = base["types"].get("EngineUrlScope")
    if scope != {"kind": "enum", "body": ["D3Local", ",", "ClosedImmutableReadOnly", ","], "public": False}:
        raise ValueError("URL scope is not the closed private selection")
    if function(base, "EngineUrlScope::allows") != tokens('match self { Self::D3Local => url == "about:blank" || crate::is_loopback_http(url), Self::ClosedImmutableReadOnly => { url == CLOSED_IMMUTABLE_DOCUMENT_URL || url == "about:blank" } }'):
        raise ValueError("constructor URL selection differs")
    # tokens() deliberately discards literals; bind the new blank value as well.
    closed_marker = 'Self::ClosedImmutableReadOnly => {\n                url == CLOSED_IMMUTABLE_DOCUMENT_URL || url == "about:blank"\n            }'
    if dispatch.count(closed_marker) != 1:
        raise ValueError("closed fixed/blank document literal predicate differs")
    tokens(dispatch[:dispatch.index(closed_marker)])
    marker = 'Self::D3Local => url == "about:blank" || crate::is_loopback_http(url),'
    if dispatch.count(marker) != 1:
        raise ValueError("original D3 blank/local predicate differs")
    tokens(dispatch[:dispatch.index(marker)])
    expected_api = ["<::next_wake_deadline", "<::pump_one", "<::retire", "EngineCompletion::complete", "EngineCompletion::deadline", "EngineCompletion::ensure_active", "EngineCompletion::ensure_current_peer", "EngineCompletion::request_id", "callback_engine_pair", "closed_immutable_callback_engine_pair"]
    if sorted(cb["public_api"]) != expected_api or signature(cb["public_api"]["closed_immutable_callback_engine_pair"]) != signature(SIGNATURE):
        raise ValueError("immutable callback public API inventory/signature differs")
    for inv, owner in [(base, "EngineThreadRuntime"), (cb, "CallbackEngineOwner"), (cb, "EngineCompletion")]:
        body = inv["types"][owner]["body"]
        require(body, "url_scope: EngineUrlScope", "opaque selected URL scope")
        if "pub" in body:
            raise ValueError("URL scope owner fields became public")
    require(function(base, "engine_thread_pair"), "url_scope: EngineUrlScope::D3Local", "original engine default")
    for name, scope_name in [("callback_engine_pair", "D3Local"), ("closed_immutable_callback_engine_pair", "ClosedImmutableReadOnly")]:
        if function(cb, name) != tokens(f"callback_pair(runtime, waker, EngineUrlScope::{scope_name})"):
            raise ValueError("callback constructor-selected scope differs")
    if function(base, "EngineThreadRuntime::preflight")[-len(tokens("validate_owner(owner, self.url_scope)")):] != tokens("validate_owner(owner, self.url_scope)"):
        raise ValueError("actor preflight scope missing")
    require(function(base, "EngineThreadRuntime::call"), "validate_owner(owner, self.url_scope)?", "actor call scope")
    if function(base, "validate_owner") != tokens('''
        if let Some(owner) = owner {
            let valid = owner.local_fixture_only
                && crate::validate_token("session_id", &owner.session_id, 128).is_ok()
                && crate::validate_token("webview_token", &owner.webview_token, 128).is_ok()
                && scope.allows(&owner.current_url);
            if !valid { return Err(RuntimeFailure::PolicyDenied("invalid or non-local D3 engine owner",)); }
        }
        Ok(())
    '''):
        raise ValueError("owner URL or identity guard differs")
    reply_guard = function(base, "bound_reply")
    if reply_guard[:reply_guard.index("{")] != tokens("if reply.current_url.as_ref().is_some_and(|url| !scope.allows(url))"):
        raise ValueError("reply URL refusal guard differs")
    for name in ["EngineCompletion::complete", "<::poll_active"]:
        require(function(cb, name), ".and_then(|reply| bound_reply(reply, self.url_scope))", "callback scope")
    if function(cb, "callback_pair") != tokens('''
        let (sender, receiver) = mpsc::sync_channel(ENGINE_PENDING_LIMIT);
        let closed = Arc::new(AtomicBool::new(false));
        let owner_thread = thread::current().id();
        (EngineThreadRuntime { sender, closed: closed.clone(), owner_thread,
            waker: waker.clone(), url_scope, },
         CallbackEngineOwner { receiver, runtime, active: None, closed, waker,
            owner_thread, retired: false, url_scope, _thread_affinity: PhantomData, },)
    '''):
        raise ValueError("callback endpoints do not share the selected scope")
    require(function(cb, "<::pump_one"), "url_scope: self.url_scope", "completion scope propagation")
    selected = selected_function(servo, "runtime_pair")
    if selected != tokens('''
        let state = Rc::new(RefCell::new(ServoCommandState::default()));
        let bridge = ServoCommandBridge { state: state.clone(), };
        let waker = Arc::new(ServoWakerAdapter(waker));
        let (endpoint, owner) = match profile {
            ServoProfile::ExistingSemanticBridge => callback_engine_pair(bridge, waker),
            ServoProfile::ClosedImmutableReadOnly => { closed_immutable_callback_engine_pair(bridge, waker) }
        };
        (ServoRuntimeEndpoint { inner: endpoint, profile, },
         ServoRuntimeOwner { inner: owner, state, },)
    '''):
        raise ValueError("actual Servo profile selector or endpoint ownership differs")
    require(selected_function(native, "finish_ready"), "self.view.as_ref().and_then(|v| v.url()).map(|url| url.to_string())", "actual native URL correspondence")

def validate(root=ROOT):
    read_source = lambda path: read(root / path).decode("utf-8", "strict")
    check(load(root / CONTRACT), read_source(DISPATCH), read_source(CALLBACK), read_source(SERVO), read_source(NATIVE))
    return {"source_contract": "PASS", "native_execution": "PENDING", "installed_activation": False}

def main():
    try:
        print(json.dumps(validate(), sort_keys=True)); return 0
    except (ValueError, OSError, UnicodeError) as error:
        print("immutable callback URL scope refused: " + str(error), file=sys.stderr); return 1
if __name__ == "__main__": raise SystemExit(main())
