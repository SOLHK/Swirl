import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string selected:"局域网设备"
    readonly property var modules:["局域网设备","网关模式","DHCP 服务","端口转发","远程设备","网络接口"]
    property var records:[
        {id:"d1",name:"示例电脑",address:"192.0.2.10",interface:"以太网（模拟）",status:"Demo"},
        {id:"d2",name:"示例平板",address:"192.0.2.11",interface:"Wi-Fi（模拟）",status:"Demo"},
        {id:"d3",name:"示例路由器",address:"192.0.2.1",interface:"网关（模拟）",status:"Demo"}
    ]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:15
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:126
            RowLayout {
                anchors.fill:parent; anchors.margins:19; spacing:17
                SwirlIcon { name:"network"; size:35; color:Theme.orange }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:7
                    Text { text:"网关与设备"; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                    Text { text:"高级系统集成功能后续开发，目前没有设备发现、DHCP 或实际路由服务。"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                }
                SwirlStatusBadge { label:"Windows 后续功能规划"; tone:"warning" }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:7
            Repeater {
                model:page.modules
                SwirlButton { text:modelData; quiet:page.selected!==modelData; onClicked:page.selected=modelData }
            }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.records
                    columns:[{key:"name",label:"设备 / 接口",w:238},{key:"address",label:"IP",w:150},
                             {key:"interface",label:"网络",w:204},{key:"status",label:"状态",w:100}]
                    onRowSelected:function(r){AppState.notice("设备详情"+r.name)}
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:315; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:19; spacing:13
                    Text { text:page.selected; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:"暂不可用"; tone:"warning" }
                    Text {
                        text:page.selected==="DHCP 服务"?
                            "后续将支持 DHCP 地址池、租约记录及网关保留地址。":
                            page.selected==="端口转发"?
                            "预览转发规则、内网 IP 映射、协议和端口范围。":
                            page.selected==="远程设备"?
                            "远程设备配对、权限和流量策略尚未实现。":
                            page.selected==="网络接口"?
                            "后续提供网卡列表、统计信息及路由数据。":
                            page.selected==="网关模式"?
                            "网络网关与路由模式仍需 Windows 平台能力支持。":
                            "局域网设备发现需要用户明确授权。"
                        color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
                    }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    Text { text:"配置界面模拟"; color:Theme.muted; font.pixelSize:10 }
                    Text { text:"网卡"; color:Theme.muted; font.pixelSize:11 }
                    SwirlComboBox { Layout.fillWidth:true; model:["以太网（示例）","Wi-Fi（示例）","自定义网卡"] }
                    Text { text:"设备标签"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { Layout.fillWidth:true; placeholderText:"设备名称" }
                    Text { text:"内网子网"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { Layout.fillWidth:true; text:"192.0.2.0/24" }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"预览设置"; onClicked:AppState.notice("网关配置") }
                    SwirlButton { text:"启用功能"; enabled:false; primary:true }
                }
            }
        }
    }
}