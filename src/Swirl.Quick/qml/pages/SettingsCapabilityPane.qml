import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    id: pane
    required property var settingsPage
    readonly property string section: settingsPage.section
    readonly property var definitions: ({
        "TUN": {summary: qsTr("当前版本尚未实现 TUN 虚拟网卡数据通路，无法接管系统全流量。"), rows: [
            {name: qsTr("TUN 入口"), detail: qsTr("驱动、数据通路与流量回环防护尚未接入。"), kind: "toggle", runtime: "tun"},
            {name: qsTr("网卡选择"), detail: qsTr("当前无法创建或选择 TUN 网卡。"), kind: "choice", values: [qsTr("尚未接入")]},
            {name: qsTr("路由排除"), detail: qsTr("尚未提供系统路由排除设置。"), kind: "toggle"},
            {name: qsTr("网关 DNS"), detail: qsTr("尚未提供 TUN DNS 接管。"), kind: "toggle"}]},
        "DNS": {summary: qsTr("解析服务与本地映射可在 DNS 配置页管理。连接时由 Rust Core 校验实际支持的配置。"), rows: [
            {name: qsTr("解析器选择"), detail: qsTr("完整解析服务选项位于 DNS 配置页。"), kind: "choice", values: [qsTr("在 DNS 配置页管理")]},
            {name: qsTr("加密 DNS"), detail: qsTr("可在 DNS 配置页填写；保存不代表当前内核支持该传输。"), kind: "toggle"},
            {name: "IPv6", detail: qsTr("此处尚未提供 IPv6 开关。"), kind: "toggle"},
            {name: qsTr("虚拟 IP 处理"), detail: qsTr("虚拟 IP 模式尚未接入。"), kind: "toggle"}]},
        "端口": {summary: qsTr("HTTP 与 SOCKS 使用同一个本地代理监听端口。当前控制接口在进程内，无独立 API 端口。"), rows: [
            {name: qsTr("HTTP 端口"), detail: qsTr("与 SOCKS 共用本地监听。此处仅显示已保存端口。"), kind: "http"},
            {name: qsTr("SOCKS 端口"), detail: qsTr("与 HTTP 共用本地监听。"), kind: "socks"},
            {name: qsTr("API 端口"), detail: qsTr("Rust Core 通过进程内接口通信。"), kind: "api"},
            {name: qsTr("端口冲突提醒"), detail: qsTr("独立提醒选项尚未接入；启动失败会保留真实错误。"), kind: "toggle"}]},
        "系统集成": {summary: qsTr("系统代理接管由活动页管理。以下桌面集成选项尚未接入。"), rows: [
            {name: qsTr("显示托盘图标"), detail: qsTr("尚未提供托盘开关。"), kind: "toggle"},
            {name: qsTr("关闭窗口后保留托盘"), detail: qsTr("尚未提供后台驻留选项。"), kind: "toggle"},
            {name: qsTr("桌面通知"), detail: qsTr("尚未接入 Windows 桌面通知。"), kind: "toggle"}]},
        "启动": {summary: qsTr("当前不提供开机自启或启动窗口偏好。以下选项不会更改 Windows 启动项。"), rows: [
            {name: qsTr("开机启动"), detail: qsTr("尚未接入 Windows 启动项。"), kind: "toggle"},
            {name: qsTr("启动时最小化"), detail: qsTr("尚未提供启动状态选项。"), kind: "toggle"},
            {name: qsTr("恢复上次窗口"), detail: qsTr("尚未提供窗口恢复选项。"), kind: "toggle"}]},
        "通知": {summary: qsTr("操作结果与错误在应用内显示。以下通知偏好尚未接入。"), rows: [
            {name: qsTr("连接状态通知"), detail: qsTr("活动页保留真实连接状态。"), kind: "toggle"},
            {name: qsTr("订阅更新通知"), detail: qsTr("更新结果保留在订阅管理。"), kind: "toggle"},
            {name: qsTr("错误通知"), detail: qsTr("错误仍显示在相关页面。"), kind: "toggle"}]},
        "数据管理": {summary: qsTr("当前记录由对应模块管理；尚未提供下列保留周期与自动清理选项。"), rows: [
            {name: qsTr("保留连接历史"), detail: qsTr("历史保留偏好尚未接入。"), kind: "toggle"},
            {name: qsTr("保留请求日志"), detail: qsTr("日志保留偏好尚未接入。"), kind: "toggle"},
            {name: qsTr("自动清理过期记录"), detail: qsTr("尚未提供自动清理周期。"), kind: "toggle"}]},
        "隐私与安全": {summary: qsTr("敏感诊断信息按现有规则脱敏，受保护的本地缓存使用 Windows DPAPI。下列独立偏好尚未接入。"), rows: [
            {name: qsTr("敏感数据脱敏"), detail: qsTr("诊断脱敏由程序内置执行，此处尚无可调开关。"), kind: "toggle", builtIn: true},
            {name: qsTr("本地加密"), detail: qsTr("适用于受保护的本地缓存与恢复快照，此处尚无可调开关。"), kind: "toggle", builtIn: true},
            {name: qsTr("证书信任"), detail: qsTr("此处尚未接入证书信任管理。"), kind: "toggle"},
            {name: qsTr("诊断授权"), detail: qsTr("连接诊断只在点击开始后执行，此处尚无持久授权开关。"), kind: "toggle"}]},
        "快捷键": {summary: qsTr("当前快捷键固定在应用内使用。自定义与全局呼出尚未接入。"), rows: [
            {name: qsTr("全局搜索快捷键"), detail: qsTr("在 Swirl 内打开侧栏搜索。"), kind: "shortcut", value: "Ctrl+K"},
            {name: qsTr("窗口显示快捷键"), detail: qsTr("尚未注册系统全局快捷键。"), kind: "shortcut", value: qsTr("未设置")},
            {name: qsTr("页面导航快捷键"), detail: qsTr("返回或前进到已访问页面。"), kind: "shortcut", value: "Alt+← / →"},
            {name: qsTr("软件设置"), detail: qsTr("打开此设置页。"), kind: "shortcut", value: "Ctrl+,"},
            {name: qsTr("主要页面"), detail: qsTr("概览、节点、连接与检视。"), kind: "shortcut", value: "Ctrl+1 / 2 / 3 / 4"},
            {name: qsTr("侧栏展开与收起"), detail: qsTr("切换侧栏显示宽度。"), kind: "shortcut", value: "Ctrl+B"}]}
    })
    readonly property var configuration: definitions[section] || {summary: "", rows: []}
    spacing: Theme.dp(10)
    SwirlText { Layout.fillWidth: true; text: pane.configuration.summary; color: Theme.muted; font.pixelSize: Theme.fontSize(13); wrapMode: Text.Wrap }
    SettingsRowPane {
        Layout.fillWidth: true
        visible: pane.section === "DNS"
        title: qsTr("已保存的解析配置")
        description: [engineController.dnsConfiguration.mode === 2 ? qsTr("自定义服务器") : engineController.dnsConfiguration.mode === 1 ? qsTr("系统与额外服务器") : qsTr("系统 DNS"), qsTr("本地映射 %1 条").arg((engineController.dnsConfiguration.hosts || []).length)].join("　")
        SwirlButton { text: qsTr("打开 DNS 配置"); onClicked: AppState.navigate("dns") }
    }
    SettingsRowPane { Layout.fillWidth: true; visible: pane.section === "端口"; title: qsTr("当前监听状态"); description: engineController.activeProxyPort > 0 ? qsTr("127.0.0.1:%1").arg(engineController.activeProxyPort) : qsTr("引擎未监听本地端口"); SwirlStatusBadge { label: engineController.stateText; tone: engineController.apiHealthy ? "success" : "neutral" } }
    SwirlText { Layout.fillWidth: true; visible: (pane.section === "TUN" || pane.section === "DNS" || pane.section === "端口") && engineController.networkConfigurationError.length > 0; text: engineController.networkConfigurationError; color: Theme.red; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    Item { Layout.preferredHeight: Theme.dp(8) }
    Repeater {
        model: pane.configuration.rows
        delegate: SettingsRowPane {
            id: setting
            required property var modelData
            Layout.fillWidth: true
            title: modelData.name
            description: modelData.detail
            SwirlToggle { visible: setting.modelData.kind === "toggle"; enabled: false; checked: setting.modelData.runtime === "tun" ? engineController.tunEnabled : setting.modelData.builtIn === true; Accessible.name: setting.modelData.name }
            SwirlComboBox { visible: setting.modelData.kind === "choice"; enabled: false; model: setting.modelData.values || []; Accessible.name: setting.modelData.name }
            SwirlTextField { visible: ["http", "socks", "api"].indexOf(setting.modelData.kind) >= 0; Layout.preferredWidth: Theme.dp(156); readOnly: true; text: setting.modelData.kind === "api" ? qsTr("无需端口") : String(engineController.proxyPort); Accessible.name: setting.modelData.name }
            SwirlButton { visible: setting.modelData.kind === "shortcut"; text: setting.modelData.value || ""; enabled: false; Accessible.name: setting.modelData.name }
        }
    }
    SwirlText { Layout.fillWidth: true; Layout.topMargin: Theme.dp(8); text: pane.section === "快捷键" ? qsTr("焦点在设置目录时，可用上下方向键切换分区，Escape 返回上一分区。") : qsTr("不可用选项尚未接入，当前不会执行或保存更改。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
}
