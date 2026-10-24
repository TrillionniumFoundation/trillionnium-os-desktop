# Asterinas 后端：organ 边界与实际验证

当前实现更新：下文的 CPU 配置反例与原运行记录属于其固定历史源码。后续 `cpu.max`
已接真实调度计费/资格/节流路径；`cpu.weight` 仍无 group-weight 调度，当前
[写合同](agents/CPU_WEIGHT_UNSUPPORTED.md)明确返回 `EOPNOTSUPP` 并保持读值 `100`，
不再接受只存值的假策略成功。`memory.max` 也已有[原层级用户数据/选定IPC帧准入](agents/CGROUP_MEMORY_ADMISSION.md)，
不是完整回收/OOM。历史反例不应继续用来描述这些后续实现，也不转授其新执行资格。

日期：2026-10-16。此变更保留 Asterinas/OSTD 主线，不新建 HOS3，不复制 Hepta organ 宿主或持久账本。本页是本轮新增的事实与接合要求，不能把当前 PR 的产物提前算入 main。

## 1. 确定的架构边界

Hepta 决定授权范围内的目标和策略；OS 后端负责实际资源执行、地址空间、设备和本地恢复。Asterinas 是多个现有 organ 角色可共用的具体执行后端，不是可以直接塞进只读 OrganHost 的硬件 handler。

固定 Hepta 的 `TrustedReadOnlyOrganV1` 明确禁止 I/O、持有能力、启动工作与外部效果。观测采集必须在既有 owner/适配器中完成，进入只读图的是有界快照。真实修改仍沿 authority/operations/实际效果适配器执行。这里不修改 Hepta 原仓库、不扩权、不引入第二执行主链。

只读 organ 替换、用户态服务替换、调度策略变更、驱动解绑与整内核更新是不同生命周期。OSTD `inject_scheduler` 是启动期的一次性注入；预算在稳定调度器内部更新，不通过重复注入或重启模型实施。整内核初期通过可回退重启更新，不承诺任意无损热替换。

## 2. 本轮不是再次只看源码

### A01 启动产物独立重放

在独立工作树读取 A01 PR #5 的精确提交 `b14e46105cd892f5e1186a46f1dcfc1ae270420a`，解压并核对已提交 kernel ELF、原始 initramfs 和本机 SeaBIOS 的哈希，然后以 q35/TCG、1 vCPU、512 MiB、无网络与数据盘重新启动。

实际 raw QEMU 返回33，来宾 CPU=1 与 `TRILLIONNIUM_A01_BOOT_OK` 标记均存在，无 panic。内核 ELF SHA256 为 `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63`。

这证明本轮重新运行了相同内核产物，不证明本轮从源重新构建、跨机器位级可复现、KVM、裸机、HOS2 或完整兼容。源码构建证据仍归 A01 原 PR。

### 实际 CPU 配额反例

新增 [客体探针](../tests/organ_backend/cpu_cap_probe.c) 和 [重放入口](../tests/organ_backend/run_guest_probe.py)。runner 核对固定内核/原始 initramfs/固件，用内存 newc 解析器生成独立测试 initramfs，不在宿主解包路径，也不修改宿主 cgroup。C 是未修改内核上的 Linux ELF 验证程序，不是用 C 重写内核。

探针创建来宾专用 cgroup，写入并读回 `cpu.max=1000 100000`，核对自身实际 cgroup 归属，再运行相同 CPU-bound 任务。观察如下：

| 运行 | 客体墙钟 ns | 客体 CPU ns | 循环迭代 |
| --- | ---: | ---: | ---: |
| 不限额 | 1,000,149,453 | 997,000,000 | 193,300,000 |
| 已配置1% cap | 1,000,128,020 | 998,000,000 | 194,400,000 |

写入警告也真实出现：`cpu.max` accepted but not enforced。配置后仍消耗约99.8%的单 CPU，而不是1%。本实验的宽松判据仅用于发现严重未执行，低使用率不会被直接认定为严格配额通过。结果为 **NOT_ENFORCED / qualification_passed=false**；runner退出0只表示诊断完成，不能将其作为内核能力绿灯。

