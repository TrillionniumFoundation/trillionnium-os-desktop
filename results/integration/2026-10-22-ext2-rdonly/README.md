# ext2 初始 RDONLY 自动 atime：开发说明与原生验收

本切片修复 ext2 在**初始以 filesystem-wide RDONLY 打开后，普通读、direct read 和 readdir 仍自动更新 atime、产生脏 inode**的问题。修复保留原 sync/writeback，使已存在的 RW 脏数据仍能写回。

2026-10-22 已取得同一正向源码的完整 core、permission SMP、ordinary QueryAbi、同一原 Agentd ELF 的新内核回归，以及只恢复旧 atime 行为的原生负控结果。**负控精确出现三个 RO 回归失败，其余 271 项通过；随后恢复了干净的修复源码。** 当前成果不完成一般只读权限、并发 remount、原 Agentd daemon 启动、原生 G2 或 F。

本目录的收据保留实际运行时身份和原字段；新增发布记录另行绑定公开 Git 身份，不改写先前生成的收据。

## 固定源码与证据

源码已发布到 [PR #243](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/243)，尚未合并；readiness 和 CI 状态见 PR。实际 native 构建 head 与公开 head 相同，不是重新构造的同 tree commit。

| 身份 | 固定值 |
| --- | --- |
| 实际构建及公开 source head | `9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd` |
| 实际 source tree | `eeae4dc1ef546d408b55c98310e99e3156f08207` |
| 直接 parent | `f85ccae8445f8d753572d41411d98ee28d253af5` |
| parent tree | `bad0a3ee66859cfcf7bf1185e4f10d0f953239ad` |
| 实际应用并格式化后的八路径 diff SHA-256 | `13d5185834f968f621ae4639b2e6109e16ebd069a6604e44c53a3c0a136443f6` |
| ordinary product kernel ELF SHA-256 | `8bda1c4876cbfbca0c441adb2d3ac4a91c4b3ff2e9faadedcb3d43503a0b6c09` |

[native-source-identity.json](native-source-identity.json) 是发布前生成的原始记录，故保留 `published: false`；[source-publication.json](source-publication.json) 单独记录后来的实际公开发布，[github-source-commit.json](github-source-commit.json) 保留 GitHub API 返回的精确 `9076f1ae… / eeae4dc1… / parent f85ccae8…` commit object。两者不能按生成时间不同而相互覆盖。该 source identity 仍记录当时实际使用的初版候选补丁摘要；最终源码以实际 applied diff、上述 commit/tree 和各运行输入记录为准。

本地审阅曾基于旧 tree `7389c0a3…` 重建八个路径。那份 partial index 不是本轮完整 `eeae4dc1…`，也不包含 parent 后来新增的全部路径。格式化后的 `attrs.rs` blob 为 `ed811244d13266a950466de407b469b51bd18846`、SHA-256 为 `1dafd642ec22a3c98d4be603b6954b12b83076774b086e1bdd91ffc5e0a953b1`；与封装 revision 2 相比只折叠了 `permission_attrs` import，其余七个源码文件内容未变。

原 [source-independent-review.json](source-independent-review.json) 保留封装 revision 2 的审查身份和实际 host 检查；[formatted-source-review.md](formatted-source-review.md) 与 [formatted-source-review.json](formatted-source-review.json) 保留格式化后八路径及负控前像的复核边界。实际八路径 diff 另存为 [applied-native-source.patch](applied-native-source.patch)。证据提交与源码 PR 分开：下文修复源码和构建入口链接固定到 `9076f1ae…`，不让证据分支中的旧源码代替实际测试实现。

[source-profile-verification.json](source-profile-verification.json) 已对 OS `9076f1ae…` 与原 Hepta `6d6097da…` / `f722fbe5…` 校验通过，绑定[现有 source profile 原件](../../../support/release/profiles/2026-10-22-organ-source.json)的 SHA-256 `260139110c06921db6a156c1f072c55d0a3218f4b8da523b509adad4471e5667`；本目录的 [source-profile-manifest.json](source-profile-manifest.json) 是同字节副本。该工具的资格仍为 **source-only**，不执行 runtime，也不转授 runtime 或生产授权；production activation 为 disabled、effects_authorized 为 false，七项生产配置仍未配置。下面的运行结论各自由独立真实 guest 收据支持。

独立复核见 [native-independent-review.md](native-independent-review.md)、[完整复核 JSON](native-independent-review.json) 和 [ABI 判定器细节](abi-independent-detail.json)：原 checker／serial parser／ABI oracle 重放、正负测试名单、源码恢复和全串口观察均已核对。该复核没有新增 guest 执行；缺席大二进制、两仓 producer receipt 与远端 CI 的边界分别保留。

### 已完成结果

| 门禁 | 实际结果 | 资格范围与收据 |
| --- | --- | --- |
| 完整 `aster-core` | **274 passed，0 failed，0 filtered，0 soft-skip；274 次实际 test start；36 个 required 名称均在收据中；raw QEMU exit 33** | [native-core-positive.json](native-core-positive.json)。包含本次五个新增 ktest，不能用五项定向测试替代该完整分母。 |
| permission SMP | **277 declared，3 passed，0 failed，274 filtered，0 soft-skip；raw QEMU exit 33** | [native-smp-positive.json](native-smp-positive.json)。实际运行的是原三个双 CPU 权限事务测试，不是 277 项全跑，也不是 ext2 并发 remount 验收。 |
| ordinary QueryAbi | **18 个 marker 各一次；C compile exit 0；product wrapper exit 0；两个 raw guest exit 均为 33；7630 个 source 输入保持不变** | [native-ordinary-positive.json](native-ordinary-positive.json)。普通 `ActionChoice::Run`，不启用 `cfg(ktest)`；四个已知控制操作仍按契约拒绝。 |
| 同一原 Agentd、新 ordinary kernel | **原 ELF 到达 Rust main，精确缺少 `HEPTA_FLEET_ROOT` 拒绝；child exit 1；QEMU exit 33；输入保持不变** | [agentd-abi-result.json](agentd-abi-result.json)。完整 shutdown 检查另见下表，daemon/G2/F/production 均为 false。 |
| 旧自动 atime 原生负控 | **274 declared；271 passed；恰好三个 RO 回归 failed；0 filtered／soft-skip；raw QEMU exit 65；原完整 gate exit 1** | [native-negative-result.json](native-negative-result.json)。负控 oracle 通过，不是将原完整 core gate 的失败改写为通过；实际负控身份与恢复结果见下文。 |

core/SMP 的 compact result 不单独重复 source head/tree；其来源必须随本目录的 source identity、完整运行环境/命令和 guest 记录一起读取。ordinary receipt 自身明确绑定完整 head/tree、source count 和前后输入一致性。只复制一段 pass 数字不能重建这个绑定。

### 完整执行归档

[native-execution.tar.xz](native-execution.tar.xz) 保留 **99 个成员、703,464 bytes**，SHA-256 为 `6602d188cf1f236e6e60a84ce36184f8a9560ca766f95e61524702e9a16a5e2d`。[native-execution-manifest.json](native-execution-manifest.json) 为 31,984 bytes，SHA-256 为 `9126a624e0567cf491408be53da5f9dccbc9e9226d843f4f6b50321c887f2e30`，逐成员绑定原始内容。归档目录为：

- `positive/`：构建、固定源码、完整 core、ordinary、SMP 的环境、命令、锁、收据、QEMU 记录和完整串口。
- `negative/`：精确旧行为补丁、正向保留输入、负控 source 前后像、实际 gate 和 oracle、恢复后的 source 记录。
- `abi/`：同一原 Agentd 的 invocation、runtime closure、完整串口、结果和 shutdown 检查。
- `abi-runner/`：实际执行的新 pin runner 四个 runtime 文件、pin review 与只改 pin 的 diff。
- `setup/v1/`：早期准备阶段记录，包括未进入 native 测试的 rustfmt 组件问题。

kernel ELF、原 Agentd ELF 等大型输入的身份由原始收据固定，不能因存在这个日志归档就假定每个二进制也在包内。本目录对应运行结果的平面 JSON 是归档相应成员的逐字节副本，便于直接核对；原 input manifest 与独立 review 另行保留，不属于这个 99-member 归档。实际原始路径见各命令记录。

## 原故障与新结果的对应关系

[旧 ordinary Agentd 证据](../2026-10-22-agentd-ordinary-abi/README.md) 已证明旧 kernel `8170402a…` 可以加载原 ELF 并到达预期配置拒绝，但其完整串口末尾在 `SYS_SYNC` 后出现一个 block Write 错误和两个 writeback I/O 错误。只读 payload 的字节未变，是后端拒绝了写入；这不等于读侧没有产生写请求。

本轮不是把旧 payload 改成可写。继续使用同一原 ELF、同一冻结 manifest、同一动态库组合和同一配置拒绝 oracle，仅把独立 runner 的三个 kernel/source pin 及对应诊断字符串重绑定到已单独构建验证的新 ordinary kernel。

| 对照项 | 旧运行 | 新运行 |
| --- | --- | --- |
| 原 Agentd ELF | 两次相同：484,463,504 bytes；SHA-256 `228d2e07583d0d27cf5750a6ba169254380fb4d49f1fdc21adcc04001fc3252f` | 相同 |
| 原 Agentd source | 两次相同：`6d6097da843f5831dfaf9cee3530da512d072a15` / `f722fbe5f24275c324089be720559a40901105f3` | 相同 |
| 冻结 input manifest SHA-256 | `999e632d8e82cc71b58436a5c0a63b50312cf83ccfcfdb35b28b947b0eb12728` | 相同 |
| runtime closure SHA-256 | `8f6801a78c66009b4a34cb4add9250ef5f42b65e3ab84533daabbfb1a58866d5` | 相同 |
| ordinary kernel SHA-256 | `8170402aaa7408eb2c4ab1ade2cd1d9641ef03ccbd37631aaec775528df2ede7` | `8bda1c4876cbfbca0c441adb2d3ac4a91c4b3ff2e9faadedcb3d43503a0b6c09` |
| Write BIO / block Write error / writeback error | **1 / 1 / 2** | **0 / 0 / 0** |
| 新日志中的 sync / reboot | — | **1 / 1** |
| 新日志中的任意 IoError | — | **0** |
| 配置拒绝 | 空 stdout；精确错误；child exit 1 | 同一精确拒绝，QEMU exit 33 |
| 完整 raw serial | 7,287,706 bytes；21,537 lines；SHA-256 `0567b1b7a03ca4d9f5c09d5113970bb3512fc976457d68e492cab2c7463dcd74` | **7,298,680 bytes；21,569 lines；SHA-256 `7b9f6ecea33141173f2e4dc683ac131bb85e2ec34ea0bb43c011188b34a61399`** |

上述新计数来自 [agentd-readonly-shutdown-check.json](agentd-readonly-shutdown-check.json)，绑定实际 ABI result 摘要及完整串口摘要。新 payload SHA-256 为 `237c321730d327262db3b6a6b400a9e76b26343c2023ac6c897a05d0e2176994`，此次运行前后保持不变；它是本次重新构造的 payload，不声称与旧 payload 字节相同。

[agentd-pin-review.json](agentd-pin-review.json) 记录准确 argv、新旧四个 runtime 文件摘要及旧包保持不变的检查。[agentd-reviewed-kernel-pin-only.diff](agentd-reviewed-kernel-pin-only.diff) 只修改 `KERNEL_SHA`、`KERNEL_HEAD`、`KERNEL_TREE` 和一个对应报错字符串。probe、cpio helper、startup source-review 及所有判据不变。新 runner SHA-256 为 `4e119a169f1daa20a4dc45113893301bef35072eea7da1158c6440357e71b61a`，旧 runner 仍是 `0994e245…`。

这份完整串口的零 Write/IoError 结果，与使用可写计数设备的三个 RO ktest 相互补充：前者验证原故障的实际加载和关机路径，后者能在后端拒写之前直接观察到不应发生的写入。ordinary QueryAbi 没有这个 Agentd payload，因此它自己的 18 个 marker 不能替代该回归。

## 最小技术修改与开发落点

生产代码仍全部位于 safe Rust kernel，未新增 unsafe、第二个 filesystem owner 或替代 writeback。入口采用既有 inode 和 filesystem 对象。

| 模块／文件 | 本次开发职责 |
| --- | --- |
| [ext2/inode/attrs.rs](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/inode/attrs.rs) | `update_atime_after_read()` 升级原 weak filesystem，读取原 `FsFlags::RDONLY`；初始 RO 跳过附带 atime 更新，RW 沿用原 dirty setter。显式 setter 保持原样。 |
| [ext2/inode/file.rs](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/inode/file.rs) | buffered/direct read 仅在 `read_len > 0` 时调用 helper；临时 inode read guard 在前一个语句结束时释放，随后才取得 write guard。 |
| [ext2/inode/dir/mod.rs](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/inode/dir/mod.rs) | 先退出原 readdir read-lock 作用域，再调用 helper；保持原 RW 下更新时间和返回结果的时机。 |
| [readonly_atime_tests.rs](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/inode/attrs/readonly_atime_tests.rs) | 可写的计数 BlockDevice、新 inode/page cache、三个 RO 回归、RW 正控与旧脏数据 flush 正控。 |
| [core checker](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/support/build/ktest/check.py) 与 [host tests](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/support/build/tests/test_ktest_checker.py) | 完整 core 最小分母 269→274，required 31→36；每个名字必须实际执行一次，不能 soft-skip 或用别的名字替换。 |
| [SMP checker](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/support/build/ktest/check-permission-smp.py) 与 [host tests](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/tests/organ_backend/test_permission_attr_smp.py) | 编译总数 272→277；仍只选择原三个双 CPU race 测试，其余 274 filtered。 |

helper 的 flags 检查沿用原子 load，不新增 superblock、block-group 或 inode-cache 锁。三个调用点先释放 read guard，避免在同一个 inode 上持有 read guard 再取得 write guard。若 filesystem 已消失，helper 只跳过附带更新时间，不把已成功的读改成新的 EIO。

[ext2/fs.rs](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/fs.rs)、[inode/sync.rs](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/inode/sync.rs) 和原 VFS sync 路径保持不变。不能以“RDONLY 时一律不 sync”解决这个缺陷，因为 filesystem 可能仍有之前 RW 操作形成的合法脏数据。第五个 ktest 专门保护这个性质。

已有 inode 权限事务契约参见 [INODE_PERMISSION_TRANSACTIONS.md](../../../docs/INODE_PERMISSION_TRANSACTIONS.md)。该专题的历史分母不替代本目录固定 source 的实际 274／36／277 结果。

### 五个新增内核测试

| 测试名 | 必须出现的真实行为 |
| --- | --- |
| `readonly_buffered_read_keeps_atime_without_writes` | 新 RO 实例真实读取完整数据；atime 不变、inode 不脏；Full/Data inode sync 与 filesystem sync 后 Write BIO 均为零；磁盘 atime 不变。 |
| `readonly_direct_read_keeps_atime_without_writes` | 真实对齐 direct read，返回长度和内容正确；随后验证相同的 atime、脏状态、写计数和磁盘值。 |
| `readonly_readdir_keeps_atime_without_writes` | 真实遍历必须包含 `. / .. / atime` 并返回非零结果；目录 atime、脏状态、sync 写计数和持久值满足 RO 判据。 |
| `writable_reads_persist_atime` | 三条路径分别创建 fresh RW 实例；读取后置脏；sync 发生 Write BIO 并清脏；持久 atime 等于本次内存观察值。无需 sleep 或假定时钟前进。 |
| `readonly_flag_does_not_discard_preexisting_dirty_data` | RW 写入 replacement 并确认置脏，随后设置原 RDONLY flag；filesystem sync 必须真正写出，新实例读回完整 replacement。 |

计数设备接受并转发所有 Write，不依赖只读后端的报错；每项从持久 fixture 重新 `Ext2::open`，避免旧 cache 掩盖磁盘值。第五项验证旧 RW 脏数据写回，不证明并发 remount 的线性化，也不新增独立的 inode Full/Data 旧脏数据资格。

## 可复现的开发与验证入口

使用 [固定构建手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/support/build/README.md)、[内核测试手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/support/build/ktest/README.md) 和 [ordinary QueryAbi 手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd/tests/kernel/control/README.md) 指定的 host、固定 nightly、OSDK、vDSO、QEMU 与 BusyBox 输入。以下命令从完整、干净、精确 source checkout 的仓库根目录执行；路径由操作者替换为自己的新任务目录。输出必须在源码树外，相关构建顺序执行，避免复用不同 checkout 路径内嵌的 OSDK。

```sh
set -eu
EXT2_RUN_ROOT=/absolute/new-ext2-rdonly-run
test ! -e "$EXT2_RUN_ROOT"
mkdir "$EXT2_RUN_ROOT"

test "$(git rev-parse HEAD)" = 9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd
test "$(git rev-parse 'HEAD^{tree}')" = eeae4dc1ef546d408b55c98310e99e3156f08207
EXT2_SOURCE_STATUS="$(git status --porcelain --untracked-files=all)"
test -z "$EXT2_SOURCE_STATUS"
test -f README.md
test ! -L README.md
test ! -s README.md

python3 -I -B support/build/verify-source.py
python3 -I -B support/build/ktest/prepare-locks.py \
  --output-dir "$EXT2_RUN_ROOT/prepared-locks"
cmp "$EXT2_RUN_ROOT/prepared-locks/aster-core.Cargo.lock" \
  support/build/ktest/locks/aster-core.Cargo.lock
cmp "$EXT2_RUN_ROOT/prepared-locks/ostd.Cargo.lock" \
  support/build/ktest/locks/ostd.Cargo.lock

python3 -I -B support/build/tests/test_ktest_checker.py
python3 -I -B tests/organ_backend/test_permission_attr_smp.py -v
python3 -I -B support/build/ktest/run.py \
  --crate aster-core --output "$EXT2_RUN_ROOT/core"

python3 -I -B tests/kernel/control/run_queryabi_candidate_guest.py \
  --expected-source-head 9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd \
  --expected-source-tree eeae4dc1ef546d408b55c98310e99e3156f08207 \
  --target-dir "$EXT2_RUN_ROOT/ordinary-target" \
  --output "$EXT2_RUN_ROOT/ordinary-queryabi"

python3 -I -B support/build/ktest/run.py \
  --permission-attr-smp --output "$EXT2_RUN_ROOT/permission-smp"
```

保留各自完整输出目录中的 environment、commands、source snapshots、生成 lock、实际 kernel ELF、QEMU argv/exit 和完整 serial；核心与 SMP 编译产物不能相互替换。`--test-name` 仅能用于调试，不构成完整 274 项验收。

本轮审阅独立执行过 host checker 的 **16 tests、15 tests，均 OK、exit 0**。它们验证证据解析／负向 fixture，不计入 274 项内核执行，也不替代真实 guest 日志。

### 同一原 Agentd 的新内核回归

历史仓库 runner 仍固定旧 `85d/8170402a…` 资格；仅传新 kernel 参数会被该旧 pin 正确拒绝。本轮实际执行目录名为 `agentd-abi-ext2-fixed-runner-v1/`，其四个 runtime 源文件在归档中保存为 **`abi-runner/`**，保持原包不变。复现时先按 [agentd-pin-review.json](agentd-pin-review.json) 核对四个文件摘要，再使用该归档版本，不临时改写历史 runner 的资格。

下列命令复用实际运行的 pin。[agentd-original-input-manifest.json](agentd-original-input-manifest.json) 已取回原始字节：**2074 bytes，SHA-256 `999e632d8e82cc71b58436a5c0a63b50312cf83ccfcfdb35b28b947b0eb12728`**，可直接作为 `--input-manifest` 的输入，不再要求另行寻找该原件。原 Agentd ELF 的实际路径和字节仍由 producer 保留，公开包没有包含该 484 MB 二进制。

原 manifest 的 `binary.path` 为相对路径 `agentd.elf`，runner 必须在 manifest 同目录内找到相同字节的 ELF；跨目录 symlink 不符合其冻结输入约束。示例把这个 sidecar 原样复制到新的任务输入目录，并把 producer 留存的原 ELF 复制为同目录的 `agentd.elf`。这种不改 manifest 字节的搬迁保持原 pin；若为搬迁更改 `binary.path` 或重新序列化 manifest，就必须记录新摘要和新的输入 pin，不能继续声称使用原 `999e632d…` 字节。

归档内 `abi/frozen-input-manifest.json` 是 runner 重新序列化的记录副本，JSON 值与新 sidecar 完全相同，但其字节 SHA-256 为 `0b464e10efeb8ac87a3bfb2697c9e4a854aae5def01935f867be13c03fbc6aeb`。复现使用上述原始 sidecar，不能用这个记录副本替换。99-member 归档未因新增 sidecar 而重写。

```sh
EXT2_ARCHIVE_ROOT=/absolute/extracted-ext2-evidence
EXT2_EVIDENCE_PACKET=/absolute/retained-ext2-evidence-directory
EXT2_ORIGINAL_ELF=/absolute/producer-retained/agentd.elf
EXT2_FROZEN_INPUT=/absolute/new-original-agentd-input
test ! -e "$EXT2_FROZEN_INPUT"
mkdir "$EXT2_FROZEN_INPUT"
cp "$EXT2_ORIGINAL_ELF" "$EXT2_FROZEN_INPUT/agentd.elf"
cp "$EXT2_EVIDENCE_PACKET/agentd-original-input-manifest.json" \
  "$EXT2_FROZEN_INPUT/agentd-original-input-manifest.json"
python3 -I -B \
  "$EXT2_ARCHIVE_ROOT/abi-runner/run_agentd_abi.py" \
  --execute \
  --input-manifest "$EXT2_FROZEN_INPUT/agentd-original-input-manifest.json" \
  --expected-input-manifest-sha256 999e632d8e82cc71b58436a5c0a63b50312cf83ccfcfdb35b28b947b0eb12728 \
  --kernel "$EXT2_RUN_ROOT/ordinary-queryabi/product-kernel.elf" \
  --expected-kernel-sha256 8bda1c4876cbfbca0c441adb2d3ac4a91c4b3ff2e9faadedcb3d43503a0b6c09 \
  --initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --qemu /usr/bin/qemu-system-x86_64 \
  --expected-qemu-sha256 8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854 \
  --cc /usr/bin/gcc-13 \
  --output "$EXT2_RUN_ROOT/agentd-abi"
```

该命令是有意的 opt-in，默认 runner 不执行设备或 guest。其范围仍是空环境下的 earliest configuration rejection。必须同时检查完整串口的 shutdown 路径，不可只抓配置拒绝 marker；本轮实际计数见 `agentd-readonly-shutdown-check.json`。若重新构建工具或 ELF 字节不同，记录新的实际输入身份并另行验收，不能把 expected hash 改成任意当前输出后继承本结果。

## 旧自动 atime 负控：实际失败与恢复

使用与格式化后源码匹配的 [negative-control-original-atime.patch](negative-control-original-atime.patch)：**1335 bytes，SHA-256 `a3d95ad68f9e8f69d7aec68c1346a4ab559d9051dc1b4195e8dee15b30a238de`**。它只改变一个 `attrs.rs`：删除 11 行，恢复原无条件 `set_atime(utils::now())`；不删除测试，不改 sync，不调低门禁。

正向前像 blob 为 `ed811244d13266a950466de407b469b51bd18846`，负控后像为 `184bd1184cb1993942334096ab839e3d6793a6cb`。先前的独立内存重建和真实 apply/reverse 审查，与随后完成的 native 执行分别保留；不把前者当作后者。

实际 [native-negative-result.json](native-negative-result.json) 固定：negative head **`76cb23695ea5d03c42bce64e9149ead8c09d8d31`**、tree **`c5f7bdc874fddeb709b09ad545ae07e9b179d250`**。仅 `attrs.rs` 一个路径改变，其余 source 文件、五个新测试和 sync 保持不变。使用同一 source-built OSDK binary 与 source path 执行完整 274 项，得到 **271 passed / 3 failed / 0 filtered / 0 soft-skip，raw QEMU 65，original gate exit 1**。

负控 kernel SHA-256 为 `efc151fbb04bf41e74258f88f7475cc016cb1a04ff3888f02470400b29622f54`，完整负控 serial SHA-256 为 `a9698a5b0bcb01675eab162464631fad6a0837a09815a5afae6b0da2bdd57731`。收据还绑定先前保留的完整 core 正向 kernel/serial，并记录 `candidate_restored=true`、`source_snapshots_unchanged=true`：执行后回到正向 `9076f1ae… / eeae4dc1…`，没有留下负控源码。

在单独任务 checkout 上应用负控并记录其真实 negative commit/tree。先核对上述前像，然后使用相同完整 core runner，保留所有 274 项测试、36 个 required 名称和未改动的测试文件。完整 runner 应因实际失败而非超时、缺依赖或源码污染返回非成功；只有精确失败集合与实际 guest 日志匹配才是有效负控。

```sh
# 从已经固定正向前像、且输出在树外的独立 negative checkout 执行。
# EXT2_NEGATIVE_PATCH 指本目录归档补丁的绝对路径。
test "$(git rev-parse HEAD)" = 9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd
test "$(git hash-object kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/inode/attrs.rs)" \
  = ed811244d13266a950466de407b469b51bd18846
git apply --check --index --whitespace=error "$EXT2_NEGATIVE_PATCH"
git apply --index "$EXT2_NEGATIVE_PATCH"
git commit -m "test: restore original ext2 read atime for negative control"
test "$(git rev-parse 'HEAD^{tree}')" = c5f7bdc874fddeb709b09ad545ae07e9b179d250
git rev-parse HEAD > "$EXT2_RUN_ROOT/negative-head.txt"
git rev-parse 'HEAD^{tree}' > "$EXT2_RUN_ROOT/negative-tree.txt"
set +e
python3 -I -B support/build/ktest/run.py \
  --crate aster-core --output "$EXT2_RUN_ROOT/old-atime-negative"
EXT2_NEGATIVE_GATE_RC=$?
set -e
test "$EXT2_NEGATIVE_GATE_RC" -eq 1
```

新建的负控 commit 会因提交元数据不同而有自己的 head，必须保存实际值；只要输入与补丁相同，预期 tree 为上面的 `c5f7bdc8…`。退出 1 本身不证明有效负控，还必须核对 guest 原始日志中的三项精确失败、其余 271 项通过、0 filtered／soft-skip、QEMU 65 和 source 输入一致性。

实际失败集合与先前源码推导完全一致：`readonly_buffered_read_keeps_atime_without_writes`、`readonly_direct_read_keeps_atime_without_writes`、`readonly_readdir_keeps_atime_without_writes`。RW 与旧脏数据正控保持通过。三个失败先发生于 atime 或 Dirty 断言，尚未进入 sync，收据明确保留 `negative_bio_write_count_claimed=false`；因此不能把“三红”写成实际观测到“三次 Write BIO”。相同时钟值也不会漏检，因为原 setter 经过 `Dirty::deref_mut` 仍会置脏。

负控第一次尝试曾因准备 helper 导入生成自身 `__pycache__`，被 clean-source guard 前置拒绝，未运行负控 native 测试。后续准备禁用 bytecode 并只清理自身已知 cache；该准备记录留在归档 `negative/setup-cache-cleanup.json`。这次前置拒绝与随后真实 guest 的三项失败分别记录，没有把前置失败计入三红。

## 仍未完成的只读与原生边界

本修复不把 RDONLY flag 原子读取升级为并发 remount 事务，也不决定特定 bind mount 的 atime 策略。显式 utimes／metadata 修改、NOATIME、跨 VFS 修改入口的完整 `EROFS` 拒绝、virtio block RO feature 协商、并发 RW→RO remount、其他 filesystem 的语义都需要各自的 owner 和验收。

旧 RW 脏数据的正控证明本切片没有通过丢弃 writeback 消除日志错误；它不证明 crash atomicity、断电恢复或所有同步接口的完整只读策略。新 Agentd 完整串口仍有 **25 条 `Unimplemented syscall number: 334` 警告**，即 x86_64 `rseq` 仍未实现；本次只验证该启动路径能够回退并到达预期配置拒绝。零 I/O error 不能被解读为无警告或完整 Linux ABI 支持。

原 Agentd 仍因缺少 `HEPTA_FLEET_ROOT` 按预期退出，没有启动 FleetRegistry/Supervisor、原 writer、模型任务、GUI session 或 HOS2 native 事务。该结果因此保持 `daemon_started=false`、`original_owner_runtime=false`、`g2_completed=false`、`f_completed=false`、`production=false`。下一步应继续使用原有进程和 owner 的真实 fixture，独立完成可写状态初始化、正常启动/停止与重启恢复，不能拿本次读取与关机回归替代这些阶段。
