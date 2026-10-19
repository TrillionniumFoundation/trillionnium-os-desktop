## 为什么需要这项修改

CPU 带宽账本需要和原校准时钟使用同一套纳秒端点，才能提供有明确窗口、累计值和 revision 的一致用量。原调度 cycles 还要独立保留；重复写配置、迟到时间或计费 owner 换代不能返还已经消耗的预算。

## 本 PR 的变化

- 在原 CpuMax / CpuControl 中实现 BOOTTIME 纳秒窗口、累计用量、欠额、高水位和持久记账故障，继续使用同一资源 owner 与配置 revision。
- 原 runqueue 在同一采样切点先结算保留的 owner，再提供私有的同锁 usage 快照；CFS/RT cycles 游标独立。
- 同值写入、降低 quota、周期切换、退出和代际变化均保留原账；时钟回退、不可用、累计溢出使原生快照失败。仅 accounting fault 下的合法 Linux max 管理恢复仍受原 metadata gate 约束，且不清除故障。
- 增加 19 个真实 Process/Task/controller 的受控内核回归；原 201 项保留，七项生产反向控制继续完整执行。三补丁仅适配实际源码；runner 的阈值和判定函数保持原样。
- 增加 G1-b 技术与开发手册，修正 A04 已合入三手册的导航状态。
- 首轮 f966 G0 的一个旧源码字符串断言真实失败；4d 仅修 tests/spec/test_a06_final_accounting_source.py，要求同一 settle_bandwidth 方法先向 retained owner 计费再重绑。产品、工作流、七负控及原 pins 没有随这次修正改变。

## 当前提交的实际验证

执行 head：`4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930`  
tree：`8eb809136a402cc54ba049b1e40dd174308c923f`

五项检查全部成功：[A06](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39240728276)、[G0](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39240728311)、[A01](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39240728231) 与两项 CodeQL 检查。官方 artifact `12182038203` 为 154,979,607 B，SHA-256 `ef5d93159c1663fb30d3cf8e39e969525bbfa03b4fedc4db10ef4c87b035d655`。

| 验证 | 当前提交结果 |
| --- | --- |
| 原源码 / 三普通内核前后快照 | 7,054 路径、mode、Git blob、size、SHA-256 独立逐项一致 |
| 完整 core | 220 passed，0 failed / filtered / soft skip；19 新名完整保留 |
| 完整 OSTD | 221 reported passed，3 明确 VMX soft skip；两套件合计实际执行通过下界 438 |
| 七项生产反向控制 | 完整 220 同名集合，精确失败数 3 / 4 / 3 / 1 / 4 / 1 / 2，原 QEMU 65 / 原 gate 1；候选源码恢复一致 |
| 普通产品 | QueryAbi14、SCM/CLOEXEC27、RLIMIT_NOFILE37、完整 Ubuntu Linux32/guest32、四 CPU 配置及有界 1/2 vCPU 原门禁成功 |

正常套件原 QEMU 33、无 timeout；独立复核读取原始 serial、ELF 与输入绑定。反向控制的检测成功不计入正常套件通过分母。本轮新 CI 独立绑定 4d，没有套用早期本地 WIP 或 #203 的资格。早期失败及原件恢复边界随独立 docs/results 归档保存。

## 尚未开放的能力

HOS2 仍仅 QueryAbi；ReadUsage、InstallBudget、QueryDelivery、RetireThrough 四操作关闭，生产 bootstrap 尚未授予资源能力。这是内部纳秒计费和一致快照切片。最终 Process/exec 授权、原 Hepta Operations 的 K↔D 持久交付、真实 Asterinas Hepta W1、physical switch 原子性、完整 SMP、cpu.weight 与设备/手机资格仍需后续实际验收。

根 README 仍为 0 字节，原 Asterinas、nightly、OSDK 与锁未调整。
