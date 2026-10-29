pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    readonly property Item motionTitle: heading.titleItem
    property int serverMode: 0
    property var hostRows: []
    property string selectedId: ""
    function preparePreviewState(state) { if (state === "dns-focus") serverAddress.forceActiveFocus() }
    function persistExitDraft() { moduleDrafts.save("feature-dns-exit", {pending:true,mode:serverMode,servers:serverAddress.text,encrypted:encryptedUrl.text,hosts:hostRows,useHosts:readHosts.checked,respectRules:respectRules.checked}) }
    function finishSettings() { moduleDrafts.save("feature-dns-exit", {}); page.Window.window.closeSettings() }
    Component.onCompleted: {
        const saved = moduleDrafts.load("feature-dns-exit")
        const config = saved.pending ? saved : engineController.dnsConfiguration
        serverMode = config.mode || 0; serverAddress.text = config.servers || ""; encryptedUrl.text = config.encrypted || ""
        hostRows = config.hosts || []; readHosts.checked = config.useHosts !== false; respectRules.checked = config.respectRules === true
    }
    component Note: SwirlText { color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; wrapMode:Text.Wrap }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: Theme.pagePadding; spacing: Theme.dp(18)
        SwirlPageHeader { id:heading; Layout.fillWidth:true; title:qsTr("DNS 与本地映射"); description:qsTr("选择解析方式，维护本机域名映射。应用后保存，取消保留原配置。"); metadata:qsTr("%1 条本地映射").arg(page.hostRows.length) }
        ScrollView {
            id: dnsBody; objectName:"motion-dns-scroll"; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff; ScrollBar.vertical:SwirlScrollBar {}
            ColumnLayout {
                width: dnsBody.availableWidth; spacing: Theme.dp(24)
                GridLayout {
                    Layout.fillWidth:true; columns:page.width>=Theme.dp(600)?2:1; columnSpacing:Theme.dp(28); rowSpacing:Theme.dp(24)
                    ColumnLayout {
                        Layout.fillWidth:true; Layout.minimumWidth:0; Layout.preferredWidth:1; Layout.alignment:Qt.AlignTop; spacing:Theme.dp(10)
                        SwirlSectionTitle { title:qsTr("解析服务器"); Layout.fillWidth:true }
                        Repeater {
                            model:[qsTr("使用系统 DNS"),qsTr("系统 DNS 与额外服务器"),qsTr("只使用自定义服务器")]
                            SwirlRadioButton { required property string modelData; required property int index; objectName:"dnsMode-"+index; text:modelData; checked:page.serverMode===index; onClicked:page.serverMode=index; Layout.fillWidth:true }
                        }
                        SwirlTextField { id:serverAddress; objectName:"dnsServerAddress"; Layout.fillWidth:true; placeholderText:qsTr("服务器地址，使用逗号分隔"); Accessible.name:qsTr("DNS 服务器地址") }
                        Note { text:qsTr("额外服务器和自定义服务器使用此地址列表。") }
                        SwirlText { text:qsTr("加密 DNS"); color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold; Layout.topMargin:Theme.dp(12) }
                        SwirlTextField { id:encryptedUrl; Layout.fillWidth:true; placeholderText:qsTr("https://、tls:// 或 tcp:// 地址"); Accessible.name:qsTr("加密 DNS URL") }
                        Note { text:qsTr("配置后，传统 DNS 用于连通性检测与解析服务器域名。") }
                    }
                    ColumnLayout {
                        Layout.fillWidth:true; Layout.minimumWidth:0; Layout.preferredWidth:1; Layout.alignment:Qt.AlignTop; spacing:Theme.dp(14)
                        SwirlSectionTitle { title:qsTr("解析行为"); Layout.fillWidth:true }
                        RowLayout { Layout.fillWidth:true; SwirlText { text:qsTr("读取 hosts 记录"); color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true; wrapMode:Text.Wrap } SwirlToggle { id:readHosts; checked:true; Accessible.name:qsTr("读取 hosts 记录") } }
                        Note { text:qsTr("将本地 hosts 记录纳入域名映射。") }
                        Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.borderWidth; color:Theme.separator }
                        RowLayout { Layout.fillWidth:true; SwirlText { text:qsTr("代理请求使用本地映射"); color:Theme.text; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true; wrapMode:Text.Wrap } SwirlToggle { id:respectRules; Accessible.name:qsTr("代理请求使用本地 DNS 映射") } }
                        Note { text:qsTr("匹配本地映射时，使用映射结果的 IP 地址发起代理请求。其他代理请求保持原解析路径。") }
                        Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.borderWidth; color:Theme.separator }
                        RowLayout { Layout.fillWidth:true; SwirlText { text:qsTr("私有 DDNS"); color:Theme.muted; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true } SwirlButton { text:qsTr("配置"); development:true; enabled:false } }
                        Note { text:qsTr("私有 DDNS 服务尚未接入。") }
                    }
                }
                Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.borderWidth; color:Theme.separator }
                RowLayout {
                    Layout.fillWidth:true
                    SwirlSectionTitle { title:qsTr("本地 DNS 映射"); Layout.fillWidth:true }
                    SwirlButton { text:qsTr("添加映射"); iconName:"plus"; onClicked:mappingDialog.open() }
                    SwirlIconButton { iconName:"dismiss"; tooltip:qsTr("删除选中的映射"); enabled:page.selectedId.length>0; onClicked:{page.hostRows=page.hostRows.filter(row=>row.id!==page.selectedId);page.selectedId=""} }
                }
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(250); cornerRadius:Theme.dp(14); border.width:0; color:Theme.surface
                    SwirlDataTable { objectName:"dnsMappingTable"; anchors.fill:parent; anchors.margins:Theme.dp(4); minimal:true; fillEmptyRows:false; rows:page.hostRows; selectedId:page.selectedId; itemHeight:Theme.dp(38); columns:[{key:"name",label:qsTr("域名"),w:240},{key:"value",label:qsTr("映射地址"),w:200},{key:"server",label:qsTr("DNS 服务器"),w:150},{key:"comment",label:qsTr("注释"),w:170}]; onRowSelected:row=>page.selectedId=row.id }
                    SwirlEmptyState { anchors.centerIn:parent; visible:page.hostRows.length===0; headline:qsTr("还没有本地映射"); detail:qsTr("添加域名和 IP 地址，指定此域名的解析结果。"); width:Math.min(parent.width-Theme.dp(32),Theme.dp(360)) }
                }
                Item { Layout.preferredHeight:Theme.dp(6) }
            }
        }
        SwirlText { text:engineController.networkConfigurationError; visible:text.length>0; color:Theme.red; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12); wrapMode:Text.Wrap }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(10)
            Note { text:qsTr("更改将在应用后保存。"); Layout.fillWidth:true }
            SwirlButton { objectName:"cancelDns"; text:qsTr("取消"); onClicked:page.finishSettings() }
            SwirlButton { objectName:"applyDns"; text:qsTr("应用"); primary:true; onClicked:{if(engineController.configureDns({mode:page.serverMode,servers:serverAddress.text,encrypted:encryptedUrl.text,hosts:page.hostRows,useHosts:readHosts.checked,respectRules:respectRules.checked})){AppState.notice(qsTr("DNS 配置已保存；连接时由 Swirl Rust Core 校验，支持的设置才会应用"));page.finishSettings()}else AppState.notice(engineController.networkConfigurationError)} }
        }
    }
    SwirlDialog {
        ownerItem:page; id:mappingDialog; title:qsTr("添加本地 DNS 映射")
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(14)
            SwirlTextField { id:host; Layout.fillWidth:true; placeholderText:qsTr("域名"); Accessible.name:qsTr("映射域名") }
            SwirlTextField { id:address; Layout.fillWidth:true; placeholderText:qsTr("IP 地址"); Accessible.name:qsTr("映射 IP 地址") }
            RowLayout { Layout.alignment:Qt.AlignRight; SwirlButton { text:qsTr("取消"); onClicked:mappingDialog.close() } SwirlButton { text:qsTr("添加"); primary:true; enabled:host.text.trim().length>0&&address.text.trim().length>0; onClicked:{page.hostRows=page.hostRows.concat([{id:String(Date.now()),name:host.text.trim(),value:address.text.trim(),server:"",comment:""}]);mappingDialog.close()} } }
        }
    }
}
