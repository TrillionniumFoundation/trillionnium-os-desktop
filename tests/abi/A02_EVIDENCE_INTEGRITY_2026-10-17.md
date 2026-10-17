# A02 编译变异证据完整性验收（2026-10-17）

代码提交：`76c1005b0752f9026dc015172f577667d70bfc47`。实际 main 基线：
`1247d30b2a8d82598482512f4d614b622499e541`。分支 `agents/A02-hos2-wire`。
执行宿主 `24f0ea2620fe`，Linux x86_64，Python 3.12.14；使用项目现有
`nightly-2026-07-21`（rustc 1.99.0-nightly，87e5904f5）。未安装替代工具链。

## 修复内容

旧外层验收只看 v6、success 和 20/20 汇总；子报告即使没有 mutant、缺少
baseline 或声称编译失败，也可能通过。现在复用现有变异定义与 Rust 输出解析器，
核验五个完整 baseline、20 个唯一变异身份、逐项源码摘要、输入与固定样本摘要、
编译 exit0、运行 exit101、指定失败测试及与 baseline 相同的完整案例集合。

工具链核验重新检查原始探针命令、整数退出码、超时、错误与版本输出，并绑定外层
已选择的 Cargo/RUSTC 及其解析路径。缓存的 valid/killed 标记不能替代原始事实。
格式错误的 JSON、bool 退出码、遗漏或矛盾的执行证据均拒绝。

生产 Rust codec、Cargo.toml、Wire 字段、黄金字节、依赖和根 README 未修改。
新增可执行改动仅三份 `tests/abi/**` 文件；没有第二套协议解析器或投递状态机。
已有 `libs/os-abi/src/lib.rs` 是唯一依赖为空的 `#![no_std]` 显式字节 codec，
支持 32B transport、64B HOS2/HOSR 头和全部五个操作。

## 实际结果

| 检查 | 本轮结果 |
| --- | --- |
| 固定 nightly 完整验收 | 13/13，0 未执行 |
| Rust 单元／集成测试 | 74/74，0 失败、忽略、过滤 |
| Rust doctest | 1/1 |
| Python 全套，普通／`-O` | 各 60/60，0 失败、错误、跳过 |
| 独立 Python cap/revision 等变异 oracle | 9/9，已包含于 60 项 |
| 独立固定黄金生成器 | 12 原始＋24 边界＋1 transport 全部匹配 |
| 编译型 Rust 源码变异 | 20/20 编译成功且被完整指定套件抓到 |
| 五个编译型 baseline | 8＋12＋7＋5＋21＝53 项通过 |
| fmt、严格 all-target Clippy、bare no_std | 全部通过 |
| 输入完整性、README | 28 个输入与代码提交逐字节匹配；README＝0 字节 |

20 个 Rust mutant 共触发 29 个预期断言失败；它们是正确捕获错误的负面控制，
不算生产失败。忽略 cap 或 expected_revision 的两个实际源码变异各触发两个
指定断言失败。编译失败、超时和测试过滤均不能计为 kill。

旧汇总 wrapper 在新增回归中有 **17 个预期 subtest 失败、0 执行错误**；开发中
首版证据检查器在原始探针／路径／案例身份回归中有 **6 个预期 subtest 失败、
0 执行错误**。这些控制使用模拟 subprocess，不能计为 Rust 编译结果。
最终修复经独立复审，真实完整旧报告仍被接受，上述反例均被拒绝。

```sh
RUSTUP_HOME=/workspace/scratch/629ae4947f18/toolchains/rustup \
python3 -B tests/abi/run_acceptance.py \
  --rustup /workspace/scratch/629ae4947f18/toolchains/cargo/bin/rustup \
  --output-dir /workspace/scratch/8e8c65a24673/a02-final-acceptance
```

另实际执行用户指定的 `cargo test --manifest-path libs/os-abi/Cargo.toml`，
使用同一固定 nightly 和独立 CARGO_TARGET_DIR，亦为 74＋1 全通过。
完整验收已分别执行独立黄金生成器和 `test_mutations.py`，不是同 codec round-trip。

三份原时间问题样本保持：ReadUsage sample=150ms、start=100ms、consumed=35ms、
cap=20ms；InstallBudget／terminal history effective=140ms、consumed=33ms。
35ms≤50ms、33ms≤40ms，且保留合法降额后的 35ms>20ms。

## 原始执行记录

- [完整验收及命令输出](results/evidence-integrity-acceptance-2026-10-17.json)
- [20 个编译型变异完整输出](results/evidence-integrity-mutations-2026-10-17.json)
- [旧汇总检查的预期失败](results/evidence-integrity-summary-before-2026-10-17.json)
- [首版身份检查的预期失败](results/evidence-integrity-identity-before-2026-10-17.json)
- [宿主、源码提交、28 个输入及报告 SHA256](results/evidence-integrity-execution-2026-10-17.json)
- [协议提案的 Rust 源码、编译命令及 13 个 raw/typed 案例](results/a00-protocol-counterexamples-147-2026-10-17.json)

## 待 A00 决策的共享语义

[Issue #147](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/147)
给出两个问题的具体字段、已编译反例和建议：

1. N0 是否还必须满足 `cumulative_cpu_ns - window_consumed_ns <= window_start_ns`。
   当前可接受 sample=150ms、cumulative=140ms、start=100ms、consumed=35ms，
   却隐含前 100ms 消耗 105ms CPU。
2. QueryDelivery 对不可执行 MAX 序列的 Reserved／Terminal／Retired，以及
   terminal 保存 OutOfOrder／Retired 的语义，与 A03 现有映射约束不一致。

这些协议选择尚未解决；依用户要求等待 A00 统一决策后再修改实现和黄金样本。
本 PR 不自行收紧共享 ABI。Issue #104 已经批准并合并的 cumulative≤sample
约束仍有效。共享 `docs/VALIDATION.md` 的旧实现状态描述也已请 A00 更新。

## A03／A05 接口交接

| 接口 | 使用边界 |
| --- | --- |
| `Request`／`Response` 与 encode/decode | 拥有值的显式字节 codec；不传 Rust 内存布局 |
| `Transport::decode_request_snapshot` | 校验完整已复制输入、地址算术和成功响应容量后，才进入语义准入 |
| `Transport::decode_response_snapshot_for` | 约束实际响应快照容量，并校验请求关联 |
| `decode_response_for`／`decode_response_prefix_for`、`Response::validate_for` | 校验语义关联；`matches_request` 仅比较 opcode/ID |
| `install_budget_request_id`／`install_budget_sequence` | 低 8 字节 LE 顺序号，高 8 字节全零；拒绝 0 和 MAX |

接口签名未变化。所有错误响应也必须事先具备该操作成功响应容量。EFAULT 后整个
输出不能作为有效结果；真实用户地址访问、boot/CapSpace 认证、权限、预约与退役
属于 consumer。HOS2 仍是实验 major=2/minor=0；本轮通过只证明宿主 codec／证据
检查，不证明内核 syscall、驱动、授权、调度或真实 Hepta 持久效果已实现。
