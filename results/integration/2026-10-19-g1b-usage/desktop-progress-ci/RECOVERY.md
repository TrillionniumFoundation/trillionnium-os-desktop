# Desktop #203 与历史 API 恢复

从仍存活的 functions store 恢复 25 份原 API response 对象，包含 #203/#199/#201/#202 的 PR、检查、jobs、artifact 元数据，及当时 Hepta 三 PR/main 的快照。本次没有重新查询这些历史对象，也没有重造旧产物审查。

原观察为 2026-10-19 08:23–08:24 UTC；#203 精确源码775061af，当时五 checks success、A06 job117950707764 success。它的旧 Draft/open 状态早于后来的实际合并，不能转记为当前状态；旧 prospective merge SHA也不能写成真实 merge SHA。

官方 artifact12172041618 的元数据仍在：153,302,416 B，SHA-256 7ec32457b02fe4fa897b32ce937f2c34d9cd0bfae034da4c5f74626ecfc539bf。原 ZIP、解压 serial/ELF、本地独立审查和两 manifest 原字节已丢失；目前没有恢复或重新执行它们。重新下载后须先比对该官方 SHA，再独立审阅，不凭这些 API 声称重做运行验收。

见 recovery-review.json、recovery-receipt.json 与新的 recovered-files-manifest.json。原 response 字符串来自保留对象；原文件 SHA 的完整清单已丢失，新清单只绑定恢复后的文件，不冒用旧清单身份。所有压缩副本逐字解压核验；可只运输 *.json.xz 和三份恢复说明/清单，未压缩原件仍在 producer。
