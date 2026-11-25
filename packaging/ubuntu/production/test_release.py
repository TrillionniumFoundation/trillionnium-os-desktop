#!/usr/bin/python3
"""Source-bound admission boundaries; no live host configuration is changed."""
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
spec=importlib.util.spec_from_file_location("release",Path(__file__).with_name("release.py"))
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
sys.modules.setdefault("release",release)
class Admission(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="droidloom-release-");self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def file(self,name="input",data=b"public",mode=0o444):
        path=self.root/name;path.write_bytes(data);path.chmod(mode);return path
    def test_duplicate_receipt_field_is_rejected(self):
        with self.assertRaises(release.Rejected):release.json_bytes(b'{"sha256":"a","sha256":"b"}')
    def test_alias_components_are_rejected(self):
        for value in ("../x","a/../x","a//x","/absolute","a/./x","a\\x"):
            with self.subTest(value=value),self.assertRaises(release.Rejected):release.safe_relative(value)
    def test_symlink_and_hardlink_sources_are_rejected(self):
        source=self.file();link=self.root/"link";link.symlink_to(source)
        with self.assertRaises(OSError):
            with release.held(link):pass
        link.unlink();os.link(source,link)
        with self.assertRaises(release.Rejected):
            with release.held(source):pass
    def test_intermediate_symlink_is_rejected(self):
        directory=self.root/"real";directory.mkdir();(directory/"leaf").write_bytes(b"x")
        (self.root/"alias").symlink_to(directory)
        with self.assertRaises(OSError):
            with release.held(self.root/"alias/leaf"):pass
    def test_original_named_inode_replacement_is_rejected(self):
        source=self.file()
        with self.assertRaises(release.Rejected):
            with release.held(source):
                replacement=self.file("replacement");os.replace(replacement,source)
    def test_original_content_change_is_rejected(self):
        source=self.file(mode=0o644)
        with self.assertRaises(release.Rejected):
            with release.held(source):source.write_bytes(b"mutated")
    def test_world_writable_and_setuid_sources_are_rejected(self):
        for mode in (0o666,0o4755):
            source=self.file(str(mode),mode=mode)
            with self.subTest(mode=mode),self.assertRaises(release.Rejected):
                with release.held(source):pass
    def test_grub_mutability_cannot_be_requested_for_other_file(self):
        source=self.file()
        with self.assertRaises(release.Rejected):
            with release.held(source,root=True,mutable_grub=True):pass
    def test_copy_is_original_and_create_only(self):
        source=self.file(data=bytes(range(256))*1000);pin=release.file_pin(source)
        target=self.root/"copy";release.copy_pin(pin,target,0o444)
        self.assertEqual(target.read_bytes(),source.read_bytes());self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o444)
        with self.assertRaises(FileExistsError):release.copy_pin(pin,target,0o444)
    def test_wrong_pin_never_creates_output(self):
        source=self.file();pin=release.file_pin(source);pin["sha256"]="0"*64;target=self.root/"copy"
        with self.assertRaises(release.Rejected):release.copy_pin(pin,target,0o444)
        self.assertFalse(target.exists())
    def test_fixed_process_output_bound_retires_original(self):
        with self.assertRaises(release.Rejected):
            release.bounded_process([sys.executable,"-c","import os;os.write(1,b'x'*8192)"],maximum=1024)
        with self.assertRaises(ChildProcessError):os.waitpid(-1,os.WNOHANG)
    def test_fixed_process_deadline_retires_original(self):
        before=time.monotonic()
        with self.assertRaises(release.Rejected):
            release.bounded_process([sys.executable,"-c","import time;time.sleep(30)"],seconds=1)
        self.assertLess(time.monotonic()-before,6)
        with self.assertRaises(ChildProcessError):os.waitpid(-1,os.WNOHANG)
    def test_only_reviewed_host_template_has_at_exception(self):
        leaf=release.HOST_ACL_MEMBER
        self.assertEqual(release.safe_host_relative(leaf),leaf)
        with self.assertRaises(release.Rejected):release.safe_relative(leaf)
        for candidate in (leaf+"x",leaf.replace("runtime-dir@","other@"),"usr/bin/a@b",leaf.replace("50-","../50-")):
            with self.subTest(candidate=candidate),self.assertRaises(release.Rejected):
                release.safe_host_relative(candidate)
        self.assertEqual(release.safe_host_absolute(str(self.root/leaf)),self.root/leaf)
        with self.assertRaises(release.Rejected):
            release.safe_host_absolute(str(self.root/"a@b"/leaf))
    def test_native_lsm_selects_only_selinux_and_rejects_malformed_or_denied(self):
        from unittest.mock import patch
        import ctypes
        import errno
        class Call:
            def __init__(self,case):self.case=case;self.calls=0
            def __call__(self,nr,attr,context,size,flags):
                self.calls+=1;value=context._obj;bound=size._obj
                if (nr.value,attr.value,value.id,flags.value)!=(459,100,101,1):
                    raise AssertionError("native selector changed")
                body=release.CONTEXT+bytes([0])
                value.context_length=len(body);value.length=(32+len(body)+7)&~7;bound.value=value.length
                for i,b in enumerate(body):value.data[i]=b
                if self.case=="denied":
                    ctypes.set_errno(errno.EACCES);return -1
                if self.case=="provider":value.id=104
                if self.case=="flags":value.flags=1
                if self.case=="size":bound.value+=1
                if self.case=="length":value.context_length=257
                if self.case=="terminator":value.data[len(body)-1]=1
                if self.case=="embedded-nul":value.data[3]=0
                if self.case=="padding":value.data[len(body)]=1
                return 0 if self.case=="count" else 1
        for case in ("valid","denied","provider","flags","size","length","terminator","embedded-nul","padding","count"):
            call=Call(case);library=type("Library",(),{})();library.syscall=call
            with self.subTest(case=case),patch.object(release.ctypes,"CDLL",return_value=library):
                if case=="valid":self.assertEqual(release.selinux_current(),release.CONTEXT)
                elif case=="denied":
                    with self.assertRaises(OSError) as result:release.selinux_current()
                    self.assertEqual(result.exception.errno,errno.EACCES)
                else:
                    with self.assertRaises(release.Rejected):release.selinux_current()
                self.assertEqual(call.calls,1)
    def test_successful_original_process_is_reaped(self):
        actual=release.bounded_process([sys.executable,"-c","print('original')"])
        self.assertEqual((actual["exit"],actual["stdout"]),(0,b"original\n"))
        with self.assertRaises(ChildProcessError):os.waitpid(-1,os.WNOHANG)
    def systemd_status(self,version):
        return ("\n\n".join("Package: "+name+"\nVersion: "+version+
            "\nArchitecture: amd64\nStatus: install ok installed\nSource: systemd"
            for name in sorted(release.SYSTEMD_FAMILY))+"\n").encode()
    def test_systemd_tool_phase_is_selected_by_actual_kernel_context_and_complete_family(self):
        old=self.systemd_status(release.SYSTEMD_ORIGINAL_VERSION)
        new=self.systemd_status(release.SYSTEMD_CANDIDATE_VERSION)
        self.assertEqual(release.systemd_phase(release.ORIGINAL_KERNEL,status=old),"original-cold")
        self.assertEqual(release.systemd_phase(release.ORIGINAL_KERNEL,status=new),"candidate-cold")
        self.assertEqual(release.cold_systemd_version(new+b"\nPackage: unrelated\nConffiles:\n"),
                         release.SYSTEMD_CANDIDATE_VERSION)
        self.assertEqual(release.systemd_phase(release.KERNEL,release.CONTEXT),"candidate-shared-runtime")
        for kernel,context,status in (("other",None,new),(release.KERNEL,b"unconfined",None),
                (release.KERNEL,release.CONTEXT,old),(release.ORIGINAL_KERNEL,release.CONTEXT,new),
                (release.ORIGINAL_KERNEL,None,None)):
            with self.subTest(kernel=kernel,context=context),self.assertRaises(release.Rejected):
                release.systemd_phase(kernel,context,status)
    def test_incomplete_mixed_or_unconfigured_systemd_family_cannot_choose_a_tool_pair(self):
        valid=self.systemd_status(release.SYSTEMD_CANDIDATE_VERSION)
        changes=(b"",valid.replace(release.SYSTEMD_CANDIDATE_VERSION.encode(),
                    release.SYSTEMD_ORIGINAL_VERSION.encode(),1),
                 valid.replace(b"install ok installed",b"install ok unpacked",1),
                 valid.replace(b"Architecture: amd64",b"Architecture: arm64",1),
                 valid.replace(b"Source: systemd",b"Source: other",1),
                 valid.replace(b"Version: ",b"Version: 3rd-",1),
                 valid+b"\n"+valid.split(b"\n\n")[0],valid.split(b"\n\n",1)[1])
        for changed in changes:
            with self.subTest(changed=changed[:120]),self.assertRaises(release.Rejected):
                release.cold_systemd_version(changed)
    def test_candidate_shared_phase_selects_only_candidate_pair_without_reading_package_database(self):
        from unittest.mock import patch
        kernel=type("Kernel",(),{"release":release.KERNEL})()
        with patch.object(release.os,"uname",return_value=kernel),\
             patch.object(release,"selinux_current",return_value=release.CONTEXT),\
             patch.object(release.Path,"read_bytes",return_value=b"1\n"),\
             patch.object(release,"held",side_effect=AssertionError("shared role must not read dpkg")):
            for name in ("systemctl","journalctl"):
                with release.fixed_tool(name) as pin:
                    self.assertEqual(pin,release.SYSTEMD_CANDIDATE_TOOLS[name])
                    self.assertNotEqual(pin,release.TOOLS[name])
        with patch.object(release.os,"uname",return_value=kernel),\
             patch.object(release,"selinux_current",return_value=release.CONTEXT),\
             patch.object(release.Path,"read_bytes",return_value=b"0\n"):
            with self.assertRaises(release.Rejected):
                with release.fixed_tool("systemctl"):pass
    def test_apparmor_source_comment_adjustment_cannot_hide_script_or_config_changes(self):
        import native_release as native
        before=("# Automatically added by dh_apparmor/"+native.core.OLD["apparmor"]+"\n").encode()
        after=("# Automatically added by dh_apparmor/"+native.core.NEW["apparmor"]+"\n").encode()
        body=before+b"echo original\n"+before
        old={"postinst":body,"postrm":body,"conffiles":b"/etc/apparmor/parser.conf\n"}
        new={**old,"postinst":body.replace(before,after),"postrm":body.replace(before,after)}
        native.apparmor_scripts(old,new)
        for changed in ({**new,"postinst":new["postinst"].replace(b"echo original",b"echo changed")},
                        {**new,"postrm":new["postrm"]+after},
                        {**new,"conffiles":b"/etc/other\n"}):
            with self.assertRaises(release.Rejected):native.apparmor_scripts(old,changed)
    def test_native_recovery_does_not_require_a_completed_application_or_package_phase(self):
        import cold_native as native
        from unittest.mock import patch
        deployment="a"*64;component="b"*64
        with patch.object(native,"original_cold_context") as context,\
             patch.object(native,"original_cold_authority",side_effect=AssertionError("mixed dpkg is the recovery input")),\
             patch.object(native,"actual_acceptance_binding",side_effect=AssertionError("recovery is not activation")),\
             patch.object(native,"verify_bundle",return_value=({},None,{},None)):
            self.assertEqual(native.physical_inputs(deployment,component,"rollback"),
                Path("/var/lib/droidloom-maintenance/releases")/deployment/"native")
            context.assert_called_once_with()
        with patch.object(native,"original_cold_authority"),\
             patch.object(native,"verify_bundle",return_value=({"schema":"old"},None,{str(i):{} for i in range(15)},None)),\
             patch.object(native,"actual_acceptance_binding",side_effect=AssertionError("incomplete family")):
            with self.assertRaises(release.Rejected):native.physical_inputs(deployment,component,"apply")
    def test_original_native_profile_preserves_the_full_installed_source_family(self):
        import native_release as native
        roles=[]
        for role in native.core.ROLES:
            roles.append({"name":native.core.NAMES[role],"source":native.core.PROJECTS[role],
                          "old_version":native.core.OLD[role]})
        roles.append({"name":"apparmor","source":"apparmor","old_version":native.core.OLD["apparmor"]})
        roles.extend({"name":name,"source":"systemd","old_version":native.systemd.OLD} for name in native.systemd.NAMES)
        for name in native.ORIGINAL_EXTRAS:
            source,version,arch=native.original_extra_identity(name,"old")
            roles.append({"name":name,"source":source,"old_version":version})
        rows=["Package: "+r["name"]+"\nSource: "+r["source"]+"\nVersion: "+r["old_version"]+
              "\nArchitecture: "+("all" if r["name"]=="systemd-dev" else "amd64")+
              "\nStatus: install ok installed" for r in roles]
        rows.extend("Package: unrelated-"+str(i)+"\nStatus: deinstall ok config-files" for i in range(2391-len(rows)))
        raw=("\n\n".join(rows)+"\n").encode()
        native.original_profile_status(raw,roles)
        changes=(raw.replace(b"Architecture: all",b"Architecture: amd64"),
                 raw.replace(b"Version: 3.9-4build1",b"Version: 3.9-4build1+other",1),
                 raw.replace(b"Status: install ok installed",b"Status: install ok unpacked",1),
                 raw.replace(b"Source: libselinux",b"Source: unrelated",1),
                 b"\n\n".join(raw.split(b"\n\n")[1:]),raw+b"\n"+rows[0].encode(),
                 raw.replace(b"Package: unrelated-0\n",b"Package: unrelated-0\nSource: systemd\nVersion: old\nArchitecture: amd64\n").replace(
                     b"Status: deinstall ok config-files",b"Status: install ok installed",1))
        for changed in changes:
            with self.subTest(changed=changed[:80]),self.assertRaises(release.Rejected):
                native.original_profile_status(changed,roles)
        with self.assertRaises(release.Rejected):native.original_profile_status(raw,roles[:-1])
    def test_physical_native_profile_cannot_be_replaced_by_fixture_count_or_unbounded_count(self):
        import cold_native as native
        from unittest.mock import patch
        cases=((native.FULL_SCHEMA,16),(native.FULL_SCHEMA,22),(native.ORIGINAL_SCHEMA,21),(native.ORIGINAL_SCHEMA,23))
        for schema,count in cases:
            with self.subTest(schema=schema,count=count),patch.object(native,"original_cold_authority"),\
                 patch.object(native,"verify_bundle",return_value=({"schema":schema},None,{str(i):{} for i in range(count)},None)),\
                 patch.object(native,"actual_acceptance_binding",side_effect=AssertionError("inexact family must be rejected first")):
                with self.assertRaises(release.Rejected):native.physical_inputs("a"*64,"b"*64,"apply")
    def test_native_all_architecture_is_not_rewritten_to_amd64(self):
        import cold_native as native
        tx=object.__new__(native.NativeTransaction);tx.roles=("systemd-dev",)
        tx.names={"systemd-dev":"systemd-dev"};tx.arch={"systemd-dev":"all"}
        rows={"systemd-dev":{"version":"old","status":"ii "}}
        self.assertEqual(tx.package_rows(rows)["systemd-dev"],("systemd-dev",rows["systemd-dev"]))
        for invalid in ({"systemd-dev:amd64":rows["systemd-dev"]},
                        {**rows,"systemd-dev:all":rows["systemd-dev"]}):
            with self.assertRaises(release.Rejected):tx.package_rows(invalid)
        args=[];tx.remaining_roles=lambda kind:tx.roles
        tx.run_dpkg=lambda stage,argv:args.append(argv)
        tx.configure("new");self.assertEqual(args,[["--configure","systemd-dev:all"]])
    def test_native_recovery_reads_only_fixed_inactive_units_with_the_exact_saved_tool(self):
        import cold_native as native
        import contextlib
        import hashlib
        from unittest.mock import patch
        path=self.file("systemctl",b"fixed normal candidate",0o755)
        @contextlib.contextmanager
        def opened(*args,**kwargs):
            self.assertEqual(args[0],"/usr/bin/systemctl")
            with path.open("rb") as handle:yield handle.fileno(),os.fstat(handle.fileno())
        tx=object.__new__(native.NativeTransaction)
        tx.root=Path("/");tx.snapshot={};tx.attempt=Path("/saved");tx.root_identity=[1,2]
        tx.roles=("systemd",)
        row={"type":"0","mode":0o755,"uid":0,"gid":0,"bytes":path.stat().st_size,
             "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
        tx.payloads={"systemd":{kind:{"payload":{"usr/bin/systemctl":{**row,"sha256":sha}}}
            for kind,sha in (("old","0"*64),("new",row["sha256"]))}}
        events=[];tx.event=lambda *args,**kwargs:events.append((args,kwargs))
        with patch.object(native,"original_cold_context",return_value={"root_identity":[1,2]}),\
             patch.object(native,"held",side_effect=opened),\
             patch.object(native,"_fixed_command",return_value={"exit":0,"stdout":b"inactive\n"}) as command:
            tx.cold_recovery_authority()
            self.assertEqual(command.call_count,len(native.COLD_OWNER_UNITS))
            for call,unit in zip(command.call_args_list,native.COLD_OWNER_UNITS):
                self.assertEqual(call.args,("/usr/bin/systemctl",row["bytes"],row["sha256"],
                    ["show","--value","--property=ActiveState",unit]))
            self.assertEqual(events[0][1]["systemctl"]["package_kind"],"new")
            command.return_value={"exit":0,"stdout":b"active\n"}
            with self.assertRaises(release.Rejected):tx.cold_recovery_authority()
            self.assertEqual(len(events),1)
@unittest.skipUnless(os.geteuid()==0 and os.environ.get("DROIDLOOM_PUBLIC_TEST_ROOT"),
                     "requires an explicit private root-owned directory for real dpkg rollback tests")
class PublicNamespaceTransaction(unittest.TestCase):
    """Real ordinary packages, confined to a fresh disposable --root tree.

    Only the outer release publication is replaced by these test inventories.
    Payload tar validation, dpkg, directory/file custody and recovery are real;
    no physical admission dispatcher or current host package database is used.
    """
    def setUp(self):
        import cold_apply
        import hashlib
        import subprocess
        from unittest.mock import patch
        self.cold=cold_apply
        parent=Path(os.environ["DROIDLOOM_PUBLIC_TEST_ROOT"])
        st=parent.lstat()
        self.assertTrue(parent.is_absolute() and stat.S_ISDIR(st.st_mode))
        self.assertEqual((st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode)),(0,0,0o700))
        self.tmp=tempfile.TemporaryDirectory(prefix="public-transaction-",dir=parent)
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/"root";self.root.mkdir(mode=0o700)
        for rel in ("var/lib/dpkg/info","var/lib/dpkg/updates","var/lib/dpkg/triggers",
                    "etc/ssh","home/alex","usr/lib/droidloom","usr/share/droidloom"):
            (self.root/rel).mkdir(parents=True,exist_ok=True)
        (self.root/"var/lib/dpkg/status").write_bytes(b"")
        (self.root/"etc/passwd").write_bytes(b"original account fixture\n")
        (self.root/"home/alex/private").write_bytes(b"unselected private fixture\n")
        self.private_identity=release.f9((self.root/"home/alex/private").stat())
        self.original={};self.untouched={}
        for rel in cold_apply.PUBLIC_NAMESPACE_ROOTS:
            path=self.root/rel
            child=path/"unselected";child.write_bytes(b"original unselected child\n")
            os.chown(child,1000,1000);child.chmod(0o600)
            self.untouched[str(child)]=release.f9(child.stat())
            os.setxattr(path,"user.droidloom-test",b"original-directory-attribute")
            os.chown(path,1000,1000);path.chmod(0o755)
        old=self.root/"usr/lib/droidloom/public-test.bin"
        old.write_bytes(b"original public file\n");old.chmod(0o644)
        os.setxattr(old,"user.droidloom-test",b"original-file-attribute")
        self.old_file=old.read_bytes()
        self.files={};self.directories={};self.packages={};self.controls={};self.scopes={}
        payloads={
            "kernel":{"usr/lib/droidloom/kernel-test/vmlinuz":(b"new normal kernel fixture\n",0o444)},
            "android":{"usr/share/droidloom/cohort-test/image":(b"new normal cohort fixture\n",0o444)},
            "host":{"usr/lib/droidloom/public-test.bin":(b"new normal host fixture\n",0o755)}}
        for role in cold_apply.PUBLIC_ORDER:
            package=self.base/("package-"+role);package.mkdir(mode=0o755);package.chmod(0o755)
            (package/"DEBIAN").mkdir(mode=0o755);(package/"DEBIAN").chmod(0o755)
            version="0.0.1"
            (package/"DEBIAN/control").write_text("Package: "+cold_apply.NAMES[role]+
                "\nVersion: "+version+"\nArchitecture: amd64\nMaintainer: Test <test@example.invalid>"
                "\nDescription: confined public transaction fixture\n")
            files={};dirs={}
            for rel,(body,mode) in payloads[role].items():
                path=package/rel;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(body);path.chmod(mode)
                row={"path":rel,"bytes":len(body),"sha256":hashlib.sha256(body).hexdigest(),"mode":mode}
                files[rel]=row;self.files[rel]=dict(row,role=role)
                parts=rel.split("/")
                for n in range(1,len(parts)):dirs["/".join(parts[:n])]=0o755
            for rel in dirs:(package/rel).chmod(0o755)
            archive=self.base/(role+".deb")
            built=subprocess.run(["/usr/bin/dpkg-deb","--build","--root-owner-group","-Znone",
                                  str(package),str(archive)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertEqual(built.returncode,0,built.stderr.decode("utf-8","replace"))
            archive.chmod(0o444);self.packages[role]=release.file_pin(archive)
            self.controls[role]={"version":version};self.directories.update(dirs)
            self.scopes[role]={"files":files,"directories":dirs}
        for rel in cold_apply.PUBLIC_NAMESPACE_ROOTS:
            path=self.root/rel;self.original[rel]=(release.f9(path.stat()),os.getxattr(path,"user.droidloom-test"))
        inputs=({},self.files,self.directories,self.packages,self.controls,self.scopes)
        self.patches=[patch.object(cold_apply,"load_inputs",return_value=inputs),
                      patch.object(cold_apply,"PRESERVE_METADATA",("/etc/passwd","/etc/ssh","/home"))]
        for p in self.patches:p.start()
        self.release_id="a"*64;self.transactions=[]

    def tearDown(self):
        for tx in self.transactions:tx.close()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def transaction(self,*,existing=False):
        tx=self.cold.PublicTransaction(self.root,self.base,self.release_id,existing=existing)
        self.transactions.append(tx);return tx

    def assert_unselected_unchanged(self):
        self.assertEqual(release.f9((self.root/"home/alex/private").stat()),self.private_identity)
        for path,identity in self.untouched.items():self.assertEqual(release.f9(Path(path).stat()),identity)

    def assert_restored(self):
        for rel,(identity,value) in self.original.items():
            path=self.root/rel;now=release.f9(path.stat())
            self.assertEqual(now[:7],identity[:7]);self.assertEqual(now[7],identity[7])
            self.assertEqual(os.getxattr(path,"user.droidloom-test"),value)
        old=self.root/"usr/lib/droidloom/public-test.bin"
        self.assertEqual(old.read_bytes(),self.old_file)
        self.assertEqual(stat.S_IMODE(old.stat().st_mode),0o644)
        self.assertEqual(os.getxattr(old,"user.droidloom-test"),b"original-file-attribute")
        self.assertFalse((self.root/"usr/lib/droidloom/kernel-test").exists())
        self.assertFalse((self.root/"usr/share/droidloom/cohort-test").exists())
        self.assert_unselected_unchanged()

    def test_real_dpkg_install_then_reopened_snapshot_restores_original_metadata_last(self):
        tx=self.transaction();tx.install()
        for rel in self.original:
            st=(self.root/rel).stat();self.assertEqual((st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode)),(0,0,0o755))
        tx.verify_installed();self.assert_unselected_unchanged();tx.close()
        rollback=self.transaction(existing=True);rollback.rollback();self.assert_restored()
        rows=[release.json_bytes(line) for line in rollback.journal.read_bytes().splitlines()]
        releases=[i for i,row in enumerate(rows) if row["phase"]=="public-namespace-released"]
        self.assertEqual(len(releases),2)
        self.assertLess(max(i for i,row in enumerate(rows) if row["phase"]=="dpkg-remove-end"),min(releases))

    def test_first_claim_crash_recovers_from_original_durable_snapshot(self):
        from unittest.mock import patch
        tx=self.transaction();event=tx.event
        def interrupted(phase,**fields):
            event(phase,**fields)
            if phase=="public-namespace-claimed":raise RuntimeError("test process interruption after first claim")
        with patch.object(tx,"event",side_effect=interrupted),self.assertRaises(RuntimeError):tx.install()
        self.assertEqual((self.root/"usr/lib/droidloom").stat().st_uid,0)
        self.assertEqual((self.root/"usr/share/droidloom").stat().st_uid,1000)
        tx.close();self.transaction(existing=True).rollback();self.assert_restored()

    def test_fixed_namespace_owner_mode_alias_and_unlisted_path_are_rejected(self):
        tx=self.transaction();path=self.root/"usr/lib/droidloom"
        for uid,gid,mode in ((1001,1001,0o755),(1000,0,0o755),(1000,1000,0o775)):
            os.chown(path,uid,gid);path.chmod(mode)
            with self.subTest(uid=uid,gid=gid,mode=mode),self.assertRaises(release.Rejected):
                with tx.directory("usr/lib/droidloom",original=True):pass
        os.chown(path,1000,1000);path.chmod(0o755)
        other=self.root/"usr/lib/unlisted";other.mkdir();os.chown(other,1000,1000)
        with self.assertRaises(release.Rejected):
            with tx.directory("usr/lib/unlisted",original=True):pass
        path.rename(path.with_name("saved"));path.symlink_to("saved")
        with self.assertRaises(OSError):
            with tx.directory("usr/lib/droidloom",original=True):pass

    def test_snapshot_inode_or_selected_file_replacement_rejects_before_any_claim(self):
        tx=self.transaction();tx.capture()
        path=self.root/"usr/lib/droidloom/public-test.bin"
        replacement=path.with_name("replacement");replacement.write_bytes(path.read_bytes())
        replacement.chmod(stat.S_IMODE(path.stat().st_mode));os.replace(replacement,path)
        with self.assertRaises(release.Rejected):tx.claim_public_namespaces()
        self.assertTrue(all((self.root/rel).stat().st_uid==1000 for rel in self.original))
        namespace=self.root/"usr/lib/droidloom";namespace.rename(namespace.with_name("saved"))
        namespace.mkdir();os.chown(namespace,1000,1000);namespace.chmod(0o755)
        with self.assertRaises(release.Rejected):tx.claim_public_namespaces()

    def test_wrong_normal_directory_mode_and_special_selected_leaf_are_rejected(self):
        tx=self.transaction();self.directories["usr/lib/droidloom"]=0o700
        with self.assertRaises(release.Rejected):
            with tx.directory("usr/lib/droidloom",original=True):pass
        self.directories["usr/lib/droidloom"]=0o755
        path=self.root/"usr/lib/droidloom/public-test.bin";path.unlink();os.mkfifo(path,0o600)
        with self.assertRaises(release.Rejected):tx.capture()

if __name__=="__main__":unittest.main()
