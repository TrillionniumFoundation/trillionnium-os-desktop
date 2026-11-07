#!/usr/bin/env python3
"""Create a new local owner candidate; never edit candidate05 or execute a worker."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
R21 = BASE.parent / 'root-cp06/native-r21/source/actual'
V2 = BASE / 'factory-v2-r2/include/berberis/kernel_api'
PREPARED = BASE / 'go4-actual-preparation-01/preparation.json'
PREPARED_SHA = 'b238f8d53e8b97ae7db9bf30c046f9e21f1fee8c140f03bbb628b78c60124b61'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, why):
    if not value:
        raise RuntimeError(why)


def change(text, before, after):
    require(text.count(before) == 1, 'non-unique preimage anchor: ' + repr(before))
    return text.replace(before, after, 1)


def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-local', action='store_true')
    args = parser.parse_args()
    if not args.write_local:
        print(json.dumps({'state': 'PLAN_ONLY', 'output': str(HERE), 'remote_actions': 0}))
        return
    prepared_raw = PREPARED.read_bytes()
    require(sha(prepared_raw) == PREPARED_SHA, 'actual candidate05 preparation changed')
    prepared = json.loads(prepared_raw)
    files = prepared['engine_files']
    source_path = 'kernel_api/proc_maps_raw_metadata_owner.cc'
    raw = (R21 / 'proc_maps_raw_metadata_owner.cc').read_bytes()
    require(sha(raw) == files[source_path], 'R21 raw owner differs from candidate05')
    old = raw.decode()
    text = change(old,
        'struct Request {\n',
        'enum class PinFailure {kNone,kPidfdOpen,kPidfdGetfd};\n'
        'struct Request {\n')
    text = change(text,
        '  bool context_invalid=false;\n  std::atomic<int> complete{0};\n',
        '  bool context_invalid=false;\n'
        '  PinFailure pin_failure=PinFailure::kNone;\n'
        '  std::atomic<int> complete{0};\n')
    text = change(text,
        '  std::atomic<int> gate{0},event{0},command{0},ready{0},tid{0};\n',
        '  std::atomic<int> gate{0},event{0},command{0},ready{0},tid{0};\n'
        '  std::atomic<int> inherited_tid{0};\n')
    text = change(text,
        '  void* stack_top=nullptr;\n  bool started=false;\n',
        '  void* stack_top=nullptr;\n'
        '  void* inherited_stack_mapping=nullptr;\n'
        '  void* inherited_stack_top=nullptr;\n'
        '  bool started=false;\n')
    text = change(text,
        'void JoinRaw() {\n  for(;;) {\n    const int tid=state.tid.load(std::memory_order_acquire);\n'
        '    if(tid==0)return;\n    Raw(SYS_futex,Address(&state.tid),FUTEX_WAIT,tid);\n  }\n}',
        'void JoinRaw(std::atomic<int>* clear_tid=&state.tid) {\n  for(;;) {\n'
        '    const int tid=clear_tid->load(std::memory_order_acquire);\n'
        '    if(tid==0)return;\n    Raw(SYS_futex,Address(clear_tid),FUTEX_WAIT,tid);\n  }\n}')
    text = change(text,
        'int PrepareStackLocked() {\n  if(state.stack_mapping!=nullptr)return 0;\n',
        'int PrepareOneStackLocked(void** owned_mapping,void** owned_top) {\n'
        '  if(*owned_mapping!=nullptr)return 0;\n')
    text = change(text,
        '  state.stack_mapping=mapping;\n  state.stack_top=static_cast<char*>(bottom)+stack_size;\n'
        '  return 0;\n}\nint OwnProcess()',
        '  *owned_mapping=mapping;\n  *owned_top=static_cast<char*>(bottom)+stack_size;\n'
        '  return 0;\n}\n'
        'int PrepareStackLocked() {\n'
        '  if(PrepareOneStackLocked(&state.stack_mapping,&state.stack_top)<0)return -1;\n'
        '  return PrepareOneStackLocked(&state.inherited_stack_mapping,&state.inherited_stack_top);\n'
        '}\nint OwnProcess()')
    text = change(text,
        'RAW_ONLY int ReadPinned(Request* request) {\n',
        '// inherited_table is true only in the fixed one-shot worker cloned by\n'
        '// this request\'s calling thread without CLONE_FILES. The ordinary worker\n'
        '// must continue acquiring a pidfd/getfd pin from the calling thread.\n'
        'RAW_ONLY int ReadPinned(Request* request,bool inherited_table) {\n')
    text = change(text,
        '  const long caller=Raw(SYS_pidfd_open,request->caller_tid,O_EXCL);\n'
        '  if(caller<0)return static_cast<int>(caller);\n'
        '  const long pinned=Raw(SYS_pidfd_getfd,caller,request->fd,0);\n'
        '  if(pinned<0) {\n    Raw(SYS_close,caller);return static_cast<int>(pinned);\n  }\n',
        '  long caller=-1;\n'
        '  long pinned=request->fd;\n'
        '  if(!inherited_table) {\n'
        '    caller=Raw(SYS_pidfd_open,request->caller_tid,O_EXCL);\n'
        '    if(caller<0) {\n'
        '      request->pin_failure=PinFailure::kPidfdOpen;return static_cast<int>(caller);\n'
        '    }\n'
        '    pinned=Raw(SYS_pidfd_getfd,caller,request->fd,0);\n'
        '    if(pinned<0) {\n'
        '      request->pin_failure=PinFailure::kPidfdGetfd;\n'
        '      Raw(SYS_close,caller);return static_cast<int>(pinned);\n'
        '    }\n'
        '  }\n')
    text = change(text,
        '  Raw(SYS_close,pinned);\n  Raw(SYS_close,caller);\n  if(result<0)',
        '  if(!inherited_table) {Raw(SYS_close,pinned);Raw(SYS_close,caller);}\n'
        '  if(result<0)')
    text = change(text,
        'RAW_ONLY int Worker(void*) {\n',
        'RAW_ONLY int InheritedWorker(void* opaque) {\n'
        '  auto* request=static_cast<Request*>(opaque);\n'
        '  request->result=ReadPinned(request,true);\n'
        '  request->complete.store(1,std::memory_order_release);\n'
        '  Raw(SYS_exit,0);\n'
        '  __builtin_unreachable();\n'
        '}\n'
        '// Caller holds Gate and Mask throughout clone, metadata and kernel\n'
        '// clear-tid. This is never used to establish initial namespace authority:\n'
        '// only an already started, explicitly admitted generation reaches it.\n'
        'void ReadInheritedAfterAllocationFailure(Request* original) {\n'
        '  if(state.inherited_stack_top==nullptr ||\n'
        '     state.inherited_tid.load(std::memory_order_acquire)!=0) {\n'
        '    original->result=-ESHUTDOWN;return;\n'
        '  }\n'
        '  Request inherited{original->caller_tid,original->fd,original->snapshot,\n'
        '                    original->caller_context};\n'
        '  const int flags=CLONE_VM|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM|\n'
        '                  CLONE_PARENT_SETTID|CLONE_CHILD_CLEARTID;\n'
        '  const long tid=berberis_proc_metadata_raw_clone_x86_64(\n'
        '      static_cast<unsigned long>(flags),state.inherited_stack_top,\n'
        '      &state.inherited_tid,InheritedWorker,&inherited);\n'
        '  if(tid<0) {original->result=static_cast<int>(tid);return;}\n'
        '  JoinRaw(&state.inherited_tid);\n'
        '  original->result=inherited.complete.load(std::memory_order_acquire)?inherited.result:-EIO;\n'
        '  original->context_invalid=inherited.context_invalid;\n'
        '}\n'
        'RAW_ONLY int Worker(void*) {\n')
    text = change(text,
        '      request->result=ReadPinned(request);\n',
        '      request->result=ReadPinned(request,false);\n')
    text = change(text,
        '  AppContext after{};\n  const int after_result=ReadContext(&after);\n'
        '  if(after_result<0 || !SameContext(caller,after) || request.context_invalid)',
        '  // Only these two exact allocation stages qualify. A later EMFILE from\n'
        '  // a filesystem, tag read or O_PATH reopen is preserved as an error.\n'
        '  if(request.result==-EMFILE &&\n'
        '     (request.pin_failure==PinFailure::kPidfdOpen ||\n'
        '      request.pin_failure==PinFailure::kPidfdGetfd))\n'
        '    ReadInheritedAfterAllocationFailure(&request);\n'
        '  AppContext after{};\n  const int after_result=ReadContext(&after);\n'
        '  if(after_result<0 || !SameContext(caller,after) || request.context_invalid)')
    text = change(text,
        '  state.tid.store(0,std::memory_order_relaxed);\n',
        '  state.tid.store(0,std::memory_order_relaxed);\n'
        '  state.inherited_tid.store(0,std::memory_order_relaxed);\n')
    text = change(text,
        'bool HasInheritedStack() {return state.stack_mapping!=nullptr;}\n',
        'bool HasInheritedStack() {\n'
        '  return state.stack_mapping!=nullptr && state.inherited_stack_mapping!=nullptr;\n'
        '}\n')
    put('preimage/' + source_path, raw)
    put('source/' + source_path, text.encode())
    changes = {source_path: (old, text)}
    for name in ('proc_maps_raw_metadata_owner.h','proc_maps_provenance.h',
                 'proc_maps_factory_protocol.h','proc_maps_kernel_statfs.h'):
        path='kernel_api/include/berberis/kernel_api/' + name
        header=(V2/name).read_bytes()
        require(sha(header)==files[path], 'header differs from actual candidate05: '+name)
        updated=header.decode()
        if name=='proc_maps_raw_metadata_owner.h':
            updated=change(updated,
                '// Memory preparation alone is safe before specialization: it creates no\n'
                '// worker, stores no credentials, and opens no request admission.\n',
                '// Memory preparation reserves the persistent and inherited-table worker\n'
                '// stacks before specialization. It creates no worker, stores no credentials\n'
                '// and opens no request admission. Both stacks survive a private fork.\n')
        if name=='proc_maps_provenance.h':
            updated=change(updated,
                '// possible virtual inode is pinned by pidfd_getfd in an independent fd table.\n',
                '// possible virtual inode is captured in an independent fd table: normally\n'
                '// by pidfd_getfd, or on an exact descriptor-allocation EMFILE by a fixed\n'
                '// worker inheriting the caller table without CLONE_FILES.\n')
        put('source/' + path, updated.encode())
        if updated.encode()!=header:
            put('preimage/' + path, header)
            changes[path]=(header.decode(),updated)
    patch=''.join(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
                    fromfile='a/'+name,tofile='b/'+name)) for name,(before,after) in changes.items())
    put('nofile-inherited-owner.patch',patch.encode())
    result={'schema':1,'state':'NEW_LOCAL_OWNER_CANDIDATE_UNQUALIFIED',
            'base_candidate05_manifest_sha256':prepared['candidate_manifest_sha256'],
            'actual_base_preparation_sha256':PREPARED_SHA,
            'changed_files':{name:{'preimage_sha256':sha(before.encode()),'candidate_sha256':sha(after.encode())}
                             for name,(before,after) in changes.items()},
            'initial_namespace_authority_changed':False,'generation_gates_changed':False,
            'credential_checks_changed':False,'tag_and_seal_validation_changed':False,
            'new_path_activation':'Only an admitted Read with exact pidfd_open or pidfd_getfd EMFILE',
            'kernel_table_capture':'raw clone without CLONE_FILES, invoked in the actual caller thread',
            'source_compiled':False,'actual_owner_positive_executed':False,
            'Android_executed':False,'candidate05_changed':False,'production_ready':False}
    put('source-derivation.json',(json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result))


if __name__=='__main__':
    main()
