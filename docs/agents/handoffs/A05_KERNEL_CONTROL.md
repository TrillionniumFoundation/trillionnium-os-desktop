# A05 内核控制实现与开发入口

核对基线：`146dedf75c5729ef1930c845eeb60e31e8111c60`，2026-10-17。已包含 [PR #148](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/148) 的进程 / exec 镜像身份隔离。
实现 owner 为 A05；A00 维护本接合手册，跨进程/调度接口由 A00 协调 A05/A06。
本文记录当前实现与可执行入口，完整 wire 和恢复语义仍以 [NATIVE_ABI](../../NATIVE_ABI.md) 为准。

## 1. 当前可用范围

主干有真实 `/dev/hepta-control` 字符设备，复用 `libs/os-abi`，只支持只读 `QueryAbi`。
实际 `Process` 持有 `(exec_epoch, nonce)`；同进程、同镜像的多次 open 与 dup 使用同一 space ID，fork 子进程首次新 open 时取得不同 nonce。nonce 使用 boot 内全局、溢出拒绝的 u64 分配器，不再使用 PID / 截断启动时间，也不是每次 open 重新分配。
control file 保存 `Weak<Process>` 和打开时的 epoch：外进程复用 fd 返回 `EPERM`，同进程成功 exec 后旧 fd 返回 `ESTALE`。这是只读身份隔离；完整 CapSpace 能力授予、管理 / 观察权限和撤销仍需可信启动接合。
`ReadUsage`、`InstallBudget`、`QueryDelivery`、`RetireThrough` 在主干返回 `EOPNOTSUPP`。
root:root/0600 的打开边界不授予未来的预算或历史管理能力。

普通 read/write 返回 `EINVAL`，seek 返回 `ESPIPE`；当前实验 ioctl 是 `_IOWR('H', 2, 32)`，值 `0xC0204802`。
这个编号不是已发布的稳定用户 ABI。增加操作支持位之前，须接完该操作的实际身份、owner 和恢复路径。

## 2. 实际源码与调用顺序

以下路径相对仓库根：

| 路径 / 符号 | 当前职责 |
| --- | --- |
| [hepta_control.rs](../../../kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs) / `init_in_first_kthread` | 初始化 boot ID，登记字符设备 |
| 同文件 / `HeptaControlDevice::open` | 从当前 Process 取得镜像身份，保存弱引用和 epoch |
| 同文件 / `HeptaControlFile::check_session` / `ioctl` | 检查精确 Process Arc 身份和 epoch，再复制有界请求、消费唯一 codec、构造 QueryAbi 回复 |
| [syscall/ioctl.rs](../../../kernel/asterinas/kernel/core/src/syscall/ioctl.rs) / `sys_ioctl` | 从实际调用 Context 取得文件引用，释放 file-table 借用后分派 |
| [process/process/mod.rs](../../../kernel/asterinas/kernel/core/src/process/process/mod.rs) / `hepta_capspace_session` | 同锁下读取 epoch 和缓存 nonce；全局分配时拒绝 u64 溢出 |
| [process/execve.rs](../../../kernel/asterinas/kernel/core/src/process/execve.rs) / `advance_hepta_exec_epoch` | 成功镜像替换后轮转 epoch、清空 nonce 缓存；epoch 耗尽时失败终止，旧 fd 不恢复有效 |
| [CPU controller](../../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs) | A06 已有的唯一 CPU 配额与统计事实 |
| [os-control API](../../../libs/os-control/API_CONTRACT.md) | A03 的身份、投递、原 owner 绑定和锁后端接口 |

当前 ioctl 先验证命令和打开进程 / 镜像身份，再复制一次32字节 transport，限制已知请求为 `HEADER_LEN + 40`，复制完整输入后再解析。
输入和输出可以重叠；后续用户修改不能改写已复制快照。QueryAbi 回复经同一 Rust codec 编码再 copyout。
当前无资源写效果，因此失败 copyout 不会产生预算效果；这不能直接外推到未来 InstallBudget。

## 3. 错误、锁与权限边界

| 错误 | 当前含义 |
| --- | --- |
| `ENOTTY` | 未识别的 ioctl 命令 |
| `EPROTONOSUPPORT` | 协议 magic/version 不支持 |
| `EOPNOTSUPP` | opcode 未知，或已知但设备路径尚未实现 |
| `EMSGSIZE` | 回复容量不足 |
| `EINVAL` | transport/请求结构不合法等 |
| `EFAULT` | 用户输入/输出内存访问失败 |
| `EPERM` | 没有当前进程、打开 owner 已失效，或调用方不是原 Process |
| `ESTALE` | 原 Process 已成功 exec，打开时的 epoch 已过期 |
| `ENOSPC` | open 分配进程镜像 nonce 时全局序号耗尽 |
| `EOVERFLOW` | 成功 exec 后轮转 epoch 耗尽；该路径使进程失败终止，不允许回绕 |

nonce / epoch 的耗尽处理是当前源码路径，不表示已运行真实耗尽或 SMP 压力验收。

用户 copy 不能在未来的 IRQ/spinlock 或资源 mutation 锁内执行。
A03 的 `LockBackend` 是可用接缝，host/Loom 结果不证明 Asterinas 的 IRQ/抢占/SMP 锁序。
当前身份使用实际 Process 与镜像 epoch，不允许回退到 PID、截断 start_time 或用户提交的 workspace。
fd 的 dup/fork/SCM_RIGHTS 继承与能力授予分别处理；当前已拒绝跨 Process / 旧镜像会话，但可信启动再激活和实际管理能力仍按统一规格实施。不能把只读 ioctl 的身份检查直接当作未来写操作的完整授权线性化证明。

## 4. 构建与宿主回归

固定输入为 Asterinas v0.19.0 / `nightly-2026-07-21`，见 [A01 构建手册](../../../support/build/README.md)。
在已配置依赖的独立 checkout 中执行：

```bash
python3 support/build/verify-source.py
bash support/build/kernel.sh kernel
sh tests/kernel/control/run-host-smoke.sh
python3 -m unittest discover -s tests/kernel/control -p 'test_*.py' -v
```

`kernel.sh` 将具体命令、工具链、源码身份、退出码和产物记录在本次新建的输出目录。
host smoke 编译并运行用户态协议负例，包含对 Linux `/dev/null` 的实际 ioctl 与 ENOTTY/EFAULT 区分；它不访问 Asterinas/HOS2 设备，成功不能替代 guest ioctl 验证。
构建报错先核对生成 OSDK crate 的锁文件、vDSO 和实际符号 ELF 路径；不要从猜测的 `target/.../asterinas` 路径找产物。

## 5. 客体重放与调试

[run_queryabi_guest.py](../../../tests/kernel/control/run_queryabi_guest.py) 提供一次性、无数据盘/host网络的 QEMU 重放。
先运行 `python3 tests/kernel/control/run_queryabi_guest.py --help` 查看实际参数；该入口仍固定一个历史 A05 ELF，以及 A01 initramfs/SeaBIOS 的独立 hash。
它不是接受任意新 ELF 的通用启动器。不能把命令行传入的新 hash 当作独立来源核验，也不能仅改常量就声称新的 fork/exec 权限验收成立。
新候选必须由 A05/A00 绑定完整源码与输入，再运行对应实际 probe 并保留新的原始结果。

调试时分别保留 guest 的 `HEPTA_QUERYABI_OK`、A01 boot marker、QEMU raw exit 和无 panic 检查。
raw33 是该退出设备的正常客体完成码；应使用 runner 结果判断，不将任意退出码或单独日志标记当成功。
复现边界参考 [已集成 A05+A06 收据](../../../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json)。

最新 [进程镜像隔离组合收据](../../../results/kernel/control/a05-main-combined-acceptance-20261017.json) 另绑定组合 tree `4b486eba185dad538e8578fb6c33916907a82cdf` 与 ELF `96b12e32ac4db1b65ff026f4576b673643cdf0d18b0836713d67ca689a4a673c`：单 vCPU 客体的 fork / exec / nonce / 非 root / dup 等标记、5 项配额和 153 项 aster-core ktest 已有执行记录。这里引用既有收据，本次文档修订没有重新运行这些 QEMU 测试；该新 ELF 不等于上面 runner 的历史固定 ELF。

## 6. 下一项实现与验收

1. 维护已合入的 Process / exec_epoch / nonce 身份与既有 fork / exec / dup 客体回归；扩展到完整能力生命周期和并发交错，不重做另一套身份源。
2. 通过可信启动记录建立管理/观察能力，不能由 open 自动签发权限。
3. 让 ReadUsage/InstallBudget 消费唯一 cgroup owner，并接 A03 的投递去重、原 owner 绑定和锁后端。
4. 证明丢响应重取、相同 D 改内容拒绝、旧 revision、撤销与最终 CPU 计费的真实交错。
5. 接通 QueryDelivery/RetireThrough；由原 Hepta owner 持久确认后退役，重启/历史丢失保持未知语义。

每个实现候选分别报告 host、QEMU、SMP、实机和持久 owner 测试，不继承本手册基线或其他 Draft 的通过状态。
