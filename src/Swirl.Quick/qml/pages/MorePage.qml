import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    readonly property var sections:[
        {title:"配置与连接",items:[
            {id:"proxies",title:"代理节点",sub:"连接节点与测试延迟",icon:"globe"},
            {id:"subscriptions",title:"订阅管理",sub:"导入与更新订阅",icon:"download"},
            {id:"profiles",title:"配置文件",sub:"查看与管理配置",icon:"document"}]},
        {title:"网络与记录",items:[
            {id:"connections",title:"连接记录",sub:"查看当前连接与流量",icon:"activity"},
            {id:"dns",title:"DNS",sub:"解析设置与查询",icon:"globe"},
            {id:"logs",title:"运行日志",sub:"查看事件与排查问题",icon:"document"}]},
        {title:"应用与工具",items:[
            {id:"settings",title:"应用设置",sub:"外观、引擎与偏好",icon:"settings"},
            {id:"toolbox",title:"网络工具",sub:"网络检测与连接诊断",icon:"gauge"},
            {id:"featurehub",title:"全部功能",sub:"浏览模块与配置草稿",icon:"grid"}]}
    ]
    ColumnLayout {
        anchors.fill:parent;anchors.margins:Theme.dp(20);spacing:Theme.dp(20)
        ColumnLayout {
            Layout.fillWidth:true;spacing:Theme.dp(6)
            Text {text:"更多";font.pixelSize:Theme.fontSize(32);font.weight:Font.DemiBold;color:Theme.text}
            Text {text:"配置、网络与应用设置";font.pixelSize:Theme.fontSize(14);color:Theme.muted}
        }
        SwirlGlassPanel {
            Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(92)
            RowLayout {
                anchors.fill:parent;anchors.margins:Theme.dp(20);spacing:Theme.dp(16)
                SwirlIcon {name:"globe";size:Theme.dp(28);color:AppState.systemProxyOn?Theme.statusGreen:Theme.muted}
                ColumnLayout {
                    Layout.fillWidth:true;spacing:Theme.dp(4)
                    Text {text:"系统代理";font.pixelSize:Theme.fontSize(17);font.weight:Font.DemiBold;color:Theme.text}
                    Text {text:engineController.systemProxy.error || (AppState.systemProxyOn?"已接管 · 127.0.0.1:"+engineController.activeProxyPort:(engineController.apiHealthy && engineController.activeNodeId.length>0)?"已连接节点，可开启系统流量转发":"连接节点后自动开启");color:engineController.systemProxy.error?Theme.orange:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;elide:Text.ElideRight}
                }
                SwirlToggle {objectName:"moreSystemProxyToggle";checked:AppState.systemProxyOn;enabled:(engineController.apiHealthy && engineController.activeNodeId.length>0)||AppState.systemProxyOn;onToggled:engineController.setSystemProxy(checked);Accessible.name:"系统代理开关"}
            }
        }
        ScrollView {
            id:scroll;Layout.fillWidth:true;Layout.fillHeight:true;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            ColumnLayout {
                width:scroll.availableWidth;spacing:Theme.dp(18)
                Repeater {
                    model:page.sections
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth:true;spacing:Theme.dp(10)
                        Text {text:modelData.title;color:Theme.muted;font.pixelSize:Theme.fontSize(13);leftPadding:Theme.dp(6)}
                        SwirlGlassPanel {
                            Layout.fillWidth:true;implicitHeight:rows.implicitHeight+Theme.dp(12)
                            ColumnLayout {
                                id:rows;anchors.left:parent.left;anchors.right:parent.right;anchors.margins:Theme.dp(6);y:Theme.dp(6);spacing:0
                                Repeater {
                                    model:modelData.items
                                    Button {
                                        required property var modelData
                                        objectName:"more-entry-"+modelData.id
                                        Layout.fillWidth:true;implicitHeight:Theme.dp(68);padding:Theme.dp(14);hoverEnabled:true
                                        background:Rectangle {radius:Theme.navigationRadius;color:parent.down?Theme.selected:parent.hovered?Theme.hover:"transparent";Behavior on color {ColorAnimation {duration:SwirlMotion.reduced?0:140}}}
                                        contentItem:RowLayout {
                                            spacing:Theme.dp(14)
                                            SwirlIcon {name:modelData.icon;size:Theme.dp(22);color:Theme.accent}
                                            ColumnLayout {
                                                Layout.fillWidth:true;spacing:Theme.dp(4)
                                                Text {text:modelData.title;color:Theme.text;font.pixelSize:Theme.fontSize(16)}
                                                Text {text:modelData.sub;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;elide:Text.ElideRight}
                                            }
                                            SwirlIcon {name:"chevron-right";size:Theme.dp(16);color:Theme.muted}
                                        }
                                        onClicked:AppState.navigate(modelData.id)
                                        Accessible.name:modelData.title
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
