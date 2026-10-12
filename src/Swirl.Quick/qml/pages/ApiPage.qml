import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string tab:"API 管理"
    property var routes:[]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(112)
            RowLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(20); spacing:Theme.dp(16)
                SwirlIcon { name:"terminal"; size:Theme.dp(31); color:Theme.accent }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:Theme.dp(6)
                    Text { text:"本地控制 API"; font.pixelSize:Theme.fontSize(20); color:Theme.text; font.weight:Font.DemiBold }
                    Text { text:"API 未启动 · 命令行仅提供参考"; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                }
                SwirlStatusBadge { label:"服务未启动"; tone:"warning" }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["API 管理","命令行指令","Permissions","访问日志"]
                SwirlButton { enabled:false; text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { enabled:false; text:"服务设置"; onClicked:settingsDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                SwirlDataTable {
                    visible:page.tab==="API 管理"
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.routes
                    columns:[{key:"method",label:"方法",w:100},{key:"path",label:"端点",w:260},
                             {key:"permission",label:"权限范围",w:160},{key:"status",label:"状态",w:112}]
                    onRowSelected:function(r){pathInput.text=r.path;methodInput.currentIndex=methodInput.model.indexOf(r.method)}
                }
                ColumnLayout {
                    visible:page.tab!=="API 管理"
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(15)
                    Text { text:AppState.zh(page.tab); color:Theme.text; font.pixelSize:Theme.fontSize(17); font.weight:Font.DemiBold }
                    Repeater {
                        model:[]
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:modelData; color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
                            SwirlButton { enabled:false; text:"预览"; onClicked:AppState.notice("命令行 / API ") }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(313); Layout.fillHeight:true
                ScrollView {
                    id:detailScroll0; anchors.fill:parent; anchors.margins:Theme.dp(17); clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                    width:detailScroll0.availableWidth; height:Math.max(implicitHeight,detailScroll0.availableHeight); spacing:Theme.dp(12)
                    Text { text:"请求"; color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlComboBox { id:methodInput; Layout.fillWidth:true; model:["GET","POST","PUT","DELETE"] }
                    SwirlTextField { id:pathInput; Layout.fillWidth:true; text:"/v1/status" }
                    Text { text:"JSON 响应预览"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:Theme.roundedRadius(width,height); color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:Theme.dp(9)
                            TextArea {
                                readOnly:true
                                text:"尚未实现；未发起 API 请求。"
                                color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(11)
                                wrapMode:Text.WrapAnywhere; background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    SwirlButton { enabled:false; text:"本地测试"; primary:true; onClicked:AppState.notice("未发送 API 请求") }
                }
                }
            }
        }
    }
    SwirlDialog {
        id:settingsDialog; title:"本地 API 设置"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:"监听地址"; color:Theme.text }
            SwirlTextField { Layout.fillWidth:true; text:"127.0.0.1"; readOnly:true }
            Text { text:"端口"; color:Theme.text }
            SwirlTextField { Layout.fillWidth:true; text:"6170"; validator:IntValidator { bottom:1024; top:65535 } }
            RowLayout {
                Layout.fillWidth:true
                Text { text:"允许 API 请求（仅界面开关）"; Layout.fillWidth:true; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                SwirlToggle { enabled:false;checked:false; onToggled:AppState.notice("API 监听服务") }
            }
            SwirlButton { enabled:false; text:"关闭"; Layout.alignment:Qt.AlignRight; onClicked:settingsDialog.close() }
        }
    }
}
