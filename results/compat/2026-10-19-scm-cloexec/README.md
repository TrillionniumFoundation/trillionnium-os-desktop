# SCM_RIGHTS close-on-exec 修复前实测

此目录保存本轮实际失败和 Linux 参照；修复后结果由新候选的 A06 CI/产物单独记录。`MANIFEST.json` 列出原始记录摘要，不把后来通过的结果写回历史失败。

- 相同静态 ELF：`0723be7d0ba01f6a94fd4766e4aaf98bc6590de4bbfe431455aefcba8e8eeb56`，压缩字节在 `probe.elf.gz`。
- 原 Linux 6.18.55 x86_64：27/27。最初受限执行有三项 `SO_PASSCRED` 错误，原 stdout/stderr 与失败报告保留；经批准重跑同一 ELF 后全部通过。
- 修复前普通 kernel：`f8785d9371f27b1f5e9ccd40da66ea25823ca50bfc7c431a89f20f88a45c4681`，字节在 `kernel.elf.gz`。27 项实际完成，3 PASS/24 FAIL，probe exit 1、普通启动完成、raw QEMU exit 33。失败由 runner 保持为 `passed=false`。
- 原 kernel 来自 [#197 的 exact-head A06 run](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39195437891)，artifact 12162141476 的 ZIP SHA 为 `593abd9f59ece10daebe4926f6c6cfc8965c622f62dadb94c04feaaadad375bd`。原 product receipt、完整 source snapshot 和独立审查均保留。该 snapshot 的三份原前后记录相同。
- #197 接合最新主线后另一次独立审查见 `g1a-new-head-review.json`，普通 kernel 字节相同。这里不把两次 ktest ELF 混为同一输入。

`red-result.json`、`red-serial.log.gz` 是最终 runner 的真实失败记录，包含 runner/CPIO helper 摘要。`prior-attempts` 保留初次 QEMU 缺模块路径的环境失败，以及修复模块路径后的第一次完整 guest 失败。恢复的是官方 Ubuntu QEMU 8.2.2 包；`qemu-inputs.json` 保存各包摘要，`qemu-launcher.sh` 只指向隔离的库、模块和 data 目录。原 SeaBIOS 和 initramfs 使用项目固定 SHA。

两个二进制的 gzip 使用 `mtime=0`，解压后必须重新核对上述原字节 SHA。这里只关闭明确的输入恢复和失败复现；不声明 CLOEXEC 修复已通过新 kernel，不声明固定 Debian 13 profile、RLIMIT_NOFILE、Hepta 效果或硬件资格完成。
