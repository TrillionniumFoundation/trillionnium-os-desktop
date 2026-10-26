#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Qualify the receiving FAIR/affinity/IPC composition under a distinct profile.

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
PROFILE = "receiving-force-v1"
ENGINE_SHA256 = '57bd6b8b5f9f9ca1d90b86ab9c9af182b66fd54761db9c844dcc64fcdbc5a3a0'

# Reviewed after receiving merge 38f4fc57; roles and hashes are literal code.
OWNERS = (
    ('oracle.parser', 'tests/kernel/network/unix_stream_oracle.py', 'eefb0f272d2c396ea6fa87c0af827f795b115ca7607c6746abf80975fe544489'),
    ('guard.historical-manifest', 'tests/kernel/network/controls/manifest.json', 'e13376b03d1f3bd85aa9746bbf6b28bf99a1c8da4f8105d37d7a2dada2be844e'),
    ('guard.ordinary-candidate', 'tests/kernel/control/run_queryabi_candidate_guest.py', '7d7a9f92110c5d5ea4a312fddd7ca5061f82bcb7106fa89c7a13161d7d8891a5'),
    ('guard.ordinary-replay', 'tests/kernel/control/run_queryabi_guest.py', '3d981b41ae4905983c67d13d8d7abfbc29318fd6a41b848523eb4c0ac1400268'),
    ('guard.historical-engine', 'tests/kernel/network/run_unix_stream_guest.py', '57bd6b8b5f9f9ca1d90b86ab9c9af182b66fd54761db9c844dcc64fcdbc5a3a0'),
    ('ipc.endpoint', 'kernel/asterinas/kernel/core/src/fs/utils/endpoint.rs', '07e67a10fad1eb4cf84f56d37834e677da1ca03354cf22fb208e0d91ecb308ba'),
    ('ipc.page-memory', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/page_memory.rs', '5e0084bb8b8752a3c24038a96d3f3dd2f43fcf9dd18e017e36c8e44998ff5e03'),
    ('cgroup.root', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/mod.rs', '57a2c8c4a5f61e5b8eb96e7e81ae62ae9f358524d02cdfcbb54655eb50df07c5'),
    ('ipc.pipe', 'kernel/asterinas/kernel/core/src/fs/pipe/common.rs', 'a3ac4014b42166deb0578444f18b0721e0c1c340448e7c3708b323f6941c8ba4'),
    ('ipc.connected', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected.rs', '2acf2709ee3983b6388235629f53e985ccf58eb08bbe960679942479f84a5b72'),
    ('ipc.init', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/init.rs', 'd3c6163b7bd23dc7f8d57b136c4a09b868a13c1c70094e89f943d462640e6eac'),
    ('ipc.listener', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/listener.rs', '6a615eced8a03015ddd2731bf91a0bfac3f5b97b7319e2826d7da72a2ddaa28d'),
    ('ipc.socket', 'kernel/asterinas/kernel/core/src/net/socket/unix/stream/socket.rs', '39d376e77ec83353df9df3880cfdd01939881b38ee572c4bf1300c7d8fd83e85'),
    ('ipc.socketpair', 'kernel/asterinas/kernel/core/src/syscall/socketpair.rs', 'ecb440dd55c99c02d565586faa4bd87fc97ad9c30f3661caaaf8ac6d005a95f6'),
    ('ipc.ring-wrapper', 'kernel/asterinas/kernel/core/src/util/ring_buffer.rs', 'c4c98b949380893cc71b02182e27db7286413766931b5d9c82b44f56a623c15e'),
    ('ipc.ring-crate', 'kernel/asterinas/kernel/libs/ring-buffer/src/lib.rs', '5e3375c47397446479681274e2a8bce3c7e778b9e4291eb97b4410fea2494839'),
    ('oracle.probe', 'tests/kernel/network/unix_stream_probe.c', 'bb7e334a76c4e201b3ef33842be7f87a235a6940d783c8c741d63839519ab747'),
    ('oracle.protocol', 'tests/kernel/network/unix_stream_protocol.json', '6577cd26c72c80f370cd4a654463316bf7fa5227a33a0e9ff3ade0e05eb9e680'),
    ('sched.mod', 'kernel/asterinas/kernel/core/src/sched/mod.rs', 'ebe89abfadcf758e40776371da5fa420059858ae207b28ffc5ab76f79ee31322'),
    ('sched.nice', 'kernel/asterinas/kernel/core/src/sched/nice.rs', '1a898d63a4899a8d6b19bdd893f0d55af8c2fd382090a675591ccab1e7e1a614'),
    ('sched.sched_class.mod', 'kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs', '282634bbf139fb3e172290b2326ea4693b60eb2070e9e34a20243c2f850731e9'),
    ('sched.sched_class.administration', 'kernel/asterinas/kernel/core/src/sched/sched_class/administration.rs', '6d849d0ea650e2d5d388b12a51f92807ef875fe6024e76b46a4b966376a05f50'),
    ('sched.sched_class.affinity', 'kernel/asterinas/kernel/core/src/sched/sched_class/affinity.rs', 'ad5af5fecb7b98a26f8915b7a96d888a28afbfd3c7a6641142a814a809263c35'),
    ('sched.sched_class.capacity', 'kernel/asterinas/kernel/core/src/sched/sched_class/capacity.rs', '989483aef47ea9f52030abcf2c5bd8dffe8a9c21b4a5e8d43ca91d9b69368275'),
    ('sched.sched_class.clock', 'kernel/asterinas/kernel/core/src/sched/sched_class/clock.rs', '3fb6e0f2489d6b46af702626e68a9734a0ecb334211425b0511790822362988f'),
    ('sched.sched_class.fair', 'kernel/asterinas/kernel/core/src/sched/sched_class/fair.rs', '693cbaf94ac26e167e4b7070c54cd685d18d0dcbc8c936285fb0c79148e89cc7'),
    ('sched.sched_class.fair.group', 'kernel/asterinas/kernel/core/src/sched/sched_class/fair/group.rs', '6acf57821fd9e9276ec226bc5a35afb7247b681c1f5a2d92bc444a00a111eff0'),
    ('sched.sched_class.fair.group.prepare', 'kernel/asterinas/kernel/core/src/sched/sched_class/fair/group/prepare.rs', '8feb3552b4fde62f9b457653c155554dc670310c48a7267455d250962c72d9c9'),
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
    ('cgroup.controller.mod', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/mod.rs', 'bffe21bb82852c168799a753f5b1b33d1ca9746d34de17503342512a1ac2a471'),
    ('cgroup.controller.cpu', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs', 'd1a05a4afe1660b9c4a36f55d6de8f00faa7eac695a3a895981df186b0b760d7'),
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
    ('inherit.thread.mod', 'kernel/asterinas/kernel/core/src/thread/mod.rs', 'ea5846bf7ca82c80de7239dcbf1a7127ef589851cca5d36bfce79a0c00aafe13'),
    ('inherit.thread.kernel_thread', 'kernel/asterinas/kernel/core/src/thread/kernel_thread.rs', '38fc03338818f36eedebfee305ff3efbf642b9370dccb88ed202b5212dda47a9'),
    ('inherit.process.clone', 'kernel/asterinas/kernel/core/src/process/clone.rs', '897f43adb87cd408a7b73bdd2b78309b06cbeaac1573fa2d013f8fa29b3000b7'),
    ('inherit.process.posix_thread.builder', 'kernel/asterinas/kernel/core/src/process/posix_thread/builder.rs', 'f4f28ecde3b98c2fb82cf9e1e331b89b3a16d704fee973ca997fde1ffc9a16ef'),
    ('ostd.sync.wait', 'kernel/asterinas/ostd/src/sync/wait.rs', '598266d76fbd90a1b3731d1107d46cb198a0cabfa1773ced70061d2e01af8f11'),
    ('ostd.sync.spin', 'kernel/asterinas/ostd/src/sync/spin.rs', '8d0b331b7ad31a61ba41fb838103d75c606d4709027d13782afd61eade294207'),
    ('ostd.sync.mutex', 'kernel/asterinas/ostd/src/sync/mutex.rs', 'e28ffd1297d74bc172d35951ec4442e8d84f7c2dc939145f449e0b6efef2f21a'),
    ('ostd.sync.guard', 'kernel/asterinas/ostd/src/sync/guard.rs', '9100d92d3214b3d3e9fcd08267ecdda3c4b2dcc25224e97a81ab39860ebedb58'),
    ('ostd.irq.guard', 'kernel/asterinas/ostd/src/irq/guard.rs', 'd314d4217b1d694b2ff1e2f193a8059fc3b5e7763d5c88329ce94b06cdf11622'),
    ('ostd.task.mod', 'kernel/asterinas/ostd/src/task/mod.rs', '973b4e149c50c2d4cbbd547472a54f548bcb407e213a78a1b1f235609fa7aa6d'),
    ('ostd.task.atomic_mode', 'kernel/asterinas/ostd/src/task/atomic_mode.rs', 'e9998f8ec7eebea34adeb2381e4ed5102861ec4254f9454f9f5187c15c293f3c'),
    ('ostd.task.processor', 'kernel/asterinas/ostd/src/task/processor.rs', '1a17aa136264d10b51c8c25a9e0d61167072c43a986c358762ef5a03bcca76fb'),
    ('ostd.task.scheduler.mod', 'kernel/asterinas/ostd/src/task/scheduler/mod.rs', '59a837d5480ff1636f0dbbc3f8cda6c02331eb01fbd5ebd4043fd94880f0fd43'),
    ('ostd.task.scheduler.info', 'kernel/asterinas/ostd/src/task/scheduler/info.rs', 'aeb4528febcc166b25882061b3f4afc93e4960a4a651e0423463db4dada7eba9'),
    ('ostd.task.preempt.mod', 'kernel/asterinas/ostd/src/task/preempt/mod.rs', '4abe7cde72c9daa7e1d3332e88d23f5f65a2c5ac489f2bf264222916486b4215'),
    ('ostd.task.preempt.guard', 'kernel/asterinas/ostd/src/task/preempt/guard.rs', '38a8b628b7c3fa462b3549b5e5d41eecd42185150b8e6572da09f4dec4a02faf'),
    ('ostd.task.preempt.cpu_local', 'kernel/asterinas/ostd/src/task/preempt/cpu_local.rs', 'f37ed91e1ec3701e46727d546da5bd647271fd196f1580fcfbb667b00d221f48'),
)


def verify_engine(data):
    if hashlib.sha256(data).hexdigest() != ENGINE_SHA256:
        raise ValueError("historical Unix engine bytes changed")


verify_engine(ENGINE.read_bytes())
spec = importlib.util.spec_from_file_location("_receiving_unix_engine", ENGINE)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
original_required_sources = engine.required_sources
original_profiles = engine.SOURCE_PROFILES


def required_sources(variant, source_profile):
    if source_profile != PROFILE:
        return original_required_sources(variant, source_profile)
    engine.require(variant == "positive", "historical mutations cannot use receiving profile")
    roles = [role for role, _, _ in OWNERS]
    paths = [path for _, path, _ in OWNERS]
    engine.require(len(set(roles)) == len(roles) and len(set(paths)) == len(paths),
                   "duplicate receiving owner role/path")
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