初次探针误以为 `/proc/version` 必须含 Asterinas 名称，因上游为兼容返回 Linux 字样而拒绝，导致测试 init 退出；此失败保留在 cpu-probe-01。修正为 runner 检查真实 ELF 哈希，并给一次性 initramfs 写入私有标记；程序还要求固定 Rust 构建标识。标记是防误操作保护，不是远程证明机制。cpu-probe-02 才是完整观测。

### A02 编译与实际修复

独立读取 PR #4 的 `eb864e8cabe803c8d5d86bfd27b6e51e2b28f907`，使用本机 Rust/Cargo 1.95.0，offline 运行。原5项测试与release构建通过；严格Clippy出现collapsible_match错误。

新增两项回归后，证实请求接受 `expected_revision=u64::MAX-1`，但成功响应及历史结果误拒绝 `previous_revision=u64::MAX-1`。将边界从 `>= MAX-1` 修正为拒绝 `MAX`，保留不回绕规则；同时修正guard写法并格式化。修复后7项测试、release、strict Clippy、fmt均通过。源码修复以独立分支、针对A02分支的叠加PR交付，不覆盖其工作树或冒充已经合入main。

## 3. A05/A06/A07 的实际接合要求

A05：绑定真实任务与能力身份，但不要把“内核接受配置”宣称为“资源执行成功”。原生入口、Linux cgroup与可信恢复入口必须抵达同一资源状态及权限边界。保留资源revision、配置来源与恢复原因的一致性。

A06：必须在公共可运行资格、实际计费、节流和timer唤醒处补真实CPU限制。现有cgroup统计可复用，不能平行维护第二份额度。`cpu.max`和`cpu.weight`现为配置存储，非现成限额机制；内存controller仍有未实现属性，不能报告有强制内存上限。先用本探针建立失败基线，再补准确误差界、父域、同值更新、其他调度类和恢复测试；低于宽松反例阈值不等于完整验收。

A07：不能在`TrustedReadOnlyOrganV1::handle`里执行ioctl或持有控制能力；快照采集和最终效果执行使用既有owner的窄适配。SQLite提交、内核效果、结果确认和退役分别验证；禁止将图路由或driver digest解释为权限/完成证明。

继续保留Asterinas完整派生。只有出现可复现的对象/权限/故障隔离结构冲突，再考虑替换服务核心或以OSTD实现新上层；CPU配置未执行本身还不是丢弃全部内核的理由。

## 4. 复跑与结果

```sh
python3 tests/organ_backend/run_guest_probe.py \
  --a01-tree /absolute/path/to/checkout-at-b14e461 \
  --output /absolute/path/to/new-disposable-result-directory
```

需要现有cc静态链接能力、QEMU、匹配固件；脚本不安装依赖或使用sudo。固定A01 checkout来自该PR，不是未经核验的移动分支。诊断结束销毁QEMU客体；没有挂载真实宿主设备。原产物和新测试镜像不重复存入本PR，只保存来源哈希、代码、命令和完整日志。

本轮[结果目录](../results/organ-backend/2026-10-16/)保留原始成功和失败。未执行：CPU节流修复、内存限制、效果型Hepta organ闭环、裸机、Android或GPU。main和各PR可继续前进，本页结论只绑定所列提交。

## 5. 精确来源

- [Hepta只读宿主源码](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-control-plane/src/organ_runtime.rs)
- [Hepta层级契约](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-control-plane/src/ORGAN_HIERARCHY.md)
- [固定CPU controller](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs)
- [固定memory controller](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/kernel/core/src/fs/fs_impls/cgroupfs/controller/memory.rs)
- [OSTD调度注入](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/ostd/src/task/scheduler/mod.rs)

源码检查摘要见source-checks.json；静态来源与本轮运行证据分开，不能把静态标记存在当作内核运行测试。
