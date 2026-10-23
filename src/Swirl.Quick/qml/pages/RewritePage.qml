pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id: page
    function preparePreviewState(state) { if (state === "rewrite-on") captureProvider.rewriteEnabled = true }
    Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width; contentHeight: body.implicitHeight + 2 * Theme.pagePadding
        clip: true; boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: SwirlScrollBar {}
        ColumnLayout {
            id: body
            x: Theme.pagePadding; width: scroll.width - 2 * Theme.pagePadding
            spacing: Theme.sectionGap
            RowLayout {
                Layout.fillWidth: true
                SwirlText { textRole:"pageTitle";text:"重写 & 映射";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold;Layout.fillWidth:true }
                SwirlToggle { objectName:"rewriteToggle";large:true;checked:captureProvider.rewriteEnabled;onToggled:captureProvider.rewriteEnabled=checked;Accessible.name:"重写与映射" }
            }
            GridLayout {
                id: grid
                Layout.fillWidth: true
                columns: width >= Theme.dp(560) ? 2 : 1
                columnSpacing: Theme.gap; rowSpacing: Theme.gap
                Repeater {
                    model: [
                        {title:"URL 重定向",description:"重定向 HTTP 请求。此功能也称为 Map Remote。Swirl 可以用 3 种不同的方法重写请求的 URL。有关更多信息，请查看手册。",button:"编辑 URL 重定向规则…",kind:"redirect"},
                        {title:"Header 重写",description:"Swirl 可以修改发送到服务器的 HTTP Header，以及修改返回响应的 Header。",button:"编辑 Header 重写规则…",kind:"header"},
                        {title:"Mock",description:"你可以模拟 API 服务器并返回静态响应。此功能也可称为 Map Local 或 API Mocking。如果你想动态返回响应，请使用脚本。",button:"编辑 Mock 规则…",kind:"mock"},
                        {title:"Body 重写",description:"Swirl 可以重写 HTTP 请求或响应的 Body，用正则表达式替换原始内容。如果你需要进行更灵活的修改，请使用脚本。",button:"编辑 Body 重写规则…",kind:"body"},
                        {title:"端口转发",description:"将传入的 TCP 连接从本地监听端口转发到指定的目标地址。",button:"编辑端口转发规则…",kind:"forward"}
                    ]
                    SwirlGlassPanel {
                        id: card
                        required property var modelData
                        required property int index
                        Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;Layout.preferredWidth:1
                        Layout.columnSpan:index===4?grid.columns:1
                        Layout.preferredHeight:cardBody.implicitHeight+2*Theme.cardPadding
                        ColumnLayout {
                            id: cardBody
                            anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
                            SwirlText { text:card.modelData.title;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold }
                            SwirlText { Layout.fillWidth:true;text:card.modelData.description;color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WordWrap }
                            Item { Layout.fillHeight:true }
                            RowLayout {
                                Layout.fillWidth:true
                                SwirlText { Layout.fillWidth:true;text:captureProvider.rewriteRules.filter(r=>r.kind===card.modelData.kind).length+" 条规则"+(captureProvider.rewriteEnabled?"生效中":"已停用");color:Theme.muted;font.pixelSize:Theme.fontSize(11) }
                                SwirlButton { objectName:"rewriteEditor-"+card.modelData.kind;text:card.modelData.button;onClicked:page.Window.window.openRewriteEditor(card.modelData.kind,card.modelData.title) }
                            }
                        }
                    }
                }
            }
            SwirlText { text:"以上计数包含了模块中的规则。";color:Theme.muted;font.pixelSize:Theme.fontSize(11) }
        }
    }
}
