# A06：奇数 TSC 周期的精确测试判定修复

本次修复仅改变 `cpu.rs` 的 `#[cfg(ktest)]` 测试。实际测试源码为 `0788f3d480751c31ccf202e15f74d85060a6702e`，tree 为 `e379667fdb96d3585cd3b5d45758fe041d76694e`，基线为 main `01caff4fb3651f57ea32e648ade5a351d20df569`。随后增加的证据和说明不替代这个真实执行身份。

## 原 CI 失败及原因

[A06 run 39096189453](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39096189453) 的 job `117583025092`、artifact `12125492767` 对应源码 `9265235c4b4f375844c923cf0b0f517d119d9937`。OSTD 已通过；aster-core 共 159 项，157 passed、2 failed，客体退出码 65，运行 0.715 秒且没有超时。六项 `final_charge_regressions` 均通过。

两个失败来自旧 `quota_debt_regressions` 的期望值：`idle_skipped_periods_never_subsidize_late_burst` 和 `long_continuous_interval_has_constant_time_bounded_debt_accounting`。当周期 P 为奇数时，区间 `[floor(P/2), P)` 的长度是 `P - P/2`，旧测试写成 `P/2`，少计了一个 TSC clock。原 CI 两组实际值 / 旧期望为 `119617125 / 119617124` 和 `1086318781 / 1086318780`。这里的单位是 TSC clocks，并非纳秒。

生产端点记账正确。本次按精确区间长度修复两处期望，未改变容差、阈值或生产算法。新增一个内核测试，以 `4*quota+1` 和 `4*quota+2` 固定奇偶周期，组合 0 / 6 个空闲周期和 0 / 4 个后续完整忙周期，共 8 个确定性边界，用独立的逐窗口端点交集积分验证现有跨周期算法。

## 实际结果

| 执行 | 结果 | 限定 |
| --- | --- | --- |
| 原 Rust `CpuMax` 和原测试，固定偶数周期 | 12 passed / 0 failed | 从基线源码提取，受控 TSC 输入 |
| 原 Rust `CpuMax` 和原测试，固定奇数周期 | 10 passed / 2 failed | 恰好复现原 CI 两项失败及数值 |
| 修复后 Rust 原函数和测试，偶数 / 奇数周期 | 各 13 passed / 0 failed | 新测试内部强制两种奇偶，不依赖宿主校准偶然性 |
| 完整 OSTD 真 QEMU | 221 declared / passed；0 failed / filtered；raw exit 33 | 3 项既有 VMX/EPT soft skip，实际至少执行 218 项 |
| 完整 aster-core 真 QEMU | 160 declared / passed；0 failed / filtered / skipped；raw exit 33 | 新边界、原两项失败和全部六项 final-charge 回归均执行通过 |

完整门禁于 2026-10-18 05:39:44–05:45:37 UTC 执行，使用既有 `support/build/ktest/run.py`、固定 test-base locks、`nightly-2026-07-21` 和当前工作树源码编译的 OSDK。没有测试名称过滤。两客体均为 q35 / TCG / max / 1 vCPU / 512 MiB，分别运行 1.223 和 0.870 秒，没有超时。实际命令、环境、生成锁、原始串口及结果见文字证据包。

受控奇数复现输入为 2,441,165,790 Hz；它能复现原 CI 数值，不代表直接测得了原 aster-core 客体的校准频率。提取的宿主 Rust 测试用于确定性诊断，完整 OSTD / aster-core 客体结果另行报告。

## 源码和产物绑定

唯一源码差异为 [cpu.rs](../../../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs) 测试区，42 行新增、4 行删除。生产区前 25,018 字节逐字节相同，SHA256 为 `e1b678e541a360de694585dfe59b12ac5df0a2ff6aa97261feeeaf63f28459a7`。文件 SHA256 为 `73154f0f42b22a8e3928a848a693b9bdb27d37ed9946db2d1e949ab0e6af3a5e`。

| 产物 | SHA256 |
| --- | --- |
| 实测 OSTD ELF | `83a58bfe68731bf40cffc649e4b6574c8833fe79508647137a881ec557ea57e0` |
| 实测 aster-core ELF | `249b96e4e12f96f1f45daa3b54af7405eedb271fa55a52404c4b8befbbaeac88` |
| OSTD 原始串口 | `9e1a05b6814bcb882a6c5ac27495ead88b06a35a80955e51473946b844766692` |
| aster-core 原始串口 | `5ad6adb985afb8ff976db3c78d2ab14793ab86134b97028d6b1cf0309f189856` |

两份 ELF 已从 target 另存并复核摘要，Git 中提交其绑定信息及完整文字证据。`acceptance-summary.json` 包含源码、锁、工具、客体配置与产物映射。`artifact-manifest.json` 对本目录可提交证据逐文件绑定；`repair-text-evidence.zip` 也在包内逐文件提供 SHA256。`original-ci-39096189453.zip` 是原 GitHub artifact 的未改动字节，SHA256 为 `ffac9492971611eb101f2e1723c0d99fa7656180c80ca126f7ca8b9ddcadf3b2`。

## 本地失败尝试与资格边界

文字包保留全部先前尝试，`repair/attempt-history.json` 区分失败与最终通过。第一次 OSTD 客体通过后，沙箱内 socket send 的独立诊断返回 EPERM，OSDK 关闭信号线程未能完成，runner 失败；它不算完整门禁成功。复用旧 OSDK 又因 `OSDK_LOCAL_DEV` 的编译期工作树路径导致同名 package 路径冲突，因此在当前工作树重新编译 OSDK。

另一独立 Cargo home 通过符号链接复用 registry 时曾出现宿主宏 StableCrateId / E0463。清理 target、在同一执行上下文清理后重跑都没有解决。最终相同的新 OSDK 配合原 Cargo home 完成全部门禁；底层 Cargo/rustc 路径或缓存原因仍未确定，没有提交编译器绕过或内核生产补丁。runner 曾在 finally 校验恢复原 OSDK，但后来再次观察到临时版本，写入者未定位；再用新 mtime 原子恢复后复核原摘要。此事实单列在 `osdk-restoration-followup.json`，不作为产品缺陷结论。

生产字节没有变化，本轮只新执行完整 OSTD 和 aster-core ktests。既有生产 ELF、固定 1 / 2 vCPU probe 和负对照保留在[上一轮执行索引](../../../integration/2026-10-18-audit-followthrough/README.md)，属于历史证据，没有冒充本轮复跑。本修复不新增一般 IRQ/SMP 交错、Hepta/HOS2 控制效果、物理硬件或移动端资格。

复跑时按[内核测试手册](../../../../support/build/ktest/README.md)准备固定依赖、VDSO 和测试锁，再从待测工作树执行 `support/build/ktest/run.py`。默认让 runner 从该工作树编译 OSDK；带本地开发编译路径的旧 OSDK 不能跨工作树直接复用。输出必须是新的独立目录，串口、锁、退出码与完整测试分母继续由原 checker 验证。
