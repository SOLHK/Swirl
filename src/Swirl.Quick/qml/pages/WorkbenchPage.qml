import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string pageId: "dashboard"
    property var features: ({
        processes:["进程名称","活动连接","上传 / 下载","进程策略"],
        requestlogs:["请求时间","目标地址","HTTP 方法","响应状态","匹配规则"],
        dashboard:["速率历史","连接趋势","Latency","最近请求","域名排行","应用排行","策略使用情况"],
        profiles:["本地配置","远程配置","Editor","Import","导出","Backup","Versions"],
        policies:["手动选择","自动选择","Failover","负载均衡","SSID","策略详情","Relationships"],
        subscriptions:["Providers","Update","Scheduling","Quota","节点数量","History","Errors"],
        rules:["规则列表","Type","Target","Priority","Editor","Hits","规则测试"],
        dns:["Resolvers","DoH","DoT","DoQ","查询日志","Cache","Hosts","Fake-IP","IPv6","Tests"],
        traffic:["时间范围","Trends","节点流量","域名流量","进程流量","Protocols","上传 / 下载"],
        tls:["TLS 开关","证书状态","解密域名","排除域名","Sessions","Certificates","信任与撤销"],
        rewrite:["URL","Headers","Body","Redirect","Reject","响应","Editor","命中次数"],
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
    function regenerate() { records=[]; selected="" }
    readonly property var filtered:records.filter(function(r){
        return r.name.toLowerCase().indexOf(search.text.toLowerCase())>=0 &&
            (filter.currentText==="全部"||r.status===filter.currentText)
    })
    ColumnLayout {
        anchors.fill:parent
        anchors.margins:Theme.dp(24)
        spacing:Theme.dp(15)
        SwirlGlassPanel {
            Layout.fillWidth:true
            Layout.preferredHeight:Theme.dp(103)
            RowLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(18)
                ColumnLayout {
                    Layout.fillWidth:true; spacing:Theme.dp(6)
                    SwirlText {textRole:"pageTitle"; text:AppState.page(page.pageId).title+"工作区"; color:Theme.text; font.pixelSize:Theme.fontSize(20); font.weight:Font.DemiBold }
                    SwirlText { text:featureList.length+" 个功能区域研发中，保留布局供后续接入。"; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                }
                SwirlStatusBadge { label:"研发中"; tone:"warning" }
                SwirlButton { development:true; enabled:false; text:"新建"; primary:true; onClicked:addDialog.open() }
            }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true
            Layout.preferredHeight:Theme.dp(228)
            visible:pageId==="dashboard"||pageId==="traffic"
            ColumnLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(16)
                SwirlText { text:"流量详情 · 研发中"; color:Theme.text; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold }
                SwirlTrafficChart { Layout.fillWidth:true; Layout.fillHeight:true }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"搜索记录" }
            SwirlComboBox { id:filter; model:["全部","已启用","","规划中"] }
            SwirlButton { development:true; enabled:false; text:"刷新"; onClicked:AppState.notice("研发中") }
            SwirlButton { development:true; enabled:false; text:"导出"; onClicked:AppState.notice("导出"+page.pageId) }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(15)
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
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
                Layout.preferredWidth:Theme.dp(310); Layout.fillHeight:true
                ScrollView {
                    id:detailScroll0; anchors.fill:parent; anchors.margins:Theme.dp(17); clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                    width:detailScroll0.availableWidth; height:Math.max(implicitHeight,detailScroll0.availableHeight); spacing:Theme.dp(11)
                    SwirlText { text:"模块详情"; color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlText { text:page.selected; color:Theme.accent; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                    SwirlText { text:"功能"; font.pixelSize:Theme.fontSize(10); color:Theme.muted }
                    ScrollView {
                        Layout.fillWidth:true
                        Layout.preferredHeight:Math.floor(Math.min(Theme.dp(260),page.height*0.34))
                        clip:true
                        ColumnLayout {
                            width:parent.width; spacing:Theme.dp(4)
                            Repeater {
                                model:page.featureList
                                RowLayout {
                                    Layout.fillWidth:true
                                    SwirlText {
                                        Layout.fillWidth:true
                                        text:modelData; color:Theme.text; font.pixelSize:Theme.fontSize(12); elide:Text.ElideRight
                                        MouseArea { anchors.fill:parent; onClicked:page.selected=modelData }
                                    }
                                    SwirlToggle { enabled:false;checked:false; onToggled:AppState.notice(modelData) }
                                }
                            }
                        }
                    }
                    SwirlText { text:"编辑器 / 输出"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        color:Theme.field; radius:Theme.roundedRadius(width,height); border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:Theme.dp(8)
                            SwirlTextArea {
                                text:"# Swirl\nfeature: "+page.selected+"\nstatus: not connected\n\n# Changes will not affect system settings."
                                color:Theme.text
                                font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(11)
                                selectByMouse:true; wrapMode:Text.Wrap
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton { development:true; enabled:false; text:page.pageId==="replay"?"发送":"应用"; onClicked:AppState.notice(text) }
                        SwirlButton { development:true; enabled:false; text:"更多"; quiet:false; onClicked:AppState.notice("更多选项") }
                    }
                }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog
        title:"创建记录"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(13)
            SwirlText { text:"记录名称"; color:Theme.text }
            SwirlTextField { id:nameField; Layout.fillWidth:true; placeholderText:"请输入名称" }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { development:true; enabled:false; text:"取消"; onClicked:addDialog.close() }
                SwirlButton { development:true; enabled:false;
                    text:"添加"; primary:true;
                    onClicked:AppState.notice("研发中")
                }
            }
        }
    }
}
