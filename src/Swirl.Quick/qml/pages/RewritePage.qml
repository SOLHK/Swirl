pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property Item motionTitle:heading.titleItem
    function preparePreviewState(state) { if (state === "rewrite-on") captureProvider.rewriteEnabled=true }
    ScrollView {
        id:scroll; anchors.fill:parent; anchors.margins:Theme.pagePadding; clip:true
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff; ScrollBar.vertical:SwirlScrollBar {}
        ColumnLayout {
            width:scroll.availableWidth; spacing:Theme.dp(22)
            SwirlPageHeader {
                id:heading; Layout.fillWidth:true; title:qsTr("重写与映射")
                description:qsTr("管理请求处理规则与本机端口转发。")
                metadata:qsTr("%1 条已保存规则").arg(captureProvider.rewriteRules.length)
                SwirlFlow { objectName:"rewriteStateFlow"; Layout.preferredWidth:Theme.dp(42); Layout.preferredHeight:Theme.dp(18); phase:captureProvider.rewriteEnabled?"succeeded":"idle" }
                SwirlToggle { objectName:"rewriteToggle"; large:true; checked:captureProvider.rewriteEnabled; onToggled:captureProvider.rewriteEnabled=checked; Accessible.name:qsTr("重写与映射规则开关") }
            }
            SwirlText { text:captureProvider.rewriteEnabled?qsTr("规则开关已开启。HTTP 重写在捕获端口处理请求，端口转发按已保存的监听配置工作。"):qsTr("规则已保留。开启后，HTTP 重写与已配置的本机转发开始处理对应请求。"); color:Theme.muted; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12); wrapMode:Text.Wrap }
            ColumnLayout {
                Layout.fillWidth:true; spacing:0
                Repeater {
                    model:[
                        {title:qsTr("URL 重定向"),detail:qsTr("按 URL 正则匹配，修改请求目的地。"),kind:"redirect",icon:"route"},
                        {title:qsTr("Header 重写"),detail:qsTr("修改请求或响应的 Header。"),kind:"header",icon:"document"},
                        {title:qsTr("Mock 响应"),detail:qsTr("对匹配请求返回静态正文与状态码。"),kind:"mock",icon:"code"},
                        {title:qsTr("Body 重写"),detail:qsTr("使用正则表达式替换请求或响应正文。"),kind:"body",icon:"edit"},
                        {title:qsTr("端口转发"),detail:qsTr("从本机监听端口转发到指定主机与端口。"),kind:"forward",icon:"network"}
                    ]
                    SwirlMotionButton {
                        id:editor; required property var modelData
                        objectName:"rewriteEditor-"+modelData.kind
                        Layout.fillWidth:true; implicitHeight:Theme.dp(94); leftPadding:Theme.dp(12); rightPadding:Theme.dp(12); hoverEnabled:true
                        readonly property int ruleCount:captureProvider.rewriteRules.filter(rule=>rule.kind===modelData.kind).length
                        background:SwirlControlSurface { radius:Theme.controlRadius; quiet:true; hovered:editor.hovered; pressed:editor.down; focused:editor.visualFocus; controlEnabled:editor.enabled; Rectangle { anchors.left:parent.left; anchors.right:parent.right; anchors.bottom:parent.bottom; height:Theme.borderWidth; color:Theme.separator } }
                        contentItem:RowLayout {
                            spacing:Theme.dp(18)
                            SwirlIcon { name:editor.modelData.icon; size:Theme.dp(24); color:Theme.accent }
                            ColumnLayout { Layout.fillWidth:true; Layout.minimumWidth:0; spacing:Theme.dp(6); SwirlText { text:editor.modelData.title; color:Theme.text; font.pixelSize:Theme.fontSize(17); font.weight:Font.DemiBold } SwirlText { text:editor.modelData.detail; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; wrapMode:Text.Wrap } }
                            SwirlText { text:qsTr("%1 条").arg(editor.ruleCount); color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                            SwirlIcon { name:"chevron-right"; size:Theme.dp(16); color:Theme.muted }
                        }
                        Accessible.name:qsTr("编辑%1，%2 条规则").arg(modelData.title).arg(ruleCount)
                        onClicked:page.Window.window.openRewriteEditor(modelData.kind,modelData.title)
                    }
                }
            }
            SwirlText { text:captureProvider.error; visible:text.length>0; textFormat:Text.PlainText; color:Theme.red; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12); wrapMode:Text.Wrap }
            SwirlText { text:qsTr("计数包含模块中的同类规则。"); color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            Item { Layout.preferredHeight:Theme.dp(6) }
        }
    }
}
