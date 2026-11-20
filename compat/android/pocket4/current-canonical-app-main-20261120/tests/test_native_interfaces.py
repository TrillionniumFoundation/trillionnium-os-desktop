"""Finite real-host IPC/reap controls; no daemon, Main or Android operation."""
import ast
import os
from pathlib import Path
import socket
import tempfile
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]

def module(path,name):
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),value.__dict__);return value

class Tests(unittest.TestCase):
    def test_actual_unix_peer_credentials_reject_other_process(self):
        native=module(ROOT/'source/native_main_observation.py','tested_native_peer')
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            if os.getuid()==os.getgid()==0:
                self.assertEqual(native.require_peer(a,os.getpid()),(os.getpid(),0,0))
            else:
                with self.assertRaisesRegex(RuntimeError,'NATIVE_SOCKET_PEER'):
                    native.require_peer(a,os.getpid())
            with self.assertRaisesRegex(RuntimeError,'NATIVE_SOCKET_PEER'):
                native.require_peer(a,os.getpid()+1000000)
        finally:a.close();b.close()

    def test_real_owned_command_guard_runs_after_reap(self):
        commands=module(ROOT/'source/business_commands.py','tested_actual_command')
        capture=module(ROOT/'inputs/main/bounded_host_capture.py','actual_pinned_capture')
        # Only the test loader points to the verified local copy; the production
        # command body and its child/subreaper operations run without mocking.
        commands.load_capture=lambda image_channel=False:capture
        events=[]
        children=Path('/proc/self/task')/str(os.getpid())/'children'
        if not children.exists():
            self.skipTest('This controller lacks the real proc children interface; run this exact control on Pocket4')
        initial=children.read_text()
        def guard(*,action_attempted=False):
            self.assertFalse(action_attempted)
            self.assertEqual(children.read_text(),initial)
            events.append(len(events))
            return {'test_only_fixed_host_identity':os.getpid()}
        with tempfile.TemporaryDirectory(prefix='canonical-command-control-') as directory:
            result=commands.run_recorded('actual-host-true',['/usr/bin/true'],3,directory,guard,
                protected_pids=[os.getpid()],mutation=False,output_bound=4096)
            self.assertEqual(result.returncode,0);self.assertEqual(result.stdout,b'');self.assertEqual(result.stderr,b'')
            self.assertTrue(result.command_observation['host_retirement_proved'])
            self.assertTrue(result.command_observation['lifecycle']['child_reaped'])
            self.assertTrue(result.command_observation['subreaper']['final_children_empty'])
        self.assertEqual(events,[0,1]);self.assertEqual(children.read_text(),initial)

    def test_original_command_cancel_fd_and_cleanup_functions_unchanged(self):
        def functions(path):
            return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(path.read_bytes()).body
                    if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
        self.assertEqual(functions(ROOT/'inputs/original-business_commands.py'),
                         functions(ROOT/'source/business_commands.py'))

    def test_python_helper_contract_keeps_exact_seven_and_current_namespace(self):
        contract=module(ROOT/'source/helper_contract.py','tested_helper_interface')
        main={'init':{'start_ticks':321},'main_user_namespace':{'user_namespace':{'device':4,'inode':9001}}}
        env={'PATH':'/system/bin','ANDROID_ROOT':'/system','ANDROID_DATA':'/data',
             'ANDROID_ART_ROOT':'/apex/com.android.art','BOOTCLASSPATH':'/system/a.jar','DEX2OATBOOTCLASSPATH':'/system/a.jar'}
        flags=['--parent-pid=222','--root-fd=4','--mnt-fd=5','--pid-fd=6','--uts-fd=7','--ipc-fd=8','--net-fd=9','--cgroup-fd=10',
               '--expected-userns-device=4','--expected-userns-inode=9001','--expected-init-start-ticks=321']
        literal=contract.COMMANDS[0][1]
        argv=[contract.HELPER['path'],*flags,'--',*contract.command_argv(env,literal)]
        contract.validate_physical_argv(argv,main,env,literal)
        for old,new in (('--expected-userns-inode=9001','--expected-userns-inode=9002'),
                        ('--expected-init-start-ticks=321','--expected-init-start-ticks=322'),
                        ('--net-fd=9','--net-fd=4')):
            candidate=[new if x==old else x for x in argv]
            with self.assertRaises(RuntimeError):contract.validate_physical_argv(candidate,main,env,literal)
        with self.assertRaises(RuntimeError):
            contract.validate_physical_argv([x for x in argv if x!='--cgroup-fd=10'],main,env,literal)

if __name__=='__main__':unittest.main()
