#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Qualify the post-1138 kernel composition under a distinct fixed profile.

The historical engine/profile files are immutable. A private engine instance
receives one code-owned fixed path/byte profile; the public legacy import stays
unchanged. This is source admission, not native authority or group-share proof.
"""
import hashlib
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ENGINE = HERE / "run_unix_stream_guest.py"
PROFILE = "post-1138-oom-adjustment-v2"
ENGINE_SHA256 = '57bd6b8b5f9f9ca1d90b86ab9c9af182b66fd54761db9c844dcc64fcdbc5a3a0'

# Frozen cd40 OOM prerequisite plus independent owned QA; inherited e7ed role identities stay explicit.
ROLE_COUNT = 182
OWNERS = (
    ('oracle.parser', 'tests/kernel/network/unix_stream_oracle.py', 'eefb0f272d2c396ea6fa87c0af827f795b115ca7607c6746abf80975fe544489'),
    ('guard.historical-manifest', 'tests/kernel/network/controls/manifest.json', 'e13376b03d1f3bd85aa9746bbf6b28bf99a1c8da4f8105d37d7a2dada2be844e'),
    ('guard.ordinary-candidate', 'tests/kernel/control/run_queryabi_candidate_guest.py', '7d7a9f92110c5d5ea4a312fddd7ca5061f82bcb7106fa89c7a13161d7d8891a5'),
    ('guard.ordinary-replay', 'tests/kernel/control/run_queryabi_guest.py', '3d981b41ae4905983c67d13d8d7abfbc29318fd6a41b848523eb4c0ac1400268'),
    ('guard.historical-engine', 'tests/kernel/network/run_unix_stream_guest.py', '57bd6b8b5f9f9ca1d90b86ab9c9af182b66fd54761db9c844dcc64fcdbc5a3a0'),
    ('ipc.endpoint', 'kernel/asterinas/kernel/core/src/fs/utils/endpoint.rs', '07e67a10fad1eb4cf84f56d37834e677da1ca03354cf22fb208e0d91ecb308ba'),
    ('ipc.page-memory', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/page_memory.rs', '5e0084bb8b8752a3c24038a96d3f3dd2f43fcf9dd18e017e36c8e44998ff5e03'),
    ('cgroup.root', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/mod.rs', '126bc2e3e21f3c28148b2b4763122045b9b407b459f021daeb6e9b803751d07b'),
    ('ipc.pipe', 'kernel/asterinas/kernel/core/src/fs/pipe/common.rs', 'a3ac4014b42166deb0578444f18b0721e0c1c340448e7c3708b323f6941c8ba4'),
    ('ipc.connected', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected.rs', '9d75fe097c1ecc8fa768c09d53ce0357fb0eb024100c495adf9d86f68b5a9eec'),
    ('ipc.init', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/init.rs', 'd3c6163b7bd23dc7f8d57b136c4a09b868a13c1c70094e89f943d462640e6eac'),
    ('ipc.listener', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/listener.rs', '6a615eced8a03015ddd2731bf91a0bfac3f5b97b7319e2826d7da72a2ddaa28d'),
    ('ipc.socket', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/socket.rs', 'faf968e06abc5581ad5f806f3e9d5999efbf731671e22783c302794f4bffd021'),
    ('ipc.socketpair', 'kernel/asterinas/kernel/core/src/syscall/socketpair.rs', 'ecb440dd55c99c02d565586faa4bd87fc97ad9c30f3661caaaf8ac6d005a95f6'),
    ('ipc.ring-wrapper', 'kernel/asterinas/kernel/core/src/util/ring_buffer.rs', 'c4c98b949380893cc71b02182e27db7286413766931b5d9c82b44f56a623c15e'),
    ('ipc.ring-crate', 'kernel/asterinas/kernel/libs/ring-buffer/src/lib.rs', '5e3375c47397446479681274e2a8bce3c7e778b9e4291eb97b4410fea2494839'),
    ('oracle.probe', 'tests/kernel/network/unix_stream_probe.c', 'bb7e334a76c4e201b3ef33842be7f87a235a6940d783c8c741d63839519ab747'),
    ('oracle.protocol', 'tests/kernel/network/unix_stream_protocol.json', '6577cd26c72c80f370cd4a654463316bf7fa5227a33a0e9ff3ade0e05eb9e680'),
    ('sched.mod', 'kernel/asterinas/kernel/core/src/sched/mod.rs', 'ebe89abfadcf758e40776371da5fa420059858ae207b28ffc5ab76f79ee31322'),
    ('sched.nice', 'kernel/asterinas/kernel/core/src/sched/nice.rs', '1a898d63a4899a8d6b19bdd893f0d55af8c2fd382090a675591ccab1e7e1a614'),
    ('sched.sched_class.mod', 'kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs', '2e9bc792ae5fea78df0244e12139e73e28c7d531acca02061b85dba068f637e1'),
    ('sched.sched_class.administration', 'kernel/asterinas/kernel/core/src/sched/sched_class/administration.rs', '6d849d0ea650e2d5d388b12a51f92807ef875fe6024e76b46a4b966376a05f50'),
    ('sched.sched_class.affinity', 'kernel/asterinas/kernel/core/src/sched/sched_class/affinity.rs', '277c121b2f962112f02381c410f189f337f22a11232fb614d303dba41d6a0484'),
    ('sched.sched_class.capacity', 'kernel/asterinas/kernel/core/src/sched/sched_class/capacity.rs', '989483aef47ea9f52030abcf2c5bd8dffe8a9c21b4a5e8d43ca91d9b69368275'),
    ('sched.sched_class.clock', 'kernel/asterinas/kernel/core/src/sched/sched_class/clock.rs', '3fb6e0f2489d6b46af702626e68a9734a0ecb334211425b0511790822362988f'),
    ('sched.sched_class.fair', 'kernel/asterinas/kernel/core/src/sched/sched_class/fair.rs', '693cbaf94ac26e167e4b7070c54cd685d18d0dcbc8c936285fb0c79148e89cc7'),
    ('sched.sched_class.fair.group', 'kernel/asterinas/kernel/core/src/sched/sched_class/fair/group.rs', 'ce59ad902323cd35e91b407bf57a6fe859c24cc1fac2d48fe94abd2b7e42e1fd'),
    ('sched.sched_class.fair.group.prepare', 'kernel/asterinas/kernel/core/src/sched/sched_class/fair/group/prepare.rs', '54d6fb543285ffd5191069a6c665881da93f628ee712e7d11a24fda8757be1ea'),
    ('sched.sched_class.idle', 'kernel/asterinas/kernel/core/src/sched/sched_class/idle.rs', 'a040f121b924c8727a419fb17c46a4ea1bc63f0791059855ec9f557796495035'),
    ('sched.sched_class.policy', 'kernel/asterinas/kernel/core/src/sched/sched_class/policy.rs', 'd2099352b163ff090e68cf46dbf8767b610c433ce6ccc4a2a23be3f9d617af96'),
    ('sched.sched_class.real_time', 'kernel/asterinas/kernel/core/src/sched/sched_class/real_time.rs', 'dc19809776172c53c5d3d5a7c563766df461d3894f719b9e03816fec4738ed22'),
    ('sched.sched_class.request', 'kernel/asterinas/kernel/core/src/sched/sched_class/request.rs', '4ef68fd81f45ae8636a7b31af261986fe46e68167925e26a9b71e8c86f67ee2f'),
    ('sched.sched_class.stop', 'kernel/asterinas/kernel/core/src/sched/sched_class/stop.rs', 'dd8dac32158592940e1d4c2635c96fc0604fe4b8c0aeab20aa6d34e5553cfe9c'),
    ('sched.sched_class.time', 'kernel/asterinas/kernel/core/src/sched/sched_class/time.rs', '3289e238ef2b27d33e8ac951c6a2d10a92110166c03bfb7ce877cfae8cab83e3'),
    ('sched.sched_class.transfer', 'kernel/asterinas/kernel/core/src/sched/sched_class/transfer.rs', '9deb6e108fea701272a9be987359d3c8c7d379fe7fb27e2579cdb0385a2e838b'),
    ('sched.stats.mod', 'kernel/asterinas/kernel/core/src/sched/stats/mod.rs', '45fff57d812f0e1258440a6cb636ec0ab81067bdcea52773571e4f34b8ad7469'),
    ('sched.stats.loadavg', 'kernel/asterinas/kernel/core/src/sched/stats/loadavg.rs', '18fc32662b6177a6337e330206cb8c3a6b3f7d5468eddab723c6c37712ce7c0e'),
    ('sched.stats.scheduler_stats', 'kernel/asterinas/kernel/core/src/sched/stats/scheduler_stats.rs', '923541151bcaf88949721106cffb7c4d7076c32a76b7308ce71b6beb28d74885'),
    ('cgroup.controller.mod', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/mod.rs', 'a3725643ab7d95a3459f48af9242702286972c823d3330e31ad681d7b7e15e8c'),
    ('cgroup.controller.cpu', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs', '1a11fc952637ef63e845037e4203670e496e8f0988c4a05212d10a968f07f665'),
    ('cgroup.controller.cpu.max_config', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/max_config.rs', '7d7e998b931382d1ea2e522994ee0883bbe82bce5acaa1df2af2fe12b6c8895a'),
    ('cgroup.controller.cpu.native', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs', '4e372815d7d9bd5e99459f1c29bca62bf96faa9c89b5f3507d9c9324da11e8b5'),
    ('cgroup.controller.cpu.native.trusted_control', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native/trusted_control.rs', 'e8af435031ab4d05fc6f86c577bff1fc480a5eadfddd09223a3a500051f45297'),
    ('syscall.sched_affinity', 'kernel/asterinas/kernel/core/src/syscall/sched_affinity.rs', '0c427f73379a74dd2ace71fdc5183110b8eba15460808922ec873a9eec0364d4'),
    ('syscall.sched_permissions', 'kernel/asterinas/kernel/core/src/syscall/sched_permissions.rs', '940ea5d576cae271a6b8e762c9bddd560c8b641c6e27fb407a6b7219f0d5ce3d'),
    ('syscall.sched_getattr', 'kernel/asterinas/kernel/core/src/syscall/sched_getattr.rs', '17d7d0b9cba420638c79cce2076bbabb6d18a17eec3d2ec8ab608bb04d597cf1'),
    ('syscall.sched_getparam', 'kernel/asterinas/kernel/core/src/syscall/sched_getparam.rs', '6a8354c29675a603acb470ed96eb34bc77e976251b8e2990611b584cb04cad1a'),
    ('syscall.sched_getscheduler', 'kernel/asterinas/kernel/core/src/syscall/sched_getscheduler.rs', '0e5a60ec00fa533d98dcdfa85769d69da65ed64568f11cd73ad39ffde54b9fa1'),
    ('syscall.sched_setattr', 'kernel/asterinas/kernel/core/src/syscall/sched_setattr.rs', 'ef7cb6f9646e2b4945d36f903ecfc0fbaa947d6a05780358695696a352373f1b'),
    ('syscall.sched_setparam', 'kernel/asterinas/kernel/core/src/syscall/sched_setparam.rs', '947e897372966960c33367592515e9e68ea72d3dea69549bff839a87009956e8'),
    ('syscall.sched_setscheduler', 'kernel/asterinas/kernel/core/src/syscall/sched_setscheduler.rs', '620d0a50e8f7bf69931f31bf09c16aa5e72c937acef6d284334398403f895020'),
    ('syscall.set_priority', 'kernel/asterinas/kernel/core/src/syscall/set_priority.rs', 'd8a888a048b1d7288c55fdea130cf985a3c18c7105b4b0238f4044d390a2e004'),
    ('syscall.get_priority', 'kernel/asterinas/kernel/core/src/syscall/get_priority.rs', 'edede90545572acee924307bce5a072e4b76bb42d3fb12de476413078ee99670'),
    ('inherit.thread.mod', 'kernel/asterinas/kernel/core/src/thread/mod.rs', '3566e1647814aeca51f861c81f5a08b6886315914ff7bd6b7651f644f7860e93'),
    ('inherit.thread.kernel_thread', 'kernel/asterinas/kernel/core/src/thread/kernel_thread.rs', '38fc03338818f36eedebfee305ff3efbf642b9370dccb88ed202b5212dda47a9'),
    ('inherit.process.clone', 'kernel/asterinas/kernel/core/src/process/clone.rs', '1a83c52fa7d0d9ef671acd4daf66a1d5a698ac23e075422c45a4cd31f92e6983'),
    ('inherit.process.posix_thread.builder', 'kernel/asterinas/kernel/core/src/process/posix_thread/builder.rs', 'f4f28ecde3b98c2fb82cf9e1e331b89b3a16d704fee973ca997fde1ffc9a16ef'),
    ('ostd.sync.wait', 'kernel/asterinas/ostd/src/sync/wait.rs', '598266d76fbd90a1b3731d1107d46cb198a0cabfa1773ced70061d2e01af8f11'),
    ('ostd.sync.spin', 'kernel/asterinas/ostd/src/sync/spin.rs', '8d0b331b7ad31a61ba41fb838103d75c606d4709027d13782afd61eade294207'),
    ('ostd.sync.mutex', 'kernel/asterinas/ostd/src/sync/mutex.rs', 'e28ffd1297d74bc172d35951ec4442e8d84f7c2dc939145f449e0b6efef2f21a'),
    ('ostd.sync.guard', 'kernel/asterinas/ostd/src/sync/guard.rs', '9100d92d3214b3d3e9fcd08267ecdda3c4b2dcc25224e97a81ab39860ebedb58'),
    ('ostd.irq.guard', 'kernel/asterinas/ostd/src/irq/guard.rs', 'd314d4217b1d694b2ff1e2f193a8059fc3b5e7763d5c88329ce94b06cdf11622'),
    ('ostd.task.mod', 'kernel/asterinas/ostd/src/task/mod.rs', '37d36b7a0739b3a8bb6792945f8e067749a8cdbcd81a6b1e0bcb924dcdab4422'),
    ('ostd.task.atomic_mode', 'kernel/asterinas/ostd/src/task/atomic_mode.rs', 'e9998f8ec7eebea34adeb2381e4ed5102861ec4254f9454f9f5187c15c293f3c'),
    ('ostd.task.processor', 'kernel/asterinas/ostd/src/task/processor.rs', 'b34e3c0846f559f33cbfba318facd0c29732ad569da863b099bff69e611fb424'),
    ('ostd.task.scheduler.mod', 'kernel/asterinas/ostd/src/task/scheduler/mod.rs', '59a837d5480ff1636f0dbbc3f8cda6c02331eb01fbd5ebd4043fd94880f0fd43'),
    ('ostd.task.scheduler.info', 'kernel/asterinas/ostd/src/task/scheduler/info.rs', 'aeb4528febcc166b25882061b3f4afc93e4960a4a651e0423463db4dada7eba9'),
    ('ostd.task.preempt.mod', 'kernel/asterinas/ostd/src/task/preempt/mod.rs', '4abe7cde72c9daa7e1d3332e88d23f5f65a2c5ac489f2bf264222916486b4215'),
    ('ostd.task.preempt.guard', 'kernel/asterinas/ostd/src/task/preempt/guard.rs', '38a8b628b7c3fa462b3549b5e5d41eecd42185150b8e6572da09f4dec4a02faf'),
    ('ostd.task.preempt.cpu_local', 'kernel/asterinas/ostd/src/task/preempt/cpu_local.rs', 'f37ed91e1ec3701e46727d546da5bd647271fd196f1580fcfbb667b00d221f48'),
    ('cgroup.raw-route-lifetime', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/scheduling_route.rs', '54a5c7ffca660f6a3200e156a17a633be641a8c9b57e1ec546ec07ab5dbcb39d'),
    ('cgroup.membership-and-retirement', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs', '8aff039bf83cc8bd3f3bc2d69acc4b678c3f18e78eae892a61c2505aaea5856d'),
    ('oracle.prepared-route-lifetime', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/group_entity_regressions.rs', 'ba318a86b1fda4849ec1ae8938e863c593e7fd7cd0436a92dd8a39a3c65a48c4'),
    ('oracle.scheduler-switch-and-spawn', 'kernel/asterinas/kernel/core/src/sched/sched_class/switch_tests.rs', '9c0ba19efb3d06a89d4f761b5d893c6082e0d5d18f57444085d6c7792f93d7c7'),
    ('contract.prepared-group-lifetime', 'support/kernel-safety/FAIR_GROUP_ENTITIES.md', '58ae0e0fcfebbd1cfe0719392affd676a2cf6182a8da1652650fbfe7f49a6484'),
    ('contract.cpu-bandwidth-n0', 'docs/ASTERINAS_CPU_BANDWIDTH_N0.md', '26e2f6950270ba899ad70ed80354fef37f7bdebbf204eb9128ad214ab05b4887'),
    ('ostd.trap.gdt', 'kernel/asterinas/ostd/src/arch/x86/trap/gdt.rs', 'de99d528a5e0361104b3cce37fddc9f54dac211496a499cd045bf5fcf7b8f62a'),
    ('oracle.ostd.gdt', 'kernel/asterinas/ostd/src/arch/x86/trap/gdt_tests.rs', 'abc35bebd58671040ff188452a90a237a21ab80052e202addb4795ec8cbd3de5'),
    ('oracle.cpu-identity.probe', 'tests/kernel/vdso-cpu/probe.c', 'ff402aa021e117db35461e4104bc8676d7c4c1d8c89f1364100992633f0825d5'),
    ('oracle.cpu-identity.runner', 'tests/kernel/vdso-cpu/run.py', '0a5e3bbe883a986d210fe4c0ef44c88096c397ed15e30b8f433b0bf82009a75e'),
    ('contract.cpu-identity.qa', 'tests/kernel/vdso-cpu/README.md', '9eeea9b59ee0a264fc275efe8713c75f2e4861d4927791e511d2e81557ecc9e1'),
    ('contract.cpu-identity.abi', 'support/kernel-safety/VDSO_CPU_IDENTITY.md', '8bec92b89171d5437dc02160ddc231fb5d746bdf49677c0f6cbe710a56074f10'),
    ('ci.a06.kernel', '.github/workflows/a06-kernel.yml', 'bd6065088987450f81fde45f3226b53a0200528999f037452fe3dc41e9fe83da'),
    ('guard.post1138-historical-profile', 'tests/kernel/network/run_unix_stream_post1138_guest.py', '11b90b025e1a82eccfdd6a46f21606c3ed6114339b65c475db4e17a048b73c26'),
    ('ostd.mm.vm-space', 'kernel/asterinas/ostd/src/mm/vm_space.rs', 'a9d966c97a72db546fe78df9efd3715c9b6f870285221584a228999b17e03b51'),
    ('ostd.mm.kernel-page-table', 'kernel/asterinas/ostd/src/mm/page_table/mod.rs', '71d11af5a7e8aa8d50c87ca433f497eae8c81504916d830ddf11bdf939b72c83'),
    ('ostd.mm.managed-page-table-root', 'kernel/asterinas/ostd/src/mm/page_table/node/mod.rs', 'c2d5d408d3df0b85e54d11d29f62a673f4408eb5c8579644139867c40484a354'),
    ('oracle.ostd.vm-space-retirement', 'kernel/asterinas/ostd/src/task/processor_retirement_tests.rs', 'cb536010a3eb169fbde7170e3998f05967f205abec616012dad93ffb3a10dd9e'),
    ('contract.vm-space-retirement', 'support/kernel-safety/VMSPACE_RETIREMENT.md', 'be8ed9abf295561008c2ccb9d7c036373a1a33571924de2da43564c4112c49cb'),
    ('guard.cpunode-historical-profile', 'tests/kernel/network/run_unix_stream_cpunode_guest.py', '82a62dee3e0c97763f20e766f721fc3afbf4d4a3f29bfb53738689a4511fae2c'),
    ('guard.vm-retirement-historical-profile', 'tests/kernel/network/run_unix_stream_retirement_guest.py', '39db5e319345ad22383b266f4daae3c11b6938f1fd82115722397405156d9ddb'),
    ('unix.signal.sendmmsg-entry', 'kernel/asterinas/kernel/core/src/syscall/sendmmsg.rs', '806256cdbb5f6217d38c6e911359a742ce11ddb5780d83c2f6267187c83a3f38'),
    ('unix.signal.writev-entry', 'kernel/asterinas/kernel/core/src/syscall/pwritev.rs', '608c5004f0105579af7295d76c8ed5ee1673bbedf3b2d28d69dd22864f83d99b'),
    ('contract.unix-signal', 'support/kernel-safety/UNIX_SOCKET_SIGPIPE.md', '1e2897c40a3cf6614cce2a4721eeeee3f61a5a28f0efedc1a8a73ce4797ff347'),
    ('oracle.unix-signal.probe-c', 'tests/kernel/unix-signal/probe.c', 'e08180d2d460723afab0ee8923c9f9eaf17c41bc40f45b5966c5683a84b7c09f'),
    ('oracle.unix-signal.run-py', 'tests/kernel/unix-signal/run.py', '9ccec5fdf9b0cc54e64519e992a15d3ef856b7929901639bfebcf794948b2850'),
    ('oracle.unix-signal.test_run-py', 'tests/kernel/unix-signal/test_run.py', '8a6086f3abca19f4549a2fae8ccebe77ce079d0a35c09379523326217275ad5b'),
    ('oracle.unix-signal.README-md', 'tests/kernel/unix-signal/README.md', '44df7be54804ebca8ac883069741541294f7057649d598bacc6df9451b3bc950'),
    ('contract.compat.networking-and-sockets.README-md', 'kernel/asterinas/book/src/kernel/linux-compatibility/syscall-flag-coverage/networking-and-sockets/README.md', '078bed4813d07b8efb5b61bc12d0f4c2df74fa66629d1e4e982dfde057dc87d9'),
    ('contract.compat.networking-and-sockets.sendto_and_sendmsg-scml', 'kernel/asterinas/book/src/kernel/linux-compatibility/syscall-flag-coverage/networking-and-sockets/sendto_and_sendmsg.scml', 'd0abd77aa5d448591c8dc1cdd4c0e708bc3653d6e3e49ef2156bb845cb11102e'),
    ('contract.compat.file-and-directory-operations.README-md', 'kernel/asterinas/book/src/kernel/linux-compatibility/syscall-flag-coverage/file-and-directory-operations/README.md', '01d9bdd4453fcf92ba2f08042bdb5afa84562b4f3ef2d5096d96940d33e59683'),
    ('contract.compat.file-and-directory-operations.fully_covered-scml', 'kernel/asterinas/book/src/kernel/linux-compatibility/syscall-flag-coverage/file-and-directory-operations/fully_covered.scml', '5578024247880cf2e5d511e68118981ed1b07a30d2b2c62d55891649d2a25e93'),
    ('unix.signal.dependency.socket-filelike-write', 'kernel/asterinas/kernel/core/src/net/socket/mod.rs', 'be5926e00f1386f4c1cbdc707c34bc0eba2d07bbe92787193878770254a18970'),
    ('unix.signal.dependency.send-flags', 'kernel/asterinas/kernel/core/src/net/socket/util/message_flags.rs', '3480122ccc58d6aea409ee5efbe9ebff200954b32c22d0d6c09845bf572c4095'),
    ('unix.signal.dependency.sendto-entry', 'kernel/asterinas/kernel/core/src/syscall/sendto.rs', '735227ea1e528bc1d66b48c72608ffdb186136d0fafa7c3a9ab7e3fde2ac296f'),
    ('unix.signal.dependency.sendmsg-entry', 'kernel/asterinas/kernel/core/src/syscall/sendmsg.rs', 'a4055a1f7ba67c694ca970cbc96f924ce5d9f8c100d629ffc912c034352b3e19'),
    ('unix.signal.dependency.user-iovec', 'kernel/asterinas/kernel/core/src/util/iovec.rs', '1741295380c3d1d3e45853d9eb6cf608abf5d49fe83bb0a20ad16c24e9e4bf0c'),
    ('unix.signal.dependency.current-posix-thread', 'kernel/asterinas/kernel/core/src/process/posix_thread/mod.rs', '4d78f23d618d5b56cbd2efe5254d9393a30966cb1eda2956befb9ce85ead2bc3'),
    ('unix.signal.dependency.current-thread-cast', 'kernel/asterinas/kernel/core/src/process/posix_thread/posix_thread_ext.rs', '523fae9cb35c23d3ebe71643c94754f325042bf2bdc10d5d3ae833e7390f030b'),
    ('unix.signal.dependency.user-task-signal-return', 'kernel/asterinas/kernel/core/src/thread/task.rs', 'abe986dcbc585026ff8b988c5a36cc1d6346c8ca51c75747107dd3ab1d2a6f08'),
    ('unix.signal.dependency.errno-conversion', 'kernel/asterinas/kernel/core/src/error.rs', 'dd784ae6f380c9580f8cbae7d6b571713d3ffb21ac17fa686d017c95761bd468'),
    ('unix.signal.module.c_types', 'kernel/asterinas/kernel/core/src/process/signal/c_types.rs', '9bc53eef6b0388dcacafde774ceca30037f28dc4e2693d7450bc9ad972da6473'),
    ('unix.signal.module.constants', 'kernel/asterinas/kernel/core/src/process/signal/constants.rs', '6d49f69446a9fbd5d4cc1e3d89090a483a9249649b17c00dbc5412f0f7fed731'),
    ('unix.signal.module.mod', 'kernel/asterinas/kernel/core/src/process/signal/mod.rs', '17819bf373d388153efaa95d88e7c2b456ab41e5909972a29f30adefdc0a601e'),
    ('unix.signal.module.pause', 'kernel/asterinas/kernel/core/src/process/signal/pause.rs', 'db96ad9e390c1357b67e09cc288cf3767f93ec20b16ad3ea58694549644ef3da'),
    ('unix.signal.module.pending', 'kernel/asterinas/kernel/core/src/process/signal/pending.rs', '1c8c3343e1ba45e071053e7cdf63291cdcaa043744cfbce2c2d85c7bb681b08e'),
    ('unix.signal.module.poll', 'kernel/asterinas/kernel/core/src/process/signal/poll.rs', 'cf5bafa0f9aceddfc37d3771c5b6ac082f49686c5a16de91738024b6b120de81'),
    ('unix.signal.module.sig_action', 'kernel/asterinas/kernel/core/src/process/signal/sig_action.rs', '56e5b7d4613d8eef1e12b55e25db33326feafaaf2ed5299043018390dd479f6d'),
    ('unix.signal.module.sig_disposition', 'kernel/asterinas/kernel/core/src/process/signal/sig_disposition.rs', 'ed43113f145cfacfc3baf6b759432eb8982daeb4e0dea1a876e0e2c8142b8f96'),
    ('unix.signal.module.sig_mask', 'kernel/asterinas/kernel/core/src/process/signal/sig_mask.rs', 'c0b60f5f934dcb10f5c9bb8703799514e893be715ee62390fc83a6c757b91d6c'),
    ('unix.signal.module.sig_num', 'kernel/asterinas/kernel/core/src/process/signal/sig_num.rs', '2b5f3021c7b5fd5320ade612ac518371850fb7d9ae45eebf4388045b8e1690a5'),
    ('unix.signal.module.sig_queues', 'kernel/asterinas/kernel/core/src/process/signal/sig_queues.rs', '1d14b6858644968327dad96e4a4a4b5b05a65bb95413a2d1f02a31b4416c5897'),
    ('unix.signal.module.sig_stack', 'kernel/asterinas/kernel/core/src/process/signal/sig_stack.rs', '5063d1b00d62f44e4a8b6ec7308ab0242266bf99b068fb395184d5d40154f7bf'),
    ('unix.signal.module.signals.fault', 'kernel/asterinas/kernel/core/src/process/signal/signals/fault.rs', 'c5e8ad16c6c12f719be7cf96bf19e826c6637fa249e2025c1f5628d30bc9bd45'),
    ('unix.signal.module.signals.kernel', 'kernel/asterinas/kernel/core/src/process/signal/signals/kernel.rs', 'b275711d35de13038be96ea6957d70f88faf837be3e253bd0c4ba738e484d694'),
    ('unix.signal.module.signals.mod', 'kernel/asterinas/kernel/core/src/process/signal/signals/mod.rs', '975bec6e1c0d9bc8fb873a1260f3dbbe4f5bc1e244ec930b86de1381f8421a8a'),
    ('unix.signal.module.signals.raw', 'kernel/asterinas/kernel/core/src/process/signal/signals/raw.rs', '13cc6f38b9e9814c261209c27d32cc2048918f8b582f83785622e941b3e3268f'),
    ('unix.signal.module.signals.seccomp', 'kernel/asterinas/kernel/core/src/process/signal/signals/seccomp.rs', 'e213d058f036a60283bcd5eedff7a87e0b12022b88258628581094e6e70911e6'),
    ('unix.signal.module.signals.user', 'kernel/asterinas/kernel/core/src/process/signal/signals/user.rs', '77499e05489f91af85ef2317bc43f1046aab2a9d20fb5be30ed400c8805ef259'),
    ('unix.signal.dependency.filelike-downcast', 'kernel/asterinas/kernel/core/src/fs/file/file_handle.rs', '48724b5e3c2a6d455718518a58550679bf8b5c592847bff29fa8f0c66e440b8a'),
    ('unix.signal.dependency.unix-public-reexport', 'kernel/asterinas/kernel/core/src/net/socket/unix/mod.rs', '05c4f11c3702ef2ce60ac80e88e1cd21316e609a91733f11d87d5d00d2c259fb'),
    ('unix.signal.dependency.unix-stream-reexport', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/mod.rs', 'f2ce8b9c6bf49908257cc939a3aa618a11e8971a0ef5767c9537a32c6f027f92'),
    ('oom.prerequisite.00.oom_adjustment.rs', 'kernel/asterinas/kernel/core/src/process/oom_adjustment.rs', 'b62736dadb1db8e9e2108d40b38e346a9197d5bfdf76da974a76924b38dd514f'),
    ('oom.prerequisite.01.tests.rs', 'kernel/asterinas/kernel/core/src/process/oom_adjustment/tests.rs', '06f3344993be9ca589dcbc41b93df3f7a237f1e280f380ccccb4d626a3b6486f'),
    ('oom.prerequisite.02.mod.rs', 'kernel/asterinas/kernel/core/src/process/mod.rs', '0be1997d4b8cd823d52b9b6e098542af08566a0bafc832849bf4b718ac553306'),
    ('oom.prerequisite.03.mod.rs', 'kernel/asterinas/kernel/core/src/process/process/mod.rs', 'd5500914f5cd0ebf89aac75811e4c8f6d47b22cc01d7b2143db3654e6e52f110'),
    ('oom.prerequisite.04.mod.rs', 'kernel/asterinas/kernel/core/src/process/process_vm/mod.rs', '9c67454ac8718cc5c7e532a9ad155ac17f8d1d21fc0f7ec342b408ecf3abf8ed'),
    ('oom.prerequisite.05.init_proc.rs', 'kernel/asterinas/kernel/core/src/process/process/init_proc.rs', '3c44ced81427f290a8d778944b809bf372e4560057d70f3c23c3b2936cd39865'),
    ('oom.prerequisite.06.test_util.rs', 'kernel/asterinas/kernel/core/src/process/test_util.rs', '77ecea5539b1b9d462ecfb6a7134cd73c2c2f0452b1d6d55b8f346916286fbe8'),
    ('oom.prerequisite.07.exit.rs', 'kernel/asterinas/kernel/core/src/process/exit.rs', 'a10d9deb35c71ab76077e892ade8227eb4fa4c1aef052a562c685b7eb6b86cf1'),
    ('oom.prerequisite.08.execve.rs', 'kernel/asterinas/kernel/core/src/process/execve.rs', '6d257baac851c2cf5da7ecdfa5a44c3f8180e34a4ac14c484a3b7a6db8235337'),
    ('oom.prerequisite.09.exit.rs', 'kernel/asterinas/kernel/core/src/process/posix_thread/exit.rs', '01d6cbc52691941c58fd063a29769f9151cb38193a4c320243f1a7667372c6a2'),
    ('oom.prerequisite.10.credentials_edit.rs', 'kernel/asterinas/kernel/core/src/process/posix_thread/credentials_edit.rs', '4f8e654cb11646ee5a8b7ee66260aec28f5c01b06be45dc9531ccb2ea6df6764'),
    ('oom.prerequisite.11.mod.rs', 'kernel/asterinas/kernel/core/src/process/credentials/mod.rs', '86b9f718e31df5e1f2743c985e5195d1f132e6608a41efaad2c454ee350c349f'),
    ('oom.prerequisite.12.credentials_.rs', 'kernel/asterinas/kernel/core/src/process/credentials/credentials_.rs', '5dd71747b74d1ad4cbf78ee75470efff07c7633c80c24b8b7c217ab89efca2d3'),
    ('oom.prerequisite.13.capabilities.rs', 'kernel/asterinas/kernel/core/src/process/credentials/capabilities.rs', 'f7b6efec8e00efff9ba0c3acd94253de11cdfaa3d79524ab17f03d88ac01b071'),
    ('oom.prerequisite.14.c_types.rs', 'kernel/asterinas/kernel/core/src/process/credentials/c_types.rs', 'ca658db895382b7932a45e80f786b41329fbc3d602deacbcecbbe6e1681181b0'),
    ('oom.prerequisite.15.user.rs', 'kernel/asterinas/kernel/core/src/process/credentials/user.rs', 'c2611a04638ea64b8237f78955f0e9c08a6ff4134c654edf9933d683a22e746b'),
    ('oom.prerequisite.16.user_ns.rs', 'kernel/asterinas/kernel/core/src/process/namespace/user_ns.rs', '87ef2baf41b6720c8f160df35b61ea0fc20664fa060041f4db6a9dd900d39a84'),
    ('oom.prerequisite.17.capability.rs', 'kernel/asterinas/kernel/core/src/security/lsm/hooks/capability.rs', '7f0ed419bd2e2ab75c4b67edbcce0b95170bb6cced9081f89cb37d90382d3408'),
    ('oom.prerequisite.18.capability.rs', 'kernel/asterinas/kernel/core/src/security/lsm/modules/capability.rs', '52ce6f885608f4781bee962e4bc73edb808d18b433b16741e002a0a8c0ff4876'),
    ('oom.prerequisite.19.mod.rs', 'kernel/asterinas/kernel/core/src/security/lsm/modules/mod.rs', '5281c0450df65176dff02dfc7f41e5811fc2781494698c870f785e6630f52a86'),
    ('oom.prerequisite.20.oom_score_adj.rs', 'kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/oom_score_adj.rs', 'e06f269b244094bb9ea0d0c8b9dc54c94b5accb59d991fd75e838a4db8a61acc'),
    ('oom.prerequisite.21.mod.rs', 'kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/mod.rs', '3f91e16a5fd49436f0c59443be052284d9eaee55b702f7929d54b3533abf138b'),
    ('oom.prerequisite.22.mod.rs', 'kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/template/mod.rs', '4b8c2c990359037480479ce96d4de4af7de995e0262beb0d498909aa37e32148'),
    ('oom.prerequisite.23.file.rs', 'kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/template/file.rs', 'c0dad4621f667280709720dfa79c1a733c1ecbb27910a0fe68c53467c9ce5de7'),
    ('oom.prerequisite.24.capget.rs', 'kernel/asterinas/kernel/core/src/syscall/capget.rs', 'd0e57f3924600dc59ddd3fa75bf15c8f83763519a9025efff3a2d0dfce357da0'),
    ('oom.prerequisite.25.capset.rs', 'kernel/asterinas/kernel/core/src/syscall/capset.rs', '9e9b05c0b5e24c4d6cca3e9d8e7a8e2e029ce7eb8c458957b8ef02fe7013e886'),
    ('oom.prerequisite.26.setresuid.rs', 'kernel/asterinas/kernel/core/src/syscall/setresuid.rs', '1f2ccdcc55852606473e4038aa3dc99817e1e22051746278a485451f78af046e'),
    ('oom.prerequisite.27.setresgid.rs', 'kernel/asterinas/kernel/core/src/syscall/setresgid.rs', 'b24ff02c65a589687d52af30d287813e43858dcd45678689abc6788fc1782592'),
    ('oom.prerequisite.28.clone.rs', 'kernel/asterinas/kernel/core/src/syscall/clone.rs', 'db55eecea5c42bad9c214ef2459f9be36a8bc1773cbf4195947b3b228960db1e'),
    ('oom.prerequisite.29.fork.rs', 'kernel/asterinas/kernel/core/src/syscall/fork.rs', 'd042992ad762f8d0818b28028bc07cbf84da8d540fd0287ecd9e270c2fdb7038'),
    ('oom.prerequisite.30.execve.rs', 'kernel/asterinas/kernel/core/src/syscall/execve.rs', '491c0302a5726f1f2f5ba65c2e638aa8f0e13d5be856ef265b228c252fb1ef19'),
    ('oom.prerequisite.31.exit.rs', 'kernel/asterinas/kernel/core/src/syscall/exit.rs', '78939966e0d7e78e1cf77d636dc18d4580c352d276cc595fee48470096284b4f'),
    ('oom.prerequisite.32.exit_group.rs', 'kernel/asterinas/kernel/core/src/syscall/exit_group.rs', '7d5bda1b761ea29a7b4b9158493f2aed42c0ba43c0de282274d685bdc83b3027'),
    ('oom.prerequisite.33.prctl.rs', 'kernel/asterinas/kernel/core/src/syscall/prctl.rs', '1dcf857ebc1667f9ffd208e71eb55fe083caebebad7bbaf2a35a2403c6e5eab8'),
    ('oom.prerequisite.34.pwrite64.rs', 'kernel/asterinas/kernel/core/src/syscall/pwrite64.rs', '3dd58793a31cf4df9e277c116480ee9f26c3c2c6655ab65f49dc4a4647654fb6'),
    ('oom.prerequisite.35.pread64.rs', 'kernel/asterinas/kernel/core/src/syscall/pread64.rs', '41aa1aeacecfd997e989c96ca46c3741c5c73533dcf7536cdecfebc665196d73'),
    ('oom.prerequisite.36.OOM_ADJUSTMENT.md', 'support/kernel-safety/OOM_ADJUSTMENT.md', '5b90c40241bbb99599462b8e0cdf5d92497949daf221b5514198a264f0b44e46'),
    ('oom.prerequisite.37.run.py', 'support/build/ktest/run.py', '9cf654eeda459413e5b8af37e1424ceea7ef11aeaa92ff2c4ececf07e8ce47e1'),
    ('oom.prerequisite.38.check.py', 'support/build/ktest/check.py', 'e80fc3fe31b689938b742b46efec461dadd07421b2039a9d247d6911f96bb314'),
    ('oom.prerequisite.39.run.py', 'tests/kernel/safety/run.py', '4d69f4dfea4ed0b5a9ef9c76dd443e0884ad7c08a1e4a278a98f3dcd234ee2fe'),
    ('oom.prerequisite.40.probe.c', 'tests/kernel/oom-adjustment/probe.c', '4091b648226f1bd86dc369c2003ed584a34d660ba03d15d6dbdaa30e54c1cfc9'),
    ('oom.prerequisite.41.run.py', 'tests/kernel/oom-adjustment/run.py', 'a0a35908baac81652bfae469adfd637a1f78b5e29edb77429baedaf30a443075'),
    ('oom.prerequisite.42.test_run.py', 'tests/kernel/oom-adjustment/test_run.py', '8e079a3db00df337bfdbd49ac6148562d7ca992e1c6a15c5ca9191d8b8c98241'),
    ('oom.prerequisite.43.README.md', 'tests/kernel/oom-adjustment/README.md', 'dc25811d9e1ba4512fbdce174f9ca967b2aea1f2904da97bce0821419de279d8'),
    ('oom.prerequisite.44.run_unix_stream_signal_guest.py', 'tests/kernel/network/run_unix_stream_signal_guest.py', 'a048b15695d6d3c6c588d823acc54d603d2b7d0cd59dcb1e1a57a1dd93868649'),
    ('oom.prerequisite.45.test_signal_source_profile.py', 'tests/kernel/network/test_signal_source_profile.py', 'aeb6cccc821e8443996f6baab56e03c5b6dbfa212571310d8fb1fd6537eb9419'),
    ('oom.prerequisite.46.post1138-unix-signal-v2-source.json.gz', 'tests/kernel/network/controls/post1138-unix-signal-v2-source.json.gz', '43463606da436086832779a397cde98fe68c4fed0ac2eb58b606b8f891da09e0'),
    ('oom.prerequisite.47.test_oom_source_profile.py', 'tests/kernel/network/test_oom_source_profile.py', 'af6d68f058dac07b1ce3d4459400c0ef1b6fb560adb868ca66f2c74ae0f0c2fc'),
    ('oom.prerequisite.48.POST1138_OOM_ADJUSTMENT_PROFILE.md', 'tests/kernel/network/POST1138_OOM_ADJUSTMENT_PROFILE.md', '5713570102f92c28a5c05d68b947bb029f06e0a56c06e007aa79ab94e77bc261'),
    ('oom.aggregate.current-source-profile', 'tests/kernel/network/test_ipc_source_profile.py', 'eae6b636d89f439f3569a834c1de99b1b71a3b7be738b18cc935e6ef9205b7f0'),
)


def verify_engine(data):
    if hashlib.sha256(data).hexdigest() != ENGINE_SHA256:
        raise ValueError("historical Unix engine bytes changed")


engine_bytes = ENGINE.read_bytes()
verify_engine(engine_bytes)
spec = importlib.util.spec_from_file_location("_post1138_oom_adjustment_engine", ENGINE)
engine = importlib.util.module_from_spec(spec)
# Execute exactly the checked bytes, rather than rereading through the loader.
exec(compile(engine_bytes, str(ENGINE), "exec"), engine.__dict__)
original_required_sources = engine.required_sources
original_profiles = engine.SOURCE_PROFILES


def required_sources(variant, source_profile):
    if source_profile != PROFILE:
        return original_required_sources(variant, source_profile)
    engine.require(variant == "positive", "historical mutations cannot use post-1138 OOM adjustment profile")
    roles = [role for role, _, _ in OWNERS]
    paths = [path for _, path, _ in OWNERS]
    engine.require(len(set(roles)) == len(roles) and len(set(paths)) == len(paths),
                   "duplicate post-1138 OOM adjustment owner role/path")
    return {path: sha for _, path, sha in OWNERS}


# Only this private engine instance knows the added name. Do not alter the
# public historical module or accept an operator-supplied hash/manifest.
engine.SOURCE_PROFILES = (*original_profiles, PROFILE)
engine.required_sources = required_sources
check_sources = engine.check_sources


def main(argv=None):
    return engine.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
