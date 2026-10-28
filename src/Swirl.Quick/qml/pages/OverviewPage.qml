pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    required property var engineController
    required property var systemProvider
    readonly property Item motionTitle: heading.titleItem
    component AccessRow: Item {
        id: row
        property string title: ""
        property string description: ""
        property string status: ""
        property bool active: false
        property bool available: false
        property bool configurable: false
        property bool toggleVisible: true
        property string configureLabel: qsTr("配置")
        signal toggled(bool on)
        signal configure()
        Layout.fillWidth: true
        implicitHeight: content.implicitHeight + Theme.dp(32)
        GridLayout {
            id: content
            anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            columns: row.width < Theme.dp(620) ? 1 : 2
            columnSpacing: Theme.dp(28); rowSpacing: Theme.dp(12)
            ColumnLayout {
                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(6)
                SwirlText { text: row.title; color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.Wrap }
                SwirlText { text: row.description; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; wrapMode: Text.Wrap }
                SwirlText { text: row.status; textFormat:Text.PlainText; color: row.active ? Theme.accent : row.available ? Theme.muted : Theme.disabledText; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter; spacing: Theme.dp(14)
                SwirlButton { visible: row.configurable; quiet: true; text: row.configureLabel; onClicked: row.configure() }
                SwirlToggle { visible: row.toggleVisible; checked: row.active; enabled: row.available; onToggled: { row.toggled(checked); checked=Qt.binding(()=>row.active) } Accessible.name: row.title }
            }
        }
        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: Theme.borderWidth; color: Theme.separator }
    }
    ScrollView {
        id: scroll
        anchors.fill: parent; anchors.margins: Theme.pagePadding; clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: SwirlScrollBar {}
        ColumnLayout {
            width: scroll.availableWidth; spacing: Theme.dp(16)
            SwirlPageHeader { id: heading; Layout.fillWidth: true; title: qsTr("概览"); description: qsTr("查看网络接管与服务能力。可用操作以当前内核的真实状态为准。") }
            SwirlSectionTitle { Layout.fillWidth: true; Layout.topMargin: Theme.dp(8); title: qsTr("本机连接") }
            AccessRow {
                title: qsTr("系统代理")
                description: qsTr("在活动页统一开启或关闭代理，按已保存策略分配流量。")
                status: page.engineController.systemProxy.error || page.engineController.routingError || (page.engineController.systemProxyBusy ? qsTr("正在切换") : active ? qsTr("由 Swirl 接管") : page.engineController.systemProxy.systemEnabled ? qsTr("由其他应用启用") : qsTr("未启用"))
                active: page.engineController.systemProxy.owned && page.engineController.systemProxy.enabled
                toggleVisible: false; configurable: true; configureLabel: qsTr("前往活动")
                onConfigure: AppState.navigate("activity")
            }
            AccessRow {
                title: qsTr("增强模式")
                description: qsTr("当前 Rust Core 尚未实现 TUN 数据通路，无法接管不遵循系统代理的应用。")
                status: active ? qsTr("已启用") : qsTr("尚未支持")
                active: page.engineController.tunEnabled; available: active && !page.engineController.busy
                onToggled: on => { if (!page.engineController.setTunEnabled(!page.engineController.tunRequested)) AppState.notice(page.engineController.routingError || page.engineController.networkConfigurationError) }
            }
            SwirlSectionTitle { Layout.fillWidth: true; Layout.topMargin: Theme.dp(16); title: qsTr("局域网与设备"); description: qsTr("地址、认证与客户端配置可以保留；当前未支持的接管能力无法开启。") }
            AccessRow {
                title: qsTr("HTTP 与 SOCKS5 局域网代理")
                description: qsTr("当前 Rust Core 尚不支持局域网代理。可保留地址与认证配置。")
                status: active ? qsTr("启用，端口 %1").arg(page.engineController.activeProxyPort) : qsTr("尚未支持")
                active: page.engineController.lanEnabled; available: active && !page.engineController.busy; configurable: true
                onConfigure: lanDialog.open()
                onToggled: on => { if (on && !page.engineController.lanConfigured) lanDialog.open(); else if (!page.engineController.setLanEnabled(on)) AppState.notice(page.engineController.networkConfigurationError) }
            }
            AccessRow {
                title: qsTr("网关模式")
                description: qsTr("管理网关配置、客户端记录与 CSV。当前 Rust Core 不支持 TUN 网关转发。")
                status: gatewayProvider.busy ? qsTr("正在配置") : gatewayProvider.running ? qsTr("启用") : gatewayProvider.configured ? qsTr("配置已保留，转发尚未支持") : qsTr("尚未配置，转发尚未支持")
                active: gatewayProvider.running; available: active && !gatewayProvider.busy; configurable: true; configureLabel: qsTr("管理设备")
                onConfigure: AppState.navigate("gateway")
                onToggled: on => { if (on && !gatewayProvider.start()) AppState.notice(gatewayProvider.error); else if (!on) gatewayProvider.stop() }
            }
            SwirlSectionTitle { Layout.fillWidth: true; Layout.topMargin: Theme.dp(16); title: qsTr("远程连接") }
            AccessRow { title: qsTr("私有组网"); description: qsTr("当前尚未接入 WireGuard / EasyTier 私有组网能力。"); status: qsTr("尚未支持"); toggleVisible: false; configurable: true; configureLabel: qsTr("查看现有节点"); onConfigure: AppState.navigate("proxies") }
            Item { Layout.preferredHeight: Theme.dp(16) }
        }
    }
 SwirlDialog{id:lanDialog;ownerItem:page;title:"HTTP & SOCKS5 局域网代理";ColumnLayout{width:parent.width;spacing:Theme.dp(12)
  SwirlText {text:"其他设备使用本机 IP 和代理端口连接，并使用下面的账户认证。";Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
  SwirlText {text:page.engineController.lanAddresses.join(" · ")+":"+page.engineController.proxyPort;color:Theme.text;font.pixelSize:Theme.fontSize(13)}
  SwirlTextField{id:lanUsername;Layout.fillWidth:true;text:page.engineController.lanUsername||"swirl";placeholderText:"用户名"}
  SwirlTextField{id:lanPassword;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:"密码（至少 8 字符）"}
  SwirlText {text:page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:{lanPassword.clear();lanDialog.close()}}SwirlButton{text:"保存";primary:true;enabled:page.engineController.canStart;onClicked:{if(page.engineController.configureLan(lanUsername.text,lanPassword.text)){lanPassword.clear();lanDialog.close()}}}}
 }}
}
