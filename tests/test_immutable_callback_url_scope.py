"""Closed scope correspondence/mutations, never actual native or approval evidence."""
import copy
from pathlib import Path
import unittest
from tools import verify_immutable_callback_url_scope as v
ROOT = Path(__file__).resolve().parents[1]
class ImmutableCallbackUrlScopeTests(unittest.TestCase):
    def inputs(self):
        return {"contract": v.load(ROOT / v.CONTRACT), **{name: (ROOT / path).read_text() for name,path in [("dispatch",v.DISPATCH),("callback",v.CALLBACK),("servo",v.SERVO),("native",v.NATIVE)]}}
    def denied(self, group, changes):
        original=self.inputs()
        for before,after in changes:
            with self.subTest(group=group,before=before):
                self.assertIn(before,original[group]); changed=dict(original)
                changed[group]=original[group].replace(before,after,1)
                with self.assertRaises(ValueError):v.check(**changed)
    def test_actual_closed_contract_and_literal_typed_signature(self):
        v.check(**self.inputs());self.assertEqual(v.validate(ROOT)["native_execution"],"PENDING")
    def test_contract_unknown_fields_exact_types_and_claims_refuse(self):
        data=self.inputs()
        for path,key,value in [("selection","caller_url_parameter",True),("selection","caller_capability_parameter",0),("non_claims","native_execution_passed",True),("api","signature",v.SIGNATURE+' extra')]:
            changed=dict(data);changed["contract"]=copy.deepcopy(data["contract"]);changed["contract"][path][key]=value
            with self.subTest(path=path,key=key):
                with self.assertRaises(ValueError):v.check(**changed)
        changed=dict(data);changed["contract"]=copy.deepcopy(data["contract"]);changed["contract"]["unknown"]=False
        with self.assertRaises(ValueError):v.check(**changed)
    def test_public_constructor_cannot_take_url_or_capability_argument(self):
        self.denied("callback",[("pub fn closed_immutable_callback_engine_pair<R: CallbackPageRuntime>(","pub fn caller_url_callback_engine_pair<R: CallbackPageRuntime>("),("    runtime: R,\n    waker: Arc<dyn EngineEventLoopWaker>,\n) -> (EngineThreadRuntime, CallbackEngineOwner<R>) {\n    callback_pair(runtime, waker, EngineUrlScope::ClosedImmutableReadOnly)","    runtime: R,\n    caller_url: String,\n    waker: Arc<dyn EngineEventLoopWaker>,\n) -> (EngineThreadRuntime, CallbackEngineOwner<R>) {\n    callback_pair(runtime, waker, EngineUrlScope::ClosedImmutableReadOnly)")])
    def test_private_closed_scope_and_existing_defaults_cannot_widen(self):
        self.denied("dispatch",[("enum EngineUrlScope {","pub enum EngineUrlScope {"),("ClosedImmutableReadOnly,\n}","ClosedImmutableReadOnly,\n    CallerSelected,\n}"),("Self::ClosedImmutableReadOnly => url == CLOSED_IMMUTABLE_DOCUMENT_URL","Self::ClosedImmutableReadOnly => crate::is_loopback_http(url)"),("url_scope: EngineUrlScope::D3Local","url_scope: EngineUrlScope::ClosedImmutableReadOnly")])
        self.denied("callback",[("callback_pair(runtime, waker, EngineUrlScope::D3Local)","callback_pair(runtime, waker, EngineUrlScope::ClosedImmutableReadOnly)"),("callback_pair(runtime, waker, EngineUrlScope::ClosedImmutableReadOnly)","callback_pair(runtime, waker, EngineUrlScope::D3Local)")])
    def test_callback_completion_poll_and_constructor_scope_cannot_detach(self):
        self.denied("callback",[("bound_reply(reply, self.url_scope)","bound_reply(reply, EngineUrlScope::D3Local)"),("url_scope: self.url_scope","url_scope: EngineUrlScope::D3Local"),("            url_scope,","            url_scope: EngineUrlScope::D3Local,")])
        original=self.inputs(); marker="bound_reply(reply, self.url_scope)";self.assertEqual(original["callback"].count(marker),2)
        for index in [0,1]:
            # Construct the selected occurrence explicitly without changing the other guard.
            changed=dict(original)
            position=original["callback"].find(marker) if index==0 else original["callback"].rfind(marker)
            changed["callback"]=original["callback"][:position]+"bound_reply(reply, EngineUrlScope::D3Local)"+original["callback"][position+len(marker):]
            with self.subTest(index=index):
                with self.assertRaises(ValueError):v.check(**changed)
    def test_actor_owner_reply_and_native_profile_scope_guards_cannot_disappear(self):
        self.denied("dispatch",[("validate_owner(owner, self.url_scope)","Ok(())"),("scope.allows(&owner.current_url)","true"),("scope.allows(&owner.current_url)","scope.allows(&owner.current_url) || true"),(".is_some_and(|url| !scope.allows(url))",".is_some_and(|url| false)"),(".is_some_and(|url| !scope.allows(url))",".is_some_and(|url| !scope.allows(url)) && false")])
        self.denied("servo",[("ServoProfile::ClosedImmutableReadOnly => {\n            closed_immutable_callback_engine_pair(bridge, waker)\n        }","ServoProfile::ClosedImmutableReadOnly => {\n            callback_engine_pair(bridge, waker)\n        }")])
    def test_exact_constant_literal_cannot_be_faked_by_comments(self):
        for group,name in [("dispatch","CLOSED_IMMUTABLE_DOCUMENT_URL"),("native","IMMUTABLE_DOCUMENT")]:
            data=self.inputs();data[group]=data[group].replace(v.DOCUMENT,"data:text/html,other",1)
            with self.subTest(group=group):
                with self.assertRaises(ValueError):v.check(**data)
                data[group]+='\n/*\n'+('pub ' if group=="native" else '')+'const '+name+': &str = "'+v.DOCUMENT+'";\n*/\n'
                with self.assertRaises(ValueError):v.check(**data)
    def test_native_result_preserves_actual_view_url(self):
        self.denied("native",[(".and_then(|v| v.url())",".map(|_| immutable_url())"),(".map(|url| url.to_string())",".map(|_| \"about:blank\".to_owned())")])
if __name__=='__main__':unittest.main()
