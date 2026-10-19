# A01 isolated runtime evidence

本目录保存 2026-10-18 本次隔离运行环境的精确记录。除本说明、来源映射与目录 SHA256SUMS 外，保留文件均按原字节复制：安装日志与脚本、环境入口、执行收据、包和实际工具输入指纹、APT 源配置及签名 InRelease 文件、所用 Ubuntu 公钥环、固定 Rust nightly 频道 manifest 与上游校验值，以及 BusyBox、QEMU、SeaBIOS 和 vDSO 的版权与许可文件。57 个原生包使用 APT download-only 获取并解包到工作目录；运行时仍复用部分宿主库和现有工具，因此这些材料是本环境的来源与执行证据，**不是可以完全重建整台宿主的依赖锁，也不证明跨宿主逐字节可复现**。InRelease 身份和下载时验证的包 metadata 已保留，庞大的 Packages 索引未复制。runtime-receipt.json 中的 QEMU 检查使用 `-S` 暂停 CPU，仅确认固定 q35/TCG/1-vCPU/512-MiB 机器、SeaBIOS 和动态依赖可以加载，**不是项目内核启动**；实际 Asterinas 构建和串口启动证据由主任务另行记录。initramfs-manifest.json 描述环境准备期间的打包检查，其二进制未收进本目录。未复制 deb 包、Rust 完整工具链、现成 Linux 内核或 ISO；此次归档没有追加测试。

SHA256SUMS covers every file in this directory except itself. `archive-source-map.json` maps each retained original file to its exact source path, byte count and digest. `evidence-SHA256SUMS` is the original pre-archive runtime manifest, retained without editing; it is distinct from this archive's complete SHA256SUMS.
