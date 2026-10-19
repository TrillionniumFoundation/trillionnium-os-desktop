# Hepta 原响应恢复记录

这是维护后创建的恢复包，不是旧 09:21 冻结包。22 份原 API、源码及两份真实 job 日志的 response 对象仍保存在 functions store；原观察时间、完整响应字符串均保留。本次没有重新查询 Hepta，也没有从摘要编造旧文件。

22 份重新序列化 JSON 的字节数均与维护前实际输出一致。旧完整 manifest 字节已丢失，因此不能独立比较原 JSON 的 SHA；新的恢复清单只绑定现存文件。10 份源码重新计算的 Git blob 均匹配保存的不可变 compare 响应。

原观察是 2026-10-19 09:06–09:07 UTC：Hepta main/base f8c9419；#2885 head43a638d4/tree84fdaf39，Draft/open/unmerged，两个 required failure。恢复时间不能替代该观察时间。UI 原日志保留 5 pass / 1 timeout failure，Architecture 保留 43 pass / 2 缺临时模块 failure。完整字段见 recovery-review.json；恢复依据见 recovery-receipt.json。

旧 README、review、两 manifest 和其他派生报告没有原字节；本包不冒用其旧 SHA。原响应与实际日志可重新支持有限结论：候选确有共享 Rust UI 与 typed client/只读网关，不能宣称原授权/effect owner、G1-c/d 或 Asterinas W1 已完成。

发布时可复制所有 *.json.xz、logs/*.log.xz、RECOVERY.md、recovery-review.json、recovery-receipt.json 和 recovered-files-manifest.json。未压缩 api/*.json 在 producer 保留；压缩副本已逐份验证解压字节一致。没有下载 artifact 或执行产品。
