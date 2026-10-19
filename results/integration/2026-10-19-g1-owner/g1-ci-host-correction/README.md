# G1 CI host contract correction：独立审查与真实门禁

## 结论与精确源码

指定的 host 检查全部通过。最终源码为 `bccb817e0d3f1987f59c1b9e7d94e939d2e6d1d3`，tree `65ddb50cd303f3c43a8226141c5298dca369db5d`，独立测试 worktree `/workspace/scratch/499c7902de8e/r10-g1-host-contract-fix` 最终 clean。初始三处修复 `bc778b6b8114e5017a467c0566f5777d85abafaf` 的 allocator 遗漏被真实运行识别，最终第四处最小修复由 root 提交，本代理没有修改产品、测试源码或门禁。

相对 `4e077aef4913179a68aa0d814018ce1a9d87cafc`，最终只有四个测试/配置文件变化。原始 diff、逐项审查结论和输入哈希分别见 `reviewed-source.diff`、`code-review.json` 和 `source-inputs.json`。

## 实际执行结果

| 检查 | 固定源码与时间（UTC，2026-10-19） | 结果 |
| --- | --- | --- |
| G0 ABI fmt | bc778b6，03:29:04 | 通过；唯一后续变化在 allocator runner，ABI 格式化输入完全相同，不重复运行 |
| G0 ABI test / strict Clippy | 最终 bccb817e，03:34:09–03:34:13 | **78 passed**，0 failed/ignored/filtered；Clippy `-D warnings` 通过 |
| G0 control std fmt / test / strict Clippy | 最终 bccb817e，03:34:13–03:34:30 | **225 passed**，0 failed/ignored/filtered；fmt/Clippy 通过 |
| G0 portable-spin test / strict Clippy | 最终 bccb817e，03:34:30–03:34:48 | **225 passed**，0 failed/ignored/filtered；`--no-default-features --features portable-spin` |
| G0 portable-spin rlib | 最终 bccb817e，03:34:48–03:34:49 | `x86_64-unknown-none` 的 `--lib` 编译通过；没有链接或启动内核 |
| A03 原 `run-models.py` 完整两 variants | 最终 bccb817e，03:34:40.292–03:35:35.218 | default shim **13 模型 / 26,675 schedules**；public backend **6 模型 / 578 schedules**；各自 fmt/test/strict Clippy 全通过 |
| A03 原 `lock_alloc/run-checks.py` | 最终 bccb817e，03:34:40.319–03:34:43.147 | **current_zero**；19 个完整场景，内部锁期间 alloc/realloc/dealloc 均 0；两个受控分配失败检查通过 |

std 与 portable-spin 执行了重叠用例，应分别报告两个 225，不能当作 450 个独立场景。所有最终执行收据均绑定 bccb817e 的源码前后哈希和 clean 状态；Loom 的源清单、临时副本、公有 backend 完整原模块及 default shim 唯一替换项均已复核。allocator 保存原生 stdout/stderr、控制事件、生成 manifest 和完整来源哈希；受控 poison/unwind 的 stderr 保留，不将预期控制输出误认成程序失败。

root 的原 spec 日志和 initial-validation 原字节也已收录，实际为 **36 tests passed**，绑定 bc778b6。本代理只独立核对计数和日志 SHA，没有重新运行它，也不扩大原收据对 root 工作树残留文件的声明范围。

## 已发现并保留的失败

1. **真正的遗漏**：bc778b6 的 allocator 原 runner build/format 成功，但生成的 os-control manifest 未登记 `ktest`；`resource_state.rs:163` 的 `#[cfg(ktest)]` 被 `-D warnings` 拒绝。03:27:26–03:27:28 的完整失败和生成 manifest 保留在 `lock-alloc-01/`、`lock-alloc-output-01/`。该轮 runtime 没有执行，不能记为 current_zero。root 的后续提交只添加同款 known-name 登记，保留 warn、unsafe forbid 和严格 Clippy，不启用 ktest。
2. **缺少缓存**：Loom offline 预取找不到固定包。之后只通过原 Cargo.lock 的 `cargo fetch --locked` 补缓存，再离线执行两个变体；原锁和输入未变化，未升级依赖。
3. **本代理的额外参数问题**：ABI crate 无依赖且没有 tracked Cargo.lock；首次给其 test 额外加 `--locked` 导致 exit 101，原 G0 workflow 并无此参数。修正为原命令语义后通过。Cargo 自动生成的锁经检查只含 `hos2-os-abi 0.1.0`，按原字节移入证据目录，不留下 checkout 变更。该失败不能归因于产品修复。

## 四处审查范围

Loom 和 allocator 的 check-cfg 都只登记已知的内核 fixture 名称，未启用它，也未添加 lint allow。prefetch fixture 调用真实 main、固定 Git seed 和 package audits，只替代 Cargo 执行；空的 OSTD metadata 是明确标注的 Cargo-free fixture，不能当作真实依赖解析证明。其 mutation 负例确认锁一旦变化就停止在 metadata 之前。A06 分别约束同一个生成 ELF 的 hash、probe 和 artifact 用途，修正了旧的出现次数假设。

## 工具、保存与未覆盖项

使用原 `implementation-tools/g1-env.sh` 的 `nightly-2026-07-21`（Rust 1.99.0-nightly），仅补装缺少的 Clippy。安装前后原 rustc、Cargo、rustfmt 与 cargo-osdk 二进制 SHA 完全相同，没有重新安装 OSDK。构建 target 和模型临时工作区都独立于活跃 G1 构建；jobs 1、incremental 关闭。

这是 host Rust、bounded Loom 和 host allocator 验证。它不构成真实内核 IRQ/SMP、任意调度/崩溃历史、移动设备控制或远端 CI 门禁通过的证明；本轮没有运行 kernel/device Cargo、QEMU 或触碰设备。两个原 Fleet 修复证据目录的 20 和 25 份交付文件均逐字节复核未变。

`files-manifest.json` 绑定本目录所有原始日志、收据和辅助脚本，排除自身递归哈希、target、工具安装及缓存。全部失败保留。后续远端 CI 观察写入新目录，不改变此快照。
