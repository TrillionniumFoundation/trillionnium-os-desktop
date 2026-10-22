# ext2 格式化后源码的旧 atime 负控

本目录只提供与实际 nightly rustfmt 后源码匹配的负控补丁和本地复核记录。没有调用 Runtime、编译或执行内核测试；没有修改冻结的 `ext2-rdonly-candidate`、`work/os` 或 `os-release`。

## 精确输入与范围

原始输入是主代理下载的 `applied-native-source.patch`，20,014 bytes，SHA256 `13d5185834f968f621ae4639b2e6109e16ebd069a6604e44c53a3c0a136443f6`。主代理报告实际 native commit 为 `9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd`、tree `eeae4dc1ef546d408b55c98310e99e3156f08207`，直接 parent 为合并主干 `f85ccae8445f8d753572d41411d98ee28d253af5`、tree `bad0a3ee66859cfcf7bf1185e4f10d0f953239ad`。

本地从旧基线 `85d394f99c73ad3194d57c876712ac01b59d90ca` / tree `7389c0a3f982983087953f75de7042fc058be088` 的原始 blob 应用该 diff，逐一核对全部 8 个改动路径的前后 blob、SHA256 和模式。七个文件与封装 revision 2 逐字节相同；`attrs.rs` 唯一变化是 `permission_attrs` import 由三行折叠为一行。

本地 partial copy 的完整 index tree 为 `3245be4f6829a3fa4149c3e0eb85a25145b44934`，**不是**实际 native tree `eeae4dc1…`。原因是实际 parent 已包含后续 22 个主干路径；主代理确认其中 21 个是历史证据，一个是 ExFAT host 测试。本复核仅证明实际 diff 的八个路径及负控所需的精确 `attrs.rs` 前像；完整 native tree 身份按主代理提供的信息记录，未在此重新证明。

## 负控交付物

`negative-control-original-atime.patch`：**1,335 bytes**，SHA256 **`a3d95ad68f9e8f69d7aec68c1346a4ab559d9051dc1b4195e8dee15b30a238de`**。

| `attrs.rs` 身份 | 原生格式化后正向源码 | 负控源码 |
| --- | --- | --- |
| Git blob | `ed811244d13266a950466de407b469b51bd18846` | `184bd1184cb1993942334096ab839e3d6793a6cb` |
| SHA256 | `1dafd642ec22a3c98d4be603b6954b12b83076774b086e1bdd91ffc5e0a953b1` | `fdbc7f31d7cf16c89874d7f8eabec89c4b4ce8896da786a567b80a54ad27ae76` |
| Bytes | 8,507 | 8,101 |
| Git mode | `100644` | `100644` |

该补丁仅删除 11 行：一行 `FsFlags` import，以及 `update_atime_after_read()` 内的 filesystem weak upgrade、RDONLY early return 和相关注释。helper 恢复为无条件调用原有 `self.inner.write().set_atime(utils::now())`。三个原调用点、五个新增 ktest、显式 atime setter、sync 和所有门禁计数均保持不变。

`native-attrs.rs` 和 `negative-attrs.rs` 是上述两个完整前后像，供对照使用；实际应用应使用带完整 blob ID 的补丁。

## 已执行验证

`review.json` 保存每个源码的身份和验证范围；`tool-results.json` 保存实际命令、exit code、stdout 和 stderr。

- `git diff --check` 通过。
- `git apply --check --index --whitespace=error <negative-patch>` 通过，exit 0，stdout/stderr 为空。
- 在独立副本实际应用补丁，再比较完整 index tree：仅 `attrs.rs` 一个路径变化。其余七个交付文件逐字节不变。
- 五个 `#[ktest]` 名称和测试文件内容保留；原 `inode/sync.rs`、`ext2/fs.rs`、`ext2/impl_for_vfs/fs.rs` 内容未变。
- `git apply --reverse --check --index --whitespace=error` 及实际 reverse 均通过；本地副本已恢复到格式化后的正向八文件内容。

独立 partial copy 初次 `checkout-index` 后未刷新 stat cache，首个 `--index` 检查拒绝了七个文件；核对内容不变、刷新本地 index 并确认旧完整 base tree 后已排除。另一次读取实际 parent tree 的尝试因本地缺失对象且网络代理不可达而失败；没有重试或 Runtime 回退。这两项准备过程均在 `review.json` 记录，不作为通过结果。

## 后续原生负控判据

请在实际 native source 的独立副本先核对上述 `attrs.rs` 前像，再应用补丁并使用原完整 core runner。分母保持 **274**，required 名称保持 **36**；不能删除或过滤新测试。

预期且尚未由本复核执行的失败集合，仅包含以下三个 RO 回归：

- `readonly_buffered_read_keeps_atime_without_writes`
- `readonly_direct_read_keeps_atime_without_writes`
- `readonly_readdir_keeps_atime_without_writes`

`writable_reads_persist_atime` 与 `readonly_flag_does_not_discard_preexisting_dirty_data` 应继续通过。第五项只保护旧 RW 脏数据会被实际 sync 写出，不证明并发 RW→RO remount 线性化。原生实际结果、失败身份及 raw guest exit 由主代理的独立运行日志确认。
