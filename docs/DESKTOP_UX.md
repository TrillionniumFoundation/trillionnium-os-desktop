# Rust桌面与应用协议

版本0.3。原生桌面以Rust实现，对话/任务/应用工作区是主界面，终端/日志只是任务内选项；恢复入口可以简化但不能代替日常UI。状态见STATUS。

## 1. 协议路线

原生Rust聊天/任务shell与compositor/session连接所有者分进程设计；后者承载Wayland客户端；X11程序通过按信任域分离的Xwayland接入；Android先以完整SurfaceFlinger显示面桥接，之后再拆逐应用窗口。框架选型仍需可编译原型确认，不在文档中虚列已采用库。

Rust是原生组件要求，不强制把兼容用户态的Xwayland/Android系统重写Rust。原生UI、合成、兼容X服务和Android显示桥分别拥有职责，不能让UI直接成为任意设备owner。

## 2. 信任域与输入

Wayland/可信输入服务决定焦点。X11可信客户端之间有共享模型，不能把同一X server的全部客户端宣称相互严格隔离；按工作区/信任域分离Xwayland，禁止跨域任意输入抓取与共享。X SECURITY扩展是参考，不是免验证的万能隔离。[X.Org](SOURCES.md#x11)

授权提示与恢复控制具有系统可信来源；普通窗口不得伪造焦点或截取另一个工作区按键。执行桥/权限管理不暴露到任意应用可调试的同UID上下文。

## 3. 平台服务

明确提供或复用D-Bus/session、文件/截图portal、PipeWire等选定音频路径、字体/文本渲染、IME、通知、剪贴板和屏幕共享；选择组件前记录依赖与跨域访问边界。文件选择返回被选对象而非整个目录授权；drag/drop与clipboard需显式共享。Hepta已有自动化授权不隐含永久全屏录制、键盘监听或Android敏感环境数据许可。

## 4. 真实状态交互

任务详情显示真实运行模式、软件/硬件渲染、资源revision及观测时间；模型生成说明与执行状态分开。submitted、partial、unknown、cancel_requested和实际完成不能都显示为“成功”。执行中停止按钮报告请求与真实停止结果的区别。

Hepta/模型失效时仍可启动应用、切换窗口、使用文件和停止任务；shell重启不应带走compositor持有的独立应用连接；compositor崩溃和GPU reset另行验证，不承诺所有旧Wayland/X11应用都能无损重连。仅保留PID不等于窗口和未保存数据可恢复。

## 5. 验证

中文候选窗、焦点、键盘/触控、缩放/旋转、多窗口、跨域clipboard、通知、音频、文件选择、shell崩溃、Android输入坐标与复位后的buffer/fence逐项测试。初期一个Android完整显示面成功不计逐应用融合通过。Web端可共享Rust领域模型/协议，但不是本机桌面启动前提。
