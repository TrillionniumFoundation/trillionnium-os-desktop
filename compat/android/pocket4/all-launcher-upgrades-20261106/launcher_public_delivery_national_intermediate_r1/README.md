# National：固定真实中间页的单次普通观察

前置实际 job 1a1b356f0cc-fc05-8238 已完整 durable0。唯一页面为 HTTP200，原 HTML 为 302,453 B / abad1338055c580f8fff71da6b68983995262d6c8f0cb5ca6cbfe4967311a6bb，唯一 Free XAPK Download for Android literal 是：

https://en.softonic.com/download/national-car-rental/android/post-download?dt=internalDownload

本包未执行。它先以普通 UID/GID1000 逐级 no-follow 打开唯一既存 HTML，绑定全部目录 FD 和文件完整 stat、长度/SHA，再从原文严格重新提取同一 literal；额外同标签链接、原文更改或路径替换均拒绝。全程持有文件/目录 FD，HTTP 后再次完整读取核 SHA 及文件完整 stat/路径。祖先目录固定 dev/inode/mode/uid/gid，允许无关兄弟目录创建改变 mtime/nlink；原文件全部9项 stat 必须不变。

之后仅一次 GET 上述中间页面。默认 urllib 身份与系统 TLS；无 CookieJar，既存 Cookie 不读、不重放，新响应 Set-Cookie 值仅保留长度/SHA脱敏表示。原成功回执不重写。最多2MiB HTML、64KiB错误正文、120秒总预算、180秒进程预算、256MiB内存。HTTP非200（含重定向）、挑战、超限、超时均失败停止。未观察到的 CDN/API 不在代码中，脚本、跳转和后继链接也不会执行。

中间 HTML 只保存原文 pin 并列出有限的未跟随 literal 下载控制；标签或 URL 不能证明 National 文件身份。完整 HTML 返回 ok 仍不等于二进制交付、APK/XAPK 资格或签名验证。商店安装器不下载、不安装；后续需要从新实际原文另行确定普通文件交付路径，取得后核全 base/split 的包名、版本、签名、架构及必需集合，保留正常 PM 检查。

9个原HTTP/FD辅助定义逐字保留；fetch函数仅有两处响应header脱敏调用差异。4项本地控制通过，包含真实自有文件固定字节/替换拒绝及FD恢复。测试使用实际本地UID/GID，不冒充远端1000拥有者实测。没有网络、Main、Android、ADB、UI、安装、权限或删除动作。

输出 pin 为本次写入 bytes 计算值，未另证输出文件完整回读或目录断电持久性。唯一输入则会实际两次完整读取和验证；这两种证据没有混淆。原 IHG 失败通道完全不引用、不复用。
