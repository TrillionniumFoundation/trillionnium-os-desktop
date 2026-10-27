# 当前组件结果与阻塞证据

这些文件属于各自明确源码，仅供审查本轮真实结果；最终产品资格仍为false。

- [Desktop e964 静态收据](desktop-e964-static.json)：103普通+103优化、fresh-cache26+26、source profile24+24、六根依赖、84文档/858链接；选入的stderr/stdout在 desktop-e964/；大体积六根metadata日志只保留原归档及SHA，不复制入仓。1180148a 的旧fresh-cache失败保留在原本地归档，e964仅修正父子缓存前缀一致性与夹具父目录。
- [原 Root Session 负控摘录](root-session-bb567-negative-selected.json)：H8d原生产源码加测试夹具bb567，同case实际失败；replacement持同inode锁时原clock/verifier仍有效，效果数0。原始case输出在 root-session-bb567/；较大的前后源码清单保留在原归档，完全相等的摘要见本目录index。这里未复制原receipt的整个环境表，也未将140MB测试ELF入仓；其原始SHA/大小保留。
- [Windows773原始分类](NATIVE-QUALIFICATION-773.json)和[解释](NATIVE-REPORT.md)：原生诊断整体FAIL，collector1 PASS不代表产品签名验证通过，junction1 FAIL未到backend断言。原始run、artifact摘要和三种签名输出事实保持原样。

[evidence-index.json](evidence-index.json)逐项记录选入文件的大小、SHA和原归档位置，并列出未复制大文件的原始身份；未选入的ZIP、源码归档、工具及旧失败不因本目录缺失而视为已执行或通过。
