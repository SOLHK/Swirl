import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string tool:"DNS 查询"
    property string result:"No test has been run.\nEnter a target and choose Run demo."
    property var tools:["DNS 查询","TCP 连通性","Traceroute","HTTP 请求","TLS 证书检查","端口检查","IP 地址查询","Whois","连接测试","网络接口信息"]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        Text { text:"选择网络诊断工具，结果均为本地模拟。"; color:Theme.muted; font.pixelSize:12 }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:15
            SwirlGlassPanel {
                Layout.preferredWidth:235; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:13; spacing:9
                    Text { text:"网络实用工具"; color:Theme.muted; font.pixelSize:11; leftPadding:8 }
                    ListView {
                        Layout.fillWidth:true; Layout.fillHeight:true; clip:true; spacing:4
                        model:page.tools
                        delegate:Rectangle {
                            width:ListView.view.width; height:40; radius:10
                            color:page.tool===modelData?Theme.selected:area.containsMouse?Theme.hover:"transparent"
                            RowLayout {
                                anchors.fill:parent; anchors.leftMargin:10
                                SwirlIcon { name:"tool"; size:17; color:Theme.muted }
                                Text { text:modelData; color:Theme.text; font.pixelSize:12; elide:Text.ElideRight; Layout.fillWidth:true }
                            }
                            MouseArea { id:area; anchors.fill:parent; hoverEnabled:true; onClicked:{page.tool=modelData;page.result="No test has been run.\nEnter a target and choose Run demo."} }
                        }
                    }
                }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:23; spacing:17
                    RowLayout {
                        Layout.fillWidth:true
                        ColumnLayout {
                            Layout.fillWidth:true
                            Text { text:page.tool; color:Theme.text; font.pixelSize:22; font.weight:Font.DemiBold }
                            Text { text:"独立检查面板"; color:Theme.muted; font.pixelSize:12 }
                        }
                        SwirlStatusBadge { label:"本地模拟"; tone:"accent" }
                    }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    Text { text:page.tool==="网络接口信息"?"网卡名称":"目标域名、地址或 URL"; color:Theme.text; font.pixelSize:13 }
                    SwirlTextField {
                        id:target; Layout.fillWidth:true
                        placeholderText:page.tool==="HTTP 请求"?"https://example.test/path":"example.test"
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlComboBox {
                            visible:page.tool==="HTTP 请求"
                            model:["GET","POST","PUT","DELETE","HEAD"]
                        }
                        SwirlTextField {
                            visible:page.tool==="端口检查" || page.tool==="TCP 连通性"
                            Layout.preferredWidth:130
                            placeholderText:"端口（443）"
                            validator:IntValidator { bottom:1; top:65535 }
                        }
                        Item { Layout.fillWidth:true }
                        SwirlButton {
                            text:"运行演示"; primary:true; iconName:"play"
                            enabled:target.text.trim().length>0
                            onClicked:{
                                page.result="模拟结果 · "+page.tool+"\n"+
                                            "目标："+target.text+"\n"+
                                            "Status: No network requests were made.\n"+
                                            "Backend connection: not configured.\n\n"+
                                            "此面板预留给未来的网络工具模块。"
                            }
                        }
                    }
                    Text { text:"结果"; color:Theme.muted; font.pixelSize:11; font.weight:Font.DemiBold }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        color:Theme.field; border.color:Theme.border; radius:12
                        ScrollView {
                            anchors.fill:parent; anchors.margins:12
                            TextArea {
                                readOnly:true; selectByMouse:true
                                text:page.result
                                color:Theme.text
                                wrapMode:Text.Wrap
                                font.family:"Cascadia Code"; font.pixelSize:12
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    SwirlButton { text:"复制结果"; onClicked:{demoProvider.copyText(page.result);AppState.toast="已复制诊断预览"} }
                }
            }
        }
    }
}