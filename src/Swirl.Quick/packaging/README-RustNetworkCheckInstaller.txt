Swirl Rust 联网测试安装版（开发验收用）

安装后，双击桌面上的“Swirl Rust 联网测试”，或从开始菜单打开“运行联网测试”。
不要手动打开 CMD，也不要双击安装目录里的 Swirl.exe 来做这项测试。

测试时让 Mihomo 保持平时正常运行。这个安装程序和测试脚本不会暂停 Mihomo，也不会修改系统代理、TUN、路由或 DNS。
黑色窗口会显示测试结果；结束后按任意键关闭。整轮最多约 10 分钟。
结果只保存在 D:\Codex\Swirl-acceptance-private-20261020\portable-runs。安装包没有私有 NodeStore 或 Mihomo。

六项测试全过表示这些显式请求进入 Swirl 的 Rust 内核并完成收发。此时普通应用仍可能通过 Mihomo 联网，不能把六项通过当成“完全不依赖 Mihomo”。
这是测试版，不会替换你现在安装的 Swirl。需要移除时，在 Windows“已安装的应用”中卸载“Swirl Rust 联网测试”。
