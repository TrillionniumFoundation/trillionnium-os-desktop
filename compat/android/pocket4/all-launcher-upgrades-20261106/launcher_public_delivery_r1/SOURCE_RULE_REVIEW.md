# 来源规则与本次独立提案

检查范围是本会话可见的用户指示、原修复材料、既有下载研究和当前冻结安装器。用户要求所有 App 升级为可用最新版，同时保留安全约束；没有在这些已检查材料中发现“所有 App 只能取厂商直链”的全局限制。此结论不声称检查过不可见历史。

原 `reference/rail-zbj-delivery-research-r1/findings.json` 和生成器选择厂商/官方商店，是该轮研究的来源范围。当前 `successor_install/source-r4-zbj-full48/candidate-r1/install_successor_native.py` 的 `ALLOWED` 是已审安装请求的有效闭集，仍保持原字节。它没有 IHG/APKMirror 条目，不能把本次页面研究直接送进旧安装器。

根代理本轮明确授权研究正常公开的可信第三方分发，但必须独立命名来源，不冒充厂商直供，不绕过站点拒绝，也不削弱安装完整性。IHG 本次归类为 `public-third-party-distribution`：官网→Play 证明应用身份；APKMirror 是独立交付线索，不能把这两条边拼成“厂商授权 APKMirror”的结论。

本提案不改旧 allowlist、不安装、不进入 Main。第一次宿主请求只取固定 variant HTML 和其中唯一 literal 中间页，普通默认身份与 TLS，至少等待15秒再请求中间页。中间页的 `here` URL 只记录，不跟随。已有观察里的临时 key 不进入执行源码。HTTP非200、重定向、挑战、缺失/歧义链接、超限或超时均停止，没有重试、代理、UA伪装、TLS/DNS替代、脚本挑战执行或 nonce 重放。

后续正常完整 APK 验证必须独立固定实际新 literal URL、完整字节/哈希、包名、版本、全部 ABI、无必需 split、普通 APK 签名与当前合法签名的关系。页面证书标签不能替代普通 apksigner 结果。若出现正常签名/完整性拒绝，应保留拒绝，不重签、不修改 APK、不忽略检查。

“未找到厂商直链”只表示检查范围内没有已核直供文件；不是“没有任何合法公开同包签名包”。全46项表分开记录厂商直供、其他公开交付、完整文件资格和业务最新版资格。
