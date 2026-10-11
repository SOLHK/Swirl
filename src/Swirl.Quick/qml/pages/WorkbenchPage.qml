import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property string pageId: "dashboard"
    property var features: ({
        dashboard:["速率历史","连接趋势","Latency","最近请求","域名排行","应用排行","策略使用情况"],
        profiles:["本地配置","远程配置","Editor","Import","导出","Backup","Versions"],
        policies:["手动选择","自动选择","Failover","负载均衡","SSID","策略详情","Relationships"],
        subscriptions:["Providers","Update","Scheduling","Quota","节点数量","History","Errors"],
        rules:["规则列表","Type","Target","Priority","Editor","Hits","规则测试"],
        dns:["Resolvers","DoH","DoT","DoQ","查询日志","Cache","Hosts","Fake-IP","IPv6","Tests"],
        traffic:["时间范围","Trends","节点流量","域名流量","进程流量","Protocols","上传 / 下载"],
        tls:["TLS 开关","证书状态","解密域名","排除域名","Sessions","Certificates","信任与撤销"],
        rewrite:["URL","Headers","Body","Redirect","Reject","模拟响应","Editor","命中次数"],
        map:["本地文件","远程 URL","Mappings","Editor","Enable","Preview"],
        breakpoint:["Rules","暂停队列","Headers","Body","Continue","Drop","修改并继续"],
        replay:["请求历史","Editor","Parameters","Response","Compare","执行历史"],
        modules:["Installed","Marketplace","Import","远程模块","Parameters","Versions","Updates"],
        automation:["定时任务","网络触发","Conditions","Actions","History","Editor"],
        api:["本地 API","Permissions","State","CLI","Examples","访问日志"],
        gateway:["Devices","Gateway","DHCP","端口转发","远程设备","Interfaces"],
        logs:["Level","Search","Filters","Details","Timeline","Clear","导出"]
    })
    readonly property var featureList:features[pageId]||[]
    property string selected:""
    property var records:[]
    Component.onCompleted:regenerate()
    onPageIdChanged:regenerate()
    function regenerate() {
        var result=[]
        for (var i=0;i<featureList.length;i++) {
            result.push({id:"demo-"+i,name:featureList[i],type:AppState.page(pageId).title,
                status:pageId==="gateway"?"规划中":i%2?"演示":"已启用",updated:"示例"})
        }
        records=result
        selected=featureList.length?featureList[0]:""
    }
    readonly property var filtered:records.filter(function(r){
        return r.name.toLowerCase().indexOf(search.text.toLowerCase())>=0 &&
            (filter.currentText==="全部"||r.status===filter.currentText)
    })
    ColumnLayout {
        anchors.fill:parent
        anchors.margins:24
        spacing:15
        SwirlGlassPanel {
            Layout.fillWidth:true
            Layout.preferredHeight:103
            RowLayout {
                anchors.fill:parent; anchors.margins:18
                ColumnLayout {
                    Layout.fillWidth:true; spacing:6
                    Text { text:AppState.page(page.pageId).title+"工作区"; color:Theme.text; font.pixelSize:20; font.weight:Font.DemiBold }
                    Text { text:featureList.length+" 个可交互功能区域，使用模拟数据"; color:Theme.muted; font.pixelSize:12 }
                }
                SwirlStatusBadge { label:page.pageId==="gateway"?"规划中":"界面演示"; tone:page.pageId==="gateway"?"warning":"accent" }
                SwirlButton { text:"新建"; primary:true; onClicked:addDialog.open() }
            }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true
            Layout.preferredHeight:228
            visible:pageId==="dashboard"||pageId==="traffic"
            ColumnLayout {
                anchors.fill:parent; anchors.margins:16
                Text { text:"流量数据 · 模拟样本"; color:Theme.text; font.pixelSize:15; font.weight:Font.DemiBold }
                SwirlTrafficChart { Layout.fillWidth:true; Layout.fillHeight:true }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"搜索演示记录" }
            SwirlComboBox { id:filter; model:["全部","已启用","演示","规划中"] }
            SwirlButton { text:"刷新"; onClicked:{page.regenerate();AppState.notice("刷新"+page.pageId)} }
            SwirlButton { text:"导出"; onClicked:AppState.notice("导出"+page.pageId) }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:15
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.filtered
                    columns:[{key:"name",label:"名称 / 操作",w:230},{key:"type",label:"模块",w:160},
                        {key:"status",label:"状态",w:105},{key:"updated",label:"时间",w:100}]
                    onRowSelected:function(record){page.selected=record.name}
                }
                SwirlEmptyState {
                    anchors.centerIn:parent
                    visible:page.filtered.length===0
                    headline:"没有匹配的记录"
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:310; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:11
                    Text { text:"模块详情"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text { text:page.selected; color:Theme.accent; font.pixelSize:14; font.weight:Font.DemiBold; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                    Text { text:"功能"; font.pixelSize:10; color:Theme.muted }
                    ScrollView {
                        Layout.fillWidth:true
                        Layout.preferredHeight:Math.min(260,page.height*0.34)
                        clip:true
                        ColumnLayout {
                            width:parent.width; spacing:4
                            Repeater {
                                model:page.featureList
                                RowLayout {
                                    Layout.fillWidth:true
                                    Text {
                                        Layout.fillWidth:true
                                        text:modelData; color:Theme.text; font.pixelSize:12; elide:Text.ElideRight
                                        MouseArea { anchors.fill:parent; onClicked:page.selected=modelData }
                                    }
                                    SwirlToggle { onToggled:AppState.notice(modelData) }
                                }
                            }
                        }
                    }
                    Text { text:"编辑器 / 输出"; color:Theme.muted; font.pixelSize:10 }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        color:Theme.field; radius:10; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:8
                            TextArea {
                                text:"# Swirl demonstration\nfeature: "+page.selected+"\nstatus: not connected\n\n# Changes will not affect system settings."
                                color:Theme.text
                                font.family:"Cascadia Code"; font.pixelSize:11
                                selectByMouse:true; wrapMode:Text.Wrap
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton { text:page.pageId==="replay"?"发送演示":"应用演示"; onClicked:AppState.notice(text) }
                        SwirlButton { text:"更多"; quiet:true; onClicked:AppState.notice("更多选项") }
                    }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog
        title:"创建演示记录"
        ColumnLayout {
            width:parent.width; spacing:13
            Text { text:"记录名称"; color:Theme.text }
            SwirlTextField { id:nameField; Layout.fillWidth:true; placeholderText:"请输入名称" }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"取消"; onClicked:addDialog.close() }
                SwirlButton {
                    text:"添加"; primary:true; enabled:nameField.text.trim().length>0
                    onClicked:{
                        page.records=page.records.concat([{id:"local-"+Date.now(),name:nameField.text.trim(),
                            type:AppState.page(page.pageId).title,status:"演示",updated:"现在"}])
                        nameField.text=""
                        addDialog.close()
                    }
                }
            }
        }
    }
}