# R11 报告恢复说明

这是2026-10-19工作区维护后新写的恢复说明。执行负责人报告10:46的维护清除了未发布的R11报告和若干本地原始材料；本代理未找到旧报告/矩阵的完整functions store副本，执行负责人另查未发现可用副本。以下新文件由保留会话、固定Git及实际恢复的原响应重建，**不是旧文件的逐字恢复**。

## 1. 旧文件身份只作历史记录

| 原文件 | 原字节数 | 原SHA-256 |
| --- | ---: | --- |
| R11_AUDIT_DRAFT.md | 61,576 | `5e07af443f6bc9ed78f3f2c34b584831d4b67bfbde519ae1de87bd043e120fbd` |
| module-matrix.json | 89,253 | `984f2d78ffcd5b296614327b87d73120ca7281ae20ac091c28ecc0900b662ef5` |

这些SHA没有赋给重建文件。旧报告引用过的旧derived review/manifest不能按会话摘要重造并冒用原hash；现在的正文、矩阵和本说明都有新字节和新身份。

## 2. 已实际恢复的内容

- **源码与已发布文档：**远端f966/tree659736已克隆，固定main00e和其文档可读取；当前PR205又推进到4d3011cf/tree8eb809。固定Git比较只增加一个host source-guard修正，产品/工作流/七负控/报告所用文档未变。当前62个文档内容和19测试源已重新读取，60路径在main已存在、2手册是候选新增。
- **Hepta原响应：**审阅代理从其functions store找回22份原response对象、完整源码/两份job日志字符串。新序列化大小与原输出一致，10源码Git blob匹配原compare；旧JSON SHA完整清单未恢复，不能声称全部旧SHA又逐项核验。新恢复包清单绑定现有文件，观察时间仍09:06–09:07。见[原响应恢复](hepta-current-review/RECOVERY.md)。
- **Desktop历史API：**25份原response恢复，保留08:23–08:24的原时点；当时#203 Draft/open早于08:35:37实际合并，prospective merge不能当真实merge。10:55时该包只含metadata，原冻结说明不改。见[API恢复](desktop-progress-ci/RECOVERY.md)。
- **#203原官方artifact：**执行负责人于10:59:34.843365 UTC重新下载153,302,416字节ZIP，SHA-256 `7ec32457b02fe4fa897b32ce937f2c34d9cd0bfae034da4c5f74626ecfc539bf`与原官方值相同，1172成员、383,208,710解压字节CRC通过。原serial/ELF/source成员可提取；11:06已形成新的green core/OSTD/source/三ELF/QueryAbi独立审查，七负控/full32/CPU未据此重审，旧派生review JSON仍未恢复。这是原字节恢复，不是产品重跑。见[归档恢复收据](pr203-restored-artifact/archive-recovery.json)。

## 3. 仍缺失、不得补造的原件

本地G1-b WIP的原serial、ELF、完整dirty-source取证和旧独立review尚未找回。维护前core220、定向EBUSY失败及正确生命周期修复作为已观察事实保留，源码/已发布候选手册可交叉阅读；不能补写原日志、用新ELF冒旧ELF，或将WIP运行改成83e/f966/4d精确头CI。#203旧派生review/两旧manifest与旧完整R11报告/矩阵也没有逐字恢复。

## 4. 新版交付边界

新版仅写[README.md](README.md)、[module-matrix.json](module-matrix.json)和本说明。完整新正文/矩阵/恢复说明也存入本代理functions store，供再次恢复核对；不改变Git或远端。结果目录中的同目录证据链接为待发布负责人按新manifest装配的布局，原producer文件已存在。

本次只读历史main某blob时遇partial clone懒取网络失败；随后以已检出固定候选内容核对bytes，用main ls-tree记录旧路径存在与blob身份，没有把未取回的旧blob内容记为已读取。当前PR205最末CI/artifact/merge仍待实际结果，本恢复者未跑Cargo/QEMU、未重打包R10、未轮询GitHub状态；仅为上游能力说明读取了一次官方0.19.0公告。后续实际CI收据与本次恢复记录分别保存。


## 5. 最终执行与发布补充

上述第1–4节保留报告重建阶段的范围，不作为最终PR205状态。4d的全新官方A06 artifact已经独立核实完整core220/OSTD221含3softskip、七完整负控、普通Linux32/SCM27/NOFILE37与CPU；#205于11:34:07 UTC正常合入同树b8d5af3f。新执行不修补旧WIP原件，也不冒用旧哈希。最新Hepta状态已另GET到11:18，同头两个required仍失败。最终正文、矩阵与三项文档状态更新及原件清单由发布负责人合并在独立docs/results提交中；原报告作者零产品执行的说明仍只属于其重建过程。[最终状态](source-publication/final-state.json)、[本轮原产物](pr205-runtime-review/README.md)、[新Hepta状态](hepta-final-status/README.md)。

最终交叉复核另纠正旧 #203 的一处历史 ELF 表述：原 QueryAbi 和 1/2 vCPU 收据绑定同一普通内核，已保存 ordinary ELF 的流式字节复核相符；共享 target 残留不替代 quota 输入身份。四个旧 CPU 读数仅对原 JSON 样本比率复算，没有重新解析串口或增加 SMP 资格。[独立历史纠正原件](pr203-identity-correction/README.md)。
