# 原版 Hepta Agentd 本地原生链接与资源恢复实录

本归档证明固定原版 `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 在 Linux x86_64 宿主完成了一次真实 executable link。最终成功产物为 `codex-hepta-agentd`，329,001,344 字节，SHA256 `f476f9bb435c5127839c48ae7135d5a6fa7695ff5253460fdd8d19d7b084d4fa`。这份构建证据本身不证明原版进程已运行、Session 已连接或 Shell 已显示原版状态；这些门禁分别归档。

实际桌面工具源码为本地 `9d2ef72a4183460b1b4f1cdad97c1c013fa9d8dd`，同完整 tree 的远端为 [`f0924a6e48c68101ec09b01ef2f69aec330a3da7`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/f0924a6e48c68101ec09b01ef2f69aec330a3da7)，tree `651ff86f8814218bab71b19a550a1d84aa3a1d41`。原版 source/tree/Cargo.lock 在每次构建前后均保持固定和干净，锁摘要为 `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389`。没有改动原版源码或降低依赖锁要求。

## 三次真实构建

| 执行 | UTC 时间 | 真实结果 |
| --- | --- | --- |
| `original-r6-build-01` | 21:49:51–22:00:08 | exit101；从本任务保留的 check 暖缓存复制到新磁盘 target 后，`protoc-bin-vendored` 的旧 rmeta/rlib 组合触发 `E0460`。原始日志和 failed receipt 保留 |
| `original-r6-build-02` | 22:02:10–22:05:00 | 只清理新 target 中九个 `protoc-bin-vendored*` 包与 `codex-code-mode-protocol`，移除 84 个文件/16.4 MiB；越过 E0460 后，在编译 `codex-core` 时触发既有 7 GiB 非可回收内存阈值，受控退出 -15。没有 OOM，不能记为成功编译 |
| `original-r6-build-03` | 22:18:15–22:21:35 | 完成缓存迁移后，在同一已准入 target 恢复构建，exit0，生成上述真实 ELF；原版源码与锁不变 |

三次构建都采用固定 Rust 1.95、`cargo build --locked --offline --profile dev-small --no-default-features -p codex-hepta-agentd --bin codex-hepta-agentd -j1`。初次实际磁盘余量为 12,099,153,920 字节，满足原先的 8 GiB 准入要求。第三次明确是同 target 的恢复执行，`fresh_full_gate_preflight_applied=false`；其初始准入、第二次失败和第三次迁移收据由路径与 SHA256 串联，不声称重新执行了需要全新工作区的完整 stock gate，也不能用于宣称冷构建的最低资源。恢复时的 700 MiB 磁盘保留与 7 GiB 非可回收内存停止阈值均未降低。

## 缓存迁移：两次失败与最终成功分别保留

迁移仅涉及本任务拥有的旧 check target 和 Cargo 下载缓存。原版 checkout、历史日志、保留的编译器、CMake 和已验收的四个 R5 UI ELF 均未改动。原访问路径改为指向磁盘副本的符号链接；只有副本通过完整校验后，才释放同一任务的 RAM 文件系统副本。

| 执行 | 真实结果 |
| --- | --- |
| `r6-retained-cache-migration-01` | 失败。check target 文件内容和文件元数据相同，但切换路径后观察到 481 个目录 mtime 变化，严格断言失败，原目录已恢复，没有释放 RAM 副本 |
| `r6-retained-cache-migration-02` | 整体失败。明确取消目录 mtime 的等价要求后，check target 迁移成功；Cargo 副本切换时根目录 mode 从 0700 变为 0755，断言失败，原 Cargo 路径已恢复。部分完成项没有被写成整体成功 |
| `r6-retained-cache-migration-03` | 通过。重新验证前次已完成的 target 迁移；Cargo 切换后恢复根目录 0700，再核验完整清单，最后释放已验证的 RAM 副本。恢复后 `/dev/shm` 余量为 3,332,542,464 字节 |

最终清单覆盖 check target 的 10,386 个文件/1,653,171,601 字节，以及 Cargo 缓存的 56,912 个文件/1,587,708,151 字节。文件字节、权限、文件 mtime、类型、符号链接与目录权限均严格相同；目录 mtime 被显式排除，不能描述为所有目录时间戳都相同。`migration-manifest-review.json` 中 1,872 条目录条目差异来自有无目录 mtime 字段的清单比较，不是首次切换时实际观察到的 481 个变化。独立的 `migration-final-review.json` 核对最终原路径、目标 inode、权限、失败链、原版源码与清单摘要。

## 可追溯文件

原始 receipts 和日志按原目录名逐字节复制，包含资源采样。三份压缩成员清单保留其原字节，可展开检查每个文件摘要。`archive-inputs.json` 记录原位置、大小和 SHA256；`source-binding.json` 固定源码身份。`executed-helpers/` 是执行后对保留任务脚本的快照，不伪称为单独的执行前签名；脚本中的本机绝对路径是历史记录，不是可移植安装指令。`SHA256SUMS` 覆盖本归档的所有其他文件。

大型 ELF、Cargo 缓存和 target 不作为源码仓库文件提交。构建成功不授予模型、objective、设备效果、Asterinas、裸机、GPU、Wayland 或移动端资格。
