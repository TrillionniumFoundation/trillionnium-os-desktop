# Pocket4 官方 App 来源闭合增量

观察日期：2026-11-09。作用域：Pocket4 Linux Droidloom。本轮无 APK 安装；CURRENT、全局 selector 及运行验收标记均未改变。

## 结果

| App / 包名 | 官方当前候选 | 新验签 | ABI | 与原装载包关系 |
| --- | --- | --- | --- | --- |
| 抖音 / com.ss.android.ugc.aweme | 41.0.0 / 410001 | v1、v2、v3 通过；同证书 | arm64-v8a | 同版本、同 code、同 signer，但完整 APK SHA 不同 |
| 淘宝 / com.taobao.taobao | 10.69.0 / 866 | v1、v2 通过；同证书 | arm64-v8a、armeabi-v7a | 同版本、同 code、同 signer，但完整 APK SHA 不同 |
| 神州租车 / com.szzc | **9.6.2 / 328** | v1、v2 通过；同证书 | arm64-v8a、armeabi-v7a | 原为 9.6.1 / 327，本轮取得官方更新候选 |
| Uber / com.ubercab | **最新完整交付包仍未知** | 未取得新的 base + splits，未声称新验签 | 最新交付未知 | 官方帮助页指向 Play；公开更新日期不能证明最新完整交付包 |

以上三个候选均在 Pocket4 root 受控目录保存，文件 uid/gid 为 0、权限 0600。每份完整包均重新执行 aapt 与 apksigner，原始输出及 SHA 已保存。验签工具的原始 META-INF 警告保留在证据中；未将“验签成功”扩写为无警告或运行合格。

## 唯一候选目录

`/home/alex/work/pocket4-android-final/cohorts/qpr1-cp3a-16176746-20261108-8b88-r1/official-app-inputs-be1746a-r2`

- `CANDIDATES.json`：22,015 字节，SHA-256 `90e9265a63aa83708c87160dcb3b27f5f40c66202fdec0360c7918e9774ce3d1`。
- `MANIFEST.json`：10,238 字节，SHA-256 `63ea9fd4fcadd28646cd25fdcb38a6e6c0ae7a054a613a79fb3b63bc9c49e415`；绑定 29 个成员、680,054,973 字节，清单自身不在成员中。
- `SOURCE-INCREMENT.json`：14,674 字节，SHA-256 `1109ce7c0145bca475d222fdeaa39cb369917a778c22b5efd7479432a8e3b7d6`。
- `RETIREMENT.json`：18,743 字节，SHA-256 `2457ab43beeaf341d06427662fa5c67a66e2e404d73e21d70992caf2bf56863c`。

| 候选文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| douyin-41.0.0-410001-official.apk | 364363658 | b1d8834c20e5dbd75e2d48b5b30dea67be88f6903dba78a78d736a80b7feff2f |
| taobao-10.69.0-866-official.apk | 95212303 | 75d76b60cbedf1a5fa1fe53184fca481d5bcef696c8a8134145925644b691808 |
| szzc-9.6.2-328-official.apk | 220267107 | c8611c1828fec03b7363a10cdc4da97c8bca1f0cf5ec91dff0c3b1e66337360f |

## 来源及证据范围

抖音：官方网站下载页 → 该页当前下载路由 JS → Android 64 位按钮 `https://ugapk.com/mGFG` → 实际官方 APK CDN。没有使用页面残留的旧 32.2.6 静态地址。完整新包与原安装包字节不同；原 range 回执的 `CONTENT_BINDING_FAILED` 仅表示旧包 SHA 比对失败。完整新 body 随后已独立新验签，并经既有 Mac SCP 通道交付 Pocket4、全量 hash 读回及 root custody。

淘宝：官方移动首页 → 官方 downloadTaobao 页面及 JS → `https://ugcdn.taobao.com/app/starlink/core/index.js?id=7420` → `https://download.alicdn.com/wireless/taobao4android/latest/taobao4android_703304.apk`。未把版权配置中的旧版本号当作最新版。

神州租车：官方公开索引中的 `https://m.zuche.com/app/` 指向 `https://static.zuchecdn.com/download/SZZC.apk`，实际跳转 `https://edfs.zuchecdn.com/android-package/SZZC.apk`。当前 HEAD 为 200，Last-Modified 为 2026-11-06；完整 GET 后解析得到 9.6.2 / 328。当前 landing page 请求超时，历史索引 404 未被当作当前可用性结论。只有一次完整下载代次，106.15 秒完成，含前缀探测的请求字节为 221,315,683，低于 400 MiB / 480 秒预算。

Uber：官方帮助页明确链接 `https://play.google.com/store/apps/details?hl=en&id=com.ubercab`。匿名公开页没有提供可核验的最新 base + 9 splits。本轮未登录、未使用第三方镜像或推断 review 中的版本号。

“当前官方”限定为观察时指定官方公开下载路径实际交付的包，不等于所有商店、灰度渠道的全局最高版本。三份 candidate 都保持 `selected=false`、`installed=false`、`runtime_accepted=false`、`production_ready=false`。

## 清理与交接

本轮成功下载的抖音 44 个分片、神州租车 27 个分片已经退役。正式归档及全量 hash 校验后，精确删除淘宝和神州租车普通下载副本、抖音 Pocket4 incoming 副本及 desktop 下载副本；这四份完整重复 APK 的文件字节合计 **1,044,206,726**。两台机器对应自有下载叶目录内已无 APK / part 残余。所有源码、原始输出、来源绑定和回执保留。

全局 selected manifest 保持 SHA `73b7578fe2376f700edd68184ed6e16182bf4b58d3b5c75554a5c597f5f3a603`。本轮没有修改 owner Android 源码、build、全局 cache 或用户数据。

`source-increment.json` 和 `retirement-summary.json` 是结构化增量，`canonical-final-manifest-receipt.json` 绑定真实远端文件；包装文件与远端原始回执的 SHA 不应混淆。该 Git 子目录保留三份新验签原始结果、当前交接和独立读回回执，由上一级 `FILES.json` 完整绑定，不包含 APK。2026-11-09 09:51 UTC 的独立读回校验了远端清单的全部 29 个成员及 Firefox 完整 APK；全局 selector 未改变。
