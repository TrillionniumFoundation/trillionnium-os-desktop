"""Host-only boundary controls; no Main, native CLI, APK or runtime guard entry."""
import sys
sys.dont_write_bytecode=True
import importlib.util, io, json, os, tempfile, types, unittest
from pathlib import Path
BASE=Path(__file__).parent
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,BASE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
m=load("installer_under_host_control","install_successor_native.py")
core=load("frozen_pure_helpers","reference_core.py")
class InstallerBoundaries(unittest.TestCase):
    def request(self):
        return {"schema":"pocket4-successor-single-native-upgrade-v1","guard":{},"app_scope":{},
                "package":"com.sdu.didi.psnger","official_verifier":{},"verifier_terminal":{},
                "output_root":"UNBOUND","coordination":{"unresolved_native_install_jobs":[],"single_coordinator":True}}
    def test_request_denies_unreviewed_package_and_unresolved_install(self):
        r=self.request();m.validate_request(r)
        r["package"]="com.sankuai.meituan.takeoutnew"
        with self.assertRaisesRegex(m.Rejected,"REVIEWED_PACKAGE"):m.validate_request(r)
        r=self.request();r["coordination"]["unresolved_native_install_jobs"]=["unknown"]
        with self.assertRaisesRegex(m.Rejected,"NO_UNSETTLED"):m.validate_request(r)
        r=self.request();r["allow_grants"]=True
        with self.assertRaisesRegex(m.Rejected,"CLOSED_INSTALL"):m.validate_request(r)
    def test_user_data_paths_have_actual_data_prefix_and_closed_user(self):
        self.assertEqual(m.user_data_path("user","com.sdu.didi.psnger"),"/data/user/0/com.sdu.didi.psnger")
        self.assertEqual(m.user_data_path("user_de","ctrip.android.view"),"/data/user_de/0/ctrip.android.view")
        for kind in ("data/user","../user","user/1","user_ce"):
            with self.assertRaisesRegex(m.Rejected,"CLOSED_USER_DATA"):m.user_data_path(kind,"ctrip.android.view")
    def test_final_receipt_failure_retains_attempted_install_unknown(self):
        def fail(*args):raise OSError(28,"owned-fixture simulated receipt failure")
        fake=types.SimpleNamespace(write_new=fail)
        result={"errors":[],"action_attempted":True,"install_verified":True,"outcome_unknown":False}
        got=m.publish_final_receipt(fake,types.SimpleNamespace(path="/UNUSED"),result)
        self.assertTrue(got["action_attempted"] and got["outcome_unknown"])
        self.assertFalse(got["install_verified"])
        self.assertEqual(got["status"],"INSTALL_OUTCOME_UNKNOWN_NO_RETRY")
        self.assertEqual(got["errors"][0]["phase"],"final_receipt")
    def test_pre_action_receipt_failure_does_not_invent_install(self):
        def fail(*args):raise OSError(28,"owned-fixture simulated receipt failure")
        result={"errors":[],"action_attempted":False,"install_verified":False,"outcome_unknown":False}
        got=m.publish_final_receipt(types.SimpleNamespace(write_new=fail),types.SimpleNamespace(path="/UNUSED"),result)
        self.assertFalse(got["action_attempted"] or got["outcome_unknown"] or got["install_verified"])
        self.assertEqual(got["status"],"REJECTED_BEFORE_INSTALL")
    def test_actual_private_empty_output_copy_and_exclusive_write(self):
        before=len(os.listdir("/proc/self/fd"))
        pool=core.FDs()
        try:
            with tempfile.TemporaryDirectory(prefix="owned-store-",dir=BASE) as d:
                os.chmod(d,0o700)
                store=m.Store.__new__(m.Store)
                store.core,store.pool,store.path=core,pool,d
                store.fd=core.open_host(pool,d,os.O_RDONLY|os.O_DIRECTORY)
                store.identity=core.metadata(store.fd)
                pin=store.write("empty.stderr",b"")
                self.assertEqual(pin["bytes"],0);self.assertEqual(core.pinned_record(pin),b"")
                with self.assertRaises(FileExistsError):store.write("empty.stderr",b"replacement")
                input_path=Path(d)/"owned-fixture.bin"
                input_path.write_bytes(b"public test copy");os.chmod(input_path,0o400)
                f=core.open_host(pool,str(input_path));raw=b"public test copy"
                copied,pin=store.copy("copy.bin",f,{"bytes":len(raw),"sha256":m.sha(raw)},m.Budget())
                os.lseek(copied,0,os.SEEK_SET)
                self.assertEqual(core.read_fd(copied,64,m.time.monotonic()+2,True),raw)
                self.assertEqual(pin["sha256"],m.sha(raw))
                with self.assertRaisesRegex(m.Rejected,"COPY_SOURCE_BYTES"):store.copy("bad-copy.bin",f,{"bytes":len(raw),"sha256":"0"*64},m.Budget())
                pool.close_all()
        finally:
            pool.close_all()
        self.assertEqual(pool.summary()["acquired"],pool.summary()["closed"])
        self.assertEqual(len(os.listdir("/proc/self/fd")),before)
    def test_root_request_pin_symlink_and_content_replacement_are_rejected(self):
        before=len(os.listdir("/proc/self/fd"))
        with tempfile.TemporaryDirectory(prefix="owned-bootstrap-",dir=BASE) as d:
            p=Path(d)/"request.json";raw=b'{"st_mtime_ns":1793961899814391132}\n'
            p.write_bytes(raw);os.chmod(p,0o400)
            pin={"path":str(p),"bytes":len(raw),"sha256":m.sha(raw)}
            self.assertEqual(m.read_bootstrap(pin,1024),raw)
            link=Path(d)/"link.json";link.symlink_to(p)
            with self.assertRaises(OSError):m.read_bootstrap({**pin,"path":str(link)},1024)
            replacement=Path(d)/"replacement.json";replacement.write_bytes(raw.replace(b"1132",b"1133"));os.chmod(replacement,0o400)
            os.replace(replacement,p)
            with self.assertRaisesRegex(m.Rejected,"BOOTSTRAP_PIN"):m.read_bootstrap(pin,1024)
        self.assertEqual(len(os.listdir("/proc/self/fd")),before)
    def test_native_response_owner_is_required_even_for_rc_zero(self):
        cmd={"spawned":True,"joined":True,"returncode":0,"timed_out":False,"output_capture_complete":True}
        data={"ok":True,"state":"running","host_pid":12345}
        self.assertEqual(m.response(core,m.canonical(data),cmd,12345),data)
        with self.assertRaisesRegex(m.Rejected,"NATIVE_RESPONSE_OWNER"):m.response(core,m.canonical(data),cmd,12346)
        data["outcome_unknown"]=True
        with self.assertRaisesRegex(m.Rejected,"NATIVE_RESPONSE_OWNER"):m.response(core,m.canonical(data),cmd,12345)
if __name__=="__main__":unittest.main(verbosity=2)
