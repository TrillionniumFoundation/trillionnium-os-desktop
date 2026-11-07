# R5 原失败的固定播放器结构诊断

本件只读取已结束并已清理 task910 的文件。原 job `1a1aadcfbb5-fc05-4837` 仍是 FAIL，不重放点击、不启动 App、不连接 UiAutomation、不截图或录音。

safe8 已独核全原字节。Main/source/artifact 保持、helper state 恢复、held/lock 释放、精确新 task 回收均成立；首因是 `buffer_viewport_observation / UNIQUE_CURRENT_PLAYER_STRUCTURE_REQUIRED`。公共 query、submit、结果、视频 click 与三次 post 读取已完成。本次没有通过 buffer 观察或发布任何 crop。

该错误在原 `viewport_observation.py` 的唯一角色查找之后。原代码要求：

1. container 下恰有一个可见、enabled、非密码、class 未截断的 `SurfaceView`。
2. container 是 video_area 的后代。
3. overlay 是 video_area 的后代。

当前 safe 摘要不含节点结构，无法判断三项中哪一项为假。诊断固定读取三个已成功 post assessment 和首个 viewport assessment，后者由已固定 nav 的完整 canonical helper wire SHA `a5009b9860f253271ca24e1e7e4b7855dc4d27b3eda6b8d986c8ced052565ec9` 绑定。它的文件 SHA/大小此前未知，因此不伪造；读取后仍须逐字 canonical wire、原 request、scope、真实 finish、完整树 hash 和恢复链全部匹配。

读取上限是 15 个固定路径、单文件 1 MiB、总 3 MiB、8 秒。目录逐级 NOFOLLOW，文件 owner/nlink/类型和前后 stat 验证、FD finally 关闭。原 c/s/nav/cleanup、两生产源及 source manifest 都有外部精确 pin。读取失败就保留失败，无降级或替代文件。

输出仅包括原谓词的三项布尔、固定四个角色计数/必要 bounds/路径 hash、SurfaceView 的资格分组计数、SurfaceView/TextureView 两种已知类型的计数及 source/tree/window/wire pins。没有完整节点、原始 text/content description、原图、pixels、未知资源名或节点路径原文。额外运行原生产 `viewport()` 纯函数，确认首个失败可从实际原 inspection 重现；不改原 predicate 或调用 capture。

六项本地控制只检查这份结构摘要：三个失败条件、重复 SurfaceView、正常组合和 raw-node 输出拒绝。它们用合成节点和明确 scope/hash seam，未读取设备/商业 UI，不能代替实际诊断或播放资格。

R5 已有 public clearCache 返回的观察不证明 R4 的缓存根因。新诊断也不授予重用已退休树的点击权。后续任何改变必须基于本次实际结构，在新 fresh flow 保留原焦点、display、package、完整树、新鲜 action、恢复及 cleanup 门。
