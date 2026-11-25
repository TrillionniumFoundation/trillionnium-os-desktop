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
if __name__=="__main__":unittest.main()
