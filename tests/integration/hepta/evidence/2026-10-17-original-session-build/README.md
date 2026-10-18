# 原版库 / 持续 Session 探针的锁诊断与真实链接

`build-02` 已实际通过 observer 构建、首次 Cargo 解析、两次连续 `--locked` metadata、原版库探针链接和两项 Rust 失效状态测试。六条命令均 exit0。运行时间为 2026-10-17 22:35:58–22:40:14 UTC；其中真实 probe 链接约 3 分 52 秒。该结果绑定本地桌面 `c50d7b9b688135a22ced2f7f3cbe21c3028d8e17`，同完整 tree 的远端为 [`028b664b4717c4dffc03dc638fa3e9a5d7a0b52a`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/028b664b4717c4dffc03dc638fa3e9a5d7a0b52a)，tree `1b606b1922751fe938fa4bcca0a923516323f418`。原版 Hepta 仍为干净的 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`。

这是实际构建与两项 Rust 测试证据。原版 Agentd、持续 Session 和 Shell 的真实运行另外归档；本目录不把一次成功链接算作运行通过，也不把复用产物算作每个后续 evidence HEAD 都重新构建。

## 真实失败与修复

| 原始目录 | 结果与含义 |
| --- | --- |
| `build-01` | failed。observer 与 metadata 成功，随后 probe 的 `--locked` build exit101，提示锁文件需要更新；没有进入新探针的 Rust 编译或运行。该次仍绑定 `9d2ef72a` / 同树远端 `f0924a6e` |
| `lock-diagnostic-01` | 复现 Cargo 排序不稳定：一次 locked metadata 成功，接下来 unlocked metadata 只移动一个重复 `[[patch.unused]]` 块，再下一次 locked metadata 拒绝。733 个 package 条目不变，原始 before/after 锁和差异保留 |
| `lock-diagnostic-02` | 仅在外部 probe 根 manifest 去掉完全相同且未使用的 SSH patch alias 后，首次解析及两次连续 locked metadata 通过。733 个 package 条目和实际 resolve graph 完全一致；只规范化了外部 probe 根目录路径。该结果自身仍只是 metadata 资格 |
| `build-02` | 使用修复后生成器进行真实六步执行，全部通过，并生成下列实际 ELF；最终锁摘要不变，源码、helper 和原版 Agentd ELF 前后校验一致 |

原版 workspace 中的同一 patch 仍保持原状；这个省略规则只适用于外部探针，并拒绝别名映射不同、被省略 target 变为活跃依赖、SSH origin 仍活跃或 unused target 数目不正确。详见 [PROBE_LOCK_STABILITY](../../PROBE_LOCK_STABILITY.md)。稳定探针锁 SHA256 为 `72cb7346158f4c3514922cc7b9020f9b9d290aec78e047264a738d52afe6ed68`；规范化实际 resolve graph SHA256 为 `1dd8dc978f55fbdd2b8c90551eaadcfe6a5b3709a82fc108de7cdc5d355e04bd`。

## 实际 ELF 与测试

| 程序 | 字节数 | SHA256 |
| --- | ---: | --- |
| 固定原版 `codex-hepta-agentd` | 329,001,344 | `f476f9bb435c5127839c48ae7135d5a6fa7695ff5253460fdd8d19d7b084d4fa` |
| 本项目 `hepta-observe` | 13,883,672 | `de5aa738234b7ebfdf35afb5e78cf0296962f76625ae1e3fffdc44ba682b7a55` |
| 链接原版库的 probe | 29,114,728 | `46c8f20bef00d5e4b76ae7fcba784937bc1c4d9a33d6b416cd4acc1b96d43365` |

三者均为实际 Linux x86_64 ELF64。Agentd 来自已单独保留的 native build03，并未在 consumer build02 重编译；其 source/lock/ELF 绑定被重新核对。observer 使用 Rust 1.88，原版库探针使用 Rust 1.95；两者均采用锁定、离线构建。最小采样磁盘余量 1,183,633,408 字节，既有 700 MiB 磁盘保留与 7 GiB 非可回收内存停止阈值未被触发或降低。成功使用已有 target，不授予冷构建耗时或最低配置资格。

两项实际 Rust 测试分别验证：受控 stop 可以在最后一份 Running 观测之后发布真实 Draining；进入 stale 后不能重新绑定 spawn、清空历史、伪称新观测或回退代次。`build-02/probe-stale-tests.log` 保留完整命令输出、原版依赖的五项 dead-code warning，以及 `2 passed; 0 failed; 0 ignored; 0 filtered out`。原版 warning 没有被改源码消除，也不被表述成新 probe 编译失败。

## 归档校验

`MANIFEST.json` 保留 56 个原始输入文件的来源、原始字节数/SHA256、归档路径、编码和归档字节数/SHA256；共 36,446,280 原始字节压为 3,400,410 字节。每个 gzip 文件均已解压回读并核对原始摘要；重复日志与锁保留原目录名称。`helper-v1` 与 `helper-v2` 各自保留，不改写第一次失败的工具来源。完整原版 seed manifest、lock 和 toolchain 同样保留。`independent-review.json` 是独立审读实际 source、receipts、日志、锁、三个当前 ELF 和两项测试后的结论。`SHA256SUMS` 覆盖本目录全部其他文件。

本目录不含 ELF 文件、编译缓存、模型请求或原版私有运行状态。后续 runtime helper 只有在原版 source/ELF、probe 两份 Rust 源码和 observer 编译输入均逐字节一致时，才可复用这些产物；新的 Shell/Session 还必须另行匹配自己的实际 UI build receipt。
